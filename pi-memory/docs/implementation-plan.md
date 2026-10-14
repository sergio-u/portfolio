# PI Memory Extension - Implementation Plan

This plan tracks the current design for `pi-memory`: markdown-backed memory, project/plan context, deterministic capture primitives, smart note skills, recall, and a manual Dream consolidation pass.

## Architecture quick reference

- Extension entry: default-exported factory `(pi: ExtensionAPI) => void | Promise<void>` from `src/extension/index.ts`.
- Packaging: ESM package, no `tsconfig.json`, Node native TypeScript via `--experimental-strip-types`.
- Skill discovery: the extension returns skill paths from `resources_discover` so PI can surface `SKILL.md` descriptions.
- Session state: `pi.appendEntry(customType, data)` stores transient entries such as the latest memory gateway and checkpoint marker.
- Persistent state: `<repo>/.memory/config.toml` stores active project, active plan, active domains, repo name, and per-repo overrides.
- Vault: all managed markdown lives under `<vault>/80_AI/`; weekly fallback captures live under `<vault>/10_Weekly/`.

## Context model

The active hierarchy has two durable levels:

1. Project: `80_AI/projects/<project>/`
2. Plan: `80_AI/projects/<project>/plans/<plan>/plan.md`

Fine-grained execution tasks are handled by PI's todo plugin, not by pi-memory. Captures that need durable context route to the active plan or project notes.

## Tool surface

The extension registers these `memory_*` tools:

- `memory_capture`
- `memory_set_frontmatter`
- `memory_search`
- `memory_list_projects`
- `memory_list_domains`
- `memory_list_projects_by_tag`
- `memory_get_context`
- `memory_resolve_capture_target`
- `memory_set_context`
- `memory_dream_stats`

## Commands

- `/note <text>`: append a formatted note to the active plan, project notes, or weekly inbox.
- `/dump <text>`: ingest a lightly formatted daily dump to the weekly inbox.
- `/organize-dump [--dry-run]`: review recent dumps and propose conservative organization.
- `/recall <query>`: search the vault.
- `/set-context [project[/plan]]`: set or refresh the active context and load the full Memory Gateway.
- `/checkpoint [--all]`: manually mark a session checkpoint.
- `/memory-doctor [target]`: inspect config, state, gateway, prompts, tools, Dream stats, or domain drift.
- `/memory-bootstrap [--dry-run]`: create missing markdown files for the active context.
- `/dream`: manual consolidation pass (stub until Phase 4).

## Hooks

- `session_start`: load config + sentinel, build the basic gateway, and store it in session state.
- `before_agent_start`: inject the latest gateway into the system prompt.
- `session_before_compact`: update the checkpoint marker.
- `session_shutdown`: update the checkpoint marker.
- `resources_discover`: expose configured skills.

## Phase 1 - Foundation

Outcome: extension loads, registers commands/tools/hooks, reads config, and can write managed markdown.

Deliverables:

- Source scaffold under `src/extension/`.
- Two-tier config loader: global `~/.pi/memory/config.toml` plus per-repo `.memory/config.toml` overrides.
- Sentinel reader/writer.
- Path safety utilities that constrain writes to managed vault roots.
- Tool registrations with Typebox schemas.
- Command registrations.
- Basic README and config template.

Validation:

- Extension loads in PI.
- `/memory-doctor config` shows merged config.
- `/memory-doctor state` shows sentinel state.
- `memory_capture` writes inside the managed vault and rejects outside paths.

## Phase 2 - Capture + Gateway

Outcome: capture and recall are usable without LLM routing.

Deliverables:

- `/note <text>` structural routing:
  1. active plan -> `plan.md` `## Log`
  2. active project -> `notes.md`
  3. no project -> weekly inbox
- `/set-context [project[/plan]]` implementation.
- Project and plan scaffold creation.
- Basic gateway on session start.
- Full gateway on `/set-context`.
- `/recall` grep path.
- `/dump` weekly-inbox capture path with model-based Obsidian ingestion and raw fallback.
- `/organize-dump --dry-run` monthly review proposal path.
- `/memory-bootstrap` deterministic file creation.

Validation:

- `/set-context pi-memory` then `/note "decided X"` writes to `projects/pi-memory/notes.md`.
- `/set-context pi-memory/v1-ext` then `/note "decided X"` writes to `projects/pi-memory/plans/v1-ext/plan.md` under `## Log`.
- `/set-context /` clears context; `/note "thought"` writes to the weekly inbox.
- `/dump "quick link"` writes to the weekly inbox even when a plan is active.
- `/organize-dump --days 30 --dry-run` reports proposed promotions without writes.
- A new PI session injects the basic Memory Gateway.
- `/set-context` refreshes the full gateway.

## Phase 3 - Smart capture + semantic recall

Outcome: LLM-mediated capture and semantic recall layer on top of deterministic primitives.

Deliverables:

- `memory-note` skill: context-aware target selection with optional domain second target.
- `memory-checkpoint` skill: hook-driven extraction of 0-3 durable observations from recent session turns.
- `memory-recall` skill: recall-shaped natural language questions use `memory_search`.
- `memory_search` semantic and hybrid modes through AnythingLLM.
- Config gates for `note.smart_routing` and AnythingLLM credentials.

Validation:

- Smart note routing can write to both the active context and a known domain.
- `[note].smart_routing = false` leaves deterministic `/note` behavior intact.
- `/recall --semantic` returns ranked hits when AnythingLLM is configured.
- Missing semantic config fails helpfully while grep still works.

## Phase 4 - Dream + Polish

Outcome: Dream consolidation works, installer is real, and the README supports first-use setup.

Deliverables:

- `memory-dream` skill invokes `memory-dream-worker`.
- Dream worker resolves contradictions, promotes repeated themes to domains, summarizes oversized notes, enriches links/frontmatter, and surfaces ideas.
- `/dream --dry-run` previews edits.
- `/dream` applies edits, appends dreamlog, and touches `.last_dream.marker`.
- Installer modeled after PI extension examples.
- End-to-end smoke test instructions.

Validation:

- Fresh setup can set context, capture notes, recall them, and run a dry-run Dream.
- Dream writes are scoped to managed vault roots.
- jj sentinel workflow is documented and reversible.

## Verification strategy

- Prefer small deterministic tests for path resolution, config merging, and markdown mutation.
- Use PI smoke tests for command and hook behavior.
- Do not run builds or tests automatically; ask first.
