---
name: align-workspace
description: >
  Audit and align the 6 workspace markdown files (SOUL.md, IDENTITY.md,
  HEARTBEAT.md, AGENTS.md, TOOLS.md, USER.md) with their intended purpose
  and recent session context. Compares current files against the official
  OpenClaw templates, analyzes recent chat sessions for missing context,
  and proposes targeted updates. Uses parallel subagents for session analysis.
  Use when the user says "align workspace", "audit workspace files",
  "update workspace from sessions", "check workspace alignment",
  "workspace review", "are my workspace files up to date", "check workspace",
  or "sync templates".
---

# Align Workspace

Audit the 6 workspace markdown files against their official templates and recent session history, then propose targeted alignment updates. Uses parallel subagents for efficient session analysis across 30 days.

## Execution

### Step 1: Read current workspace files

Read all 6 files from the workspace root:

- `SOUL.md` -- agent personality, values, boundaries
- `IDENTITY.md` -- agent name, vibe, avatar
- `HEARTBEAT.md` -- periodic check tasks
- `AGENTS.md` -- workspace conventions, memory, red lines, group chat rules
- `TOOLS.md` -- environment-specific notes, CLI inventory, research patterns
- `USER.md` -- human's profile, preferences, work/personal context

### Step 2: Fetch official templates

Fetch each template from the OpenClaw docs to understand intended purpose and structure:

```
https://docs.openclaw.ai/reference/templates/SOUL
https://docs.openclaw.ai/reference/templates/IDENTITY
https://docs.openclaw.ai/reference/templates/HEARTBEAT
https://docs.openclaw.ai/reference/templates/AGENTS
https://docs.openclaw.ai/reference/templates/TOOLS
https://docs.openclaw.ai/reference/templates/USER
```

Use `web_fetch` for each URL. Extract the template structure, required sections, and guidance notes.

### Step 3: Extract session context

Run the extraction script for the past 30 days in a single call:

```bash
uv run skills/digest-day/scripts/extract_sessions.py --days 30
```

Run from the workspace root (`~/.openclaw/workspace`). This outputs a JSON array with one entry per day.

Save the output and split into tier files for subagent processing:

```python
python3 -c "
import json
with open('/tmp/align-all.json') as f:
    days = json.load(f)
# Tier 1: last 7 days (high priority)
# Tier 2: days 8-14 (medium priority)
# Tier 3: days 15-30 (low priority, pattern scanning only)
for i, tier_days in enumerate([days[-7:], days[-14:-7], days[:-14]]):
    with open(f'/tmp/align-tier{i+1}.json', 'w') as out:
        json.dump(tier_days, out)
    sessions = sum(d['sessionCount'] for d in tier_days)
    print(f'Tier {i+1}: {len(tier_days)} days, {sessions} sessions')
"
```

Skip tiers with 0 total sessions.

### Step 4: Spawn subagents for session analysis

Spawn up to 3 subagents (one per tier) to analyze sessions for workspace-relevant signals:

**Tier 1 subagent (last 7 days, `medium` / Sonnet):**
```
sessions_spawn:
  mode: run
  agentId: medium
  lightContext: true
  label: align-tier1
  task: <prompt from references/tier1-subagent-prompt.md>
```

**Tier 2 subagent (days 8-14, `medium` / Sonnet):**
```
sessions_spawn:
  mode: run
  agentId: medium
  lightContext: true
  label: align-tier2
  task: <prompt from references/tier2-subagent-prompt.md>
```

**Tier 3 subagent (days 15-30, `small` / Flash):**
```
sessions_spawn:
  mode: run
  agentId: small
  lightContext: true
  label: align-tier3
  task: <prompt from references/tier3-subagent-prompt.md>
```

Spawn all in parallel, then `sessions_yield` to wait for results.

Each subagent reads its tier file and extracts workspace-relevant signals (see prompt templates for specific instructions per tier).

### Step 5: Analyze gaps (main agent)

After subagents return, the main agent aggregates findings and compares against the workspace files and templates. For each of the 6 files, assess:

1. **Template alignment** -- Does the file's structure match its intended purpose per the official template? Are any template-recommended sections missing or misused?
2. **Session-derived context** -- Is there information from recent sessions that should be reflected but isn't? Focus on:
   - Corrections the user made to the agent's behavior
   - New tools, workflows, or skills adopted
   - Changes in work context, projects, or personal interests
   - Stated preferences (communication style, formatting, language)
   - Frustrations that suggest missing guardrails
