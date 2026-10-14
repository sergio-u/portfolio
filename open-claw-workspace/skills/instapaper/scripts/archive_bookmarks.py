#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""Archive Instapaper bookmarks by ID.

Moves bookmarks to the archive folder. Supports batch processing with rate limiting.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from auth import InstapaperClient  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Archive Instapaper bookmarks.")
    parser.add_argument(
        "bookmark_ids",
        nargs="*",
        help="Bookmark IDs to archive (space-separated)",
    )
    parser.add_argument(
        "--from-file",
        help="JSON file containing an array of bookmark IDs or objects with bookmark_id field",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between API calls in seconds (default: 0.5)",
    )
    return parser.parse_args()


def archive_bookmarks(
    bookmark_ids: list[str],
    delay: float = 0.5,
) -> dict[str, Any]:
    """Archive a list of bookmarks.

    Returns dict with archived, failed, and total counts.
    """
    client = InstapaperClient()
    results: list[dict[str, Any]] = []

    for i, bid in enumerate(bookmark_ids):
        try:
            client.post("/api/1/bookmarks/archive", {"bookmark_id": str(bid)})
            results.append({"bookmark_id": bid, "status": "archived"})
        except Exception as exc:
            results.append({"bookmark_id": bid, "status": "failed", "error": str(exc)})

        if i < len(bookmark_ids) - 1:
            time.sleep(delay)

    archived = sum(1 for r in results if r["status"] == "archived")
    failed = sum(1 for r in results if r["status"] == "failed")

    return {
        "total": len(bookmark_ids),
        "archived": archived,
        "failed": failed,
        "results": results,
    }


def main() -> None:
    args = parse_args()

    bookmark_ids: list[str] = list(args.bookmark_ids or [])

    if args.from_file:
        with open(args.from_file) as f:
            data = json.load(f)
        for item in data:
            if isinstance(item, dict):
                bid = str(item.get("bookmark_id", ""))
                if bid:
                    bookmark_ids.append(bid)
            else:
                bookmark_ids.append(str(item))

    if not bookmark_ids:
        print("No bookmark IDs provided.", file=sys.stderr)
        sys.exit(1)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_ids: list[str] = []
    for bid in bookmark_ids:
        if bid not in seen:
            seen.add(bid)
            unique_ids.append(bid)

    try:
        result = archive_bookmarks(unique_ids, delay=args.delay)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
