#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["fast-flights>=3.1.0", "typing_extensions"]
# ///
"""Search for flights on a specific date using fast-flights (Google Flights)."""

import argparse
import json
import sys

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search for flights on a specific date."
    )
    parser.add_argument("origin", help="Departure airport IATA code (e.g., SEA)")
    parser.add_argument("destination", help="Arrival airport IATA code (e.g., MEX)")
    parser.add_argument("departure_date", help="Departure date (YYYY-MM-DD)")
    parser.add_argument(
        "--return-date", "-r",
        default=None,
        help="Return date for round trip (YYYY-MM-DD)",
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
        "--sort-by", "-o",
        default="CHEAPEST",
        choices=["CHEAPEST", "DURATION", "DEPARTURE_TIME", "ARRIVAL_TIME"],
        help="Sort results by (default: CHEAPEST)",
    )
    parser.add_argument(
        "--time", "-t",
        default=None,
        help="Departure time window in 24h format (e.g., 6-20)",
    )
    parser.add_argument(
        "--arrival-time",
        default=None,
        help="Arrival time window in 24h format (e.g., 18-23)",
    )
    parser.add_argument(
        "--airlines", "-a",
        nargs="*",
        default=None,
        help="Filter by airline IATA codes (e.g., AA DL UA)",
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
        default=10,
        help="Maximum number of results to show (default: 10)",
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


def fmt_time(dt) -> str:
    """SimpleDatetime -> 'HH:MM'."""
    return f"{dt.time[0]:02d}:{dt.time[1]:02d}"


def fmt_date(dt) -> str:
    """SimpleDatetime -> 'YYYY-MM-DD'."""
    return f"{dt.date[0]:04d}-{dt.date[1]:02d}-{dt.date[2]:02d}"


def fmt_duration(minutes: int | None) -> str:
    if not minutes:
        return ""
    return f"{minutes // 60}h {minutes % 60}m"


def sort_key(result, sort_by: str):
    legs = result.flights
    if sort_by == "CHEAPEST":
        return result.price if result.price is not None else float("inf")
    if sort_by == "DURATION":
        return sum(leg.duration or 0 for leg in legs)
    if sort_by == "DEPARTURE_TIME":
        return legs[0].departure.time if legs else (99, 99)
    if sort_by == "ARRIVAL_TIME":
        return legs[-1].arrival.time if legs else (99, 99)
    return 0


def leg_to_dict(leg) -> dict:
    return {
        "from": leg.from_airport.code,
        "from_name": leg.from_airport.name,
        "to": leg.to_airport.code,
        "to_name": leg.to_airport.name,
        "departure_date": fmt_date(leg.departure),
        "departure_time": fmt_time(leg.departure),
        "arrival_date": fmt_date(leg.arrival),
        "arrival_time": fmt_time(leg.arrival),
        "duration": fmt_duration(leg.duration),
        "duration_minutes": leg.duration,
        "plane_type": leg.plane_type,
    }


def result_to_dict(result) -> dict:
    legs = result.flights
    return {
        "price": result.price,
        "airlines": result.airlines,
        "stops": max(len(legs) - 1, 0),
        "total_duration": fmt_duration(sum(leg.duration or 0 for leg in legs)),
        "carbon_kg": (
            round(result.carbon.emission / 1000) if result.carbon and result.carbon.emission else None
        ),
        "legs": [leg_to_dict(leg) for leg in legs],
    }


def format_result(result, idx: int) -> str:
    legs = result.flights
    airlines = ", ".join(result.airlines) if result.airlines else "?"
    stops = max(len(legs) - 1, 0)
    stop_str = "Nonstop" if stops == 0 else f"{stops} stop(s)"
    total = fmt_duration(sum(leg.duration or 0 for leg in legs))

    price = f"${result.price}" if result.price is not None else "$?"
    lines = [f"[{idx}] {price}  {airlines}  [{stop_str}, {total}]"]

    for leg in legs:
        dep = f"{leg.from_airport.code} {fmt_time(leg.departure)}"
        arr = f"{leg.to_airport.code} {fmt_time(leg.arrival)}"
        date = fmt_date(leg.departure)
        extra = f" ({leg.plane_type})" if leg.plane_type else ""
        lines.append(f"     {date}  {dep} -> {arr}  {fmt_duration(leg.duration)}{extra}")

    return "\n".join(lines)


def main() -> None:
    args = parse_args()

    dep_start, dep_end = parse_hour_window(args.time)
    arr_start, arr_end = parse_hour_window(args.arrival_time)
    max_stops = STOPS_MAP[args.max_stops]
    airlines = [a.upper() for a in args.airlines] if args.airlines else None

    legs = [
        FlightQuery(
            date=args.departure_date,
            from_airport=args.origin.upper(),
            to_airport=args.destination.upper(),
            max_stops=max_stops,
            airlines=airlines,
            earliest_departure_hour=dep_start,
            latest_departure_hour=dep_end,
            earliest_arrival_hour=arr_start,
            latest_arrival_hour=arr_end,
        )
    ]

    if args.return_date:
        legs.append(
            FlightQuery(
                date=args.return_date,
                from_airport=args.destination.upper(),
                to_airport=args.origin.upper(),
                max_stops=max_stops,
                airlines=airlines,
            )
        )

    try:
        query = create_query(
            flights=legs,
            trip="round-trip" if args.return_date else "one-way",
            seat=CABIN_MAP[args.cabin_class],
            passengers=Passengers(adults=args.passengers),
            currency=args.currency,
            language="en-US",
            hide_separate_and_self_transfer=args.hide_separate_tickets,
        )
        results = list(get_flights(query))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if not results:
        print("No flights found.", file=sys.stderr)
        sys.exit(1)

    results.sort(key=lambda r: sort_key(r, args.sort_by))
    results = results[: args.max_results]

    if args.json_output:
        print(json.dumps([result_to_dict(r) for r in results], indent=2))
    else:
        for i, result in enumerate(results, 1):
            print(format_result(result, i))
            if i < len(results):
                print()


if __name__ == "__main__":
    main()
