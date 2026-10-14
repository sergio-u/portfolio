---
name: tidal
user-invocable: false
description: >
  Manage Tidal music library: search artists, get top tracks, get album tracks,
  create and modify playlists, list playlists, look up track info.
  Use when the user asks to search Tidal, build a playlist, find top songs for
  an artist, add tracks, deduplicate a playlist, or manage their Tidal library.
  Triggers on "tidal", "add to playlist", "find on tidal", "top tracks",
  "create playlist", "search tidal", "tidal playlist", "add songs to tidal",
  "manage tidal playlist", "tidal favorites", "music library".
---

# Tidal

Manage Tidal via `tidalapi` through self-contained `uv run --script` CLI scripts.

## Execution

All commands return JSON. Run via:

```bash
uv run skills/tidal/scripts/tidal_cli.py <command> [args]
```

### search-artist

```bash
tidal_cli.py search-artist "Blood Orange" --limit 3
```

### top-tracks

```bash
tidal_cli.py top-tracks <artist_id> --limit 5
```

### create-playlist

```bash
tidal_cli.py create-playlist "My Playlist" --description "Description here"
```

### add-tracks

```bash
tidal_cli.py add-tracks <playlist_id> '[111, 222, 333]'
```

### list-playlists

```bash
tidal_cli.py list-playlists
```

## Standalone Utility Scripts

These are simpler scripts (not part of `tidal_cli.py`) that take positional args:

```bash
uv run skills/tidal/scripts/<script>.py <args>
```

- **`album_tracks.py <album_id>`** - list all tracks on an album (returns JSON)
- **`track_info.py <track_id>`** - get track details plus artist top tracks
- **`archive_monthly_likes.py [--month YYYY-MM] [--dry-run]`** - archive monthly likes into yearly playlists
- **`kexp_setlist_sync.py <program> [--episodes N | --episode DATE] [--artist-fallback] [--episode-duplicates] [--write]`** - preview or sync KEXP setlists

`tidal_playlist.py` is the shared module for session loading, exact-name playlist lookup, complete paginated track reads, ordered batched writes, and playlist folder lookup. KEXP sync deduplicates equivalent catalog entries by track id or ISRC. Reuse it instead of copying those operations into scripts.

## Typical Workflow

1. Search for artist: `search-artist "Artist Name"` → get artist ID
2. Get top tracks: `top-tracks <artist_id> --limit 10`
3. Create playlist: `create-playlist "Name"`
4. Add tracks: `add-tracks <playlist_id> '[id1, id2, ...]'`

To build a playlist from multiple artists, collect track IDs from step 2 for each, then add them all in a single `add-tracks` call.

## Festival / Lineup Playlist Workflow

> **Note:** This section covers a seasonal/one-off workflow. It could be moved to `references/` in the future to keep this file focused on core operations.

Build discovery playlists from a festival lineup (schedule image, setlist, or artist list). Write a one-off inline Python script using `tidalapi` directly for bulk operations — the CLI is too slow for 50+ artists.

### When you have the full schedule (stages + times)

1. Extract artists from the schedule image, ordered chronologically by start time (within the same time slot, order by stage priority: main stage first)
2. Skip non-music acts (cultural performances, art installations, puppet shows, SURPRISE slots)
3. For collaborative/b2b acts (e.g. "Rossi. x Chloé Caillet"), split into separate artist entries with 3 tracks each
4. If a reference playlist exists, fetch it first and build a name→ID mapping to use verified IDs
5. For each artist: use verified ID if available, otherwise strict exact-match search only
6. Get top 3 tracks per artist with deduplication (no two versions of the same song)
7. Clear existing playlist (or create new), add tracks in schedule order using batch size 40
8. Review output: check not-found list, verify no mismatches

### When you only have a setlist (artist names, no times)

1. Add artists in the order given (or alphabetical if unordered)
2. Same search → top tracks → create → add flow (strict matching, dedup)
3. User can reorder later once the schedule drops — use the full rebuild approach to reorder

### Artist search pitfalls

**Ambiguous names are the #1 source of errors.** Common traps:

