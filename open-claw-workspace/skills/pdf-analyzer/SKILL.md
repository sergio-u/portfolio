---
name: pdf-analyzer
description: >
  Extract text, search content, and analyze PDF documents using PyMuPDF.
  Use when the user says "read this PDF", "extract text from PDF", "search PDF",
  "what does this PDF say", "analyze this document", "PDF summary", "check this
  contract", "find in PDF", or shares a PDF file and wants its content read,
  searched, or summarized. Handles text-based PDFs; does not support OCR for
  image-only scans.
---

# PDF Analyzer

Extract text and search PDF documents via PyMuPDF.

## Execution

```bash
uv run skills/pdf-analyzer/scripts/extract.py <pdf-path> [options]
```

Run from the workspace root (`~/.openclaw/workspace`).

### Common operations

**Extract all text:**
```bash
uv run skills/pdf-analyzer/scripts/extract.py /path/to/file.pdf
```

**Extract specific pages (1-indexed):**
```bash
uv run skills/pdf-analyzer/scripts/extract.py /path/to/file.pdf --pages "1-5"
uv run skills/pdf-analyzer/scripts/extract.py /path/to/file.pdf --pages "1,3,8-12"
```

**Search for a keyword:**
```bash
uv run skills/pdf-analyzer/scripts/extract.py /path/to/file.pdf --search "balcony"
```

**Quick summary (page count, text coverage):**
```bash
uv run skills/pdf-analyzer/scripts/extract.py /path/to/file.pdf --summary
```

**Metadata (author, dates, encryption):**
```bash
uv run skills/pdf-analyzer/scripts/extract.py /path/to/file.pdf --metadata
```

**Table of contents:**
```bash
uv run skills/pdf-analyzer/scripts/extract.py /path/to/file.pdf --toc
```

**Truncate long output:**
```bash
uv run skills/pdf-analyzer/scripts/extract.py /path/to/file.pdf --max-chars 5000
```

**JSON output (for programmatic use):**
```bash
uv run skills/pdf-analyzer/scripts/extract.py /path/to/file.pdf --search "term" --output json
```

## Workflow

For large PDFs (50+ pages):

1. Start with `--summary` to check page count and text coverage
2. Use `--toc` to find relevant sections
3. Use `--search "keyword"` to locate specific content
4. Extract targeted pages with `--pages` instead of full text

If `--summary` shows 0 chars and no text, the PDF is image-based (scanned). This skill does not support OCR -- use the `image` tool to read individual pages visually instead.

## Conventions

- Summarize extracted text for the user -- don't dump raw pages
- For legal/contract documents, highlight key clauses and obligations
- When searching, report page numbers and surrounding context
- Use `--max-chars` for large documents to avoid flooding output
- Inbound PDFs from Telegram/channels land in `~/.openclaw/media/inbound/`

## Requirements

- `uv` (manages pymupdf dependency automatically via inline script metadata)
- No manual install needed -- `uv run` handles everything on first use
