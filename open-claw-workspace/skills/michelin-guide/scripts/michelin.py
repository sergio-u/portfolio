#!/usr/bin/env python3
"""Live Michelin Guide search/detail/enrichment helper.

This script is intentionally small and domain-specific. It uses Scrapling's HTTP
Fetcher first because ordinary curl/requests can get AWS WAF challenges from
Michelin. It falls back to requests only if Scrapling is unavailable.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:
    from scrapling import Fetcher  # type: ignore
except Exception:  # pragma: no cover - requests fallback is for degraded envs
    Fetcher = None  # type: ignore

BASE_URL = "https://guide.michelin.com"
DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

DISTINCTION_LABELS = {
    "": "Selected",
    "none": "Selected",
    "selected": "Selected",
    "plate": "Selected",
    "the_plate_michelin": "Selected",
    "the-plate-michelin": "Selected",
    "bib": "Bib Gourmand",
    "bib_gourmand": "Bib Gourmand",
    "bib-gourmand": "Bib Gourmand",
    "1": "1 Star",
    "1_star": "1 Star",
    "1-star": "1 Star",
    "1 star": "1 Star",
    "1-stars-michelin": "1 Star",
    "one_star": "1 Star",
    "2": "2 Stars",
    "2_star": "2 Stars",
    "2-stars": "2 Stars",
    "2 star": "2 Stars",
    "2-stars-michelin": "2 Stars",
    "two_stars": "2 Stars",
    "3": "3 Stars",
    "3_star": "3 Stars",
    "3-stars": "3 Stars",
    "3 star": "3 Stars",
    "3-stars-michelin": "3 Stars",
    "three_stars": "3 Stars",
}

PRICE_MAP = {
    "CAT_P01": "$",
    "CAT_P02": "$$",
    "CAT_P03": "$$$",
    "CAT_P04": "$$$$",
    "CAT_P05": "$$$$$",
}


@dataclass
class MichelinRecord:
    name: str | None = None
    michelin_url: str | None = None
    distinction: str | None = None
    stars: int = 0
    bib_gourmand: bool = False
    selected: bool = False
    green_star: bool = False
    cuisine: str | None = None
    price: str | None = None
    address: str | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    country_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    phone: str | None = None
    website: str | None = None
    image_url: str | None = None
    inspector_summary: str | None = None
    accepts_reservations: str | None = None
    chef: str | None = None
    michelin_id: str | None = None
    source_listing_url: str | None = None
    fetched_at: str | None = None
    match_score: float | None = None
    matched_candidate: dict[str, Any] | None = None

    def finalize(self) -> "MichelinRecord":
        label = normalize_distinction(self.distinction)
        self.distinction = label
        self.stars = stars_from_distinction(label)
        self.bib_gourmand = label == "Bib Gourmand"
        self.selected = label == "Selected"
        return self


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def norm_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def normalize_distinction(value: Any) -> str:
    raw = str(value or "").strip()
    key = norm_key(raw)
    if key in DISTINCTION_LABELS:
        return DISTINCTION_LABELS[key]
    if "bib" in key:
        return "Bib Gourmand"
    if "3" in key and "star" in key:
        return "3 Stars"
    if "2" in key and "star" in key:
        return "2 Stars"
    if "1" in key and "star" in key:
        return "1 Star"
    if "green" in key:
        return "Green Star"
    return raw or "Selected"


def stars_from_distinction(label: str | None) -> int:
    if not label:
        return 0
    if label.startswith("3"):
        return 3
    if label.startswith("2"):
        return 2
    if label.startswith("1"):
        return 1
    return 0


def to_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "green_star", "green-star"}


def to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_html(url: str, timeout: int = 45, debug: bool = False) -> str:
    if Fetcher is not None:
        page = Fetcher.get(url, timeout=timeout)
        body = getattr(page, "body", b"")
        html = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
        if debug:
            print(f"fetcher=scrapling url={url} bytes={len(html)}", file=sys.stderr)
        if html.strip():
            return html

    resp = requests.get(url, headers={"User-Agent": DEFAULT_UA, "Referer": "https://www.google.com/"}, timeout=timeout)
    if debug:
        print(f"fetcher=requests url={url} status={resp.status_code} bytes={len(resp.text)}", file=sys.stderr)
    resp.raise_for_status()
    return resp.text


def soup_for(url: str, timeout: int = 45, debug: bool = False) -> BeautifulSoup:
    html = fetch_html(url, timeout=timeout, debug=debug)
    return BeautifulSoup(html, "lxml")


def first_attr(soup_or_tag: Any, selectors: Iterable[str], attrs: Iterable[str]) -> str | None:
    for selector in selectors:
        tag = soup_or_tag.select_one(selector)
        if not tag:
            continue
        for attr in attrs:
            value = tag.get(attr)
            if value not in (None, ""):
                return str(value)
    return None


def attrs_for_card(card: Any) -> dict[str, str]:
    for selector in [".js-favorite-restaurant", ".js-bookmark-restaurant", "[data-restaurant-name]", "[data-dtm-distinction]"]:
        tag = card.select_one(selector)
        if tag:
            return {k: str(v) for k, v in tag.attrs.items()}
    return {}


def parse_price_cuisine(card: Any) -> tuple[str | None, str | None, str | None]:
    scores = [clean_text(x.get_text(" ", strip=True)) for x in card.select(".card__menu-footer--score")]
    scores = [x for x in scores if x]
    location = scores[0] if scores else None
    price = cuisine = None
    if len(scores) >= 2:
        parts = [clean_text(p) for p in re.split(r"\s*·\s*", scores[-1])]
        parts = [p for p in parts if p]
        if parts:
            price = parts[0]
        if len(parts) > 1:
            cuisine = " · ".join(parts[1:])
    return location, price, cuisine


def record_from_card(card: Any, listing_url: str, fetched_at: str) -> MichelinRecord:
    attrs = attrs_for_card(card)
    link = card.select_one("a.link[href]") or card.select_one("a[href*='/restaurant/']")
    href = link.get("href") if link else None
    title = card.select_one(".card__menu-content--title")
    image = card.select_one("a[ci-bg-url]")
    location, price_text, cuisine_text = parse_price_cuisine(card)

    raw_distinction = (
        attrs.get("data-distinction")
        or attrs.get("data-dtm-distinction")
        or card.get("data-map-pin-name")
        or ""
    )
    if attrs.get("data-green-star"):
        green_star = to_bool(attrs.get("data-green-star")) or norm_key(attrs.get("data-green-star")) == "green_star"
    else:
        green_star = False

    price = price_text or PRICE_MAP.get(attrs.get("data-dtm-price", ""), attrs.get("data-dtm-price"))

    rec = MichelinRecord(
        name=clean_text(attrs.get("data-restaurant-name")) or clean_text(link.get_text(" ", strip=True) if link else None) or clean_text(title.get_text(" ", strip=True) if title else None),
        michelin_url=urljoin(BASE_URL, href) if href else None,
        distinction=raw_distinction,
        green_star=green_star,
        cuisine=cuisine_text,
        price=price,
        city=clean_text(attrs.get("data-dtm-city")),
        region=clean_text(attrs.get("data-dtm-region")),
        country=clean_text(attrs.get("data-restaurant-country-label")) or clean_text(location),
        country_code=clean_text(attrs.get("data-restaurant-country")),
        latitude=to_float(card.get("data-lat")),
        longitude=to_float(card.get("data-lng")),
        chef=clean_text(attrs.get("data-dtm-chef")),
        michelin_id=clean_text(attrs.get("data-dtm-id") or attrs.get("data-pid") or card.get("data-id")),
        image_url=clean_text(image.get("ci-bg-url") if image else None),
        source_listing_url=listing_url,
        fetched_at=fetched_at,
    ).finalize()
    return rec


def listing_page_url(base_url: str, page_num: int) -> str:
    if page_num <= 1:
        return base_url
    base = base_url.rstrip("/")
    if re.search(r"/page/\d+$", base):
        return re.sub(r"/page/\d+$", f"/page/{page_num}", base)
    return f"{base}/page/{page_num}"


def parse_listing(url: str, max_pages: int = 1, timeout: int = 45, debug: bool = False) -> list[MichelinRecord]:
    fetched_at = now_iso()
    records: list[MichelinRecord] = []
    seen_urls: set[str] = set()
    for page_num in range(1, max_pages + 1):
        page_url = listing_page_url(url, page_num)
        soup = soup_for(page_url, timeout=timeout, debug=debug)
        cards = soup.select(".card__menu")
        if debug:
            print(f"page={page_num} cards={len(cards)} url={page_url}", file=sys.stderr)
        if page_num > 1 and not cards:
            break
        for card in cards:
            rec = record_from_card(card, page_url, fetched_at)
            key = rec.michelin_url or f"{rec.name}:{rec.latitude}:{rec.longitude}"
            if key in seen_urls:
                continue
            seen_urls.add(key)
            records.append(rec)
    return records


def parse_jsonld(soup: BeautifulSoup) -> dict[str, Any]:
    for script in soup.select('script[type="application/ld+json"]'):
        text = script.string or script.get_text("", strip=True)
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and str(item.get("@type", "")).lower() == "restaurant":
                return item
    return {}


def address_from_jsonld(data: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    addr = data.get("address") if isinstance(data.get("address"), dict) else {}
    street = clean_text(addr.get("streetAddress"))
    city = clean_text(addr.get("addressLocality"))
    region = clean_text(addr.get("addressRegion"))
    country = clean_text(addr.get("addressCountry"))
    parts = [p for p in [street, city, region, clean_text(addr.get("postalCode")), country] if p]
    return (", ".join(parts) if parts else None, city, region, country)


def parse_detail(url: str, timeout: int = 45, debug: bool = False) -> MichelinRecord:
    fetched_at = now_iso()
    soup = soup_for(url, timeout=timeout, debug=debug)
    data = parse_jsonld(soup)
    meta = soup.select_one(".restaurant-details__likeinfo") or soup.select_one(".js-favorite-restaurant")
    attrs = {k: str(v) for k, v in meta.attrs.items()} if meta else {}

    address, city, region, country = address_from_jsonld(data)
    review = data.get("review") if isinstance(data.get("review"), dict) else {}
    geo = data.get("geo") if isinstance(data.get("geo"), dict) else {}

    description = (
        clean_text(soup.select_one(".data-sheet__description").get_text(" ", strip=True))
        if soup.select_one(".data-sheet__description")
        else None
    ) or clean_text(review.get("description"))

    website_tag = soup.select_one('a[data-event="CTA_website"][href]')
    phone_tag = soup.select_one('a[data-event="CTA_tel"][href]')

    raw_distinction = (
        attrs.get("data-distinction")
        or attrs.get("data-dtm-distinction")
        or data.get("award")
        or ""
    )
    if raw_distinction and str(raw_distinction).lower().startswith("selected"):
        raw_distinction = "Selected"

    rec = MichelinRecord(
        name=clean_text(data.get("name")) or clean_text(attrs.get("data-restaurant-name")),
        michelin_url=clean_text(data.get("url")) or url,
        distinction=raw_distinction,
        green_star=to_bool(attrs.get("data-green-star")),
        cuisine=clean_text(data.get("servesCuisine")),
        price=PRICE_MAP.get(attrs.get("data-dtm-price", "")) or clean_text(attrs.get("data-dtm-price")) or clean_text(data.get("priceRange")),
        address=address,
        city=city or clean_text(attrs.get("data-dtm-city")),
        region=region or clean_text(attrs.get("data-dtm-region")),
        country=country or clean_text(attrs.get("data-restaurant-country-label")),
        country_code=clean_text(attrs.get("data-restaurant-country")),
        latitude=to_float(data.get("latitude") or geo.get("latitude")),
        longitude=to_float(data.get("longitude") or geo.get("longitude")),
        phone=clean_text((phone_tag.get("href") or "").replace("tel:", "") if phone_tag else None) or clean_text(data.get("telephone")),
        website=clean_text(website_tag.get("href") if website_tag else None),
        image_url=clean_text(data.get("image")),
        inspector_summary=description,
        accepts_reservations=clean_text(data.get("acceptsReservations")),
        chef=clean_text(attrs.get("data-dtm-chef")),
        michelin_id=clean_text(attrs.get("data-restaurant-id") or attrs.get("data-dtm-id") or attrs.get("data-pid")),
        fetched_at=fetched_at,
    ).finalize()
    return rec


def merge_detail(base: MichelinRecord, detail: MichelinRecord) -> MichelinRecord:
    merged = MichelinRecord(**asdict(base))
    for field, value in asdict(detail).items():
        if field in {"source_listing_url", "match_score", "matched_candidate"}:
            continue
        if value not in (None, "", [], {}):
            setattr(merged, field, value)
    return merged.finalize()


def load_candidates(path: str) -> list[dict[str, Any]]:
    raw = json.loads(Path(path).read_text())
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        for key in ["results", "restaurants", "candidates", "items"]:
            if isinstance(raw.get(key), list):
                return [x for x in raw[key] if isinstance(x, dict)]
    raise SystemExit("Candidate JSON must be an array or an object with results/restaurants/candidates/items array")


def candidate_name(candidate: dict[str, Any]) -> str | None:
    for key in ["name", "title", "restaurant", "place_name"]:
        if candidate.get(key):
            return clean_text(candidate.get(key))
    return None


def match_score(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm_key(a), norm_key(b)).ratio() * 100.0


def enrich(candidates_path: str, listing_url: str, max_pages: int, details: bool, min_score: float, timeout: int, debug: bool) -> list[dict[str, Any]]:
    candidates = load_candidates(candidates_path)
    records = parse_listing(listing_url, max_pages=max_pages, timeout=timeout, debug=debug)
    if details:
        detailed: list[MichelinRecord] = []
        for rec in records:
            if rec.michelin_url:
                try:
                    detailed.append(merge_detail(rec, parse_detail(rec.michelin_url, timeout=timeout, debug=debug)))
                    time.sleep(0.4)
                except Exception as exc:
                    if debug:
                        print(f"detail failed url={rec.michelin_url} error={exc}", file=sys.stderr)
                    detailed.append(rec)
            else:
                detailed.append(rec)
        records = detailed

    enriched: list[dict[str, Any]] = []
    for cand in candidates:
        name = candidate_name(cand)
        best: MichelinRecord | None = None
        best_score = 0.0
        if name:
            for rec in records:
                if not rec.name:
                    continue
                score = match_score(name, rec.name)
                if score > best_score:
                    best_score = score
                    best = rec
        output = dict(cand)
        if best and best_score >= min_score:
            rec_dict = compact_dict(best)
            rec_dict["match_score"] = round(best_score, 1)
            output["michelin"] = rec_dict
        elif best:
            output["michelin_possible_match"] = {
                "name": best.name,
                "michelin_url": best.michelin_url,
                "match_score": round(best_score, 1),
                "threshold": min_score,
            }
        else:
            output["michelin"] = None
        enriched.append(output)
    return enriched


def compact_dict(rec: MichelinRecord) -> dict[str, Any]:
    data = asdict(rec)
    return {k: v for k, v in data.items() if v not in (None, "", [], {})}


def print_records(records: list[MichelinRecord], fmt: str) -> None:
    rows = [compact_dict(r.finalize()) for r in records]
    if fmt == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    elif fmt == "jsonl":
        for row in rows:
            print(json.dumps(row, ensure_ascii=False))
    elif fmt == "csv":
        if not rows:
            return
        fields = sorted({k for row in rows for k in row.keys()})
        writer = csv.DictWriter(sys.stdout, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    else:
        for i, row in enumerate(rows, 1):
            bits = [row.get("distinction"), row.get("cuisine"), row.get("price"), row.get("city") or row.get("region")]
            meta = " · ".join(str(x) for x in bits if x)
            print(f"{i}. {row.get('name') or '(unknown)'}" + (f" — {meta}" if meta else ""))
            if row.get("inspector_summary"):
                print(f"   {row['inspector_summary']}")
            if row.get("michelin_url"):
                print(f"   {row['michelin_url']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live Michelin Guide search/detail/enrichment helper")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--debug", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_search = sub.add_parser("search-url", help="Parse a Michelin listing URL")
    p_search.add_argument("url")
    p_search.add_argument("--max-pages", type=int, default=1)
    p_search.add_argument("--details", action="store_true")
    p_search.add_argument("--format", choices=["json", "jsonl", "csv", "text"], default="text")

    p_detail = sub.add_parser("detail", help="Parse one Michelin restaurant detail URL")
    p_detail.add_argument("url")
    p_detail.add_argument("--format", choices=["json", "jsonl", "csv", "text"], default="text")

    p_enrich = sub.add_parser("enrich", help="Enrich restaurant candidate JSON with Michelin matches")
    p_enrich.add_argument("--candidates", required=True)
    p_enrich.add_argument("--listing-url", required=True)
    p_enrich.add_argument("--max-pages", type=int, default=1)
    p_enrich.add_argument("--details", action="store_true")
    p_enrich.add_argument("--min-score", type=float, default=82.0)
    p_enrich.add_argument("--format", choices=["json", "jsonl"], default="json")

    args = parser.parse_args(argv)

    if args.cmd == "search-url":
        records = parse_listing(args.url, max_pages=args.max_pages, timeout=args.timeout, debug=args.debug)
        if args.details:
            merged: list[MichelinRecord] = []
            for rec in records:
                if rec.michelin_url:
                    try:
                        merged.append(merge_detail(rec, parse_detail(rec.michelin_url, timeout=args.timeout, debug=args.debug)))
                        time.sleep(0.4)
                    except Exception as exc:
                        if args.debug:
                            print(f"detail failed url={rec.michelin_url} error={exc}", file=sys.stderr)
                        merged.append(rec)
                else:
                    merged.append(rec)
            records = merged
        print_records(records, args.format)
        return 0

    if args.cmd == "detail":
        print_records([parse_detail(args.url, timeout=args.timeout, debug=args.debug)], args.format)
        return 0

    if args.cmd == "enrich":
        rows = enrich(args.candidates, args.listing_url, args.max_pages, args.details, args.min_score, args.timeout, args.debug)
        if args.format == "jsonl":
            for row in rows:
                print(json.dumps(row, ensure_ascii=False))
        else:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
