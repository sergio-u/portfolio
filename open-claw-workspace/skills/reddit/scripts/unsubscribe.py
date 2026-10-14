#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["praw"]
# ///
"""Unsubscribe from subreddits listed in a cleanup plan."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import praw


def main() -> None:
    p = argparse.ArgumentParser(description="Unsubscribe from subreddits.")
    p.add_argument("--plan", required=True, help="Path to cleanup_plan.json")
    p.add_argument("--confirm", action="store_true", help="Actually unsubscribe (default: dry-run)")
    p.add_argument("--output", default=None, help="Path for results JSON")
    args = p.parse_args()

    with open(args.plan) as f:
        plan = json.load(f)

    to_unsub = plan.get("unsubscribe", [])
    if not to_unsub:
        print("No subreddits to unsubscribe from.", file=sys.stderr)
        return

    mode = "LIVE" if args.confirm else "DRY-RUN"
    print(f"[{mode}] Will unsubscribe from {len(to_unsub)} subreddits.", file=sys.stderr)

    if not args.confirm:
        for name in to_unsub:
            print(f"  Would unsub: r/{name}", file=sys.stderr)
        print(f"\nDry run complete. Use --confirm to execute.", file=sys.stderr)
        return

    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        refresh_token=os.getenv("REDDIT_REFRESH_TOKEN"),
        user_agent=os.getenv("REDDIT_USER_AGENT", "openclaw-skill:v1.0"),
    )

    results = []
    for i, name in enumerate(to_unsub, 1):
        try:
            reddit.subreddit(name).unsubscribe()
            results.append({"name": name, "status": "unsubscribed"})
            print(f"[{i}/{len(to_unsub)}] r/{name} unsubscribed", file=sys.stderr)
        except Exception as e:
            results.append({"name": name, "status": "error", "error": str(e)})
            print(f"[{i}/{len(to_unsub)}] r/{name} ERROR: {e}", file=sys.stderr)

    succeeded = sum(1 for r in results if r["status"] == "unsubscribed")
    failed = sum(1 for r in results if r["status"] == "error")
    print(f"\nDone: {succeeded} unsubscribed, {failed} errors.", file=sys.stderr)

    if args.output:
        report = {
            "executed": datetime.now(timezone.utc).isoformat(),
            "total": len(to_unsub),
            "succeeded": succeeded,
            "failed": failed,
            "results": results,
        }
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)


if __name__ == "__main__":
    main()
