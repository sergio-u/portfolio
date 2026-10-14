#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["trafilatura"]
# ///
"""Fetch and extract the main content from a web page using trafilatura."""

import argparse
import json
import sys
from urllib.parse import urlparse

import trafilatura


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract main text content from a web page URL."
    )
    parser.add_argument("url", help="URL of the page to extract")
    parser.add_argument(
        "--include-comments",
        action="store_true",
        default=False,
        help="Include user comments/discussion from the page",
    )
    parser.add_argument(
        "--include-links",
        action="store_true",
        default=False,
        help="Include hyperlinks in the output",
    )
    parser.add_argument(
        "--include-images",
        action="store_true",
        default=False,
        help="Include image metadata",
    )
    parser.add_argument(
        "--no-tables",
        action="store_true",
        default=False,
        help="Exclude tables from the output",
    )
    parser.add_argument(
        "--output-format",
        choices=["txt", "json", "markdown", "xml"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--favor-precision",
        action="store_true",
        default=False,
        help="Favor extraction precision over recall",
    )
    parser.add_argument(
        "--favor-recall",
        action="store_true",
        default=False,
        help="Favor extraction recall over precision",
    )
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        default=False,
        help="Disable fallback extractors (faster but may miss content)",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=0,
        help="Truncate output to this many chars (0 = no limit)",
    )
    return parser.parse_args()


def fetch_and_extract(args: argparse.Namespace) -> dict | str | None:
    """Download and extract content from the given URL."""
    downloaded = trafilatura.fetch_url(args.url)
    if downloaded is None:
        return None

    # Build extraction kwargs
    extract_kwargs: dict = {
        "include_comments": args.include_comments,
        "include_tables": not args.no_tables,
        "include_links": args.include_links,
        "include_images": args.include_images,
        "no_fallback": args.no_fallback,
    }

    if args.favor_precision:
        extract_kwargs["favor_precision"] = True
    elif args.favor_recall:
        extract_kwargs["favor_recall"] = True

    if args.output_format == "json":
        extract_kwargs["output_format"] = "json"
        extract_kwargs["with_metadata"] = True
        raw = trafilatura.extract(downloaded, **extract_kwargs)
        if raw is None:
            return None
        return json.loads(raw)
    elif args.output_format == "xml":
        extract_kwargs["output_format"] = "xmltei"
        return trafilatura.extract(downloaded, **extract_kwargs)
    elif args.output_format == "markdown":
        extract_kwargs["output_format"] = "markdown"
        return trafilatura.extract(downloaded, **extract_kwargs)
    else:
        # plain text
        return trafilatura.extract(downloaded, **extract_kwargs)


def truncate(text: str, max_length: int) -> str:
    """Truncate text to max_length chars, appending a notice if truncated."""
    if max_length <= 0 or len(text) <= max_length:
        return text
    return text[:max_length] + "\n\n[... truncated at " + str(max_length) + " chars]"


def main() -> None:
    args = parse_args()

    try:
        result = fetch_and_extract(args)
    except Exception as exc:
        print(f"Error extracting {args.url}: {exc}", file=sys.stderr)
        sys.exit(1)

    if result is None:
        print(f"Could not fetch or extract content from: {args.url}", file=sys.stderr)
        sys.exit(1)

    if isinstance(result, dict):
        output = json.dumps(result, indent=2)
    else:
        output = result

    if args.max_length > 0:
        output = truncate(output, args.max_length)

    print(output)


if __name__ == "__main__":
    main()
