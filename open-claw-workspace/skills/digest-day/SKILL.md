---
name: digest-day
description: >
  Summarize openclaw sessions into a weekly digest in the Obsidian vault. Primary mode is weekly
  digest (last 7 days) using parallel subagents, but also supports single-day runs.
  Use when the user says "digest day", "digest week", "weekly digest", "digest sessions",
  "update daily notes", "summarize this week", "summarize today's sessions",
  "what did we work on", "session summary", "daily digest", "weekly summary",
  or "what happened this week".
---

# Digest Day

Extracts and synthesizes openclaw session transcripts into a weekly Obsidian digest. Uses parallel subagents (one per day) for weekly digests.

## Execution

### Step 1: Extract sessions

```bash
uv run skills/digest-day/scripts/extract_sessions.py [--date YYYY-MM-DD] [--days N]
```

Run from the workspace root (`~/.openclaw/workspace`). Defaults to today's date. With `--days N`, extracts N consecutive days ending on `--date` and outputs a JSON array (one entry per day). Single-day mode (default) outputs a flat object.

The script collects sessions from two sources:
- `"active"` — current sessions from the `openclaw sessions` index
- `"archived"` — sessions cleared via `/new` or `/reset` (full JSONL transcripts preserved as `.reset.` files)

Multiple sessions from the same channel on the same day (e.g., after a `/new`) are separate context windows — treat each independently.

If the script fails or returns 0 sessions, tell the user and stop. Do not fabricate a digest.

### Step 2: Save per-day JSON files

For multi-day runs, save each day's extracted JSON to a temp file:

```bash
/tmp/digest-YYYY-MM-DD.json
```

Use a Python one-liner to split the array output into individual files:

```bash
python3 -c "
import json, sys
with open('/tmp/digest-all.json') as f:
    days = json.load(f)
for day in days:
    with open(f'/tmp/digest-{day[\"date\"]}.json', 'w') as out:
        json.dump(day, out)
print(f'Wrote {len(days)} day files')
"
```

### Step 3: Spawn subagents (multi-day mode)

For weekly digests, spawn two types of subagents:

**A. Per-day session subagents (one per day):**

```
sessions_spawn:
  mode: run
  agentId: medium
  lightContext: true
  label: digest-YYYY-MM-DD
  task: <subagent prompt from references/subagent-prompt.md>
```

**B. Daily notes subagent (one for all days):**

Scan `10_Daily/YYYY-MM-DD.md` for each day in the range. If any daily notes exist with content (beyond the empty template), spawn a single subagent that reads all of them and extracts anything not already covered by session transcripts -- manual notes, inbox items, things jotted down outside of openclaw sessions.

```
sessions_spawn:
  mode: run
  agentId: medium
  lightContext: true
  label: digest-daily-notes
  task: <daily notes prompt from references/daily-notes-subagent-prompt.md>
```

Skip this subagent if no daily notes exist for the date range.

Spawn all subagents in parallel, then `sessions_yield` to wait for results. All completions arrive as push events. Note: max concurrent subagents is configurable via `agents.defaults.subagents.maxChildrenPerAgent` (currently 10).

For single-day runs (1-2 sessions, light day), skip subagents and synthesize directly in the main agent.

**Subagent heuristic:** Use subagents when processing 3+ days or when any single day has 3+ sessions. For a single quiet day, just do it inline.

### Step 4: Aggregate and curate

After all subagents return, the main agent:

1. Reviews each day's digest for quality — trim over-detailed items, cut noise that slipped through
2. Detects cross-day threads: topics that span multiple days (e.g., "Music Assistant setup Apr 13 → 14", "Sprint sync work Apr 17-18")
3. Writes the complete curated digest to the weekly digest file
4. Presents a concise completion summary to the user with the output path

Do not ask for confirmation before writing the weekly digest. The digest is an internal Obsidian artifact and can be revised later. User review is useful, but should happen after the file exists.

### Step 5: Curate the subagent output

Subagents do first-pass filtering but the main agent is the final editor. Apply these checks:

