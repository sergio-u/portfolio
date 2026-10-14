---
name: gws
description: >
  Google Workspace CLI — manage Calendar, Drive, Gmail, Sheets, and more.
  Use when the user wants to interact with any Google Workspace service.
  Triggers: "Google Workspace", "calendar", "drive", "sheets", "gmail",
  "check my calendar", "create event", "list drive files",
  "upload to drive", "send email", "check email", "create spreadsheet",
  "schedule meeting", "what's on my calendar".
---

# Google Workspace CLI Skill

Thin wrapper around `@googleworkspace/cli` (`gws`). Per-tool sub-skills live alongside this file as symlinks into the vendored upstream repo (`gws-repo/`); user-authored sibling skills add workflows that aren't part of upstream.

## Reference

Per-tool skills (symlinks into `gws-repo/skills/`):

| Skill | Description |
|-------|-------------|
| [gws-shared](gws-shared/SKILL.md) | Auth, global flags, CLI syntax, security rules |
| [gws-calendar](gws-calendar/SKILL.md) | Manage calendars and events (full API) |
| [gws-calendar-agenda](gws-calendar-agenda/SKILL.md) | Show upcoming events |
| [gws-calendar-insert](gws-calendar-insert/SKILL.md) | Create a new event |
| [gws-drive](gws-drive/SKILL.md) | Manage files, folders, shared drives (full API) |
| [gws-drive-upload](gws-drive-upload/SKILL.md) | Upload a file |
| [gws-gmail-read](gws-gmail-read/SKILL.md) | Read Gmail messages |
| [gws-sheets](gws-sheets/SKILL.md) | Read and write spreadsheets |

User-authored siblings (real dirs, tracked):

| Skill | Description |
|-------|-------------|
| [gws-calendar-flights](gws-calendar-flights/SKILL.md) | Add flight itineraries and trip blocks from booking confirmations |
| [gws-calendar-attach](gws-calendar-attach/SKILL.md) | Attach Drive files to existing calendar events |

For the full upstream skill catalog (100+ skills, recipes, personas), see `gws-repo/SKILL.md` after bootstrapping.

## Setup

`gws-repo/` is gitignored — see [SETUP.md](SETUP.md) to bootstrap on a fresh clone.

## Authentication

Prefer the local workspace wrapper `skills/gws/gws` for Google Workspace actions. It sets `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` from `~/.openclaw/.env`; npm-global `gws` may not have Sergio's credentials wired up.

```bash
skills/gws/gws auth setup                                              # one-time: create Cloud project, enable APIs
skills/gws/gws auth login                                              # subsequent logins
skills/gws/gws auth login -s drive,gmail,calendar,sheets               # scope-limited (testing/unverified apps)
```

## Quick reference

```bash
# Check today's agenda
skills/gws/gws calendar +agenda --today

# Create an event
skills/gws/gws calendar +insert --summary 'Meeting' \
  --start '2026-03-12T10:00:00-07:00' --end '2026-03-12T11:00:00-07:00'

# List Drive files
skills/gws/gws drive files list --params '{"pageSize": 5}'

# Discover any API method
skills/gws/gws schema calendar.events.insert
```

## User conventions (apply to all gws sub-skills)

- If Sergio explicitly asks to add/create a calendar event and provides enough event details (title/date/time, with location if available), create it directly without an extra confirmation prompt. Use `skills/gws/gws calendar +insert` and summarize the result afterward.
- Ask a concise clarification only when a required event detail is missing or ambiguous (for example: date, start time, timezone, target calendar, or which duplicate/conflicting interpretation to use).
- Confirm with the user before destructive or high-risk operations (deletes, bulk updates, moving files, sending emails, changing attendees/notifications, or modifying existing events in a way that could notify others). Calendar inserts requested explicitly by Sergio are not considered high-risk.
- Prefer `--dry-run` for destructive operations to validate locally first.
- Present results as clean summaries, not raw JSON. Use `--format json` only when parsing programmatically.
- Use `gws schema <method>` for runtime API discovery instead of memorizing parameters.
- Never output secrets (API keys, tokens) directly. Use `--sanitize <TEMPLATE>` for PII / content safety screening when applicable.
