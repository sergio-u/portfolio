# Openclaw Skills Conventions

These conventions are derived from the existing skills in the `~/.openclaw/workspace/skills/` directory. They extend the upstream AgentSkill spec with openclaw-specific patterns. When they conflict, these conventions take precedence.

## Folder & Naming

- Skills live in `~/.openclaw/workspace/skills/<name>/`
- Folder name = slash command name (auto-discovered via `nativeSkills: auto`)
  - If the skill should be invocable as `/foo`, the folder must be named `foo`
  - Choose short, memorable names for the command (e.g. `ado` not `azure-devops`)
- Folder names: kebab-case, no spaces, no capitals, no underscores
- File must be exactly `SKILL.md` (case-sensitive)
- No `README.md` inside skill folders

## Frontmatter

```yaml
---
name: skill-name
description: >
  One paragraph. First sentence = what it does. Second = when to use it.
  Include explicit trigger phrases in quotes. Keep under 1024 chars.
---
```

- Use `>` folded scalar for multiline descriptions (not inline strings)
- `name` must match the folder name
- Add `user-invocable: false` only if the skill should NOT be a slash command (e.g. helper skills used by other skills)

## SKILL.md Body Structure

Follow this section order (skip sections that don't apply):

```markdown
# Display Name

One-line summary of what the skill wraps or does.

## Execution

How to invoke the tool. Show the primary command pattern(s).

## [Domain-Specific Sections]

Operations, workflows, API reference, etc. Vary by skill.

## Reference

Cache tables, known IDs, user-specific config. Updatable at runtime.

## Conventions

Behavioral rules: output formatting, confirmation before destructive ops, etc.

## Authentication

How credentials are resolved. Env vars, .env files, etc.

## Requirements

What must be installed. Keep it minimal.

## Troubleshooting

Common errors and fixes (optional, add as issues are discovered).
```

## Execution Patterns

Choose the pattern that fits the tool:

### 1. CLI Wrapper (e.g. `gh`, `ado`)

For skills that wrap an existing CLI tool. Show common commands with flags.

```markdown
## Execution

```bash
az repos pr list --repository <repo> --org <org-url> -o json
```

Use `-o json` when parsing results; `-o table` for display.
```

### 2. uv run Scripts (e.g. `flights`, `reddit`, `trafilatura`)

For Python scripts with inline dependencies managed by uv. Scripts are self-contained.

```markdown
## Execution

```bash
uv run skills/<name>/script.py <args> [options]
```

Run from the workspace root (`~/.openclaw/workspace`).
```

### 3. Local venv + REPL (e.g. `splitwise`, `scrapling`)

For Python SDKs that need a persistent venv. Use a `scripts/repl.py` or `scripts/run.py` runner.

```markdown
## Execution

```bash
cd ~/.openclaw/workspace/skills/<name>
.venv/bin/python scripts/repl.py 'print(result)'
```

Always use the venv Python -- never bare `python`.
```

### 4. MCP Wrapper (e.g. `todoist`)

For skills that wrap an MCP server configured in `config/mcporter.json`.

```markdown
## Execution

```bash
mcporter call <server>.<tool> param=value
mcporter call <server>.<tool> --args '{"param": "value"}'
```

Tool schemas come from the MCP server at runtime. Don't duplicate them.
```

### 5. Custom Binary (e.g. `gws`)

For skills with a local wrapper script/binary.

```markdown
## Execution

```bash
skills/<name>/<binary> <command> [flags]
```
```

### 6. Multi-Agent Orchestration (e.g. `digest-day`)

For skills that process multiple independent units in parallel using subagents.

```markdown
## Execution

1. Extract data per unit (script or CLI)
2. Save per-unit files to /tmp/
3. Spawn one subagent per unit (sessions_spawn, mode=run, `agentId: small|medium|large`, lightContext=true)
4. sessions_yield to wait for all completions
5. Aggregate, curate, and present results
```

Key conventions:
- Store subagent prompt template in `references/subagent-prompt.md`
- Use file-based handoff for large data, task-string for small data
- Use named subagent tiers instead of per-spawn model overrides: `small` for Flash/Haiku-class extraction, `medium` for Sonnet-class analysis, `large` for Opus-class heavyweight review
- Main agent always does a curation pass on subagent output
- See `references/multi-agent-workflow.md` in the new-skill skill for full guide

## Reference / Cache Tables

For skills that interact with entities the user accesses repeatedly (projects, repos, groups, IDs), add a reference table:

```markdown
## Reference

| Entity | Name | ID |
|---|---|---|
| Project | My Project | abc123 |

> **Maintenance:** Update this table as you learn new entities.
```

This avoids redundant API calls. Include a maintenance note so the agent updates the table when new entities are discovered.

## Authentication Patterns

Document auth clearly. Common patterns in this workspace:

- **Env var (per-org):** `ADO_<ORG>_PAT` -- resolve automatically from reference tables
- **Env var (global):** `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`
- **Dotenv file:** `.env` in the skill root (e.g. `skills/splitwise/.env`)
- **Credential file:** Path to a JSON credential (e.g. `~/.openclaw/credentials/google-workspace.json`)

Never hardcode secrets in SKILL.md. Never ask the user for token values if the env var is documented.

## Conventions Section

Every skill should have a Conventions section. Common rules:

- Confirm before destructive actions (deletes, bulk updates, abandoning PRs)
- Present results as clean summaries -- don't dump raw JSON
- Use machine-readable output (`-o json`, `--json`) when parsing; human-friendly when displaying
- Run from workspace root unless the skill requires `cd` into its directory

## Sub-Skills

For complex integrations, split into a parent skill + sub-skills (see `gws` pattern):

```
skills/gws/
  SKILL.md              # Parent: overview + quick reference
  gws-calendar/
    SKILL.md            # Sub-skill: calendar-specific operations
  gws-drive/
    SKILL.md            # Sub-skill: drive-specific operations
```

The parent SKILL.md links to sub-skills via a table. Sub-skills share the parent's auth and binary.

## Workflow / Recipe Docs

For repeatable operating loops that belong inside an existing skill but do not need their own slash command, add a focused workflow or recipe doc beside `SKILL.md`.

Example:

```
skills/obsidian/
  SKILL.md
  Habit System Workflow.md
```

Use this pattern when:
- the capability is mostly instructions, checklists, or review loops
- the workflow clearly belongs to one existing skill
- adding a whole sub-skill would be unnecessary overhead

When you do this:
- keep the main `SKILL.md` lean
- add a short pointer from `SKILL.md` to the workflow doc
- update frontmatter/trigger guidance only if the new workflow materially changes when the skill should trigger

## Shared Helper Skills

For larger skill families, it can be useful to add a shared/helper sub-skill for auth, global syntax, or safety rules.

Example shape:

```
skills/gws/
  SKILL.md
  gws-shared/
    SKILL.md
  gws-calendar/
    SKILL.md
  gws-drive/
    SKILL.md
```

Use a shared/helper skill when multiple sub-skills would otherwise duplicate the same core instructions.

## Reviewing Skills

When reviewing an existing skill, check:

1. **Frontmatter:** name matches folder, description has WHAT + WHEN + trigger phrases, uses `>` multiline
2. **Structure:** Follows the section order above
3. **Execution:** Uses the right pattern for the tool type
4. **Reference tables:** Present if the skill uses recurring entities/IDs
5. **Auth:** Documented, no hardcoded secrets
6. **Conventions:** Present, includes confirmation rules and output formatting
7. **Trigger quality:** Would it fire on obvious requests? Would it over-trigger on unrelated ones?

## Existing Skills (for reference)

Read existing skills in `~/.openclaw/workspace/skills/` to see working examples of each pattern:

| Skill | Pattern | Notes |
|---|---|---|
| `gh` | CLI wrapper | Minimal, clean |
| `ado` | CLI wrapper | Multi-org auth, reference tables, sprints |
| `todoist` | MCP wrapper | Cache table, task routing, labels |
| `flights` | uv run scripts | Two scripts, options tables, fallback |
| `reddit` | uv run scripts | Research workflow, SearxNG integration |
| `trafilatura` | uv run scripts | Minimal, single script |
| `youtube-transcript` | uv run scripts | Output formats, error handling |
| `splitwise` | venv + repl | SDK wrapper, auth via .env |
| `scrapling` | venv + runner | Fetcher escalation strategy |
| `digest-day` | multi-agent | Parallel subagents for weekly digest, `medium` per day |
| `gws` | custom binary | Parent + sub-skills + shared helper |
| `obsidian` | filesystem | Vault structure + attached workflow docs |
| `restaurant-finder` | Docker + scripts | Multi-step workflow, user preferences |