- Short/common names match wrong artists: "SOSA" → Soda Stereo, "Rossi." → Rick Ross, "Youna" → Young Thug, "GENESI" → Genesis, "ROZ" → Rozalén
- Generic words match worship/church music: "Worship" → Elevation Worship, "Gabe Real" → Christian artist
- Niche DJ/Do LaB acts often match wrong artists: "Fifi" → FIFA Sound, "MASSIO" → Mansionair, "Doom Dave" → Dave Doobinin, "Novasoul" → nova.sol
- Misspellings compound the problem: "Redke" → Blonde Redhead
- Some major artists are simply **not on Tidal**: e.g. Labrinth (only karaoke/cover versions exist)

**Mitigations:**

- **Use strict exact-match only** — compare `artist.name` case-insensitively against the search query. If they don't match, **do not use the result**. Never fall back to the first search result. Wrong tracks are worse than missing tracks.
- **Use a reference playlist** if one exists (e.g. a curated festival playlist) to get verified artist IDs — cross-reference by name and use IDs directly. This eliminates search ambiguity entirely.
- **Try appending context** to harder searches: "SOSA UK", "Youna KR", "ROZ DJ" — but only accept exact matches on the resulting name
- **For collaborative acts** like "Chloe Caillet x Rossi." or "Armin van Buuren x Adam Beyer", search each artist separately and add 3 tracks from each
- **Niche/Do LaB/small-stage acts** are frequently not on Tidal at all — accept not-found and skip rather than matching wrong artists

### Featured artist display

`artist.get_top_tracks()` returns tracks where the artist **appears** (primary or featured). The track's `track.artist` field shows the **primary** artist, which may be someone else. Example: Hamdi's top track may show "Skrillex" as primary because Hamdi is featured on it. **This is expected** — the tracks are correct, just displayed under the collab partner's name.

### Track deduplication

`artist.get_top_tracks()` can return multiple versions of the same song (original, remix, remaster, radio edit, etc.). When picking top N tracks per artist, **deduplicate by normalized song name** — strip parentheticals `(...)`, brackets `[...]`, `feat.`/`ft.` suffixes, and ` - Remastered`/`Live`/`Remix` tags, then compare base names. Fetch `limit * 3` candidates and filter down to `limit` unique songs.

```python
def normalize_track_name(name):
    name = re.sub(r'\s*[\(\[].*?[\)\]]', '', name)
    name = re.sub(r'\s*(feat\.?|ft\.?|featuring)\s+.*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*-\s*(remaster|live|remix|radio|acoustic|deluxe|bonus|edit|version|instrumental).*', '', name, flags=re.IGNORECASE)
    return name.strip().lower()
```

### Batch add and ETag errors

Any mutation (`add`, `clear`, `remove_by_indices`) can trigger **412 Precondition Failed** errors due to stale ETags. Fix: **re-instantiate `UserPlaylist`** before each mutation and add a delay between operations. Use batch size of 40 for adds, 2s delay after `clear()`, 1s between batches.

```python
# Clear requires a fresh object
up = tidalapi.playlist.UserPlaylist(session, playlist_id)
up.clear()
time.sleep(2)

# Each batch also needs a fresh object
for start in range(0, len(track_ids), 40):
    batch = track_ids[start:start + 40]
    up = tidalapi.playlist.UserPlaylist(session, playlist_id)
    up.add(batch)
    time.sleep(1)
```

**Important:** if `clear()` succeeds but the subsequent re-add fails, the playlist will be empty. The clear + re-add approach is atomic in intent but not in execution — if interrupted, you must re-run the full rebuild.

### Playlist folders

The CLI doesn't expose folders, but `tidalapi` supports them:

```python
# List folders
folders = session.user.favorites.playlist_folders()

# Move playlist into a folder
folder.add_items([playlist_id])
```

### Full rebuild (reorder)

To fix ordering or update a playlist with new artists, use `UserPlaylist.clear()` then re-add all tracks in the correct order. This is cleaner than incremental `move_by_index` operations. Clearing a playlist **does not affect likes/favorites** — those are separate. Always re-instantiate `UserPlaylist` before `clear()` to get a fresh ETag.

### Removing specific tracks

To remove a few wrong tracks without a full rebuild, use `remove_by_indices` with the track positions:

