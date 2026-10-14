---
name: memory-note
description: |
  Capture a knowledge fragment from this PI session into the user's pi-memory vault when the user explicitly asks to persist it. Proactive capture is exceptional: use it only for stable, non-derivable context that a future session would need, such as a cross-project preference, a difficult gotcha and workaround, or rationale not encoded in repository artifacts. Never capture individual questionnaire answers, provisional choices, or implementation details already recorded in code, tests, documentation, plans, commits, or Git history. Routes captures to the active plan, project notes, weekly inbox, or a relevant domain page. NEVER deletes existing content; the only frontmatter mutation allowed is toggling status:completed on an active plan when the user clearly signals completion.
---

# memory-note

This skill captures durable knowledge into the user's pi-memory vault (an Obsidian-friendly markdown tree). The vault lives outside the current repo and persists across sessions.

The user runs `/note <text>` for explicit captures; that command uses deterministic structural routing on its own (active-plan > project-notes > weekly-inbox). Your job is the harder case: the user is in the middle of normal conversation and you notice something worth preserving.

## Proactive capture budget

Proactive capture is a rare exception, not a running transcript.

- Never capture after each questionnaire answer or incremental implementation choice.
- Wait until a related decision group is stable, then capture at most one consolidated note for that logical phase.
- Skip anything a future session can recover from code, tests, documentation, a plan, a commit message, `Changes.md`, or Git history.
- Do not capture provisional decisions that may still be revised; wait for convergence.
- If repo-specific context would fall back to the weekly inbox because no project context is active, skip it or ask once whether to set project context.
- Explicit user requests such as "remember this" or `/note` are not subject to this proactive budget.

Before any proactive capture, ask: "Would a future session be unable to recover this from durable project artifacts?" If not, do not capture.

## When to capture proactively

Capture-worthy moments share a pattern: the conversation just produced information that a future session would benefit from but will not be able to derive from code or git history alone.

Examples:

- The user explained why an approach was chosen over an alternative.
- A non-obvious gotcha and its workaround surfaced.
- A configuration value, external resource, or magic number took effort to find.
- The user changed direction on something significant.
- A piece of cross-project context the user dropped offhand.
- A plan was just completed or needs a durable log entry.

Skip when:

- The information is fully derivable from current files or git history.
- It is transient scratch state.
- It duplicates something already saved.
- The user is asking a question rather than producing a fact.

If unsure, ask one tight sentence: "Worth capturing as a note?"

## Workflow

### Step 1 - Read context

Call `memory_get_context()`. It returns the active repo, project, plan, active domains, resolved capture roots, and note-routing flags.

If `project` is `null`, captures with no clear domain default to the weekly inbox.

### Step 2 - Read available domains

Call `memory_list_domains()` to learn which topic pages exist. The note may belong on one of these in addition to, or instead of, the active context.

### Step 3 - Decide targets

Pick one or more targets. Do not construct absolute paths by hand. For the primary current-context target, call `memory_resolve_capture_target(target="current")`. For a domain target, call `memory_resolve_capture_target(target="domain", domain="<tag>")`.

Vault shape:

```
<vault>/80_AI/
├── projects/
│   └── <project>/
│       ├── project.md
│       ├── notes.md
│       └── plans/
│           └── <plan>/
│               └── plan.md  <- write to "## Log"
├── domains/
│   └── <tag>.md
└── ...
<vault>/10_Weekly/
└── 2026-W21.md              <- write to "## Inbox" fallback
```

Routing precedence:

1. Active plan -> that plan's `plan.md` under `## Log`.
2. Active project, no plan -> project's `notes.md`.
3. No project -> weekly note `## Inbox`.
4. In addition, if the note clearly affects a known domain, add that domain's `<tag>.md` as a second target.

Most notes hit one target. Cross-cutting notes hit two.

### Step 4 - Format the line

Standard format:

```
- [YYYY-MM-DD HH:MM] <text>
```

Use the local time. Keep the line single-line.

### Step 5 - Write

For each resolved target, call `memory_capture(file, line, section?)` using the exact file and section returned by `memory_resolve_capture_target`.

### Step 6 - Optional: toggle plan completion

If the note clearly expresses that the active plan is done, call `memory_set_frontmatter(plan_file, "status", "completed")`. This is the only frontmatter mutation this skill is allowed to make.

### Step 7 - Confirm

Report which target(s) you wrote to. Keep it short: `noted under <label> -> <path>`.

## Examples

### Active plan, single target

Context: `project=pi-memory, plan=plans/v1-ext`.

User says: "ok this is funny - `smol-toml` strips empty arrays from `[state].projects`. Workaround is to set them as `["__empty"]` and filter on read."

Target: active plan `plan.md` `## Log`.

Line: `- [2026-05-22 14:30] smol-toml strips empty arrays; workaround = ["__empty"] sentinel and filter on read.`

### Project active, cross-cutting domain

Context: `project=pi-memory, plan=(none)`.

User says: "by the way, jj's `git.private-commits` revset uses `glob:` syntax, not regex. Cost me an hour."

Targets: project `notes.md` and `domains/jj.md`.

### Plan completion

Context: `project=pi-memory, plan=plans/v1-ext`.

User says: "v1-ext is done - all acceptance criteria pass."

Target: active plan `plan.md` `## Log`.
Extra step: call `memory_set_frontmatter(plan_file, "status", "completed")`.

## What this skill MUST NOT do

- Do not write to files outside the configured vault root.
- Do not delete or rewrite existing lines; captures are append-only.
- Do not create new domain files unless `[note].auto_create_domains = true`.
- Do not mutate frontmatter other than `status: completed` on the active plan when completion is clear.
- Do not ask permission before every capture; capture and report when it is clearly worthwhile.
