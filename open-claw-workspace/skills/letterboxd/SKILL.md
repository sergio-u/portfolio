---
name: letterboxd
description: >
  Browse and filter Letterboxd lists, find films by rating, and get film details
  (ratings, directors, runtime, genres). Uses scrapling for all fetching -- no scripts of its own.
  Use when the user says "letterboxd", "new on VOD", "what to watch", "film recommendations",
  "movie list", "letterboxd list", "top rated films", "what's good on digital",
  "find me a movie", or wants to browse/filter a Letterboxd list.
---

# Letterboxd

Browse Letterboxd lists and film pages. All fetching is done via the **scrapling** skill -- read it first if unfamiliar with the execution pattern.

## Execution

All operations use scrapling's Fetcher (plain HTTP, no JS rendering needed):

```bash
cd ~/.openclaw/workspace/skills/scrapling
.venv/bin/python scripts/run.py << 'PYEOF'
page = Fetcher.get("<letterboxd_url>")
# ... extract using selectors documented below
PYEOF
```

Letterboxd does not block plain HTTP requests. Always start with `Fetcher.get()`.

## Workflows

### Browse a List

Fetch the grid view of any list. Each page returns up to 100 films.

```
https://letterboxd.com/<user>/list/<list-slug>/
https://letterboxd.com/<user>/list/<list-slug>/page/<N>/
```

**Sort options** (append to URL):
- `/by/rating/` -- Letterboxd weighted rating (highest first)
- `/by/date/` -- release date
- `/by/name/` -- alphabetical
- `/by/added/` -- order added to list (default)
- `/by/popularity/` -- popularity
- `/by/length-shortest-first/` or `/by/length/`

**Extract films** from grid view:

```python
items = page.css("[data-film-id]")
for item in items:
    name = item.attrib.get("data-item-name")        # "Ballistic (2025)"
    slug = item.attrib.get("data-item-slug")         # "ballistic-2025"
    film_id = item.attrib.get("data-film-id")        # "1126868"
    link = item.attrib.get("data-item-link")          # "/film/ballistic-2025/"
    index = item.attrib.get("data-list-index")        # position in sorted view
```

Year can be parsed from the name: `re.search(r'\((\d{4})\)', name)`.

### Get Film Rating

Ratings are not on list pages. Fetch the CSI histogram endpoint per film:

```
https://letterboxd.com/csi/film/<slug>/rating-histogram/
```

The **last tooltip** contains the weighted average:

```python
import re
rpage = Fetcher.get(f"https://letterboxd.com/csi/film/{slug}/rating-histogram/")
tooltips = rpage.css(".tooltip")
for t in tooltips:
    title = t.attrib.get("title", "")
    m = re.match(r'Weighted average of ([\d.]+) based on ([\d,]+) ratings', title)
    if m:
        avg = float(m.group(1))
        count = int(m.group(2).replace(",", ""))
```

**Cost:** 1 HTTP request per film. Use sparingly -- only fetch ratings when needed (e.g., verifying the cutoff point in a sorted list).

### Get Film Details

The JSON endpoint returns basic metadata without rendering the full page:

```
https://letterboxd.com/film/<slug>/json/
```

Returns: name, releaseYear, runTime, slug, directors, poster URLs. Does **not** include rating or genres.

For genres and full cast, scrape the film page itself:

```
https://letterboxd.com/film/<slug>/
```

Use the JSON-LD script tag (`script[type='application/ld+json']`) for structured data: directors, cast, production companies, genre, country of origin.

### Top-Rated from a List (Common Pattern)

To find well-rated films from a specific year in a list:

1. Fetch the list sorted by rating: `/<user>/list/<slug>/by/rating/`
2. Filter by year from `data-item-name`
3. The sort uses Letterboxd's Bayesian weighted average (factors in vote count), so top results are reliably good
4. Stop after 1-2 pages -- the tail drops off quickly
5. Optionally spot-check the rating of the last film via the histogram endpoint

## Reference

### Saved Lists

| Name | URL | Notes |
|---|---|---|
| New Releases on Digital VOD | `filmfestival/list/new-releases-on-digital-vod` | ~1,045 films, updated frequently, newest first |

> **Maintenance:** Add lists here as they become useful. Format: `<user>/list/<slug>`.

## Conventions

- Use scrapling `Fetcher.get()` for all requests -- no JS rendering needed
- Don't bulk-fetch ratings for entire lists; only fetch what's needed for the query
- Present results as clean lists (title, year, director if available), not raw HTML or JSON
- When showing "top films", default to first page of `/by/rating/` unless the user specifies otherwise
- Confirm before fetching more than 2 pages (200+ films) to avoid excessive requests
- Year filtering is free (parsed from `data-item-name`) -- prefer it over rating fetches when possible

## Requirements

- Scrapling skill installed at `~/.openclaw/workspace/skills/scrapling/` with working venv
