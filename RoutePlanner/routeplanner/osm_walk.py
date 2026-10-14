"""OSM street-graph random-walk engine (`--engine osm`).

A true "drunken walk": instead of placing a handful of anchor waypoints and
letting a router connect them (which reads as a boring convex loop), we walk
the actual OSM walking network edge-by-edge with a seeded
RNG — no immediate U-turns, biased against retracing and against hugging a convex
boundary — then close onto the destination via shortest path. Exploration happens
at street granularity, so legs fill their footprint instead of tracing a circle.

A route is an ordered anchor list `[start, *pois, end]` (`end == start` for a
loop). Each leg between consecutive anchors wanders to fill its share of the
target length; the pure loop is the degenerate single-leg `a == b` case. A leg
can also be `direct` (shortest path, e.g. carrying groceries home).

Produces an `ors.RouteResult`, so the rest of the pipeline (export, scoring, the
cli retry loop) is unchanged. osmnx/networkx are imported lazily so the ORS-only
install never needs the heavy geo stack.
"""
from __future__ import annotations

import math
import random
from collections import Counter, deque
from pathlib import Path
from typing import Protocol

from . import ors, strategy
from .geo import EARTH_RADIUS_M, Coord, bearing_deg, haversine_m, midpoint
from .scoring import route_quality_breakdown

# Graph footprint: a loop of length L never strays more than ~L/2 from home, so
# 0.65 x target gives the outbound walk + shortest-path return comfortable room.
GRAPH_RADIUS_FACTOR = 0.65
GRAPH_RADIUS_MIN_M = 800.0
GRAPH_RADIUS_MAX_M = 12_000.0
GRAPH_BUCKET_M = 500.0          # round radius up to this, so nearby runs share a cache file
GRAPH_REUSE_NEAR_M = 200.0      # reuse a cached graph whose center is this close
GRAPH_ANCHOR_MARGIN_M = 1200.0  # wander room added beyond the farthest anchor from center

# One route_through() call generates many walks and returns the best by the
# quality score, so each retry-loop attempt is already de-circled and low-retrace.
# Cheap once the graph is cached, so we can afford a wide pool.
CANDIDATES_PER_CALL = 14
EDGE_REUSE_WEIGHT = 2.0         # penalty per meter of street walked more than once
SELF_CROSS_WEIGHT = 150.0      # penalty per self-intersection (tiny loops / crossings)
DOUBLEBACK_WEIGHT = 2.5        # penalty per meter of same-street out-and-back
DOUBLEBACK_NEAR_M = 25.0       # antiparallel legs closer than this = same street, not next block
DOUBLEBACK_COARSE_M = 20.0     # coarsen the route to this before pairing antiparallel legs
SPATIAL_REVISIT_M = 22.0       # in the walk, avoid stepping back this close to where we were
SPATIAL_REVISIT_MEMORY = 14    # how many recent coords the out-and-back check looks back over
TURN_CUE_DEG = 40.0            # heading change (after coarsening) that earns a turn waypoint
CUE_SEGMENT_M = 30.0           # coarsen the route to this before measuring turns
RETRACE_PENALTY = 3.0           # inflate already-walked edges on the return leg
RECENT_EDGES = 10               # anti-backtrack memory (drunken but self-avoiding-ish)
MAX_WALK_STEPS = 4000           # runaway guard
RETURN_FACTOR = 1.25            # streets-vs-straight-line factor for the leg-close estimate
# Mild, fixed outward drift on a loop leg: enough to leave home and not just churn
# the block, but low on purpose so the walk fills area rather than shooting out in
# an elongated lobe (which reads as circular). Reach controls distance; this stays.
# On a transit leg it's the *ceiling* of a progress-coupled pull toward B.
OUTBOUND_STRENGTH = 0.5
VISITED_NODE_PENALTY = 0.2      # discourage self-crossing / tiny block loops
ALLEY_DESIRABILITY = 0.08       # alleys, driveways, parking aisles, access-restricted
SERVICE_DESIRABILITY = 0.3      # generic service roads
# Transit legs meander inside a reach-scaled band around the straight A-B line, so
# the wander stays loosely on its way to B instead of straying far and overshooting.
CORRIDOR_MIN_M = 150.0
CORRIDOR_MAX_M = 1000.0
# OSM tags that mark a way we'd rather not route a walk down (penalised, not banned).
_AVOID_SERVICE = {"alley", "driveway", "parking_aisle", "drive-through"}
_AVOID_ACCESS = {"private", "no", "customers", "delivery", "permit"}
_REAL_WAY = {"footway", "residential", "pedestrian", "living_street"}


