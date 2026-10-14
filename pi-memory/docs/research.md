# pi-memory Research Notes

This document records the current design conclusions for pi-memory after simplifying the context hierarchy to project and plan. Earlier experiments with a smaller nested planning level were removed because PI's todo plugin now owns fine-grained execution tracking.

## Design conclusion

pi-memory should store durable context, not task execution state.

- Project: durable area for project metadata, notes, and plans.
- Plan: durable area for a goal, decisions, and log entries.
- Domain: cross-cutting knowledge shared across projects or repos.
- Weekly inbox: fallback capture target when no project is active and raw dump target for messy daily links/snippets.
- Todo plugin: task-level execution, blockers, and step tracking.

This split keeps the memory vault high-signal and avoids competing task systems.

## Prior art patterns retained

### Markdown as source of truth

The vault remains ordinary markdown so it is easy to inspect, edit, grep, and version. Generated content should be append-only where possible.

### Explicit context loading

A small basic gateway loads automatically. Full project/plan/domain content loads only on `/set-context`, keeping prompt budget under user control.

### Per-repo sentinel state

The repo-local `.memory/config.toml` stores active project, active plan, active domains, repo name, and overrides. With jj, a private `[memory]` commit can make the context branch-local without pushing it.

### Deterministic primitives first

Commands and tools should have deterministic paths:

- capture line to resolved target
- set one frontmatter field
- search markdown
- list projects/domains
- resolve current/weekly/domain target
- set project/plan context

LLM skills layer on top, but the basic behaviors must remain usable without them.

### Manual consolidation

Dream remains manual. It should produce a reviewable edit plan, then apply bounded edits inside the managed vault roots.

## Current vault shape

```text
80_AI/
  projects/
    <project>/
      project.md
      notes.md
      plans/
        <plan>/
          plan.md
  domains/
    <tag>.md
  dreamlog.md
10_Weekly/
  <YYYY-Www>.md
```

## Current routing rules

1. Active plan -> `projects/<project>/plans/<plan>/plan.md` under `## Log`.
2. Active project -> `projects/<project>/notes.md`.
3. No active project -> weekly note under `## Inbox`.
4. `/dump` always writes to the weekly inbox, regardless of active context.
5. Smart routing may add a domain page as a second target.

## Current hook model

- `session_start`: build basic gateway and store it in session state.
- `before_agent_start`: inject latest gateway into the system prompt.
- `session_before_compact`: update checkpoint marker.
- `session_shutdown`: update checkpoint marker.
- `resources_discover`: expose skills according to config.

There is intentionally no per-turn memory hook. High-frequency work tracking belongs in the todo plugin.

## Current skill model

- `memory-note`: smart capture to active context and optional domains.
- `memory-recall`: recall-shaped natural language search.
- `memory-checkpoint`: hook/manual extraction of 0-3 durable observations.
- `memory-dream`: manual consolidation pass.

## Decision log

- Keep project/plan as the only memory hierarchy. Reason: task-level granularity overlaps with PI todo and created extra routing, cleanup, and prompt complexity.
- Keep deterministic `/note` even when smart routing exists. Reason: the user needs a guaranteed capture path.
- Keep Dream manual. Reason: consolidation edits should be reviewable and reversible.
- Keep weekly inbox fallback. Reason: captures without active context should not fail or force context selection.
- Add `/dump` plus dry-run `/organize-dump`. Reason: low-friction capture should not force classification; monthly review can avoid creating domains for one-offs and should not assume the current repo's active project.
- Keep repo-as-domain auto-loading when the domain file exists. Reason: repo-specific facts often matter outside a single project.

## Implementation notes

- Avoid adding new hierarchy levels unless there is a concrete durable-memory use case that the todo plugin cannot cover.
- When a plan is active, all durable progress notes go to the plan log.
- The gateway should report active project, active plan, domains, and Dream freshness only.
- Existing removed behavior can be recovered from git if the simplified model proves insufficient.
