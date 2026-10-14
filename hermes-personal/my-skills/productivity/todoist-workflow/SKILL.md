---
name: todoist-workflow
description: "Use when reading or changing Todoist tasks or projects."
version: 0.1.0
author: Sergio + Hermes
metadata:
  hermes:
    tags: [todoist, tasks, productivity, gtd]
    related_skills: [weekly-review-planning]
---

# Todoist workflow (personal)

Local conventions on top of the official Doist MCP server (`todoist` in `mcp_servers`, package `@doist/todoist-mcp`, key `TODOIST_API_KEY` in `~/.hermes/.env`). This skill holds behavior only; the server is upstream-managed. This is the PERSONAL Hermes; the work Hermes has its own copy of this skill using the same Todoist account.

## IDs: use the cache first

Read `references/ids.md` before any call that needs a project/section/label/user ID. Don't look up IDs that are already cached.

- If a cached ID fails (404 / not found), or the user mentions a project, section or label that isn't cached, query Todoist once, then **update `references/ids.md`** (skill_manage write_file) with the date.
- The project URL slug ends in the ID: `app.todoist.com/app/project/personal-<id>` -> `<project-id>`.
- Times: the user's timezone is America/Los_Angeles. Resolve "today/tomorrow" in that zone.

## Conventions (v0, minimal; refine as they settle)

1. **Where tasks go:** personal by default -> Personal > Inbox. Use Work > Inbox only when the user explicitly says work. Never use the global Inbox. If a task clearly fits an existing section, put it there directly: groceries -> Personal > Groceries (SF > Groceries only when the user says SF), things to buy someday -> Wishlist, multi-step personal efforts -> Projects, not-now ideas -> Someday. Section meanings are in ids.md.
2. **Capture without asking:** when the user says "todo / remind me / add a task / add X to groceries", create the task and report it in one line. Grocery items: one task per item, short noun ("Milk"), no verb needed.
3. **Ask first:** completing, deleting or moving tasks, editing tasks the user wrote, and bulk changes of more than 3 tasks. This applies even in YOLO mode.
4. **Task text:** begin with a verb and keep it short ("Book dentist"). Put context and source links in the description, not the title.
4a. **`AI` label:** every task the agent creates gets the `AI` label, so agent-created tasks stay auditable.
5. **Priority:** use only P1 (this week, it matters) and P4 (default). Don't set P2/P3 unless asked. (In the API, `priority` 4 = P1 and 1 = P4.)
6. **Due dates:** set them only for real deadlines or when the user names a date. Never invent dates to "organize".
7. **Routines:** Core Routines section + `core-routines` label hold recurring personal habits; don't edit their recurrence without asking.
8. **Labels:** reuse existing labels (see ids.md); don't create new ones without the user agreeing.

## Pitfalls

Items marked (legacy) came from the old OpenClaw skill (April 2026, older server version). Re-check them against the tool schema if a call misbehaves, and delete any that no longer apply.

- (legacy) `add-tasks` takes camelCase `projectId`/`sectionId`/`parentId`. With snake_case the task silently lands in the global Inbox. After creating a task, confirm it landed in the right project.
- (legacy) `update-tasks` silently skipped tasks when `content` was missing, so pass the current title.
- (legacy) `reschedule-tasks` only works on tasks that already have a due date. To set a first due date, use `update-tasks`.
- `delete-object` needs both `type` and `id`.
- `find-tasks` is paginated: follow `cursor` while `hasMore` is true. For date questions (today, overdue), use `find-tasks-by-date`.
- `@doist/todoist-ai` is deprecated; the package is now `@doist/todoist-mcp`.
- REST base is `https://api.todoist.com/api/v1` (paginated `results`). The old `/rest/v2` is gone, so prefer the MCP tools for routine work.
