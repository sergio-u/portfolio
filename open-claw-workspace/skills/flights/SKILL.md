---
name: flights
description: >
  Search for flights using Google Flights via the fast-flights library.
  Use when the user says "search flights", "find flights to", "cheapest flight",
  "flight prices", "fly from X to Y", "when is cheapest to fly", or wants to
  compare prices or plan air travel.
---

# Flights

## Execution

### Search Flights (specific date)

```bash
uv run skills/flights/search_flights.py <origin> <destination> <date> [options]
```

#### Examples

```bash
# One-way, cheapest first
uv run skills/flights/search_flights.py SEA MEX 2026-03-20

# Round trip
uv run skills/flights/search_flights.py SEA MEX 2026-03-20 -r 2026-03-28

# Nonstop only, top 3
uv run skills/flights/search_flights.py SEA MEX 2026-03-20 -r 2026-03-28 -s NON_STOP -n 3

# Business class, morning departures
uv run skills/flights/search_flights.py SEA MEX 2026-03-20 -c BUSINESS -t 6-12

# Evening arrival window (e.g. land around 9pm)
uv run skills/flights/search_flights.py SEA SFO 2026-09-05 -s NON_STOP --arrival-time 19-23

# JSON output for processing
uv run skills/flights/search_flights.py SEA MEX 2026-03-20 -r 2026-03-28 --json
```

#### Options

| Flag | Description |
|------|-------------|
| `-r, --return-date` | Return date (YYYY-MM-DD) for round trip |
| `-c, --cabin-class` | ECONOMY, PREMIUM_ECONOMY, BUSINESS, FIRST |
| `-s, --max-stops` | ANY, NON_STOP, ONE_STOP, TWO_PLUS_STOPS |
| `-o, --sort-by` | CHEAPEST, DURATION, DEPARTURE_TIME, ARRIVAL_TIME |
| `-t, --time` | Departure window (e.g., 6-20 for 6am-8pm) |
| `--arrival-time` | Arrival window (e.g., 19-23) |
| `-a, --airlines` | Filter by IATA codes (e.g., -a AA DL UA) |
| `-p, --passengers` | Number of adult passengers (default: 1) |
| `-n, --max-results` | Max results to show (default: 10) |
| `--currency` | Currency code (default: USD) |
| `--hide-separate-tickets` | Hide separate-ticket / self-transfer itineraries |
| `--json` | Output JSON instead of formatted text |

### Search Dates (cheapest dates in a range)

```bash
uv run skills/flights/search_dates.py <origin> <destination> -f <start> -t <end> [options]
```

`fast-flights` has no native date-range endpoint, so this script sweeps the
range one date at a time in parallel and reports the best price per date or
date pair. Cost grows with the number of candidate dates — keep ranges tight.

#### Examples

```bash
# Find cheapest dates for a 9-day round trip in March
uv run skills/flights/search_dates.py SEA MEX -f 2026-03-15 -t 2026-03-31 -d 9 -R --sort-by-price

# Fixed outbound, flexible return window
uv run skills/flights/search_dates.py SEA SFO -f 2026-09-05 -t 2026-09-05 \
  --return-from 2026-09-29 --return-to 2026-10-04 -s NON_STOP --sort-by-price

# One-way, filter to weekends only
uv run skills/flights/search_dates.py SEA MEX -f 2026-03-15 -t 2026-04-15 --days fri sat

# JSON output
uv run skills/flights/search_dates.py SEA MEX -f 2026-03-15 -t 2026-03-31 -d 7 -R --json
```

#### Options

| Flag | Description |
|------|-------------|
| `-f, --from-date` | Start of departure date range (required) |
| `-t, --to-date` | End of departure date range (required) |
| `-d, --duration` | Trip duration in days (default: 7) |
| `-R, --round-trip` | Search round-trip flights |
| `--return-from` | Start of return date range (overrides `--duration`) |
| `--return-to` | End of return date range (overrides `--duration`) |
| `-c, --cabin-class` | ECONOMY, PREMIUM_ECONOMY, BUSINESS, FIRST |
| `-s, --max-stops` | ANY, NON_STOP, ONE_STOP, TWO_PLUS_STOPS |
| `-a, --airlines` | Filter by IATA codes |
| `--time` | Outbound departure window (e.g., 6-20) |
| `--return-time` | Return departure window (e.g., 17-23) |
| `--sort-by-price` | Sort results cheapest first |
| `--days` | Filter departure by day of week (e.g., --days mon fri) |
| `--return-days` | Filter return by day of week (e.g., --return-days sat sun) |
| `-p, --passengers` | Number of adult passengers (default: 1) |
| `-n, --max-results` | Max results (default: 20) |
| `--currency` | Currency code (default: USD) |
| `--hide-separate-tickets` | Hide separate-ticket / self-transfer itineraries |
| `--workers` | Parallel requests (default: 4) |
| `--json` | Output JSON |

## Reference

### Fallback: Google Flights via Browser

If `fast-flights` returns empty results or Google changes its response format,
use `agent-browser` with Google Flights' natural language URL query as a fallback:

```bash
WS_URL=$(curl -s http://<home-server>:9222/json/version | jq -r '.webSocketDebuggerUrl')
npx agent-browser --cdp "$WS_URL" open "https://www.google.com/travel/flights?q=flights+from+ORD+to+MEX+on+March+18+2026+one+way"
npx agent-browser --cdp "$WS_URL" wait --load networkidle
npx agent-browser --cdp "$WS_URL" snapshot -i -u
```

Google Flights parses the natural language query in the `q=` parameter and pre-fills the search form. The snapshot output includes flight links with prices, airlines, times, stops, and durations embedded in the link text -- grep for `"From [0-9]+ US dollars"` to extract results quickly.

**Tips:**
- Use `+` for spaces in the URL query string.
- Queries like `round trip nonstop flights from SEA to SFO departing September 5 2026 returning October 3 2026` work well.
- Adding time filters like `after 4pm` in the query is unreliable -- use the script flags or filter results manually instead.
- For round trips, the snapshot initially shows only outbound options. Click the desired outbound (via `eval` on the `[role="link"]` aria-label) to reveal returning flights.
- This approach is slower than the Python scripts but returns richer data (baggage allowance, separate-ticket warnings, price insights).
- Always `npx agent-browser --cdp "$WS_URL" close` when done.

## Conventions

- Airport codes are IATA (3-letter): SEA, MEX, JFK, LAX, etc.
- Dates are always YYYY-MM-DD.
- Default sort is CHEAPEST. Use DURATION when the user cares about travel time.
- Use `search_dates.py` when the user has flexible dates; `search_flights.py` for specific dates.
- For comparing multiple date combos, prefer `search_dates.py` with `--round-trip` over multiple `search_flights.py` calls.
- Present results as a clean summary; only show raw JSON if the user asks.
- Use `--json` for machine-readable output when parsing results programmatically.
- Confirm before running large batch searches across many date ranges.
- Prices are live and change frequently; note this when advising on booking.

## Requirements

- `uv` must be installed (script dependencies are managed inline via uv).
- `fast-flights` (>=3.1.0) plus `typing_extensions`, installed automatically by uv
  from inline script metadata.

## Authentication

No authentication required. `fast-flights` queries Google Flights directly
without API keys, using a Base64-encoded Protobuf query string.
