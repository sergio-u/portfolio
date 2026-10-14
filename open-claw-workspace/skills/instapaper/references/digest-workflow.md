# Instapaper Digest Workflow

Produce a readable digest of recent Instapaper saves in the Obsidian vault.

## Invocation

Trigger when the user asks for an "instapaper digest", "reading digest", "digest my saves", "what did I save this week", or similar. Supports flexible time ranges.

## Parameters

| Param | Default | Description |
|---|---|---|
| hours | 24 | Time window (24 = daily, 168 = weekly) |
| target | daily | "daily" or "weekly" -- affects output format and file naming |

Default to daily (24h) unless the user asks for a weekly digest.

## Output Location

```
~/Documents/Sync/Notebook/2026-H1/00_Inbox/AI/Instapaper_Digests/
```

- Daily: `YYYY-MM-DD.md`
- Weekly: `Week of YYYY-MM-DD.md` (Monday of the week)

## Architecture Overview

Three rounds: Extract → Summarize → Curate.

```
┌─────────────────────────────────────────────┐
│ Main Agent                                   │
│  1. list_bookmarks --hours N --classify      │
│  2. Group by source_type                     │
│  3. Save groups to /tmp/                     │
│                                              │
│  Round 1: Extract (parallel subagents)       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│  │ articles │ │ hn+links │ │ reddit   │    │
│  │ extract  │ │ extract  │ │ extract  │    │
│  └──────────┘ └──────────┘ └──────────┘    │
│  + youtube transcript subagent if needed     │
│                                              │
│  Round 2: Summarize (parallel subagents)     │
│  ┌──────────┐ ┌──────────┐                  │
│  │ batch 1  │ │ batch 2  │ ...              │
│  │ 8-10 items│ │ 8-10 items│                 │
│  └──────────┘ └──────────┘                  │
│                                              │
│  Round 3: Curate (main agent)               │
│  - Topic grouping & merging                  │
│  - Paragraph prose with inline links         │
│  - Write Obsidian note                       │
└─────────────────────────────────────────────┘
```

## Step-by-Step

### Step 1: List and classify bookmarks

```bash
cd ~/.openclaw/workspace
source ~/.openclaw/.env 2>/dev/null
export INSTAPAPER_KEY INSTAPAPER_SECRET INSTAPAPER_USER INSTAPAPER_PASS
uv run skills/instapaper/scripts/list_bookmarks.py --hours N --classify
```

Save the full output to `/tmp/instapaper-digest-bookmarks.json`.

Count bookmarks per source_type. If 0 bookmarks, tell the user and stop.

### Step 2: Prepare extraction batches

Split bookmarks into groups by source_type. Save each group:
- `/tmp/instapaper-extract-articles.json`
- `/tmp/instapaper-extract-hackernews.json`
- `/tmp/instapaper-extract-reddit.json`
- `/tmp/instapaper-extract-youtube.json`

Use a Python one-liner or inline script:
```python
import json
with open('/tmp/instapaper-digest-bookmarks.json') as f:
    bookmarks = json.load(f)
groups = {}
for b in bookmarks:
    t = b.get('source_type', 'article')
    groups.setdefault(t, []).append(b)
for t, items in groups.items():
    with open(f'/tmp/instapaper-extract-{t}.json', 'w') as f:
        json.dump(items, f)
    print(f'{t}: {len(items)} items')
```

**Always coerce `bookmark_id` to `int` when comparing or merging.** The YouTube path
emits string ids while every other source emits integers, so naive set membership
silently drops items. This cost 12 YouTube items on a real run -- they extracted fine
and vanished at merge time. Use `int(x['bookmark_id'])` on both sides of every
comparison, and reconcile counts (see Step 5).

### Step 3: Round 1 -- Extract (parallel subagents)

Spawn one subagent per non-empty source group. Use the extract subagent prompt from `references/extract-subagent-prompt.md`.

```
sessions_spawn:
  mode: run
  agentId: small
  model: luna
  lightContext: true
  label: instapaper-extract-{type}
  task: <extract subagent prompt with group-specific instructions>
```

**Model selection.** Always pin `model` explicitly; do not rely on tier defaults.
On a real run the default `small` tier (gemini-3-flash) rejected every single request
at 0 tokens with a provider schema error, killing five subagents before any work
started. Current working defaults: `luna` for extraction (`small`), `terra` for
summarization (`medium`). If a spawn fails instantly at ~0 tokens, that is a model
routing problem, not a prompt problem -- switch models rather than retrying.

**Subagent responsibilities by type:**

| Type | Extraction method |
|---|---|
| article | `fetch_and_extract.py` with `--bookmark-id` and `--max-chars 5000` |
| hackernews | hackernews skill `fetch_post.py` for comments + `fetch_and_extract.py` for linked article URL |
| reddit | reddit skill `fetch_post.py` -- comments ARE the content |
| youtube | youtube-transcript skill |

Each subagent writes its results to `/tmp/instapaper-extracted-{type}.json`.

After spawning all extraction subagents, `sessions_yield`.