def route_through(
    start: Coord,
    pois: list[Coord],
    end: Coord | None,
    target_m: float,
    seed: int,
    reach: float,
    wiggle: float,
    cache_dir: Path,
    *,
    keep_order: bool = False,
    direct_return: bool = False,
) -> ors.RouteResult:
    """Generate a wandering route through `[start, *pois, end]` (end defaults to start).

    Every leg wanders to fill its share of `target_m`, except the final leg when
    `direct_return` is set (it takes the shortest path — carrying groceries home).

    Deterministic given its arguments (same purity contract as strategy.plan):
    the seed drives every random draw and the graph download is content-stable.
    """
    end = end if end is not None else start
    ordered = strategy._choose_order(
        start, list(pois), end, target_m, random.Random(seed), keep_order
    )
    anchors = [start, *ordered, end]

    graph = _load_graph(anchors, target_m, cache_dir)
    ox_nearest = _osmnx().distance.nearest_nodes
    # lon/lat order is crossed ONLY here, at the osmnx boundary — mirror the
    # lat-first discipline ors.py uses for the ORS boundary.
    anchor_nodes = [int(ox_nearest(graph, X=a.lon, Y=a.lat)) for a in anchors]

    direct = [False] * (len(anchors) - 1)
    if direct_return and direct:
        direct[-1] = True
    budgets = _allocate_budgets(graph, anchors, anchor_nodes, target_m, direct)

    best: ors.RouteResult | None = None
    best_nodes: list[int] | None = None
    best_score = math.inf
    for i in range(CANDIDATES_PER_CALL):
        rng = random.Random((seed << 8) + i)
        candidate = _one_candidate(
            graph, anchors, anchor_nodes, budgets, direct, rng, reach, wiggle
        )
        if candidate is None:
            continue
        result, full_nodes = candidate
        score = _candidate_score(graph, result, full_nodes, target_m)
        if score < best_score:
            best, best_nodes, best_score = result, full_nodes, score
    if best is None or best_nodes is None:
        raise RuntimeError("OSM walk produced no route (graph too sparse near an anchor?)")
    best.debug = _quality_metrics(graph, best, best_nodes, target_m, best_score)
    return best


def route_loop(
    start: Coord,
    target_m: float,
    seed: int,
    reach: float,
    wiggle: float,
    cache_dir: Path,
) -> ors.RouteResult:
    """A pure home loop: the degenerate `[start, start]` anchored route."""
    return route_through(start, [], None, target_m, seed, reach, wiggle, cache_dir)


def _allocate_budgets(
    graph, anchors: list[Coord], anchor_nodes: list[int], target_m: float, direct: list[bool]
) -> list[float]:
    """Per-leg target length. Direct legs claim their real shortest-path length;
    wander legs split the remainder proportional to their straight-line share.

    Floored at each leg's own straight line (a leg can't be shorter than that).
    When the anchors' straight-line sum already exceeds target the route comes out
    long — the honest "geographically infeasible" case the cli surfaces as
    best-effort, never a silent target bump.
    """
    straights = [haversine_m(a, b) for a, b in zip(anchors[:-1], anchors[1:])]
    budgets = [0.0] * len(straights)
    direct_len = 0.0
    for i, is_direct in enumerate(direct):
        if is_direct:
            path = _shortest_path(graph, anchor_nodes[i], anchor_nodes[i + 1], set())
            budgets[i] = _path_edge_length(graph, path) if path else straights[i]
            direct_len += budgets[i]

    wander = [i for i in range(len(straights)) if not direct[i]]
    if not wander:
        return budgets
    remaining = max(0.0, target_m - direct_len)
    weight_total = sum(straights[i] for i in wander)
    for i in wander:
        share = straights[i] / weight_total if weight_total > 0 else 1.0 / len(wander)
        budgets[i] = max(straights[i], remaining * share)
    return budgets


