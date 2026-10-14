#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["spotipy"]
# ///
"""Spotify CLI - search artists, get top tracks, get artist info."""
import argparse, json, sys, os
from pathlib import Path
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

CREDS_FILE = Path(__file__).parent.parent / ".spotify-creds.json"

def get_client():
    if CREDS_FILE.exists():
        creds = json.loads(CREDS_FILE.read_text())
        os.environ["SPOTIPY_CLIENT_ID"] = creds["client_id"]
        os.environ["SPOTIPY_CLIENT_SECRET"] = creds["client_secret"]
    return spotipy.Spotify(auth_manager=SpotifyClientCredentials())

def cmd_search_artist(args):
    sp = get_client()
    results = sp.search(q=f"artist:{args.query}", type="artist", limit=args.limit)
    artists = [{"id": a["id"], "name": a["name"], "followers": a["followers"]["total"], "genres": a["genres"][:3]}
               for a in results["artists"]["items"]]
    print(json.dumps({"ok": True, "artists": artists}))

def cmd_artist_info(args):
    sp = get_client()
    a = sp.artist(args.artist_id)
    print(json.dumps({"ok": True, "artist": {"id": a["id"], "name": a["name"], "followers": a["followers"]["total"],
                                              "genres": a["genres"], "popularity": a["popularity"]}}))

def cmd_top_tracks(args):
    sp = get_client()
    results = sp.artist_top_tracks(args.artist_id, country=args.market)
    tracks = [{"id": t["id"], "name": t["name"], "artist": t["artists"][0]["name"],
               "artist_id": t["artists"][0]["id"], "album": t["album"]["name"],
               "popularity": t["popularity"]}
              for t in results["tracks"][:args.limit]]
    # Also get artist name
    artist_name = tracks[0]["artist"] if tracks else "Unknown"
    print(json.dumps({"ok": True, "artist": artist_name, "tracks": tracks}))

def cmd_artist_albums(args):
    sp = get_client()
    results = sp.artist_albums(args.artist_id, album_type=args.type, limit=args.limit, country=args.market)
    albums = [{"id": a["id"], "name": a["name"], "release_date": a["release_date"], "total_tracks": a["total_tracks"]}
              for a in results["items"]]
    print(json.dumps({"ok": True, "albums": albums}))

def cmd_album_tracks(args):
    sp = get_client()
    album = sp.album(args.album_id)
    tracks = [{"id": t["id"], "name": t["name"], "artist": t["artists"][0]["name"],
               "artist_id": t["artists"][0]["id"], "track_number": t["track_number"]}
              for t in album["tracks"]["items"]]
    print(json.dumps({"ok": True, "album": album["name"], "artist": album["artists"][0]["name"], "tracks": tracks}))

def main():
    parser = argparse.ArgumentParser(description="Spotify CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("search-artist")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=5)

    p = sub.add_parser("artist-info")
    p.add_argument("artist_id")

    p = sub.add_parser("top-tracks")
    p.add_argument("artist_id")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--market", default="US")

    p = sub.add_parser("artist-albums")
    p.add_argument("artist_id")
    p.add_argument("--type", default="single,album")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--market", default="US")

    p = sub.add_parser("album-tracks")
    p.add_argument("album_id")

    args = parser.parse_args()
    {"search-artist": cmd_search_artist, "artist-info": cmd_artist_info,
     "top-tracks": cmd_top_tracks, "artist-albums": cmd_artist_albums,
     "album-tracks": cmd_album_tracks}[args.cmd](args)

if __name__ == "__main__":
    main()
