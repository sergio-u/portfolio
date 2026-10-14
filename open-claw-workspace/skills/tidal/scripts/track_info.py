#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["tidalapi"]
# ///
"""Get track info and artist top tracks from a track ID."""
import json, sys
from pathlib import Path
import tidalapi

SESSION_FILE = Path(__file__).parent.parent / ".tidal-session.json"
session = tidalapi.Session()
session.login_session_file(SESSION_FILE, do_pkce=True)

track_id = int(sys.argv[1])
track = session.track(track_id)
artist = track.artist
print(f"Track: {track.name} by {artist.name} (artist ID: {artist.id})", file=sys.stderr)

tracks = artist.get_top_tracks(limit=5)
out = [{"id": t.id, "name": t.name, "artist": t.artist.name} for t in tracks]
print(json.dumps({"ok": True, "artist": artist.name, "artist_id": artist.id, "tracks": out}))
