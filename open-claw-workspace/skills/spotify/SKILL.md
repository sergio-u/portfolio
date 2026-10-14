---
name: spotify
user-invocable: false
description: >
  Search and browse the Spotify catalog: find artists, get top tracks, list
  albums, get album tracks, look up artist info. Use when the user asks to search
  songs, find an artist, look up an album, or needs Spotify data for
  cross-referencing with other music services. Triggers on "spotify",
  "search spotify", "search songs", "find artist", "look up album",
  "Spotify search", "spotify top tracks", "album tracks", "artist albums".
---

# Spotify

Search and browse the Spotify catalog via `spotipy` using Client Credentials auth (read-only).

## Execution

All commands return JSON. Run via:

```bash
uv run skills/spotify/scripts/spotify_cli.py <command> [args]
```

### search-artist

```bash
spotify_cli.py search-artist "Blood Orange" --limit 5
```

Returns: `{ok, artists: [{id, name, followers, genres}]}`

### artist-info

```bash
spotify_cli.py artist-info "6LEeAFiJF8OuPx747e1wxR"
```

Returns: `{ok, artist: {id, name, followers, genres, popularity}}`

### top-tracks

```bash
spotify_cli.py top-tracks "6LEeAFiJF8OuPx747e1wxR" --limit 5 --market US
```

Returns: `{ok, artist, tracks: [{id, name, artist, artist_id, album, popularity}]}`

### artist-albums

```bash
spotify_cli.py artist-albums "6LEeAFiJF8OuPx747e1wxR" --type "album,single" --limit 10
```

Returns: `{ok, albums: [{id, name, release_date, total_tracks}]}`

### album-tracks

```bash
spotify_cli.py album-tracks "4yP0hdKOZPNshxUOjY0cZj"
```

Returns: `{ok, album, artist, tracks: [{id, name, artist, artist_id, track_number}]}`

### Usage Examples

```bash
# Find an artist and get their top tracks
uv run skills/spotify/scripts/spotify_cli.py search-artist "Radiohead" --limit 1
uv run skills/spotify/scripts/spotify_cli.py top-tracks "<artist-id>" --limit 10

# Get all albums by an artist
uv run skills/spotify/scripts/spotify_cli.py artist-albums "<artist-id>" --type "album" --limit 20

# Cross-reference workflow: Spotify top tracks -> Tidal search
uv run skills/spotify/scripts/spotify_cli.py top-tracks "<artist-id>" --limit 5
# Then search Tidal by "artist + song name" for each track
```

## Reference

- Client Credentials auth is read-only: search, artist info, tracks, albums. No playlist management.
- For small/indie artists, Spotify top tracks are more reliable than Tidal's (larger catalog, fewer name collisions).
- The `--market` flag defaults to `US`. Change for region-specific availability.
- Cross-referencing workflow: get Spotify top tracks, then search Tidal by "artist + song name" to find correct matches.

## Conventions

- Present results as readable summaries -- don't dump raw JSON at the user.
- Confirm with the user before bulk operations or actions that modify external state.
- Use `--limit` to keep result sets manageable; default to 5-10 results unless the user asks for more.
- Use JSON output for programmatic parsing and cross-referencing with other services.

## Authentication

Stored in `skills/spotify/.spotify-creds.json`:

```json
{"client_id": "<your-client-id>", "client_secret": "<your-client-secret>"}
```

Get credentials at https://developer.spotify.com/dashboard. If missing, ask the user.

## Requirements

- `uv` package manager.
- `spotipy` Python library (managed via `uv`).
- Spotify API credentials in `skills/spotify/.spotify-creds.json`.

## Troubleshooting

### Token expiry
Client Credentials tokens expire after 1 hour. The `spotipy` library handles automatic refresh, but if you see 401 errors, verify credentials in `.spotify-creds.json` are still valid.

### Rate limits
Spotify enforces rate limits (429 responses). If hit, wait and retry. For bulk operations, add brief delays between requests.

### Scope limitations
Client Credentials auth is read-only catalog access. It cannot manage playlists, control playback, or access user library data. If the user needs those features, a different auth flow (Authorization Code) would be required.
