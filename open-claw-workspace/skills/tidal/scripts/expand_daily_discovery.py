#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["tidalapi"]
# ///
"""Prepend an expanded TIDAL Daily Discovery mix to a monthly playlist.

For each track in the source mix, this adds:
  1. the original Daily Discovery track
  2. the artist's top N tracks, default 3

Default mode prepends new tracks to the monthly playlist for the run date,
creating it in the requested TIDAL playlist folder when it does not exist yet.
Existing track IDs already in the monthly playlist are skipped. Pass --dry-run
to preview the plan without creating or prepending anything.

Examples:
  uv run --script skills/tidal/scripts/expand_daily_discovery.py \
    https://tidal.com/mix/0168b72e5da67d56d312385d8bb715

  uv run --script skills/tidal/scripts/expand_daily_discovery.py \
    https://tidal.com/mix/0168b72e5da67d56d312385d8bb715 --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import tidalapi
from tidalapi.exceptions import ObjectNotFound

from tidal_playlist import (
    add_tracks_to_playlist,
    find_user_playlist_by_name,
    get_playlist_folder,
    get_playlist_track_ids,
    get_session,
)

DEFAULT_FOLDER = "Discover"
DEFAULT_TIMEZONE = "America/Los_Angeles"
DEFAULT_NAME_TEMPLATE = "Daily Discovery Expanded - {month}"
DEFAULT_DESCRIPTION_TEMPLATE = (
    "Monthly Daily Discovery expansion for {month}. Each run prepends tracks from "
    "{mix_title}: original song plus top {top_n} songs from each artist."
)


def parse_mix_id(value: str) -> str:
    """Accept either a raw mix id or a tidal.com/mix/<id> URL."""
    value = value.strip()
    if not value:
        raise ValueError("mix id/url cannot be empty")

    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0].lower() == "mix":
            return parts[1]
        raise ValueError(f"URL does not look like a TIDAL mix URL: {value}")

    return value


def normalize_track_name(name: str) -> str:
    """Normalize names enough to avoid adding obvious duplicate versions."""
    name = re.sub(r"\s*[\(\[].*?[\)\]]", "", name)
    name = re.sub(r"\s*(feat\.?|ft\.?|featuring)\s+.*", "", name, flags=re.IGNORECASE)
    name = re.sub(
        r"\s*-\s*(remaster|live|remix|radio|acoustic|deluxe|bonus|edit|version|instrumental).*",
        "",
        name,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", name).strip().lower()


def track_summary(track: Any, reason: str) -> dict[str, Any]:
    return {
        "id": track.id,
        "name": track.name,
        "artist": track.artist.name,
        "artist_id": track.artist.id,
        "reason": reason,
    }


def unavailable_artist_warning(track: Any, exc: Exception) -> dict[str, Any]:
    return {
        "source_track_id": track.id,
        "source_track": track.name,
        "artist_id": track.artist.id,
        "artist": track.artist.name,
        "error": str(exc),
    }


def build_expanded_track_plan(session: tidalapi.Session, mix_id: str, top_n: int) -> dict[str, Any]:
    mix = session.mix(mix_id)
    original_tracks = [item for item in mix.items() if isinstance(item, tidalapi.media.Track)]

    if not original_tracks:
        raise RuntimeError(f"Mix {mix_id!r} returned no tracks")

    seen_track_ids: set[int] = set()
    planned_track_ids: list[int] = []
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for original in original_tracks:
        row_added: list[dict[str, Any]] = []

        def add_track(track: Any, reason: str) -> bool:
            if track.id in seen_track_ids:
                return False
            seen_track_ids.add(track.id)
            planned_track_ids.append(track.id)
            row_added.append(track_summary(track, reason))
            return True

        add_track(original, "original_daily_discovery")

        warning = None
        try:
            artist = session.artist(original.artist.id)
            # Fetch more than needed because top-track lists often contain remixes,
            # radio edits, live versions, or the original Daily Discovery track.
            top_tracks = artist.get_top_tracks(limit=max(top_n * 6, 20))
        except ObjectNotFound as exc:
            warning = unavailable_artist_warning(original, exc)
            warnings.append(warning)
            top_tracks = []

        local_normalized_names = {normalize_track_name(original.name)}
        top_tracks_added = 0
        for candidate in top_tracks:
            if candidate.id == original.id:
                continue

            normalized_name = normalize_track_name(candidate.name)
            if not normalized_name or normalized_name in local_normalized_names:
                continue

            if add_track(candidate, "artist_top_track"):
                local_normalized_names.add(normalized_name)
                top_tracks_added += 1

            if top_tracks_added >= top_n:
                break

        row = {
            "source_track": track_summary(original, "source"),
            "top_tracks_requested": top_n,
            "top_tracks_added": top_tracks_added,
            "added": row_added,
        }
        if warning:
            row["warning"] = warning
        rows.append(row)

    return {
        "mix": {
            "id": mix_id,
            "title": mix.title,
            "subtitle": getattr(mix, "sub_title", None),
            "original_track_count": len(original_tracks),
        },
        "track_ids": planned_track_ids,
        "rows": rows,
        "warnings": warnings,
    }


def get_playlist_update_plan(
    session: tidalapi.Session,
    playlist_name: str,
    track_ids: list[int],
) -> dict[str, Any]:
    match = find_user_playlist_by_name(session, playlist_name)

    if not match:
        return {
            "playlist_exists": False,
            "playlist_id": None,
            "existing_track_count": 0,
            "duplicate_track_count": 0,
            "prepend_track_count": len(track_ids),
            "final_track_count": len(track_ids),
            "track_ids_to_add": track_ids,
        }

    playlist_id = match.get("uuid") or match.get("id")
    if not playlist_id:
        raise RuntimeError(f"Matched playlist {playlist_name!r} did not include an id/uuid")

    playlist = session.playlist(playlist_id)
    existing_track_ids = set(get_playlist_track_ids(playlist))
    track_ids_to_add = [track_id for track_id in track_ids if track_id not in existing_track_ids]

    return {
        "playlist_exists": True,
        "playlist_id": playlist.id,
        "existing_track_count": playlist.num_tracks,
        "duplicate_track_count": len(track_ids) - len(track_ids_to_add),
        "prepend_track_count": len(track_ids_to_add),
        "final_track_count": playlist.num_tracks + len(track_ids_to_add),
        "track_ids_to_add": track_ids_to_add,
    }


def create_or_prepend_playlist(
    session: tidalapi.Session,
    playlist_name: str,
    description: str,
    track_ids: list[int],
    folder_name: str,
) -> dict[str, Any]:
    update_plan = get_playlist_update_plan(session, playlist_name, track_ids)

    requested_ids = update_plan["track_ids_to_add"]
    if update_plan["playlist_exists"]:
        playlist_id = update_plan["playlist_id"]
        accepted_ids = add_tracks_to_playlist(session, playlist_id, requested_ids, position=0)
        updated = session.playlist(playlist_id)
        result = {
            "id": playlist_id,
            "name": updated.name,
            "description": getattr(updated, "description", None),
            "action": "prepend" if requested_ids else "noop",
            "existing_track_count": update_plan["existing_track_count"],
            "duplicate_track_count": update_plan["duplicate_track_count"],
            "requested_track_count": len(requested_ids),
            "prepended_track_count": len(accepted_ids),
            "num_tracks": updated.num_tracks,
            "folder": None,
        }
        if len(accepted_ids) != len(requested_ids):
            result["warning"] = (
                f"TIDAL accepted {len(accepted_ids)} of {len(requested_ids)} requested tracks."
            )
        return result

    folder = get_playlist_folder(session, folder_name)
    playlist = session.user.create_playlist(playlist_name, description)
    accepted_ids = add_tracks_to_playlist(session, playlist.id, requested_ids, position=0)
    folder.add_items([playlist.id])

    created = session.playlist(playlist.id)
    result = {
        "id": playlist.id,
        "name": playlist.name,
        "description": description,
        "action": "create",
        "existing_track_count": 0,
        "duplicate_track_count": 0,
        "requested_track_count": len(requested_ids),
        "prepended_track_count": len(accepted_ids),
        "num_tracks": created.num_tracks,
        "folder": {"id": folder.id, "name": folder.name},
    }
    if len(accepted_ids) != len(requested_ids):
        result["warning"] = (
            f"TIDAL accepted {len(accepted_ids)} of {len(requested_ids)} requested tracks."
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mix", help="TIDAL mix URL or raw mix id")
    parser.add_argument("--top", type=int, default=3, help="top tracks per artist to add after the original")
    parser.add_argument("--folder", default=DEFAULT_FOLDER, help="TIDAL playlist folder name")
    parser.add_argument("--date", help="run date, YYYY-MM-DD; default is today in --timezone")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE, help="timezone used for the default date/month")
    parser.add_argument("--name-template", default=DEFAULT_NAME_TEMPLATE, help="supports {date} and {month}")
    parser.add_argument(
        "--description-template",
        default=DEFAULT_DESCRIPTION_TEMPLATE,
        help="supports {date}, {month}, {mix_title}, and {top_n}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="preview the playlist plan without creating anything",
    )
    parser.add_argument("--json", action="store_true", help="print full JSON output")
    args = parser.parse_args()

    if args.top < 0:
        parser.error("--top must be >= 0")

    mix_id = parse_mix_id(args.mix)
    date = args.date or datetime.now(ZoneInfo(args.timezone)).date().isoformat()
    month = date[:7]
    playlist_name = args.name_template.format(date=date, month=month)

    session = get_session()
    plan = build_expanded_track_plan(session, mix_id, args.top)
    playlist_update_plan = get_playlist_update_plan(session, playlist_name, plan["track_ids"])
    description = args.description_template.format(
        date=date,
        month=month,
        mix_title=plan["mix"]["title"],
        top_n=args.top,
    )

    result: dict[str, Any] = {
        "ok": True,
        "mode": "dry-run" if args.dry_run else "prepend-monthly",
        "date": date,
        "month": month,
        "playlist_name": playlist_name,
        "folder_name": args.folder,
        "description": description,
        "planned_track_count": len(plan["track_ids"]),
        "playlist_update_plan": {key: value for key, value in playlist_update_plan.items() if key != "track_ids_to_add"},
        "mix": plan["mix"],
        "rows": plan["rows"],
        "warnings": plan["warnings"],
    }

    if not args.dry_run:
        result["playlist"] = create_or_prepend_playlist(
            session=session,
            playlist_name=playlist_name,
            description=description,
            track_ids=plan["track_ids"],
            folder_name=args.folder,
        )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Mode: {result['mode']}")
        print(f"Mix: {plan['mix']['title']} ({plan['mix']['original_track_count']} source tracks)")
        print(f"Playlist: {playlist_name}")
        print(f"Folder: {args.folder}")
        print(f"Planned tracks: {len(plan['track_ids'])}")
        print(f"Existing tracks: {playlist_update_plan['existing_track_count']}")
        print(f"Duplicates skipped: {playlist_update_plan['duplicate_track_count']}")
        print(f"Tracks to prepend: {playlist_update_plan['prepend_track_count']}")
        if args.dry_run:
            print("Dry run only. Re-run without --dry-run to prepend/create the monthly playlist.")
        else:
            playlist = result["playlist"]
            print(f"{playlist['action'].title()}: {playlist['name']} ({playlist['id']})")
            print(f"Prepended tracks: {playlist['prepended_track_count']}")
            if "warning" in playlist:
                print(f"Warning: {playlist['warning']}", file=sys.stderr)
            print(f"Verified tracks: {playlist['num_tracks']}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
