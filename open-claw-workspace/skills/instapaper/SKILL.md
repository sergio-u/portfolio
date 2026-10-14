---
name: instapaper
description: >
  Manage Instapaper bookmarks and extract article content via the Instapaper API.
  List recent saves, fetch extracted article text, and route content extraction
  through companion skills based on source type (Reddit, Hacker News, YouTube,
  or general articles). Use when the user says "instapaper", "my saved articles",
  "reading list", "what did I save", "recent bookmarks", "fetch my instapaper",
  "digest my saves", "reading queue", or references Instapaper bookmarks.
---

# Instapaper

Manage Instapaper bookmarks and extract article content. Routes to companion skills for specialized sources.

## Execution

### List Bookmarks

```bash
uv run skills/instapaper/scripts/list_bookmarks.py [options]
```

| Option | Default | Description |
|---|---|---|
| `--hours N` | 0 | Only bookmarks saved within the last N hours (0 = all) |
| `--limit N` | 500 | Max bookmarks to fetch (1-500) |
| `--folder ID` | unread | Folder: unread, starred, archive, or folder_id |
| `--classify` | off | Add `source_type` field based on URL domain |

Output: JSON array of bookmark objects with `bookmark_id`, `url`, `title`, `time`, `hash`, etc.

Note: YouTube Shorts (`youtube.com/shorts/`) are automatically filtered out -- they have no meaningful extractable content.

### Fetch Article Text

```bash
uv run skills/instapaper/scripts/fetch_text.py BOOKMARK_ID [options]
```

| Option | Default | Description |
|---|---|---|
| `--strip-html` | off | Return plain text instead of HTML |
| `--max-chars N` | 0 | Truncate output to N chars (0 = no limit) |

Output: JSON with `bookmark_id`, `content_type`, `char_count`, and `content`.

### Archive Bookmarks

```bash
uv run skills/instapaper/scripts/archive_bookmarks.py ID1 ID2 ... [options]
```

| Option | Default | Description |
|---|---|---|
| `--from-file PATH` | - | JSON file with bookmark IDs or objects with bookmark_id field |
| `--delay N` | 0.5 | Seconds between API calls (rate limiting) |

Output: JSON with `total`, `archived`, `failed` counts and per-item results.

## Workflow

### Content Extraction by Source Type

Use `--classify` when listing bookmarks to get a `source_type` field. Then route extraction:

| Source Type | Extraction Strategy |
|---|---|
| **reddit** | Use the `reddit` skill (`fetch_post.py`) with the bookmark URL |
| **hackernews** | Use the `hackernews` skill (`fetch_post.py`) for post + comments (use default `--min-points 0` -- Algolia reports 0 on most comments). THEN extract the linked article URL (from the `url` field in the response) using the article fallback chain below. Call `fetch_and_extract.py` on the linked URL **without** `--bookmark-id`. |
| **youtube** | Use the `youtube-transcript` skill to fetch transcript |
| **article** | Use the article fallback chain below. If `fetch_and_extract.py` returns `status: "defer_youtube"`, re-route to youtube-transcript using the `youtube_url` field. |

### Article Fallback Chain

Four tiers, increasing weight. Move to the next only when the previous returns insufficient content (<200 chars, paywall fragments, or errors):

1. **Instapaper get_text** (`fetch_text.py`) -- fastest, content already extracted at save time. Works for most sites.
2. **trafilatura** (`skills/trafilatura/fetch_page.py`) -- strong fallback, handles soft paywalls and most article sites without a browser. Successfully extracts from sites Instapaper misses (e.g. Seattle Times).
3. **web_fetch** (built-in tool) -- catches JS-rendered sites and some sources that trafilatura misses (e.g. The Verge, Pitchfork, Windows Central). Use with `--max-chars 5000` equivalent.
4. **CDP browser** (agent-browser) -- last resort. Real browser with AdGuard + Bypass Paywalls Clean filter list. Handles JS-rendered content and paywalled sites that earlier tiers can't crack. Open URL, wait for render, extract `document.body.innerText` or use readability.

Do NOT use scrapling in this chain -- trafilatura covers its use cases and the CDP browser is strictly more capable for the remaining edge cases.

### Pointer Page Detection

Some bookmarks point to aggregator/link pages rather than the actual article (e.g., 3 Quarks Daily, Longform, Kottke). These pages have very short extracted content but contain an outbound link to the real article on a different domain.

**Detection:** If extracted content is <200 chars and contains one or more outbound links to a different domain, follow the most prominent outbound link and re-extract from that URL using the fallback chain above.

**When to apply:** After the first extraction attempt returns <200 chars. Do not apply if the content is genuinely short (check if the page looks like a stub/aggregator vs. an actual short article).

### Digest Workflow (recent saves)

For producing daily or weekly reading digests in the Obsidian vault, follow:

`references/digest-workflow.md`

This handles the full pipeline: extract -> summarize -> curate -> write to `00_Inbox/AI/Instapaper_Digests/`.

Triggers: "instapaper digest", "reading digest", "digest my saves", "what did I save this week"

### HN Extraction Detail

HN bookmarks require two-part extraction:
1. **Discussion**: `hackernews` skill fetches post metadata + comments
2. **Linked article**: The `url` field in the hackernews response points to the external article. Extract that separately using the article fallback chain above.

Both pieces are needed for a complete digest entry.

**Never pass `--bookmark-id` when extracting an HN bookmark's linked article.** Instapaper's
cached text for an HN bookmark is the *comment page*, not the article, and it is long enough
to pass as a successful extraction. `fetch_and_extract.py` now guards against this (it skips
the Instapaper cache for `news.ycombinator.com` URLs and rejects text matching the HN
comment-page pattern), but passing the linked URL alone is still the correct call. Sanity
check any HN result whose content opens with `NNN points by <user> ... | hide | past |
favorite`.

## Conventions

- Run from the workspace root (`~/.openclaw/workspace`).
- Present results as readable summaries. Do not dump raw JSON at the user.
- When listing bookmarks, show title + domain + time saved -- not raw URLs.
- For digest workflows, batch by source type to minimize skill switching.
- For HN posts: always fetch both the discussion AND the linked article content.
- Do NOT re-implement fetching logic from companion skills -- delegate to reddit, hackernews, youtube-transcript, or trafilatura as documented above.
- Confirm before any destructive operations (delete, archive in bulk).
- **Never auto-archive after digests.** Always ask the user explicitly and only archive on confirmation.
- Mark extraction results with quality indicators in chat: "ok" (>200 chars), "partial" (<200 chars), "failed" (0 chars or error). These go in the pipeline and chat reports, not in the Obsidian digest.

## Authentication

Env vars in `~/.openclaw/.env`:

| Variable | Description |
|---|---|
| `INSTAPAPER_KEY` | OAuth consumer key |
| `INSTAPAPER_SECRET` | OAuth consumer secret |
| `INSTAPAPER_USER` | Account username (email) |
| `INSTAPAPER_PASS` | Account password |

## Requirements

- `uv` package manager.
- `requests` Python library (managed via inline uv script deps).
- Env vars above must be set.

## Troubleshooting

### Instapaper get_text returns empty
Some sites block Instapaper's crawler or are paywalled. Fall through to trafilatura, then CDP browser.

### trafilatura returns truncated content
Usually means the site requires JS rendering. Fall through to CDP browser.

### CDP browser extraction
Requires the remote Chrome at `<home-server>:9222` to be running. AdGuard with Bypass Paywalls Clean filter list handles most soft paywalls. Hard paywalls (NYT, WSJ) require an active subscription in the browser profile.