def _one_candidate(
    graph,
    anchors: list[Coord],
    anchor_nodes: list[int],
    budgets: list[float],
    direct: list[bool],
    rng: random.Random,
    reach: float,
    wiggle: float,
) -> tuple[ors.RouteResult, list[int]] | None:
    """Walk every leg with one seeded rng and stitch them into a single route."""
    full_nodes = [anchor_nodes[0]]
    for i in range(len(anchor_nodes) - 1):
        leg = _one_leg(
            graph, anchor_nodes[i], anchor_nodes[i + 1],
            anchors[i], anchors[i + 1], budgets[i], direct[i], rng, reach, wiggle,
        )
        if leg is None or len(leg) < 2:
            return None
        full_nodes.extend(leg[1:])
    if len(full_nodes) < 3:
        return None

    polyline = _assemble_polyline(graph, full_nodes)
    if len(polyline) < 3:
        return None
    length_m = _path_edge_length(graph, full_nodes)
    cues = _turn_cues(graph, full_nodes)
    return (
        ors.RouteResult(polyline=polyline, length_m=length_m, steps=[], turn_cues=cues),
        full_nodes,
    )


def _one_leg(
    graph,
    a_node: int,
    b_node: int,
    a_coord: Coord,
    b_coord: Coord,
    leg_budget: float,
    direct: bool,
    rng: random.Random,
    reach: float,
    wiggle: float,
) -> list[int] | None:
    """Node sequence for one leg: direct, a pure loop (a == b), or transit (a != b)."""
    if direct:
        return _shortest_path(graph, a_node, b_node, set())
    if a_node == b_node:
        return _loop_leg(graph, a_node, a_coord, leg_budget, rng, reach, wiggle)
    return _transit_leg(graph, a_node, b_node, a_coord, b_coord, leg_budget, rng, reach, wiggle)


def _loop_leg(
    graph, start_node: int, start: Coord, leg_budget: float,
    rng: random.Random, reach: float, wiggle: float,
) -> list[int] | None:
    # Wandering near home keeps a tiny home leg -> a compact dense loop; heading
    # out -> a wider one. Stop once walked + estimated home leg hits the (jittered)
    # budget, so total length lands near target without a systematic undershoot.
    stop_target_m = leg_budget * rng.uniform(0.92, 1.02)
    # reach sets how far the walk may range from home: low = compact, winds back on
    # itself (dense, space-filling); high = roams wide.
    max_home_radius_m = _clamp(leg_budget * (0.18 + 0.30 * reach), 300.0, 6000.0)
    cap = _RadiusCap(start, max_home_radius_m)

    nodes = _walk_out(
        graph, start_node, start, stop_target_m, rng, wiggle,
        bias_sign=-1.0, cap=cap, progress_pull=False,
    )
    if len(nodes) < 2:
        return None
    used = {frozenset((u, v)) for u, v in zip(nodes[:-1], nodes[1:])}
    home_path = _shortest_path(graph, nodes[-1], start_node, used)
    if home_path is None:
        return None
    return nodes + home_path[1:]


