"""Shared TIDAL playlist operations."""

from __future__ import annotations

import time
from functools import partial
from pathlib import Path
from typing import Any

import tidalapi

SESSION_FILE = Path(__file__).resolve().parent.parent / ".tidal-session.json"


def get_session(session_file: Path = SESSION_FILE) -> tidalapi.Session:
    """Load and validate the saved TIDAL session."""
    session = tidalapi.Session()
    session.request_session.request = partial(session.request_session.request, timeout=30)
    if session_file.exists():
        session.login_session_file(session_file, do_pkce=True)
    if not session.check_login():
        raise RuntimeError(f"Not logged in. Expected session file at {session_file}")
    return session


def find_user_playlist_by_name(
    session: tidalapi.Session,
    playlist_name: str,
) -> dict[str, Any] | None:
    """Find one user playlist by exact name without loading unrelated playlists."""
    matches: list[dict[str, Any]] = []
    limit = 100
    offset = 0

    while True:
        response = session.request.request(
            "GET",
            f"users/{session.user.id}/playlists",
            params={"limit": limit, "offset": offset},
        )
        payload = response.json()
        items = payload.get("items", [])
        matches.extend(item for item in items if item.get("title") == playlist_name)

        offset += len(items)
        total = payload.get("totalNumberOfItems")
        if not items or (total is not None and offset >= total):
            break

    if len(matches) > 1:
        ids = ", ".join(str(item.get("uuid") or item.get("id")) for item in matches)
        raise RuntimeError(f"Multiple playlists named {playlist_name!r} found: {ids}")

    return matches[0] if matches else None


def get_playlist_tracks(playlist: Any) -> list[Any]:
    """Return every track in a playlist, following all result pages."""
    return list(playlist.tracks_paginated())


def get_playlist_track_ids(playlist: Any) -> list[int]:
    """Return every track id in a playlist, following all result pages."""
    return [track.id for track in get_playlist_tracks(playlist)]


def add_tracks_to_playlist(
    session: tidalapi.Session,
    playlist_id: str,
    track_ids: list[int],
    position: int = -1,
    *,
    allow_duplicates: bool = False,
    batch_size: int = 40,
) -> list[int]:
    """Add tracks in batches at the top or end and return accepted track ids."""
    batches = [
        track_ids[start : start + batch_size]
        for start in range(0, len(track_ids), batch_size)
    ]
    if position == 0:
        batches.reverse()

    accepted: list[int] = []
    for batch in batches:
        # Re-instantiating avoids stale ETag/precondition errors on TIDAL mutations.
        playlist = tidalapi.playlist.UserPlaylist(session, playlist_id)
        accepted.extend(
            playlist.add(
                batch,
                allow_duplicates=allow_duplicates,
                position=position,
            )
        )
        time.sleep(1)
    return accepted


def get_playlist_folder(
    session: tidalapi.Session,
    folder_name: str,
    *,
    create: bool = False,
):
    """Find a named root folder, optionally creating it."""
    folder = next(
        (
            folder
            for folder in session.user.favorites.playlist_folders()
            if folder.name.casefold() == folder_name.casefold()
        ),
        None,
    )
    if folder is None:
        if not create:
            raise RuntimeError(f"TIDAL playlist folder not found: {folder_name!r}")
        folder = session.user.create_folder(folder_name)
        time.sleep(0.5)
    return folder
