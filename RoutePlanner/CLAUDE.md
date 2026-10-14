# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Run commands

This is a `uv`-managed Python project (no Makefile, no test runner, no linter set up).

```
uv sync                                                       # install deps into .venv
uv sync --extra osm                                           # + OSM engine deps (osmnx etc.)
uv run python -m routeplanner --start LAT,LON --minutes 30    # route planner CLI (ORS engine)
uv run python -m routeplanner --start LAT,LON --minutes 30 --engine osm   # graph random-walk
uv run python -m routeplanner.geocode "place name"            # geocoding CLI
```

There is no test suite. The modules with non-trivial pure logic that would be most worth testing if it's ever added are `geo.py`, `strategy.py`, `scoring.py`, and `osm_walk.py`.

## Architecture

The package is a thin pipeline: **CLI args → (engine) → export**, where the engine is one of two:

- **ORS** (default, `--engine ors`): `strategy.plan()` builds a spec, `ors.route()` calls OpenRouteService.
- **OSM** (`--engine osm`): `osm_walk.route_through()` walks the OSM street graph directly through an anchor list (loops, `--poi`, `--end`, all supported). Needs the `osm` extra.

Both engines emit the same `ors.RouteResult(polyline, length_m, steps)`, so `export.py`, `scoring.py`, and the `cli.py` retry loop are engine-agnostic. Two entry points share the package: `routeplanner` (route generator) and `routeplanner.geocode` (Pelias address lookup). They share `config.py` and the `Coord` type but are otherwise independent.

The modules with real algorithmic content are `strategy.py` (ORS spec/detour math), `osm_walk.py` (graph random walk), and `scoring.py` (route quality metric). Everything else is plumbing.

### Spec dispatch in `strategy.py`

`plan(inputs)` returns one of two specs based on whether POIs and/or an end point are provided:

| `pois` | `end` | Spec | How ORS handles it |
|---|---|---|---|
| ✗ | ✗ | `RoundTripSpec` | ORS's `round_trip` endpoint (seed → varied loop) |
| any | any other combo | `WaypointSpec` | Standard directions with explicit waypoints |

For `WaypointSpec` mode, the anchor list is `[start, *ordered_pois, end]` (where `end == start` for loops without an explicit endpoint). When the straight-line length is below target, `_pad_with_detours` inserts random perpendicular waypoints between each anchor pair — that's the only place "make the route longer" logic lives. The detour math uses straight-line geometry; real walking distance is typically 1.2–1.6× longer, so the retry loop in `cli.py` re-rolls the seed up to 5 times trying to land in tolerance.

### Retry loop lives in `cli.py`, not `strategy.py`

`strategy.plan()` is pure — given inputs, produces a spec, deterministic with the seed. The retry loop that bumps the seed and re-calls the engine on tolerance misses is in `cli.main()` (shared by both engines via `_finish_best_effort`). If all `MAX_ATTEMPTS` retries miss, it surfaces a "best-effort" message with the closest match. `osm_walk.route_through()` is likewise pure/deterministic-with-seed. Don't move retry logic into `strategy.py` or `osm_walk.py`.

### OSM random-walk engine (`--engine osm`)

`osm_walk.route_through(start, pois, end, …)` produces a "drunken walk" over an ordered anchor list `[start, *ordered_pois, end]` (`end == start` for a loop). Each **leg** between consecutive anchors is walked edge-by-edge with a seeded RNG, then closed onto the next anchor via shortest path — exploration happens at street granularity, so legs fill their footprint instead of tracing a boring convex circle (the ORS `round_trip` failure mode). Pure/deterministic given `(start, pois, end, target_m, seed, reach, wiggle, keep_order, direct_return)`; returns a normal `RouteResult`. The pure home loop is the degenerate single-leg `a_node == b_node` case (so `route_loop()` is just a thin wrapper); POI order is picked by reused `strategy._choose_order`.

