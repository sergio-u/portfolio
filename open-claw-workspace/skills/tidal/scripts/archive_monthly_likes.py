#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["tidalapi"]
# ///
"""Archive monthly liked tracks into a yearly playlist under a Likes folder."""

import argparse
import calendar
import json
import sys
import time
from datetime import datetime, timezone

from tidal_playlist import (
    add_tracks_to_playlist,
    find_user_playlist_by_name,
    get_playlist_folder,
    get_playlist_track_ids,
    get_session,
)


def fetch_monthly_likes(session, year, month):
    """Fetch all tracks liked during the given month via the raw Tidal API."""
    month_start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        month_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        month_end = datetime(year, month + 1, 1, tzinfo=timezone.utc)

    tracks = []
    offset = 0
    limit = 100

    while True:
        params = {
            "limit": limit,
            "offset": offset,
            "order": "DATE",
            "orderDirection": "DESC",
        }
        resp = session.request.request(
            "GET", f"users/{session.user.id}/favorites/tracks", params=params
        )
        items = resp.json().get("items", [])
        if not items:
            break

        for item in items:
            created_str = item.get("created", "")
            try:
                created = datetime.fromisoformat(created_str.replace("+0000", "+00:00"))
            except ValueError:
                continue

            if created >= month_end:
                continue
            if created < month_start:
                return tracks  # past our window, done

            track_data = item.get("item", {})
            artist_name = track_data.get("artist", {}).get("name", "Unknown")
            tracks.append({
                "id": track_data.get("id"),
                "title": track_data.get("title", ""),
                "artist": artist_name,
                "created": created.isoformat(),
            })

        offset += limit
        time.sleep(0.3)

    return tracks


def find_or_create_playlist(session, name, description, dry_run=False):
    """Find an existing playlist by name, or create a new one."""
    match = find_user_playlist_by_name(session, name)
    if match:
        playlist_id = match.get("uuid") or match.get("id")
        if not playlist_id:
            raise RuntimeError(f"Matched playlist {name!r} did not include an id/uuid")
        playlist = session.playlist(playlist_id)
        print(f"Found existing playlist: {name} ({playlist.id})", file=sys.stderr)
        return playlist

    if dry_run:
        print(f"Would create playlist: {name}", file=sys.stderr)
        return None

    print(f"Creating playlist: {name}", file=sys.stderr)
    return session.user.create_playlist(name, description)


def ensure_folder_structure(session, playlist_id, dry_run=False):
    """Place playlist into the Liked Songs folder. Best-effort."""
    folder_name = "Liked Songs"
    try:
        try:
            target_folder = get_playlist_folder(session, folder_name)
        except RuntimeError:
            if dry_run:
                print(f"Would create '{folder_name}' folder", file=sys.stderr)
                return f"{folder_name} (would create)"
            target_folder = get_playlist_folder(session, folder_name, create=True)
            print(f"Created '{folder_name}' folder", file=sys.stderr)

        if not dry_run:
            target_folder.add_items([playlist_id])
            print(f"Moved playlist into {folder_name} folder", file=sys.stderr)
        return folder_name
    except Exception as exc:
        print(f"Warning: folder organization failed: {exc}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="Archive monthly liked tracks into a playlist.")
    parser.add_argument(
        "--month",
        default=None,
        help="Target month as YYYY-MM (default: current month)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without making changes",
    )
    args = parser.parse_args()

    # Parse month (defaults to previous month, since this runs on the 1st)
    if args.month:
        try:
            dt = datetime.strptime(args.month, "%Y-%m")
            year, month = dt.year, dt.month
        except ValueError:
            print(json.dumps({"ok": False, "error": "Invalid --month format. Use YYYY-MM."}))
            sys.exit(1)
    else:
        now = datetime.now(timezone.utc)
        if now.month == 1:
            year, month = now.year - 1, 12
        else:
            year, month = now.year, now.month - 1

    month_name = calendar.month_name[month]
    playlist_name = f"Liked {year}"

    print(f"Archiving likes for {month_name} {year} into '{playlist_name}'...", file=sys.stderr)

    try:
        session = get_session()
    except RuntimeError:
        print(json.dumps({"ok": False, "error": "Not logged in. Run tidal_cli.py login first."}))
        return 1

    # Fetch liked tracks for the month
    tracks = fetch_monthly_likes(session, year, month)
    print(f"Found {len(tracks)} liked tracks for {month_name} {year}", file=sys.stderr)

    if not tracks:
        print(json.dumps({
            "ok": True,
            "month": f"{year}-{month:02d}",
            "playlist_name": playlist_name,
            "tracks_found": 0,
            "tracks_added": 0,
            "tracks_skipped": 0,
            "dry_run": args.dry_run,
        }, indent=2))
        return 0

    # Find or create yearly playlist
    description = f"Liked tracks from {year}"
    playlist = find_or_create_playlist(session, playlist_name, description, dry_run=args.dry_run)

    track_ids = [track["id"] for track in tracks if track["id"] is not None]
    existing_ids = set(get_playlist_track_ids(playlist)) if playlist else set()
    new_ids = [track_id for track_id in track_ids if track_id not in existing_ids]
    duplicates = len(track_ids) - len(new_ids)

    if args.dry_run:
        print("\nTracks that would be archived:", file=sys.stderr)
        for track in tracks:
            print(
                f"  {track['artist']} - {track['title']} (liked {track['created'][:10]})",
                file=sys.stderr,
            )
        print(f"Would add {len(new_ids)} tracks ({duplicates} already present)", file=sys.stderr)
        accepted_ids = new_ids
        folder_path = ensure_folder_structure(session, None, dry_run=True)
    else:
        if not new_ids:
            print("All tracks already in playlist, nothing to add.", file=sys.stderr)
        else:
            print(f"Adding {len(new_ids)} tracks ({duplicates} already present)...", file=sys.stderr)
        accepted_ids = add_tracks_to_playlist(session, playlist.id, new_ids)
        folder_path = ensure_folder_structure(session, playlist.id)

    rejected = len(new_ids) - len(accepted_ids)
    if rejected:
        print(
            f"Warning: TIDAL accepted {len(accepted_ids)} of {len(new_ids)} requested tracks.",
            file=sys.stderr,
        )

    result = {
        "ok": True,
        "month": f"{year}-{month:02d}",
        "playlist_name": playlist_name,
        "playlist_id": getattr(playlist, "id", None),
        "tracks_found": len(tracks),
        "tracks_added": len(accepted_ids),
        "tracks_skipped": duplicates,
        "tracks_rejected": rejected,
        "folder": folder_path,
        "dry_run": args.dry_run,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
