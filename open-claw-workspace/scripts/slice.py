#!/usr/bin/env python3
"""Occasional curation of historical memory files, one small slice at a time.

Companion to memory_curator.py (which handles weekly Dreaming output). This one
handles the orthogonal chore: whole raw session transcripts in memory/*.md that
are searchable but mostly noise.

Reuses memory_curator's transaction primitives; adds only slice-specific logic.

    slice.py candidates --limit 20        # what is left to curate
    slice.py prepare  --name mar-batch --files a.md b.md
    # ...agent writes review.json + summary-preview.md, then:
    python3 scripts/check_review.py <run-dir>
    slice.py apply    --run-id mar-batch  # archive + summary, atomically
    slice.py commit   --run-id mar-batch  # after reindex + spot-check
    slice.py restore  --run-id mar-batch  # undo, verified by hash
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

_spec = importlib.util.spec_from_file_location(
    "memory_curator", Path(__file__).with_name("memory_curator.py")
)
mc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mc)

CuratorError = mc.CuratorError
ACTIONS = {"archive-only", "summarize"}

# A file is "raw session transcript" if it looks like the session-memory hook
# wrote it, rather than a hand-curated daily note.
SESSION_HEADER = re.compile(r"^# Session:", re.M)
ROLE_TURN = re.compile(r"^(?:user|assistant):\s", re.M | re.I)


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def slice_paths(workspace: Path, run_id: str | None = None) -> dict[str, Path]:
    root = workspace / "state" / "memory-curator"
    paths = {
        "runs": root / "history-runs",
        "archives": root / "history-archive",
        "curated": workspace / "memory" / "curated",
    }
    if run_id:
        paths["run"] = paths["runs"] / run_id
        paths["archive"] = paths["archives"] / run_id
    return paths


def is_raw_session(text: str) -> bool:
    return bool(SESSION_HEADER.search(text)) or bool(ROLE_TURN.search(text))


def already_curated(workspace: Path) -> set[str]:
    """Paths archived by any previously applied slice."""
    done: set[str] = set()
    runs = slice_paths(workspace)["runs"]
    if not runs.exists():
        return done
    for op_path in runs.glob("*/operation.json"):
        op = mc.read_json(op_path, {})
        for item in op.get("files", []):
            done.add(item["source"])
    return done


def candidates(workspace: Path, limit: int) -> list[dict[str, Any]]:
    done = already_curated(workspace)
    rows = []
    for path in sorted((workspace / "memory").glob("*.md")):
        rel = str(path.relative_to(workspace))
        if rel in done:
            continue
        text = path.read_text(errors="replace")
        if not is_raw_session(text):
            continue
        rows.append({"path": rel, "bytes": len(text.encode()), "raw_session": True})
    rows.sort(key=lambda r: r["path"])
    return rows[:limit]


def prepare(workspace: Path, name: str, files: list[str]) -> dict[str, Any]:
    paths = slice_paths(workspace, name)
    if paths["run"].exists():
        raise CuratorError(f"slice already exists: {paths['run']}")
    if paths["archive"].exists():
        raise CuratorError(f"archive already exists: {paths['archive']}")

    done = already_curated(workspace)
    entries = []
    for rel in files:
        rel = str(Path(rel))
        if rel in done:
            raise CuratorError(f"already curated in an earlier slice: {rel}")
        src = workspace / rel
        if not src.exists():
            raise CuratorError(f"missing source: {rel}")
        data = src.read_bytes()
        entries.append(
            {
                "path": rel,
                "bytes": len(data),
                "sha256": mc.file_fingerprint(src)["sha256"],
            }
        )
    if not entries:
        raise CuratorError("no files given")

    manifest = {
        "version": 1,
        "run_id": name,
        "mode": "dry-run",
        "created_at": mc.now_iso(),
        "policy": {
            "source_files_immutable": True,
            "archive_only_after_review": True,
            "summary_destination": f"memory/curated/{name}.md",
            "archive_destination": str(paths["archive"].relative_to(workspace)),
        },
        "files": entries,
    }
    paths["run"].mkdir(parents=True)
    mc.write_json(paths["run"] / "manifest.json", manifest)
    return {
        "run_id": name,
        "files": len(entries),
        "bytes": sum(e["bytes"] for e in entries),
        "run_dir": str(paths["run"].relative_to(workspace)),
        "next": "write review.json + summary-preview.md, then run check_review.py",
    }


def _load_review(run_dir: Path) -> list[dict[str, Any]]:
    review = mc.read_json(run_dir / "review.json", None)
    if not review:
        raise CuratorError("missing review.json; run the semantic review first")
    records = review.get("records") or review.get("reviews")
    if not isinstance(records, list):
        raise CuratorError("review.json has no 'records' array")
    return records


def apply(workspace: Path, run_id: str) -> dict[str, Any]:
    paths = slice_paths(workspace, run_id)
    run_dir = paths["run"]
    manifest = mc.read_json(run_dir / "manifest.json", None)
    if not manifest:
        raise CuratorError(f"missing manifest for slice {run_id}")
    records = _load_review(run_dir)

    by_source = {r["source"]: r for r in records}
    expected = {f["path"] for f in manifest["files"]}
    if set(by_source) != expected:
        raise CuratorError("review does not cover exactly the manifest sources")
    for r in records:
        if r.get("action") not in ACTIONS:
            raise CuratorError(f"{r['source']}: invalid action {r.get('action')!r}")

    # Preimages must be untouched since prepare.
    for f in manifest["files"]:
        src = workspace / f["path"]
        if not src.exists():
            raise CuratorError(f"source disappeared: {f['path']}")
        if mc.file_fingerprint(src)["sha256"] != f["sha256"]:
            raise CuratorError(f"source changed since prepare: {f['path']}")

    archive = paths["archive"]
    raw_dir = archive / "raw"
    raw_dir.mkdir(parents=True, mode=0o700)

    op = {
        "version": 1,
        "run_id": run_id,
        "status": "prepared",
        "prepared_at": mc.now_iso(),
        "archive_root": str(archive.relative_to(workspace)),
        "summary_path": manifest["policy"]["summary_destination"],
        "files": [],
    }

    # Copy and verify before removing anything.
    for f in manifest["files"]:
        src = workspace / f["path"]
        dst = raw_dir / f["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if mc.file_fingerprint(dst)["sha256"] != f["sha256"]:
            raise CuratorError(f"archive verification failed: {f['path']}")
        op["files"].append(
            {
                "source": f["path"],
                "archive": str(dst.relative_to(workspace)),
                "sha256": f["sha256"],
                "action": by_source[f["path"]]["action"],
            }
        )
    mc.write_json(run_dir / "operation.json", op)

    # Write the distilled summary, if any claims survived review.
    summarize = [r for r in records if r["action"] == "summarize"]
    if summarize:
        out = workspace / manifest["policy"]["summary_destination"]
        lines = [
            f"# Curated Historical Memory - {run_id}",
            "",
            "_Distilled from archived raw session transcripts; originals in the curator archive._",
            "",
        ]
        for r in summarize:
            for claim in r.get("durable_claims", []):
                lines.append(f"- {claim} Source: {r['source_citation']}")
        mc.atomic_write_text(out, "\n".join(lines) + "\n", run_id)
        op["summary_written"] = True
        op["summary_sha256"] = mc.file_fingerprint(out)["sha256"]

    for f in manifest["files"]:
        (workspace / f["path"]).unlink()

    op["status"] = "applied"
    op["applied_at"] = mc.now_iso()
    mc.write_json(run_dir / "operation.json", op)
    counts: dict[str, int] = {}
    for item in op["files"]:
        counts[item["action"]] = counts.get(item["action"], 0) + 1
    return {
        "run_id": run_id,
        "status": "applied",
        "counts": counts,
        "summary_written": op.get("summary_written", False),
        "next": "openclaw memory index --force, spot-check recall, then commit",
    }


def commit(workspace: Path, run_id: str, note: str | None) -> dict[str, Any]:
    run_dir = slice_paths(workspace, run_id)["run"]
    op = mc.read_json(run_dir / "operation.json", None)
    if not op:
        raise CuratorError(f"missing operation.json for slice {run_id}")
    if op["status"] != "applied":
        raise CuratorError(f"slice status is {op['status']!r}, expected 'applied'")

    for item in op["files"]:
        if (workspace / item["source"]).exists():
            raise CuratorError(f"source still present: {item['source']}")
        arc = workspace / item["archive"]
        if not arc.exists():
            raise CuratorError(f"archive missing: {item['archive']}")
        if mc.file_fingerprint(arc)["sha256"] != item["sha256"]:
            raise CuratorError(f"archive hash mismatch: {item['archive']}")

    op["status"] = "committed"
    op["committed_at"] = mc.now_iso()
    if note:
        op["note"] = note
    mc.write_json(run_dir / "operation.json", op)
    return {"run_id": run_id, "status": "committed", "files": len(op["files"])}


def restore(workspace: Path, run_id: str) -> dict[str, Any]:
    """Undo a slice: put archived originals back, remove the summary."""
    run_dir = slice_paths(workspace, run_id)["run"]
    op = mc.read_json(run_dir / "operation.json", None)
    if not op:
        raise CuratorError(f"missing operation.json for slice {run_id}")

    for item in op["files"]:
        arc = workspace / item["archive"]
        if not arc.exists():
            raise CuratorError(f"archive missing, cannot restore: {item['archive']}")
        if mc.file_fingerprint(arc)["sha256"] != item["sha256"]:
            raise CuratorError(f"archive hash mismatch, refusing: {item['archive']}")

    restored = []
    for item in op["files"]:
        dst = workspace / item["source"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(workspace / item["archive"], dst)
        restored.append(item["source"])

    summary = op.get("summary_path")
    if summary and op.get("summary_written"):
        (workspace / summary).unlink(missing_ok=True)

    op["status"] = "restored"
    op["restored_at"] = mc.now_iso()
    mc.write_json(run_dir / "operation.json", op)
    return {
        "run_id": run_id,
        "status": "restored",
        "files": len(restored),
        "next": "openclaw memory index --force",
    }


def status(workspace: Path) -> dict[str, Any]:
    runs = slice_paths(workspace)["runs"]
    slices = []
    if runs.exists():
        for run_dir in sorted(runs.iterdir()):
            op = mc.read_json(run_dir / "operation.json", None)
            man = mc.read_json(run_dir / "manifest.json", {})
            slices.append(
                {
                    "run_id": run_dir.name,
                    "status": op["status"] if op else "prepared",
                    "files": len(op["files"]) if op else len(man.get("files", [])),
                }
            )
    remaining = len(candidates(workspace, limit=10**6))
    return {"slices": slices, "remaining_raw_session_files": remaining}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=str(workspace_root()))
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("candidates", help="list uncurated raw session files")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("prepare", help="snapshot a slice for review")
    p.add_argument("--name", required=True)
    p.add_argument("--files", nargs="+", required=True)

    for name, helptext in (
        ("apply", "archive sources and write the summary"),
        ("restore", "undo an applied slice"),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--run-id", required=True)

    p = sub.add_parser("commit", help="finalize after reindex and spot-check")
    p.add_argument("--run-id", required=True)
    p.add_argument("--note")

    sub.add_parser("status", help="slice ledger and remaining work")

    args = parser.parse_args()
    ws = Path(args.workspace).expanduser().resolve()
    try:
        if args.command == "candidates":
            result = {"candidates": candidates(ws, args.limit)}
        elif args.command == "prepare":
            result = prepare(ws, args.name, args.files)
        elif args.command == "apply":
            result = apply(ws, args.run_id)
        elif args.command == "commit":
            result = commit(ws, args.run_id, args.note)
        elif args.command == "restore":
            result = restore(ws, args.run_id)
        else:
            result = status(ws)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (CuratorError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