- **Too many items?** A subagent returning 8+ items probably isn't filtering hard enough. Trim to the strongest 3-5.
- **Implementation details leaking?** "Refreshed PATs", "moved items between iterations", "updated config file" — these are steps, not outcomes. Collapse into the parent action.
- **Troubleshooting noise?** Skip resolved debugging unless it leaves durable state or context the user would need later: config changed, model/provider workaround chosen, a persistent bug identified, or a future action remains.
- **Missing personal items?** Subagents sometimes focus on the "louder" work sessions and miss personal items from the same day. Cross-check against the session list.
- **Duplicate across days?** If the same project appears on consecutive days, keep only the most informative entry unless there's a genuine progression worth noting.
- **Relevance checkpoint:** The current ranking process is good when `medium` (Sonnet) subagents are used and the main agent does this curation pass. Do not redesign ranking unless weekly digests start feeling noisy again.

### Step 6: Write weekly digest

Vault root: `~/Documents/Sync/Notebook/2026-H1`

Output is a single weekly digest file:

```
35_AI_Summaries/Weekly Digests/Session Digest YYYY-MM-DD to YYYY-MM-DD.md
```

Format:

```markdown
# Session Digest: Mon DD - Mon DD, YYYY

## Cross-day Threads
- Thread description spanning dates

---

## Day, Month DDth
### Work
- item
### Personal
- item

---

## Day, Month DDth
### Personal
- item

---

...
```

Rules:
- Cross-day threads section goes first -- this is the highest-value part of the weekly view
- Each day gets its own `## ` section with the full day name and date
- Omit `### Work` or `### Personal` sub-headers if a day has no items in that category
- Days with nothing worth recording get a single line: "Nothing worth recording"
- Separate days with `---`
- If daily notes had content not covered by sessions, merge those items into the appropriate day

### Step 7: Offer vault distribution

After writing the digests, ask: "Want me to scan the vault for related notes?"

If the user says yes:

1. Get vault file listing:
   ```bash
   fdfind -e md --exclude .obsidian ~/Documents/Sync/Notebook/2026-H1
   ```

2. For files with names related to digest topics, read their first 10 lines.

3. Suggest (present all at once, let user pick):
   - Existing notes worth linking to/from the daily note
   - Existing notes worth appending new context to
   - New note titles with a 2-3 line outline for topics deserving their own page

4. Only write after explicit per-item confirmation.

## Filtering Rules

These rules apply to both subagents and the main agent's curation pass.

**Always skip:**
- Q&A and troubleshooting exchanges (the user asked, got an answer, moved on)
- Routine operations (file reads, installs, config changes, debugging iterations)
- Requests to remember/save something to a skill or memory (that info is already persisted elsewhere)
- Tool call chatter, error-retry loops, clarification Q&A
- Greetings, meta-discussion about how to proceed
- Anything the user could re-derive from code, git, or tool history

**Keep only what passes this test:** "Would I be confused or lose track of something if this weren't written down?" Think breadcrumbs, not changelog. Each item should jog memory, not document a procedure.

**Worth noting (not routine):**
- New skill or workflow created
- Significant purchase decisions (not trivial add-ons)
- Financial/legal decisions (tax, FBAR, etc.)
- Infrastructure changes that affect multiple tools
- Project plans or system designs committed to vault/files

