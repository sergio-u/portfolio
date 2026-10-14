#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["tidalapi", "spotipy"]
# ///
"""
Build a Coachella 2026 day playlist on Tidal.
Artists sorted by set time, top 3 tracks each.
Falls back to Spotify cross-search for small/missing artists.

Usage:
  uv run build_day_playlist.py --day friday --dry-run
  uv run build_day_playlist.py --day friday --create
"""

import json, sys, os, time, argparse
from pathlib import Path

import tidalapi
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

SKILL_DIR = Path(__file__).parent.parent
TIDAL_DIR = SKILL_DIR.parent / "tidal"
SPOTIFY_DIR = SKILL_DIR.parent / "spotify"
TIDAL_SESSION = TIDAL_DIR / ".tidal-session.json"
SPOTIFY_CREDS = SPOTIFY_DIR / ".spotify-creds.json"

# ─── LINEUPS ───────────────────────────────────────────────
# Format: (time_slot, stage, artist_name)
# Sorted by time within each day

FRIDAY = [
    ("2:00", "Sonora", "Febuary"),
    ("2:00", "Yuma", "Jessica Brankka"),
    ("2:00", "Heineken House", "Sander Kleinenberg"),
    ("1:00", "Yuma", "Sahar Z"),
    ("3:00", "Sonora", "Carolina Durante"),
    ("3:00", "Gobi", "Bob Baker Marionettes"),
    ("3:00", "Yuma", "Arodes"),
    ("4:00", "Coachella Stage", "Blood Orange"),
    ("4:00", "Sonora", "Cachirula & Loojan"),
    ("4:00", "Sahara", "Youna"),
    ("4:00", "Mojave", "CMAT"),
    ("5:00", "Coachella Stage", "Foster the People"),
    ("5:00", "Outdoor Theater", "Dabeull"),
    ("5:00", "Sonora", "The Two Lips"),
    ("5:00", "Gobi", "NewDad"),
    ("5:00", "Sahara", "HUGEL"),
    ("5:00", "Mojave", "Slayyyter"),
    ("5:00", "Yuma", "Chloe Caillet"),
    ("5:00", "Yuma", "Rossi."),
    ("5:00", "Heineken House", "Kryptogram"),
    ("6:00", "Outdoor Theater", "BINI"),
    ("6:00", "Sonora", "Ninajirachi"),
    ("6:00", "Yuma", "Prospa"),
    ("6:00", "Heineken House", "Robin Schulz"),
    ("7:00", "Coachella Stage", "Teddy Swims"),
    ("7:00", "Gobi", "Joyce Manor"),
    ("7:00", "Mojave", "Devo"),
    ("7:00", "Sahara", "Marlon Hoffstadt"),
    ("7:00", "Yuma", "Groove Armada"),
    ("8:00", "Outdoor Theater", "Ethel Cain"),
    ("8:00", "Sonora", "Fleshwater"),
    ("8:00", "Gobi", "Lykke Li"),
    ("8:00", "Mojave", "Holly Humberstone"),
    ("8:00", "Sahara", "Levity"),
    ("8:00", "Heineken House", "Wale"),
    ("9:00", "Coachella Stage", "the xx"),
    ("9:00", "Sonora", "Wednesday"),
    ("9:00", "Gobi", "fakemink"),
    ("9:00", "Mojave", "Moby"),
    ("9:00", "Sahara", "KATSEYE"),
    ("9:00", "Yuma", "Max Dean"),
    ("9:00", "Yuma", "Luke Dean"),
    ("9:00", "Quasar", "PAWSA"),
    ("9:00", "Quasar", "Armin Van Buuren"),
    ("9:00", "Quasar", "Adam Beyer"),
    ("9:00", "Heineken House", "Zerb"),
    ("10:00", "Coachella Stage", "Sabrina Carpenter"),
    ("10:00", "Outdoor Theater", "Turnstile"),
    ("10:00", "Sonora", "Hot Mulligan"),
    ("10:00", "Gobi", "Creepy Nuts"),
    ("10:00", "Yuma", "Max Styler"),
    ("11:00", "Outdoor Theater", "Disclosure"),
    ("11:00", "Sonora", "Not For Radio"),
    ("11:00", "Mojave", "Dijon"),
    ("11:00", "Sahara", "Central Cee"),
    ("11:00", "Yuma", "Gordo"),
    ("12:00", "Coachella Stage", "Anyma"),
    ("12:00", "Gobi", "Joost"),
    ("12:00", "Sahara", "Sexyy Red"),
    ("1:00am", "Yuma", "Kettama"),
]

DAYS = {
    "friday": FRIDAY,
    # saturday and sunday will be added later
}


def get_tidal():
    session = tidalapi.Session()
    if TIDAL_SESSION.exists():
        session.login_session_file(TIDAL_SESSION, do_pkce=True)
    if not session.check_login():
        print("ERROR: Not logged into Tidal.", file=sys.stderr)
        sys.exit(1)
    return session


def get_spotify():
    if SPOTIFY_CREDS.exists():
        creds = json.loads(SPOTIFY_CREDS.read_text())
        os.environ["SPOTIPY_CLIENT_ID"] = creds["client_id"]
        os.environ["SPOTIPY_CLIENT_SECRET"] = creds["client_secret"]
    return spotipy.Spotify(auth_manager=SpotifyClientCredentials())


