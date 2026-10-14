---
name: memory-dream
description: |
  Periodic consolidation pass over the memory vault. Manual invocation only (via /dream); never auto-fired. Reads files modified during the awake period (since last .last_dream.marker mtime), scoped to <vault>/80_AI/ and <vault>/10_Weekly/. Spawns the memory-dream-worker subagent via pi-subagents to perform five operations: resolve contradictions, promote repeated themes to domains, summarise oversized notes, enrich links and frontmatter, and surface ideas from session JSONLs. Writes results to <vault>/80_AI/dreamlog.md. Reversible (one git/jj commit per dream).
disable-model-invocation: true
---

# memory-dream (STUB - Phase 4 will implement)

Skill registered for description-only loading in Phase 1. Manual-only; never auto-invoked.

When implemented, this skill's workflow will:

1. Resolve awake-period file list within `[dream].scope` (default: `80_AI/`, `10_Weekly/`).
2. Spawn the `memory-dream-worker` subagent via pi-subagents.
3. Pass the file list as the worker's scope.
4. Wait for subagent completion; receive structured edit plan and dreamlog section.
5. If `--dry-run`: print plan and do not apply edits.
6. Otherwise: apply edits, append the dreamlog section, and touch `.last_dream.marker`.

See `docs/proposal.md` for the design.
