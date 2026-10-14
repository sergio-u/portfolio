#!/usr/bin/env python3
"""
Scrapling snippet runner.

Pre-imports all Scrapling fetchers and session classes.
Runs the given code and exits cleanly (no interactive prompt).

Usage:
  python run.py '<code>'
  python run.py << 'PYEOF'
  multi-line code here
  PYEOF

Available names in snippet scope:
  Fetcher, StealthyFetcher, DynamicFetcher
  FetcherSession, StealthySession, DynamicSession
"""
import sys

# Get code from argument or stdin
if len(sys.argv) > 1:
    code = sys.argv[1]
else:
    code = sys.stdin.read()

if not code.strip():
    print("ERROR: No code provided.", file=sys.stderr)
    sys.exit(1)

from scrapling.fetchers import (
    Fetcher,
    StealthyFetcher,
    DynamicFetcher,
    FetcherSession,
    StealthySession,
    DynamicSession,
)

namespace = {
    "__builtins__": __builtins__,
    "Fetcher": Fetcher,
    "StealthyFetcher": StealthyFetcher,
    "DynamicFetcher": DynamicFetcher,
    "FetcherSession": FetcherSession,
    "StealthySession": StealthySession,
    "DynamicSession": DynamicSession,
}

try:
    exec(compile(code, "<snippet>", "exec"), namespace)
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(1)

# Explicit exit ensures no hanging browser processes block the caller
sys.exit(0)
