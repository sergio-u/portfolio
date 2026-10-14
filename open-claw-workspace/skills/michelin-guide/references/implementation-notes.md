# Michelin Guide Implementation Notes

## Why live-first

This skill complements `restaurant-finder`, so its default job is recommendation-time enrichment rather than global analytics. It should search current Michelin listing/detail pages for the area being considered and annotate candidate restaurants.

## Reference reconnaissance

- `xubing0602/dining_map`: best current extraction strategy observed. It uses list pages first, then detail pages, with JSON-LD + `dLayer` / data attributes + HTML fallback. No license was visible during initial research, so use only as a conceptual reference.
- `timrogers/michelin-guide-scraper`: MIT, simple TypeScript implementation that finds list cards and parses detail-page JSON-LD.
- `ngshiheng/michelin-my-maps`: MIT, mature Go/Colly project with conservative crawling, historical DB, and CSV/Kaggle outputs. Good reference if adding offline/historical mode later.

## Tested sample listing URLs

- `https://guide.michelin.com/us/en/city-of-edinburgh/edinburgh/restaurants`
  - Scrapling Fetcher returned 200 and 44 `.card__menu` cards on 2026-07-06.
- `https://guide.michelin.com/us/en/ciudad-de-mexico/roma-sur_2000648_noindex/restaurants`
  - Scrapling Fetcher returned 200 and 52 `.card__menu` cards on 2026-07-06.

Direct curl to award pages returned an AWS WAF challenge from this host; Scrapling Fetcher worked on the city/neighborhood listing pages.

## Current parser strategy

List cards expose enough metadata for a quick Michelin signal:

- `.card__menu` with `data-id`, `data-lat`, `data-lng`, `data-map-pin-name`
- nested `a.link` detail URL
- nested `data-restaurant-name`
- nested `data-dtm-distinction`, `data-distinction`, `data-green-star`, `data-dtm-price`, `data-dtm-city`, `data-dtm-region`, `data-restaurant-country`
- `.card__menu-footer--score` for location and price/cuisine text

Detail pages expose:

- `script[type="application/ld+json"]` for schema.org restaurant data
- `.restaurant-details__likeinfo` / `.js-favorite-restaurant` data attributes
- `.data-sheet__description` for fuller inspector text
- `a[data-event="CTA_website"]` and `a[data-event="CTA_tel"]`

## Future upgrades

- Discover Michelin listing URLs from free-form city/neighborhood names.
- Add optional browser fallback for pages where Scrapling Fetcher fails.
- Add radius/nearby filtering using lat/lon from Michelin cards/details.
- Add a tiny TTL cache with visible `fetched_at`, off by default for explicit fresh runs.
- Add export to GeoJSON/Google My Maps-compatible CSV.