def _transit_leg(
    graph, a_node: int, b_node: int, a_coord: Coord, b_coord: Coord,
    leg_budget: float, rng: random.Random, reach: float, wiggle: float,
) -> list[int] | None:
    stop_target_m = leg_budget * rng.uniform(0.92, 1.02)
    width = _clamp(
        haversine_m(a_coord, b_coord) * (0.25 + 0.6 * reach), CORRIDOR_MIN_M, CORRIDOR_MAX_M
    )
    cap = _SegmentCap(a_coord, b_coord, width)

    nodes = _walk_out(
        graph, a_node, b_coord, stop_target_m, rng, wiggle,
        bias_sign=1.0, cap=cap, progress_pull=True,
    )
    used = {frozenset((u, v)) for u, v in zip(nodes[:-1], nodes[1:])}
    tail = _shortest_path(graph, nodes[-1], b_node, used)
    if tail is None:
        return None
    return nodes + tail[1:]


def _quality_metrics(
    graph, result: ors.RouteResult, nodes: list[int], target_m: float, score: float
) -> dict[str, float]:
    """The decision-relevant numbers for the chosen route, for --debug-score.

    These are the exact signals selection used (not the geometric self_overlap
    proxy), so an agent reading them sees why this route won.
    """
    breakdown = route_quality_breakdown(result.polyline)
    alley_m = 0.0
    for u, v in zip(nodes[:-1], nodes[1:]):
        attrs = _min_length_edge(graph, u, v)
        if _edge_desirability(attrs) < 1.0:
            alley_m += attrs.get("length", 0.0)
    return {
        "score": score,
        "length_miss_m": result.length_m - target_m,
        "retrace_m": _repeated_edge_m(graph, nodes),
        "doubleback_m": _doubleback_m(result.polyline),
        "crossings": float(_self_intersections(nodes)),
        "alley_pct": alley_m / result.length_m * 100 if result.length_m else 0.0,
        "circular": breakdown["circular"],
        "straight_run": breakdown["straight_run"],
        "turn_cues": float(len(result.turn_cues or [])),
    }


def _candidate_score(
    graph, result: ors.RouteResult, full_nodes: list[int], target_m: float
) -> float:
    """Lower is better: length miss dominates; retrace and shape break ties.

    Uses the graph's EXACT repeated-edge meters instead of scoring's geometric
    self_overlap proxy — the proxy can't tell walking a street twice (bad) from
    an adjacent street one block over (good), but the graph knows the real edges.
    """
    breakdown = route_quality_breakdown(result.polyline)
    reuse_m = _repeated_edge_m(graph, full_nodes)
    crossings = _self_intersections(full_nodes)
    return (
        abs(result.length_m - target_m) * 4
        + reuse_m * EDGE_REUSE_WEIGHT
        + crossings * SELF_CROSS_WEIGHT
        + _doubleback_m(result.polyline) * DOUBLEBACK_WEIGHT
        + breakdown["circular"]
        + breakdown["straight_run"]
    )


def _self_intersections(nodes: list[int]) -> int:
    """Count interior nodes visited more than once (tiny loops / self-crossings)."""
    interior = Counter(nodes[1:-1])
    return sum(count - 1 for count in interior.values() if count > 1)


def _doubleback_m(coords: list[Coord]) -> float:
    """Meters of same-street out-and-back: antiparallel legs running close together.

    The proximity threshold is the discriminator that exact edge-reuse and node
    revisits miss: walking up a street and back down its *opposite sidewalk* uses
    distinct edges/nodes but is an unnatural out-and-back, whereas covering the
    *next street over* (~a block away) is good. Antiparallel + within
    DOUBLEBACK_NEAR_M catches the former without flagging the latter.
    """
    coarse = _coarsen(coords, DOUBLEBACK_COARSE_M)
    legs = [
        (midpoint(a, b), bearing_deg(a, b), haversine_m(a, b))
        for a, b in zip(coarse[:-1], coarse[1:])
    ]
    penalty = 0.0
    for i, (mid_i, bearing_i, len_i) in enumerate(legs):
        for mid_j, bearing_j, len_j in legs[i + 3:]:
            if _angle_diff(bearing_i, bearing_j) < 150.0:
                continue
            if haversine_m(mid_i, mid_j) < DOUBLEBACK_NEAR_M:
                penalty += min(len_i, len_j)
    return penalty


