#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "trafilatura"]
# ///
"""Extract article content with fallback chain.

Tries Instapaper get_text first, falls back to trafilatura.
Detects YouTube-embed wrapper pages and signals for transcript extraction.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Add lib to path for shared auth module
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from utils import strip_html  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract article content with fallback chain."
    )
    parser.add_argument("url", help="Article URL to extract")
    parser.add_argument(
        "--bookmark-id",
        default="",
        help="Instapaper bookmark ID (enables get_text as first attempt)",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=0,
        help="Truncate output to N characters (0 = no limit)",
    )
    parser.add_argument(
        "--skip-instapaper",
        action="store_true",
        help="Skip Instapaper get_text and go straight to trafilatura",
    )
    return parser.parse_args()


# Instapaper's cached text for a Hacker News bookmark is the HN *comment page*,
# not the linked article. It is well over the 200-char threshold, so it silently
# passes as a successful extraction. Detect and reject it.
HN_COMMENT_PAGE_RE = re.compile(
    r"^\s*\d+\s+points?\s+by\s+\S+.*?\|\s*(hide|past|favorite)", re.IGNORECASE | re.DOTALL
)


def is_aggregator_url(url: str) -> bool:
    """True if the URL is a discussion/aggregator page rather than an article."""
    return "news.ycombinator.com" in (url or "")


def looks_like_hn_comment_page(text: str | None) -> bool:
    """True if extracted text is an HN comment page rather than article content."""
    if not text:
        return False
    return bool(HN_COMMENT_PAGE_RE.match(text[:300]))


def try_instapaper(bookmark_id: str) -> str | None:
    """Try Instapaper get_text. Returns text or None."""
    if not bookmark_id:
        return None
    try:
        from auth import InstapaperClient  # noqa: E402

        client = InstapaperClient()
        resp = client.post("/api/1/bookmarks/get_text", {"bookmark_id": bookmark_id})
        text = strip_html(resp.text)
        if looks_like_hn_comment_page(text):
            return None  # HN comment page cached under this bookmark id, not the article
        if len(text) >= 200:
            return text
        return None  # Too short, likely paywall/extraction failure
    except Exception:
        return None


def try_trafilatura(url: str) -> str | None:
    """Try trafilatura extraction. Returns text or None."""
    try:
        import trafilatura

        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        text = trafilatura.extract(downloaded, include_comments=False)
        if text and len(text) >= 200:
            return text
        return None
    except Exception:
        return None


def detect_youtube_embed(url: str, content: str | None) -> str | None:
    """Check if a page embeds a YouTube video as its primary content.

    Returns the YouTube video URL if found and extracted text is thin, else None.
    """
    import requests as _requests  # ensure available in this scope

    # Check if content is missing, very thin, or doesn't look like real article text
    # Pages with YouTube embeds often extract boilerplate/sidebar (can be 1000+ chars)
    # but the actual article content is in the video
    # Always check pages under 5000 chars for embeds
    if content and len(content) > 5000:
        return None

    try:
        resp = _requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        html = resp.text
    except Exception:
        return None

    # Look for YouTube embeds or links
    patterns = [
        r'youtube\.com/embed/([\w-]+)',
        r'youtube\.com/watch\?v=([\w-]+)',
        r'youtu\.be/([\w-]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return f"https://www.youtube.com/watch?v={match.group(1)}"
    return None


def fetch_and_extract(
    url: str,
    bookmark_id: str = "",
    max_chars: int = 0,
    skip_instapaper: bool = False,
) -> dict[str, Any]:
    """Extract article content using the fallback chain.

    Returns dict with url, method, status, content, char_count.
    Also detects YouTube-embed pages and signals for transcript extraction.
    """
    content = None
    method = "none"

    # Tier 1: Instapaper get_text
    # Never use the Instapaper cache for aggregator/discussion URLs: the cached
    # text is the comment page, not the linked article.
    if not skip_instapaper and bookmark_id and not is_aggregator_url(url):
        content = try_instapaper(bookmark_id)
        if content:
            method = "instapaper"

    # Tier 2: trafilatura
    if content is None:
        content = try_trafilatura(url)
        if content:
            method = "trafilatura"

    # Tier 3: CDP browser would go here (not automated -- requires agent-browser)

    # Check if this is actually a YouTube-embed page with thin text
    youtube_url = detect_youtube_embed(url, content)
    if youtube_url:
        return {
            "url": url,
            "bookmark_id": bookmark_id,
            "method": "youtube_embed",
            "status": "defer_youtube",
            "content": content or "",
            "char_count": len(content) if content else 0,
            "youtube_url": youtube_url,
        }

    if content is None:
        return {
            "url": url,
            "bookmark_id": bookmark_id,
            "method": "none",
            "status": "failed",
            "content": "",
            "char_count": 0,
        }

    if max_chars > 0 and len(content) > max_chars:
        content = content[:max_chars] + "\n\n[...truncated]"

    return {
        "url": url,
        "bookmark_id": bookmark_id,
        "method": method,
        "status": "ok",
        "content": content,
        "char_count": len(content),
    }


def main() -> None:
    args = parse_args()
    result = fetch_and_extract(
        url=args.url,
        bookmark_id=args.bookmark_id,
        max_chars=args.max_chars,
        skip_instapaper=args.skip_instapaper,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
