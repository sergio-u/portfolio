"""Decide what waypoints to send to ORS.

Two output shapes:
- RoundTripSpec: pure variety loop, ORS picks waypoints from a seed.
- WaypointSpec: explicit anchor list (start, optional POIs, end), padded with
  random detour points when the straight-line length is below target.

(The "wander" loop style lived here too, but the OSM graph-walk engine
`osm_walk.py` superseded it; loops with no POIs/end now just use ORS round_trip.)
"""
from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass
from typing import Union

from .geo import (
    Coord,
    bearing_deg,
    haversine_m,
    midpoint,
    offset_point,
    path_length_m,
)


@dataclass
class RoundTripSpec:
    start: Coord
    length_m: float
    points: int
    seed: int


@dataclass
class WaypointSpec:
    coordinates: list[Coord]


Spec = Union[RoundTripSpec, WaypointSpec]


@dataclass
class PlanInputs:
    start: Coord
    target_minutes: float
    tolerance_minutes: float
    pace_kmh: float
    pois: list[Coord] | None = None
    end: Coord | None = None
    seed: int | None = None
    keep_order: bool = False
    no_detours: bool = False


def minutes_to_m(minutes: float, pace_kmh: float) -> float:
    return pace_kmh * 1000 * minutes / 60


def plan(inputs: PlanInputs) -> Spec:
    target_m = minutes_to_m(inputs.target_minutes, inputs.pace_kmh)
    seed = inputs.seed if inputs.seed is not None else random.randint(0, 1_000_000)

    if inputs.end is None and not inputs.pois:
        return _free_loop(inputs.start, target_m, seed)

    end = inputs.end if inputs.end is not None else inputs.start
    pois = list(inputs.pois or [])
    rng = random.Random(seed)
    ordered = _choose_order(inputs.start, pois, end, target_m, rng, inputs.keep_order)
    anchors = [inputs.start, *ordered, end]

    if inputs.no_detours:
        return WaypointSpec(coordinates=anchors)

    return _pad_with_detours(anchors, target_m, rng)


def _free_loop(start: Coord, target_m: float, seed: int) -> RoundTripSpec:
    points = 5 if target_m > 2000 else 3
    return RoundTripSpec(start=start, length_m=target_m, points=points, seed=seed)


def _choose_order(
    start: Coord,
    pois: list[Coord],
    end: Coord,
    target_m: float,
    rng: random.Random,
    keep_order: bool,
) -> list[Coord]:
    if keep_order or len(pois) <= 1:
        return list(pois)
    if len(pois) == 2:
        options = [list(pois), list(reversed(pois))]
        return min(options, key=lambda p: abs(path_length_m([start, *p, end]) - target_m))
    perms = list(itertools.permutations(pois))
    sampled = rng.sample(perms, k=min(20, len(perms)))
    best = min(sampled, key=lambda p: abs(path_length_m([start, *p, end]) - target_m))
    return list(best)


def _pad_with_detours(
    anchors: list[Coord], target_m: float, rng: random.Random
) -> WaypointSpec:
    current_m = path_length_m(anchors)
    if current_m >= target_m:
        return WaypointSpec(coordinates=anchors)

    deficit = target_m - current_m
    legs = list(zip(anchors[:-1], anchors[1:]))
    leg_lens = [haversine_m(a, b) for a, b in legs]
    total = sum(leg_lens) or 1.0

    final: list[Coord] = [anchors[0]]
    for (a, b), leg_len in zip(legs, leg_lens):
        share = leg_len / total
        new_target = leg_len + deficit * share
        d_sq = (new_target / 2) ** 2 - (leg_len / 2) ** 2
        if d_sq > 0 and leg_len > 0:
            # Cap to leg length so the detour can't fly absurdly far off course.
            d = min(math.sqrt(d_sq), leg_len)
            side = rng.choice([-1, 1])
            perp = (bearing_deg(a, b) + 90 * side) % 360
            final.append(offset_point(midpoint(a, b), perp, d))
        final.append(b)

    return WaypointSpec(coordinates=final)
