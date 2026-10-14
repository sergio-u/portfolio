---
name: obsidian
description: >
  Manage Sergio's Obsidian vault -- create notes, search, organize, triage
  inbox, and maintain consistency. Use when the user says "daily note",
  "update vault", "find in notes", "obsidian", "search notes", "add a note",
  "save to my notebook", "triage inbox", "knowledge base", "find my note about",
  "move this to obsidian", "save this to obsidian", "create a note", or
  references their personal notes/notebook system.
---

# Obsidian Vault Manager

Manage Sergio's Obsidian vault -- create notes, search, organize, triage inbox, and maintain consistency.

## Execution

### Vault Location

```
~/Documents/Sync/Notebook/2026-H1
```

Assign to `$VAULT` mentally. All paths below are relative to this root.

### Create a Note

1. Determine the right folder from the folder table below.
2. **Filename**: Descriptive, capitalized major words, hyphens over underscores. Example: `Japan Food Guide - Authentic Restaurants.md`
3. **Daily notes**: Always `YYYY-MM-DD.md` in `10_Daily/`.
4. **Header**: Start with `# Title` matching the filename (without `.md`).
5. **Wiki-links**: Use `[[Note Title]]` for internal references. Do not use markdown links for internal notes.
6. **Write** the file with `write` tool.

#### Daily Note Template

If creating today's daily note and it doesn't already exist:

```markdown
# [Full Day Name], [Month] [Ordinal Day] [Year]

---

## Inbox

---

## Work

---

## Personal

---
```

Example: `# Friday, March 27th 2026`

Check first: `read 10_Daily/YYYY-MM-DD.md` -- if it exists, append to it instead.

### Search the Vault

**By content:**
```bash
rg "search terms" ~/Documents/Sync/Notebook/2026-H1 --type md -l
```
Add `-i` for case-insensitive. Add `--max-count 3` to limit matches per file.

**By filename:**
```bash
fdfind "pattern" ~/Documents/Sync/Notebook/2026-H1 -e md
```

**Recently modified:**
```bash
fdfind -e md --changed-within 7d ~/Documents/Sync/Notebook/2026-H1 --exclude .obsidian
```

**Find all wiki-link references to a note:**
```bash
rg '\[\[Note Title\]\]' ~/Documents/Sync/Notebook/2026-H1 --type md -l
```

### Append to an Existing Note

To add content under a specific section (e.g., "## Work" in a daily note):

1. `read` the file.
2. Find the target section header.
3. Find where that section ends (next `## ` header or `---` separator or EOF).
4. Use `edit` to insert content before the section boundary.

For timestamped work entries, use bold time format: `**HH:mm** - Entry text`

### Move / Rename a Note

1. Move the file with `exec` (`mv`).
2. **Update wiki-links**: Search for references to the old name and update them.
   ```bash
   rg '\[\[Old Note Title\]\]' ~/Documents/Sync/Notebook/2026-H1 --type md -l
   ```
3. For each file found, use `edit` to replace `[[Old Note Title]]` with `[[New Note Title]]`.
4. Always confirm with the user before bulk moves.

### Triage Inbox

1. List inbox contents:
   ```bash
   fdfind -e md . ~/Documents/Sync/Notebook/2026-H1/00_Inbox
   ```
2. For each note, read it briefly and suggest a destination folder.
3. Present suggestions to the user for approval before moving.

### Temporary Workflow: Habit System Weekly Loop

If the user asks to review the habit system week by week, update the current week plan, create the next week guide, or make in-flight adjustments during the week, follow:

`~/.openclaw/workspace/skills/obsidian/Habit System Workflow.md`

Use that workflow to decide:
- whether to update the week guide, the master plan, or both
- how to run weekly reviews from recent daily notes
- how to capture in-flight changes without rewriting the whole system
- how to create the next week's operating guide

## Domain-Specific

### Vault Structure

```
2026-H1/
  00_Inbox/                           # Unsorted captures -- triage regularly
  10_Daily/                           # Daily notes: YYYY-MM-DD.md (omitted below for brevity)
  20_Active_Projects/                 # Current projects and initiatives
    Interview Prep/                   #   Subfolder example
  30_Knowledge_Base/                  # Reference and evergreen notes
    Clippings/                        #   Web clippings, saved articles
    Guides/                           #   How-to guides, reference docs
      Work/                           #     Work-specific guides
  35_AI_Summaries/                    # AI-generated content and summaries
  99_System/                          # Vault config -- mostly hands off
    Templates/                        #   Templater templates
    Attachments/                      #   Media files, images
```

Numeric prefixes = workflow order (00 intake -> 10 daily -> 20 active -> 30 reference -> 35 AI -> 99 meta).

### Note Cache

All notes except daily notes (`10_Daily/YYYY-MM-DD.md` files omitted for brevity). Check here before searching.

Last updated: 2026-08-01