def _repeated_edge_m(graph, nodes: list[int]) -> float:
    """Meters of street walked more than once (exact, direction-agnostic)."""
    counts = Counter(frozenset((u, v)) for u, v in zip(nodes[:-1], nodes[1:]))
    return sum(
        _edge_length(graph, *edge) * (count - 1)
        for edge, count in counts.items()
        if count > 1 and len(edge) == 2
    )


# --------------------------------------------------------------------------- #
# Random walk
# --------------------------------------------------------------------------- #

def _walk_out(
    graph,
    start_node: int,
    anchor: Coord,
    stop_target_m: float,
    rng: random.Random,
    wiggle: float,
    bias_sign: float,
    cap: _Cap,
    progress_pull: bool,
) -> list[int]:
    """Edge-by-edge seeded walk until walked + estimated close-onto-anchor leg hits
    the budget. `anchor` is what the walk drifts relative to and closes onto:
    home (drift away, `bias_sign=-1`) for a loop, the destination B (drift toward,
    `bias_sign=+1`) for a transit leg.
    """
    recent: deque[frozenset] = deque(maxlen=RECENT_EDGES)
    visited: set[frozenset] = set()
    visited_nodes: set[int] = {start_node}
    recent_coords: deque[Coord] = deque(maxlen=SPATIAL_REVISIT_MEMORY)
    nodes = [start_node]
    current = start_node
    prev: int | None = None
    walked_m = 0.0

    for _ in range(MAX_WALK_STEPS):
        cur_c = _node_coord(graph, current)
        close_leg_m = RETURN_FACTOR * haversine_m(cur_c, anchor)
        if walked_m + close_leg_m >= stop_target_m:
            break
        neighbors = list(graph.successors(current))
        candidates = [n for n in neighbors if n != prev] or neighbors
        if not candidates:
            break
        # On a transit leg the pull toward B ramps from ~0 (budget plentiful: free
        # meander, burn the slack) to OUTBOUND_STRENGTH+ as the remaining budget
        # shrinks toward the straight-line-to-B (commit to arriving). A loop leg
        # uses the fixed outward drift.
        if progress_pull:
            remaining = max(stop_target_m - walked_m, 1.0)
            pull = OUTBOUND_STRENGTH * _clamp(close_leg_m / remaining, 0.0, 1.5)
        else:
            pull = OUTBOUND_STRENGTH
        weights = [
            _step_weight(
                graph, current, prev, nbr, recent, visited, visited_nodes,
                recent_coords, wiggle, anchor, bias_sign, pull, cap,
            )
            for nbr in candidates
        ]
        chosen = rng.choices(candidates, weights=weights, k=1)[0]
        walked_m += _edge_length(graph, current, chosen)
        edge = frozenset((current, chosen))
        recent.append(edge)
        visited.add(edge)
        visited_nodes.add(chosen)
        recent_coords.append(cur_c)
        nodes.append(chosen)
        prev, current = current, chosen
    return nodes


