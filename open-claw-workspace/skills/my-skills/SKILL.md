---
name: my-skills
description: >
  List Sergio's custom workspace skills and show a short usage reminder for each.
  Use when the user asks things like "my skills", "list my custom skills", "what skills do I have",
  "show custom skills", or runs /skill my-skills.
---

# My Skills

List skills from `~/.openclaw/workspace/skills` and present a concise reminder list.

## Steps

1. Enumerate directories under `~/.openclaw/workspace/skills`.
2. Keep only directories containing `SKILL.md`.
3. For each, read YAML frontmatter (`name`, `description`) from `SKILL.md`.
4. Return a compact list:
   - skill name
   - one-line description/triggers (trimmed)
   - quick invoke hint: `/skill <name> ...`

## Output style

- Keep it short and scannable.
- Sort alphabetically by skill name.
- Prefer bullet list; avoid dumping raw file contents.