3. **Staleness** -- Is any existing content outdated based on recent sessions? (e.g., tools removed, workflows changed, preferences reversed)
4. **Duplication** -- Is the same information repeated across files or duplicated with specific skill definitions? Workspace files should not repeat what lives in a `SKILL.md`.

### Step 6: Present findings

Show the user a structured report:

```
## Alignment Report

### SOUL.md
- **Template alignment:** [OK / issues]
- **Gaps:** [list of missing context from sessions]
- **Stale content:** [list of outdated items]
- **Proposed changes:** [specific edits, additions, or removals]

### IDENTITY.md
...
(repeat for all 6 files)

### Cross-file issues
- **Duplications:** [items repeated across files or with skills]
- **Contradictions:** [conflicting guidance between files]
```

For each proposed change, show the specific edit (what to add/remove/modify and where) and **why** -- a one-line justification linking to a concrete session signal, a factual correction, or a clear behavioral improvement. If you can't articulate why in one line, the change probably isn't worth proposing. Keep proposals terse -- breadcrumbs, not essays.

**Do not make any changes.** Wait for the user to approve, reject, or modify each proposal.

### Step 7: Apply approved changes

Only after the user explicitly approves (all or specific items), apply the changes to the workspace files. Show a summary of what was changed after applying.

## Reference

| Path | Purpose |
|---|---|
| `skills/digest-day/scripts/extract_sessions.py` | Shared session extraction script (supports `--days N`) |
| `references/tier1-subagent-prompt.md` | High-priority subagent prompt (last 7 days, full analysis) |
| `references/tier2-subagent-prompt.md` | Medium-priority subagent prompt (days 8-14, corrections + preferences) |
| `references/tier3-subagent-prompt.md` | Low-priority subagent prompt (days 15-30, major patterns only) |

## Conventions

- **No changes for the sake of changes.** Every proposed edit must serve a clear, justifiable purpose. "Aligning with template" is not sufficient reason alone -- the template is guidance, not a spec. Only propose additions, corrections, or removals that would materially improve the agent's behavior, the user's experience, or prevent a concrete problem.
- **Additions:** Only if something is genuinely missing and its absence has caused or would cause confusion, missed context, or wrong behavior.
- **Corrections:** Only if existing content is factually wrong, outdated, or actively misleading.
- **Removals:** Only if content is duplicated elsewhere (e.g., in a SKILL.md), contradicts other files, or is stale enough to cause wrong behavior.
- **Leave good-enough alone.** If a file works and the user hasn't expressed friction with it, don't propose restructuring it to match a template more closely.
- No emojis in any output.
- Never fabricate session context -- only cite what the extraction script returns.
- Workspace files should complement skills, not duplicate them. If something belongs in a SKILL.md, say so instead of adding it to a workspace file.
- Respect the template's intended purpose for each file. Don't put TOOLS.md content in AGENTS.md or vice versa.
- Present the full report in one pass. Don't drip-feed findings file by file.
- The extraction script is shared with digest-day -- do not copy it.
- **Subagent selection:** use `agentId: medium` for tiers 1-2 (Sonnet; needs judgment about what's workspace-relevant), and `agentId: small` for tier 3 (Flash; just pattern scanning over a large window).

## Requirements

- `uv` (for running the extraction script)
- `skills/digest-day/scripts/extract_sessions.py` -- shared script for extracting session transcripts
- `web_fetch` tool access (for fetching official templates from docs.openclaw.ai)
- `sessions_spawn` tool (for parallel subagent orchestration)

## Troubleshooting

### Template fetch fails
The docs site may be down or URLs may have changed. If a template can't be fetched, skip the template comparison for that file and note it in the report. The skill can still analyze session context and cross-file issues without templates.

### Too many sessions to process
The subagent pattern handles this well -- each tier's subagent processes its window independently. If a single tier is still too large (e.g., tier 3 with 16 days of heavy activity), the main agent can further split it.

### No sessions found
If the extraction script returns 0 sessions across all dates, skip the session analysis and only perform template alignment and cross-file checks.

### Subagent returns irrelevant signals
The main agent curates all subagent output before presenting to the user. Filter out signals that don't map to any workspace file's purpose.
