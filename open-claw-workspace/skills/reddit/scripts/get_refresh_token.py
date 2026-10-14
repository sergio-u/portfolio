#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["praw"]
# ///
"""One-time OAuth2 flow to obtain a Reddit refresh token."""

import os
import sys
from urllib.parse import parse_qs, urlparse

import praw


REDIRECT_URI = "http://localhost:65010"
SCOPES = ["identity", "mysubreddits", "read", "subscribe"]


def main() -> None:
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT", "openclaw-skill:v1.0")

    if not client_id or not client_secret:
        print("Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET first.", file=sys.stderr)
        sys.exit(1)

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
        redirect_uri=REDIRECT_URI,
    )

    url = reddit.auth.url(duration="permanent", scopes=SCOPES, state="openclaw")
    print(f"\nOpen this URL in your browser:\n\n{url}\n")
    print("After authorizing, your browser will redirect to a URL that fails to load.")
    print("Copy the FULL URL from the address bar and paste it here.\n")
    redirect_url = input("Paste redirect URL: ").strip()
    params = parse_qs(urlparse(redirect_url).query)
    if "error" in params:
        print(f"Error: {params['error'][0]}", file=sys.stderr)
        sys.exit(1)
    code = params["code"][0]
    refresh_token = reddit.auth.authorize(code)
    print(f"\nRefresh token:\n\n{refresh_token}\n")
    print("Save this as REDDIT_REFRESH_TOKEN in your .env file.")


if __name__ == "__main__":
    main()
