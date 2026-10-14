#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["tidalapi"]
# ///
"""Get tracks from a Tidal album by ID."""
import json, sys
from pathlib import Path
import tidalapi

SESSION_FILE = Path(__file__).parent.parent / ".tidal-session.json"
session = tidalapi.Session()
session.login_session_file(SESSION_FILE, do_pkce=True)

album_id = int(sys.argv[1])
album = session.album(album_id)
tracks = album.tracks()
out = [{"id": t.id, "name": t.name, "artist": t.artist.name} for t in tracks]
print(json.dumps({"ok": True, "album": album.name, "tracks": out}))
