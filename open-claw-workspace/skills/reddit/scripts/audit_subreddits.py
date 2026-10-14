#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["praw"]
# ///
"""Audit subscribed subreddits: check status, activity, and tag categories."""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

import praw
import prawcore.exceptions


TV_KEYWORDS = [
    "netflix", "hbo", "hulu", "disney+", "amazon prime", "apple tv",
    "series", "season", "episode", "tv show", "television",
    "fx on hulu", "showtime", "paramount+", "peacock",
]

ANIME_KEYWORDS = ["anime", "manga", "shonen", "seinen", "isekai"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Audit subscribed subreddits.")
    p.add_argument("--input", required=True, help="Path to snapshot JSON")
    p.add_argument("--output", required=True, help="Path for audit report JSON")
    p.add_argument("--inactive-months", type=int, default=12, help="Inactivity threshold in months")
    p.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    p.add_argument("--progress-file", default=None, help="Checkpoint file (default: data/audit_progress.json)")
    p.add_argument("--batch-size", type=int, default=50, help="Checkpoint every N subs")
    return p.parse_args()


def detect_category_hints(name: str, title: str, description: str) -> list[str]:
    hints = []
    text = f"{name} {title} {description}".lower()
    for kw in TV_KEYWORDS:
        if kw in text:
            hints.append("tv_show")
            break
    for kw in ANIME_KEYWORDS:
        if kw in text:
            hints.append("anime")
            break
    return hints


def humanize_age(days: int) -> str:
    if days < 1:
        return "<1d ago"
    if days < 30:
        return f"{days}d ago"
    if days < 365:
        return f"{days // 30}mo ago"
    return f"{days // 365}y ago"


def audit_subreddit(reddit: praw.Reddit, name: str) -> dict[str, Any]:
    result: dict[str, Any] = {"name": name, "status": "unknown"}
    try:
        sub = reddit.subreddit(name)
        # Force fetch to detect banned/private
        _ = sub.id
        result["status"] = "accessible"
        result["title"] = sub.title
        result["subscribers"] = sub.subscribers
        result["nsfw"] = sub.over18
        result["subreddit_type"] = sub.subreddit_type
        result["public_description"] = (sub.public_description or "")[:300]
        result["category_hints"] = detect_category_hints(
            name, sub.title or "", sub.public_description or ""
        )
        # Check last activity
        posts = list(sub.new(limit=1))
        if posts:
            ts = posts[0].created_utc
            result["last_post_utc"] = ts
            age = (datetime.now(timezone.utc) - datetime.fromtimestamp(ts, tz=timezone.utc)).days
            result["last_post_age_days"] = age
        else:
            result["last_post_utc"] = None
            result["last_post_age_days"] = None
    except prawcore.exceptions.NotFound:
        result["status"] = "banned"
    except prawcore.exceptions.Forbidden:
        result["status"] = "private"
    except prawcore.exceptions.Redirect:
        result["status"] = "redirected"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    return result


def load_progress(path: str) -> dict[str, Any]:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"completed": [], "results": []}


def save_progress(path: str, progress: dict[str, Any]) -> None:
    with open(path, "w") as f:
        json.dump(progress, f)


def main() -> None:
    args = parse_args()
    progress_file = args.progress_file or os.path.join(
        os.path.dirname(args.output), "audit_progress.json"
    )

    with open(args.input) as f:
        subs = json.load(f)
    sub_names = [s["name"] for s in subs]

    progress = load_progress(progress_file) if args.resume else {"completed": [], "results": []}
    completed_set = set(progress["completed"])
    results = progress["results"]

    remaining = [n for n in sub_names if n not in completed_set]
    total = len(sub_names)
    done_so_far = len(completed_set)

    if not remaining:
        print("All subreddits already audited.", file=sys.stderr)
    else:
        reddit = praw.Reddit(
            client_id=os.getenv("REDDIT_CLIENT_ID"),
            client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
            refresh_token=os.getenv("REDDIT_REFRESH_TOKEN"),
            user_agent=os.getenv("REDDIT_USER_AGENT", "openclaw-skill:v1.0"),
        )

        start_time = time.time()
        for i, name in enumerate(remaining):
            idx = done_so_far + i + 1
            result = audit_subreddit(reddit, name)
            results.append(result)
            progress["completed"].append(name)
            completed_set.add(name)

            # Progress line
            status = result["status"]
            age_str = ""
            if result.get("last_post_age_days") is not None:
                age_str = f" (last post: {humanize_age(result['last_post_age_days'])})"
            print(f"[{idx}/{total}] r/{name}... {status}{age_str}", file=sys.stderr)

            # Checkpoint + ETA
            if (i + 1) % args.batch_size == 0:
                save_progress(progress_file, progress)
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed
                eta_s = (len(remaining) - i - 1) / rate if rate > 0 else 0
                eta_m = eta_s / 60
                print(f"  -- checkpoint saved. ETA: {eta_m:.1f} min remaining", file=sys.stderr)

        # Final save
        save_progress(progress_file, progress)

    # Build report
    inactive_threshold = args.inactive_months * 30
    summary = {
        "accessible": 0, "banned": 0, "private": 0,
        "redirected": 0, "error": 0,
        f"inactive_{args.inactive_months}mo": 0,
    }
    for r in results:
        s = r["status"]
        if s in summary:
            summary[s] += 1
        age = r.get("last_post_age_days")
        if age is not None and age > inactive_threshold:
            summary[f"inactive_{args.inactive_months}mo"] += 1

    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "inactive_threshold_months": args.inactive_months,
        "summary": summary,
        "subreddits": results,
    }

    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nAudit complete. Report: {args.output}", file=sys.stderr)
    print(f"Summary: {json.dumps(summary, indent=2)}", file=sys.stderr)


if __name__ == "__main__":
    main()
