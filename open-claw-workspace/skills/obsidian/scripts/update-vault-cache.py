#!/usr/bin/env python3
"""
Update the Note Cache table in the obsidian SKILL.md.

Scans the vault for all .md files (excluding 10_Daily/ and .obsidian/),
builds a markdown table, and replaces the existing Note Cache section
in SKILL.md.

Usage:
    python3 scripts/update-vault-cache.py

Environment:
    VAULT_PATH  - override vault location (default: ~/Documents/Sync/Notebook/2026-H1)
    SKILL_PATH  - override SKILL.md location (default: sibling ../SKILL.md)
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

VAULT_DEFAULT = os.path.expanduser("~/Documents/Sync/Notebook/2026-H1")
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DEFAULT = SCRIPT_DIR.parent / "SKILL.md"

EXCLUDED_DIRS = {"10_Daily", ".obsidian", ".trash"}

# Section markers
CACHE_HEADER = "### Note Cache"
CACHE_END_MARKER = "### "  # next section at same or higher level


def scan_vault(vault_path: str) -> list[tuple[str, str]]:
    """Return sorted list of (relative_path, first_heading_or_filename) tuples."""
    vault = Path(vault_path)
    notes = []

    for md_file in sorted(vault.rglob("*.md")):
        # Skip excluded directories
        rel = md_file.relative_to(vault)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue

        # Extract first H1 heading as description hint
        description = ""
        try:
            with open(md_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    # Skip YAML frontmatter
                    if line == "---":
                        # Read until closing ---
                        for fmline in f:
                            if fmline.strip() == "---":
                                break
                        continue
                    if line.startswith("# "):
                        description = line[2:].strip()
                        break
                    if line and not line.startswith("#"):
                        # First non-empty, non-heading line as fallback
                        description = line[:80]
                        break
        except Exception:
            pass

        if not description:
            description = md_file.stem

        notes.append((str(rel), description))

    return notes


def build_table(notes: list[tuple[str, str]]) -> str:
    """Build markdown table from notes list."""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        CACHE_HEADER,
        "",
        "All notes except daily notes (`10_Daily/YYYY-MM-DD.md` files omitted for brevity). Check here before searching.",
        "",
        f"Last updated: {today}",
        "",
        "| Path | Description |",
        "|---|---|",
    ]

    for path, desc in notes:
        # Escape pipes in description
        desc = desc.replace("|", "\\|")
        lines.append(f"| `{path}` | {desc} |")

    lines.append("")
    lines.append(
        "> **Maintenance:** Update this table when notes are created, moved, or deleted."
        " This is a cache and may be outdated — if a note isn't listed here,"
        " fall back to `fdfind`/`rg` search before assuming it doesn't exist."
    )

    return "\n".join(lines)


def update_skill(skill_path: str, new_table: str) -> bool:
    """Replace the Note Cache section in SKILL.md. Returns True if updated."""
    path = Path(skill_path)
    content = path.read_text(encoding="utf-8")

    # Find the cache section
    cache_start = content.find(CACHE_HEADER)
    if cache_start == -1:
        print(f"Warning: '{CACHE_HEADER}' not found in {skill_path}. Appending.")
        content = content.rstrip() + "\n\n" + new_table + "\n"
        path.write_text(content, encoding="utf-8")
        return True

    # Find the end of the cache section (next ### header or end of file)
    after_header = content[cache_start + len(CACHE_HEADER):]
    end_match = re.search(r"\n### ", after_header)
    if end_match:
        cache_end = cache_start + len(CACHE_HEADER) + end_match.start()
    else:
        # Check for next ## header
        end_match = re.search(r"\n## ", after_header)
        if end_match:
            cache_end = cache_start + len(CACHE_HEADER) + end_match.start()
        else:
            cache_end = len(content)

    # Replace
    new_content = content[:cache_start] + new_table + "\n" + content[cache_end:]
    path.write_text(new_content, encoding="utf-8")
    return True


def main():
    vault_path = os.environ.get("VAULT_PATH", VAULT_DEFAULT)
    skill_path = os.environ.get("SKILL_PATH", str(SKILL_DEFAULT))

    if not Path(vault_path).is_dir():
        print(f"Error: Vault not found at {vault_path}", file=sys.stderr)
        sys.exit(1)

    if not Path(skill_path).is_file():
        print(f"Error: SKILL.md not found at {skill_path}", file=sys.stderr)
        sys.exit(1)

    notes = scan_vault(vault_path)
    print(f"Found {len(notes)} notes (excluding daily notes)")

    table = build_table(notes)
    update_skill(skill_path, table)
    print(f"Updated {skill_path}")


if __name__ == "__main__":
    main()
