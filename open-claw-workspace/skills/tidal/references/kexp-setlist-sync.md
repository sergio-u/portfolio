# KEXP to TIDAL Runbook

## First-time authentication

Authenticate once before previewing or writing:

```bash
uv run --script skills/tidal/scripts/tidal_cli.py login
```

Expected result: browser-based PKCE login completes and `skills/tidal/.tidal-session.json` is saved.

## Find a program

```bash
uv run --script skills/tidal/scripts/kexp_setlist_sync.py --list-programs
```

Expected output: active KEXP program ids and names, one per line.

## Weekly agent job

Use these values when creating the OpenClaw clawjob:

- Program: `El Sonido`
- KEXP program id: `2`
- Tidal folder: `Radio`
- Playlist template: `KEXP El Sonido - YYYY`
- Working directory: workspace root
- Package index: default public PyPI; do not embed a workstation proxy in the script or clawjob
- Command: `uv run --script skills/tidal/scripts/kexp_setlist_sync.py "El Sonido" --artist-fallback --episode-duplicates --write`
- Scope: El Sonido only; do not add other programs to this job
- Cadence: weekly, after the latest El Sonido airing has finished

The 2026 target is `KEXP El Sonido - 2026` (`787587e0-a4a3-4d8d-b0d7-808e02ba53f8`) in `Radio` (`b72cdfc3-299d-426a-89d5-a67da441390c`). Names are authoritative; ids are diagnostic references. Current bootstrap contains 1,079 tracks through the August 24, 2026 episode. Every validated strict candidate and approved artist fallback from the full 2026 audit is present. Forty-seven strict source misses remain: 29 are represented by already-present artist fallbacks and 18 have no confidently resolved Tidal artist.

The 2025 target is `KEXP El Sonido - 2025` (`ec273ede-0d61-469c-8175-a7105499b9f4`) in `Radio`. It contains 1,492 tracks from 52 episodes after strict matching, artist fallbacks, and multiple recovery passes. The remaining 56 unique source songs are listed in `notes/el-sonido-2025-missing-tracks.md` with KEXP metadata and the top three Tidal candidates for manual review.

Routine writes find the yearly playlist by name and preserve its existing folder placement. With `--artist-fallback`, a genuine song non-find adds one top track per confidently resolved credited artist. These substitutions are logged separately, never counted as song matches, and are used only when no song candidate clears the current confidence gates. With `--episode-duplicates`, the same recording may appear in separate weekly episodes while ignored `skills/tidal/.kexp-sync-state.json` prevents a rerun from duplicating the same episode. State is bound to the Tidal playlist id and uses a pending transaction plus playlist-prefix reconciliation so a crash cannot blindly replay a duplicate-enabled write. Repeats within one episode remain deduplicated. Historical and multi-episode backfills keep their existing global ID/ISRC deduplication.

Before enabling the clawjob against an existing yearly playlist, seed its latest already-present episode once without changing Tidal:

```bash
uv run --script skills/tidal/scripts/kexp_setlist_sync.py "El Sonido" --artist-fallback --seed-episode-state
```

The current workspace state is seeded for the August 24, 2026 episode with 44 tracks. Seed again after cloning to another machine, losing the ignored state file, or replacing the Tidal playlist. On the first successful write of a new calendar year, verify the new `KEXP El Sonido - YYYY` playlist is moved into `Radio` before considering the job successful. A repeated weekly run should report a no-op when that episode state is complete.

The clawjob result must always state the unmatched count and list every unmatched song. Treat any unmatched song or accepted/requested write mismatch as a warning requiring review; do not report an unqualified success.

## Weekly sync

Preview latest El Sonido episode first:

```bash
uv run --script skills/tidal/scripts/kexp_setlist_sync.py "El Sonido" --artist-fallback --episode-duplicates
```

Expected output includes `Mode: preview`, episode start time, aired and matched counts, every unmatched song, target yearly playlist, and `Preview only`.

Review misses. Script first uses cached MusicBrainz recording-ID to ISRC resolution when KEXP supplies an identifier, then combines full-credit, title-first, and album-title searches. Fallback scoring uses KEXP album/version metadata as positive evidence, never as a general requirement. Capitalization, whitespace, quotes, accents, punctuation, and Unicode script differences normalize before comparison. It trusts split credits only for confirmed collaborations and allows only one-sided fuzzy title or artist matching. Exact live/remix versions with matching album evidence rank first; when unavailable, studio/base tracks are acceptable fallbacks. Studio sources still reject unrelated live/remix candidates, except an exact normalized title whose complete multi-artist credits match the remix candidate. When multiple candidates independently pass all current title, artist, and version confidence gates, Tidal search rank selects one rather than dropping the source song. Candidates that do not clear those gates stay unmatched. Then write:

