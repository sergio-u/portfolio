---
name: digest-this
description: >
  Digest the current session into the Obsidian daily note. Synthesizes
  the ongoing conversation into key findings and appends them under
  the Work and Personal sections. Use when the user says "digest this",
  "digest this session", "save this to daily note", "add this to my note",
  "log this session", "capture this", "summarize session", "what did we do",
  or "session summary".
---

# Digest This

Synthesizes the current conversation into the Obsidian daily note. No script needed -- the conversation is already in context.

## Execution

### Step 1: Synthesize

Review the current conversation and act as an **aggressive filter**. The daily note is limited real estate; treat every bullet like it costs money.

**Always skip:**
- Q&A and troubleshooting exchanges (the user asked, got an answer, moved on)
- Routine operations (file reads, installs, config changes, debugging iterations)
- Requests to remember/save something to a skill or memory (already persisted elsewhere)
- Tool call chatter, error-retry loops, clarification Q&A
- Greetings, meta-discussion about how to proceed
- Anything the user could re-derive from code, git, or tool history

**Keep only what passes this test:** "Would I be confused or lose track of something if this weren't written down?" Think breadcrumbs, not changelog. Each item should jog memory, not document a procedure.

**Classify as work or personal** using the heuristic in `USER.md` (section "Work vs Personal Heuristic").

**Rank by importance.** Include only items that earn their space:
- **~5 items max** for a typical session
- A big session might warrant ~8
- A routine session with no surprises might warrant 1-2 or zero

**Format: one line per item, terse.** Fragments, not full sentences. Think "commit message" brevity.

```markdown
### Session Digest
- Rewrote digest-day skill -- flat list format, aggressive filtering, merged inbox triage into single review pass
- DRY issue: digest skills duplicated obsidian daily note template; now reference obsidian skill instead
```

**Format rules:**
- Flat list under `### Session Digest` -- no sub-headers. One list, ranked by importance.
- Use `[[wiki-links]]` for vault notes referenced or worth creating
- No emojis
- If this session was routine with no lasting insight, say so and don't write anything

### Step 2: Present for review

Show the synthesized digest to the user before writing anything. Format it exactly as it would appear in the daily note.

If the daily note has an `## Inbox` section with content, include the proposed triage in the same review -- do not prompt separately.

### Step 3: Update daily note

Vault root: `~/Documents/Sync/Notebook/2026-H1`

Follow the obsidian skill's daily note template and formatting conventions. If the daily note doesn't exist, create it using that template.

1. Read `10_Daily/YYYY-MM-DD.md` (today's date).

2. Check if `### Session Digest` already exists under `## Work` or `## Personal`.
   - If yes: merge with the new one. Deduplicate, keep the better-worded version, add genuinely new items. Show merged result in Step 2.

3. Insert `### Session Digest` content:
   - Work items under `## Work`, personal items under `## Personal`
   - Place digest after existing content, before the next `---` or `## ` header
   - If all items are work (common), only add digest under `## Work`

4. If inbox was triaged: move items and clear `## Inbox` content (keep header and `---`).

## Conventions

- **Breadcrumbs, not changelog.** Each bullet should jog memory about something that matters. If this session was routine Q&A, skip it entirely.
- No emojis in any output.
- Never dump raw conversation text -- always synthesize.
- Always present the digest for review before writing to the vault.
- Follow the obsidian skill's formatting conventions (wiki-links, bold timestamps, `-` for lists, `---` separators).

## Troubleshooting

### Vault path doesn't exist
Check `skills/obsidian/SKILL.md` for the current path -- it may have changed on semester rollover.

### Daily note has unexpected format
Read the full file before editing. Insert at the most logical position. Preserve all existing content.
