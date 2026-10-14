"""CLI entry point: parse args, run retry loop, print outputs."""
from __future__ import annotations

import argparse
import dataclasses
import random
import sys
from typing import Sequence

from . import export, ors, osm_walk
from .config import Config, load
from .geo import Coord
from .scoring import route_quality_breakdown
from .strategy import PlanInputs, minutes_to_m, plan

MAX_ATTEMPTS = 5


def _parse_coord(s: str) -> Coord:
    parts = s.split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Expected 'lat,lon', got {s!r}")
    try:
        return Coord(lat=float(parts[0].strip()), lon=float(parts[1].strip()))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Could not parse coords {s!r}: {exc}")


def _unit_float(s: str) -> float:
    try:
        value = float(s)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected a number in 0.0-1.0, got {s!r}: {exc}")
    if not 0.0 <= value <= 1.0:
        raise argparse.ArgumentTypeError(f"Expected a value in 0.0-1.0, got {value}")
    return value


def _resolve_dial(value: float | None, rng: random.Random, center: float = 0.5) -> float:
    """Use an explicit dial value, or sample one around `center` (clamped to 0-1).

    Sampling keeps unspecified runs varied without the user touching the dials;
    drawing from a seeded rng keeps a given --seed reproducible.
    """
    if value is not None:
        return value
    return min(1.0, max(0.0, rng.gauss(center, 0.2)))


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="routeplanner",
        description="Generate walking routes from a start point.",
    )
    p.add_argument("--start", type=_parse_coord, required=True, help="lat,lon")
    p.add_argument("--end", type=_parse_coord, default=None,
                   help="lat,lon (omit for a loop back to --start)")
    p.add_argument("--poi", type=_parse_coord, action="append", dest="pois", default=None,
                   help="lat,lon for a point of interest. Repeatable.")
    p.add_argument("--minutes", type=float, required=True, help="Target walk time")
    p.add_argument("--tolerance", type=float, default=5.0, help="+/- minutes (default 5)")
    p.add_argument("--pace", type=float, default=None,
                   help="Walking pace km/h. Overrides WALKING_PACE_KMH from .env.")
    p.add_argument("--seed", type=int, default=None, help="Random seed (default: random)")
    p.add_argument("--keep-order", action="store_true",
                   help="Visit POIs in the given order. Default: algorithm picks order.")
    p.add_argument("--no-detours", action="store_true",
                   help="Direct path through POIs; ignore target length.")
    p.add_argument("--engine", choices=["ors", "osm"], default="ors",
                   help="Routing engine: 'ors' (OpenRouteService) or 'osm' (street-graph "
                        "random walk; needs `uv sync --extra osm`).")
    p.add_argument("--direct-return", action="store_true",
                   help="OSM engine: take the shortest path on the final leg into "
                        "the destination (e.g. carrying groceries home) instead of "
                        "wandering; the wander budget shifts to the earlier legs.")
    p.add_argument("--reach", type=_unit_float, default=None,
                   help="OSM engine: how far the walk roams 0.0-1.0, compact/local (0) to "
                        "far-ranging (1). Default: sampled ~0.5 per run (seeded).")
    p.add_argument("--wiggle", type=_unit_float, default=None,
                   help="Serpentine dial 0.0-1.0: gentle curves (0) to tight switchbacks "
                        "(1). Default: sampled ~0.7 per run (seeded).")
    p.add_argument("--debug-score", action="store_true",
                   help="Print the route quality penalty breakdown for the chosen route.")
    p.add_argument("--label", default="walk", help="Label embedded in the GPX filename.")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    cfg = load()
    pace = args.pace if args.pace is not None else cfg.walking_pace_kmh
    target_m = minutes_to_m(args.minutes, pace)
    tolerance_m = minutes_to_m(args.tolerance, pace)
    base_seed = args.seed if args.seed is not None else random.randint(0, 1_000_000)

    if args.engine == "osm":
        dial_rng = random.Random(base_seed)
        # Unspecified dials sample normally around a center (seeded), so routes
        # vary run-to-run without the user touching the knobs.
        reach = _resolve_dial(args.reach, dial_rng)
        wiggle = _resolve_dial(args.wiggle, dial_rng, center=0.7)
        print(f"Dials:   reach={reach:.2f}  wiggle={wiggle:.2f}")
        best: tuple[float, ors.RouteResult, int] | None = None
        for attempt in range(MAX_ATTEMPTS):
            # SystemExit (missing osm extra) is BaseException, so it propagates
            # past this Exception handler and surfaces its install hint directly.
            try:
                result = osm_walk.route_through(
                    args.start, args.pois or [], args.end, target_m,
                    base_seed + attempt, reach, wiggle, cfg.graph_cache_dir,
                    keep_order=args.keep_order, direct_return=args.direct_return,
                )
            except Exception as exc:
                print(f"[attempt {attempt + 1}] OSM walk error: {exc}", file=sys.stderr)
                continue
            delta = abs(result.length_m - target_m)
            if delta <= tolerance_m:
                _print_result(result, base_seed + attempt, args.label, cfg, pace,
                              input_start=args.start, input_end=args.end, pois=args.pois,
                              exact=True, debug_score=args.debug_score)
                return 0
            if best is None or delta < best[0]:
                best = (delta, result, base_seed + attempt)
        return _finish_best_effort(best, args, cfg, pace)

    base = PlanInputs(
        start=args.start,
        target_minutes=args.minutes,
        tolerance_minutes=args.tolerance,
        pace_kmh=pace,
        pois=args.pois,
        end=args.end,
        seed=base_seed,
        keep_order=args.keep_order,
        no_detours=args.no_detours,
    )

    best: tuple[float, ors.RouteResult, int] | None = None
    for attempt in range(MAX_ATTEMPTS):
        attempt_inputs = dataclasses.replace(base, seed=base_seed + attempt)
        spec = plan(attempt_inputs)
        try:
            result = ors.route(spec, cfg.ors_api_key, cfg.ors_base_url)
        except Exception as exc:
            print(f"[attempt {attempt + 1}] ORS error: {exc}", file=sys.stderr)
            continue
        delta = abs(result.length_m - target_m)
        if delta <= tolerance_m:
            _print_result(result, base_seed + attempt, args.label, cfg, pace,
                          input_start=args.start, input_end=args.end, pois=args.pois,
                          exact=True, debug_score=args.debug_score)
            return 0

        if best is None or delta < best[0]:
            best = (delta, result, base_seed + attempt)

    return _finish_best_effort(best, args, cfg, pace)


