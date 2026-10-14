#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["praw>=7.7,<8"]
# ///
"""Read-only Reddit CLI via PRAW (app-only OAuth; no account access).

Credentials: env vars, or KEY=VALUE lines in --env-file (default ~/.hermes/.env;
only REDDIT_* keys are loaded, real env vars win).
  REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET   required ("script" app)
  REDDIT_USER_AGENT                        recommended: "hermes-reddit/0.3 by u/<you>"

Commands: search, thread, sub, user, info
Exit codes: 0 ok, 1 error/credentials, 2 post below --min-score with --filter-post.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import praw
import prawcore

DEFAULT_UA = "hermes-reddit/0.3"
BOT_AUTHORS = {"automoderator"}
JUNK_BODIES = {"[removed]", "[deleted]", ""}


class LowScorePost(Exception):
    pass


# ---------------------------------------------------------------- setup
def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.removeprefix("export ").strip()
        if k.startswith("REDDIT_") and k not in os.environ:
            os.environ[k] = v.strip().strip('"').strip("'")


def client() -> praw.Reddit:
    cid, secret = os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
    if not cid or not secret:
        die("set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET (env or --env-file)")
    r = praw.Reddit(client_id=cid, client_secret=secret, check_for_async=False, check_for_updates=False,
                    user_agent=os.environ.get("REDDIT_USER_AGENT", DEFAULT_UA))
    r.read_only = True
    return r


def die(msg: str, code: int = 1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- helpers
def ts(t: float | None) -> str | None:
    return None if t is None else datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def age_days(t: float) -> int:
    return (datetime.now(timezone.utc) - datetime.fromtimestamp(t, tz=timezone.utc)).days


def author(x) -> str | None:
    return x.author.name if x.author else None


def trunc(text: str, n: int) -> str:
    return text if n <= 0 or len(text) <= n else text[:n].rstrip() + "…"


def is_junk(c) -> bool:
    body = c.body.strip()
    if c.author is None and body in JUNK_BODIES:
        return True
    if c.author and c.author.name.lower() in BOT_AUTHORS:
        return True
    return "i am a bot" in body.lower()


def post_dict(s, body: bool = True, max_body: int = 0) -> dict:
    d = {
        "id": s.id,
        "title": s.title,
        "subreddit": s.subreddit.display_name,
        "author": author(s),
        "score": s.score,
        "upvote_ratio": getattr(s, "upvote_ratio", None),
        "num_comments": s.num_comments,
        "created_utc": ts(s.created_utc),
        "permalink": "https://www.reddit.com" + s.permalink,
        "flair": s.link_flair_text,
        "nsfw": s.over_18,
        "locked": s.locked,
    }
    if not s.is_self:
        d["link"] = s.url
    if body and s.is_self and s.selftext:
        d["selftext"] = trunc(s.selftext, max_body)
    return d


def comment_tree(comments, a, budget: list[int], level: int = 0) -> list[dict]:
    out: list[dict] = []
    for c in comments:
        if budget[0] <= 0:
            break
        if isinstance(c, praw.models.MoreComments):
            if c.count:
                out.append({"more": c.count})
            continue
        if not a.keep_junk and is_junk(c):
            continue
        if c.score < a.min_score:
            continue
        budget[0] -= 1
        node = {"id": c.id, "author": author(c), "score": c.score, "created_utc": ts(c.created_utc),
                "is_op": c.is_submitter, "body": trunc(c.body, a.max_body)}
        if c.distinguished:
            node["distinguished"] = c.distinguished
        if level + 1 < a.depth and c.replies:
            kids = comment_tree(c.replies, a, budget, level + 1)
            if kids:
                node["replies"] = kids
        out.append(node)
    return out


def flatten(nodes: list[dict], depth: int = 0) -> list[dict]:
    out = []
    for n in nodes:
        if "more" in n:
            continue
        kids = n.pop("replies", [])
        out.append({**n, "depth": depth})
        out += flatten(kids, depth + 1)
    return out


# ---------------------------------------------------------------- markdown
def md_post_line(p: dict) -> str:
    line = (f"- **{p['title']}** — r/{p['subreddit']} · {p['score']}↑ · {p['num_comments']} comments · "
            f"u/{p['author'] or '[deleted]'} · {p['created_utc']}\n  {p['permalink']}")
    if p.get("selftext"):
        line += "\n  > " + p["selftext"].replace("\n", " ")
    return line


def md_comments(nodes: list[dict], level: int = 0) -> list[str]:
    lines, pad = [], "  " * level
    for n in nodes:
        if "more" in n:
            lines.append(f"{pad}- _[{n['more']} more replies not loaded]_")
            continue
        tag = " (OP)" if n["is_op"] else (f" ({n['distinguished']})" if n.get("distinguished") else "")
        body = n["body"].replace("\n", f"\n{pad}  ")
        lines.append(f"{pad}- **u/{n['author'] or '[deleted]'}{tag}** · {n['score']}↑\n{pad}  {body}")
        lines += md_comments(n.get("replies", []), level + 1)
    return lines


def md_thread(d: dict) -> str:
    p = d["post"]
    head = [f"# {p['title']}"]
    head += [f"r/{p['subreddit']} · u/{p['author'] or '[deleted]'} · {p['score']}↑ ({p['upvote_ratio']}) · "
             f"{p['num_comments']} comments · {p['created_utc']}" + (" · locked" if p["locked"] else ""),
             p["permalink"]]
    if p.get("link"):
        head.append(f"Link: {p['link']}")
    if p.get("selftext"):
        head += ["", p["selftext"]]
    return "\n".join(head + ["", f"## Comments ({d['comments_shown']} shown)", ""] + md_comments(d["comments"]))


def render(data: Any, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(data, indent=2, ensure_ascii=False)
    if isinstance(data, dict) and "post" in data:
        return md_thread(data)
    if isinstance(data, dict) and "threads" in data:  # research bundle
        parts = []
        for t in data["threads"]:
            parts.append(md_thread(t) if "post" in t else f"# (failed) {t['target']}\n{t['error']}")
        return "\n\n---\n\n".join(parts)
    if isinstance(data, dict) and "items" not in data:  # status/plan output
        return json.dumps(data, indent=2, ensure_ascii=False)
    items = data.get("items", []) if isinstance(data, dict) else data
    if not items:
        return "_No results._"
    first = items[0]
    if "title" in first and "num_comments" in first:
        return "\n".join(md_post_line(p) for p in items)
    if "link_title" in first:
        return "\n".join(f"- r/{c['subreddit']} · {c['score']}↑ · {c['created_utc']} — {c['link_title']}\n"
                         f"  {c['permalink']}\n  > {trunc(c['body'], 500).replace(chr(10), ' ')}" for c in items)
    return "\n".join("- " + " · ".join(f"{k}: {v}" for k, v in i.items() if v not in (None, "")) for i in items)


# ---------------------------------------------------------------- read commands
def fetch_thread(r, target: str, a) -> dict:
    s = r.submission(url=target) if target.startswith("http") else r.submission(id=target.removeprefix("t3_"))
    s.comment_sort = a.comment_sort
    if a.filter_post and s.score < a.min_score:
        raise LowScorePost(f"post score {s.score} < --min-score {a.min_score}")
    s.comments.replace_more(limit=a.more)
    tree = comment_tree(s.comments, a, [a.max_comments])
    shown = sum(1 for _ in _walk(tree))
    if a.flat:
        tree = flatten(tree)
    return {"post": post_dict(s, max_body=a.max_body), "comments": tree, "comments_shown": shown}


def _walk(nodes):
    for n in nodes:
        if "more" not in n:
            yield n
            yield from _walk(n.get("replies", []))


def cmd_thread(r, a):
    if len(a.targets) == 1:
        return fetch_thread(r, a.targets[0], a)
    threads = []
    for t in a.targets:  # batch mode: keep going on per-thread failure
        try:
            threads.append(fetch_thread(r, t, a))
        except LowScorePost as e:
            log(f"skip {t}: {e}")
        except (prawcore.exceptions.PrawcoreException, praw.exceptions.PRAWException, ValueError) as e:
            threads.append({"target": t, "error": f"{type(e).__name__}: {e}"})
    return {"threads": threads}


def cmd_search(r, a):
    sub = r.subreddit(a.subreddit or "all")
    res = sub.search(a.query, sort=a.sort, time_filter=a.time, limit=a.limit)
    items = [post_dict(s, body=a.bodies, max_body=a.max_body or 300) for s in res]
    return {"items": [p for p in items if p["score"] >= a.min_score]}


def cmd_sub(r, a):
    sub = r.subreddit(a.name)
    kw: dict[str, Any] = {"limit": a.limit}
    if a.listing in ("top", "controversial"):
        kw["time_filter"] = a.time
    return {"items": [post_dict(s, body=a.bodies, max_body=a.max_body or 300)
                      for s in getattr(sub, a.listing)(**kw)]}


def cmd_user(r, a):
    lst = getattr(r.redditor(a.name), a.kind)
    items = getattr(lst, a.sort)(limit=a.limit)
    if a.kind == "submissions":
        return {"items": [post_dict(s, body=a.bodies, max_body=a.max_body or 300) for s in items]}
    return {"items": [{"id": c.id, "subreddit": c.subreddit.display_name, "score": c.score,
                       "created_utc": ts(c.created_utc), "link_title": c.link_title,
                       "permalink": "https://www.reddit.com" + c.permalink, "body": c.body} for c in items]}


def subreddit_info(r, name: str) -> dict:
    """Status + activity for one subreddit (never raises)."""
    out: dict[str, Any] = {"name": name, "status": "unknown"}
    try:
        sub = r.subreddit(name)
        _ = sub.id  # force fetch
        desc = sub.public_description or ""
        out.update(status="accessible", title=sub.title, subscribers=sub.subscribers, nsfw=sub.over18,
                   subreddit_type=sub.subreddit_type, created_utc=ts(sub.created_utc),
                   public_description=desc[:300])
        posts = list(sub.new(limit=1))
        out["last_post_utc"] = ts(posts[0].created_utc) if posts else None
        out["last_post_age_days"] = age_days(posts[0].created_utc) if posts else None
    except prawcore.exceptions.NotFound:
        out["status"] = "banned"
    except prawcore.exceptions.Forbidden:
        out["status"] = "private"
    except prawcore.exceptions.Redirect:
        out["status"] = "not_found"
    except Exception as e:  # noqa: BLE001 — audit must keep going
        out.update(status="error", error=f"{type(e).__name__}: {e}")
    return out


def cmd_info(r, a):
    return {"items": [subreddit_info(r, n) for n in a.names]}


# ---------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Reddit via PRAW", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    ap.add_argument("--format", choices=["md", "json"], default="md")
    ap.add_argument("--env-file", type=Path, default=Path.home() / ".hermes/.env")
    sp = ap.add_subparsers(dest="cmd", required=True)
    times = ["all", "year", "month", "week", "day", "hour"]

    def common_list(p, n=25):
        p.add_argument("-n", "--limit", type=int, default=n)
        p.add_argument("--bodies", action="store_true", help="include post text (truncated)")
        p.add_argument("--max-body", type=int, default=0, help="truncate bodies (0 = 300 for lists)")

    p = sp.add_parser("search", help="search posts")
    p.add_argument("query")
    p.add_argument("-s", "--subreddit", help="restrict (a+b for several)")
    p.add_argument("--sort", default="relevance", choices=["relevance", "hot", "top", "new", "comments"])
    p.add_argument("-t", "--time", default="all", choices=times)
    p.add_argument("--min-score", type=int, default=0)
    common_list(p)
    p.set_defaults(fn=cmd_search)

    p = sp.add_parser("thread", help="post + comments; several targets = batch")
    p.add_argument("targets", nargs="+", metavar="URL_OR_ID")
    p.add_argument("--depth", type=int, default=3)
    p.add_argument("--max-comments", type=int, default=100)
    p.add_argument("--min-score", type=int, default=1, help="drop comments below this (default 1)")
    p.add_argument("--max-body", type=int, default=0, help="truncate post/comment bodies (0 = no limit)")
    p.add_argument("--more", type=int, default=0, help="'load more' expansions, 1 API call each; -1 = all")
    p.add_argument("--comment-sort", default="top", choices=["top", "best", "new", "controversial", "old", "q&a"])
    p.add_argument("--filter-post", action="store_true", help="exit 2 / skip if post score < --min-score")
    p.add_argument("--keep-junk", action="store_true", help="keep removed/deleted/bot comments")
    p.add_argument("--flat", action="store_true", help="flat list with depth field instead of a tree")
    p.set_defaults(fn=cmd_thread)

    p = sp.add_parser("sub", help="list a subreddit")
    p.add_argument("name")
    p.add_argument("--listing", default="hot", choices=["hot", "new", "top", "rising", "controversial"])
    p.add_argument("-t", "--time", default="week", choices=times)
    common_list(p)
    p.set_defaults(fn=cmd_sub)

    p = sp.add_parser("user", help="a user's posts or comments")
    p.add_argument("name")
    p.add_argument("--kind", default="submissions", choices=["submissions", "comments"])
    p.add_argument("--sort", default="new", choices=["new", "hot", "top"])
    common_list(p)
    p.set_defaults(fn=cmd_user)

    p = sp.add_parser("info", help="subreddit status/activity")
    p.add_argument("names", nargs="+")
    p.set_defaults(fn=cmd_info)

    return ap


def main() -> None:
    a = build_parser().parse_args()
    if getattr(a, "more", 0) == -1:
        a.more = None
    load_env_file(a.env_file)
    try:
        out = a.fn(client(), a)
    except LowScorePost as e:
        die(str(e), 2)
    except prawcore.exceptions.ResponseException as e:
        die(f"Reddit API HTTP {e.response.status_code} — check credentials / user agent / app approval")
    except prawcore.exceptions.OAuthException as e:
        die(f"OAuth failed: {e} — check client id/secret or refresh token")
    except (prawcore.exceptions.NotFound, prawcore.exceptions.Redirect):
        die("not found (bad subreddit/user/post id?)")
    except prawcore.exceptions.Forbidden:
        die("forbidden (private/quarantined/banned)")
    except prawcore.exceptions.PrawcoreException as e:
        die(f"{type(e).__name__}: {e}")
    sys.stdout.reconfigure(encoding="utf-8")
    print(render(out, a.format))


if __name__ == "__main__":
    main()
