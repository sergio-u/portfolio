#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx", "beautifulsoup4", "lxml"]
# ///
"""Search Anna's Archive for books. Returns structured JSON results."""

import argparse
import json
import os
import re
import sys
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

# .org was seized Jan 2026. Mirrors without DDoS-Guard (scriptable):
MIRRORS = [
    "https://annas-archive.gd",
    "https://annas-archive.pk",
]
BASE_URL = os.environ.get("ANNAS_BASE_URL", MIRRORS[0])

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

CONTENT_TYPES = {
    "any": "book_any",
    "fiction": "book_fiction",
    "nonfiction": "book_nonfiction",
    "textbook": "book_nonfiction",
    "comic": "book_comic",
}

SORT_OPTIONS = {
    "relevant": "",
    "popular": "",  # client-side re-rank by base score
    "newest": "newest",
    "oldest": "oldest",
    "largest": "largest",
    "smallest": "smallest",
}


def build_search_url(query: str, lang: str, ext: str, content: str, sort: str) -> str:
    params = {"q": query}
    if lang:
        params["lang"] = lang
    if ext:
        params["ext"] = ext
    if content:
        params["content"] = CONTENT_TYPES.get(content, content)
    sort_val = SORT_OPTIONS.get(sort, "")
    if sort_val:
        params["sort"] = sort_val
    return f"{BASE_URL}/search?{urlencode(params)}"


def extract_meta_dots(text: str) -> dict:
    """Parse metadata line like 'English [en] · EPUB · 1.0MB · 1964 · Book (fiction)'."""
    parts = [p.strip() for p in text.split("·")]
    meta = {"language": "", "format": "", "size": "", "year": ""}

    for part in parts:
        lang_match = re.search(r"\[(\w{2,3})\]", part)
        if lang_match:
            meta["language"] = lang_match.group(1)
            continue

        fmt_match = re.search(
            r"\b(EPUB|PDF|MOBI|AZW3?|DJVU|CBZ|CBR|FB2|DOCX?|TXT)\b", part, re.I
        )
        if fmt_match:
            meta["format"] = fmt_match.group(1).lower()
            continue

        size_match = re.search(r"\d+\.?\d*\s*(?:MB|KB|GB|TB)", part, re.I)
        if size_match:
            meta["size"] = size_match.group(0).strip()
            continue

        year_match = re.search(r"\b(19|20)\d{2}\b", part)
        if year_match:
            meta["year"] = year_match.group(0)

    return meta


def parse_results(html: str) -> list[dict]:
    """Parse search results from HTML.

    Result card structure (as of 2026-04):
      div.flex.pt-3.pb-3.border-b          -- card container
        a.custom-a.block[href^='/md5/']     -- cover image link
        div.max-w-full                      -- info container
          a.js-vim-focus[href^='/md5/']     -- title link
          a[href^='/search'] > span.icon-[mdi--user-edit]  -- author
          a[href^='/search'] > span.icon-[mdi--company]    -- publisher
          div.text-gray-800                 -- metadata line (lang · format · size · year)
          div.text-sm.text-gray-600         -- description
    """
    soup = BeautifulSoup(html, "lxml")
    results = []

    # Find result cards via the cover image link
    for cover_link in soup.select("a.custom-a.block[href^='/md5/']"):
        href = cover_link.get("href", "")
        md5 = href.replace("/md5/", "").strip()
        if not md5:
            continue

        # Navigate to the card container (parent div)
        card = cover_link.parent
        if card is None:
            continue

        # Find the info div
        info_div = card.select_one("div.max-w-full")
        if info_div is None:
            continue

        # Title: from the js-vim-focus title link
        title = ""
        title_link = info_div.select_one("a.js-vim-focus[href^='/md5/']")
        if title_link:
            title = title_link.get_text(strip=True)

        # Authors: link containing the user-edit icon
        authors = ""
        author_icon = info_div.select_one(
            "a[href^='/search'] span.icon-\\[mdi--user-edit\\]"
        )
        if author_icon and author_icon.parent:
            authors = author_icon.parent.get_text(strip=True)

        # Publisher: link containing the company icon
        publisher = ""
        pub_icon = info_div.select_one(
            "a[href^='/search'] span.icon-\\[mdi--company\\]"
        )
        if pub_icon and pub_icon.parent:
            publisher = pub_icon.parent.get_text(strip=True)

        # Metadata line (language, format, size, year)
        meta = {"language": "", "format": "", "size": "", "year": ""}
        meta_div = info_div.select_one("div.text-gray-800")
        if meta_div:
            meta = extract_meta_dots(meta_div.get_text())

        # Description
        description = ""
        desc_div = info_div.select_one("div.text-sm.text-gray-600")
        if desc_div:
            description = desc_div.get_text(strip=True)

        # Popularity score (hidden div with "base score: N, final score: N")
        score = 0.0
        for hidden in card.select("div.hidden"):
            text = hidden.get_text(strip=True)
            if "base score" in text:
                m = re.search(r"base score:\s*([\d.]+)", text)
                if m:
                    score = float(m.group(1))
                break

        result = {
            "title": title,
            "authors": authors,
            "publisher": publisher,
            "md5": md5,
            "url": f"{BASE_URL}/md5/{md5}",
            "language": meta.get("language", ""),
            "format": meta.get("format", ""),
            "size": meta.get("size", ""),
            "year": meta.get("year", ""),
            "score": score,
        }
        if description:
            result["description"] = description

        results.append(result)

    return results


