#!/usr/bin/env python3
"""Reverse geocode coordinates or GPX waypoints via HeiGIT Pelias."""
from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import requests

GPX_NS = {"g": "http://www.topografix.com/GPX/1/1"}


@dataclass(frozen=True)
class Coord:
    lat: float
    lon: float


def parse_coord(value: str) -> Coord:
    parts = value.split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Expected 'lat,lon', got {value!r}")
    try:
        return Coord(lat=float(parts[0].strip()), lon=float(parts[1].strip()))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Could not parse coordinate {value!r}: {exc}") from exc


def coords_from_gpx(path: Path) -> list[tuple[str, Coord]]:
    root = ET.parse(path).getroot()
    named: list[tuple[str, Coord]] = []
    for index, elem in enumerate(root.findall("g:wpt", GPX_NS), 1):
        name = elem.findtext("g:name", default=f"wpt-{index}", namespaces=GPX_NS)
        named.append((name, Coord(lat=float(elem.attrib["lat"]), lon=float(elem.attrib["lon"]))))
    if named:
        return named

    for index, elem in enumerate(root.findall(".//g:trkpt", GPX_NS), 1):
        named.append((f"trkpt-{index}", Coord(lat=float(elem.attrib["lat"]), lon=float(elem.attrib["lon"]))))
    return named


def reverse_geocode(coord: Coord, api_key: str, base_url: str, *, layers: str | None = None, size: int = 1) -> list[dict]:
    params: dict[str, str | float | int] = {
        "point.lat": coord.lat,
        "point.lon": coord.lon,
        "size": size,
    }
    if layers:
        params["layers"] = layers
    response = requests.get(
        f"{base_url.rstrip('/')}/reverse",
        params=params,
        headers={"Authorization": api_key},
        timeout=15,
    )
    response.raise_for_status()
    return response.json().get("features", [])


def summarize_feature(feature: dict) -> dict[str, object]:
    props = feature.get("properties", {})
    geometry = feature.get("geometry", {})
    coords = geometry.get("coordinates") or [None, None]
    return {
        "label": props.get("label") or props.get("name") or "(no label)",
        "confidence": props.get("confidence"),
        "layer": props.get("layer"),
        "lat": coords[1],
        "lon": coords[0],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--coord", type=parse_coord, action="append", help="Coordinate as lat,lon. Repeatable.")
    source.add_argument("--gpx", type=Path, help="Read coordinates from GPX waypoints, or trackpoints if no waypoints exist.")
    parser.add_argument("--api-key", default=os.environ.get("ORS_API_KEY"), help="HeiGIT/ORS API key. Defaults to ORS_API_KEY.")
    parser.add_argument("--pelias-base-url", default=os.environ.get("PELIAS_BASE_URL", "https://api.heigit.org/pelias/v1"))
    parser.add_argument("--layers", default=None, help="Comma-separated Pelias layers, e.g. address,venue,locality.")
    parser.add_argument("--size", type=int, default=1, help="Results per coordinate.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.api_key:
        print("ORS_API_KEY missing; pass --api-key or set ORS_API_KEY.", file=sys.stderr)
        return 2

    named_coords = [(f"coord-{i}", coord) for i, coord in enumerate(args.coord or [], 1)]
    if args.gpx:
        named_coords = coords_from_gpx(args.gpx)
    if not named_coords:
        print("No coordinates found.", file=sys.stderr)
        return 1

    output = []
    try:
        for name, coord in named_coords:
            features = reverse_geocode(coord, args.api_key, args.pelias_base_url, layers=args.layers, size=args.size)
            results = [summarize_feature(feature) for feature in features]
            output.append({"name": name, "input": {"lat": coord.lat, "lon": coord.lon}, "results": results})
    except requests.HTTPError as exc:
        print(f"Pelias reverse-geocode error: {exc}", file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(f"Pelias request failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        for item in output:
            print(f"{item['name']}: {item['input']['lat']:.6f},{item['input']['lon']:.6f}")
            if not item["results"]:
                print("  No result")
            for result in item["results"]:
                conf = f" conf={result['confidence']}" if result.get("confidence") is not None else ""
                layer = f" [{result['layer']}]" if result.get("layer") else ""
                print(f"  {result['label']}{layer}{conf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
