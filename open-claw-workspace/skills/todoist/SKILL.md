---
name: todoist
description: >
  Manage tasks, projects, and labels in Todoist via MCP. Use when the user wants
  to add tasks, check their to-do list, complete tasks, reschedule, search tasks,
  manage projects or sections, or do any Todoist operations. Triggers on "add a
  task", "remind me to", "to-do", "todoist", "what's on my list", "mark done",
  "complete task", "reschedule", "move task", "my tasks", "task list".
---

# Todoist

Interact with Todoist through the `todoist` MCP server.

## Execution

```bash
mcporter call todoist.<tool> param=value
mcporter call todoist.<tool> --args '{"param": "value"}'
```

Use `--output json` when you need to parse results.

## Task Routing

When the user adds tasks without specifying a project:

1. **Determine context** -- is it personal or work-related?
2. **Route to the appropriate inbox:**
   - Personal tasks -> `Personal > Inbox` (section `<id>`)
   - Work tasks -> `Work > Inbox` (section `<id>`)
3. If the task clearly belongs to an existing section (e.g., groceries, a specific work project), place it there directly.
4. If the user asks you to create a new project or section, do so and update the cache table above.

## PR Links

When a task includes a pull request URL, extract the PR number from the URL and add it to the task **description** in this format:

```
**PR:** [#<number>](<full URL>)
```

Example: given `https://<org>.visualstudio.com/Pipelines/_git/Contoso.GraphService/pullrequest/123456`, add:

```
**PR:** [#123456](https://<org>.visualstudio.com/Pipelines/_git/Contoso.GraphService/pullrequest/123456)
```

- Works with any PR URL format (Azure DevOps, GitHub, etc.) -- extract the trailing number.
- If multiple PR links are provided, stack them on separate lines.
- If the task already has a description, append the PR link(s) below existing content.

## AI Label

All tasks created by the agent must include the label `AI` (label name: `AI`). Pass `labels: ["AI"]` in the `add-tasks` call. This replaces the old convention of routing to a dedicated AI project.

## Reference

### Project & Section Cache

Use these IDs directly to avoid a `get-overview` roundtrip. If the user references a project or section not listed here, call `get-overview` or `find-projects`/`find-sections` to resolve it.

Last updated: 2026-04-05

| Type | Name | ID | Parent |
|---------|----------------------------|-----------------------|--------|
| Project | Personal | `<id>` | -- |
| Section | Personal > Inbox | `<id>` | Personal |
| Section | Personal > Weekend | `<id>` | Personal |
| Section | Personal > Projects | `<id>` | Personal |
| Section | Personal > Someday | `<id>` | Personal |
| Section | Personal > Wishlist | `<id>` | Personal |
| Section | Personal > Groceries | `<id>` | Personal |
| Project | Work | `<id>` | -- |
| Section | Work > Inbox | `<id>` | Work |
| Section | Work > ProjectA | `<projecta-section-id>` | Work |
| Section | Work > OCE | `<id>` | Work |
| Section | Work > ProjectB | `<projectb-section-id>` | Work |

**Global Inbox** (no project): `<id>`

> **Section semantics:**
> - **OCE** = on-call rotation tasks
> - **ProjectA** = active work project
> - **ProjectB** = paused work project; route by project context when both apply

> **Maintenance:** When you create or rename projects/sections, update this table.

## Conventions

- Confirm with the user before destructive actions: `delete-object`, `complete-tasks` on multiple items.
- For date queries, prefer `find-tasks-by-date` over `find-tasks` -- it handles overdue items properly.
- Use `get-overview` only when the cache above is insufficient (new/unknown projects).
- When creating projects or sections, update the cache table in this file afterward.
- Present results as readable summaries -- don't dump raw JSON at the user.
- Use `--output json` when parsing results programmatically.

## API Gotchas

### `add-tasks` uses camelCase keys for routing

`add-tasks` requires **camelCase** field names: `projectId`, `sectionId`, `parentId`. Snake_case (`project_id`, `section_id`, `parent_id`) is silently ignored and tasks land in the global Inbox.

```json
{"content": "Buy milk", "projectId": "<id>", "sectionId": "<id>", "labels": ["AI"]}
```

### `update-tasks` requires `content`

`update-tasks` silently skips tasks if `content` is not included in the payload. Always pass the current task title as `content` even if you're only changing other fields (labels, description, etc.).

### `reschedule-tasks` vs `update-tasks` for dates

- Use `reschedule-tasks` to change due dates on tasks that **already have a due date**. The field is `date` (not `dueDate`).
- `reschedule-tasks` fails if the task has no existing due date.
- For tasks **without a due date**, use `update-tasks` with `due_date` to set one for the first time.
- `update-tasks` with `dueDate` does NOT work for changing dates — the field is ignored.

### `delete-object` requires `type`

`delete-object` requires both `type` (e.g., `"task"`, `"project"`, `"section"`) and `id`. Omitting `type` returns a validation error.

```bash
mcporter call todoist.delete-object --args '{"type": "task", "id": "<task-id>"}'
```

### `find-tasks` pagination

Results are paginated (default 10). Check `hasMore` and use the `cursor` field from the response to fetch subsequent pages:

```bash
mcporter call todoist.find-tasks --args '{"projectId": "...", "cursor": "<cursor-from-previous>"}' --output json
```

## Requirements

- Todoist MCP server must be running and accessible via `mcporter`.
- MCP server configuration in the agent's MCP config file.

## Troubleshooting

### MCP connection failures
If `mcporter call todoist.<tool>` returns a connection error, verify the MCP server is running. Restart the server if needed and retry.

### Stale cache
If a project or section ID from the cache table returns a "not found" error, the cache is stale. Call `get-overview` to get current IDs and update the table in this file.

### Task not appearing in expected project
Check that the correct section ID was used. If the user recently reorganized projects, refresh the cache via `get-overview`.
