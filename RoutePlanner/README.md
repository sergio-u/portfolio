# RoutePlanner

Generates varied walking routes from a start point and exports them as GPX for
watch apps. I built it to stop retracing the same loops around home. The OSM
engine wanders the real street graph edge by edge, then scores candidates
against the usual failures of generated walks: out-and-back spurs, long straight
runs, and big convex loops that trace a perimeter.

## Features

- Random loops of a target duration via ORS round-trip routing
- "Drunken walk" loops via the OSM street-graph engine (`--engine osm`), which wanders the real walking network edge by edge for exploratory, non-circular routes
- A-to-B walks (for example, home to a cafe through a park)
- Loops visiting one or more points of interest, with detour padding (ORS) or per-leg wandering (OSM) to hit a target time
- `--direct-return` (OSM): wander out through your POIs, then take the shortest path home (carrying groceries)
- POI order auto-picked to fit the time budget (or fixed with `--keep-order`)
- GPX output for watch apps (WorkOutDoors, Komoot, Strava, etc.)
- WorkOutDoors-friendly waypoint cues for turns
- Google Maps deep-link preview that closes loops cleanly
- Separate geocoding tool for resolving addresses/places to coordinates

## Setup

Requires Python 3.10+ and [`uv`](https://github.com/astral-sh/uv).

```
uv sync
```

Create `.env` (gitignored):

```
ORS_API_KEY=your-openrouteservice-key
ORS_BASE_URL=https://api.heigit.org/openrouteservice/v2
PELIAS_BASE_URL=https://api.heigit.org/pelias/v1
WALKING_PACE_KMH=5.6
OUTPUT_DIR=./routes
```

Get a free API key at [openrouteservice.org](https://openrouteservice.org/) (2000 requests/day).

## Usage

### Random loop

```
uv run python -m routeplanner --start LAT,LON --minutes 30
```

### Drunken-walk loop (OSM engine)

```
uv sync --extra osm    # one-time: pulls osmnx/networkx
uv run python -m routeplanner --start LAT,LON --minutes 45 --engine osm
```

The OSM engine walks the actual OSM walking network edge-by-edge with a seeded
RNG (biased against retracing, alleys, and convex "boring circle" shapes), then
closes onto each anchor via shortest path. It generates many candidates per run
and returns the best by route quality. Two dials, both auto-sampled per run so
unspecified runs vary: `--reach` (how far it roams) and `--wiggle` (serpentine).

### Loop via POIs

```
# ORS (detour padding):
uv run python -m routeplanner --start LAT,LON --minutes 40 --poi LAT,LON --poi LAT,LON

# OSM (every leg wanders through each POI):
uv run python -m routeplanner --start LAT,LON --minutes 40 --engine osm --poi LAT,LON

# OSM with a direct shortest path home on the last leg (groceries):
uv run python -m routeplanner --start LAT,LON --minutes 40 --engine osm \
  --poi LAT,LON --direct-return
```

### A-to-B walk (one-way)

```
uv run python -m routeplanner --start LAT,LON --end LAT,LON --minutes 25
uv run python -m routeplanner --start LAT,LON --end LAT,LON --minutes 25 --engine osm
```

### A-to-B via POIs

```
uv run python -m routeplanner --start LAT,LON --end LAT,LON \
  --poi LAT,LON --minutes 30
```

### Flags

| Flag | Default | Notes |
|---|---|---|
| `--start LAT,LON` | required | Start coordinate |
| `--end LAT,LON` | none | Endpoint (omit for a loop back to start) |
| `--poi LAT,LON` | none | Repeatable; intermediate stops |
| `--minutes N` | required | Target walking time |
| `--tolerance N` | 5 | Acceptable +/- minutes |
| `--pace N` | from `.env` | Override walking pace (km/h) |
| `--seed N` | random | For reproducible routes |
| `--engine ors\|osm` | ors | `osm` = street-graph drunken walk (needs `uv sync --extra osm`) |
| `--reach 0-1` | sampled | OSM: how far the walk roams, from compact to far-ranging |
| `--wiggle 0-1` | sampled | OSM: how serpentine the walk is, from straight to switchback |
| `--direct-return` | off | OSM: shortest path on the final leg into the destination |
| `--keep-order` | off | Visit POIs in the given order; default is auto-pick |
| `--no-detours` | off | ORS: direct path through POIs; ignore target length |
| `--label TEXT` | walk | Embedded in output GPX filename |

### Output

```
Length:  3.02 km  (~32.4 min @ 5.6 km/h)
Seed:    511
GPX:     routes/2026-05-26_222959_walk1_s511.gpx
Google:  https://www.google.com/maps/dir/.../data=!4m2!4m1!3e2
```

- The GPX file is the source of truth for the route. AirDrop it to your phone and import it into your walking app. For Apple Watch I use WorkOutDoors (iOS, $6): drop the GPX into Files and it draws the route on the watch dial with off-route alerts. Turn cues are exported as filtered WorkOutDoors-style waypoints to avoid clutter.
- The Google Maps URL uses walking mode and closes loops at your start. Open it to preview the route before heading out.

## Geocoding tool

Resolve a place name or address to coordinates so you can paste them into the route planner.

```
uv run python -m routeplanner.geocode "Espresso Vivace" --country US
uv run python -m routeplanner.geocode "400 Broad St" --near 47.61,-122.34 --within 5
```

Flags: `--near LAT,LON`, `--within KM` (requires `--near`), `--country ISO`, `--layers venue,address,...`, `--size N`.

## Project structure

```
routeplanner/
  config.py    # Load settings from .env
  geo.py       # Coord dataclass + haversine, bearing, offset math
  strategy.py  # Plan waypoints (round_trip or anchored with detours)
  ors.py       # OpenRouteService HTTP client
  osm_walk.py  # OSM street-graph random-walk engine (--engine osm)
  scoring.py   # Route quality guardrails and candidate ranking
  geocode.py   # Pelias forward-geocoding CLI
  export.py    # GPX writer + Google Maps URL builder
  cli.py       # Argparse, retry loop, output
  __main__.py  # Entry point for `python -m routeplanner`
```

## Known limitations

- ORS snaps your input coordinate to the nearest pedestrian node, which can land on a different street where OSM walking data is sparse. The URLs always use your input coordinate; the routed GPX starts at the snap point.
- If routing through your POIs already exceeds the target time, the script reports "best-effort" with the closest match instead of shortening the route. Raise `--minutes` or `--tolerance`.
- ORS round-trip loops come out about 5-10% longer than requested. Widen `--tolerance` or aim slightly low if you need a hard target.
- Apple Maps URLs don't support multi-stop walking, so there is no Apple Maps link. Use the GPX or the Google link.
