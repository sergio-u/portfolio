---
name: michelin-guide
description: >
  Search and enrich restaurants with live Michelin Guide data: Stars, Bib Gourmand,
  Green Star, Selected status, cuisine, price, address, inspector notes, and official URLs.
  Use when the user asks for "Michelin", "Michelin Guide", "Michelin stars", "Bib Gourmand",
  "Green Star", "Michelin listed", "enrich restaurant recommendations", or wants Michelin
  signals added to restaurant-finder results.
---

# Michelin Guide

Live-first Michelin Guide lookup and enrichment for restaurant recommendation workflows.

## Execution

Run commands from the workspace root unless explicitly `cd`ing into the skill directory.

### First-time setup

```bash
cd ~/.openclaw/workspace/skills/michelin-guide
uv venv .venv
uv pip install --python .venv -r <(uv pip compile pyproject.toml)
```

If process substitution is unavailable, use:

```bash
cd ~/.openclaw/workspace/skills/michelin-guide
uv venv .venv
uv pip install --python .venv beautifulsoup4 lxml requests 'scrapling[all]'
```

### Search a Michelin listing URL

```bash
cd ~/.openclaw/workspace/skills/michelin-guide
.venv/bin/python scripts/michelin.py search-url \
  'https://guide.michelin.com/us/en/city-of-edinburgh/edinburgh/restaurants' \
  --max-pages 2 --details --format json
```

### Fetch one Michelin detail page

```bash
cd ~/.openclaw/workspace/skills/michelin-guide
.venv/bin/python scripts/michelin.py detail \
  'https://guide.michelin.com/us/en/ciudad-de-mexico/cuauhtemoc_1995126/restaurant/taqueria-el-jarocho' \
  --format json
```

### Enrich restaurant-finder candidates

```bash
cd ~/.openclaw/workspace/skills/michelin-guide
.venv/bin/python scripts/michelin.py enrich \
  --candidates /tmp/restaurants.json \
  --listing-url 'https://guide.michelin.com/us/en/ciudad-de-mexico/roma-sur_2000648_noindex/restaurants' \
  --max-pages 2 --details --format json
```

Candidate JSON may be either an array of objects or an object with a `results` array. Candidate name keys accepted: `name`, `title`, `restaurant`, or `place_name`.

## Operations

### Live search / area scrape

Use `search-url` when the user provides or you can discover a Michelin listing URL for a city, neighborhood, or filtered award page. Examples:

- `https://guide.michelin.com/us/en/city-of-edinburgh/edinburgh/restaurants`
- `https://guide.michelin.com/us/en/ciudad-de-mexico/roma-sur_2000648_noindex/restaurants`
- `https://guide.michelin.com/us/en/restaurants/bib-gourmand`
- `https://guide.michelin.com/us/en/restaurants/all-starred`

The script parses list cards first and optionally fetches detail pages with `--details` for inspector summaries, phone, website, award text, and richer structured data.

### Recommendation enrichment

Use `enrich` after `restaurant-finder` produces candidates. The command searches the live Michelin listing URL and fuzzy-matches candidates by name. Treat matches below `--min-score` as uncertain and surface the score instead of claiming a Michelin listing.

### Detail lookup

Use `detail` when you already have an official Michelin restaurant URL. It is the most reliable path because detail pages expose JSON-LD plus Michelin data attributes.

## Data Sources

Parsing order:

1. Michelin list-page card attributes (`data-lat`, `data-lng`, `data-map-pin-name`, `data-dtm-distinction`, `data-restaurant-name`).
2. Detail-page JSON-LD (`script[type="application/ld+json"]`).
3. Michelin detail/list data attributes (`data-dtm-*`, `data-distinction`, `data-green-star`).
4. HTML fallbacks for description, website, phone, price/cuisine, facilities, and tags.

## Reference

| Source | Purpose | Notes |
|---|---|---|
| `xubing0602/dining_map` | Extraction strategy reference | No license found during initial research; do not copy code verbatim. |
| `timrogers/michelin-guide-scraper` | Minimal JSON-LD extraction reference | MIT; useful simple model. |
| `ngshiheng/michelin-my-maps` | Conservative crawl/resume and historical dataset reference | MIT; useful for future offline/historical mode. |

## Conventions

- Prefer live Michelin pages for current recommendations; do not use stale global datasets unless the user explicitly asks for offline or historical analysis.
- Cache only operationally if needed, and always show `fetched_at` when presenting Michelin-derived data.
- Keep scraping bounded: use specific city/neighborhood/award listing URLs, small `--max-pages`, and `--details` only when richer data is needed.
- Confirm before high-volume global scrapes; Michelin can WAF-challenge ordinary HTTP clients.
- Use the venv Python only: `skills/michelin-guide/.venv/bin/python`; never rely on bare `python`.
- Present Michelin signals compactly: distinction, cuisine, price, neighborhood/city, inspector summary, and official Michelin URL.
- Mark fuzzy matches and uncertain fields explicitly; never silently convert a weak name match into a confirmed Michelin listing.
- Respect the Michelin Guide website terms and local laws. This skill is intended for small, live recommendation enrichment, not bulk republication.

## Authentication

No authentication is required. The skill reads public Michelin Guide pages.

## Requirements

- `uv`
- Python 3.11+
- Local `.venv` in this skill directory
- Python packages: `scrapling[all]`, `beautifulsoup4`, `lxml`, `requests`

## Troubleshooting

### `requests` or `curl` returns an empty page / AWS WAF challenge

Use the script normally; it tries Scrapling's `Fetcher` first. Direct `curl` from this host received `x-amzn-waf-action: challenge` during initial testing.

### No cards found

Check that the URL is a Michelin restaurant listing page, not a homepage or article. Try `--debug` to print fetch and selector diagnostics.

### Weak enrichment matches

Lowering `--min-score` can find more possible matches, but present them as uncertain. Prefer official Michelin URLs when available.
