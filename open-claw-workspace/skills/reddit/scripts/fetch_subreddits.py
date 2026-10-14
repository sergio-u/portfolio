#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["praw"]
# ///
"""Fetch the authenticated user's subscribed subreddits."""

import json
import os
import sys

import praw


def main() -> None:
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    refresh_token = os.getenv("REDDIT_REFRESH_TOKEN")
    user_agent = os.getenv("REDDIT_USER_AGENT", "openclaw-skill:v1.0")

    if not client_id or not client_secret or not refresh_token:
        print(
            "Set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, and REDDIT_REFRESH_TOKEN.",
            file=sys.stderr,
        )
        sys.exit(1)

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
        user_agent=user_agent,
    )

    subs = []
    for sub in reddit.user.subreddits(limit=None):
        subs.append({
            "name": sub.display_name,
            "title": sub.title,
            "subscribers": sub.subscribers,
            "nsfw": sub.over18,
        })

    subs.sort(key=lambda s: s["name"].lower())
    print(json.dumps(subs, indent=2))


if __name__ == "__main__":
    main()
