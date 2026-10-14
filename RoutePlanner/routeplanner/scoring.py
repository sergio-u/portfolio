"""Route quality scoring for wandering walks.

Deliberately small. The generator (osm_walk.py) is responsible for producing
interesting, non-convex geometry; scoring only applies cheap guardrails against
the failure modes that survive generation, and ranks candidates within an engine:

- out-and-back spurs / self-overlap (walking the same stretch twice),
- long featureless straight runs (which read as a commute, not a wander), and
- circular / boundary-hugging loops (a big convex blob that traces a perimeter
  and never explores its interior — the "boring circle" failure mode).

Kept small on purpose: heavy scoring collapses variety toward one "optimal"
shape, which is the opposite of what a wandering walk wants.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .geo import EARTH_RADIUS_M, Coord, bearing_deg, haversine_m, midpoint, path_length_m

COARSE_STEP_M = 90.0
STRAIGHT_RUN_M = 320.0
STRAIGHT_RUN_TURN_DEG = 20.0
SELF_OVERLAP_NEAR_M = 90.0
ANTIPARALLEL_TURN_DEG = 150.0

# Circularity guardrail. A loop's length divided by its convex-hull perimeter
# measures how much it fills its footprint vs. just tracing the boundary: a
# circle/convex blob sits near 1.0, a dense space-filling wander runs 1.5-1.8+.
# Empirically (the routes/ corpus) boring ORS round-trips land ~1.1-1.25 and the
# good wanders ~1.6-1.8, so we reward length well above the hull perimeter.
# Only applied to loops (start ~= end); a point-to-point route legitimately has a
# thin hull and must not be punished for it.
TARGET_HULL_RATIO = 1.6
CONVEXITY_WEIGHT = 0.6
LOOP_CLOSE_M = 150.0


def route_quality_penalty_m(coords: list[Coord]) -> float:
    """Total meters-equivalent quality penalty (sum of the breakdown)."""
    return sum(route_quality_breakdown(coords).values())


def route_quality_breakdown(coords: list[Coord]) -> dict[str, float]:
    """Per-guardrail penalties in meters-equivalent units, for --debug-score."""
    if len(coords) < 3:
        return {}
    legs = _coarse_legs(coords)
    if not legs:
        return {}
    return {
        "self_overlap": _self_overlap_penalty(legs),
        "straight_run": _straight_run_penalty(legs),
        "circular": _circular_penalty(coords),
    }


def _circular_penalty(coords: list[Coord]) -> float:
    """Penalize convex, boundary-hugging loops; reward interior-filling wanders.

    Returns 0 for non-loops (the hull ratio only means "boring" when the route
    closes back on itself) and for loops whose length already exceeds
    TARGET_HULL_RATIO x their convex-hull perimeter.
    """
    if haversine_m(coords[0], coords[-1]) > LOOP_CLOSE_M:
        return 0.0
    length_m = path_length_m(coords)
    hull_perimeter_m = _convex_hull_perimeter_m(coords)
    if hull_perimeter_m <= 0.0:
        return 0.0
    ratio = length_m / hull_perimeter_m
    return max(0.0, TARGET_HULL_RATIO - ratio) * length_m * CONVEXITY_WEIGHT


@dataclass(frozen=True)
class _Leg:
    a: Coord
    b: Coord
    length_m: float
    bearing: float


def _coarse_legs(coords: list[Coord]) -> list[_Leg]:
    points = _coarse_points(coords)
    legs: list[_Leg] = []
    for a, b in zip(points[:-1], points[1:]):
        length_m = haversine_m(a, b)
        if length_m >= COARSE_STEP_M * 0.5:
            legs.append(_Leg(a, b, length_m, bearing_deg(a, b)))
    return legs


def _coarse_points(coords: list[Coord]) -> list[Coord]:
    points = [coords[0]]
    distance_since_last = 0.0
    previous = coords[0]
    for coord in coords[1:]:
        distance_since_last += haversine_m(previous, coord)
        if distance_since_last >= COARSE_STEP_M:
            points.append(coord)
            distance_since_last = 0.0
        previous = coord
    if points[-1] != coords[-1]:
        points.append(coords[-1])
    return points


def _self_overlap_penalty(legs: list[_Leg]) -> float:
    """Penalize out-and-back spurs: legs that double back over earlier ground."""
    penalty = 0.0
    for previous, current in zip(legs[:-1], legs[1:]):
        if _turn_angle(previous.bearing, current.bearing) > ANTIPARALLEL_TURN_DEG:
            penalty += min(previous.length_m, current.length_m) * 1.5 + 150.0

    for i, first in enumerate(legs):
        first_midpoint = midpoint(first.a, first.b)
        for second in legs[i + 2:]:
            if _turn_angle(first.bearing, second.bearing) < ANTIPARALLEL_TURN_DEG:
                continue
            if haversine_m(first_midpoint, midpoint(second.a, second.b)) < SELF_OVERLAP_NEAR_M:
                penalty += min(first.length_m, second.length_m) * 1.1
    return penalty


def _straight_run_penalty(legs: list[_Leg]) -> float:
    """Penalize long near-collinear runs in ANY direction (incl. diagonals).

    Runs are measured against the bearing the run started at, so a gradual curve
    breaks into short runs and is not penalized; only genuinely straight stretches
    accumulate length.
    """
    penalty = 0.0
    run_m = 0.0
    run_start_bearing: float | None = None

    for leg in legs:
        if (
            run_start_bearing is not None
            and _turn_angle(run_start_bearing, leg.bearing) <= STRAIGHT_RUN_TURN_DEG
        ):
            run_m += leg.length_m
        else:
            penalty += _straight_run_overage(run_m)
            run_m = leg.length_m
            run_start_bearing = leg.bearing

    return penalty + _straight_run_overage(run_m)


def _straight_run_overage(run_m: float) -> float:
    return max(0.0, run_m - STRAIGHT_RUN_M) * 1.2


def _turn_angle(a: float, b: float) -> float:
    diff = abs((b - a + 180) % 360 - 180)
    return min(diff, 360 - diff)


def _convex_hull_perimeter_m(coords: list[Coord]) -> float:
    """Perimeter (m) of the convex hull of the route's points."""
    pts = _project_xy(coords)
    hull = _convex_hull(pts)
    if len(hull) < 3:
        return 0.0
    return sum(
        math.dist(hull[i], hull[(i + 1) % len(hull)]) for i in range(len(hull))
    )


def _project_xy(coords: list[Coord]) -> list[tuple[float, float]]:
    """Local equirectangular projection to meters, centered on the centroid.

    Distances are tiny (single-neighborhood) so the flat-earth error is
    negligible and lets us reuse plain planar convex-hull math.
    """
    lat0 = sum(c.lat for c in coords) / len(coords)
    lon0 = sum(c.lon for c in coords) / len(coords)
    cos_lat0 = math.cos(math.radians(lat0))
    return [
        (
            math.radians(c.lon - lon0) * cos_lat0 * EARTH_RADIUS_M,
            math.radians(c.lat - lat0) * EARTH_RADIUS_M,
        )
        for c in coords
    ]


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Andrew's monotone-chain convex hull (counter-clockwise, no repeat)."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]
