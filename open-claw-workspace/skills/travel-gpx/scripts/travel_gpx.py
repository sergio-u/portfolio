#!/usr/bin/env python3
"""Generate WorkOutDoors-friendly GPX files from a travel-day route spec."""
from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GPX_NS = "http://www.topografix.com/GPX/1/1"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
ET.register_namespace("", GPX_NS)
ET.register_namespace("xsi", XSI_NS)


@dataclass(frozen=True)
class Point:
    id: str
    name: str
    lat: float
    lon: float
    role: str = ""
    notes: str = ""
    address: str = ""
    optional: bool = False

    @property
    def description(self) -> str:
        parts = []
        if self.role:
            parts.append(f"Role: {self.role}")
        if self.address:
            parts.append(f"Address: {self.address}")
        if self.notes:
            parts.append(self.notes)
        if self.optional:
            parts.append("Optional / backup stop")
        return " | ".join(parts)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "route"


def load_spec(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError as exc:
            raise SystemExit("YAML input requires PyYAML; use JSON or install pyyaml.") from exc
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise SystemExit("Route spec must be a JSON/YAML object.")
    return data


def parse_points(spec: dict[str, Any]) -> dict[str, Point]:
    points: dict[str, Point] = {}
    for raw in spec.get("waypoints", []):
        if not isinstance(raw, dict):
            raise SystemExit("Each waypoint must be an object.")
        missing = [key for key in ("id", "name", "lat", "lon") if raw.get(key) in (None, "")]
        if missing:
            ident = raw.get("id") or raw.get("name") or "<unknown>"
            raise SystemExit(f"Waypoint {ident!r} is missing required field(s): {', '.join(missing)}")
        point = Point(
            id=str(raw["id"]),
            name=str(raw["name"]),
            lat=float(raw["lat"]),
            lon=float(raw["lon"]),
            role=str(raw.get("role") or ""),
            notes=str(raw.get("notes") or ""),
            address=str(raw.get("address") or ""),
            optional=bool(raw.get("optional", False)),
        )
        if point.id in points:
            raise SystemExit(f"Duplicate waypoint id: {point.id}")
        points[point.id] = point
    if not points:
        raise SystemExit("Route spec must include at least one waypoint.")
    return points


def variant_points(variant: dict[str, Any], points: dict[str, Point]) -> list[Point]:
    order = variant.get("waypoint_order") or variant.get("waypoints")
    if not isinstance(order, list) or not order:
        raise SystemExit(f"Variant {variant.get('id', '<unknown>')!r} needs a non-empty waypoint_order list.")
    missing = [str(point_id) for point_id in order if str(point_id) not in points]
    if missing:
        raise SystemExit(f"Variant {variant.get('id', '<unknown>')!r} references unknown waypoint id(s): {', '.join(missing)}")
    return [points[str(point_id)] for point_id in order]


def add_text(parent: ET.Element, tag: str, text: str | None) -> ET.Element | None:
    if not text:
        return None
    child = ET.SubElement(parent, f"{{{GPX_NS}}}{tag}")
    child.text = text
    return child


def build_gpx(
    *,
    route_name: str,
    route_desc: str,
    variant_id: str,
    points: list[Point],
    include_track: bool,
    include_route: bool,
) -> ET.ElementTree:
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    root = ET.Element(
        f"{{{GPX_NS}}}gpx",
        {
            "version": "1.1",
            "creator": "OpenClaw travel-gpx",
            f"{{{XSI_NS}}}schemaLocation": f"{GPX_NS} {GPX_NS}/gpx.xsd",
        },
    )
    metadata = ET.SubElement(root, f"{{{GPX_NS}}}metadata")
    add_text(metadata, "name", route_name)
    add_text(metadata, "desc", route_desc)
    add_text(metadata, "time", now_iso)

    for point in points:
        wpt = ET.SubElement(root, f"{{{GPX_NS}}}wpt", {"lat": f"{point.lat:.7f}", "lon": f"{point.lon:.7f}"})
        add_text(wpt, "name", point.name)
        add_text(wpt, "desc", point.description)
        add_text(wpt, "type", point.role or "travel_stop")

    if include_route:
        rte = ET.SubElement(root, f"{{{GPX_NS}}}rte")
        add_text(rte, "name", f"{route_name} ({variant_id})")
        for point in points:
            rtept = ET.SubElement(rte, f"{{{GPX_NS}}}rtept", {"lat": f"{point.lat:.7f}", "lon": f"{point.lon:.7f}"})
            add_text(rtept, "name", point.name)
            add_text(rtept, "desc", point.description)

    if include_track and len(points) >= 2:
        trk = ET.SubElement(root, f"{{{GPX_NS}}}trk")
        add_text(trk, "name", f"{route_name} ({variant_id})")
        add_text(trk, "desc", "Straight-line connector track between planned travel anchors; use as a flexible spine, not turn-by-turn routing.")
        trkseg = ET.SubElement(trk, f"{{{GPX_NS}}}trkseg")
        for point in points:
            ET.SubElement(trkseg, f"{{{GPX_NS}}}trkpt", {"lat": f"{point.lat:.7f}", "lon": f"{point.lon:.7f}"})

    ET.indent(root, space="  ")
    return ET.ElementTree(root)


def generate(spec_path: Path, output_dir: Path, track_mode: str, include_route: bool) -> list[Path]:
    spec = load_spec(spec_path)
    points = parse_points(spec)
    variants = spec.get("variants") or [{"id": "core", "waypoint_order": list(points.keys())}]
    if not isinstance(variants, list) or not variants:
        raise SystemExit("variants must be a non-empty list when provided.")

    base_name = str(spec.get("name") or spec_path.stem)
    city = str(spec.get("city") or "").strip()
    date = str(spec.get("date") or "").strip()
    theme = str(spec.get("theme") or "").strip()
    label_parts = [part for part in (date, city, theme or base_name) if part]
    file_prefix = slugify(" ".join(label_parts) or base_name)
    route_desc = str(spec.get("description") or "Travel-day GPX generated from route spec.")

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for raw_variant in variants:
        if not isinstance(raw_variant, dict):
            raise SystemExit("Each variant must be an object.")
        variant_id = slugify(str(raw_variant.get("id") or raw_variant.get("name") or "variant"))
        selected = variant_points(raw_variant, points)
        variant_name = str(raw_variant.get("name") or variant_id)
        route_name = f"{base_name} — {variant_name}"
        variant_track_mode = str(raw_variant.get("track_mode") or track_mode).lower()
        include_track = variant_track_mode not in {"none", "waypoints-only", "waypoint-only"}
        tree = build_gpx(
            route_name=route_name,
            route_desc=route_desc,
            variant_id=variant_id,
            points=selected,
            include_track=include_track,
            include_route=include_route,
        )
        output_path = output_dir / f"{file_prefix}-{variant_id}.gpx"
        tree.write(output_path, encoding="utf-8", xml_declaration=True)
        written.append(output_path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path, help="Route spec JSON/YAML file.")
    parser.add_argument("--output-dir", type=Path, default=Path("routes/travel"), help="Directory for generated GPX files.")
    parser.add_argument(
        "--track-mode",
        choices=["straight", "none", "waypoints-only"],
        default="straight",
        help="Use 'straight' for a simple connector track, or 'none'/'waypoints-only' for waypoint-only GPX.",
    )
    parser.add_argument("--include-route", action="store_true", help="Also include <rte>/<rtept> elements in addition to waypoints/track.")
    args = parser.parse_args(argv)

    written = generate(args.spec, args.output_dir, args.track_mode, args.include_route)
    print("Generated GPX files:")
    for path in written:
        print(f"- {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