def _step_weight(
    graph,
    current: int,
    prev: int | None,
    nbr: int,
    recent: deque,
    visited: set,
    visited_nodes: set,
    recent_coords: deque,
    wiggle: float,
    bias_anchor: Coord,
    bias_sign: float,
    pull_strength: float,
    cap: _Cap,
) -> float:
    cur_c = _node_coord(graph, current)
    nbr_c = _node_coord(graph, nbr)
    weight = 1.0

    # Don't re-walk the same street: a strong nudge for edges just used, a milder
    # one for any edge used earlier this route. Penalties, not bans — a short
    # reuse is still allowed when it's genuinely the only natural way through.
    edge = frozenset((current, nbr))
    if edge in recent:
        weight *= 0.15
    elif edge in visited:
        weight *= 0.5

    # Avoid self-crossing / tiny block loops: stepping onto an already-visited
    # node usually closes a small loop back over ground just covered.
    if nbr in visited_nodes:
        weight *= VISITED_NODE_PENALTY

    # Avoid same-street out-and-back: stepping close to where we were a few nodes
    # ago (e.g. up a street, back down its opposite sidewalk) reads as unnatural.
    # Skip the last two coords — those are just normal forward progress.
    if any(haversine_m(nbr_c, c) < SPATIAL_REVISIT_M for c in list(recent_coords)[:-2]):
        weight *= 0.2

    # Avoid alleys, driveways, parking aisles, and access-restricted ways.
    weight *= _edge_desirability(_min_length_edge(graph, current, nbr))

    # Avoid dead-end spurs: stepping into a node with no onward edge forces an
    # out-and-back over the same street (the dashed-stub pattern on the map).
    # Strong penalty, not a ban — a cul-de-sac with a view is still reachable.
    if not any(n != current for n in graph.successors(nbr)):
        weight *= 0.05

    # Directional bias: drift away from the anchor (loop, bias_sign<0) or toward it
    # (transit leg, bias_sign>0), by the cos of the angle to that bearing.
    target_bearing = bearing_deg(cur_c, bias_anchor)
    if bias_sign < 0:
        target_bearing = (target_bearing + 180.0) % 360.0
    align = math.cos(math.radians(_angle_diff(bearing_deg(cur_c, nbr_c), target_bearing)))
    weight *= max(0.05, 1.0 + pull_strength * align)

    # Wiggle: high prefers turns (switchbacks), low prefers going straight.
    if prev is not None:
        in_bearing = bearing_deg(_node_coord(graph, prev), cur_c)
        turn_norm = _angle_diff(bearing_deg(cur_c, nbr_c), in_bearing) / 180.0
        turn_pref = (1.0 - wiggle) * (1.0 - turn_norm) + wiggle * turn_norm
        weight *= 0.2 + turn_pref

    # Soft cap keeps the walk compact: a max radius from home (loop) or inside a
    # band around the straight A-B line (transit leg).
    if cap.outside(nbr_c):
        weight *= 0.1

    return weight


def _shortest_path(graph, source: int, target: int, used_edges: set) -> list[int] | None:
    """Shortest path source->target, avoiding already-walked edges and alleys/private ways."""
    nx = _networkx()

    def weight(u, v, data) -> float:
        attrs = data if "length" in data else min(
            data.values(), key=lambda d: d.get("length", math.inf)
        )
        cost = float(attrs.get("length", 0.0)) / max(_edge_desirability(attrs), 0.05)
        return cost * (RETRACE_PENALTY if frozenset((u, v)) in used_edges else 1.0)

    try:
        return nx.shortest_path(graph, source, target, weight=weight)
    except nx.NetworkXNoPath:
        try:
            return nx.shortest_path(graph, source, target, weight="length")
        except nx.NetworkXNoPath:
            return None


# --------------------------------------------------------------------------- #
# Soft caps (keep the walk loosely on course)
# --------------------------------------------------------------------------- #

class _Cap(Protocol):
    """A soft geographic bound: `outside(c)` is True where stepping is penalised."""

    def outside(self, coord: Coord) -> bool: ...


class _RadiusCap:
    """Loop leg: stay within a max radius of home."""

    def __init__(self, center: Coord, radius_m: float) -> None:
        self.center = center
        self.radius_m = radius_m

    def outside(self, coord: Coord) -> bool:
        return haversine_m(coord, self.center) > self.radius_m


class _SegmentCap:
    """Transit leg: stay within a band around the straight A-B line."""

    def __init__(self, a: Coord, b: Coord, width_m: float) -> None:
        self.a = a
        self.b = b
        self.width_m = width_m

    def outside(self, coord: Coord) -> bool:
        return _cross_track_m(self.a, self.b, coord) > self.width_m


