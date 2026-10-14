---
name: reddit
description: "Use when reading, searching or researching Reddit. Read-only PRAW CLI via uv: threads, search, listings."
---

# Reddit

One self-contained, read-only uv script: `scripts/reddit.py` (PRAW, app-only OAuth — no account access, no writes).

```bash
R=~/.hermes/my-skills/research/reddit/scripts/reddit.py
uv run --script $R <command> [--format md|json] ...
```

Markdown output is the default (LLM-friendly). Use `--format json` (global flag, goes **before** the command) for piping between steps.

## Credentials

Loaded from env or `~/.hermes/.env` (only `REDDIT_*` keys; real env wins):
- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` — "script" app at reddit.com/prefs/apps.
- `REDDIT_USER_AGENT` — `hermes-reddit/0.3 by u/<name>`; generic UAs get throttled.

Never print or echo secrets.

## Research workflow ("what does Reddit think about X")

1. **Discover**: web_search `site:reddit.com X` (Google ranks threads better than Reddit search), and/or `reddit.py search "X" --sort top -t year --min-score 5`.
2. **Fetch** the top 2–4 threads in one batch call:
   `reddit.py thread URL1 URL2 URL3 --max-comments 40 --max-body 1500`
3. **Synthesize** consensus, disagreements, and notable specifics; cite permalinks.

Direct links: `reddit.py thread URL` and then summarize. Use this instead of web_extract for reddit.com URLs — extract returns empty on Reddit's JS-rendered pages. Bare post IDs (e.g. `1wkpl3q` from the URL) work as targets.

When combining with GitHub/web research on a topic, flag astroturfing signals (mod spam bans, "paid posts" comments, low-upvote hype) and weigh them against repo health data.

## Commands

| Command | Purpose |
|---|---|
| `search Q [-s sub1+sub2] [--sort top] [-t year] [--min-score N] [--bodies]` | Search posts |
| `thread URL_OR_ID... [--depth 3] [--max-comments 100] [--min-score 1] [--max-body N] [--more N] [--comment-sort top] [--flat] [--filter-post] [--keep-junk]` | Post + comment tree. If several targets are given, batch mode keeps going when one fails |
| `sub NAME [--listing hot/new/top/rising] [-t week]` | Subreddit listing |
| `user NAME [--kind comments]` | User history |
| `info NAME...` | Status (accessible/private/banned/not_found), subscribers, last post age |

Defaults for threads: top sort, comments with score below 1 are dropped, and AutoModerator, "I am a bot" and removed/deleted comments are filtered out.

## Conventions & pitfalls

- `--more` costs one API call per expansion; the default of 0 is enough for research.
- Errors: HTTP 401/403 means bad credentials or the app isn't approved; `not found` means a bad name or ID. PRAW handles rate limits itself.
- The OpenClaw original (with subscription audit/unsubscribe/multireddit tools) is archived at `~/.hermes/archive/openclaw-imports-*/reddit` and still live in `~/.openclaw/workspace/skills/reddit`. Only the read-only parts were ported, on purpose.
