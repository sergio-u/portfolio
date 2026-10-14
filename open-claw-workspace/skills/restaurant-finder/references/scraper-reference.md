# Google Maps Scraper Reference

Source: https://github.com/gosom/google-maps-scraper

## Active Workaround

Use the validated Rod-backend image while the Playwright image is broken upstream:

```text
gosom/google-maps-scraper@sha256:d1362d953bc6d522bd19901dfca2168bcf65b339718f1d35dfbd53213f6ebb09
```

This digest was validated on 2026-07-11 against a real Google Maps query: it returned 20 valid records with no failed jobs, and `scripts/filter_results.py` successfully filtered/ranked them.

Do **not** use the mutable `latest` tag: it currently fails at startup when Playwright-Go tries to download the removed `playwright-1.57.0-linux.zip` driver (upstream issue https://github.com/gosom/google-maps-scraper/issues/302).

## Docker Run Command

```bash
mkdir -p /tmp/restaurant-finder && \
touch /tmp/restaurant-finder/results.json && \
docker run --rm --shm-size=1g \
  -v /path/to/queries.txt:/queries:ro \
  -v /tmp/restaurant-finder/results.json:/results.json \
  gosom/google-maps-scraper@sha256:d1362d953bc6d522bd19901dfca2168bcf65b339718f1d35dfbd53213f6ebb09 \
  -input /queries \
  -results /results.json \
  -json \
  -depth 3 \
  -c 1 \
  -geo 'LAT,LON' \
  -radius METERS \
  -exit-on-inactivity 5m
```

`--shm-size=1g` provides Chromium enough shared memory. Start at `-c 1` and increase only after validating a representative multi-query search.

## Key CLI Flags

| Flag | Description | Default |
|---|---|---|
| `-input` | Path to queries file (one query per line) | required |
| `-results` | Output file path | stdout |
| `-json` | Output JSON instead of CSV | CSV |
| `-depth` | Max scroll depth in results list | 10 |
| `-geo` | Center coordinates, e.g. `'25.0807,-77.3425'` | none |
| `-radius` | Search radius in meters | 10000 |
| `-zoom` | Map zoom level 0-21 | 15 |
| `-lang` | Language code for results | en |
| `-c` | Concurrency (parallel jobs) | half CPU cores |
| `-exit-on-inactivity` | Auto-exit after idle period | none |
| `-email` | Extract emails from business websites | off |
| `-extra-reviews` | Collect up to ~300 reviews per place | off |

## Input Format

Plain text, one query per line. Natural language — same as typing into Google Maps:

```
restaurants near Pike Place Market Seattle
vegetarian restaurants Capitol Hill Seattle
sushi restaurants downtown Seattle
```

Optional custom ID suffix: `query text #!#MyCustomID`

## Output Format (JSON)

Newline-delimited JSON (one JSON object per line). Key fields:

```json
{
  "title": "Restaurant Name",
  "category": "Italian restaurant",
  "categories": ["Italian restaurant", "Pizza restaurant"],
  "address": "123 Main St, City",
  "complete_address": { "street": "...", "city": "...", "state": "...", "country": "..." },
  "open_hours": {
    "Monday": ["11\u202fAM\u201310\u202fPM"],
    "Sunday": ["12\u20139\u202fPM"]
  },
  "review_rating": 4.5,
  "review_count": 200,
  "price_range": "$$",
  "description": "...",
  "about": [
    {
      "id": "offerings",
      "name": "Offerings",
      "options": [
        { "name": "Vegetarian options", "enabled": true },
        { "name": "Vegan options", "enabled": true }
      ]
    }
  ],
  "user_reviews": [
    {
      "Name": "Reviewer",
      "Rating": 5,
      "Description": "Review text..."
    }
  ],
  "latitude": 25.0807,
  "longtitude": -77.3425,
  "link": "https://www.google.com/maps/place/...",
  "web_site": "https://restaurant.com",
  "menu": { "link": "...", "source": "..." },
  "phone": "..."
}
```

Note: Rod emits the legacy `longtitude` spelling. The restaurant filter script supports this exact field name.

## Performance

- The 2026-07-11 Rod smoke test returned 20 records from one local query at `-depth 1 -c 1` in ~20 seconds.
- First run may download the image if it is absent locally.
- Typical multi-query restaurant searches still need several minutes.

## Tips

- Use `-depth 3` for most searches (balance between coverage and speed)
- Set `-radius` to 2x the desired walking radius to catch nearby places that Google indexes at slightly different coordinates
- The `about` field contains structured Google Maps attributes including dietary options — more reliable than text search
- The `open_hours` dict uses full day names as keys (e.g., "Sunday"), with values as lists of time-range strings
- Time ranges use Unicode narrow no-break space (`\u202f`) and en-dash (`\u2013`) separators
