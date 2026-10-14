#!/usr/bin/env python3
"""
Splitwise REPL helper.
Pre-initializes `s` as an authenticated Splitwise instance.
Pass Python code as a command-line argument, or pipe it to stdin.

Usage:
  python repl.py '<code>'
  echo '<code>' | python repl.py
"""
import os
import sys
from pathlib import Path

# Load .env from skill root
skill_root = Path(__file__).parent.parent
env_file = skill_root / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

consumer_key = os.environ.get("SPLITWISE_CONSUMER_KEY", "")
consumer_secret = os.environ.get("SPLITWISE_CONSUMER_SECRET", "")
api_key = os.environ.get("SPLITWISE_API_KEY", "")

if not api_key:
    print("ERROR: SPLITWISE_API_KEY not set. Add it to skills/splitwise/.env", file=sys.stderr)
    sys.exit(1)

from splitwise import Splitwise
from splitwise.expense import Expense
from splitwise.user import ExpenseUser
from splitwise.group import Group

# `s` is the authenticated Splitwise instance available to all snippets
s = Splitwise(consumer_key, consumer_secret, api_key=api_key)

# Get code from arg or stdin
if len(sys.argv) > 1:
    code = sys.argv[1]
else:
    code = sys.stdin.read()

exec(compile(code, "<snippet>", "exec"), {
    "__builtins__": __builtins__,
    "s": s,
    "Splitwise": Splitwise,
    "Expense": Expense,
    "ExpenseUser": ExpenseUser,
    "Group": Group,
})
