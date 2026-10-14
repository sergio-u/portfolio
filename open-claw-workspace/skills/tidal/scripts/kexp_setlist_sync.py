#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["anyascii>=0.3.3,<0.4", "filelock>=3.20,<4", "requests>=2.32.3,<3", "tidalapi"]
# ///
"""Preview or sync recent KEXP program setlists to yearly TIDAL playlists."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from time import sleep, time as current_time
from types import SimpleNamespace
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
import tidalapi
from anyascii import anyascii
from filelock import FileLock, Timeout
from tidalapi.exceptions import ObjectNotFound

from tidal_playlist import (
    add_tracks_to_playlist,
    find_user_playlist_by_name,
    get_playlist_tracks,
    get_session,
)

KEXP_API = "https://api.kexp.org/v2/"
MUSICBRAINZ_API = "https://musicbrainz.org/ws/2/recording/"
KEXP_TIMEZONE = ZoneInfo("America/Los_Angeles")
USER_AGENT = "open-claw-workspace-kexp-tidal-sync/1.0"
MUSICBRAINZ_USER_AGENT = (
    "open-claw-workspace-kexp-tidal-sync/1.0 "
    "(https://github.com/sergio-u/open-claw-workspace)"
)
MATCH_CACHE_FILE = Path(__file__).resolve().parent.parent / ".kexp-match-cache.json"
MATCH_CACHE_LOCK = Path(f"{MATCH_CACHE_FILE}.lock")
SYNC_STATE_FILE = Path(__file__).resolve().parent.parent / ".kexp-sync-state.json"
SYNC_STATE_LOCK = Path(f"{SYNC_STATE_FILE}.lock")
GROUP_WINDOW = timedelta(minutes=15)
PLAY_WINDOW = timedelta(hours=8)
TIDAL_TITLE_SEARCH_LIMIT = 300
MIN_FUZZY_TITLE_LENGTH = 8
MIN_TITLE_SIMILARITY = 0.90
MIN_ARTIST_SIMILARITY = 0.87
MIN_ALBUM_SIMILARITY = 0.8
MIN_ALBUM_FUZZY_LENGTH = 4
ARTIST_SIMILARITY_MARGIN = 0.03
ARTIST_SEPARATOR = re.compile(
    r"\s*(?:,|&|\bfeat(?:uring)?\.?|\bft\.?|\bcon\b|\bwith\b|\band\b)\s*"
    r"|\s+[xX]\s+",
    re.IGNORECASE,
)
_MATCH_CACHE: dict[str, Any] | None = None
_MUSICBRAINZ_FAILURES = 0
_MUSICBRAINZ_DISABLED = False


@dataclass(frozen=True)
class Episode:
    """One program airing represented by one or more KEXP show records."""

    start_time: datetime
    shows: tuple[dict[str, Any], ...]

    @property
    def show_ids(self) -> set[int]:
        """Return KEXP show ids belonging to this airing."""
        return {show["id"] for show in self.shows}


def parse_datetime(value: str) -> datetime:
    """Parse an API timestamp and require or assign an explicit timezone."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=KEXP_TIMEZONE)


def kexp_get(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch one KEXP API page with the required User-Agent header."""
    url = urljoin(KEXP_API, url)
    if not url.startswith(KEXP_API):
        raise RuntimeError(f"Refusing unexpected KEXP pagination URL: {url}")
    response = requests.get(
        url,
        params=params,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_all_pages(endpoint: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Follow KEXP pagination links and return every result."""
    results: list[dict[str, Any]] = []
    url: str | None = endpoint
    page_params = params
    while url:
        payload = kexp_get(url, page_params)
        page = payload.get("results", [])
        if not page:
            break
        results.extend(page)
        url = payload.get("next")
        page_params = None
    return results


def read_match_cache() -> dict[str, Any]:
    """Read and validate the optional MusicBrainz cache."""
    empty = {"musicbrainz_isrcs": {}}
    if not MATCH_CACHE_FILE.exists():
        return empty
    try:
        cache = json.loads(MATCH_CACHE_FILE.read_text())
        recordings = cache["musicbrainz_isrcs"]
        if not isinstance(recordings, dict) or any(
            not isinstance(recording_id, str)
            or not isinstance(isrcs, list)
            or any(not isinstance(isrc, str) for isrc in isrcs)
            for recording_id, isrcs in recordings.items()
        ):
            raise ValueError("invalid cache shape")
        return {"musicbrainz_isrcs": recordings}
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"Warning: ignoring invalid match cache: {exc}", file=sys.stderr)
        return empty