| Path | Description |
|---|---|
| `20_Active_Projects/Example Project.md` | Example project overview |
| `30_Knowledge_Base/Guides/Example Guide.md` | Example how-to guide |
| `80_AI/projects/example/project.md` | Example AI project memory |

> **Maintenance:** Update this table when notes are created, moved, or deleted. This is a cache and may be outdated — if a note isn't listed here, fall back to `fdfind`/`rg` search before assuming it doesn't exist.

### Choosing the Right Folder

| Content type | Destination |
|---|---|
| Quick capture, unsorted | `00_Inbox/` |
| Today's log, journal, work notes | `10_Daily/YYYY-MM-DD.md` |
| Project with active work | `20_Active_Projects/` (subfolder if complex) |
| Reference material, evergreen info | `30_Knowledge_Base/` |
| Web clipping, saved article | `30_Knowledge_Base/Clippings/` |
| How-to, guide, reference doc | `30_Knowledge_Base/Guides/` |
| AI-generated summary or research | `35_AI_Summaries/` |
| Template files only | `99_System/Templates/` |

When unsure, use `00_Inbox/` and let the user triage later.

### Formatting Rules

- **Headers**: `#` for title (once), `##` for sections, `###` for subsections.
- **Links**: `[[Note Title]]` for internal. Standard markdown for external URLs.
- **Timestamps**: `**HH:mm**` in bold for work log entries.
- **Lists**: Use `-` (hyphen), 2-space indent per level.
- **Tasks**: `- [ ]` for checkboxes.
- **Section separators**: `---` (three hyphens).
- **No Templater syntax**: When creating notes via CLI/tools, write literal dates and content. Templater syntax (`<% tp.* %>`) is only for templates used inside Obsidian.

Note: For a comprehensive formatting reference beyond these rules, a dedicated `references/formatting-guide.md` could house extended examples and edge cases.

## Conventions

- **Never modify** anything in `.obsidian/` -- managed by the Obsidian app.
- **Never delete notes** without explicit confirmation. Prefer moving to `00_Inbox/` if unsure.
- **Preserve wiki-links** when renaming or moving files.
- **Confirm before bulk operations** (moving multiple files, renaming with many references).
- **Attachments** go in `99_System/Attachments/`, referenced as `![[filename.ext]]`.
- Summarize search results cleanly -- show file paths and matched context, not raw grep output.
- Use machine-readable output when results will be parsed downstream.

## Syncthing Rescan

The vault is synced via Syncthing. After creating or updating any file, trigger a rescan so changes propagate to other devices immediately:

```bash
SYNCTHING_CONFIG=~/.local/state/syncthing/config.xml
read -r GUI_ADDR API_KEY <<<"$(python3 -c "
import xml.etree.ElementTree as ET
gui = ET.parse('$SYNCTHING_CONFIG').getroot().find('gui')
print(gui.find('address').text, gui.find('apikey').text)
")"
curl -s -X POST -H "X-API-Key: $API_KEY" \
  "http://$GUI_ADDR/rest/db/scan?folder=uety7-ydnmr&sub=<relative-path>"
```

- `<relative-path>` is relative to the Notebook root (e.g., `2026-H1/20_Active_Projects`)
- **Never hardcode the GUI address.** Syncthing binds to a single tailnet address, not
  `0.0.0.0`, so `localhost` will also refuse connections. The address changes across
  network migrations (this setup moved NetBird -> Tailscale), so always read
  `gui/address` from `config.xml` as shown above.
- Notebook folder ID: `uety7-ydnmr`
- Always trigger after `write` or `edit` operations on vault files
- A connection refusal here means the address is stale, **not** that Syncthing is down.
  Confirm with `ss -tlnp | grep 8384` or `pgrep -a syncthing` before concluding the
  service has failed.

## Requirements

- Obsidian vault synced at `~/Documents/Sync/Notebook/2026-H1`
- `rg` (ripgrep) and `fdfind` available on the system for search operations
- Write access to the vault directory
- Syncthing running for cross-device sync (see Syncthing Rescan above)

## Troubleshooting

### Vault not found or path errors
- Verify the vault exists at `~/Documents/Sync/Notebook/2026-H1`
- The vault path rotates by half-year (H1/H2). If files are missing, check if a new vault period has started and the path needs updating.

### File conflicts after sync
- Obsidian Sync or Syncthing may create conflict files (e.g., `Note (conflict).md`). Search for these with `fdfind "conflict" $VAULT -e md` and resolve manually.
- If two versions exist, read both and merge content, then delete the conflict copy (with user confirmation).

### Wiki-links broken after move/rename
- Always update references after moving a note. Search with `rg '\[\[Old Title\]\]' $VAULT --type md -l` and batch-update.
- If many links are broken, list them all for the user before making changes.

### Daily note already exists
- Always check with `read` before creating. If it exists, append to the appropriate section instead of overwriting.

### Search returns too many results
- Add `-i` for case-insensitive only when needed. Use `--max-count 3` to limit per-file matches.
- Narrow with glob filters: `rg "term" $VAULT --type md --glob '!99_System/**'`