**Never trust a subagent's completion report. Verify its output file on disk.**
Observed failure modes on a single real run: seven extraction subagents crashed
mid-task while reporting "completed"; several wrote no file at all; one reported 13
clean extractions whose `content` was entirely HN comment text. Treat the file, not
the message, as the completion signal:

```python
import json, glob
for f in sorted(glob.glob('/tmp/instapaper-extracted-*.json')):
    try:
        d = json.load(open(f))
    except Exception as e:
        print('BAD', f, e); continue           # corrupt or partial write
    contaminated = sum(1 for x in d
                       if 'points by' in (x.get('content') or '')[:120])
    print(f, len(d), 'items', 'CONTAMINATED:', contaminated)
```

Check per chunk: file exists, parses as JSON, item count matches the input batch, and
no item's `content` opens with the HN comment-page pattern. Re-queue any gaps. Do not
run two writers against the same output path concurrently -- a subagent and a manual
recovery job racing on one file produced corrupt JSON on a real run.

### Step 4: Retry failed extractions

After all extraction subagents complete:

1. Read all `/tmp/instapaper-extracted-*.json` files
2. Collect items with `status: "failed"` or `char_count < 200`
3. For each failed item, retry extraction in the main agent using `web_fetch` with the bookmark URL (max 5000 chars)
4. If `web_fetch` returns usable content (>200 chars), update the item's content, char_count, status, and method
5. Filter out items that are still failed/empty after retry -- do not send them to summarization
6. Write the cleaned, merged list for batching

This step is fast (no subagents needed) and typically recovers 50-70% of failures from JS-rendered sites that trafilatura misses.

### Step 5: Round 2 -- Summarize (parallel subagents)

After retry and filtering:

1. Read all `/tmp/instapaper-extracted-*.json` files
2. Merge into a single list, coercing `int(x['bookmark_id'])` on every id
3. Reconcile before proceeding: `usable + failed == listed`. If the numbers do not
   add up, find the missing ids before spawning anything -- do not let items vanish
   silently between stages.
4. Split into batches of 8-10 items
5. Spawn summarization subagents using `references/summarize-subagent-prompt.md`

```
sessions_spawn:
  mode: run
  agentId: medium
  model: terra
  lightContext: true
  label: instapaper-summarize-{N}
  task: <summarize subagent prompt with batch content>
```

Each summarization subagent:
- Reads the raw extracted content for its batch
- Produces a 3-6 sentence summary per item (longer for interesting/novel, shorter for routine)
- Suggests 1-3 theme tags per item (e.g. "AI", "Seattle", "Music", "Dev Tools")
- Writes output to `/tmp/instapaper-summary-{N}.json`

After spawning, `sessions_yield`.

Verify summarizer output the same way as extraction: parse each
`/tmp/instapaper-summary-*.json`, count items against the batch input, and re-queue
missing ids. Summarizers stop early more often than they crash -- one batch wrote 5 of
10 items and reported success.

### Step 6: Round 3 -- Curate (main agent)

After all summarization subagents complete:

1. Read all `/tmp/instapaper-summary-*.json` files
2. Group items by topic similarity -- not by source type. An article, HN thread, and Reddit post about the same subject become one section.
3. For each topic group, write merged paragraph-style prose weaving all sources together with inline markdown links
4. Variable depth: rich topics (3+ sources, novel/interesting) get 2-3 paragraphs; single-source or lightweight items get 1-2 sentences
5. Order topics by richness (most sources first), then standalone items
6. Report extraction notes (failures, fallbacks, boilerplate) in chat only -- not in the digest
7. Present the complete digest for user review before writing

**Never write a URL from memory. Copy it from the record's `url` field.**
Composing prose invites plausible-looking, correctly-formatted, wrong URLs. On a real
run 87 of 122 links were fabricated this way and would have shipped silently. Verify
mechanically before presenting the digest, and fix every mismatch:

```python
import json, re, glob
real = set()
for f in glob.glob('/tmp/instapaper-summary-*.json'):
    for x in json.load(open(f)):
        real.add(str(x.get('url', '')).strip())
draft = open('/tmp/digest-draft.md').read()
links = re.findall(r'\[([^\]]+)\]\((https?://[^)]+)\)', draft)
bad = [(t, u) for t, u in links if u not in real]
print('links:', len(links), 'unverified:', len(bad))
for t, u in bad:
    print('  ', t[:50], u[:80])
```

Every markdown link must exactly match a `url` in the extracted records. If a record's
own stored URL is wrong (it happens), drop the line rather than publish a misleading
link.

### Step 7: Write to Obsidian

After user approval:

```
~/Documents/Sync/Notebook/2026-H1/00_Inbox/AI/Instapaper_Digests/YYYY-MM-DD.md
```

Trigger Syncthing rescan (see obsidian skill for the curl command).

### Step 8: Archive processed bookmarks

After the digest is written to the vault and the user has confirmed:

1. Ask: "Archive these N bookmarks on Instapaper?"
2. Only proceed on explicit confirmation
3. Archive using the bookmark IDs from the digest run:

