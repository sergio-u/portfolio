# Workspace Skill Examples

Condensed examples from our own `~/.openclaw/workspace/skills/` directory. Each shows a different execution pattern with the key structural elements. Read the full skill files for complete details.

---

## Pattern 1: CLI Wrapper (`gh`)

Minimal skill wrapping an existing CLI tool. No scripts, no auth complexity.

```yaml
---
name: gh
description: >
  Search GitHub for repos, issues, PRs, discussions, code, and more via the gh CLI.
  Use when the user says "search GitHub", "find issues", "list PRs", "search repos",
  "GitHub code search", or asks to look something up on GitHub.
---
```

**Key traits:**
- Shows common commands with flags in Execution section
- Mentions `--json` for machine-readable vs human-friendly output
- Conventions: don't dump raw JSON, confirm before destructive ops
- Auth: just notes `gh auth login` is required
- 60 lines total -- very lean

---

## Pattern 2: CLI Wrapper with Reference Tables (`ado`)

Complex CLI wrapper with multi-org auth and cached entity IDs.

```yaml
---
name: ado
description: >
  Manage Azure DevOps repositories, pull requests, work items, pipelines, wiki,
  and notifications via the az devops CLI. Use when the user asks to create or
  review pull requests, manage work items, trigger pipelines, browse repos,
  check build status, read/write wiki pages, or do any Azure DevOps operation.
  Triggers on "azure devops", "ADO", "pull request", "work item", "pipeline",
  "azure repos", "devops board", "sprint", "backlog", "my work items", "wiki",
  "tsg", "pull requests", "pipelines", "work items", "az devops".
---
```

**Key traits:**
- Reference table maps org names to IDs, PATs, default projects
- Auth uses env vars with naming convention: `ADO_<ORG>_PAT`
- Domain sections organized by operation type (PRs, Work Items, Pipelines, Wiki)
- 512 lines -- larger due to many operations, but still structured

---

## Pattern 3: uv run Scripts (`flights`)

Self-contained Python scripts with inline dependencies managed by uv.

```yaml
---
name: flights
description: >
  Search for flights using the Google Flights API via the fli library.
  Use when the user says "search flights", "find flights to", "cheapest flight",
  "flight prices", "fly from X to Y", "when is cheapest to fly", or wants to
  compare prices or plan air travel.
---
```

**Key traits:**
- Two scripts: `search_flights.py` (specific date) and `search_dates.py` (date range)
- Run from workspace root: `uv run skills/flights/search_flights.py <args>`
- Options documented in clean tables
- Includes a fallback strategy (agent-browser with Google Flights) when the API returns empty
- No auth required -- library queries directly

---

## Pattern 4: uv run Scripts with Research Workflow (`reddit`)

Script-based skill combined with SearxNG web search for discovery.

```yaml
---
name: reddit
description: >
  Interact with Reddit via PRAW. Fetch post details and comments, manage
  subscriptions (list, audit, unsubscribe), and organize subreddits into
  multireddits. Also use for research workflows: search Reddit via SearxNG
  (site:reddit.com) to find relevant threads, then fetch and parse the top
  results with this skill. Triggers on "browse reddit", "manage subreddits",
  "fetch posts", "reddit", "look up this Reddit post", "what does Reddit say about",
  "Reddit recommendations for", "summarize this thread"...
---
```

**Key traits:**
- Combines web_search (SearxNG) discovery with script-based fetching
- Multiple scripts for different operations (fetch, manage subs, multireddits)
- Auth via env vars in `.env` file at workspace root
- Research workflow pattern: search -> discover -> fetch -> summarize

---

## Pattern 5: MCP Wrapper with Cache Table (`todoist`)

Wraps an MCP server, includes task routing logic and entity cache.

