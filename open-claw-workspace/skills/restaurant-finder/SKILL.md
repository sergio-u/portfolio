---
name: "restaurant-finder"
description: "Use a pinned Rod image while upstream Playwright driver downloads are broken."
---

# Restaurant Finder

Search for restaurants near a location using google-maps-scraper, then filter and rank results.

## Execution

### Step 1: Gather Parameters

Ask the user for (or infer from context):

| Parameter | Required | Default | Notes |
|---|---|---|---|
| location | yes | - | Address, hotel name, landmark, city |
| radius | no | 800m | Walking distance in meters. 800m ~ 10 min walk |
| cuisine | no | any | e.g. Italian, Indian, sushi, seafood |
| dietary | no | none | vegetarian, vegan, or none |
| day_time | no | none | e.g. "Sunday 21:00" -- filter by open hours |
| price | no | any | $, $$, $$$, $$$$ |
| max_results | no | 10 | Number of top results to return |

### Step 2: Resolve Location Coordinates

Look up the latitude/longitude of the location. Use web search if needed to find coordinates for a landmark or hotel. Store as `LAT` and `LON`.

### Step 3: Generate Queries

Create a queries file with 3-5 search terms tailored to the filters. Examples:

- No filters: `restaurants near [location]`
- Cuisine filter: `[cuisine] restaurants [city]`
- Dietary filter: `vegetarian restaurants [city]`, `vegan restaurants [city]`
- Combined: `vegetarian Italian restaurants [city]`

Always include at least one broad query like `restaurants near [landmark] [city]` to catch places the narrower queries miss.

Write queries to a temp file, one per line.

### Step 4: Run Scraper

Run the scraper via Docker once the required location is known; do not add a separate confirmation prompt just because the scraper takes a few minutes. Refer to `references/scraper-reference.md` for the full command and flags.

Use the pinned Rod-backend image below. The Playwright image is temporarily unavailable because its driver download fails upstream (GitHub issue #302). Do not substitute `gosom/google-maps-scraper:latest` unless its Playwright driver is explicitly revalidated.

Key flags:
- `-geo 'LAT,LON'` -- center the search
- `-radius [meters]` -- search radius (use 2x the user's walking radius to get more candidates)
- `-json` -- structured output for processing
- `-depth 3` -- scroll depth for results
- `-exit-on-inactivity 5m` -- auto-stop when done

### Step 5: Post-Process Results

Run `scripts/filter_results.py` to filter and rank. The script:

1. Deduplicates by title + address
2. Calculates walking distance from the location using haversine formula
3. Filters by the user's max walking radius
4. Checks open hours for the requested day/time (if specified)
5. Scans for dietary signals in the `about` structured data, `categories`, `description`, and `user_reviews` text
6. Ranks results by: dietary match > open at requested time > review rating (weighted by review count)

Usage:
```bash
python3 scripts/filter_results.py \
  --input results.json \
  --lat LAT --lon LON \
  --radius 800 \
  [--dietary vegetarian|vegan] \
  [--day Sunday] [--time 21:00] \
  [--cuisine italian] \
  [--price '$$'] \
  [--max-results 10]
```

### Step 6: Present Results

Show the top matches in a clean format:

```
1. Restaurant Name -- Rating (review count), Price
   Address -- Distance from location
   Sunday hours: X-Y
   Vegetarian: confirmed/likely/unknown
   Relevant review: "..."
   Google Maps: link
```

Group results into tiers:
- **Best matches** -- all criteria met
- **Worth considering** -- most criteria met, one uncertain (e.g. hours unknown)

## User Preferences

Defaults to apply unless the user specifies otherwise:

### Search Parameters
- **Language:** Use the local language of the country being searched (`-lang es` in Mexico, `-lang fr` in France, etc.) -- queries should also be written in the local language
- **Scraper depth:** `-depth 4` -- deeper scroll for more results
- **Scraper radius:** 2x the user's requested distance (e.g. 7km request -> `-radius 10000`)

### Filtering Defaults
- **Minimum rating:** 4.3
- **Exclude chains:** Filter out known chains (e.g. La Casa de Tono, Potzollcalli, Toks, El Huequito, Fisher's) unless explicitly asked
- **Prefer local/non-touristy:** When ranking, favor places with authentic local reviews over influencer-driven spots

### Ranking Formula
- Score = `rating * log10(review_count + 1)`
- Sort open-now places first, then by score descending
- When presenting hidden gems, also sort by fewest reviews to surface under-the-radar spots

### Presentation
- Show Google Maps link for each result
- Include 1-2 relevant review excerpts per place (prefer specific food mentions over generic praise)
- Flag closing times prominently when the user has a time constraint
- Note when a place is known to sell out early
- Group into: open now (confirmed) -> hours unknown -> closing soon -> closed today

## Conventions

- Summarize results cleanly -- use the tiered format described in Step 6
- Use machine-readable output (JSON) when results will be parsed or piped downstream
- Never silently discard results -- if filtering removes all candidates, report what was found and why it was excluded
- Flag uncertain data (unknown hours, unconfirmed dietary info) rather than hiding those results

## Authentication

No authentication required. The scraper uses public Google Maps data.

## Requirements

- Docker installed and running (the scraper runs as a container)
- Image: `gosom/google-maps-scraper@sha256:d1362d953bc6d522bd19901dfca2168bcf65b339718f1d35dfbd53213f6ebb09` (the validated `latest-rod` image as of 2026-07-11)
- Python 3 with standard library (for `scripts/filter_results.py`)

## Notes

- The scraper takes 3-5 minutes minimum to run for typical multi-query searches; the validated depth-1 one-query smoke test completed in ~20 seconds.
- Rod is a temporary workaround. It is an older upstream build, so re-evaluate when the Playwright image has a tested fix for upstream issue #302.
- Rod output uses `longtitude` (legacy misspelling); the current filter script supports it.
- Hours data is not always populated -- flag these as "unknown" rather than excluding
- Future enhancement: augment with Google Places API for structured `servesVegetarianFood` and `regularOpeningHours` fields
