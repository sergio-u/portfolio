# Letterboxd Selectors & Endpoints Reference

Detailed reference for CSS selectors, data attributes, and internal endpoints used when scraping Letterboxd via scrapling.

## List Page (Grid View)

**URL:** `https://letterboxd.com/<user>/list/<slug>/`

**Pagination:** `/page/2/`, `/page/3/`, etc. (100 items per page)

### Film Items

**Selector:** `[data-film-id]` or `.film-poster`

Each item is a `div.react-component` with these data attributes:

| Attribute | Example | Description |
|---|---|---|
| `data-item-name` | `The Napa Boys (2025)` | Title with year |
| `data-item-slug` | `the-napa-boys` | URL slug |
| `data-item-link` | `/film/the-napa-boys/` | Relative film URL |
| `data-film-id` | `1393309` | Numeric film ID |
| `data-item-full-display-name` | `The Napa Boys (2025)` | Same as item-name |
| `data-poster-url` | `/film/the-napa-boys/image-150/` | Poster image path |
| `data-list-index` | `0` | Position in current sort order |
| `data-details-endpoint` | `/film/the-napa-boys/json/` | JSON metadata endpoint |

## List Page (Detail View)

**URL:** `https://letterboxd.com/<user>/list/<slug>/detail/`

**Selector:** `article.list-detailed-entry`

Contains the same `data-*` attributes as grid view (nested in a `div.react-component` child), plus an HTML body with title, year link, and sometimes director. No additional metadata vs grid view in practice.

## Film JSON Endpoint

**URL:** `https://letterboxd.com/film/<slug>/json/`

Returns JSON (wrapped in HTML tags) with:

```json
{
  "name": "Ballistic",
  "releaseYear": 2025,
  "runTime": 96,
  "slug": "ballistic-2025",
  "directors": [{"name": "Chad Faust"}],
  "id": 1126868,
  "url": "/film/ballistic-2025/",
  "image150": "/film/ballistic-2025/image-150/"
}
```

**Note:** Response is `<html><body>{json}</body></html>`. Parse with:
```python
import json
data = json.loads(page.css("body")[0].text)
```

Does NOT include: rating, genres, cast, or full credits.

## Rating Histogram (CSI Endpoint)

**URL:** `https://letterboxd.com/csi/film/<slug>/rating-histogram/`

Returns an HTML fragment with a rating distribution table.

### Selectors

- **Individual ratings:** `.tooltip` elements with `title` attribute
  - Format: `"34 ★★ ratings (21%)"`
  - Pattern: `r'(\d[\d,]*)\s+(.+?)\s+ratings?\s+\((\d+)%\)'`
- **Weighted average:** Last `.tooltip` element
  - Format: `"Weighted average of 4.60 based on 113,535 ratings"`
  - Pattern: `r'Weighted average of ([\d.]+) based on ([\d,]+) ratings'`

### Star Labels

| Label | Value |
|---|---|
| `half-★` | 0.5 |
| `★` | 1.0 |
| `★½` | 1.5 |
| `★★` | 2.0 |
| `★★½` | 2.5 |
| `★★★` | 3.0 |
| `★★★½` | 3.5 |
| `★★★★` | 4.0 |
| `★★★★½` | 4.5 |
| `★★★★★` | 5.0 |

## Film Page (Full)

**URL:** `https://letterboxd.com/film/<slug>/`

### JSON-LD (Structured Data)

**Selector:** `script[type='application/ld+json']`

Contains `@type: Movie` schema.org data. CDATA-wrapped -- strip before parsing:

```python
raw = scripts[0].text.strip()
if raw.startswith("/*"):
    raw = raw.split("*/", 1)[1].rsplit("/*", 1)[0].strip()
data = json.loads(raw)
```

Fields: `name`, `director[]`, `actors[]`, `genre[]`, `countryOfOrigin[]`, `productionCompany[]`, `releasedEvent[]`, `dateCreated`, `dateModified`, `image`.

**Does NOT include:** rating (loaded via CSI), runtime (use JSON endpoint instead).

## Sort Parameters

Append to any list URL before pagination:

| Parameter | Sort |
|---|---|
| (none) | List order (default) |
| `/by/rating/` | Letterboxd Bayesian weighted rating |
| `/by/date/` | Release date (newest first) |
| `/by/date-earliest/` | Release date (oldest first) |
| `/by/name/` | Alphabetical |
| `/by/added/` | Date added to list |
| `/by/popularity/` | Popularity |
| `/by/length/` | Runtime (longest first) |
| `/by/length-shortest-first/` | Runtime (shortest first) |

## Pagination

- 100 items per page (both grid and detail views)
- Total count available in meta description: `"A list of 1,045 films..."`
- Pattern: `r'A list of ([\d,]+) films'` from `meta[name=description]`
