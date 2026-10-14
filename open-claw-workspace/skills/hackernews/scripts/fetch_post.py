#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""Fetch a HackerNews post and comments in a compact, LLM-friendly format."""

import argparse
import json
import re
import sys
from typing import Any

import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch a HackerNews post and comments as JSON."
    )
    parser.add_argument("url", help="HackerNews post URL or item ID")
    parser.add_argument(
        "--max-comments",
        type=int,
        default=50,
        help="Maximum number of top-level comments to include (default: 50)",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=2,
        help="Maximum comment depth to include (default: 2)",
    )
    parser.add_argument(
        "--min-points",
        type=int,
        default=0,
        help="Minimum points threshold for comments (default: 0)",
    )
    parser.add_argument(
        "--max-body",
        type=int,
        default=0,
        help="Truncate comment bodies to this many chars (0 = no limit)",
    )
    return parser.parse_args()


def extract_item_id(url_or_id: str) -> str:
    """Extract item ID from a URL or raw ID string."""
    if url_or_id.isdigit():
        return url_or_id

    match = re.search(r"(?:id=|items/)(\d+)", url_or_id)
    if match:
        return match.group(1)

    raise ValueError(
        f"Could not extract item ID from: {url_or_id}. "
        f"Expected: https://news.ycombinator.com/item?id=12345 or just '12345'"
    )


def _truncate(text: str, max_len: int) -> str:
    if max_len <= 0 or len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _is_junk(comment: dict[str, Any]) -> bool:
    """Filter deleted/dead comments."""
    if not comment.get("text"):
        return True
    author = comment.get("author")
    if author is None:
        return True
    return False


def collect_comments(
    comment: dict[str, Any],
    depth: int,
    max_depth: int,
    counter: dict[str, int],
    max_comments: int,
    min_points: int,
    max_body: int,
    out: list[dict[str, Any]],
) -> None:
    """Flatten comments into a list with depth indicators (matches reddit output shape)."""
    if counter["n"] >= max_comments:
        return
    if _is_junk(comment):
        return

    points = comment.get("points") or 0
    if min_points > 0 and points < min_points:
        return

    counter["n"] += 1
    body = comment.get("text", "")
    out.append({
        "author": comment.get("author"),
        "points": points,
        "depth": depth,
        "body": _truncate(body, max_body),
    })

    if depth < max_depth:
        for child in comment.get("children", []):
            collect_comments(
                child, depth + 1, max_depth, counter,
                max_comments, min_points, max_body, out,
            )


def fetch_hackernews_post(
    url_or_id: str,
    max_comments: int = 50,
    depth: int = 2,
    min_points: int = 0,
    max_body: int = 0,
) -> dict[str, Any]:
    """Fetch a HackerNews post with comments via the Algolia API.

    Raises:
        ValueError: If item ID cannot be extracted or API request fails.
    """
    item_id = extract_item_id(url_or_id)
    api_url = f"https://hn.algolia.com/api/v1/items/{item_id}"

    try:
        response = requests.get(api_url, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ValueError(f"Failed to fetch HackerNews item {item_id}: {exc}")

    data = response.json()

    if not data.get("id"):
        raise ValueError(f"Invalid response for item {item_id}")

    counter = {"n": 0}
    comments: list[dict[str, Any]] = []

    for child in data.get("children", []):
        collect_comments(
            child,
            depth=0,
            max_depth=depth,
            counter=counter,
            max_comments=max_comments,
            min_points=min_points,
            max_body=max_body,
            out=comments,
        )

    result: dict[str, Any] = {
        "id": data.get("id"),
        "title": data.get("title"),
        "author": data.get("author"),
        "points": data.get("points", 0),
        "created_at": data.get("created_at"),
        "url": data.get("url"),
        "type": data.get("type"),
        "num_comments": len(data.get("children", [])),
    }
    if data.get("text"):
        result["body"] = _truncate(data["text"], max_body)
    result["comments"] = comments

    return result


def main() -> None:
    args = parse_args()
    try:
        data = fetch_hackernews_post(
            url_or_id=args.url,
            max_comments=args.max_comments,
            depth=args.depth,
            min_points=args.min_points,
            max_body=args.max_body,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
