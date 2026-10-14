#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["trafilatura>=2.2,<3"]
# ///
"""Fetch one URL and print a JSON envelope: {url, title, content, metadata} or {url, error}.

Derived from Q:\\src\\Personal\\pi-config\\extensions\\web-access\\scripts\\fetch_page.py
(same trafilatura defaults: markdown, tables on, no comments/links/images), adapted to
return title + metadata in one pass for the Hermes web_extract contract.
"""

import json
import sys

import trafilatura


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) != 2:
        print(json.dumps({"error": "usage: fetch_page.py <url>"}))
        sys.exit(2)
    url = sys.argv[1]
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded is None:
            print(json.dumps({"url": url, "error": "Could not fetch page (network error, block, or non-HTML)"}))
            return
        content = trafilatura.extract(
            downloaded, url=url, output_format="markdown", include_tables=True,
            include_comments=False, include_links=False, include_images=False,
        )
        if not content:
            print(json.dumps({"url": url, "error": "No main content extracted (page may be JS-rendered or paywalled)"}))
            return
        meta = trafilatura.extract_metadata(downloaded, default_url=url)
        md = meta.as_dict() if meta is not None else {}
        keep = {k: md.get(k) for k in ("author", "date", "sitename", "hostname", "description") if md.get(k)}
        print(json.dumps({"url": url, "title": md.get("title") or "", "content": content, "metadata": keep}))
    except Exception as exc:  # noqa: BLE001 - report every failure as a per-URL error
        print(json.dumps({"url": url, "error": f"{type(exc).__name__}: {exc}"}))


if __name__ == "__main__":
    main()
