#!/usr/bin/env python3
"""Regenerate ~/.hermes/.env.example from .env: keep comments/blank lines, strip every value."""
import re
from pathlib import Path
H = Path.home() / ".hermes"
out = ["# Generated from .env by scripts/sync-env-example.py: keys only, values stripped.\n"]
for line in (H / ".env").read_text().splitlines(keepends=True):
    m = re.match(r"^(\s*)(export\s+)?([A-Za-z_][A-Za-z0-9_]*)=", line)
    if m:
        out.append(f"{m.group(1)}{m.group(2) or ''}{m.group(3)}=\n")
    elif not line.strip() or line.lstrip().startswith("#"):
        out.append(line if line.endswith("\n") else line + "\n")
(H / ".env.example").write_text("".join(out))
print(sum(1 for l in out if re.match(r"^\s*(export\s+)?[A-Za-z_]\w*=$", l)), "keys")