def _finish_best_effort(
    best: tuple[float, ors.RouteResult, int] | None,
    args: argparse.Namespace,
    cfg: Config,
    pace: float,
) -> int:
    """Print the closest-match result after the retry loop, or fail if none."""
    if best is None:
        print("All attempts failed. Check inputs and try again.", file=sys.stderr)
        return 1

    exact = best[0] <= minutes_to_m(args.tolerance, pace)
    if not exact:
        print(
            f"Could not hit target +/- {args.tolerance:.0f}min in {MAX_ATTEMPTS} attempts; "
            "showing closest match.",
            file=sys.stderr,
        )
    _print_result(best[1], best[2], args.label, cfg, pace,
                  input_start=args.start, input_end=args.end, pois=args.pois,
                  exact=exact, debug_score=args.debug_score)
    return 0


def _print_result(
    result: ors.RouteResult,
    seed: int,
    label: str,
    cfg: Config,
    pace_kmh: float,
    input_start: Coord,
    input_end: Coord | None,
    pois: list[Coord] | None,
    exact: bool,
    debug_score: bool = False,
) -> None:
    est_minutes = result.length_m / (pace_kmh * 1000 / 60)
    waypoints: list[tuple[str, Coord]] = [("Start", input_start)]
    if pois:
        for i, poi in enumerate(pois, 1):
            waypoints.append((f"POI {i}", poi))
    if input_end is not None:
        waypoints.append(("End", input_end))
    # Engines that pick their own cues (OSM) pass them directly as named
    # waypoints; engines that rely on ORS-style step filtering pass `steps`.
    if result.turn_cues is not None:
        waypoints.extend(result.turn_cues)
    gpx_path = export.write_gpx(
        result.polyline, cfg.output_dir, f"{label}_s{seed}",
        waypoints=waypoints, steps=result.steps,
    )
    preview = export.sample_for_preview(result.polyline, n=8)
    # Override URL endpoints with user's input coords (avoid ORS snap drift).
    # For loops, append input_start to close the loop in the path-style URL.
    if preview:
        preview[0] = input_start
        if input_end is not None:
            preview[-1] = input_end
        else:
            preview.append(input_start)
    print(f"Length:  {result.length_m / 1000:.2f} km  (~{est_minutes:.1f} min @ {pace_kmh:.1f} km/h)")
    print(f"Seed:    {seed}")
    print(f"GPX:     {gpx_path}")
    print(f"Google:  {export.google_maps_url(preview)}")
    if not exact:
        print("Note: best-effort, target tolerance not met.")
    if debug_score:
        # The OSM engine reports the exact signals it selected on; ORS falls back
        # to the geometric quality breakdown (no edge-level info available).
        metrics = result.debug
        if metrics is None:
            metrics = route_quality_breakdown(result.polyline)
        for name, value in metrics.items():
            print(f"           {name:<14} {value:9.1f}")
