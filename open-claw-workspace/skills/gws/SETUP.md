# gws skill — setup

How to bootstrap the `gws` skill on a fresh clone, add or remove upstream skills, and update.

## Layout

```
skills/gws/
├── SKILL.md                ← thin reference + cross-cutting user conventions
├── SETUP.md                ← this file
├── gws                     ← npx-based wrapper script (tracked)
├── gws-calendar-flights/   ← user-authored skill (tracked)
├── gws-calendar-attach/    ← user-authored skill (tracked)
├── gws-repo/               ← upstream clone (gitignored)
└── gws-<name>              ← symlinks into gws-repo/skills/<name> (gitignored)
```

`gws-repo/` and the per-tool symlinks are **gitignored** — the git repo only tracks user-authored content. The symlinks exist on disk for the agent loader to discover the upstream skills.

## Bootstrap

### Option A — git clone the upstream repo (recommended)

```bash
git clone https://github.com/googleworkspace/cli skills/gws/gws-repo

for n in gws-calendar gws-calendar-agenda gws-calendar-insert \
         gws-drive gws-drive-upload gws-gmail-read \
         gws-shared gws-sheets; do
  ln -sfn "gws-repo/skills/$n" "skills/gws/$n"
done
```

### Option B — npx skills add (full upstream)

```bash
npx skills add https://github.com/googleworkspace/cli
```

Then run the same symlink loop from Option A.

### Option C — npx skills add (per-skill, no symlinks)

```bash
npx skills add https://github.com/googleworkspace/cli/tree/main/skills/gws-calendar
npx skills add https://github.com/googleworkspace/cli/tree/main/skills/gws-drive
# ...repeat for each desired skill
```

This installs each skill as a real directory, no symlinks needed. Update `.gitignore` to match if you don't want them tracked.

## Updating upstream

```bash
git -C skills/gws/gws-repo pull
```

Symlinks pick up the new content automatically — nothing else to do.

If you used Option C (`npx skills add`), re-run the command for each skill to refresh.

## Adding another upstream skill

```bash
ln -sfn gws-repo/skills/<new-name> skills/gws/<new-name>
```

Add the symlink path to `.gitignore` (the `gws-* working-dir symlinks` block) so it stays untracked.

## Adding your own skill

Create a real directory and SKILL.md under `skills/gws/`:

```
skills/gws/<your-skill>/SKILL.md
```

Track it normally with `git add`. Don't symlink user-authored skills — they should live in version control.

## Removing a skill

```bash
rm skills/gws/<name>            # removes only the symlink; gws-repo/ is untouched
```

Optionally drop the matching line from `.gitignore` if you want the absence visible elsewhere.

## Authentication

See [SKILL.md](SKILL.md) for `gws auth setup` and login flows.
