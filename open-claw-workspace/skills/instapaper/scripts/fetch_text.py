#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""Fetch the extracted text/HTML of an Instapaper bookmark via get_text API.

Returns the article content that Instapaper extracted and cleaned.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from auth import InstapaperClient  # noqa: E402
from utils import strip_html  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch article text for an Instapaper bookmark."
    )
    parser.add_argument(
        "bookmark_id",
        help="Instapaper bookmark ID",
    )
    parser.add_argument(
        "--strip-html",
        action="store_true",
        help="Strip HTML tags and return plain text",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=0,
        help="Truncate output to N characters (0 = no limit)",
    )
    return parser.parse_args()


def fetch_text(
    bookmark_id: str,
    strip: bool = False,
    max_chars: int = 0,
) -> dict[str, Any]:
    """Fetch article text for a bookmark.

    Returns dict with bookmark_id, content, content_type, and char_count.
    """
    client = InstapaperClient()

    resp = client.post("/api/1/bookmarks/get_text", {"bookmark_id": bookmark_id})

    content = resp.text
    content_type = "html"

    if strip:
        content = strip_html(content)
        content_type = "text"

    if max_chars > 0 and len(content) > max_chars:
        content = content[:max_chars] + "\n\n[...truncated]"

    return {
        "bookmark_id": bookmark_id,
        "content_type": content_type,
        "char_count": len(content),
        "content": content,
    }


def main() -> None:
    args = parse_args()
    try:
        result = fetch_text(
            bookmark_id=args.bookmark_id,
            strip=args.strip_html,
            max_chars=args.max_chars,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