- **One walker, two leg flavours** (`_one_leg`): a **loop leg** (`a == b`) drifts *away* from home (`bias_sign=-1`, fixed `OUTBOUND_STRENGTH`) and is held in by a max-home-radius cap; a **transit leg** (`a != b`) drifts *toward* B with a **progress-coupled pull** (≈0 while budget is plentiful → free meander, ramping up as the remaining budget nears the straight-line-to-B → commits to arriving) and is held inside a **reach-scaled corridor** around the straight A–B line. `_step_weight` is shared — only the bias bearing and the cap differ. **Don't** re-derive the loop's outbound drift from a knob (it produced elongated lobes that read as circular).
- **Per-leg budget** (`_allocate_budgets`): `target_m` is split across legs proportional to each leg's straight-line share, floored at that straight line. **`--direct-return`** makes the final leg a shortest path (carrying groceries home); it claims its real path length and the wander budget shifts to the earlier legs. If the anchors' straight-line sum already exceeds target the route comes out long — the honest "geographically infeasible" case surfaced as best-effort, never a silent target bump.
- **Don't re-walk the same street**: recently-used edges get a strong weight penalty, any earlier-used edge a mild one, and shortest-path closes inflate already-walked edges (`RETRACE_PENALTY`). These are penalties, not bans — short reuse is allowed when it's the only way through. Circles are penalized (see metric) but stay valid; the goal is variety, not banning shapes.
- **Length control**: each leg stops when `walked + 1.25 × straight-line-to-anchor ≥ leg_budget` (no systematic undershoot). Each call generates `CANDIDATES_PER_CALL` whole routes and returns the best by `_candidate_score` (length miss dominates, route quality breaks ties), so each retry attempt is already de-circled.
- **lat-first**: the ONLY place lon/lat order is crossed is the osmnx boundary (`nearest_nodes(X=lon, Y=lat)`, node `x`/`y`) — same discipline as the ORS boundary. Don't shuffle order elsewhere.
- **Graph cache**: graphs are multi-MB Overpass downloads cached to `OSM_CACHE_DIR` (`./.osm_cache`) keyed by rounded center + radius bucket. The center is the anchors' bbox center and the radius covers the farthest anchor (plus wander room) so a distant POI/end is never outside the disk; for a pure loop this reduces to the start + loop footprint, so loop runs share the same cache file as before. Reused when a cached graph covers the request. This is exempt from the "no caching / single-flight" rule below — that rule is about the quota'd ORS API, not a graph it would be absurd to re-fetch per seed bump.

### Route quality metric (`scoring.py`)

`route_quality_breakdown()` returns meters-equivalent penalties: `self_overlap` (retracing), `straight_run` (commute-like), and **`circular`** — the "boring circle" detector. `--debug-score` shows these for the ORS engine; the OSM engine instead prints the exact signals it selected on (`RouteResult.debug`: retrace_m, doubleback_m, crossings, alley_pct, circular, ...), since it has edge-level info the geometric proxy lacks. `circular` penalizes loops whose length is low relative to their **convex-hull perimeter** (a circle/convex blob ≈ 1.0×; a dense wander ≈ 1.6–1.8×). It's loop-only (skipped when start≠end, since a point-to-point route legitimately has a thin hull) and a soft penalty, not a filter — circles still win when they're the best length fit.

### Coord convention

The internal `Coord(lat, lon)` dataclass uses **lat first** everywhere. Conversions to `[lon, lat]` happen only at the ORS boundary (`ors.py` body construction and response parsing). Don't shuffle the order inside `strategy.py` or `geo.py`.

### Google Maps URL: path-style, not `api=1`

`export.google_maps_url()` uses the path-style URL (`/maps/dir/lat,lon/lat,lon/.../data=!4m2!4m1!3e2`), **not** the documented `api=1&waypoints=` form. The `api=1` form silently breaks when `origin == destination` (Apple-Maps-like collapsing to a single-stop route) and has a 9-waypoint cap. The path-style form closes loops cleanly when the first and last segments are identical and has no cap. The opaque `data=!4m2!4m1!3e2` blob is Google's minimal encoded walking-mode flag (`!3e2` = enum 2 = walking) — leave it as-is unless you've verified an alternative.

Apple Maps URLs were tried and removed: the URL scheme doesn't reliably render multi-stop walking. Don't add them back.

### Endpoints (read carefully)

The ORS hosted service has migrated. Use exactly:

- Directions: `https://api.heigit.org/openrouteservice/v2` ← *with* the `/openrouteservice/` segment
- Pelias geocode: `https://api.heigit.org/pelias/v1`

Both `api.openrouteservice.org/...` (deprecated) and `api.heigit.org/v2/...` (no `/openrouteservice/`) return 404. Authentication for both is the **same** ORS API key passed in an `Authorization` header.

## Project preferences

- **Skip defensive validation scaffolding.** Don't add mirrored allowlists, frozensets-of-valid-values, or parse-time gates for things the upstream API already knows (e.g. Pelias layer names). Pass user inputs through and let the API surface errors. This was tried for `--layers` and rolled back.
- **No hardcoded coordinate defaults.** Start, end, and POIs are always explicit CLI params; the `.env` carries service config (API key, endpoint, pace) but not locations.
- **Single-flight ORS calls.** No caching, no async, no batching — calls are 100–500ms and the daily quota is 2000. Keep `ors.py` a thin pass-through.

## Empirical gotchas

- **ORS snaps inputs.** Your start coord can get snapped onto a different street if OSM walking data is sparse. The URLs always print your input coord, but the GPX starts at the snap point. Document this when surprising; don't try to "fix" it with `radiuses` (causes more failures than it prevents).
- **ORS `round_trip` overshoots length.** Random loops come out ~5–10% longer than the requested `length`. The retry loop absorbs this for most targets; widen `--tolerance` for tight budgets.
- **POI loops can be geographically infeasible.** If `home → POIs → home` already exceeds the target time at walking speeds, no detour math can shorten it. The retry loop surfaces "best-effort" — that's the honest behavior; don't try to "fix" it by silently bumping the target.