def tidal_search_artist(session, name, limit=3):
    """Search Tidal for artist, return top track IDs or None."""
    results = session.search(name, models=[tidalapi.artist.Artist], limit=5)
    artists = results.get("artists", [])
    if not artists:
        return None
    artist = artists[0]
    tracks = artist.get_top_tracks(limit=limit)
    if not tracks:
        return None
    return {
        "artist_id": artist.id,
        "artist_name": artist.name,
        "tracks": [{"id": t.id, "name": t.name, "artist": t.artist.name} for t in tracks],
    }


def tidal_search_track(session, track_name, artist_name):
    """Search Tidal for a specific track by name + artist."""
    query = f"{artist_name} {track_name}"
    results = session.search(query, models=[tidalapi.media.Track], limit=5)
    tracks = results.get("tracks", [])
    artist_lower = artist_name.lower()
    for t in tracks:
        if artist_lower in t.artist.name.lower() or t.artist.name.lower() in artist_lower:
            return {"id": t.id, "name": t.name, "artist": t.artist.name}
    if tracks:
        return {"id": tracks[0].id, "name": tracks[0].name, "artist": tracks[0].artist.name}
    return None


def spotify_top_tracks(sp, artist_name, limit=3):
    """Get artist's top track names from Spotify for cross-searching."""
    try:
        results = sp.search(q=f"artist:{artist_name}", type="artist", limit=3)
        artists = results["artists"]["items"]
        if not artists:
            return None
        artist_id = artists[0]["id"]
        sp_name = artists[0]["name"]
        top = sp.artist_top_tracks(artist_id, country="US")
        return {
            "spotify_artist": sp_name,
            "tracks": [(t["name"], sp_name) for t in top["tracks"][:limit]],
        }
    except Exception as e:
        print(f"  Spotify error: {e}", file=sys.stderr)
        return None


def process_lineup(tidal, sp, lineup):
    """Process a full lineup, return list of track IDs and a log."""
    all_track_ids = []
    log = []

    for time_slot, stage, artist_name in lineup:
        entry = {"time": time_slot, "stage": stage, "artist": artist_name}
        print(f"\n{time_slot} | {stage} | {artist_name}", file=sys.stderr)

        # 1. Try Tidal direct
        result = tidal_search_artist(tidal, artist_name, limit=3)
        if result and result["tracks"]:
            ids = [t["id"] for t in result["tracks"]]
            all_track_ids.extend(ids)
            entry.update({"source": "tidal", "matched": result["artist_name"],
                          "tracks": result["tracks"], "count": len(ids)})
            for t in result["tracks"]:
                print(f"  + {t['name']} by {t['artist']}", file=sys.stderr)
            log.append(entry)
            time.sleep(0.2)
            continue

        # 2. Spotify fallback -> cross-search on Tidal
        print(f"  Tidal miss, trying Spotify...", file=sys.stderr)
        sp_result = spotify_top_tracks(sp, artist_name, limit=3)
        if not sp_result:
            print(f"  MISS on both services", file=sys.stderr)
            entry.update({"source": "miss", "matched": None, "tracks": [], "count": 0})
            log.append(entry)
            time.sleep(0.2)
            continue

        found = []
        for track_name, sp_artist in sp_result["tracks"]:
            t = tidal_search_track(tidal, track_name, sp_artist)
            if t:
                found.append(t)
                all_track_ids.append(t["id"])
                print(f"  + {t['name']} by {t['artist']} (via Spotify)", file=sys.stderr)
            else:
                print(f"  x {track_name} by {sp_artist} (not on Tidal)", file=sys.stderr)

        entry.update({
            "source": "spotify_crossref" if found else "miss_crossref",
            "matched": sp_result["spotify_artist"],
            "tracks": found, "count": len(found),
        })
        log.append(entry)
        time.sleep(0.3)

    return all_track_ids, log


def main():
    parser = argparse.ArgumentParser(description="Build Coachella day playlist")
    parser.add_argument("--day", required=True, choices=list(DAYS.keys()))
    parser.add_argument("--create", action="store_true", help="Create playlist on Tidal")
    parser.add_argument("--dry-run", action="store_true", help="Search only, don't create")
    parser.add_argument("--playlist-name", default=None)
    args = parser.parse_args()

    lineup = DAYS[args.day]
    tidal = get_tidal()
    sp = get_spotify()

    track_ids, log = process_lineup(tidal, sp, lineup)

    # Summary
    found = [e for e in log if e["count"] > 0]
    missed = [e for e in log if e["count"] == 0]
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Artists: {len(lineup)} | Found: {len(found)} | Missed: {len(missed)} | Tracks: {len(track_ids)}", file=sys.stderr)
    if missed:
        print("Missed:", file=sys.stderr)
        for m in missed:
            print(f"  - {m['artist']} ({m['time']}, {m['stage']})", file=sys.stderr)

    if args.create and track_ids:
        name = args.playlist_name or f"Coachella 2026 {args.day.title()}"
        playlist = tidal.user.create_playlist(name, f"Coachella 2026 {args.day.title()} - artists in set time order, top 3 tracks each")
        up = tidalapi.playlist.UserPlaylist(tidal, playlist.id)
        # Add in batches of 50
        for i in range(0, len(track_ids), 50):
            up.add(track_ids[i:i+50])
            time.sleep(0.5)
        print(f"\nCreated playlist: {name} ({playlist.id}) with {len(track_ids)} tracks", file=sys.stderr)

    # JSON output
    print(json.dumps({"ok": True, "day": args.day, "track_ids": track_ids,
                       "total_tracks": len(track_ids), "log": log}))


if __name__ == "__main__":
    main()