```bash
uv run --script skills/tidal/scripts/kexp_setlist_sync.py "El Sonido" --artist-fallback --episode-duplicates --write
```

Expected output includes `Mode: write`, `Tracks accepted`, unmatched count and names, and either a create, prepend, or no-op action. Any unmatched song or accepted/requested mismatch appears as a warning in the agent's job result.

## Multi-episode backfill

Preview four recent episodes, newest first:

```bash
uv run --script skills/tidal/scripts/kexp_setlist_sync.py "El Sonido" --episodes 4
```

Write after reviewing misses:

```bash
uv run --script skills/tidal/scripts/kexp_setlist_sync.py "El Sonido" --episodes 4 --write
```

Backfills preserve newest-first order per yearly playlist: missing newer episodes prepend and missing older episodes append. Script refuses a missing episode that would require an ambiguous middle insertion. Runs crossing New Year target separate `KEXP El Sonido - YYYY` playlists. The same commands accept any KEXP program name or id for manual past-year or other-show backfills; only the scheduled clawjob is restricted to El Sonido. Do not pass `--episode-duplicates` to backfills because duplicate episode state is intentionally latest-weekly-only.

### Post-backfill recovery loop

When a backfill still has many unmatched sources after artist fallbacks:

1. Build a unique residual list separating sources with candidates that miss the confidence gates from sources with no resolved artist.
2. Run a read-only identifier pass: KEXP recording ID to MusicBrainz ISRC to Tidal.
3. Run a read-only Tidal pass using full credit/title, raw and ASCII title-only top 300, cleaned title, album plus title, and each trusted artist credit plus title.
4. Add only candidates that pass current title, artist, album, version, and ID/ISRC deduplication rules.
5. Inspect newly labeled examples for reusable rules, update the self-check first, and rerun only the residual pool.
6. Perform at most one more rule pass. Stop when recovery is negligible or further reduction requires weak candidates or policy substitutions.
7. Export every remaining source with episode, KEXP metadata, top candidates, `Decision: pending`, and `Reusable rule: pending` so manual choices can become labeled input for a later matcher cleanup.

Never hide residual counts. Report strict matches, fallback substitutions, no-artist sources, accepted writes, and the path to the manual-review list.

To select one known airing, use its local ISO date or full timestamp:

```bash
uv run --script skills/tidal/scripts/kexp_setlist_sync.py "El Sonido" --episode 2026-08-24
```

If one date contains several airings, use one timestamp listed by the ambiguity error. When an existing yearly playlist has no track overlap with a named episode, the script refuses to guess whether that episode belongs at the top or bottom.

## KEXP API gotchas

- Unsupported query parameters are ignored with HTTP 200. `/shows?program=<id>` and `/plays?show=<id>` do not filter. Script filters program and show ids client-side.
- `/shows` supports `start_time_after` and `start_time_before`; `/plays` supports `airdate_after` and `airdate_before`. Script uses these time windows.
- One airing can span several show records sharing or nearly sharing a start time. Record ids are not reliably ordered. Script groups nearby records before reading plays.
- Separate blocks of one program can air hours apart. Grouping uses a short window so those remain distinct episodes.
- `/plays` has no result count and uses pagination links. It can keep returning `next` after an empty page, so script follows links until `next` ends or a page is empty.
- KEXP returns HTTP 403 without a User-Agent header. Every request goes through one helper that supplies it.
- Air breaks omit artist and song fields. Script checks `play_type` before reading them.
- Only about half of track plays include a MusicBrainz recording id. When present, the script resolves it to ISRCs through the public, unauthenticated MusicBrainz API at its one-request-per-second limit and caches results in ignored `skills/tidal/.kexp-match-cache.json`. MusicBrainz OAuth credentials are neither needed nor stored. After three MusicBrainz failures in one run, the optional identifier path disables itself and matching continues through Tidal heuristics. Tracks without a usable ISRC fall back to structured artist, title, album, and version evidence.

## Offline self-check

```bash
uv run --script skills/tidal/scripts/kexp_setlist_sync.py --self-check
```

Expected output: `Self-check passed.` No network or credentials are used.
