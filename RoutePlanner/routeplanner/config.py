"""Load runtime config from .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    ors_api_key: str
    ors_base_url: str
    pelias_base_url: str
    walking_pace_kmh: float
    output_dir: Path
    graph_cache_dir: Path


def load() -> Config:
    load_dotenv()
    key = os.environ.get("ORS_API_KEY")
    if not key:
        raise SystemExit("ORS_API_KEY missing from .env")
    ors_url = os.environ.get(
        "ORS_BASE_URL", "https://api.heigit.org/openrouteservice/v2"
    ).rstrip("/")
    pelias_url = os.environ.get(
        "PELIAS_BASE_URL", "https://api.heigit.org/pelias/v1"
    ).rstrip("/")
    pace = float(os.environ.get("WALKING_PACE_KMH", "5.0"))
    out = Path(os.environ.get("OUTPUT_DIR", "./routes"))
    out.mkdir(parents=True, exist_ok=True)
    # OSM walking graphs are multi-MB Overpass downloads cached on disk so the
    # seed-bump retry loop doesn't re-fetch per attempt. Unlike the ORS rule
    # ("no caching, single-flight"), which is about a quota'd 100-500ms API,
    # caching the graph is mandatory for the OSM engine to be usable.
    graph_cache = Path(os.environ.get("OSM_CACHE_DIR", "./.osm_cache"))
    graph_cache.mkdir(parents=True, exist_ok=True)
    return Config(
        ors_api_key=key,
        ors_base_url=ors_url,
        pelias_base_url=pelias_url,
        walking_pace_kmh=pace,
        output_dir=out,
        graph_cache_dir=graph_cache,
    )
