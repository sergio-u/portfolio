#!/usr/bin/env python3
"""
Filter and rank restaurant results from google-maps-scraper.

Usage:
    python3 filter_results.py \
        --input results.json \
        --lat 25.0807 --lon -77.3425 \
        --radius 800 \
        --dietary vegetarian \
        --day Sunday --time 21:00 \
        --cuisine italian \
        --price '$$' \
        --max-results 10
"""

import argparse
import json
import math
import re
import sys


def haversine(lat1, lon1, lat2, lon2):
    """Distance in meters between two lat/lon points."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def parse_close_hour(time_str):
    """Parse a closing time string like '10 PM' into 24h integer hour."""
    s = time_str.upper().replace("\u202f", " ").replace("\u2009", " ").strip()
    if "24" in s or "OPEN 24" in s:
        return 24
    ampm = "PM" if "PM" in s else ("AM" if "AM" in s else None)
    if not ampm:
        return None
    digits = re.sub(r"[^\d:]", "", s)
    if ":" in digits:
        h_str, _ = digits.split(":", 1)
        h = int(h_str)
    elif digits:
        h = int(digits)
    else:
        return None
    if ampm == "PM" and h != 12:
        h += 12
    elif ampm == "AM" and h == 12:
        h = 0
    return h


def check_open_at(open_hours, day, hour):
    """
    Check if open_hours covers a given day and hour.
    Returns True (open), False (closed), or None (unknown).
    """
    if not open_hours or not isinstance(open_hours, dict):
        return None

    day_val = None
    for k, v in open_hours.items():
        if k.lower() == day.lower():
            day_val = v
            break
    if day_val is None:
        return None

    if isinstance(day_val, list):
        for time_range in day_val:
            if not time_range:
                continue
            tr = str(time_range)
            if "closed" in tr.lower():
                return False
            if "24" in tr:
                return True
            parts = re.split(r"[–—]", tr)
            if len(parts) >= 2:
                close_h = parse_close_hour(parts[-1])
                if close_h is not None:
                    # Restaurants closing after midnight (1AM, 2AM) are still open at 9PM
                    return close_h >= hour or close_h <= 4
        return None
    return None


def extract_about_text(about):
    """Flatten the structured 'about' field into searchable text."""
    if not about:
        return ""
    if isinstance(about, str):
        return about
    texts = []
    for section in about:
        if isinstance(section, dict):
            texts.append(section.get("name", "") or "")
            for opt in section.get("options") or []:
                if isinstance(opt, dict) and opt.get("enabled"):
                    texts.append(opt.get("name", "") or "")
    return " ".join(texts)


def extract_about_options(about):
    """Extract enabled option names from the structured 'about' field."""
    options = set()
    if not about or not isinstance(about, list):
        return options
    for section in about:
        if isinstance(section, dict):
            for opt in section.get("options") or []:
                if isinstance(opt, dict) and opt.get("enabled"):
                    options.add((opt.get("name", "") or "").lower())
    return options


def check_dietary(record, dietary):
    """
    Check if a restaurant matches a dietary requirement.
    Returns 'confirmed' (in Google attributes), 'likely' (found in reviews/text), or 'no'.
    """
    if not dietary:
        return "n/a"

    dietary_lower = dietary.lower()
    keywords = {
        "vegetarian": ["vegetarian", "veggie", "meat-free", "meatless"],
        "vegan": ["vegan", "plant-based", "plant based"],
    }
    search_terms = keywords.get(dietary_lower, [dietary_lower])

    # Check structured about data first (most reliable)
    about_options = extract_about_options(record.get("about"))
    for term in search_terms:
        for opt in about_options:
            if term in opt:
                return "confirmed"

    # Check categories
    cats = record.get("categories") or []
    if isinstance(cats, list):
        cat_text = " ".join(c for c in cats if isinstance(c, str)).lower()
        for term in search_terms:
            if term in cat_text:
                return "confirmed"

    # Check reviews and description text
    texts = [
        record.get("description", "") or "",
        extract_about_text(record.get("about")),
    ]
    for rev in record.get("user_reviews") or []:
        if isinstance(rev, dict):
            texts.append(rev.get("Description", "") or rev.get("text", "") or "")
    combined = " ".join(texts).lower()
    for term in search_terms:
        if term in combined:
            return "likely"

    return "no"


def check_cuisine(record, cuisine):
    """Check if a restaurant matches a cuisine type."""
    if not cuisine:
        return True
    cuisine_lower = cuisine.lower()
    texts = [
        record.get("category", "") or "",
        record.get("description", "") or "",
    ]
    cats = record.get("categories") or []
    if isinstance(cats, list):
        texts.extend(c for c in cats if isinstance(c, str))
    combined = " ".join(texts).lower()
    return cuisine_lower in combined


def check_price(record, price):
    """Check if price_range matches."""
    if not price:
        return True
    rp = record.get("price_range", "") or ""
    return rp == price or not rp  # include unknown prices


def get_sunday_hours_display(open_hours, day):
    """Get the hours string for display."""
    if not open_hours or not isinstance(open_hours, dict):
        return "unknown"
    for k, v in open_hours.items():
        if k.lower() == day.lower():
            if isinstance(v, list):
                return ", ".join(str(x) for x in v)
            return str(v)
    return "unknown"


def find_relevant_review(record, dietary):
    """Find a review mentioning dietary needs, or the first review."""
    reviews = record.get("user_reviews") or []
    if dietary:
        keywords = ["vegetarian", "vegan", "veggie", "plant-based", "meat-free", "healthy"]
        for rev in reviews:
            if isinstance(rev, dict):
                text = (rev.get("Description", "") or rev.get("text", "") or "").lower()
                if any(k in text for k in keywords):
                    return rev.get("Description", "") or rev.get("text", "")
    if reviews and isinstance(reviews[0], dict):
        return reviews[0].get("Description", "") or reviews[0].get("text", "")
    return None


def main():
    parser = argparse.ArgumentParser(description="Filter restaurant scraper results")
    parser.add_argument("--input", required=True, help="Path to results.json (newline-delimited)")
    parser.add_argument("--lat", type=float, required=True, help="Center latitude")
    parser.add_argument("--lon", type=float, required=True, help="Center longitude")
    parser.add_argument("--radius", type=int, default=800, help="Max walking distance in meters (default: 800)")
    parser.add_argument("--dietary", choices=["vegetarian", "vegan"], help="Dietary filter")
    parser.add_argument("--day", help="Day of week (e.g. Sunday)")
    parser.add_argument("--time", help="Time in HH:MM 24h format (e.g. 21:00)")
    parser.add_argument("--cuisine", help="Cuisine type (e.g. italian, indian, sushi)")
    parser.add_argument("--price", help="Price range (e.g. $$)")
    parser.add_argument("--max-results", type=int, default=10, help="Max results to show")
    parser.add_argument("--output", help="Output JSON file (optional)")

    args = parser.parse_args()

    # Parse requested hour
    req_hour = None
    if args.time:
        req_hour = int(args.time.split(":")[0])

    # Load and deduplicate
    with open(args.input) as f:
        content = f.read().strip()

    records = []
    seen = set()
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            key = (r.get("title", ""), r.get("address", ""))
            if key not in seen:
                seen.add(key)
                records.append(r)
        except json.JSONDecodeError:
            continue

    print(f"Loaded {len(records)} unique records", file=sys.stderr)

    # Filter and enrich
    results = []
    for r in records:
        lat = r.get("latitude")
        lon = r.get("longtitude")  # Note: typo in scraper field name
        if lat is None or lon is None:
            continue

        # Distance filter
        dist = haversine(args.lat, args.lon, float(lat), float(lon))
        if dist > args.radius:
            continue

        # Cuisine filter
        if not check_cuisine(r, args.cuisine):
            continue

        # Price filter
        if not check_price(r, args.price):
            continue

        # Enrich with computed fields
        open_status = None
        hours_display = "unknown"
        if args.day:
            hours_display = get_sunday_hours_display(r.get("open_hours"), args.day)
            if req_hour is not None:
                open_status = check_open_at(r.get("open_hours"), args.day, req_hour)

        dietary_status = check_dietary(r, args.dietary)
        relevant_review = find_relevant_review(r, args.dietary)

        results.append({
            "title": r.get("title"),
            "category": r.get("category"),
            "categories": r.get("categories"),
            "address": r.get("address"),
            "distance_m": round(dist),
            "review_rating": r.get("review_rating"),
            "review_count": r.get("review_count"),
            "price_range": r.get("price_range") or "unknown",
            "hours_display": hours_display,
            "open_at_requested": open_status,
            "dietary_match": dietary_status,
            "relevant_review": (relevant_review or "")[:250],
            "link": r.get("link"),
            "web_site": r.get("web_site"),
            "menu_link": (r.get("menu") or {}).get("link", ""),
        })

    print(f"After filtering: {len(results)} results", file=sys.stderr)

    # Sort: dietary match > open status > rating
    def sort_key(r):
        dietary_score = {"confirmed": 0, "likely": 1, "no": 2, "n/a": 0}
        open_score = {True: 0, None: 1, False: 2}
        return (
            dietary_score.get(r["dietary_match"], 2),
            open_score.get(r["open_at_requested"], 1),
            -(r.get("review_rating") or 0),
            -(r.get("review_count") or 0),
        )

    results.sort(key=sort_key)
    results = results[: args.max_results]

    # Output
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Wrote {len(results)} results to {args.output}", file=sys.stderr)

    # Always print summary table
    print()
    header = f"{'#':>2}  {'NAME':<34} {'RTG':>4} {'CNT':>5} {'DIST':>5}"
    if args.dietary:
        header += f" {'DIET':>10}"
    if args.day:
        header += f" {'HOURS':>8}"
    header += f" {'PRICE':>6}"
    print(header)
    print("=" * len(header))

    for i, r in enumerate(results, 1):
        name = (r["title"] or "")[:33]
        rating = r.get("review_rating") or "-"
        count = r.get("review_count") or "-"
        dist = f"{r['distance_m']}m"
        line = f"{i:>2}  {name:<34} {str(rating):>4} {str(count):>5} {dist:>5}"
        if args.dietary:
            line += f" {r['dietary_match']:>10}"
        if args.day:
            open_str = {True: "YES", False: "NO", None: "?"}[r["open_at_requested"]]
            line += f" {open_str:>8}"
        line += f" {r['price_range']:>6}"
        print(line)

    # Print details for top results
    print()
    for i, r in enumerate(results[:args.max_results], 1):
        print(f"--- {i}. {r['title']} ---")
        print(f"  Rating: {r.get('review_rating', '?')} ({r.get('review_count', '?')} reviews) | Price: {r['price_range']}")
        print(f"  Address: {r.get('address')} | Distance: {r['distance_m']}m")
        if args.day:
            print(f"  {args.day} hours: {r['hours_display']}")
        if args.dietary:
            print(f"  {args.dietary.capitalize()}: {r['dietary_match']}")
        if r.get("relevant_review"):
            print(f'  Review: "{r["relevant_review"]}"')
        print(f"  Maps: {r.get('link', 'n/a')}")
        print()


if __name__ == "__main__":
    main()
