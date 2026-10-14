# pi-memory

Memory and planning extension for the [Pi](https://github.com/earendil-works/pi-coding-agent)
coding agent. It keeps notes, decisions, and resume points in an Obsidian vault,
organized by project and plan, and puts a short summary of the active context in
front of the agent at the start of each turn. Everything it writes is plain
Markdown that I can read and edit, and every write goes to a file I can see.

## Status

In daily use: `/note`, `/dump`, `/recall`, `/set-context`, `/checkpoint`,
`/memory-bootstrap`, `/memory-doctor`, and ten agent tools. `/organize-dump`
only proposes changes (dry run). Not built yet: the Dream consolidation pass
(`/dream` is a stub) and automatic observation capture from session hooks. The
extension is about 3,600 lines of TypeScript.

## Design

- Notes route deterministically. A note goes to the active plan, otherwise the
  active project, otherwise this week's inbox. With smart routing on, the
  `memory-note` skill can also copy a cross-cutting note to a domain page.
- Context is per repository. `/set-context` writes `<repo>/.memory/config.toml`;
  global defaults live in `~/.pi/memory/config.toml`.
- The Memory Gateway comes in two sizes. Session start loads cheap metadata
  (repo, project, plan, domains, Dream freshness); `/set-context` loads the full
  version with the project file, recent notes, the active plan, and domain
  pages. Pi appends the latest gateway to the system prompt
  before each agent turn.
- Writes stay conservative. The extension writes only under the configured vault
  folders, bootstrap never rewrites an existing file, and organizing dumps or
  consolidating memory is a reviewed step.
- Task-level execution state is left to Pi's todo tool; pi-memory keeps durable
  context only.

The full spec is in [docs/proposal.md](docs/proposal.md), design conclusions in
[docs/research.md](docs/research.md),
the phased build plan in [docs/implementation-plan.md](docs/implementation-plan.md),
and flow diagrams in [diagrams/](diagrams/).

## Install

```bash
git clone https://github.com/sergio-u/portfolio
cd portfolio/pi-memory
npm install
pi install "$PWD"
```

## Quick start

1. Copy the example config and set your vault root:

   ```bash
   mkdir -p ~/.pi/memory
   cp templates/config.example.toml ~/.pi/memory/config.toml
   ```

   ```toml
   [vault]
   root = "/Users/YOU/Notes"
   ```

2. In a repository, set a project, and optionally a plan, then create any
   missing files:

   ```text
   /set-context pi-memory
   /set-context pi-memory/v1-ext
   /memory-bootstrap --dry-run
   /memory-bootstrap
   ```

3. Capture, dump, and search:

   ```text
   /note decided to keep Dream manual so edits stay reviewable
   /dump latency dashboard: https://...
   /recall Dream manual
   ```

## Commands

| Command | Purpose |
| --- | --- |
| `/note <text>` | Capture a durable note to the active plan, project, or weekly inbox |
| `/dump <text>` | Append a raw link, command, or snippet to the weekly inbox |
| `/organize-dump [--days N\|--weeks N\|--current-week] --dry-run` | Propose how to organize recent dumps |
| `/recall <query>` | Search memory |
| `/set-context [project[/plan]]` | Set, refresh, move up (`..`), or clear (`/`) context |
| `/checkpoint [--all]` | Write a manual checkpoint line and advance the marker |
| `/memory-bootstrap [--dry-run]` | Create missing project, plan, domain, or weekly files |
| `/memory-doctor <target>` | Inspect `state`, `config`, `gateway`, `domains`, `prompts`, `tools`, or `dream` |
| `/dream` | Run Dream consolidation (not implemented yet) |

A note is routed like this:

1. Active plan: `80_AI/projects/<project>/plans/<plan>/plan.md`, under `## Log`.
2. Active project: `80_AI/projects/<project>/notes.md`.
3. No active project: `10_Weekly/<this-week>.md`, under `## Inbox`.

`/dump` always writes to the weekly inbox, even when a project is active. It is
for things that would otherwise sit in a scratch editor tab. The configured
model turns multiline dumps into light Markdown; if that call fails, the dump is
saved as a raw fenced block so nothing is lost:

```markdown
## Inbox

### 2026-06-04

- Release checklist
  - Rollback runbook: https://...
  - Feature flag dashboard: https://...
```

`/organize-dump` scans recent inboxes and proposes copies to existing domains,
possible project or runbook snippets, new domains (only after repeated
evidence), and items to leave alone. It never moves or deletes notes.

`/recall` works with plain grep. Semantic and hybrid modes need an
[AnythingLLM](https://anythingllm.com) workspace.

## Vault layout

pi-memory writes only under these folders:

```text
<vault>/
  80_AI/
    projects/<project>/
      project.md
      notes.md
      plans/<plan>/plan.md
    domains/<tag>.md
    dreamlog.md
    .last_dream.marker
  10_Weekly/
    <YYYY-Www>.md
```

## Configuration

Global settings live in `~/.pi/memory/config.toml`; see
[templates/config.example.toml](templates/config.example.toml) for every
option. `vault.root` is the only required value.

The per-repository file holds active context and optional overrides for any
global section:

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

For semantic recall, set `ANYTHINGLLM_HOST` and `ANYTHINGLLM_API_KEY`, or the
`[anythingllm]` section of the global config. Keep the API key out of
per-repository files.

## Version control

The extension reads and writes `<repo>/.memory/config.toml` and leaves
versioning to you. Add `.memory/` to `.gitignore` to keep context local, track
it to share context, or with jj keep it in a private commit:

```bash
jj config set --user git.private-commits "description(glob:'[memory]*')"
```