```python
up = tidalapi.playlist.UserPlaylist(session, playlist_id)
up.remove_by_indices([0, 3, 7])  # remove tracks at these positions
```

Re-instantiate `UserPlaylist` before calling to avoid ETag errors.

### Daily Discovery expansion

`skills/tidal/scripts/expand_daily_discovery.py <mix-url-or-id>` prepends an expanded TIDAL Daily Discovery mix to a monthly playlist named `Daily Discovery Expanded - YYYY-MM` by adding each source track plus the artist's top tracks. It creates the monthly playlist in the `Discover` folder if missing, skips track IDs already in the playlist on later runs, and inserts each new run at the top while preserving that run's track order. Use `--dry-run` to preview. Supported options are documented by `--help`; removed legacy flags are not accepted.

### KEXP setlist sync

`skills/tidal/scripts/kexp_setlist_sync.py <program>` previews the latest airing by default. Programs accept a numeric id or case-insensitive name. Use `--episodes N` for a newest-to-oldest backfill, `--episode YYYY-MM-DD` for one airing, and `--list-programs` to discover ids. Matching first resolves cached KEXP recording IDs through MusicBrainz ISRCs, then combines full-credit, title-first, and album-title searches. Fallback scoring normalizes capitalization, whitespace, quotes, accents, punctuation, and Unicode scripts, then uses KEXP album/version metadata as positive evidence rather than a requirement. Guarded collaboration connectors and only one-sided fuzzy title or artist matching remain. Exact live/remix versions are preferred; when unavailable, studio/base tracks are allowed. When multiple candidates independently clear all current confidence gates, Tidal search rank selects one. `--artist-fallback` substitutes one top track per confidently resolved artist only when no song candidate clears those gates and logs substitutions separately. `--episode-duplicates` preserves repeats across weekly episodes and uses ignored local episode state to keep reruns idempotent; backfills retain global ID/ISRC deduplication. The script writes only with explicit `--write`.

```bash
uv run --script skills/tidal/scripts/kexp_setlist_sync.py "El Sonido" --artist-fallback --episode-duplicates
uv run --script skills/tidal/scripts/kexp_setlist_sync.py "El Sonido" --artist-fallback --episode-duplicates --write
```

See `references/kexp-setlist-sync.md` for authentication, weekly use, backfills, expected output, and KEXP API behavior.

### One-off scripts

Festival playlist scripts go in `skills/tidal/scripts/one-off/` (personal lineup scripts are not included here). They use inline `tidalapi` directly with the shared session file. Each script:

- Has a hardcoded artist list with verified Tidal IDs from a reference playlist where available
- Falls back to strict exact-match search for unknown artists (never accepts fuzzy matches)
- Deduplicates top tracks to avoid multiple versions of the same song
- Uses batch size 40 with ETag re-instantiation for reliable adds
- Outputs a JSON summary with found/not-found/mismatch details

Preferred pattern: import `search_tidal_artists`/`select_tidal_artist` from `kexp_setlist_sync.py` instead of ad-hoc exact-string search. KEXP matching returns nothing when several TIDAL artists share a name; for lineup playlists, fall back to the top search-rank exact/alias candidate and flag it as ambiguous in the report rather than dropping the artist.

## Conventions

- Confirm with the user before write operations (create-playlist, add-tracks, clear), except `expand_daily_discovery.py` when Sergio explicitly asks to run it. `kexp_setlist_sync.py` previews by default and writes only with `--write`.
- Parse JSON output and present it readably — do not dump raw JSON to the user
- When searching for a specific song (not artist), write a quick inline `uv run` python snippet calling `session.search(query, models=[tidalapi.media.Track])`
- For bulk operations (10+ artists), write a one-off Python script rather than running CLI commands in a loop
- Always validate artist matches before adding tracks — flag any name that doesn't match the search query
- When a reference playlist exists, extract artist IDs from it first to avoid search ambiguity

## Authentication

First-time login requires user interaction (opens a browser URL for PKCE auth):

```bash
uv run skills/tidal/scripts/tidal_cli.py login
```

Session persists in `skills/tidal/.tidal-session.json` and is reused automatically.

## Requirements

- `uv` (for `uv run --script` execution)
- `tidalapi` (declared as inline script dependency)
- Browser access for first-time PKCE authentication
