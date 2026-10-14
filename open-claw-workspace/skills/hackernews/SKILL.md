---
name: hackernews
description: >
  Fetch and summarize Hacker News posts and comment threads via the Algolia HN API.
  Also use for research workflows: search HN via SearxNG (site:news.ycombinator.com)
  to find relevant discussions, then fetch and parse the top results with this skill.
  Triggers on "hacker news", "hackernews", "HN", "what does HN think about",
  "HN discussion", "fetch this HN thread", "summarize this HN post",
  "HN recommendations for", or any news.ycombinator.com URL/item ID.
---

# Hacker News

Fetch and summarize Hacker News posts and comment threads via the Algolia HN API. No auth required.

## Execution

### Fetch Post

```bash
uv run skills/hackernews/scripts/fetch_post.py "URL_OR_ID" [options]
```

| Option | Default | Description |
|---|---|---|
| `--max-comments N` | 50 | Max comments to include |
| `--depth N` | 2 | Max comment thread depth |
| `--min-points N` | 0 | Min points threshold for comments |
| `--max-body N` | 0 | Truncate comment bodies to N chars (0 = no limit) |

Output: JSON with post metadata and a flat comment list with `depth` indicators (same shape as reddit skill).

## Workflow

### Research queries ("what does HN think about X")

1. **Discover** relevant threads using `web_search`: `site:news.ycombinator.com QUERY`
2. **Fetch** the top 2-4 most relevant posts with this skill.
3. **Synthesize** findings into a clear summary for the user.

### Direct links (user shares a news.ycombinator.com URL)

1. **Fetch** the post directly.
2. **Summarize** or present as requested.

## Conventions

- Run from the workspace root (`~/.openclaw/workspace`).
- Present results as readable summaries. Do not dump raw JSON at the user.
- HN comments via Algolia often report 0 points -- do NOT use `--min-points` for filtering. Use the default (0).
- When fetching multiple threads, keep to 2-4 posts max to avoid context overload.
- Do NOT use a separate search script -- use the built-in `web_search` tool with `site:news.ycombinator.com` for discovery (same pattern as the reddit skill).
- HN comment bodies may contain HTML entities -- present cleaned text to the user.
- Most HN posts link to an external article (the `url` field in output). When the goal is full content extraction (e.g. for digests), fetch both the discussion AND the linked article separately.

## Requirements

- `uv` package manager.
- `requests` Python library (managed via inline uv script deps).
- No auth or API keys required (Algolia HN API is public).
