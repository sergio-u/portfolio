"""Forward geocoding: text query -> coords via HeiGIT Pelias.

Standalone from the route planner. Run with:
    uv run python -m routeplanner.geocode "Espresso Vivace"
    uv run python -m routeplanner.geocode --near 47.61,-122.34 "400 Broad St"
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Sequence

import requests

from .config import load
from .geo import Coord


@dataclass(frozen=True)
class GeocodeResult:
    label: str
    coord: Coord
    confidence: float | None


def search(
    text: str,
    api_key: str,
    base_url: str,
    near: Coord | None = None,
    within_km: float | None = None,
    country: str | None = None,
    layers: str | None = None,
    size: int = 5,
) -> list[GeocodeResult]:
    params: dict[str, str | float | int] = {"text": text, "size": size}
    if near is not None:
        params["focus.point.lat"] = near.lat
        params["focus.point.lon"] = near.lon
    if within_km is not None:
        if near is None:
            raise ValueError("--within requires --near")
        params["boundary.circle.lat"] = near.lat
        params["boundary.circle.lon"] = near.lon
        params["boundary.circle.radius"] = within_km
    if country:
        params["boundary.country"] = country
    if layers:
        params["layers"] = layers
    resp = requests.get(
        f"{base_url}/search",
        params=params,
        headers={"Authorization": api_key},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    results: list[GeocodeResult] = []
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        lon, lat = feat["geometry"]["coordinates"]
        results.append(
            GeocodeResult(
                label=props.get("label", "(no label)"),
                coord=Coord(lat=lat, lon=lon),
                confidence=props.get("confidence"),
            )
        )
    return results


def _parse_coord(s: str) -> Coord:
    parts = s.split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Expected 'lat,lon', got {s!r}")
    return Coord(lat=float(parts[0].strip()), lon=float(parts[1].strip()))


def _parse_within(s: str) -> float:
    cleaned = s.strip().lower().removesuffix("km").strip()
    try:
        v = float(cleaned)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Could not parse radius {s!r}: {exc}")
    if v <= 0:
        raise argparse.ArgumentTypeError("--within must be > 0")
    return v


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="routeplanner.geocode",
        description="Look up coordinates for a place or address.",
    )
    p.add_argument("text", help="Free-text place name or address.")
    p.add_argument("--near", type=_parse_coord, default=None,
                   help="lat,lon to bias results toward (e.g. your start point).")
    p.add_argument("--within", type=_parse_within, default=None, metavar="KM",
                   help="Hard radius (km) around --near. Requires --near.")
    p.add_argument("--country", default=None, metavar="ISO",
                   help="Restrict to ISO 3166 country code (e.g. US, DE).")
    p.add_argument("--layers", default=None,
                   help="Comma-separated Pelias layers (e.g. venue,address).")
    p.add_argument("--size", type=int, default=5, help="Max results to show.")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    cfg = load()
    if args.within is not None and args.near is None:
        print("--within requires --near", file=sys.stderr)
        return 2
    try:
        results = search(
            text=args.text,
            api_key=cfg.ors_api_key,
            base_url=cfg.pelias_base_url,
            near=args.near,
            within_km=args.within,
            country=args.country,
            layers=args.layers,
            size=args.size,
        )
    except requests.HTTPError as exc:
        print(f"Pelias error: {exc}", file=sys.stderr)
        return 1

    if not results:
        print("No results.")
        return 1

    for i, r in enumerate(results, 1):
        conf = f"  (conf {r.confidence:.2f})" if r.confidence is not None else ""
        print(f"{i}. {r.label}{conf}")
        print(f"   {r.coord.lat:.6f},{r.coord.lon:.6f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
