---
name: memory-checkpoint
description: |
  Fire-and-forget checkpoint capture from the recent PI session. Triggered automatically by the session_before_compact hook and the session_shutdown hook, and by the manual /checkpoint command as an alpha fallback. Reads the segment of the session since the last checkpoint and produces 0-3 single-line observations worth keeping for future sessions. At session_shutdown, may emit a [resume YYYY-MM-DD HH:MM] line as the first observation if the user appeared to be mid-task. Captures route through the same context-aware target selection as memory-note (active plan > project notes > weekly inbox). Use only when explicitly invoked; this skill is not meant for the LLM to fire on its own.
disable-model-invocation: true
---

# memory-checkpoint

This skill captures durable observations from the session-just-passed. It runs in two contexts:

1. **Pre-compact** - PI is about to compress the conversation. Anything worth keeping must be written to disk now or it is gone.
2. **Shutdown** - the session is ending. Same goal, plus the special `[resume]` line if work was interrupted mid-task.

The skill is also reachable manually via `/checkpoint` for the case where a hook did not fire when it should have. The skill body is identical in all three contexts; only the mode varies.

## Operating principles

The window is small. Do not try to be clever. Capture raw facts; let `/dream` consolidate them later.

- Aim for 0-3 lines total. Zero lines is a valid outcome.
- One line per fact. Append-only.
- Present tense, declarative.
- Skip anything that:
  - Was already captured this session via `/note` or memory-note.
  - Is fully derivable from the code or git diff.
  - Is transient conversation scaffolding.
  - Is the same tool output the user just saw.

## Workflow

### Step 1 - Detect mode

Read the entry written by the calling hook. If you cannot determine mode, treat it as `manual`.

### Step 2 - Pull the segment

Read recent turns via `ctx.sessionManager.getBranch()` since the last `memory-checkpoint-marker` entry. If no marker exists yet, use the session start as the lower bound, or the entire session when invoked with `/checkpoint --all`.

### Step 3 - Read context

Call `memory_get_context()`. Routing follows the standard precedence (plan > project notes > weekly inbox). Most checkpoint lines land in a single target: the active context.

### Step 4 - Identify observations

Re-read the segment with the question "what would a future session benefit from knowing?" in mind. Good candidates:

- A decision the user made, with the reason.
- A non-obvious gotcha and its resolution.
- A meaningful change of direction.
- A new external resource or configuration value.
- A plan that just completed and should be marked `status: completed`.

Less than three is good. Pick the highest-signal items and stop. If nothing qualifies, write zero lines and exit.

### Step 5 - Shutdown mode only: decide `[resume]`

If mode is `shutdown`, check whether the user looked mid-task: an unanswered question, unfinished tool call, or stated next step that was not taken. If yes, emit a `[resume]` line as the first observation:

```
- [resume 2026-05-22 17:42] next: finish the writer.ts fix; smol-toml roundtrip test was failing.
```

If unclear, omit `[resume]` rather than guess.

### Step 6 - Format

Each observation, one line:

```
- [auto YYYY-MM-DD HH:MM] <single-sentence observation>
```

Use the `[auto ...]` prefix so a later `git grep '\[auto'` distinguishes auto-captures from `/note` captures and `[resume]` lines.

### Step 7 - Write

For each line, call `memory_capture(file, line, section)`. Use the same target the user's deterministic `/note` would pick. Section is `## Log` for plan logs, `## Inbox` for weekly notes, omitted for project `notes.md`.

If a plan just completed, also call `memory_set_frontmatter(plan_file, "status", "completed")`, but only when the segment makes completion unambiguous.

### Step 8 - Update the marker

After writing, or even if zero lines were written, call `pi.appendEntry("memory-checkpoint-marker", { entryId: <current session entry id>, ts: <ISO timestamp> })`. The next checkpoint reads from this marker.

### Step 9 - Report

If invoked manually via `/checkpoint`, report the line count and targets via `ctx.ui.notify`. If invoked by a hook, stay silent.

## Examples

### Pre-compact, single fact

Mode: `pre-compact`. Context: project=pi-memory, plan=plans/v1-ext.

Segment shows: user spent 8 turns finding that `smol-toml` strips empty arrays; landed on the sentinel-string workaround; integrated it into writer.ts.

Output: 1 line to plan `plan.md` `## Log`:

```
- [auto 2026-05-22 14:30] smol-toml strips empty arrays; workaround = ["__empty"] sentinel + filter on read.
```

### Shutdown, mid-task

Mode: `shutdown`. Context: project=pi-memory, plan=plans/v1-ext.

Segment shows: user was debugging a failing roundtrip test in writer.ts; conversation ended after a `/quit` without resolution.

Output: 2 lines to plan `plan.md` `## Log`:

```
- [resume 2026-05-22 17:42] next: finish writer.ts roundtrip test; suspect the sentinel filter runs before deserialize.
- [auto 2026-05-22 17:42] writer.ts roundtrip test failing with sentinel filter applied pre-deserialize.
```

### Manual /checkpoint, nothing to capture

User invokes `/checkpoint` mid-session. Last 20 turns were `/recall` calls and reading docs: pure exploration, no decisions or discoveries.

Output: 0 lines. Update the marker and report `checkpoint: nothing to capture (0 lines).`

## What this skill MUST NOT do

- Do not trigger from natural conversation. This skill is hook-driven and `disable-model-invocation: true` is set on purpose.
- Do not write more than 3 lines.
- Do not write to multiple targets. Pick the highest-precedence single target from `memory_get_context`.
- Do not ask the user permission.
- Do not try to compress long sessions. Raw facts; `/dream` consolidates.
- Do not echo tool output or conversation scaffolding.
- Do not read or modify files outside the configured vault root.
