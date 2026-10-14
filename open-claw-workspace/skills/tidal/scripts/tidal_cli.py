#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["tidalapi"]
# ///
"""Tidal CLI — search, top tracks, playlist management via tidalapi."""

import argparse
import json
import sys
from pathlib import Path

import tidalapi

SESSION_FILE = Path(__file__).parent.parent / ".tidal-session.json"


def get_session():
    session = tidalapi.Session()
    if SESSION_FILE.exists():
        session.login_session_file(SESSION_FILE, do_pkce=True)
    if not session.check_login():
        print(json.dumps({"ok": False, "error": "Not logged in. Run 'login' first."}))
        sys.exit(1)
    return session


def cmd_login(args):
    session = tidalapi.Session()
    session.login_session_file(SESSION_FILE, do_pkce=True)
    if session.check_login():
        user_id = session.user.id if session.user else None
        print(json.dumps({"ok": True, "message": "Logged in successfully.", "user_id": user_id}))
    else:
        print(json.dumps({"ok": False, "error": "Login failed."}))


def cmd_search_artist(args):
    session = get_session()
    results = session.search(args.query, models=[tidalapi.artist.Artist], limit=args.limit)
    artists = []
    for a in results.get("artists", []):
        artists.append({"id": a.id, "name": a.name})
    print(json.dumps({"ok": True, "artists": artists}))


def cmd_top_tracks(args):
    session = get_session()
    artist = session.artist(args.artist_id)
    tracks = artist.get_top_tracks(limit=args.limit)
    out = []
    for t in tracks:
        out.append({"id": t.id, "name": t.name, "artist": t.artist.name})
    print(json.dumps({"ok": True, "artist": artist.name, "tracks": out}))


def cmd_create_playlist(args):
    session = get_session()
    playlist = session.user.create_playlist(args.name, args.description or "")
    print(json.dumps({"ok": True, "playlist_id": playlist.id, "name": playlist.name}))


def cmd_add_tracks(args):
    session = get_session()
    playlist = session.playlist(args.playlist_id)
    track_ids = json.loads(args.track_ids)
    # UserPlaylist wrapper needed for modification
    user_playlist = tidalapi.playlist.UserPlaylist(session, playlist.id)
    user_playlist.add(track_ids)
    print(json.dumps({"ok": True, "added": len(track_ids), "playlist_id": args.playlist_id}))


def cmd_list_playlists(args):
    session = get_session()
    playlists = session.user.playlists()
    out = []
    for p in playlists:
        out.append({"id": p.id, "name": p.name, "num_tracks": p.num_tracks})
    print(json.dumps({"ok": True, "playlists": out}))


def main():
    parser = argparse.ArgumentParser(description="Tidal CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="Authenticate with Tidal via PKCE")

    p_search = sub.add_parser("search-artist", help="Search for an artist")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=3)

    p_top = sub.add_parser("top-tracks", help="Get top tracks for an artist")
    p_top.add_argument("artist_id", type=int)
    p_top.add_argument("--limit", type=int, default=5)

    p_create = sub.add_parser("create-playlist", help="Create a new playlist")
    p_create.add_argument("name")
    p_create.add_argument("--description", default="")

    p_add = sub.add_parser("add-tracks", help="Add tracks to a playlist")
    p_add.add_argument("playlist_id")
    p_add.add_argument("track_ids", help="JSON array of track IDs")

    p_list = sub.add_parser("list-playlists", help="List user playlists")

    args = parser.parse_args()

    commands = {
        "login": cmd_login,
        "search-artist": cmd_search_artist,
        "top-tracks": cmd_top_tracks,
        "create-playlist": cmd_create_playlist,
        "add-tracks": cmd_add_tracks,
        "list-playlists": cmd_list_playlists,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
