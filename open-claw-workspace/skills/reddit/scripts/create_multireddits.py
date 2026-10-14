#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["praw"]
# ///
"""Create private multireddits from a cleanup plan."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import praw


MAX_DISPLAY_NAME = 50


def main() -> None:
    p = argparse.ArgumentParser(description="Create multireddits from cleanup plan.")
    p.add_argument("--plan", required=True, help="Path to cleanup_plan.json")
    p.add_argument("--confirm", action="store_true", help="Actually create (default: dry-run)")
    p.add_argument("--output", default=None, help="Path for results JSON")
    args = p.parse_args()

    with open(args.plan) as f:
        plan = json.load(f)

    multireddits = plan.get("multireddits", {})
    if not multireddits:
        print("No multireddits defined in plan.", file=sys.stderr)
        return

    mode = "LIVE" if args.confirm else "DRY-RUN"
    print(f"[{mode}] Will create {len(multireddits)} multireddits.", file=sys.stderr)

    if not args.confirm:
        for name, subs in multireddits.items():
            sub_list = subs if isinstance(subs, list) else subs.get("subreddits", [])
            display = name[:MAX_DISPLAY_NAME]
            print(f"  {display}: {len(sub_list)} subs", file=sys.stderr)
        print(f"\nDry run complete. Use --confirm to execute.", file=sys.stderr)
        return

    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        refresh_token=os.getenv("REDDIT_REFRESH_TOKEN"),
        user_agent=os.getenv("REDDIT_USER_AGENT", "openclaw-skill:v1.0"),
    )

    # Check existing multireddits to avoid collisions
    existing = set()
    try:
        for m in reddit.user.multireddits():
            existing.add(m.display_name.lower())
    except Exception:
        pass

    results = []
    for name, subs in multireddits.items():
        sub_list = subs if isinstance(subs, list) else subs.get("subreddits", [])
        display = name[:MAX_DISPLAY_NAME]

        if display.lower() in existing:
            print(f"  SKIP {display}: already exists", file=sys.stderr)
            results.append({"name": display, "status": "skipped", "reason": "already exists"})
            continue

        try:
            multi = reddit.multireddit.create(
                display_name=display,
                subreddits=sub_list,
                visibility="private",
            )
            results.append({
                "name": display,
                "status": "created",
                "path": multi.path,
                "sub_count": len(sub_list),
            })
            print(f"  CREATED {display} ({len(sub_list)} subs) -> {multi.path}", file=sys.stderr)
        except Exception as e:
            results.append({"name": display, "status": "error", "error": str(e)})
            print(f"  ERROR {display}: {e}", file=sys.stderr)

    succeeded = sum(1 for r in results if r["status"] == "created")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"] == "error")
    print(f"\nDone: {succeeded} created, {skipped} skipped, {failed} errors.", file=sys.stderr)

    if args.output:
        report = {
            "executed": datetime.now(timezone.utc).isoformat(),
            "total": len(multireddits),
            "succeeded": succeeded,
            "skipped": skipped,
            "failed": failed,
            "results": results,
        }
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)


if __name__ == "__main__":
    main()
