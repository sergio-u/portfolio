#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pymupdf"]
# ///
"""PDF text extraction and analysis using PyMuPDF.

Usage:
    uv run skills/pdf-analyzer/scripts/extract.py <pdf-path> [options]

Options:
    --pages RANGE       Page range: "1-5", "3", "1,3,5-7" (1-indexed, default: all)
    --search KEYWORD    Search for keyword (case-insensitive), show matching pages with context
    --metadata          Show document metadata only
    --toc               Show table of contents
    --output FORMAT     Output format: text (default), json
    --max-chars N       Truncate output to N characters (0 = no limit, default: 0)
    --summary           Show page count, char counts per page, and keyword density
"""

import argparse
import json
import sys
import pymupdf


def parse_page_range(spec: str, total: int) -> list[int]:
    """Parse page range spec like '1-5', '3', '1,3,5-7' into 0-indexed list."""
    pages = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            start = max(1, int(start))
            end = min(total, int(end))
            pages.update(range(start - 1, end))
        else:
            p = int(part) - 1
            if 0 <= p < total:
                pages.add(p)
    return sorted(pages)


def extract_text(doc, pages: list[int] | None = None) -> dict[int, str]:
    """Extract text from specified pages (0-indexed). Returns {page_num: text}."""
    if pages is None:
        pages = list(range(len(doc)))
    return {p: doc[p].get_text() for p in pages if 0 <= p < len(doc)}


def search_keyword(doc, keyword: str, pages: list[int] | None = None, context_chars: int = 150) -> list[dict]:
    """Search for keyword across pages, return matches with context."""
    if pages is None:
        pages = list(range(len(doc)))
    keyword_lower = keyword.lower()
    results = []
    for p in pages:
        if p < 0 or p >= len(doc):
            continue
        text = doc[p].get_text()
        text_lower = text.lower()
        idx = 0
        while True:
            idx = text_lower.find(keyword_lower, idx)
            if idx == -1:
                break
            start = max(0, idx - context_chars)
            end = min(len(text), idx + len(keyword) + context_chars)
            results.append({
                "page": p + 1,
                "position": idx,
                "context": text[start:end].strip().replace("\n", " "),
            })
            idx += len(keyword)
    return results


def get_metadata(doc) -> dict:
    """Extract document metadata."""
    meta = doc.metadata or {}
    return {
        "pages": len(doc),
        "title": meta.get("title", ""),
        "author": meta.get("author", ""),
        "subject": meta.get("subject", ""),
        "creator": meta.get("creator", ""),
        "producer": meta.get("producer", ""),
        "created": meta.get("creationDate", ""),
        "modified": meta.get("modDate", ""),
        "encrypted": doc.is_encrypted,
    }


def get_summary(doc, pages: list[int] | None = None) -> dict:
    """Page count and character counts per page."""
    if pages is None:
        pages = list(range(len(doc)))
    page_stats = []
    for p in pages:
        text = doc[p].get_text()
        page_stats.append({"page": p + 1, "chars": len(text), "has_text": len(text.strip()) > 0})
    total_chars = sum(s["chars"] for s in page_stats)
    text_pages = sum(1 for s in page_stats if s["has_text"])
    return {
        "total_pages": len(doc),
        "analyzed_pages": len(pages),
        "pages_with_text": text_pages,
        "total_chars": total_chars,
        "page_stats": page_stats,
    }


def main():
    parser = argparse.ArgumentParser(description="Extract and analyze PDF content")
    parser.add_argument("pdf", help="Path to PDF file")
    parser.add_argument("--pages", help="Page range: '1-5', '3', '1,3,5-7' (1-indexed)")
    parser.add_argument("--search", help="Search for keyword (case-insensitive)")
    parser.add_argument("--metadata", action="store_true", help="Show metadata only")
    parser.add_argument("--toc", action="store_true", help="Show table of contents")
    parser.add_argument("--output", choices=["text", "json"], default="text", help="Output format")
    parser.add_argument("--max-chars", type=int, default=0, help="Truncate output to N chars (0=unlimited)")
    parser.add_argument("--summary", action="store_true", help="Show page/char summary")
    args = parser.parse_args()

    doc = pymupdf.open(args.pdf)
    pages = parse_page_range(args.pages, len(doc)) if args.pages else None

    if args.metadata:
        meta = get_metadata(doc)
        if args.output == "json":
            print(json.dumps(meta, indent=2))
        else:
            for k, v in meta.items():
                print(f"{k}: {v}")
        return

    if args.toc:
        toc = doc.get_toc()
        if args.output == "json":
            print(json.dumps([{"level": t[0], "title": t[1], "page": t[2]} for t in toc], indent=2))
        elif toc:
            for level, title, page in toc:
                indent = "  " * (level - 1)
                print(f"{indent}{title} (p.{page})")
        else:
            print("No table of contents found.")
        return

    if args.summary:
        summary = get_summary(doc, pages)
        if args.output == "json":
            print(json.dumps(summary, indent=2))
        else:
            print(f"Total pages: {summary['total_pages']}")
            print(f"Analyzed: {summary['analyzed_pages']}")
            print(f"With text: {summary['pages_with_text']}")
            print(f"Total chars: {summary['total_chars']}")
            if summary["total_chars"] == 0:
                print("\nNo extractable text found. PDF may be image-based (scanned). OCR not supported.")
        return

    if args.search:
        results = search_keyword(doc, args.search, pages)
        if args.output == "json":
            print(json.dumps(results, indent=2))
        elif results:
            print(f"Found {len(results)} match(es) for '{args.search}':\n")
            for r in results:
                print(f"  Page {r['page']}: ...{r['context']}...")
                print()
        else:
            print(f"No matches found for '{args.search}'.")
        return

    # Default: extract text
    text_data = extract_text(doc, pages)
    if args.output == "json":
        output = {str(k + 1): v for k, v in text_data.items()}
        print(json.dumps(output, indent=2))
    else:
        full_text = ""
        for p in sorted(text_data.keys()):
            text = text_data[p]
            if text.strip():
                header = f"=== Page {p + 1} ==="
                full_text += f"{header}\n{text}\n\n"
        if args.max_chars and len(full_text) > args.max_chars:
            full_text = full_text[:args.max_chars] + "\n\n[... truncated ...]"
        if full_text.strip():
            print(full_text)
        else:
            print("No extractable text found. PDF may be image-based (scanned). OCR not supported.")

    doc.close()


if __name__ == "__main__":
    main()
