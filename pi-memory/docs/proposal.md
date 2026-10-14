# pi-memory Proposal

## Goal

Build a PI extension that gives the agent durable, markdown-backed memory without turning every session into an auto-capture firehose.

The extension should:

- Track project and plan context across PI sessions.
- Capture durable notes, decisions, gotchas, and resume points into an Obsidian vault.
- Dump messy daily links/snippets into a weekly inbox before organizing them.
- Search prior memory with grep and optional AnythingLLM semantic recall.
- Load a compact Memory Gateway into the PI system prompt.
- Periodically consolidate the vault with a manual Dream pass.

Fine-grained execution state belongs to PI's todo plugin. pi-memory keeps durable context only.

## Non-goals

- Replacing git, jj, or the filesystem as the source of truth.
- Automatically summarizing every turn.
- Managing task-level execution state.
- Writing outside the configured vault roots.
- Hiding memory mutations from the user.

## Vault layout

```text
<vault>/
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
    .last_dream.marker
  10_Weekly/
    <YYYY-Www>.md
```

Project files hold durable project metadata. Plan files hold durable plan goals, decisions, and logs. Domain files hold cross-cutting knowledge such as `jj`, `csharp`, or repo-as-domain notes. Weekly notes are the fallback inbox when no project is active.

## Config model

Global config lives at `~/.pi/memory/config.toml`. Per-repo state and overrides live at `<repo>/.memory/config.toml`.

Global config sections:

- `[vault]`: vault root, managed folder names, weekly note format, weekly inbox heading.
- `[capture]`: checkpoint hook toggles, model hint, max observations.
- `[dream]`: cadence, scope, domain creation policy, size thresholds.
- `[note]`: smart routing, domain creation policy, multi-target policy.
- `[gateway]`: full gateway budget and notes tail size.
- `[dump]`: low-friction weekly inbox ingestion and optional ingest model.
- `[organize]`: conservative dump-review defaults and domain-sprawl controls.
- `[anythingllm]`: semantic recall settings.

Per-repo sentinel state:

```toml
[repo]
name = "memory-dev"

[state]
projects = ["pi-memory"]
plan = "plans/v1-ext"
domains = ["jj"]

[overrides.vault]
root = "/tmp/pi-memory-test-vault"
```

## Routing

Deterministic capture routing uses this precedence:

| Context | Target |
| --- | --- |
| Active plan | Active plan's `plan.md` under `## Log` |
| Active project, no plan | Active project `notes.md` |
| No active project | Weekly note `## Inbox` |

The `memory-note` skill can add a second target when the content clearly belongs on a known domain page.

## Memory Gateway

The gateway has two depths.

### Basic gateway

Loaded at `session_start`. It contains only cheap metadata:

- repo name
- active project
- active plan
- active domains
- Dream freshness

Example:

```markdown
## Memory state (basic -- run /set-context for full)

Repo: memory-dev   Project: pi-memory   Plan: v1-ext
Domains: jj, pi-memory
Last dream: 3d ago.
```

### Full gateway

Loaded by `/set-context`. It includes:

- basic gateway header
- full `project.md`
- tail of `notes.md`
- active `plan.md`
- known active domain pages

The full gateway is token-budgeted and can be refreshed with `/set-context` with no args.

## Commands

| Command | Behavior |
| --- | --- |
| `/note <text>` | Deterministically captures to active plan, project notes, or weekly inbox. |
| `/dump <text>` | Ingests daily links/snippets/gotchas into the weekly inbox, grouped by day and lightly formatted for Obsidian. |
| `/organize-dump [--dry-run]` | Reviews recent dumps and proposes conservative organization without moving, creating, or inferring project destinations from the current repo. |
| `/recall <query>` | Searches the vault; grep always works, semantic/hybrid require AnythingLLM. |
| `/set-context [project[/plan]]` | Updates context and loads the Memory Gateway. `/` or `~` clears; `..` moves up one level. |
| `/checkpoint [--all]` | Manually records a checkpoint boundary and writes a minimal marker line. |
| `/memory-doctor [target]` | Shows internal state, config, gateway, prompt skills, tools, Dream stats, or domain drift. |
| `/memory-bootstrap [--dry-run]` | Creates missing markdown scaffolds for active context. |
| `/dream [--dry-run]` | Runs the manual consolidation pass. |

## Tools

| Tool | Purpose |
| --- | --- |
| `memory_capture` | Append one formatted line to a managed markdown file. |
| `memory_set_frontmatter` | Set one YAML frontmatter field on a managed markdown file. |
| `memory_search` | Search the vault with grep, semantic, or hybrid mode. |
| `memory_list_projects` | List project folders. |
| `memory_list_domains` | List domain pages. |
| `memory_list_projects_by_tag` | Find projects tagged with a domain/repo. |
| `memory_get_context` | Return repo, project, plan, domains, paths, and note flags. |
| `memory_resolve_capture_target` | Resolve `current`, `weekly`, or `domain` to a safe file/section. |
| `memory_set_context` | Set project/plan context and refresh the gateway. |
| `memory_dream_stats` | Report last Dream and awake-period file count. |

## Hooks

| Hook | Behavior |
| --- | --- |
| `session_start` | Build and store the basic gateway. Notify when Dream is overdue. |
| `before_agent_start` | Append latest gateway to the system prompt. |
| `session_before_compact` | Update the checkpoint marker. |
| `session_shutdown` | Update the checkpoint marker. |
| `resources_discover` | Expose skills according to config gates. |

## Skills

| Skill | Trigger | Purpose |
| --- | --- | --- |
| `memory-note` | Auto-invocable when smart routing is enabled | Capture durable facts and optionally add a domain target. |
| `memory-recall` | Recall-shaped user requests | Query prior memory. |
| `memory-checkpoint` | Hook/manual only | Extract 0-3 durable observations from a session segment. |
| `memory-dream` | Manual only | Consolidate the vault via the Dream worker. |

## Dream pass

Dream is manual and reversible. It reads files modified since `.last_dream.marker` within configured scope and delegates to `memory-dream-worker`.

Operations:

1. Resolve contradictions in place.
2. Promote repeated themes to domain pages.
3. Summarize or split oversized notes.
4. Enrich links and frontmatter.
5. Surface ideas from session logs.

The skill applies the edit plan, appends a dreamlog section, and touches `.last_dream.marker`.

## Acceptance criteria

- `/set-context project` sets active project and loads the full gateway.
- `/set-context project/plan` sets active plan and creates missing plan scaffold.
- `/set-context ..` moves from plan to project, then from project to no active context.
- `/set-context /` clears context and routes future captures to weekly inbox.
- `/note` writes to active plan, project notes, or weekly inbox according to context.
- `/dump` always writes to the weekly inbox regardless of active context.
- `/organize-dump` is dry-run only and does not create new domains.
- `memory_resolve_capture_target(target="current")` returns the same target as deterministic `/note`.
- `memory_get_context()` returns no task-level hierarchy beyond project and plan.
- `memory_search` grep mode works without AnythingLLM.
- Semantic recall errors helpfully when AnythingLLM is not configured.
- `/memory-bootstrap --dry-run` reports files without writing them.
- `/memory-doctor state` shows repo, active project, active plan, domains, and cwd.
- Dream writes stay inside managed vault roots.
