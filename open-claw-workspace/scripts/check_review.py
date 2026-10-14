#!/usr/bin/env python3
"""Validate a historical-curation slice review before anything is moved.

Catches the failure modes that matter for a personal agent:
  - schema/key drift (e.g. "records" vs "reviews")
  - a source with no decision, or a decision for an unknown source
  - summarize claims with missing or unresolvable citations
  - source files edited between manifest and review
  - sensitive values leaking into the curated summary

Usage: python3 scripts/check_review.py state/memory-curator/history-runs/<run-id>
Exit 0 = safe to apply. Exit 1 = do not proceed.
"""

from __future__ import annotations

import json
import hashlib
import re
import sys
from pathlib import Path

ACTIONS = {"archive-only", "summarize"}

# Values that must never reach a curated summary.
SENSITIVE = re.compile(
    r"""(
      Bearer\s|API_KEY|TOKEN\s*=|[Pp]assword
    | \b\d{1,3}(?:\.\d{1,3}){3}\b          # bare IPs
    | nabu\.casa
    | Sender\s*\(untrusted|Conversation\s+info\s*\(untrusted
    | "(?:message_id|sender_id|conversation_label|topic_id)"
    | ^\s*(?:user|assistant):\s            # raw transcript turns
    )""",
    re.X | re.M,
)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def main() -> int:
    if len(sys.argv) != 2:
        fail("usage: check_review.py <run-dir>")
    run = Path(sys.argv[1])
    workspace = Path(__file__).resolve().parents[1]

    manifest_path = run / "manifest.json"
    review_path = run / "review.json"
    for p in (manifest_path, review_path):
        if not p.exists():
            fail(f"missing {p}")

    try:
        manifest = json.loads(manifest_path.read_text())
        review = json.loads(review_path.read_text())
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON: {exc}")

    # Accept either key, but say so loudly rather than silently coercing.
    records = review.get("records")
    if records is None:
        records = review.get("reviews")
        if records is not None:
            print("WARN: review uses legacy 'reviews' key; prefer 'records'")
    if not isinstance(records, list):
        fail("review has no 'records' (or 'reviews') array")

    sources = {f["path"] for f in manifest["files"]}
    reviewed = [r.get("source") for r in records]

    if len(reviewed) != len(set(reviewed)):
        fail("duplicate decisions for the same source")
    missing = sources - set(reviewed)
    extra = set(reviewed) - sources
    if missing:
        fail(f"no decision for: {sorted(missing)}")
    if extra:
        fail(f"decision for unknown source: {sorted(extra)}")

    # Sources must be untouched since the manifest was written.
    for f in manifest["files"]:
        p = workspace / f["path"]
        if not p.exists():
            fail(f"source disappeared: {f['path']}")
        if hashlib.sha256(p.read_bytes()).hexdigest() != f["sha256"]:
            fail(f"source changed since manifest: {f['path']}")

    summary = run / "summary-preview.md"
    summary_text = summary.read_text() if summary.exists() else ""

    n_summarize = 0
    for r in records:
        src = r.get("source")
        action = r.get("action")
        if action not in ACTIONS:
            fail(f"{src}: invalid action {action!r} (expected {sorted(ACTIONS)})")
        if not (r.get("rationale") or "").strip():
            fail(f"{src}: missing rationale")

        if action != "summarize":
            continue
        n_summarize += 1

        claims = r.get("durable_claims") or []
        if not claims:
            fail(f"{src}: summarize with no durable_claims (use archive-only)")

        cite = r.get("source_citation", "")
        m = re.match(r"(memory/[^#]+)#L(\d+)-L(\d+)$", cite)
        if not m:
            fail(f"{src}: bad citation {cite!r} (want memory/file.md#L10-L20)")
        cited = workspace / m.group(1)
        if not cited.exists():
            fail(f"{src}: citation points at missing file {m.group(1)}")
        n_lines = len(cited.read_text(errors="replace").splitlines())
        start, end = int(m.group(2)), int(m.group(3))
        if not (1 <= start <= end <= n_lines):
            fail(f"{src}: citation {cite} out of range (file has {n_lines} lines)")

        for claim in claims:
            if claim.strip() and claim.strip() not in summary_text:
                fail(f"{src}: claim not present in summary-preview.md: {claim[:60]}...")

    if summary_text:
        hits = SENSITIVE.findall(summary_text)
        if hits:
            fail(f"sensitive content in summary: {hits[:5]}")

    print(
        f"OK: {len(records)} sources, {n_summarize} summarize, "
        f"{len(records) - n_summarize} archive-only, hashes match, citations resolve"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