```yaml
---
name: todoist
description: >
  Manage tasks, projects, and labels in Todoist via MCP. Use when the user wants
  to add tasks, check their to-do list, complete tasks, reschedule, search tasks,
  manage projects or sections, or do any Todoist operations. Triggers on "add a
  task", "remind me to", "to-do", "todoist", "what's on my list", "mark done",
  "complete task", "reschedule", "move task", "my tasks", "task list".
---
```

**Key traits:**
- Execution via `mcporter call todoist.<tool> param=value`
- Task Routing section with decision logic (personal vs work, inbox routing)
- Project & Section Cache table with IDs to avoid API roundtrips
- Maintenance notes: "When you create or rename projects/sections, update this table"
- AI Label convention: all agent-created tasks get labeled `AI`
- 107 lines -- medium size with rich domain logic

---

## Pattern 6: venv + REPL (`splitwise`)

Python SDK requiring a persistent virtualenv.

```yaml
---
name: splitwise
description: >
  Manage Splitwise expenses, groups, and balances via the Splitwise Python SDK.
  Use when the user says "split expense", "who owes", "add expense", "settle up",
  "Splitwise", "split the bill", "check balances", "how much do I owe", or
  references any Splitwise account management.
---
```

**Key traits:**
- Uses `.venv/bin/python` -- never bare `python`
- REPL pattern: `cd skills/splitwise && .venv/bin/python scripts/repl.py 'code'`
- Auth via `.env` in skill directory
- Reference section caches group names/IDs and friend IDs

---

## Pattern 7: Pure Shell / API-Based (`upgrade-check`)

No scripts -- uses shell commands, curl, and local CLI tools directly.

```yaml
---
name: upgrade-check
description: >
  Analyze OpenClaw releases between the current installed version and the latest available,
  check GitHub issue volume/rate trends, review the changelog for critical fixes and new features,
  and compare current config against new options. Use when the user says "should I upgrade",
  "upgrade check", "check for updates", "what changed since my version", "release notes",
  "is it safe to upgrade", "check openclaw updates", or "what's new in openclaw".
---
```

**Key traits:**
- Multi-step workflow using shell commands (curl, jq, openclaw CLI)
- Structured output format defined in the skill
- Reference table tracks "Our Active Setup" for relevance classification
- Rate limiting guidance (sleep between API calls)
- No scripts directory -- everything is inline shell

---

## Pattern 8: Custom Binary with Sub-Skills (`gws`)

Wraps a local binary with sub-skill organization for large APIs.

**Key traits:**
- Parent SKILL.md provides overview and links to sub-skills
- Sub-skills in subdirectories: `gws-calendar/SKILL.md`, `gws-drive/SKILL.md`
- Shared helper sub-skill pattern: `gws-shared/SKILL.md`
- All sub-skills share the parent's auth and binary
- Sub-skill table in parent for quick navigation

---

## Pattern 9: Existing Skill + Workflow Doc (`obsidian`)

Extends an existing skill with a focused operating loop that does not need its own slash command.

**Key traits:**
- Main `SKILL.md` stays lean
- A standalone workflow/recipe doc holds the detailed loop
- `SKILL.md` points to that workflow when the request matches
- Good for weekly reviews, checklists, triage loops, or evolving processes

Example shape:

```text
skills/obsidian/
  SKILL.md
  Habit System Workflow.md
```

---

## Common Elements Across All Skills

1. **Frontmatter**: `>` folded scalar for description, trigger phrases in quotes, name matches folder
2. **Section order**: Display Name > Execution > Domain > Reference > Conventions > Auth > Requirements > Troubleshooting
3. **Conventions section**: Always present. Includes "confirm before destructive ops" and output formatting rules
4. **Reference/Cache tables**: Used when the skill interacts with recurring entities (projects, orgs, groups)
5. **Maintenance notes**: Remind the agent to update cache tables when entities change
6. **Auth**: Documented but never hardcoded. Env vars, `.env` files, or credential files
7. **No README.md**: All docs in SKILL.md or references/
