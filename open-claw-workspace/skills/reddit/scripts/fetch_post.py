#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["praw"]
# ///
"""Fetch a Reddit post and top comments in a compact, LLM-friendly format."""

import argparse
import json
import os
import sys
from typing import Any, cast

import praw


class LowScorePostError(Exception):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch a Reddit post and top comments as JSON."
    )
    parser.add_argument("url", help="Reddit post URL or post ID")
    parser.add_argument(
        "--max-comments",
        type=int,
        default=50,
        help="Maximum number of comments to include",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=2,
        help="Maximum comment depth to include",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=0,
        help="Minimum score threshold for comments (default: 0)",
    )
    parser.add_argument(
        "--max-body",
        type=int,
        default=0,
        help="Truncate comment bodies to this many chars (0 = no limit)",
    )
    parser.add_argument(
        "--filter-post",
        action="store_true",
        help="Also apply min-score to the post itself; exits with code 2 if post score is too low",
    )
    parser.add_argument(
        "--client-id",
        default=os.getenv("REDDIT_CLIENT_ID"),
        help="Reddit API client id (or REDDIT_CLIENT_ID)",
    )
    parser.add_argument(
        "--client-secret",
        default=os.getenv("REDDIT_CLIENT_SECRET"),
        help="Reddit API client secret (or REDDIT_CLIENT_SECRET)",
    )
    parser.add_argument(
        "--user-agent",
        default=os.getenv("REDDIT_USER_AGENT", "openclaw-skill:v1.0"),
        help="Reddit API user agent (or REDDIT_USER_AGENT)",
    )
    return parser.parse_args()


def build_reddit_client(
    client_id: str | None,
    client_secret: str | None,
    user_agent: str | None,
) -> praw.Reddit:
    if not client_id or not client_secret or not user_agent:
        raise ValueError(
            "Missing Reddit credentials. Provide --client-id, --client-secret, "
            "--user-agent or set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, "
            "REDDIT_USER_AGENT."
        )
    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
        check_for_async=False,
    )


def _is_junk(comment: Any) -> bool:
    """Return True for deleted/removed comments or bot-generated noise."""
    body = comment.body.strip()
    if comment.author is None and body in ("[removed]", "[deleted]", ""):
        return True
    author = str(comment.author).lower() if comment.author else ""
    if author == "automoderator":
        return True
    if "i am a bot" in body.lower():
        return True
    return False


def _truncate(text: str, max_len: int) -> str:
    if max_len <= 0 or len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def collect_comments(
    comment: Any,
    depth: int,
    max_depth: int,
    counter: dict[str, int],
    max_comments: int,
    min_score: int,
    max_body: int,
    out: list[dict[str, Any]],
) -> None:
    """Flatten comments into a list with depth indicators."""
    if counter["n"] >= max_comments:
        return
    if _is_junk(comment):
        return
    if comment.score < min_score:
        return
    counter["n"] += 1
    out.append({
        "author": str(comment.author) if comment.author else None,
        "score": comment.score,
        "depth": depth,
        "body": _truncate(comment.body, max_body),
    })
    if depth < max_depth:
        for reply in list(cast(object, comment.replies)):
            collect_comments(
                reply, depth + 1, max_depth, counter,
                max_comments, min_score, max_body, out,
            )


def fetch_submission_data(
    reddit: praw.Reddit,
    url: str,
    max_depth: int,
    max_comments: int,
    min_score: int,
    max_body: int,
    filter_post: bool,
) -> dict[str, Any]:
    if url.startswith("http"):
        submission = reddit.submission(url=url)
    else:
        submission = reddit.submission(id=url)

    submission.comment_sort = "top"
    submission.comments.replace_more(limit=0)

    if filter_post and submission.score < min_score:
        raise LowScorePostError(
            f"Post score ({submission.score}) is below minimum ({min_score})"
        )

    counter = {"n": 0}
    comments: list[dict[str, Any]] = []
    for comment in list(cast(object, submission.comments)):
        collect_comments(
            comment, 0, max_depth, counter,
            max_comments, min_score, max_body, comments,
        )

    result: dict[str, Any] = {
        "sub": str(submission.subreddit),
        "title": submission.title,
        "author": str(submission.author) if submission.author else None,
        "score": submission.score,
        "permalink": submission.permalink,
    }
    if submission.is_self and submission.selftext:
        result["body"] = _truncate(submission.selftext, max_body)
    elif not submission.is_self:
        result["link"] = submission.url
    result["comments"] = comments

    return result


def fetch_reddit_post(
    url: str,
    max_comments: int = 50,
    depth: int = 2,
    min_score: int = 0,
    max_body: int = 0,
    filter_post: bool = False,
    client_id: str | None = None,
    client_secret: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    """Fetch a Reddit post with comments.

    Raises:
        ValueError: If Reddit credentials are missing.
    """
    reddit = build_reddit_client(
        client_id or os.getenv("REDDIT_CLIENT_ID"),
        client_secret or os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent or os.getenv("REDDIT_USER_AGENT"),
    )
    return fetch_submission_data(
        reddit, url, depth, max_comments, min_score, max_body, filter_post
    )


def main() -> None:
    args = parse_args()
    try:
        data = fetch_reddit_post(
            url=args.url,
            max_comments=args.max_comments,
            depth=args.depth,
            min_score=args.min_score,
            max_body=args.max_body,
            filter_post=args.filter_post,
            client_id=args.client_id,
            client_secret=args.client_secret,
            user_agent=args.user_agent,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except LowScorePostError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)

    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
