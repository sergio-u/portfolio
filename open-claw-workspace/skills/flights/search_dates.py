#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["fast-flights>=3.1.0", "typing_extensions"]
# ///
"""Find the cheapest dates to fly between two airports using fast-flights.

fast-flights has no native date-range endpoint, so this script sweeps the
requested range one date at a time (in parallel) and reports the best price
found for each candidate date or date pair.
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from fast_flights import FlightQuery, Passengers, create_query, get_flights

CABIN_MAP = {
    "ECONOMY": "economy",
    "PREMIUM_ECONOMY": "premium-economy",
    "BUSINESS": "business",
    "FIRST": "first",
}

STOPS_MAP = {
    "ANY": None,
    "NON_STOP": 0,
    "ONE_STOP": 1,
    "TWO_PLUS_STOPS": 2,
}

DAY_MAP = {
    "mon": 0, "monday": 0,
    "tue": 1, "tuesday": 1,
    "wed": 2, "wednesday": 2,
    "thu": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find the cheapest dates to fly between two airports."
    )
    parser.add_argument("origin", help="Departure airport IATA code (e.g., SEA)")
    parser.add_argument("destination", help="Arrival airport IATA code (e.g., MEX)")
    parser.add_argument(
        "--from-date", "-f",
        required=True,
        help="Start of date range (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--to-date", "-t",
        required=True,
        help="End of date range (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--duration", "-d",
        type=int,
        default=7,
        help="Trip duration in days for round trips (default: 7)",
    )
    parser.add_argument(
        "--round-trip", "-R",
        action="store_true",
        help="Search for round-trip flights",
    )
    parser.add_argument(
        "--return-from",
        default=None,
        help="Start of return date range (YYYY-MM-DD). Overrides --duration.",
    )
    parser.add_argument(
        "--return-to",
        default=None,
        help="End of return date range (YYYY-MM-DD). Overrides --duration.",
    )
    parser.add_argument(
        "--cabin-class", "-c",
        default="ECONOMY",
        choices=list(CABIN_MAP),
        help="Cabin class (default: ECONOMY)",
    )
    parser.add_argument(
        "--max-stops", "-s",
        default="ANY",
        choices=list(STOPS_MAP),
        help="Max stops (default: ANY)",
    )
    parser.add_argument(
        "--airlines", "-a",
        nargs="*",
        default=None,
        help="Filter by airline IATA codes (e.g., AA DL UA)",
    )
    parser.add_argument(
        "--time",
        default=None,
        help="Outbound departure time window in 24h format (e.g., 6-20)",
    )
    parser.add_argument(
        "--return-time",
        default=None,
        help="Return departure time window in 24h format (e.g., 17-23)",
    )
    parser.add_argument(
        "--sort-by-price",
        action="store_true",
        help="Sort results by price (lowest first)",
    )
    parser.add_argument(
        "--days",
        nargs="*",
        default=None,
        help="Filter departure by day of week (e.g., mon fri)",
    )
    parser.add_argument(
        "--return-days",
        nargs="*",
        default=None,
        help="Filter return by day of week (e.g., sat sun)",
    )
    parser.add_argument(
        "--passengers", "-p",
        type=int,
        default=1,
        help="Number of adult passengers (default: 1)",
    )
    parser.add_argument(
        "--max-results", "-n",
        type=int,
        default=20,
        help="Maximum number of results to show (default: 20)",
    )
    parser.add_argument(
        "--currency",
        default="USD",
        help="Currency code (default: USD)",
    )
    parser.add_argument(
        "--hide-separate-tickets",
        action="store_true",
        help="Hide separate-ticket and self-transfer itineraries",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Parallel requests (default: 4). Keep low to avoid rate limiting.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output raw JSON instead of formatted text",
    )
    return parser.parse_args()


def parse_hour_window(value: str | None) -> tuple[int | None, int | None]:
    if not value:
        return None, None
    try:
        start, end = value.split("-")
        return int(start), int(end)
    except ValueError:
        raise SystemExit(f"Invalid time window '{value}'. Use a format like 6-20.")


def parse_day_filter(values: list[str] | None) -> set[int] | None:
    if not values:
        return None
    days = set()
    for value in values:
        key = value.lower()
        if key in DAY_MAP:
            days.add(DAY_MAP[key])
        else:
            print(f"Warning: unknown day '{value}', ignoring", file=sys.stderr)
    return days or None


def date_range(start: str, end: str) -> list[date]:
    d0 = datetime.strptime(start, "%Y-%m-%d").date()
    d1 = datetime.strptime(end, "%Y-%m-%d").date()
    if d1 < d0:
        raise SystemExit("--to-date must not be earlier than --from-date.")
    return [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]


def fmt_duration(minutes: int | None) -> str:
    if not minutes:
        return ""
    return f"{minutes // 60}h {minutes % 60}m"


def fmt_time(dt) -> str:
    return f"{dt.time[0]:02d}:{dt.time[1]:02d}"


def build_pairs(args) -> list[tuple[date, date | None]]:
    out_days = parse_day_filter(args.days)
    ret_days = parse_day_filter(args.return_days)

    departures = [d for d in date_range(args.from_date, args.to_date)
                  if out_days is None or d.weekday() in out_days]

    is_round_trip = args.round_trip or args.return_from or args.return_to
    if not is_round_trip:
        return [(d, None) for d in departures]

    pairs: list[tuple[date, date | None]] = []
    if args.return_from or args.return_to:
        ret_start = args.return_from or args.to_date
        ret_end = args.return_to or args.return_from or args.to_date
        returns = [d for d in date_range(ret_start, ret_end)
                   if ret_days is None or d.weekday() in ret_days]
        for dep in departures:
            for ret in returns:
                if ret > dep:
                    pairs.append((dep, ret))
    else:
        for dep in departures:
            ret = dep + timedelta(days=args.duration)
            if ret_days is not None and ret.weekday() not in ret_days:
                continue
            pairs.append((dep, ret))
    return pairs


def search_pair(args, dep: date, ret: date | None):
    dep_start, dep_end = parse_hour_window(args.time)
    ret_start, ret_end = parse_hour_window(args.return_time)
    max_stops = STOPS_MAP[args.max_stops]
    airlines = [a.upper() for a in args.airlines] if args.airlines else None

    legs = [
        FlightQuery(
            date=dep.isoformat(),
            from_airport=args.origin.upper(),
            to_airport=args.destination.upper(),
            max_stops=max_stops,
            airlines=airlines,
            earliest_departure_hour=dep_start,
            latest_departure_hour=dep_end,
        )
    ]
    if ret is not None:
        legs.append(
            FlightQuery(
                date=ret.isoformat(),
                from_airport=args.destination.upper(),
                to_airport=args.origin.upper(),
                max_stops=max_stops,
                airlines=airlines,
                earliest_departure_hour=ret_start,
                latest_departure_hour=ret_end,
            )
        )

    try:
        query = create_query(
            flights=legs,
            trip="round-trip" if ret is not None else "one-way",
            seat=CABIN_MAP[args.cabin_class],
            passengers=Passengers(adults=args.passengers),
            currency=args.currency,
            language="en-US",
            hide_separate_and_self_transfer=args.hide_separate_tickets,
        )
        results = [r for r in get_flights(query) if r.price is not None]
    except Exception as exc:
        return {"departure": dep.isoformat(),
                "return": ret.isoformat() if ret else None,
                "error": str(exc)}

    if not results:
        return None

    best = min(results, key=lambda r: r.price)
    first = best.flights[0] if best.flights else None
    return {
        "departure": dep.isoformat(),
        "return": ret.isoformat() if ret else None,
        "price": best.price,
        "airlines": best.airlines,
        "stops": max(len(best.flights) - 1, 0),
        "total_duration": fmt_duration(sum(l.duration or 0 for l in best.flights)),
        "first_departure_time": fmt_time(first.departure) if first else None,
        "options": len(results),
    }


def main() -> None:
    args = parse_args()
    pairs = build_pairs(args)

    if not pairs:
        print("No candidate dates matched the given filters.", file=sys.stderr)
        sys.exit(1)

    workers = max(1, args.workers)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        raw = list(pool.map(lambda p: search_pair(args, p[0], p[1]), pairs))

    errors = [r for r in raw if r and "error" in r]
    results = [r for r in raw if r and "error" not in r]

    for err in errors:
        label = err["departure"] + (f" -> {err['return']}" if err["return"] else "")
        print(f"Warning: {label}: {err['error']}", file=sys.stderr)

    if not results:
        print("No flights found for these dates.", file=sys.stderr)
        sys.exit(1)

    if args.sort_by_price:
        results.sort(key=lambda r: r["price"])
    else:
        results.sort(key=lambda r: (r["departure"], r["return"] or ""))

    results = results[: args.max_results]

    if args.json_output:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            airlines = ", ".join(r["airlines"]) if r["airlines"] else "?"
            stop_str = "Nonstop" if r["stops"] == 0 else f"{r['stops']} stop(s)"
            when = r["departure"]
            if r["return"]:
                when = f"{r['departure']} -> {r['return']}"
            dep_time = f" dep {r['first_departure_time']}" if r["first_departure_time"] else ""
            print(f"  {when}  ${r['price']:<5} {airlines}  [{stop_str}, {r['total_duration']}]{dep_time}")


if __name__ == "__main__":
    main()