def write_match_cache(cache: dict[str, Any]) -> None:
    """Replace the cache atomically without making matching depend on the write."""
    temporary_path = None
    try:
        with NamedTemporaryFile(
            "w",
            dir=MATCH_CACHE_FILE.parent,
            prefix=".kexp-match-cache-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(cache, temporary, ensure_ascii=True, indent=2)
            temporary.write("\n")
        temporary_path.replace(MATCH_CACHE_FILE)
    except OSError as exc:
        print(f"Warning: could not write match cache: {exc}", file=sys.stderr)
    finally:
        try:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink()
        except OSError:
            pass


def read_sync_state() -> dict[str, Any]:
    """Read and validate critical per-episode idempotency state."""
    if not SYNC_STATE_FILE.exists():
        return {"playlists": {}}
    try:
        state = json.loads(SYNC_STATE_FILE.read_text())
        playlists = state["playlists"]
        if not isinstance(playlists, dict):
            raise ValueError("invalid playlists")
        for playlist in playlists.values():
            if not isinstance(playlist, dict):
                raise ValueError("invalid playlist")
            playlist_id_value = playlist.get("playlist_id")
            if playlist_id_value is not None and not isinstance(playlist_id_value, str):
                raise ValueError("invalid playlist id")
            episodes = playlist["episodes"]
            if not isinstance(episodes, dict):
                raise ValueError("invalid episodes")
            for episode_id, episode in list(episodes.items()):
                if isinstance(episode, list):
                    episode = {"recorded": episode, "pending": None}
                    episodes[episode_id] = episode
                if not isinstance(episode, dict):
                    raise ValueError("invalid episode")
                recorded = episode.get("recorded")
                pending = episode.get("pending")
                if not isinstance(recorded, list) or any(
                    not isinstance(identity, str) for identity in recorded
                ):
                    raise ValueError("invalid recorded identities")
                if pending is not None and (
                    not isinstance(pending, dict)
                    or not isinstance(pending.get("tracks"), list)
                    or not isinstance(pending.get("before_count"), int)
                    or any(
                        not isinstance(track, dict)
                        or not isinstance(track.get("id"), int)
                        or not isinstance(track.get("identity"), str)
                        for track in pending.get("tracks", [])
                    )
                    or not isinstance(pending.get("before_top_ids"), list)
                    or any(
                        not isinstance(track_id, int)
                        for track_id in pending.get("before_top_ids", [])
                    )
                ):
                    raise ValueError("invalid pending transaction")
        return state
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid KEXP sync state: {exc}") from exc


def write_sync_state(state: dict[str, Any]) -> None:
    """Atomically replace critical per-episode idempotency state."""
    temporary_path = None
    try:
        with NamedTemporaryFile(
            "w",
            dir=SYNC_STATE_FILE.parent,
            prefix=".kexp-sync-state-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(state, temporary, ensure_ascii=True, indent=2)
            temporary.write("\n")
        temporary_path.replace(SYNC_STATE_FILE)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def track_identity(track: dict[str, Any]) -> str:
    """Return stable recording identity for episode state."""
    return f"isrc:{track['isrc']}" if track.get("isrc") else f"id:{track['id']}"


def report_tracks(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Return unique matched and fallback tracks for one episode."""
    unique = {}
    for track in [*report["matched"], *report.get("fallbacks", [])]:
        unique.setdefault(track_identity(track), track)
    return list(unique.values())


def track_matches_existing(track: dict[str, Any], existing_tracks: list[Any]) -> bool:
    """Check exact identity or equivalent visible recording metadata."""
    for existing in existing_tracks:
        if track["id"] == existing.id or (
            track.get("isrc")
            and track["isrc"] == getattr(existing, "isrc", None)
        ):
            return True
        existing_duration = getattr(existing, "duration", None)
        if (
            track.get("duration") is not None
            and existing_duration is not None
            and abs(track["duration"] - existing_duration) <= 3
            and normalize_match_text(track["song"])
            == normalize_match_text(existing.name)
            and normalize_words(track["artist"])
            == normalize_words(existing.artist.name)
        ):
            return True
    return False


def reconcile_pending_ids(
    pending: dict[str, Any],
    current_top_ids: list[int],
    current_count: int,
) -> set[int]:
    """Recover accepted IDs from a duplicate-enabled prepend transaction."""
    before_count = pending["before_count"]
    before_top = pending["before_top_ids"]
    pending_ids = [track["id"] for track in pending["tracks"]]
    if current_count < before_count:
        raise RuntimeError("Playlist shrank during pending episode write")

    if before_top:
        positions = [
            index
            for index in range(len(current_top_ids) - len(before_top) + 1)
            if current_top_ids[index : index + len(before_top)] == before_top
        ]
    else:
        positions = [current_count - before_count]

    for position in reversed(positions):
        inserted = current_top_ids[:position]
        inserted_set = set(inserted)
        expected = [track_id for track_id in pending_ids if track_id in inserted_set]
        if inserted == expected:
            return inserted_set
    raise RuntimeError(
        "Could not reconcile pending episode write; inspect playlist before retrying"
    )


def get_recording_isrcs(recording_id: str) -> list[str]:
    """Resolve one MusicBrainz recording id to cached ISRCs."""
    global _MATCH_CACHE, _MUSICBRAINZ_DISABLED, _MUSICBRAINZ_FAILURES

    if _MATCH_CACHE is not None:
        cached = _MATCH_CACHE.get("musicbrainz_isrcs", {})
        if recording_id in cached:
            return cached[recording_id]

    try:
        with FileLock(str(MATCH_CACHE_LOCK), timeout=60):
            cache = read_match_cache()
            cached = cache["musicbrainz_isrcs"]
            if recording_id in cached:
                _MATCH_CACHE = cache
                return cached[recording_id]
            if _MUSICBRAINZ_DISABLED:
                return []

            request_started = current_time()
            try:
                response = requests.get(
                    f"{MUSICBRAINZ_API}{recording_id}",
                    params={"inc": "isrcs", "fmt": "json"},
                    headers={"User-Agent": MUSICBRAINZ_USER_AGENT},
                    timeout=10,
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                _MUSICBRAINZ_FAILURES += 1
                print(
                    f"Warning: MusicBrainz lookup failed for {recording_id}: {exc}",
                    file=sys.stderr,
                )
                if _MUSICBRAINZ_FAILURES >= 3:
                    _MUSICBRAINZ_DISABLED = True
                    print(
                        "Warning: disabling MusicBrainz lookups for this run after "
                        "three failures",
                        file=sys.stderr,
                    )
                return []
            finally:
                wait = 1.1 - (current_time() - request_started)
                if wait > 0:
                    sleep(wait)

            isrcs = response.json().get("isrcs") or []
            cached[recording_id] = isrcs
            _MATCH_CACHE = cache
            write_match_cache(cache)
            return isrcs
    except Timeout:
        print("Warning: timed out waiting for MusicBrainz cache lock", file=sys.stderr)
        return []


def match_recording_id(session: tidalapi.Session, recording_id: str | None):
    """Return an exact Tidal ISRC match for a KEXP recording id, if available."""
    if not recording_id:
        return None
    for isrc in get_recording_isrcs(recording_id):
        try:
            tracks = session.get_tracks_by_isrc(isrc)
        except ObjectNotFound:
            continue
        if tracks:
            return tracks[0]
    return None


def list_programs() -> list[dict[str, Any]]:
    """Return active KEXP programs sorted by name."""
    programs = get_all_pages("programs/", {"limit": 100})
    return sorted(
        (program for program in programs if program.get("is_active")),
        key=lambda program: program["name"].casefold(),
    )


def resolve_program(identifier: str, programs: list[dict[str, Any]]) -> dict[str, Any]:
    """Resolve an active program by numeric id, exact name, or unique partial name."""
    if identifier.isdigit():
        matches = [program for program in programs if program.get("id") == int(identifier)]
    else:
        folded = identifier.casefold()
        exact = [program for program in programs if program["name"].casefold() == folded]
        matches = exact or [program for program in programs if folded in program["name"].casefold()]

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        candidates = ", ".join(f"{item['name']} ({item['id']})" for item in matches)
        raise RuntimeError(f"Program {identifier!r} is ambiguous: {candidates}")
    raise RuntimeError(f"Program {identifier!r} not found. Run with --list-programs.")


def group_episodes(
    shows: list[dict[str, Any]],
    program_id: int,
    window: timedelta = GROUP_WINDOW,
) -> list[Episode]:
    """Group nearby show records for one program into distinct airings."""
    matching = sorted(
        (show for show in shows if show.get("program") == program_id),
        key=lambda show: parse_datetime(show["start_time"]),
        reverse=True,
    )
    groups: list[list[dict[str, Any]]] = []
    anchors: list[datetime] = []

    for show in matching:
        started = parse_datetime(show["start_time"])
        if groups and anchors[-1] - started <= window:
            groups[-1].append(show)
        else:
            groups.append([show])
            anchors.append(started)

    return [
        Episode(
            start_time=min(parse_datetime(show["start_time"]) for show in group),
            shows=tuple(group),
        )
        for group in groups
    ]


def fetch_show_records(after: datetime, before: datetime) -> list[dict[str, Any]]:
    """Fetch show records in a working server-side time window."""
    return get_all_pages(
        "shows/",
        {
            "limit": 100,
            "start_time_after": after.isoformat(),
            "start_time_before": before.isoformat(),
        },
    )


def recent_episodes(program_id: int, count: int) -> list[Episode]:
    """Return the requested number of latest episodes, newest first."""
    if count < 1:
        raise ValueError("--episodes must be at least 1")

    before = datetime.now(timezone.utc)
    lookback_days = max(45, count * 14)
    episodes: list[Episode] = []
    while lookback_days <= 1460:
        shows = fetch_show_records(before - timedelta(days=lookback_days), before)
        episodes = group_episodes(shows, program_id)
        if len(episodes) >= count:
            return episodes[:count]
        lookback_days *= 2
    raise RuntimeError(f"Found only {len(episodes)} episodes in four years")


def named_episode(program_id: int, selector: str) -> Episode:
    """Select one episode by ISO date or timestamp."""
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", selector):
            selected_date = date.fromisoformat(selector)
            after = datetime.combine(selected_date, time.min, KEXP_TIMEZONE)
            before = after + timedelta(days=1)
            target = None
        else:
            target = parse_datetime(selector)
            after = target - GROUP_WINDOW
            before = target + GROUP_WINDOW
    except ValueError as exc:
        raise ValueError("--episode must be an ISO date or timestamp") from exc

    episodes = group_episodes(fetch_show_records(after, before), program_id)
    if target is not None:
        episodes = [
            episode
            for episode in episodes
            if abs(episode.start_time - target) <= GROUP_WINDOW
        ]
    if len(episodes) == 1:
        return episodes[0]
    if not episodes:
        raise RuntimeError(f"No episode found for {selector}")

    starts = ", ".join(episode.start_time.isoformat() for episode in episodes)
    raise RuntimeError(f"Episode {selector!r} is ambiguous: {starts}")


def extract_setlist(episode: Episode, plays: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter, order, and deduplicate track plays for one episode."""
    tracks: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for play in sorted(plays, key=lambda item: parse_datetime(item["airdate"])):
        if play.get("show") not in episode.show_ids or play.get("play_type") != "trackplay":
            continue
        artist = play.get("artist")
        song = play.get("song")
        if not artist or not song:
            continue
        key = (" ".join(artist.casefold().split()), " ".join(song.casefold().split()))
        if key in seen:
            continue
        seen.add(key)
        tracks.append(play)
    return tracks


def fetch_setlist(episode: Episode) -> list[dict[str, Any]]:
    """Fetch and extract all track plays for one episode."""
    starts = [parse_datetime(show["start_time"]) for show in episode.shows]
    plays = get_all_pages(
        "plays/",
        {
            "limit": 100,
            "airdate_after": (min(starts) - timedelta(minutes=5)).isoformat(),
            "airdate_before": (max(starts) + PLAY_WINDOW).isoformat(),
        },
    )
    return extract_setlist(episode, plays)


def normalize_words(value: str) -> str:
    """Normalize script, accents, punctuation, casing, and whitespace."""
    return re.sub(r"[\W_]+", " ", anyascii(value).casefold()).strip()


def normalize_match_text(value: str) -> str:
    """Normalize a title, including known feature and version suffixes."""
    qualifier = (
        r"feat\.?|ft\.?|featuring|remaster(?:ed)?|live|remix(?:es)?|remox|rmx|mix|"
        r"radio(?: edit)?|acoustic|deluxe|bonus|edit|version|instrumental|cover"
    )
    previous = None
    while value != previous:
        previous = value
        value = re.sub(
            rf"\s*[\(\[][^\)\]]*(?<!\w)(?:{qualifier})(?!\w)[^\)\]]*[\)\]]\s*$",
            "",
            value,
            flags=re.IGNORECASE,
        )
    value = re.sub(
        r"\s*(?:\([^\)]*\)\s*)?COVER\s*[\"']?\s*$",
        "",
        value,
    )
    value = re.sub(
        r"\s+-\s+cover\s*[\"']?\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\s*(feat\.?|ft\.?|featuring)\s+.*", "", value, flags=re.IGNORECASE)
    value = re.sub(
        rf"\s*-\s*(?:(?<!\w)(?:{qualifier})(?!\w).*|"
        rf"[^-]*(?<!\w)(?:remix|remox|rmx|mix|edit)(?!\w))\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return normalize_words(value)


def version_qualifiers(value: str) -> set[str]:
    """Return normalized recording-version hints from display metadata."""
    text = normalize_words(value)
    qualifiers = set()
    if re.search(r"\b(live|en vivo|unplugged)\b", text):
        qualifiers.add("live")
    if re.search(r"\b(remix(?:es)?|remox|rmx)\b", text):
        qualifiers.add("remix")
    if re.search(r"\bremaster(?:ed)?\b", text):
        qualifiers.add("remaster")
    for qualifier in ("acoustic", "instrumental", "cover", "edit"):
        if re.search(rf"\b{qualifier}\b", text):
            qualifiers.add(qualifier)
    return qualifiers


def album_match_score(source_album: str | None, track: Any) -> float:
    """Score normalized KEXP and Tidal album agreement."""
    candidate_album = getattr(getattr(track, "album", None), "name", None)
    if not source_album or not candidate_album:
        return 0.0
    source = normalize_words(source_album)
    candidate = normalize_words(candidate_album)
    if source == candidate:
        return 1.0
    if min(len(source), len(candidate)) < MIN_ALBUM_FUZZY_LENGTH:
        return 0.0
    if source in candidate or candidate in source:
        return 0.95
    similarity = SequenceMatcher(None, source, candidate).ratio()
    return similarity if similarity >= MIN_ALBUM_SIMILARITY else 0.0


def candidate_version_score(
    track: Any,
    source_title: str,
    source_album: str | None,
    source_is_live: bool,
) -> int:
    """Prefer candidates compatible with KEXP version hints."""
    source = version_qualifiers(f"{source_title} {source_album or ''}")
    if source_is_live:
        source.add("live")
    candidate = version_qualifiers(
        " ".join(
            filter(
                None,
                [
                    track.name,
                    getattr(track, "version", None),
                    getattr(getattr(track, "album", None), "name", None),
                ],
            )
        )
    )
    strong = source & {"live", "remix", "acoustic", "instrumental"}
    if strong:
        if strong <= candidate:
            return (
                3
                if not source_album
                or album_match_score(source_album, track) >= MIN_ALBUM_SIMILARITY
                else 1
            )
        if strong <= {"live", "remix"} and not candidate & {
            "live",
            "remix",
            "acoustic",
            "instrumental",
        }:
            return 1
        return -1
    if candidate & {"live", "remix"}:
        return -1
    return 0 if "remaster" in candidate else 1


def normalize_artist_alias(value: str) -> str:
    """Normalize guarded article and infix connector differences."""
    articles = {"el", "la", "las", "los", "the"}
    collectives = {"banda", "conjunto", "grupo"}
    words = normalize_words(value).split()
    if len(words) > 1 and words[0] in collectives:
        words = words[1:]
    if len(words) > 1 and words[0] in articles and words[1] not in articles:
        words = words[1:]
    words = ["compania" if word == "cia" else word for word in words]
    normalized = " ".join(
        word
        for index, word in enumerate(words)
        if word not in {"and", "y"} or index in {0, len(words) - 1}
    )
    return re.sub(
        r"(?<=[^\W\d_])\s+(?=\d)|(?<=\d)\s+(?=[^\W\d_])",
        "",
        normalized,
    )


def split_artist_credits(value: str) -> list[str]:
    """Split a display credit while preserving each original artist name."""
    return list(dict.fromkeys(part.strip() for part in ARTIST_SEPARATOR.split(value) if part.strip()))


def has_explicit_collaboration(value: str) -> bool:
    """Return whether a trusted connector has nonempty credits on both sides."""
    return bool(
        re.search(
            r"\S\s+(?:feat(?:uring)?\.?|ft\.?)\s+\S",
            value,
            flags=re.IGNORECASE,
        )
    )


def tidal_artist_names(track: Any) -> set[str]:
    """Return normalized structured artists for a Tidal track."""
    artists = getattr(track, "artists", None) or [track.artist]
    return {normalize_words(artist.name) for artist in artists}


def artist_match_score(
    track: Any,
    source_artist: str,
    source_artist_count: int,
) -> int:
    """Score exact full-credit or confirmed collaboration matches."""
    tidal_names = tidal_artist_names(track)
    full_credit = normalize_words(source_artist)
    if full_credit in tidal_names:
        return 100
    full_alias = normalize_artist_alias(source_artist)
    if full_alias and any(
        full_alias == normalize_artist_alias(name) for name in tidal_names
    ):
        return 90

    spanish_parts = {
        normalize_words(part)
        for part in re.split(r"\s+y\s+", source_artist, flags=re.IGNORECASE)
    }
    if len(spanish_parts) > 1 and spanish_parts <= tidal_names:
        return len(spanish_parts)

    parts = {normalize_words(part) for part in split_artist_credits(source_artist)}
    overlap = parts & tidal_names
    if has_explicit_collaboration(source_artist):
        primary = normalize_words(split_artist_credits(source_artist)[0])
        if primary in tidal_names:
            return max(1, len(overlap))
    if not overlap or len(parts) < 2 or len(tidal_names) < 2:
        return 0
    if source_artist_count > 1 or parts <= tidal_names:
        return len(overlap)
    return 0


def complete_artist_correspondence(track: Any, source_artist: str) -> bool:
    """Return whether every source credit is represented exactly in Tidal."""
    tidal_names = tidal_artist_names(track)
    full_credit = normalize_words(source_artist)
    if full_credit in tidal_names:
        return True
    parts = {normalize_words(part) for part in split_artist_credits(source_artist)}
    spanish_parts = {
        normalize_words(part)
        for part in re.split(r"\s+y\s+", source_artist, flags=re.IGNORECASE)
    }
    return (
        len(parts) > 1 and parts <= tidal_names
    ) or (
        len(spanish_parts) > 1 and spanish_parts <= tidal_names
    )


def fuzzy_artist_match_score(track: Any, source_artist: str) -> float:
    """Score small artist spelling differences with unique credit alignment."""
    parts = {
        normalize_artist_alias(part)
        for part in split_artist_credits(source_artist)
    }
    candidates = {
        normalize_artist_alias(name) for name in tidal_artist_names(track)
    }
    if len(parts) == 1:
        source = next(iter(parts))
        if any(
            min(len(source), len(candidate)) >= 8
            and (
                source.startswith(f"{candidate} ")
                or candidate.startswith(f"{source} ")
            )
            for candidate in candidates
        ):
            return 0.99
        source_compact = re.sub(r"\W", "", source_artist)
        if (
            source_compact.isupper()
            and 2 <= len(source_compact) <= 5
            and any(candidate.startswith(f"{source} ") for candidate in candidates)
        ):
            return 0.99
        best, candidate_length = max(
            (
                (SequenceMatcher(None, source, candidate).ratio(), len(candidate))
                for candidate in candidates
            ),
            default=(0.0, 0),
        )
        if min(len(source), candidate_length) < 6:
            return 0.0
        return best if best >= MIN_ARTIST_SIMILARITY else 0.0

    pairs = sorted(
        (
            (SequenceMatcher(None, source, candidate).ratio(), source, candidate)
            for source in parts
            for candidate in candidates
            if source == candidate or min(len(source), len(candidate)) >= 5
        ),
        reverse=True,
    )
    matched_sources = set()
    matched_candidates = set()
    similarities = []
    for similarity, source, candidate in pairs:
        if similarity < MIN_ARTIST_SIMILARITY:
            continue
        if source in matched_sources or candidate in matched_candidates:
            continue
        matched_sources.add(source)
        matched_candidates.add(candidate)
        similarities.append(similarity)
    if len(matched_sources) != len(parts) or not any(
        similarity == 1.0 for similarity in similarities
    ):
        return 0.0
    return sum(similarities) / len(similarities)


def select_tidal_candidate(
    tracks: list[Any],
    source_artist: str,
    source_title: str,
    *,
    source_artist_count: int = 0,
    source_album: str | None = None,
    source_is_live: bool = False,
    allow_fuzzy_title: bool,
    allow_fuzzy_artist: bool = False,
):
    """Select one validated candidate or return None when confidence is insufficient."""
    title = normalize_match_text(source_title)
    source_versions = version_qualifiers(f"{source_title} {source_album or ''}")
    if source_is_live:
        source_versions.add("live")
    strong_versions = source_versions & {"live", "remix", "acoustic", "instrumental"}
    scored: list[tuple[Any, float, float, float, int, int]] = []

    seen_ids: set[int] = set()
    for rank, track in enumerate(tracks):
        if track.id in seen_ids:
            continue
        seen_ids.add(track.id)
        candidate_title = normalize_match_text(track.name)
        title_exact = candidate_title == title
        title_similarity = SequenceMatcher(None, title, candidate_title).ratio()
        album_score = album_match_score(source_album, track)
        version_score = candidate_version_score(
            track,
            source_title,
            source_album,
            source_is_live,
        )
        artist_score = float(
            artist_match_score(track, source_artist, source_artist_count)
        )
        if not artist_score and allow_fuzzy_artist and title_exact:
            fuzzy_artist = fuzzy_artist_match_score(track, source_artist)
            if (
                fuzzy_artist
                and version_score > 0
                and (
                    album_score >= MIN_ALBUM_SIMILARITY
                    or len(title) >= MIN_FUZZY_TITLE_LENGTH
                )
            ):
                artist_score = fuzzy_artist
        if (
            version_score < 0
            and title_exact
            and "remix" in version_qualifiers(
                " ".join(
                    filter(
                        None,
                        [
                            track.name,
                            getattr(track, "version", None),
                            getattr(getattr(track, "album", None), "name", None),
                        ],
                    )
                )
            )
            and len(split_artist_credits(source_artist)) > 1
            and complete_artist_correspondence(track, source_artist)
        ):
            version_score = 0
        if not artist_score or version_score < 0:
            continue
        title_without_parenthetical = normalize_match_text(
            re.sub(r"\s*[\(\[][^\)\]]+[\)\]]\s*$", "", source_title)
        )
        stylized_title = (
            min(len(title), len(candidate_title)) >= 6
            and title.translate(str.maketrans({"0": "o"})).replace(" ", "")
            == candidate_title.translate(str.maketrans({"0": "o"})).replace(" ", "")
            and artist_score >= 1.0
        )
        title_extension = (
            min(len(title), len(candidate_title)) >= 12
            and (
                f" {title} " in f" {candidate_title} "
                or f" {candidate_title} " in f" {title} "
            )
        ) or (
            len(title_without_parenthetical) >= 8
            and candidate_title == title_without_parenthetical
            and artist_score >= 1.0
            and not strong_versions
        )
        title_threshold = (
            0.85
            if album_score >= MIN_ALBUM_SIMILARITY and artist_score >= 0.99
            else MIN_TITLE_SIMILARITY
        )
        if title_exact or (
            allow_fuzzy_title
            and min(len(title), len(candidate_title)) >= MIN_FUZZY_TITLE_LENGTH
            and (
                title_similarity >= title_threshold
                or title_extension
                or stylized_title
            )
        ):
            scored.append(
                (
                    track,
                    artist_score,
                    title_similarity,
                    album_score,
                    version_score,
                    rank,
                )
            )

    if not scored:
        return None
    full_credit = normalize_words(source_artist)
    exact_solo = [
        item for item in scored if tidal_artist_names(item[0]) == {full_credit}
    ]
    if exact_solo:
        scored = exact_solo
    scored.sort(key=lambda item: (-item[1], -item[2], -item[4], -item[3], item[5]))
    return scored[0][0]


def search_tidal_tracks(
    session: tidalapi.Session,
    query: str,
    limit: int = 10,
) -> list[Any]:
    """Search only Tidal tracks."""
    return session.search(
        query,
        models=[tidalapi.media.Track],
        limit=limit,
    ).get("tracks", [])


def search_tidal_artists(session: tidalapi.Session, query: str) -> list[Any]:
    """Search only Tidal artists."""
    return session.search(
        query,
        models=[tidalapi.artist.Artist],
        limit=10,
    ).get("artists", [])


def select_tidal_artist(artists: list[Any], source_artist: str):
    """Resolve one artist only when one exact or close candidate clearly wins."""
    unique = list({artist.id: artist for artist in artists}.values())
    source = normalize_words(source_artist)
    exact = [artist for artist in unique if normalize_words(artist.name) == source]
    if len(exact) == 1:
        return exact[0]

    source_alias = normalize_artist_alias(source_artist)
    aliases = [
        artist
        for artist in unique
        if source_alias and normalize_artist_alias(artist.name) == source_alias
    ]
    if len(aliases) == 1:
        return aliases[0]

    scored = sorted(
        (
            (SequenceMatcher(None, source, normalize_words(artist.name)).ratio(), artist)
            for artist in unique
            if min(len(source), len(normalize_words(artist.name))) >= 8
        ),
        key=lambda item: -item[0],
    )
    if not scored or scored[0][0] < MIN_ARTIST_SIMILARITY:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < ARTIST_SIMILARITY_MARGIN:
        return None
    return scored[0][1]


def resolve_tidal_artists(session: tidalapi.Session, play: dict[str, Any]) -> list[Any]:
    """Resolve a band as one artist or each confirmed collaboration credit."""
    source_artist = play["artist"]
    full_results = search_tidal_artists(session, source_artist)
    full_match = select_tidal_artist(full_results, source_artist)
    if full_match:
        return [full_match]
    credits = split_artist_credits(source_artist)
    if len(credits) < 2 or (
        len(play.get("artist_ids") or []) < 2
        and not has_explicit_collaboration(source_artist)
    ):
        return []

    resolved = []
    seen_ids = set()
    for credit in credits:
        artist = select_tidal_artist(search_tidal_artists(session, credit), credit)
        if artist and artist.id not in seen_ids:
            seen_ids.add(artist.id)
            resolved.append(artist)
    return resolved


def get_artist_fallbacks(session: tidalapi.Session, play: dict[str, Any]) -> list[dict[str, Any]]:
    """Return one top track per confidently resolved source artist."""
    fallbacks = []
    seen_track_ids = set()
    for artist in resolve_tidal_artists(session, play):
        try:
            top_tracks = artist.get_top_tracks(limit=10)
        except ObjectNotFound:
            continue
        track = next(
            (track for track in top_tracks if track.id not in seen_track_ids),
            None,
        )
        if track is None:
            continue
        seen_track_ids.add(track.id)
        fallbacks.append(
            {
                "id": track.id,
                "isrc": getattr(track, "isrc", None),
                "artist": track.artist.name,
                "song": track.name,
                "duration": getattr(track, "duration", None),
                "fallback_artist": artist.name,
                "fallback_artist_id": artist.id,
                "kexp_artist": play["artist"],
                "kexp_song": play["song"],
                "reason": "artist_top_track",
            }
        )
    return fallbacks


def match_tidal_track(session: tidalapi.Session, play: dict[str, Any]):
    """Return a matched Tidal track, or None when no candidate is confident enough."""
    recording_match = match_recording_id(session, play.get("recording_id"))
    if recording_match:
        return recording_match

    full_query = f"{play['artist']} {play['song']}"
    source_artist_count = len(play.get("artist_ids") or [])
    source_album = play.get("album")
    source_is_live = bool(play.get("is_live"))
    candidates = search_tidal_tracks(session, full_query)
    selection_args = {
        "source_artist_count": source_artist_count,
        "source_album": source_album,
        "source_is_live": source_is_live,
    }
    match = select_tidal_candidate(
        candidates,
        play["artist"],
        play["song"],
        allow_fuzzy_title=False,
        **selection_args,
    )
    if match:
        return match

    seen_ids = {track.id for track in candidates}
    seen_queries = {full_query.casefold().strip()}
    base_title = normalize_match_text(play["song"])
    queries = [
        (play["song"], TIDAL_TITLE_SEARCH_LIMIT),
        (anyascii(play["song"]), TIDAL_TITLE_SEARCH_LIMIT),
        (base_title, TIDAL_TITLE_SEARCH_LIMIT),
    ]
    if source_album:
        queries.append((f"{source_album} {base_title}", 30))
    for artist in split_artist_credits(play["artist"]):
        queries.append((f"{artist} {base_title}", 30))
        compact_artist = normalize_artist_alias(artist)
        if compact_artist != normalize_words(artist):
            queries.append((f"{compact_artist} {base_title}", 30))
    for query, limit in queries:
        normalized_query = query.casefold().strip()
        if not normalized_query or normalized_query in seen_queries:
            continue
        seen_queries.add(normalized_query)
        for track in search_tidal_tracks(session, query, limit=limit):
            if track.id not in seen_ids:
                seen_ids.add(track.id)
                candidates.append(track)

    for allow_fuzzy_title, allow_fuzzy_artist in (
        (False, False),
        (False, True),
        (True, False),
    ):
        match = select_tidal_candidate(
            candidates,
            play["artist"],
            play["song"],
            allow_fuzzy_title=allow_fuzzy_title,
            allow_fuzzy_artist=allow_fuzzy_artist,
            **selection_args,
        )
        if match:
            return match
    return None


def playlist_name(program: dict[str, Any], year: int) -> str:
    """Return the stable yearly playlist name for a program."""
    return f"KEXP {program['name']} - {year}"


def playlist_id(match: dict[str, Any]) -> str:
    """Read a playlist id from a personal-playlist API result."""
    value = match.get("uuid") or match.get("id")
    if not value:
        raise RuntimeError(f"Matched playlist {match.get('title')!r} has no id/uuid")
    return str(value)


def seed_episode_state(
    session: tidalapi.Session,
    program: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    """Record an already-present episode without changing Tidal."""
    name = playlist_name(program, report["year"])
    match = find_user_playlist_by_name(session, name)
    if not match:
        raise RuntimeError(f"Cannot seed missing playlist {name!r}")
    playlist = session.playlist(playlist_id(match))
    existing_tracks = get_playlist_tracks(playlist)
    tracks = report_tracks(report)
    missing = [
        track for track in tracks if not track_matches_existing(track, existing_tracks)
    ]
    if missing:
        details = ", ".join(
            f"{track['artist']} - {track['song']} ({track['id']})"
            for track in missing
        )
        raise RuntimeError(
            f"Cannot seed {report['start_time']}: {len(missing)} tracks are absent: "
            f"{details}"
        )
    try:
        with FileLock(str(SYNC_STATE_LOCK), timeout=60):
            state = read_sync_state()
            playlist_state = state["playlists"].get(name)
            if playlist_state is None or playlist_state.get("playlist_id") not in {
                None,
                str(playlist.id),
            }:
                playlist_state = {"playlist_id": str(playlist.id), "episodes": {}}
                state["playlists"][name] = playlist_state
            else:
                playlist_state["playlist_id"] = str(playlist.id)
            playlist_state["episodes"][report["start_time"]] = {
                "recorded": sorted(track_identity(track) for track in tracks),
                "pending": None,
            }
            write_sync_state(state)
    except Timeout as exc:
        raise RuntimeError("Timed out waiting for KEXP sync state lock") from exc
    return {
        "playlist": name,
        "episode": report["start_time"],
        "recorded_track_count": len(tracks),
    }


def update_latest_episode_playlist(
    session: tidalapi.Session,
    program: dict[str, Any],
    report: dict[str, Any],
    *,
    write: bool,
) -> dict[str, Any]:
    """Plan or write one episode with cross-episode duplicates and rerun state."""
    name = playlist_name(program, report["year"])
    match = find_user_playlist_by_name(session, name)
    playlist = session.playlist(playlist_id(match)) if match else None
    existing_count = playlist.num_tracks if playlist else 0
    tracks = report_tracks(report)
    accepted_ids: list[int] = []
    recovered_ids: set[int] = set()
    action = "noop"

    try:
        with FileLock(str(SYNC_STATE_LOCK), timeout=60):
            state = read_sync_state()
            playlist_state = state["playlists"].get(name)
            if playlist is not None:
                if playlist_state is None:
                    raise RuntimeError(
                        f"Episode state is not initialized for {name!r}; "
                        "run with --seed-episode-state first"
                    )
                if playlist_state.get("playlist_id") != str(playlist.id):
                    raise RuntimeError(
                        f"Episode state belongs to another playlist for {name!r}; "
                        "run with --seed-episode-state"
                    )
            elif playlist_state is not None:
                raise RuntimeError(
                    f"Episode state references a missing playlist for {name!r}; "
                    "remove or reseed the state"
                )
            elif write and tracks:
                playlist = session.user.create_playlist(
                    name,
                    f"KEXP {program['name']} episodes from {report['year']}, newest first.",
                )
                action = "create"
                playlist_state = {
                    "playlist_id": str(playlist.id),
                    "episodes": {},
                }
                state["playlists"][name] = playlist_state
                write_sync_state(state)
            else:
                playlist_state = {"playlist_id": None, "episodes": {}}

            episodes = playlist_state["episodes"]
            episode_state = episodes.setdefault(
                report["start_time"],
                {"recorded": [], "pending": None},
            )
            pending = episode_state.get("pending")
            if pending:
                if not write or playlist is None:
                    raise RuntimeError(
                        "Pending episode write requires --write recovery"
                    )
                current = session.playlist(playlist.id)
                limit = (
                    len(pending["tracks"])
                    + len(pending["before_top_ids"])
                    + 5
                )
                current_top_ids = [
                    track.id for track in current.tracks(limit=limit)
                ]
                recovered_ids = reconcile_pending_ids(
                    pending,
                    current_top_ids,
                    current.num_tracks,
                )
                recorded = set(episode_state["recorded"])
                recorded.update(
                    track["identity"]
                    for track in pending["tracks"]
                    if track["id"] in recovered_ids
                )
                episode_state["recorded"] = sorted(recorded)
                episode_state["pending"] = None
                write_sync_state(state)

            recorded = set(episode_state["recorded"])
            requested = [
                track for track in tracks if track_identity(track) not in recorded
            ]
            if requested:
                if write and action != "create":
                    action = "prepend"
                elif not write:
                    action = "would-create" if playlist is None else "would-prepend"
                if write:
                    current = session.playlist(playlist.id)
                    before_top_ids = [
                        track.id for track in current.tracks(limit=10)
                    ]
                    episode_state["pending"] = {
                        "tracks": [
                            {
                                "id": track["id"],
                                "identity": track_identity(track),
                            }
                            for track in requested
                        ],
                        "before_count": current.num_tracks,
                        "before_top_ids": before_top_ids,
                    }
                    write_sync_state(state)
                    accepted_ids = add_tracks_to_playlist(
                        session,
                        playlist.id,
                        [track["id"] for track in requested],
                        position=0,
                        allow_duplicates=True,
                        batch_size=100,
                    )
                    accepted = set(accepted_ids)
                    recorded.update(
                        track_identity(track)
                        for track in requested
                        if track["id"] in accepted
                    )
                    episode_state["recorded"] = sorted(recorded)
                    episode_state["pending"] = None
                    write_sync_state(state)
    except Timeout as exc:
        raise RuntimeError("Timed out waiting for KEXP sync state lock") from exc

    result = {
        "year": report["year"],
        "name": name,
        "playlist_id": getattr(playlist, "id", None),
        "action": "recovered" if recovered_ids and action == "noop" else action,
        "existing_track_count": existing_count,
        "duplicate_track_count": len(tracks) - len(requested),
        "requested_track_count": len(requested),
        "accepted_track_count": len(accepted_ids) if write else None,
        "recovered_track_count": len(recovered_ids),
    }
    if write and len(accepted_ids) != len(requested):
        result["warning"] = (
            f"TIDAL accepted {len(accepted_ids)} of {len(requested)} requested tracks."
        )
    if write and playlist:
        result["final_track_count"] = session.playlist(playlist.id).num_tracks
    return result


def build_episode_reports(
    session: tidalapi.Session,
    episodes: list[Episode],
    *,
    artist_fallback: bool = False,
) -> list[dict[str, Any]]:
    """Fetch each setlist and strictly match its tracks on TIDAL."""
    reports: list[dict[str, Any]] = []
    for episode in episodes:
        plays = fetch_setlist(episode)
        matched: list[dict[str, Any]] = []
        fallbacks: list[dict[str, Any]] = []
        unmatched: list[dict[str, str]] = []
        for play in plays:
            track = match_tidal_track(session, play)
            if track is None:
                unmatched.append({"artist": play["artist"], "song": play["song"]})
                if artist_fallback:
                    fallbacks.extend(get_artist_fallbacks(session, play))
            else:
                matched.append(
                    {
                        "id": track.id,
                        "isrc": getattr(track, "isrc", None),
                        "artist": track.artist.name,
                        "song": track.name,
                        "duration": getattr(track, "duration", None),
                        "kexp_artist": play["artist"],
                        "kexp_song": play["song"],
                    }
                )
        reports.append(
            {
                "start_time": episode.start_time.isoformat(),
                "year": episode.start_time.astimezone(KEXP_TIMEZONE).year,
                "show_ids": sorted(episode.show_ids),
                "aired_count": len(plays),
                "matched_count": len(matched),
                "fallback_count": len(fallbacks),
                "matched": matched,
                "fallbacks": fallbacks,
                "unmatched": unmatched,
            }
        )
    return reports


def plan_playlist_insertions(
    existing_ids: set[int],
    year_reports: list[dict[str, Any]],
    playlist_exists: bool,
    name: str,
    *,
    existing_isrcs: set[str] | None = None,
    allow_unanchored_prepend: bool,
) -> tuple[list[int], list[int], int]:
    """Plan safe top and end insertions around episodes already present."""
    missing_by_episode: dict[int, list[int]] = {}
    partial_prepend_ids: list[int] = []
    present_episodes: list[int] = []
    existing_isrcs = existing_isrcs or set()
    planned_ids = set(existing_ids)
    planned_isrcs = set(existing_isrcs)
    matched_count = 0

    for index, report in enumerate(year_reports):
        report_tracks = [*report["matched"], *report.get("fallbacks", [])]
        tracks = list({track["id"]: track for track in report_tracks}.values())
        matched_count += len(report_tracks)
        present = [
            track
            for track in tracks
            if track["id"] in existing_ids
            or (track.get("isrc") and track["isrc"] in existing_isrcs)
        ]
        missing = []
        for track in tracks:
            if track["id"] in planned_ids or (
                track.get("isrc") and track["isrc"] in planned_isrcs
            ):
                continue
            missing.append(track)
            planned_ids.add(track["id"])
            if track.get("isrc"):
                planned_isrcs.add(track["isrc"])
        if present and len(present) != len(tracks):
            if allow_unanchored_prepend and index == 0:
                partial_prepend_ids.extend(track["id"] for track in missing)
                present_episodes.append(index)
                continue
            raise RuntimeError(
                f"Episode {report['start_time']} is only partly present in {name!r}; "
                "refusing an ambiguous insertion."
            )
        if present:
            present_episodes.append(index)
        elif missing:
            missing_by_episode[index] = [track["id"] for track in missing]

    if not playlist_exists:
        return [], [
            track_id
            for index in sorted(missing_by_episode)
            for track_id in missing_by_episode[index]
        ], matched_count
    if not present_episodes:
        if not allow_unanchored_prepend and missing_by_episode:
            raise RuntimeError(
                f"No selected episode is already present in {name!r}; "
                "refusing an ambiguous insertion."
            )
        return [
            track_id
            for index in sorted(missing_by_episode)
            for track_id in missing_by_episode[index]
        ], [], matched_count

    first_present = min(present_episodes)
    last_present = max(present_episodes)
    middle = [
        index
        for index in missing_by_episode
        if first_present < index < last_present
    ]
    if middle:
        starts = ", ".join(year_reports[index]["start_time"] for index in middle)
        raise RuntimeError(
            f"Episodes {starts} belong in the middle of {name!r}; "
            "refusing to reorder the playlist automatically."
        )

    prepend_ids = partial_prepend_ids + [
        track_id
        for index in sorted(missing_by_episode)
        if index < first_present
        for track_id in missing_by_episode[index]
    ]
    append_ids = [
        track_id
        for index in sorted(missing_by_episode)
        if index > last_present
        for track_id in missing_by_episode[index]
    ]
    return prepend_ids, append_ids, matched_count


def update_playlists(
    session: tidalapi.Session,
    program: dict[str, Any],
    episode_reports: list[dict[str, Any]],
    *,
    write: bool,
    allow_unanchored_prepend: bool,
    episode_duplicates: bool = False,
) -> list[dict[str, Any]]:
    """Plan or apply yearly playlist changes while preserving episode order."""
    if episode_duplicates:
        if len(episode_reports) != 1:
            raise ValueError("episode duplicates require exactly one latest episode")
        return [
            update_latest_episode_playlist(
                session,
                program,
                episode_reports[0],
                write=write,
            )
        ]

    years = dict.fromkeys(report["year"] for report in episode_reports)
    results: list[dict[str, Any]] = []

    for year in years:
        name = playlist_name(program, year)
        match = find_user_playlist_by_name(session, name)
        playlist = session.playlist(playlist_id(match)) if match else None
        existing_tracks = get_playlist_tracks(playlist) if playlist else []
        existing_ids = {track.id for track in existing_tracks}
        existing_isrcs = {
            track.isrc for track in existing_tracks if getattr(track, "isrc", None)
        }
        existing_count = playlist.num_tracks if playlist else 0
        year_reports = [report for report in episode_reports if report["year"] == year]
        prepend_ids, append_ids, matched_count = plan_playlist_insertions(
            existing_ids,
            year_reports,
            playlist is not None,
            name,
            existing_isrcs=existing_isrcs,
            allow_unanchored_prepend=allow_unanchored_prepend,
        )

        requested_ids = prepend_ids + append_ids
        accepted_ids: list[int] = []
        actions: list[str] = []
        if requested_ids:
            if playlist is None:
                actions.append("create" if write else "would-create")
                if write:
                    playlist = session.user.create_playlist(
                        name,
                        f"KEXP {program['name']} episodes from {year}, newest first.",
                    )
                    accepted_ids.extend(
                        add_tracks_to_playlist(session, playlist.id, append_ids)
                    )
            else:
                for label, track_ids, position in (
                    ("prepend", prepend_ids, 0),
                    ("append", append_ids, -1),
                ):
                    if not track_ids:
                        continue
                    actions.append(label if write else f"would-{label}")
                    if write:
                        accepted_ids.extend(
                            add_tracks_to_playlist(
                                session,
                                playlist.id,
                                track_ids,
                                position=position,
                            )
                        )

        result = {
            "year": year,
            "name": name,
            "playlist_id": getattr(playlist, "id", None),
            "action": "+".join(actions) or "noop",
            "existing_track_count": existing_count,
            "duplicate_track_count": matched_count - len(requested_ids),
            "requested_track_count": len(requested_ids),
            "accepted_track_count": len(accepted_ids) if write else None,
        }
        if write and len(accepted_ids) != len(requested_ids):
            result["warning"] = (
                f"TIDAL accepted {len(accepted_ids)} of {len(requested_ids)} requested tracks."
            )
        if write and playlist:
            result["final_track_count"] = session.playlist(playlist.id).num_tracks
        results.append(result)

    return results


def run_self_check() -> None:
    """Check grouping and setlist extraction against recorded response shapes."""
    global MATCH_CACHE_FILE, MATCH_CACHE_LOCK, SYNC_STATE_FILE, SYNC_STATE_LOCK, _MATCH_CACHE

    shows = [
        {"id": 10, "program": 7, "start_time": "2026-01-03T08:00:00-08:00"},
        {"id": 11, "program": 7, "start_time": "2026-01-03T08:00:00-08:00"},
        {"id": 12, "program": 7, "start_time": "2026-01-03T12:00:00-08:00"},
        {"id": 13, "program": 8, "start_time": "2026-01-03T08:00:00-08:00"},
    ]
    episodes = group_episodes(shows, 7)
    assert [episode.show_ids for episode in episodes] == [{12}, {10, 11}]

    plays = [
        {
            "id": 1,
            "airdate": "2026-01-03T08:02:00-08:00",
            "show": 10,
            "artist": "First Artist",
            "song": "First Song",
            "play_type": "trackplay",
        },
        {
            "id": 2,
            "airdate": "2026-01-03T08:03:00-08:00",
            "show": 10,
            "play_type": "airbreak",
        },
        {
            "id": 3,
            "airdate": "2026-01-03T08:04:00-08:00",
            "show": 11,
            "artist": "Second Artist",
            "song": "Second Song",
            "play_type": "trackplay",
        },
        {
            "id": 4,
            "airdate": "2026-01-03T08:05:00-08:00",
            "show": 11,
            "artist": "First Artist",
            "song": "First Song",
            "play_type": "trackplay",
        },
        {
            "id": 5,
            "airdate": "2026-01-03T08:06:00-08:00",
            "show": 13,
            "artist": "Wrong Program",
            "song": "Wrong Song",
            "play_type": "trackplay",
        },
    ]
    setlist = extract_setlist(episodes[1], plays)
    assert [(play["artist"], play["song"]) for play in setlist] == [
        ("First Artist", "First Song"),
        ("Second Artist", "Second Song"),
    ]
    assert normalize_match_text("Song (Live)") == "song"
    assert normalize_match_text("Song (Theme)") == "song theme"
    assert normalize_match_text("MonteViso - Dalila Remox") == "monteviso"
    assert normalize_match_text(
        "if you wanna party (Eli Escobar remix)"
    ) == "if you wanna party"
    assert normalize_match_text('"ME PORTO BONITO (POST-PUNK) COVER"') == "me porto bonito"
    assert normalize_match_text("Song (Olive Branch)") == "song olive branch"
    assert normalize_match_text("Song (Premixed Feelings)") == "song premixed feelings"
    assert normalize_match_text("Under Cover") == "under cover"
    assert "remix" not in version_qualifiers("mix pa llorar en tu cuarto")
    assert normalize_words("Estacion Sub_Tropico") == "estacion sub tropico"
    assert normalize_artist_alias("Las Ultrasonicas") == "ultrasonicas"
    assert normalize_artist_alias("Isidro Cuevas and Willy Cabanas") == (
        "isidro cuevas willy cabanas"
    )
    assert normalize_artist_alias("The The") == "the the"
    assert normalize_artist_alias("And One") == "and one"
    assert normalize_artist_alias("Nusar 3000") == "nusar3000"
    assert normalize_words('"ACCIÓN"') == "accion"
    assert normalize_words("東京")
    assert all(ord(character) < 128 for character in normalize_words("東京"))

    def fake_track(
        track_id,
        title,
        artists,
        duration=180,
        album=None,
        version=None,
        isrc=None,
    ):
        artist_objects = [SimpleNamespace(name=name) for name in artists]
        return SimpleNamespace(
            id=track_id,
            name=title,
            artist=artist_objects[0],
            artists=artist_objects,
            album=SimpleNamespace(name=album) if album else None,
            version=version,
            duration=duration,
            isrc=isrc,
        )

    exact_identifier = fake_track(35, "Exact Recording", ["Exact Artist"])
    previous_cache = _MATCH_CACHE
    _MATCH_CACHE = {"musicbrainz_isrcs": {"recording": ["EXACT-ISRC"]}}
    exact_session = SimpleNamespace(
        get_tracks_by_isrc=lambda isrc: [exact_identifier] if isrc == "EXACT-ISRC" else []
    )
    assert match_recording_id(exact_session, "recording").id == 35
    _MATCH_CACHE = previous_cache

    previous_cache_file = MATCH_CACHE_FILE
    previous_cache_lock = MATCH_CACHE_LOCK
    previous_sync_file = SYNC_STATE_FILE
    previous_sync_lock = SYNC_STATE_LOCK
    with TemporaryDirectory() as directory:
        MATCH_CACHE_FILE = Path(directory) / "cache.json"
        MATCH_CACHE_LOCK = Path(f"{MATCH_CACHE_FILE}.lock")
        write_match_cache({"musicbrainz_isrcs": {"valid": ["VALID-ISRC"]}})
        assert read_match_cache()["musicbrainz_isrcs"]["valid"] == ["VALID-ISRC"]
        MATCH_CACHE_FILE.write_text("{")
        assert read_match_cache() == {"musicbrainz_isrcs": {}}

        SYNC_STATE_FILE = Path(directory) / "state.json"
        SYNC_STATE_LOCK = Path(f"{SYNC_STATE_FILE}.lock")
        sync_state = {
            "playlists": {
                "playlist": {
                    "playlist_id": "playlist-id",
                    "episodes": {
                        "episode": {
                            "recorded": ["isrc:EXACT-ISRC"],
                            "pending": None,
                        }
                    },
                }
            }
        }
        write_sync_state(sync_state)
        assert read_sync_state() == sync_state
        SYNC_STATE_FILE.write_text("{")
        try:
            read_sync_state()
        except RuntimeError:
            pass
        else:
            raise AssertionError("invalid sync state must fail closed")
    MATCH_CACHE_FILE = previous_cache_file
    MATCH_CACHE_LOCK = previous_cache_lock
    SYNC_STATE_FILE = previous_sync_file
    SYNC_STATE_LOCK = previous_sync_lock

    pending = {
        "tracks": [
            {"id": 1, "identity": "isrc:ONE"},
            {"id": 2, "identity": "isrc:TWO"},
        ],
        "before_count": 2,
        "before_top_ids": [9, 8],
    }
    assert reconcile_pending_ids(pending, [9, 8], 2) == set()
    assert reconcile_pending_ids(pending, [1, 2, 9, 8], 4) == {1, 2}
    assert reconcile_pending_ids(pending, [1, 9, 8], 3) == {1}
    try:
        reconcile_pending_ids(pending, [7, 9, 8], 3)
    except RuntimeError:
        pass
    else:
        raise AssertionError("unknown pending prefix must fail closed")

    solo = fake_track(1, "Mabuse", ["Los Punsetes"], 175)
    collaboration = fake_track(
        2,
        "Mabuse",
        ["Los Punsetes", "Las Ligas Menores"],
        176,
    )
    assert select_tidal_candidate(
        [solo, collaboration],
        "Los Punsetes & Las Ligas Menores",
        "Mabuse",
        allow_fuzzy_title=False,
    ).id == 2

    band = fake_track(7, "September", ["Earth, Wind & Fire"])
    fragment = fake_track(8, "September", ["Earth"])
    assert select_tidal_candidate(
        [fragment, band],
        "Earth, Wind & Fire",
        "September",
        allow_fuzzy_title=False,
    ).id == 7
    assert select_tidal_candidate(
        [fragment],
        "Earth, Wind & Fire",
        "September",
        allow_fuzzy_title=False,
    ) is None

    shortened_credit = fake_track(9, "PIZALE", ["SUSOBRINO", "Xiuhtezcatl"])
    assert select_tidal_candidate(
        [shortened_credit],
        "Susobrino, Xiuhtezcatl Martinez",
        "PIZALE",
        source_artist_count=2,
        allow_fuzzy_title=False,
    ).id == 9

    omitted_feature = fake_track(67, "Abrazame", ["Los Rakas"])
    assert select_tidal_candidate(
        [omitted_feature],
        "Los Rakas feat. Faviola",
        "Abrazame (Uproot Andy Remix)",
        allow_fuzzy_title=False,
    ).id == 67

    spanish_connector_match = fake_track(
        59,
        "SIGUEME",
        ["Xiuhtezcatl", "Renata Flores"],
    )
    assert select_tidal_candidate(
        [spanish_connector_match],
        "Xiuhtezcatl y Renata Flores",
        "SIGUEME",
        allow_fuzzy_title=False,
    ).id == 59

    connector_match = fake_track(
        10,
        "Mis Sentimientos",
        ["Los Angeles Azules", "Ximena Sarinana"],
        album="Como Te Voy a Olvidar",
    )
    assert select_tidal_candidate(
        [connector_match],
        "Los Angeles Azules con Ximena Sarinana",
        "Mis sentimientos",
        source_artist_count=2,
        source_album="Como te voy a olvidar",
        allow_fuzzy_title=False,
    ).id == 10

    partial_credit = fake_track(
        33,
        "Cebollas Verdes",
        ["Khruangbin"],
        album="Cebollas Verdes",
    )
    assert select_tidal_candidate(
        [partial_credit],
        "Khruangbin & Quantic",
        "Cebollas Verdes",
        source_artist_count=2,
        source_album="Cebollas Verdes",
        allow_fuzzy_title=False,
    ) is None

    expanded_title = fake_track(
        34,
        "HDA (Historia del Arte)",
        ["Las Bistecs"],
        album="Oferta",
    )
    assert select_tidal_candidate(
        [expanded_title],
        "Las Bistecs",
        "Historia del Arte",
        source_album="Oferta",
        allow_fuzzy_title=True,
    ).id == 34

    partial_artist_title = fake_track(
        36,
        "Basame Mucho (Dark Horse Remix)",
        ["Lisa Ono"],
        album="SOMNYAMA",
    )
    assert select_tidal_candidate(
        [partial_artist_title],
        "Dark Horse, Lisa Ono",
        "Besame Mucho (Dark Horse Remix)",
        source_artist_count=2,
        source_album="SOMNYAMA",
        allow_fuzzy_title=True,
    ) is None

    album_title_alias = fake_track(
        37,
        "Tu mi delirio (feat. Maraca)",
        ["Afro Cuban Jazz Project", "Maraca"],
        album="Descarga Uno (feat. Maraca)",
    )
    assert select_tidal_candidate(
        [album_title_alias],
        "Afro-Cuban Jazz Project",
        "Tu Mi Delirio (Bolero)",
        source_album="Descarga Uno",
        allow_fuzzy_title=True,
    ).id == 37

    multi_artist_typo = fake_track(
        54,
        "Extrano",
        ["Miranda!", "Santiago Motorizado"],
        album="Extrano",
    )
    assert select_tidal_candidate(
        [multi_artist_typo],
        "Miranda!, Santiago C. Motorizado",
        "Extrano",
        source_album="Extrano",
        allow_fuzzy_title=False,
        allow_fuzzy_artist=True,
    ).id == 54

    artist_typo = fake_track(11, "Wey", ["Luisa Almaguer"], album="Weyes")
    assert select_tidal_candidate(
        [artist_typo],
        "Luisa Amalguer",
        "Wey",
        source_album="Weyes",
        allow_fuzzy_title=False,
        allow_fuzzy_artist=True,
    ).id == 11
    artist_typo_no_album = fake_track(
        48,
        "La Nueva Montana",
        ["Tigre Ulli"],
    )
    assert select_tidal_candidate(
        [artist_typo_no_album],
        "Tigre Uili",
        "La Nueva Montana",
        allow_fuzzy_title=False,
        allow_fuzzy_artist=True,
    ).id == 48
    acronym_artist = fake_track(
        56,
        "Threshold",
        ["SDH Semiotics Department of Heteronyms"],
    )
    assert select_tidal_candidate(
        [acronym_artist],
        "SDH",
        "Threshold",
        allow_fuzzy_title=False,
        allow_fuzzy_artist=True,
    ).id == 56
    artist_typo_with_album = fake_track(
        53,
        "Djabe (feat. Melanie)",
        ["Ghetto Kumbe"],
        album="Ghetto Kumbe",
    )
    assert select_tidal_candidate(
        [artist_typo_with_album],
        "Guettho Kumbe",
        "Djabe",
        source_album="Guettho Kumbe",
        allow_fuzzy_title=False,
        allow_fuzzy_artist=True,
    ).id == 53
    assert select_tidal_candidate(
        [
            fake_track(28, "Exact Song", ["Example Artost"], album="Album"),
            fake_track(29, "Exact Song", ["Example Artust"], album="Album"),
        ],
        "Example Artist",
        "Exact Song",
        source_album="Album",
        allow_fuzzy_title=False,
        allow_fuzzy_artist=True,
    ).id == 28
    assert album_match_score("I", fake_track(30, "Song", ["Artist"], album="Live in Paris")) == 0.0
    assert album_match_score("I", fake_track(31, "Song", ["Artist"], album="I")) == 1.0

    title_extension = fake_track(
        50,
        "Let's Make Love And Listen To Death From Above",
        ["CSS"],
    )
    assert select_tidal_candidate(
        [title_extension],
        "CSS",
        "Let's Make Love And Listen To",
        allow_fuzzy_title=True,
    ).id == 50
    dropped_parenthetical = fake_track(61, "Caramegau", ["Pahua"])
    assert select_tidal_candidate(
        [dropped_parenthetical],
        "Pahua",
        "Caramegau (Simglish)",
        allow_fuzzy_title=True,
    ).id == 61

    embedded_title = fake_track(
        68,
        "Metro Balderas (Estacion del metro Balderas)",
        ["Rodrigo Gonzalez"],
    )
    assert select_tidal_candidate(
        [embedded_title],
        "Rodrigo Gonzalez",
        'Estacion Del Metro Balderas"',
        allow_fuzzy_title=True,
    ).id == 68

    parenthetical_title = fake_track(
        55,
        "La Nina del Volcan",
        ["SBM", "YoSoyMatt"],
    )
    assert select_tidal_candidate(
        [parenthetical_title],
        "SBM",
        "Volcano (La Nina del Volcan)",
        allow_fuzzy_title=True,
    ).id == 55

    compact_title = fake_track(65, "Acapulco '78", ["Fase"])
    assert select_tidal_candidate(
        [compact_title],
        "Fase",
        "Acapulco78",
        allow_fuzzy_title=True,
    ).id == 65

    remix_with_all_artists = fake_track(
        66,
        "Soy Yo (feat. Doozie & MOJJO) (Doozie & MOJJO Remix)",
        ["Bomba Estereo", "Doozie", "MOJJO"],
    )
    assert select_tidal_candidate(
        [remix_with_all_artists],
        "Bomba Estereo, Doozie, Mojjo",
        "Soy yo",
        allow_fuzzy_title=False,
    ).id == 66

    stylized_title = fake_track(60, "DES0KUPA", ["LUCY"])
    assert select_tidal_candidate(
        [stylized_title],
        "LUCY",
        "DESOKUPA",
        allow_fuzzy_title=True,
    ).id == 60

    fuzzy = fake_track(3, "obsessed with you", ["GAZZI"], 196)
    fuzzy_title_no_album = fake_track(
        49,
        "Sabor de la Cumbia",
        ["Philthy Dronez"],
    )
    assert select_tidal_candidate(
        [fuzzy_title_no_album],
        "Philthy Dronez",
        "Sabor de cumbia",
        allow_fuzzy_title=True,
    ).id == 49
    assert select_tidal_candidate(
        [fuzzy],
        "GAZZI",
        "obssed with you",
        allow_fuzzy_title=False,
    ) is None
    assert select_tidal_candidate(
        [fuzzy],
        "GAZZI",
        "obssed with you",
        allow_fuzzy_title=True,
    ).id == 3

    studio = fake_track(
        12,
        "Bulls on Parade",
        ["Rage Against the Machine"],
        229,
        "Evil Empire",
    )
    live = fake_track(
        13,
        "Bulls on Parade",
        ["Rage Against the Machine"],
        317,
        "Live at the Grand Olympic Auditorium",
    )
    assert select_tidal_candidate(
        [live, studio],
        "Rage Against the Machine",
        "Bulls on Parade",
        source_album="Evil Empire",
        allow_fuzzy_title=False,
    ).id == 12
    assert select_tidal_candidate(
        [live],
        "Rage Against the Machine",
        "Bulls on Parade",
        source_album="Evil Empire",
        allow_fuzzy_title=False,
    ) is None
    remix_only = fake_track(
        32,
        "Exact Song",
        ["Exact Artist"],
        album="Exact Song Remixes",
    )
    assert select_tidal_candidate(
        [remix_only],
        "Exact Artist",
        "Exact Song",
        source_album="Exact Song",
        allow_fuzzy_title=False,
    ) is None

    luna_studio = fake_track(14, "Luna", ["Zoe"], 227, "Reptilectric")
    luna_live = fake_track(
        15,
        "Luna",
        ["Zoe"],
        280,
        "MTV Unplugged Musica de Fondo (Reissue/Live)",
    )
    assert select_tidal_candidate(
        [luna_studio, luna_live],
        "Zoe",
        "Luna (Live)",
        source_album="MTV Unplugged: Musica de fondo",
        allow_fuzzy_title=False,
    ).id == 15

    ranked = [
        fake_track(16, "Persiana Americana", ["Soda Stereo"], 292, "Hits"),
        fake_track(17, "Persiana Americana", ["Soda Stereo"], 293, "Collection"),
    ]
    assert select_tidal_candidate(
        ranked,
        "Soda Stereo",
        "Persiana americana",
        source_album="Obras cumbres",
        allow_fuzzy_title=False,
    ).id == 16

    rubio_studio = fake_track(18, "IR", ["Rubio"], 273, "Mango Negro")
    rubio_live = fake_track(19, "IR", ["Rubio"], 307, "En Vivo")
    assert select_tidal_candidate(
        [rubio_studio, rubio_live],
        "Rubio",
        "IR",
        source_album="Live on KEXP",
        source_is_live=True,
        allow_fuzzy_title=False,
    ).id == 18
    remix_base = fake_track(42, "Exact Song", ["Exact Artist"], album="Original")
    assert select_tidal_candidate(
        [remix_base],
        "Exact Artist",
        "Exact Song (Remix)",
        source_album="Original",
        allow_fuzzy_title=False,
    ).id == 42
    assert select_tidal_candidate(
        [remix_base],
        "Exact Artist",
        "Exact Song (Acoustic)",
        source_album="Original",
        allow_fuzzy_title=False,
    ) is None
    assert select_tidal_candidate(
        [remix_base],
        "Exact Artist",
        "Exact Song (Instrumental)",
        source_album="Original",
        allow_fuzzy_title=False,
    ) is None

    # Solo credit must beat a same-title collaboration superset (Broke Carrey).
    solo_exact = fake_track(20, "MIGUELITO", ["Broke Carrey"], 148)
    collab_superset = fake_track(21, "MIGUELITO", ["Broke Carrey", "trouve feraud"], 150)
    assert select_tidal_candidate(
        [solo_exact, collab_superset],
        "Broke Carrey",
        "Miguelito",
        allow_fuzzy_title=False,
    ).id == 20
    assert select_tidal_candidate(
        [collab_superset, solo_exact],
        "Broke Carrey",
        "Miguelito",
        allow_fuzzy_title=False,
    ).id == 20

    fuzzy_solo = fake_track(
        69,
        "La Pollera Amarilla",
        ['Gladys "La bomba tucumana"'],
        album="La Pollera Amarilla",
    )
    fuzzy_collaboration = fake_track(
        70,
        "La Pollera Amarilla",
        ['Gladys "La bomba tucumana"', "Belen Gal"],
        album="La Pollera Amarilla",
    )
    assert select_tidal_candidate(
        [fuzzy_solo, fuzzy_collaboration],
        "Gladys La Bomba",
        "La Pollera Amarilla",
        source_album="La Pollera Amarilla",
        allow_fuzzy_title=False,
        allow_fuzzy_artist=True,
    ).id == 69

    # Same shape with a punctuated band name (Miranda!).
    miranda_solo = fake_track(22, "Traición", ["Miranda!"], 182)
    miranda_collab = fake_track(
        23,
        "Traición",
        ["Miranda!", "Emmanuel Horvilleur", "Juan Ingaramo"],
        190,
    )
    assert select_tidal_candidate(
        [miranda_solo, miranda_collab],
        "Miranda!",
        "Traición",
        allow_fuzzy_title=False,
    ).id == 22

    near_duplicate_releases = [
        fake_track(38, "Same Recording", ["Solo Artist"], 180),
        fake_track(39, "Same Recording", ["Solo Artist"], 182),
    ]
    assert select_tidal_candidate(
        near_duplicate_releases,
        "Solo Artist",
        "Same Recording",
        allow_fuzzy_title=False,
    ).id == 38
    fuzzy_same_title_releases = [
        fake_track(62, "Lamento en la Selva", ["Los Mirlos"], 189),
        fake_track(63, "Lamento en la Selva", ["Los Mirlos"], 187),
    ]
    assert select_tidal_candidate(
        fuzzy_same_title_releases,
        "Los Mirlos",
        "Lamento de la selva",
        allow_fuzzy_title=True,
    ).id == 62

    fuzzy_duration_tie = [
        fake_track(40, "A sufficiently long title X", ["Solo Artist"], 180),
        fake_track(41, "A sufficiently long title Y", ["Solo Artist"], 182),
    ]
    assert select_tidal_candidate(
        fuzzy_duration_tie,
        "Solo Artist",
        "A sufficiently long title",
        allow_fuzzy_title=True,
    ).id == 40

    partial_credit_tie = [
        fake_track(
            57,
            "Shared Song",
            ["Artist One", "Guest A"],
            album="Shared Album",
        ),
        fake_track(
            58,
            "Shared Song",
            ["Artist One", "Guest B"],
            album="Shared Album",
        ),
    ]
    assert select_tidal_candidate(
        partial_credit_tie,
        "Artist One & Artist Two",
        "Shared Song",
        source_artist_count=2,
        source_album="Shared Album",
        allow_fuzzy_title=False,
    ).id == 57

    same_isrc_conflict = [
        fake_track(
            51,
            "Un Poco Mas De Amor",
            ["Jiony", "Karen y Los Remedios"],
            isrc="SAME-ISRC",
        ),
        fake_track(
            52,
            "Un Poco Mas De Amor",
            ["Jiony", "Ana Karen Barajas", "Karen y Los Remedios"],
            isrc="SAME-ISRC",
        ),
    ]
    assert select_tidal_candidate(
        same_isrc_conflict,
        "Jiony Ft. Karen y Los Remedios",
        "Un Poco Mas De Amor",
        allow_fuzzy_title=False,
    ).id == 51

    # Exact full artist and title may use Tidal rank when any version is acceptable.
    assert select_tidal_candidate(
        [
            fake_track(24, "Twin Recording", ["Solo Artist"], 180),
            fake_track(25, "Twin Recording", ["Solo Artist"], 240),
        ],
        "Solo Artist",
        "Twin Recording",
        allow_fuzzy_title=False,
    ).id == 24

    # A genuine multi-artist source credit must not be hijacked by the new tier.
    assert select_tidal_candidate(
        [
            fake_track(26, "Split Credit", ["Artist One"], 180),
            fake_track(27, "Split Credit", ["Artist One", "Artist Two"], 181),
        ],
        "Artist One & Artist Two",
        "Split Credit",
        allow_fuzzy_title=False,
    ).id == 27

    ambiguous_title = "a sufficiently long title"
    ambiguous_tracks = [
        fake_track(4, ambiguous_title, ["Artist One", "Artist Two"], 180),
        fake_track(5, ambiguous_title, ["Artist One", "Artist Two"], 240),
    ]
    assert select_tidal_candidate(
        ambiguous_tracks,
        "Artist One & Artist Two",
        ambiguous_title,
        allow_fuzzy_title=False,
    ).id == 4

    fallback = fake_track(6, "Fallback Song", ["First Artist", "Second Artist"])
    fallback_one = fake_track(43, "Top One", ["Artist One"])
    fallback_two = fake_track(44, "Top Two", ["Artist Two"])
    artist_one = SimpleNamespace(
        id=101,
        name="Artist One",
        get_top_tracks=lambda limit: [fallback_one],
    )
    artist_two = SimpleNamespace(
        id=102,
        name="Artist Two",
        get_top_tracks=lambda limit: [fallback_two],
    )

    class ArtistFallbackSession:
        def search(self, query, models, limit):
            return {
                "artists": {
                    "Artist One": [artist_one],
                    "Artist Two": [artist_two],
                }.get(query, [])
            }

    artist_fallbacks = get_artist_fallbacks(
        ArtistFallbackSession(),
        {
            "artist": "Artist One & Artist Two",
            "artist_ids": ["one", "two"],
            "song": "Missing Song",
        },
    )
    assert [track["id"] for track in artist_fallbacks] == [43, 44]

    class BandFallbackSession(ArtistFallbackSession):
        def search(self, query, models, limit):
            return {
                "artists": {
                    "Earth": [SimpleNamespace(id=103, name="Earth")],
                    "Wind": [SimpleNamespace(id=104, name="Wind")],
                    "Fire": [SimpleNamespace(id=105, name="Fire")],
                    "Brio": [SimpleNamespace(id=106, name="Brio")],
                    "Confidence": [SimpleNamespace(id=107, name="Confidence")],
                    "Mexicans": [SimpleNamespace(id=108, name="Mexicans")],
                    "Guns": [SimpleNamespace(id=109, name="Guns")],
                }.get(query, [])
            }

    assert get_artist_fallbacks(
        BandFallbackSession(),
        {
            "artist": "Earth, Wind & Fire",
            "artist_ids": ["band"],
            "song": "Missing Song",
        },
    ) == []
    for band in ("Con Brio", "With Confidence", "Mexicans With Guns"):
        assert get_artist_fallbacks(
            BandFallbackSession(),
            {"artist": band, "artist_ids": ["band"], "song": "Missing Song"},
        ) == []

    class FakeSession:
        def __init__(self):
            self.queries = []

        def search(self, query, models, limit):
            self.queries.append(query)
            return {
                "tracks": [fallback]
                if query == "First Artist fallback song"
                else []
            }

    fake_session = FakeSession()
    assert match_tidal_track(
        fake_session,
        {
            "artist": "First Artist, Second Artist",
            "artist_ids": ["first", "second"],
            "song": "Fallback Song",
        },
    ).id == 6
    assert "First Artist fallback song" in fake_session.queries

    class TitleSession(FakeSession):
        def search(self, query, models, limit):
            self.queries.append(query)
            return {"tracks": [fallback] if query == "Fallback Song" else []}

    title_session = TitleSession()
    assert match_tidal_track(
        title_session,
        {
            "artist": "First Artist, Second Artist",
            "artist_ids": ["first", "second"],
            "song": "Fallback Song",
        },
    ).id == 6
    assert "Fallback Song" in title_session.queries

    class AlbumSession(FakeSession):
        def search(self, query, models, limit):
            self.queries.append(query)
            return {"tracks": [fallback] if query == "Album fallback song" else []}

    album_session = AlbumSession()
    assert match_tidal_track(
        album_session,
        {
            "artist": "First Artist, Second Artist",
            "artist_ids": ["first", "second"],
            "song": "Fallback Song",
            "album": "Album",
        },
    ).id == 6
    assert "Album fallback song" in album_session.queries

    compact_artist_track = fake_track(64, "MOTA", ["nusar3000"])

    class CompactArtistSession(FakeSession):
        def search(self, query, models, limit):
            self.queries.append(query)
            return {"tracks": [compact_artist_track] if query == "nusar3000 mota" else []}

    compact_session = CompactArtistSession()
    assert match_tidal_track(
        compact_session,
        {"artist": "Nusar 3000", "song": "MOTA"},
    ).id == 64
    assert "nusar3000 mota" in compact_session.queries

    class TitleVariantSession(FakeSession):
        def search(self, query, models, limit):
            self.queries.append(query)
            return {"tracks": []}

    variant_session = TitleVariantSession()
    assert match_tidal_track(
        variant_session,
        {"artist": "Some Artist", "song": "\u00bfY SI DESCANSAS?"},
    ) is None
    assert "\u00bfY SI DESCANSAS?" in variant_session.queries
    assert "?Y SI DESCANSAS?" in variant_session.queries
    assert "y si descansas" in variant_session.queries

    assert select_tidal_candidate(
        [fake_track(65, "Bajo De La Piel", ["Sofia"], album="La Vida Era Mas Corta")],
        "Sofia",
        "Bajo La Piel",
        source_album="La Vida era mas corta",
        allow_fuzzy_title=True,
    ).id == 65

    fuzzy_tie_tracks = [
        fake_track(46, "Exact Song", ["Example Artost"], album="Album"),
        fake_track(47, "Exact Song", ["Example Artust"], album="Album"),
    ]

    class FuzzyTieSession:
        def search(self, query, models, limit):
            return {"tracks": fuzzy_tie_tracks}

    assert match_tidal_track(
        FuzzyTieSession(),
        {"artist": "Example Artist", "song": "Exact Song", "album": "Album"},
    ).id == 46

    one_shot_playlist = SimpleNamespace(
        tracks_paginated=lambda: iter(
            [SimpleNamespace(id=40, isrc="FIRST"), SimpleNamespace(id=41, isrc="SECOND")]
        )
    )
    materialized_tracks = get_playlist_tracks(one_shot_playlist)
    assert {track.id for track in materialized_tracks} == {40, 41}
    assert {track.isrc for track in materialized_tracks} == {"FIRST", "SECOND"}

    reports = [
        {"start_time": "new", "matched": [{"id": 1}]},
        {"start_time": "old", "matched": [{"id": 2}]},
    ]
    assert plan_playlist_insertions(
        set(), reports, False, "playlist", allow_unanchored_prepend=False
    )[:2] == ([], [1, 2])
    fallback_reports = [
        {
            "start_time": "fallback",
            "matched": [],
            "fallbacks": [{"id": 45, "isrc": "FALLBACK"}],
        }
    ]
    assert plan_playlist_insertions(
        set(), fallback_reports, False, "playlist", allow_unanchored_prepend=False
    )[:2] == ([], [45])
    assert plan_playlist_insertions(
        {2}, reports, True, "playlist", allow_unanchored_prepend=False
    )[:2] == ([1], [])
    assert plan_playlist_insertions(
        {1}, reports, True, "playlist", allow_unanchored_prepend=False
    )[:2] == ([], [2])
    assert plan_playlist_insertions(
        set(), reports, True, "playlist", allow_unanchored_prepend=True
    )[:2] == ([1, 2], [])

    partial_latest = [
        {"start_time": "latest", "matched": [{"id": 1}, {"id": 3}]}
    ]
    assert plan_playlist_insertions(
        {1},
        partial_latest,
        True,
        "playlist",
        allow_unanchored_prepend=True,
    )[:2] == ([3], [])
    try:
        plan_playlist_insertions(
            {1},
            partial_latest,
            True,
            "playlist",
            allow_unanchored_prepend=False,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("named partial episode must be refused")

    historical_partial = [
        {"start_time": "new", "matched": [{"id": 1}]},
        {"start_time": "old", "matched": [{"id": 2}, {"id": 3}]},
    ]
    try:
        plan_playlist_insertions(
            {1, 2},
            historical_partial,
            True,
            "playlist",
            allow_unanchored_prepend=True,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("historical partial episode must be refused")

    isrc_report = [
        {"start_time": "same recording", "matched": [{"id": 9, "isrc": "SAME"}]}
    ]
    assert plan_playlist_insertions(
        {8},
        isrc_report,
        True,
        "playlist",
        existing_isrcs={"SAME"},
        allow_unanchored_prepend=False,
    )[:2] == ([], [])

    repeated_isrc_reports = [
        {"start_time": "new", "matched": [{"id": 10, "isrc": "REPEAT"}]},
        {"start_time": "old", "matched": [{"id": 11, "isrc": "REPEAT"}]},
    ]
    assert plan_playlist_insertions(
        set(),
        repeated_isrc_reports,
        False,
        "playlist",
        allow_unanchored_prepend=False,
    )[:2] == ([], [10])

    same_episode_isrc = [
        {
            "start_time": "new",
            "matched": [
                {"id": 12, "isrc": "ONE-RECORDING"},
                {"id": 13, "isrc": "ONE-RECORDING"},
            ],
        }
    ]
    assert plan_playlist_insertions(
        set(),
        same_episode_isrc,
        False,
        "playlist",
        allow_unanchored_prepend=False,
    )[:2] == ([], [12])

    try:
        plan_playlist_insertions(
            set(), reports, True, "playlist", allow_unanchored_prepend=False
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("unanchored named insertion must be refused")

    middle_reports = [
        {"start_time": "new", "matched": [{"id": 1}]},
        {"start_time": "middle", "matched": [{"id": 2}]},
        {"start_time": "old", "matched": [{"id": 3}]},
    ]
    try:
        plan_playlist_insertions(
            {1, 3},
            middle_reports,
            True,
            "playlist",
            allow_unanchored_prepend=False,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("middle insertion must be refused")


def print_human(result: dict[str, Any]) -> None:
    """Print a concise human-readable sync report."""
    print(f"Mode: {result['mode']}")
    print(f"Program: {result['program']['name']} ({result['program']['id']})")
    for episode in result["episodes"]:
        print(f"Episode: {episode['start_time']}")
        print(f"  Aired: {episode['aired_count']}")
        print(f"  Matched: {episode['matched_count']}")
        print(f"  Artist fallbacks: {episode['fallback_count']}")
        print(f"  Unmatched: {len(episode['unmatched'])}")
        if episode["unmatched"]:
            print(
                f"Warning: {len(episode['unmatched'])} unmatched songs for "
                f"{episode['start_time']}.",
                file=sys.stderr,
            )
        for track in episode["unmatched"]:
            print(f"    {track['artist']} - {track['song']}")
        for fallback in episode["fallbacks"]:
            print(
                f"    Fallback: {fallback['kexp_artist']} - {fallback['kexp_song']} -> "
                f"{fallback['fallback_artist']} - {fallback['song']}"
            )
    for playlist in result["playlists"]:
        print(f"Playlist: {playlist['name']}")
        print(f"  Action: {playlist['action']}")
        print(f"  Existing tracks: {playlist['existing_track_count']}")
        print(f"  Duplicates skipped: {playlist['duplicate_track_count']}")
        print(f"  Tracks requested: {playlist['requested_track_count']}")
        if playlist["accepted_track_count"] is not None:
            print(f"  Tracks accepted: {playlist['accepted_track_count']}")
        if "warning" in playlist:
            print(f"  Warning: {playlist['warning']}", file=sys.stderr)
    if result["mode"] == "preview":
        print("Preview only. Re-run with --write to create or modify playlists.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("program", nargs="?", help="KEXP program id or name")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--episodes", type=int, default=1, help="number of recent episodes")
    selection.add_argument("--episode", help="one episode as an ISO date or timestamp")
    parser.add_argument("--list-programs", action="store_true", help="list active KEXP programs")
    parser.add_argument("--write", action="store_true", help="create or modify TIDAL playlists")
    parser.add_argument(
        "--artist-fallback",
        action="store_true",
        help="use one top track per resolved artist for genuine song non-finds",
    )
    parser.add_argument(
        "--episode-duplicates",
        action="store_true",
        help="preserve cross-episode repeats using local episode state",
    )
    parser.add_argument(
        "--seed-episode-state",
        action="store_true",
        help="record an already-present latest episode without changing Tidal",
    )
    parser.add_argument("--json", action="store_true", help="print JSON output")
    parser.add_argument("--self-check", action="store_true", help="run the offline parser check")
    args = parser.parse_args()

    if args.self_check:
        run_self_check()
        print("Self-check passed.")
        return 0
    if (args.episode_duplicates or args.seed_episode_state) and (
        args.episode or args.episodes != 1
    ):
        parser.error("episode duplicate state supports only the latest episode")
    if args.seed_episode_state and args.write:
        parser.error("--seed-episode-state cannot be combined with --write")

    programs = list_programs()
    if args.list_programs:
        if args.json:
            print(json.dumps({"ok": True, "programs": programs}, ensure_ascii=False, indent=2))
        else:
            for program in programs:
                print(f"{program['id']:>3}  {program['name']}")
        return 0
    if not args.program:
        parser.error("program is required unless --list-programs or --self-check is used")

    program = resolve_program(args.program, programs)
    episodes = (
        [named_episode(program["id"], args.episode)]
        if args.episode
        else recent_episodes(program["id"], args.episodes)
    )
    session = get_session()
    episode_reports = build_episode_reports(
        session,
        episodes,
        artist_fallback=args.artist_fallback,
    )
    if args.seed_episode_state:
        seeded = seed_episode_state(session, program, episode_reports[0])
        result = {"ok": True, "mode": "seed-episode-state", "seeded": seeded}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(
                f"Seeded {seeded['recorded_track_count']} tracks for "
                f"{seeded['episode']} in {seeded['playlist']}."
            )
        return 0

    playlist_reports = update_playlists(
        session,
        program,
        episode_reports,
        write=args.write,
        allow_unanchored_prepend=args.episode is None,
        episode_duplicates=args.episode_duplicates,
    )
    warnings = [
        f"{report['start_time']}: {len(report['unmatched'])} unmatched songs"
        for report in episode_reports
        if report["unmatched"]
    ]
    warnings.extend(
        f"{report['start_time']}: {len(report['fallbacks'])} artist fallback tracks"
        for report in episode_reports
        if report["fallbacks"]
    )
    warnings.extend(
        playlist["warning"] for playlist in playlist_reports if "warning" in playlist
    )
    result = {
        "ok": True,
        "mode": "write" if args.write else "preview",
        "program": {"id": program["id"], "name": program["name"]},
        "episodes": episode_reports,
        "playlists": playlist_reports,
        "warnings": warnings,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_human(result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
