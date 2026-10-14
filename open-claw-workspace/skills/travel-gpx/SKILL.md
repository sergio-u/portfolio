---
name: "travel-gpx"
description: "Generate WorkOutDoors-friendly GPX files and reverse-geocode waypoint labels."
---

# Travel GPX / WorkOutDoors Routes

Use this skill when Sergio asks to create, export, or prototype a GPX walking route for a trip day, especially for Apple Watch + WorkOutDoors.

## Goal

Turn a loose travel-day plan into one or more `.gpx` files that are easy to import into WorkOutDoors. The GPX is a flexible walking spine, not a replacement for Google Maps POI details, hours, transit, or ad hoc search.

## Inputs

Ask only for information that is genuinely missing:

- city/date/theme
- start/end anchors
- main stops and optional backups
- exact coordinates when available
- desired variants: `core`, `scenic`, `low-energy`, etc.

If coordinates are missing, resolve or research them before generating GPX. Keep uncertainty visible in waypoint notes when coordinates/hours are not verified.

## Route spec format

Create a JSON or YAML spec with:

- `name`, `city`, optional `date`, optional `theme`, optional `description`
- `waypoints`: objects with `id`, `name`, `lat`, `lon`, optional `role`, `address`, `notes`, `optional`
- `variants`: objects with `id`, optional `name`, `waypoint_order`, optional `track_mode`

Use `examples/madrid-prado-sunset.json` as the starting template.

## Generate GPX

Run:

```bash
python3 scripts/travel_gpx.py path/to/spec.json --output-dir routes/travel
```

Useful options:

```bash
# waypoint-only GPX, no connector track
python3 scripts/travel_gpx.py path/to/spec.json --track-mode waypoints-only

# include route-point elements as well as waypoints/track for app compatibility testing
python3 scripts/travel_gpx.py path/to/spec.json --include-route
```

Default output is one GPX per variant, named from date/city/theme plus the variant id.

## Reverse geocoding / coordinate sanity checks

The RoutePlanner reference repo currently has a Pelias forward-geocoding CLI (`routeplanner/geocode.py`), not a reverse-geocoding CLI, but the same HeiGIT Pelias base URL and ORS API key convention apply. Use the companion reverse-geocode script when you need to sanity-check coordinates or enrich anonymous GPX points with nearby place/address labels.

```bash
# one or more explicit coordinates
python3 scripts/reverse_geocode.py --coord 40.4138,-3.6921 --layers venue,address

# inspect existing GPX waypoints, or trackpoints if there are no waypoints
python3 scripts/reverse_geocode.py --gpx routes/travel/example.gpx --layers venue,address --json
```

The script reads `ORS_API_KEY` and optional `PELIAS_BASE_URL` from the environment, matching RoutePlanner's config pattern. Treat reverse-geocoded labels as hints, not source-of-truth POI verification.

## WorkOutDoors compatibility guidance

The RoutePlanner reference repo exports `<wpt>` markers plus a `<trk>` line for WorkOutDoors. Follow that pattern by default:

- include waypoint names that are short and useful on the watch
- put purpose/caveats in `<desc>`
- include a simple `<trk>` connector when we want a visible route spine
- use waypoint-only mode when the route line would be misleading
- make variants separate GPX files for v1

Do not overbuild routing for v1. If walking routing is unavailable, generate waypoint-only or straight-line connector GPX and clearly label it as a flexible spine, not turn-by-turn directions.

## Output contract

When done, return:

- generated GPX file path(s)
- short route summary
- waypoint list by variant
- assumptions/caveats
- optional Google Maps checklist/search links for POI detail verification

Attach generated GPX files when the channel supports file attachments.

## Safety / account boundaries

- GPX generation is local-file-only and safe.
- Reverse geocoding calls HeiGIT Pelias with coordinates; use only when that external lookup is appropriate.
- Do not mutate Google Maps saved lists unless explicitly requested.
- Do not use Google account/browser automation by default.
- Verify coordinates and hours when they matter; otherwise mark them as assumptions.

## Reference notes

Sergio's RoutePlanner repo is the GPX reference implementation. Useful pieces inspected:

- `routeplanner/export.py`: GPX writer with WorkOutDoors-style waypoints and `<trk>` output.
- `routeplanner/geocode.py`: Pelias forward geocoder; reverse geocoding should mirror this simple HTTP pattern but call `/reverse` with `point.lat`/`point.lon`.
- `README.md`: confirms WorkOutDoors import flow and GPX as source of truth.
- `CLAUDE.md`: preserves lat-first `Coord(lat, lon)` convention and notes that `<trk>` + waypoint cues are the established path.

V1 here intentionally starts with a small local spec-to-GPX generator instead of requiring ORS/Pelias API keys. Later versions can reuse more of RoutePlanner for true walking paths or turn cue generation.