```bash
cd ~/.openclaw/workspace
source ~/.openclaw/.env 2>/dev/null
export INSTAPAPER_KEY INSTAPAPER_SECRET INSTAPAPER_USER INSTAPAPER_PASS
uv run skills/instapaper/scripts/archive_bookmarks.py --from-file /tmp/instapaper-digest-bookmarks.json
```

This keeps the unread queue clean and prevents re-processing on the next run. Never archive before the digest is confirmed.

**Archive only what actually made it into the digest**, not the raw listing -- items that
failed extraction should stay unread for manual revisit (per user preference).

**`archive_bookmarks.py` exit codes are unreliable in both directions.** On a real run it
exited 0 with an empty log having archived only 109 of 196, then exited 1 having archived
all 87 remaining. Always verify by re-listing and intersecting:

```python
import json
unread = {int(x['bookmark_id']) for x in json.load(open('/tmp/post-archive-unread.json'))}
targeted = {int(x['bookmark_id']) for x in json.load(open('/tmp/archive-ids.json'))}
remaining = sorted(unread & targeted)
print('still unread:', len(remaining))   # re-run archive on these
```

## Digest Format

```markdown
# Instapaper Digest: [Month DDth, YYYY | Week of Month DDth]

> N articles processed. ~X min read.

## [Topic/Theme Name]

Paragraph-style summary merging all related sources into cohesive prose.
Interesting or novel topics get 2-3 paragraphs with more depth.
Lighter or routine items get 1-2 sentences.

Multiple sources on the same topic merge into one cohesive section -- an article from The Verge,
an HN discussion, and a Reddit thread about the same subject become one narrative, not three entries.

Sources:
- [Article Title](https://example.com)
- [HN Discussion](https://news.ycombinator.com/item?id=...)
- [Reddit Thread](https://reddit.com/r/...)

---

## [Next Topic]

Shorter topic with fewer sources gets a brief treatment.
A concise but informative summary -- enough for the reader to decide whether to read the original.

Sources:
- [Single Source Title](https://example.com)
```

## Format Rules

- No per-article headers -- articles merge into themed paragraph prose
- Source links go as a bullet list at the end of each topic section, NOT inline in the text
- Format: `- [Descriptive Title](https://url)`
- No separate Sources table at the end -- each section has its own sources
- No Threads section -- related articles across sources naturally merge into topic sections
- No Extraction Notes in the digest -- report those in chat only
- Variable depth: interesting/novel topics get 2-3 paragraphs; lighter items get 1-2 sentences
- Group by topic/area, not by source type (article/HN/reddit/youtube all merge if same topic)
- Topics ordered by richness (most sources/depth first), then standalone items
- Separate topic sections with `---`
- No emojis
- Read time target: ~20-30 min for a daily digest at speed-reading pace
- The goal is a "Reader's Digest" -- enough depth to decide whether to read the original, not just headlines

## Scaling Heuristics

Scale by **chunk size**, not by a fixed subagent count. Per-child runtime is the dominant
crash predictor: on a real run, 12-item chunks ran 4-7 minutes and 7 of 15 extraction
subagents died mid-task. Keep each child short.

**Rules:**

| Rule | Value |
|---|---|
| Items per extraction chunk | **8** (never exceed 10) |
| Items per summarization batch | 8-10 |
| Max concurrent children | 10 (waves beyond that) |
| Minimum group size to delegate at all | **8 items** |

- **Do not delegate groups smaller than 8 items.** Spawn overhead plus crash risk exceeds
  any parallelism benefit. Extract them in-process. (A 4-item youtube group and an 8-item
  reddit group were delegated on a real run for no gain.)
- **The parent is the retry engine, not a re-spawner.** Delegation is for the *first* pass.
  After verifying wave output on disk, extract remaining gaps in-process with a per-item
  checkpointed loop. On a real run that in-process loop handled ~93 items across 8 chunks
  with zero losses, while repeated re-spawning kept hitting the same failure mode.
- **One writer per output path, always.** Never let a subagent and a parent recovery loop
  target the same file; that race produced corrupt JSON on a real run. If the parent takes
  over a chunk, ignore the child's eventual output.
- **Extraction and summarization fail differently.** Extraction is subprocess-bound and
  long-running, so it crashes; summarization is short and mostly stops early instead. Apply
  the aggressive chunking to extraction; summarization batches of 8-10 are fine as-is.

Waves:
1. Extraction chunks, up to 10 concurrent
2. `sessions_yield`, then verify every output file on disk (see Step 3)
3. Gap-fill in-process rather than re-spawning
4. Summarization batches, up to 10 concurrent, `sessions_yield` between waves

## Conventions

- Always present the digest for review before writing to the vault
- Never fabricate summaries -- if extraction failed, note it
- Never fabricate URLs -- copy them from the record's `url` field and verify mechanically (Step 6)
- Mark partial extractions (<200 chars extracted) in chat when reporting to user
- Verify child output on disk before accepting any subagent's completion report
- For weekly digests, consider whether grouping by day or by theme works better for the volume. Default to theme grouping.
- This workflow delegates to companion skills (reddit, hackernews, youtube-transcript, trafilatura). Do not reimplement their logic.
