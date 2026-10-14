"""Pure coordinate math. No external deps."""
from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_M = 6_371_000


@dataclass(frozen=True)
class Coord:
    lat: float
    lon: float


def haversine_m(a: Coord, b: Coord) -> float:
    lat1, lon1 = math.radians(a.lat), math.radians(a.lon)
    lat2, lon2 = math.radians(b.lat), math.radians(b.lon)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def bearing_deg(a: Coord, b: Coord) -> float:
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlon = math.radians(b.lon - a.lon)
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def offset_point(origin: Coord, bearing_d: float, distance_m: float) -> Coord:
    br = math.radians(bearing_d)
    lat1 = math.radians(origin.lat)
    lon1 = math.radians(origin.lon)
    dr = distance_m / EARTH_RADIUS_M
    lat2 = math.asin(
        math.sin(lat1) * math.cos(dr) + math.cos(lat1) * math.sin(dr) * math.cos(br)
    )
    lon2 = lon1 + math.atan2(
        math.sin(br) * math.sin(dr) * math.cos(lat1),
        math.cos(dr) - math.sin(lat1) * math.sin(lat2),
    )
    return Coord(lat=math.degrees(lat2), lon=math.degrees(lon2))


def midpoint(a: Coord, b: Coord) -> Coord:
    return Coord(lat=(a.lat + b.lat) / 2, lon=(a.lon + b.lon) / 2)


def path_length_m(coords: list[Coord]) -> float:
    return sum(haversine_m(a, b) for a, b in zip(coords[:-1], coords[1:]))