**Not worth noting (routine Q&A):**
- One-off lookups (keyboard shortcuts, CLI flags, product comparisons that didn't lead to a purchase)
- Troubleshooting that resolved without lasting changes
- Gaming, casual recommendations, trivia
- Purchases under ~$20 that are obvious (film, adapters, spacers)

**Classify as work or personal** using the heuristic in `USER.md` (section "Work vs Personal Heuristic"). A single session can produce both work and personal items. The extraction script includes a `topicId` field when the session comes from a Telegram forum topic:
- **Topic 624** = work (strongest signal, per USER.md)
- **Other topics / direct chat** = almost always personal
- **Topic 46** = ignore entirely (skip this session)
- **Voice/Even AI sessions** = lightweight; skip unless they contain decisions or actions not captured in other sessions from the same day
Use topic as the primary signal, then fall back to content-based classification.

**Rank by importance** within each category. Include only items that earn their space:
- A routine day: 1-3 items or even zero
- A typical day: 3-5 items
- A busy, eventful day: up to 8-10
- Let the quality test drive the count, not an arbitrary cap

**Format: one line per item, terse.** Use fragments, not full sentences. Think "commit message" brevity.

```markdown
### Session Digest
- Set up Spotify skill -- playlist sync working, artist matching needs `x && y` collaborator logic
- NetBird: stuck in userspace on Mac due to MS Defender network extension conflict; daemon/CLI version mismatch (0.62 vs 0.67) fixed via homebrew reinstall
- Discovered AnythingLLM has OpenAPI docs at `/api/docs` -- useful for knowledge-base skill
```

**Format rules:**
- Flat list under `### Session Digest` -- no sub-headers (Log/Learnings/Open/etc). One list, ranked by importance.
- Use `[[wiki-links]]` for vault notes referenced or worth creating
- No emojis
- If the entire day was routine Q&A with no lasting insight, say "Nothing worth recording today" and skip writing to the vault

## Reference

| Path | Purpose |
|---|---|
| `openclaw sessions --json` | Active session index (sessionId, key, kind, updatedAt) |
| `~/.openclaw/agents/main/sessions/*.jsonl` | Active session transcripts |
| `~/.openclaw/agents/main/sessions/*.jsonl.reset.*` | Archived session transcripts |
| `~/Documents/Sync/Notebook/2026-H1` | Obsidian vault root |
| `skills/obsidian/SKILL.md` | Vault structure, daily note template, formatting rules |
| `references/subagent-prompt.md` | Prompt template for per-day session subagent |
| `references/daily-notes-subagent-prompt.md` | Prompt template for daily notes subagent |
| `35_AI_Summaries/Weekly Digests/` | Weekly digest output folder |

## Conventions

- **Breadcrumbs, not changelog.** Each bullet should jog memory about something that matters, not document what happened. If a whole session was routine Q&A, skip it entirely.
- No emojis in any output.
- Never dump raw transcript text -- always synthesize.
- The script already filters out sessions with fewer than 3 user messages.
- Write the curated weekly digest to the vault without asking for confirmation first; then report the path and offer follow-up edits if needed.
- Vault distribution is a separate opt-in step -- never auto-scan.
- Follow the obsidian skill's formatting conventions (wiki-links, bold timestamps, `-` for lists, `---` separators).
- **Weekly digest is the default mode.** When the user says "digest" without specifying, default to last 7 days.
- **Subagent agentId: `medium` (Sonnet).** `small`/Flash is too permissive with filtering; `medium` applies the quality test reliably.

## Requirements

- `uv` (for running the extraction script)
- `skills/digest-day/scripts/extract_sessions.py` -- extracts session transcripts from active and archived session files
- Access to `~/.openclaw/agents/main/sessions/` (session transcript storage)
- `sessions_spawn` tool (for parallel subagent orchestration)

## Troubleshooting

### Script returns 0 sessions
The user may not have had qualifying sessions today (each needs 3+ user messages). Check the date with `--date` flag. Archived sessions use session start time, not reset time, so a session started yesterday but reset today won't appear under today.

### Vault path doesn't exist
The vault root may have changed (semester rollover). Check `skills/obsidian/SKILL.md` for the current path.

### Daily note has unexpected format
If the daily note was manually edited and doesn't match the expected template, read it fully before editing. Insert content at the most logical position rather than failing. Preserve all existing content.

### Subagent returns too many items
The main agent is the final editor. Trim aggressively -- subagents err on the side of inclusion, main agent err on the side of exclusion.

### Subagent misses personal items
Cross-check the session list. If a day had sessions on both topic 624 and direct chat, but the subagent only returned work items, the personal sessions may have been filtered too aggressively.
