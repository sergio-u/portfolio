---
name: reddit
description: >
  Interact with Reddit via PRAW. Fetch post details and comments, manage
  subscriptions (list, audit, unsubscribe), and organize subreddits into
  multireddits. Also use for research workflows: search Reddit via SearxNG
  (site:reddit.com) to find relevant threads, then fetch and parse the top
  results with this skill. Triggers on "browse reddit", "manage subreddits",
  "fetch posts", "reddit", "look up this Reddit post", "what does Reddit say
  about", "Reddit recommendations for", "summarize this thread", "list my
  subreddits", "clean up my subscriptions", "create multireddits", or any
  Reddit URL/post ID.
---

# Reddit

Interact with Reddit via PRAW: fetch posts, manage subscriptions, organize multireddits.

## Execution

- **Fetch Post** -- Retrieve a post's full content and scored/threaded comments by URL or ID.
- **Fetch Subreddits** -- List all subscribed subreddits for the authenticated user.
- **Audit Subreddits** -- Check status (banned/private/accessible), last activity, and tag categories for all subscriptions. Supports resumable runs.
- **Categorize Subreddits** -- Group audited subs into broad themes for multireddit creation. Offline, no API calls.
- **Unsubscribe** -- Bulk unsubscribe from a list of subreddits. Dry-run by default.
- **Create Multireddits** -- Create private multireddits from a categorized plan. Dry-run by default.

### Workflow

#### Research queries ("what does Reddit think about X")

1. **Discover** relevant threads using SearxNG: `site:reddit.com QUERY`
2. **Fetch** the top 2-4 most relevant posts with this skill.
3. **Synthesize** findings into a clear summary for the user.

#### Direct links (user shares a reddit.com URL)

1. **Fetch** the post directly.
2. **Summarize** or present as requested.

#### Subscription cleanup

1. **Fetch** current subscriptions and save a snapshot.
2. **Audit** all subs for status and activity (~1 sub/sec, use `--resume` for long runs).
3. **Categorize** into themes.
4. **Review** with the user -- confirm unsubscribes and multireddit groupings.
5. **Execute** unsubscribe + multireddit creation with `--confirm`.

### Scripts

#### Fetch Post

```bash
uv run skills/reddit/scripts/fetch_post.py "URL_OR_ID" [options]
```

Options: `--max-comments N`, `--depth N`, `--min-score N`, `--max-body N`, `--filter-post`

Output: JSON with post metadata and a flat comment list with `depth` indicators.

#### Fetch Subreddits

```bash
uv run skills/reddit/scripts/fetch_subreddits.py
```

Requires `REDDIT_REFRESH_TOKEN`. Output: JSON array of subscribed subreddits (name, title, subscribers, nsfw).

#### Audit Subreddits

```bash
uv run skills/reddit/scripts/audit_subreddits.py \
  --input data/subreddits_snapshot.json \
  --output data/audit_report.json \
  --inactive-months 12 \
  --resume
```

Checks each sub's status and last post date. Checkpoints every 50 subs to `data/audit_progress.json`. Tags TV/anime subs via keyword matching.

#### Categorize Subreddits

```bash
uv run skills/reddit/scripts/categorize_subreddits.py \
  --input data/audit_report.json \
  --output data/categorized.json
```

Offline keyword-based grouping. Merges categories with <10 subs, splits those >100 (Reddit multireddit limit).

#### Unsubscribe

```bash
uv run skills/reddit/scripts/unsubscribe.py --plan data/cleanup_plan.json [--confirm]
```

Dry-run by default. Pass `--confirm` to execute. Optional `--output` for results JSON.

#### Create Multireddits

```bash
uv run skills/reddit/scripts/create_multireddits.py --plan data/cleanup_plan.json [--confirm]
```

Creates private multireddits. Dry-run by default. Skips existing multireddits by name. Optional `--output` for results JSON.

#### Get Refresh Token

```bash
uv run skills/reddit/scripts/get_refresh_token.py
```

One-time OAuth2 flow. Prints an authorization URL, you paste back the redirect URL, and it returns a refresh token. Scopes: identity, mysubreddits, read, subscribe.

## Reference

### Data Directory

`skills/reddit/data/` stores snapshots, audit reports, categorized output, cleanup plans, and execution results. These are gitignored working files.

## Conventions

- Run from the workspace root (`~/.openclaw/workspace`).
- Present results as readable summaries. Do not dump raw JSON at the user.
- If a post is NSFW (`over_18: true`), mention it before showing content.
- When fetching posts for research, use `--min-score 2` to filter noise.
- Always dry-run destructive operations (unsubscribe, multireddit creation) before confirming.
- Confirm with the user before executing any destructive operation with `--confirm`.
- Use JSON output for programmatic parsing between pipeline steps.

## Requirements

- `uv` package manager.
- `praw` Python library (managed via `uv`).
- Environment variables: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`.
- For user-authenticated endpoints: `REDDIT_REFRESH_TOKEN`.

## Troubleshooting

### Credentials error
Ensure `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and `REDDIT_USER_AGENT` env vars are set. For user-authenticated endpoints (subscriptions, unsubscribe, multireddits), also set `REDDIT_REFRESH_TOKEN`.

### Rate limiting
PRAW handles rate limits automatically. The audit script processes ~1 sub/sec. For 900+ subs, expect ~15-30 minutes. Use `--resume` to recover from interruptions.

### Refresh token expired
Re-run `get_refresh_token.py` to obtain a new token.