def _cross_track_m(a: Coord, b: Coord, p: Coord) -> float:
    """Perpendicular distance (m) from p to the great-circle through a->b."""
    d13 = haversine_m(a, p) / EARTH_RADIUS_M
    delta = math.radians(bearing_deg(a, p) - bearing_deg(a, b))
    return abs(math.asin(_clamp(math.sin(d13) * math.sin(delta), -1.0, 1.0)) * EARTH_RADIUS_M)


# --------------------------------------------------------------------------- #
# Polyline / length / turn cues
# --------------------------------------------------------------------------- #

def _assemble_polyline(graph, nodes: list[int]) -> list[Coord]:
    polyline = [_node_coord(graph, nodes[0])]
    for u, v in zip(nodes[:-1], nodes[1:]):
        polyline.extend(_leg_geometry(graph, u, v)[1:])
    return polyline


def _leg_geometry(graph, u: int, v: int) -> list[Coord]:
    """Full street geometry from u to v (curved when osmnx kept a LineString)."""
    data = _min_length_edge(graph, u, v)
    u_c, v_c = _node_coord(graph, u), _node_coord(graph, v)
    geom = data.get("geometry") if data else None
    if geom is None:
        return [u_c, v_c]
    pts = [Coord(lat=y, lon=x) for x, y in geom.coords]
    if haversine_m(pts[0], u_c) > haversine_m(pts[-1], u_c):
        pts.reverse()
    return pts


def _path_edge_length(graph, nodes: list[int]) -> float:
    return sum(_edge_length(graph, u, v) for u, v in zip(nodes[:-1], nodes[1:]))


def _turn_cues(graph, nodes: list[int]) -> list[tuple[str, Coord]]:
    """Place a waypoint where the route makes a real turn.

    The walk graph is sidewalk-detailed, so one street intersection is several
    nodes (corners + crossings); measuring the turn per node would fire many
    cues for a single corner. So we first coarsen the route to ~CUE_SEGMENT_M
    segments (collapsing intersection micro-structure and gentle curves into
    straight runs), then place a cue wherever the coarsened path changes heading
    by more than TURN_CUE_DEG. TURN_CUE_DEG is the knob: lower = catches gentle /
    diagonal turns, higher = only obvious corners.
    """
    coarse = _coarsen([_node_coord(graph, n) for n in nodes], CUE_SEGMENT_M)
    cues: list[tuple[str, Coord]] = []
    for a, b, c in zip(coarse[:-2], coarse[1:-1], coarse[2:]):
        signed = (bearing_deg(b, c) - bearing_deg(a, b) + 540.0) % 360.0 - 180.0
        if abs(signed) >= TURN_CUE_DEG:
            cues.append((_cue_label(signed), b))
    return cues


def _coarsen(points: list[Coord], step_m: float) -> list[Coord]:
    """Keep points at least step_m apart, so micro-structure collapses to runs."""
    coarse = [points[0]]
    for point in points[1:]:
        if haversine_m(coarse[-1], point) >= step_m:
            coarse.append(point)
    if coarse[-1] != points[-1]:
        coarse.append(points[-1])
    return coarse


def _cue_label(signed_turn: float) -> str:
    side = "Right" if signed_turn >= 0 else "Left"
    mag = abs(signed_turn)
    if mag >= 160.0:
        return "U-Turn"
    if mag >= 110.0:
        return f"Sharp {side}"
    return side


# --------------------------------------------------------------------------- #
# Graph cache
# --------------------------------------------------------------------------- #

def _load_graph(anchors: list[Coord], target_m: float, cache_dir: Path):
    ox = _osmnx()
    ox.settings.cache_folder = str(cache_dir / "overpass")
    center = _bbox_center(anchors)
    # Cover every anchor (plus wander room) and at least the loop footprint, so a
    # far POI/end is never outside the downloaded disk.
    max_anchor_m = max((haversine_m(center, a) for a in anchors), default=0.0)
    radius_m = _clamp(
        max(max_anchor_m + GRAPH_ANCHOR_MARGIN_M, target_m * GRAPH_RADIUS_FACTOR),
        GRAPH_RADIUS_MIN_M, GRAPH_RADIUS_MAX_M,
    )

    cached = _find_cached_graph(center, radius_m, cache_dir)
    if cached is not None:
        return ox.io.load_graphml(cached)

    bucket_m = math.ceil(radius_m / GRAPH_BUCKET_M) * GRAPH_BUCKET_M
    graph = ox.graph.graph_from_point(
        (center.lat, center.lon), dist=bucket_m, network_type="walk"
    )
    path = cache_dir / f"walk_{center.lat:.3f}_{center.lon:.3f}_{int(bucket_m)}m.graphml"
    ox.io.save_graphml(graph, path)
    return graph