def fetch_inline_info(md5s: list[str]) -> dict[str, dict]:
    """Fetch download/quality/list counts for a batch of md5s.

    Calls GET /dyn/md5/inline_info/{md5} for each (with Accept: text/css to
    bypass DDoS-Guard caching). Returns {md5: {downloads_total, ...}}.
    """
    info = {}
    with httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "text/css"},
        follow_redirects=True,
        timeout=10,
    ) as client:
        for md5 in md5s:
            try:
                resp = client.get(f"{BASE_URL}/dyn/md5/inline_info/{md5}")
                if resp.status_code == 200:
                    info[md5] = resp.json()
            except Exception:
                continue
    return info


def fetch_html(url: str) -> str:
    """Fetch a page with browser-like headers. Falls back to other mirrors on failure."""
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=30,
    ) as client:
        try:
            resp = client.get(url)
            resp.raise_for_status()
            # Check for DDoS-Guard challenge page
            if len(resp.text) < 500 and "Verifying your connection" in resp.text:
                raise httpx.ConnectError("DDoS-Guard challenge detected")
            return resp.text
        except (httpx.ConnectError, httpx.ConnectTimeout):
            # Try fallback mirrors if the user hasn't set a custom base URL
            if os.environ.get("ANNAS_BASE_URL"):
                raise
            for mirror in MIRRORS:
                if mirror in url:
                    continue
                fallback_url = url.replace(BASE_URL, mirror)
                try:
                    resp = client.get(fallback_url)
                    resp.raise_for_status()
                    if len(resp.text) < 500 and "Verifying your connection" in resp.text:
                        continue
                    print(f"Note: using mirror {mirror}", file=sys.stderr)
                    return resp.text
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    continue
            raise


def _popularity_key(r: dict) -> float:
    """Composite popularity score. Downloads are the primary signal, quality
    stars and list saves are strong secondary signals."""
    return (
        r.get("downloads", 0)
        + r.get("quality", 0) * 500
        + r.get("lists", 0) * 50
    )


def search(
    query: str,
    lang: str = "en",
    ext: str = "",
    content: str = "any",
    sort: str = "relevant",
    max_results: int = 10,
) -> list[dict]:
    url = build_search_url(query, lang, ext, content, sort)
    html = fetch_html(url)
    # Strip HTML comments for cleaner parsing
    html = html.replace("<!--", "").replace("-->", "")
    results = parse_results(html)

    # Fetch real stats from the inline_info API
    md5s = [r["md5"] for r in results]
    info = fetch_inline_info(md5s)
    for r in results:
        stats = info.get(r["md5"], {})
        r["downloads"] = stats.get("downloads_total", 0)
        r["quality"] = stats.get("great_quality_count", 0)
        r["lists"] = stats.get("lists_count", 0)

    # Client-side re-rank by weighted popularity
    if sort == "popular":
        results.sort(key=_popularity_key, reverse=True)

    return results[:max_results]


def format_results(results: list[dict]) -> str:
    """Format results as a readable list."""
    if not results:
        return "No results found."

    lines = []
    for i, r in enumerate(results, 1):
        parts = [f"{i}. {r['title']}"]
        if r["authors"]:
            parts.append(f"   Author: {r['authors']}")
        if r["publisher"]:
            parts.append(f"   Publisher: {r['publisher']}")
        meta_parts = []
        if r["language"]:
            meta_parts.append(r["language"].upper())
        if r["format"]:
            meta_parts.append(r["format"].upper())
        if r["size"]:
            meta_parts.append(r["size"])
        if r["year"]:
            meta_parts.append(r["year"])
        stats = []
        if r.get("downloads"):
            stats.append(f"{r['downloads']:,} DLs")
        if r.get("quality"):
            stats.append(f"{r['quality']} stars")
        if r.get("lists"):
            stats.append(f"{r['lists']} lists")
        if stats:
            meta_parts.append(" · ".join(stats))
        if meta_parts:
            parts.append(f"   {' · '.join(meta_parts)}")
        parts.append(f"   MD5: {r['md5']}")
        if r.get("description"):
            desc = r["description"]
            if len(desc) > 120:
                desc = desc[:117] + "..."
            parts.append(f"   {desc}")
        lines.append("\n".join(parts))

    return "\n\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Search Anna's Archive for books",
        epilog="Set ANNAS_BASE_URL env var to use a different mirror (default: annas-archive.gd)",
    )
    parser.add_argument("query", help="Search query (title, author, ISBN, etc.)")
    parser.add_argument(
        "-l", "--lang", default="en",
        help="Language filter: ISO 639-1 code (default: en). Use '' for any.",
    )
    parser.add_argument(
        "-e", "--ext", default="",
        help="File format filter: epub, pdf, mobi, etc. (default: any)",
    )
    parser.add_argument(
        "-c", "--content", default="any",
        choices=["any", "fiction", "nonfiction", "textbook", "comic"],
        help="Content type (default: any)",
    )
    parser.add_argument(
        "-s", "--sort", default="relevant",
        choices=["relevant", "popular", "newest", "oldest", "largest", "smallest"],
        help="Sort order (default: relevant). 'popular' re-ranks by score client-side.",
    )
    parser.add_argument(
        "-n", "--max-results", type=int, default=10,
        help="Maximum results to return (default: 10)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output raw JSON instead of formatted text",
    )

    args = parser.parse_args()
    try:
        results = search(
            query=args.query,
            lang=args.lang,
            ext=args.ext,
            content=args.content,
            sort=args.sort,
            max_results=args.max_results,
        )
    except httpx.ConnectError as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        print(f"Tried: {BASE_URL}", file=sys.stderr)
        print("Set ANNAS_BASE_URL to use a reachable mirror.", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"HTTP error: {e.response.status_code}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print(format_results(results))


if __name__ == "__main__":
    main()
