"""Thin HTTP client for OpenRouteService foot-walking directions."""
from __future__ import annotations

from dataclasses import dataclass

import requests

from .geo import Coord
from .strategy import RoundTripSpec, Spec, WaypointSpec


@dataclass
class Step:
    """A single turn instruction from ORS."""
    coord: Coord
    instruction: str
    distance_m: float = 0.0


@dataclass
class RouteResult:
    polyline: list[Coord]
    length_m: float
    steps: list[Step]
    # Pre-resolved turn cues as (label, coord), set by engines that pick their
    # own waypoints (the OSM engine: one per >60deg turn) instead of relying on
    # export's distance-based filtering of `steps`. ORS leaves this None.
    turn_cues: list[tuple[str, Coord]] | None = None
    # Decision-relevant quality metrics for the chosen route (name -> value),
    # set by the OSM engine for --debug-score. ORS leaves this None.
    debug: dict[str, float] | None = None


def route(spec: Spec, api_key: str, base_url: str) -> RouteResult:
    """POST to ORS; return RouteResult with polyline, length, and turn steps.

    Raises requests.HTTPError on non-2xx; caller decides whether to retry.
    """
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
        "Accept": "application/geo+json, application/json",
    }
    url = f"{base_url}/directions/foot-walking/geojson"

    if isinstance(spec, RoundTripSpec):
        body = {
            "coordinates": [[spec.start.lon, spec.start.lat]],
            "options": {
                "round_trip": {
                    "length": spec.length_m,
                    "points": spec.points,
                    "seed": spec.seed,
                }
            },
        }
    elif isinstance(spec, WaypointSpec):
        body = {"coordinates": [[c.lon, c.lat] for c in spec.coordinates]}
    else:
        raise TypeError(f"Unknown spec type: {type(spec).__name__}")

    resp = requests.post(url, json=body, headers=headers, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    feature = data["features"][0]
    geometry = feature["geometry"]["coordinates"]  # [[lon, lat], ...]
    length_m = feature["properties"]["summary"]["distance"]
    polyline = [Coord(lat=lat, lon=lon) for lon, lat in geometry]

    # Extract turn-by-turn steps from segments.
    steps: list[Step] = []
    for segment in feature["properties"].get("segments", []):
        for step in segment.get("steps", []):
            wp_index = step["way_points"][0]
            coord = polyline[wp_index]
            steps.append(
                Step(
                    coord=coord,
                    instruction=step["instruction"],
                    distance_m=float(step.get("distance", 0.0)),
                )
            )

    return RouteResult(polyline=polyline, length_m=length_m, steps=steps)