def _bbox_center(anchors: list[Coord]) -> Coord:
    lats = [a.lat for a in anchors]
    lons = [a.lon for a in anchors]
    return Coord(lat=(min(lats) + max(lats)) / 2, lon=(min(lons) + max(lons)) / 2)


def _find_cached_graph(center: Coord, radius_m: float, cache_dir: Path) -> Path | None:
    """Reuse a cached graph centered near `center` with a large-enough radius."""
    best: tuple[float, Path] | None = None
    for path in cache_dir.glob("walk_*m.graphml"):
        parsed = _parse_cache_center(path)
        if parsed is None:
            continue
        center_coord, bucket_m = parsed
        if bucket_m < radius_m:
            continue
        dist = haversine_m(center, center_coord)
        if dist <= GRAPH_REUSE_NEAR_M and (best is None or bucket_m < best[0]):
            best = (bucket_m, path)
    return best[1] if best else None


def _parse_cache_center(path: Path) -> tuple[Coord, float] | None:
    try:
        _, lat_s, lon_s, bucket_s = path.stem.split("_")
        return Coord(lat=float(lat_s), lon=float(lon_s)), float(bucket_s.rstrip("m"))
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Small graph helpers
# --------------------------------------------------------------------------- #

def _node_coord(graph, node: int) -> Coord:
    data = graph.nodes[node]
    return Coord(lat=data["y"], lon=data["x"])


def _min_length_edge(graph, u: int, v: int) -> dict:
    edges = graph.get_edge_data(u, v)  # {key: data} for a MultiDiGraph
    return min(edges.values(), key=lambda d: d.get("length", math.inf))


def _edge_length(graph, u: int, v: int) -> float:
    return float(_min_length_edge(graph, u, v).get("length", 0.0))


def _edge_desirability(attrs: dict) -> float:
    """How walkable an edge is: 1.0 for a normal street/sidewalk, low for an
    alley, driveway, parking aisle, or access-restricted way.

    A multiplier, applied as a penalty in the walk and as extra cost on the
    return path — never a ban, so an alley that's the only through-route still
    works.
    """
    desirability = 1.0
    if _tag_set(attrs.get("service")) & _AVOID_SERVICE:
        desirability *= ALLEY_DESIRABILITY
    if _tag_set(attrs.get("access")) & _AVOID_ACCESS:
        desirability *= ALLEY_DESIRABILITY
    highway = _tag_set(attrs.get("highway"))
    if "service" in highway and not (highway & _REAL_WAY):
        desirability *= SERVICE_DESIRABILITY
    return desirability


def _tag_set(value) -> set:
    """An OSM tag value normalized to a set (it may be missing, a str, or a list)."""
    if value is None:
        return set()
    return set(value) if isinstance(value, list) else {value}


def _angle_diff(a: float, b: float) -> float:
    diff = abs((b - a + 180.0) % 360.0 - 180.0)
    return min(diff, 360.0 - diff)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _osmnx():
    try:
        import osmnx  # noqa: PLC0415 (lazy: keep the heavy geo stack opt-in)
    except ImportError:
        raise SystemExit("--engine osm needs the osm extra: uv sync --extra osm")
    return osmnx


def _networkx():
    try:
        import networkx  # noqa: PLC0415
    except ImportError:
        raise SystemExit("--engine osm needs the osm extra: uv sync --extra osm")
    return networkx
