#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""List Instapaper bookmarks with optional time filtering.

Outputs JSON array of bookmarks. Use --hours to filter to recent saves.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

# Add lib to path for shared auth module
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from auth import InstapaperClient  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List Instapaper bookmarks.")
    parser.add_argument(
        "--hours",
        type=float,
        default=0,
        help="Only include bookmarks saved within the last N hours (0 = all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Max bookmarks to fetch from API (1-500, default 500)",
    )
    parser.add_argument(
        "--folder",
        default="unread",
        help="Folder to list: unread (default), starred, archive, or folder_id",
    )
    parser.add_argument(
        "--classify",
        action="store_true",
        help="Add a 'source_type' field based on URL domain",
    )
    return parser.parse_args()


SOURCE_PATTERNS: list[tuple[str, list[str]]] = [
    ("reddit", ["reddit.com"]),
    ("hackernews", ["news.ycombinator.com", "hn.algolia.com"]),
    ("youtube", ["youtube.com", "youtu.be"]),
    ("article", []),  # fallback
]

SKIP_PATTERNS: list[str] = [
    "youtube.com/shorts/",
]


def classify_url(url: str) -> str:
    """Classify a URL into a source type for downstream routing."""
    url_lower = url.lower()
    for source_type, domains in SOURCE_PATTERNS:
        for domain in domains:
            if domain in url_lower:
                return source_type
    return "article"


def list_bookmarks(
    hours: float = 0,
    limit: int = 500,
    folder: str = "unread",
    classify: bool = False,
) -> list[dict[str, Any]]:
    """Fetch bookmarks from Instapaper, optionally filtered by time."""
    client = InstapaperClient()

    params: dict[str, str] = {"limit": str(min(max(limit, 1), 500))}
    if folder:
        params["folder_id"] = folder

    resp = client.post("/api/1/bookmarks/list", params)
    data = resp.json()

    # API returns a mixed array; extract bookmarks only
    if isinstance(data, list):
        bookmarks = [item for item in data if item.get("type") == "bookmark"]
    elif isinstance(data, dict):
        bookmarks = data.get("bookmarks", [])
    else:
        bookmarks = []

    # Time filter
    if hours > 0:
        cutoff = time.time() - (hours * 3600)
        bookmarks = [b for b in bookmarks if b.get("time", 0) >= cutoff]

    # Skip YouTube Shorts and other non-extractable URLs
    bookmarks = [b for b in bookmarks if not any(p in b.get("url", "").lower() for p in SKIP_PATTERNS)]

    # Classify
    if classify:
        for b in bookmarks:
            b["source_type"] = classify_url(b.get("url", ""))

    return bookmarks


def main() -> None:
    args = parse_args()
    try:
        bookmarks = list_bookmarks(
            hours=args.hours,
            limit=args.limit,
            folder=args.folder,
            classify=args.classify,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(bookmarks, indent=2))


if __name__ == "__main__":
    main()
