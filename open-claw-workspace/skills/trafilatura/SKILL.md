---
name: trafilatura
description: >
  Extract the main text content from any web page URL using trafilatura.
  Use when the user says "extract article", "scrape page text", "get content from URL",
  "fetch article text", or shares a link and wants its content read, summarized, or analyzed.
---

# Trafilatura

## Execution

```bash
uv run skills/trafilatura/fetch_page.py <url>
```

Default behavior: returns markdown output with tables included, no comments, no inline links, no images.
This is the right call for the vast majority of pages -- articles, blog posts, wiki pages, newsletters.

### Optional flags (rarely needed):

- `--output-format {txt,json,markdown,xml}` -- output format (default: markdown)
- `--include-comments` -- include user-generated comments from the page
- `--include-links` -- include hyperlinks in the output
- `--include-images` -- include image metadata
- `--no-tables` -- exclude tables from the output
- `--favor-precision` -- tighter extraction, less noise
- `--favor-recall` -- broader extraction, more content
- `--no-fallback` -- disable fallback extractors (faster but may miss content)
- `--max-length N` -- truncate output to N chars (0 = no limit)

## Conventions

- Default invocation (no flags) is correct for most pages. Only add flags if the user asks for something specific.
- Use `--max-length` when you only need a preview or the page is very long.
- Use `--output-format json` when you need metadata (title, author, date) alongside the text.
- Present extracted content as a readable summary unless the user asks for raw text.
- If extraction returns nothing, tell the user the page couldn't be parsed (may be JS-rendered or paywalled).
- Confirm before performing bulk extraction on many URLs.
- Use machine-readable output (`--output-format json`) when parsing results programmatically.

## Requirements

- `uv` must be installed (script dependencies are managed inline via uv).
