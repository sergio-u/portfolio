"""GPX writer and Apple/Google Maps deep-link builders."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .geo import Coord, haversine_m, path_length_m

if TYPE_CHECKING:
    from .ors import Step


def _xml_escape(s: str) -> str:
    """Escape XML special characters in text content."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# Map ORS instruction prefixes to short WorkOutDoors-style labels.
_TURN_SIMPLIFICATIONS = [
    ("Head ", "Start"),
    ("Go straight", "Straight"),
    ("Continue straight", "Straight"),
    ("Continue", "Continue"),
    ("Turn sharp right", "Sharp Right"),
    ("Turn sharp left", "Sharp Left"),
    ("Turn slight right", "Slight Right"),
    ("Turn slight left", "Slight Left"),
    ("Turn right", "Right"),
    ("Turn left", "Left"),
    ("Keep right", "Keep Right"),
    ("Keep left", "Keep Left"),
    ("Make a U-turn", "U-Turn"),
    ("Enter the roundabout", "Roundabout"),
    ("Leave the roundabout", "Exit Roundabout"),
    ("Stay on the roundabout", "Roundabout"),
    ("Take the stairs", "Stairs"),
    ("Go up the stairs", "Stairs Up"),
    ("Go down the stairs", "Stairs Down"),
    ("Follow", "Follow Path"),
    ("Arrive at", "End"),
]

_MIN_TURN_WAYPOINT_DISTANCE_M = 115.0
_MIN_ROUTINE_STEP_DISTANCE_M = 80.0
_MAX_TURN_WAYPOINTS = 24
_SKIP_TURN_LABELS = {"Start", "Continue", "Straight", "End"}
_ALWAYS_KEEP_TURN_LABELS = {
    "Sharp Right",
    "Sharp Left",
    "U-Turn",
    "Roundabout",
    "Exit Roundabout",
    "Stairs",
    "Stairs Up",
    "Stairs Down",
}


def _simplify_instruction(instruction: str) -> str:
    """Convert verbose ORS instruction to short turn label."""
    for prefix, label in _TURN_SIMPLIFICATIONS:
        if instruction.startswith(prefix):
            return label
    return instruction.split(",")[0][:20]


def write_gpx(
    coords: list[Coord],
    output_dir: Path,
    label: str,
    *,
    waypoints: list[tuple[str, Coord]] | None = None,
    steps: list["Step"] | None = None,
) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = output_dir / f"{ts}_{label}.gpx"
    pts = "\n".join(f'      <trkpt lat="{c.lat:.7f}" lon="{c.lon:.7f}"/>' for c in coords)

    # Build <wpt> elements: POI markers + turn-by-turn cues.
    wpt_lines: list[str] = []
    if waypoints:
        for name, c in waypoints:
            wpt_lines.append(
                f'  <wpt lat="{c.lat:.7f}" lon="{c.lon:.7f}">\n'
                f"    <name>{_xml_escape(name)}</name>\n"
                f"    <time>{now_iso}</time>\n"
                f"    <type>user</type>\n"
                f"  </wpt>"
            )
    if steps:
        for short, coord in _turn_waypoints(steps):
            wpt_lines.append(
                f'  <wpt lat="{coord.lat:.7f}" lon="{coord.lon:.7f}">\n'
                f"    <name>{_xml_escape(short)}</name>\n"
                f"    <time>{now_iso}</time>\n"
                f"    <type>user</type>\n"
                f"  </wpt>"
            )
    wpts = "\n".join(wpt_lines) + "\n" if wpt_lines else ""

    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="routeplanner" '
        'xmlns="http://www.topografix.com/GPX/1/1">\n'
        f"{wpts}"
        f"  <trk>\n    <name>{label}</name>\n    <trkseg>\n"
        f"{pts}\n"
        "    </trkseg>\n  </trk>\n</gpx>\n"
    )
    return path


def _turn_waypoints(steps: list["Step"]) -> list[tuple[str, Coord]]:
    # Skip first ("Head...") and last ("Arrive...") — covered by Start/End waypoints.
    # Skip "Continue"/"Straight" — no actual direction change.
    raw = [
        (_simplify_instruction(step.instruction), step.coord, step.distance_m)
        for step in (steps[1:-1] if len(steps) > 2 else steps)
    ]
    filtered = [
        (label, coord, distance_m)
        for label, coord, distance_m in raw
        if _should_keep_turn(label, distance_m)
    ]

    kept: list[tuple[str, Coord]] = []
    for label, coord, _distance_m in filtered:
        if kept and haversine_m(kept[-1][1], coord) < _MIN_TURN_WAYPOINT_DISTANCE_M:
            if label in _ALWAYS_KEEP_TURN_LABELS and kept[-1][0] not in _ALWAYS_KEEP_TURN_LABELS:
                kept[-1] = (label, coord)
            continue
        kept.append((label, coord))
    return _limit_turn_waypoints(kept)


def _should_keep_turn(label: str, distance_m: float) -> bool:
    if label in _SKIP_TURN_LABELS:
        return False
    return label in _ALWAYS_KEEP_TURN_LABELS or distance_m >= _MIN_ROUTINE_STEP_DISTANCE_M


def _limit_turn_waypoints(turns: list[tuple[str, Coord]]) -> list[tuple[str, Coord]]:
    if len(turns) <= _MAX_TURN_WAYPOINTS:
        return turns

    important = {
        index
        for index, (label, _coord) in enumerate(turns)
        if label in _ALWAYS_KEEP_TURN_LABELS
    }
    coords = [coord for _label, coord in turns]
    turn_span_m = path_length_m(coords)
    max_turns = max(8, min(_MAX_TURN_WAYPOINTS, round(turn_span_m / 240)))
    routine_budget = max(0, max_turns - len(important))
    routine_indexes = [index for index in range(len(turns)) if index not in important]

    if routine_budget <= 0:
        selected = sorted(important)[:max_turns]
    elif routine_budget >= len(routine_indexes):
        selected = sorted({*important, *routine_indexes})
    else:
        selected_routine = _evenly_spaced_indexes(routine_indexes, routine_budget)
        selected = sorted({*important, *selected_routine})

    return [turns[index] for index in selected]


def _evenly_spaced_indexes(indexes: list[int], count: int) -> list[int]:
    if count <= 0:
        return []
    if count == 1:
        return [indexes[len(indexes) // 2]]
    last = len(indexes) - 1
    return [indexes[round(i * last / (count - 1))] for i in range(count)]


def sample_for_preview(coords: list[Coord], n: int = 8) -> list[Coord]:
    """Evenly sample N points from a polyline so map URLs don't blow up.

    Duplicates are dropped (first occurrence wins) so palindromic polylines
    (e.g. home -> POI -> home) collapse to the outbound half.
    """
    if len(coords) <= n:
        samples = list(coords)
    else:
        indices = [round(i * (len(coords) - 1) / (n - 1)) for i in range(n)]
        samples = [coords[i] for i in indices]
    seen: set[Coord] = set()
    deduped: list[Coord] = []
    for s in samples:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped


def google_maps_url(waypoints: list[Coord]) -> str:
    """Path-style Google Maps directions URL with walking mode.

    Each waypoint is a path segment. This format closes loops cleanly when
    the first and last segments are identical (the api=1 query format
    misbehaves with origin == destination).
    """
    if len(waypoints) < 2:
        raise ValueError("Need at least 2 waypoints for a directions URL")
    path = "/".join(f"{c.lat},{c.lon}" for c in waypoints)
    return f"https://www.google.com/maps/dir/{path}/data=!4m2!4m1!3e2"
