#!/usr/bin/env python3
"""Transactional guardrails for semantic curation of Dreaming promotions.

The semantic agent edits MEMORY.md/USER.md and writes decisions.json. This
helper owns discovery, snapshots, validation, rollback, and the idempotency
ledger so a failed or interrupted curator run cannot silently corrupt memory.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any


PROMOTION_HEADING_RE = re.compile(r"^## Promoted From Short-Term Memory \(([^)]+)\)\s*$")
MARKER_RE = re.compile(r"^[ \t]*<!--\s*openclaw-memory-promotion:([^\r\n]*?)\s*-->[ \t]*$")
SOURCE_KEY_RE = re.compile(r"^memory:(.+):(\d+):(\d+)$")
METRIC_RE = re.compile(r"\[score=\d+(?:\.\d+)?\s+recalls=\d+\s+avg=\d+(?:\.\d+)?\s+source=memory/", re.I)
BANNED_RE = re.compile(
    r"Sender \(untrusted metadata\)|Conversation info \(untrusted metadata\)|"
    r'\"(?:message_id|sender_id|conversation_label|topic_id|group_subject)\"\s*:|'
    r"(?:^|\s)(?:user|assistant):\s",
    re.I | re.M,
)
ALLOWED_ACTIONS = {"keep", "rewrite", "remove"}
TRACKED = ("MEMORY.md", "USER.md")


class CuratorError(RuntimeError):
    pass


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def run_id_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_fingerprint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "sha256": None, "size": 0}
    data = path.read_bytes()
    return {"exists": True, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def state_paths(workspace: Path) -> dict[str, Path]:
    root = workspace / "state" / "memory-curator"
    return {
        "root": root,
        "runs": root / "runs",
        "ledger": root / "ledger.json",
        "lock": root / "active-run.json",
    }


def parse_promotions(memory_text: str) -> list[dict[str, Any]]:
    lines = memory_text.splitlines(keepends=True)
    headings: list[tuple[int, str]] = []
    all_level_two = [idx for idx, line in enumerate(lines) if line.startswith("## ")]
    for idx, line in enumerate(lines):
        match = PROMOTION_HEADING_RE.match(line.rstrip("\r\n"))
        if match:
            headings.append((idx, match.group(1)))

    candidates: list[dict[str, Any]] = []
    for section_start, section_date in headings:
        section_end = next((idx for idx in all_level_two if idx > section_start), len(lines))
        marker_rows: list[tuple[int, str]] = []
        for idx in range(section_start + 1, section_end):
            match = MARKER_RE.match(lines[idx].rstrip("\r\n"))
            if match:
                marker_rows.append((idx, match.group(1).strip()))
        for marker_idx, (line_idx, key) in enumerate(marker_rows):
            entry_end = marker_rows[marker_idx + 1][0] if marker_idx + 1 < len(marker_rows) else section_end
            raw = "".join(lines[line_idx:entry_end]).strip()
            source_match = SOURCE_KEY_RE.match(key)
            source = None
            if source_match:
                source = {
                    "path": source_match.group(1),
                    "start_line": int(source_match.group(2)),
                    "end_line": int(source_match.group(3)),
                }
            candidates.append(
                {
                    "marker": key,
                    "section_date": section_date,
                    "memory_start_line": line_idx + 1,
                    "memory_end_line": entry_end,
                    "raw": raw,
                    "raw_sha256": sha256_text(raw),
                    "source": source,
                }
            )
    return candidates


def source_excerpt(workspace: Path, source: dict[str, Any] | None, context: int = 4) -> dict[str, Any] | None:
    if not source:
        return None
    path = workspace / source["path"]
    if not path.exists() or not path.is_file():
        return {**source, "error": "source file missing"}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, int(source["start_line"]) - context)
    end = min(len(lines), int(source["end_line"]) + context)
    excerpt = [{"line": i, "text": lines[i - 1]} for i in range(start, end + 1)]
    return {**source, "context_start": start, "context_end": end, "excerpt": excerpt}


def load_ledger(workspace: Path) -> dict[str, Any]:
    paths = state_paths(workspace)
    return read_json(paths["ledger"], {"version": 1, "updated_at": None, "entries": {}})


def discover(workspace: Path, include_all: bool) -> list[dict[str, Any]]:
    memory_path = workspace / "MEMORY.md"
    memory_text = memory_path.read_text(encoding="utf-8") if memory_path.exists() else ""
    ledger = load_ledger(workspace)
    processed = set(ledger.get("entries", {}))
    found = []
    for candidate in parse_promotions(memory_text):
        if not include_all and candidate["marker"] in processed:
            continue
        candidate["source_evidence"] = source_excerpt(workspace, candidate["source"])
        found.append(candidate)
    return found


def acquire_lock(workspace: Path, run_id: str) -> None:
    lock = state_paths(workspace)["lock"]
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists():
        active = read_json(lock, {})
        raise CuratorError(f"active curator run exists: {active.get('run_id', 'unknown')}; recover or roll it back first")
    write_json(lock, {"run_id": run_id, "created_at": now_iso()})


def assert_lock(workspace: Path, run_id: str) -> None:
    active = read_json(state_paths(workspace)["lock"], {})
    if active.get("run_id") != run_id:
        raise CuratorError(f"run {run_id} does not own the active curator lock")


def release_lock(workspace: Path, run_id: str) -> None:
    assert_lock(workspace, run_id)
    state_paths(workspace)["lock"].unlink(missing_ok=True)


def prepare(workspace: Path, include_all: bool, requested_run_id: str | None) -> dict[str, Any]:
    run_id = requested_run_id or run_id_now()
    acquire_lock(workspace, run_id)
    try:
        paths = state_paths(workspace)
        run_dir = paths["runs"] / run_id
        if run_dir.exists():
            raise CuratorError(f"run directory already exists: {run_dir}")
        backup_dir = run_dir / "backup"
        backup_dir.mkdir(parents=True)
        snapshots = []
        for relative in TRACKED:
            source = workspace / relative
            target = backup_dir / relative
            existed = source.exists()
            if existed:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            snapshots.append({"path": relative, "existed": existed, "fingerprint": file_fingerprint(source)})
        candidates = discover(workspace, include_all)
        manifest = {
            "version": 1,
            "run_id": run_id,
            "created_at": now_iso(),
            "workspace": str(workspace),
            "include_all": include_all,
            "snapshots": snapshots,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "decisions_path": str(run_dir / "decisions.json"),
        }
        write_json(run_dir / "manifest.json", manifest)
        run_status = "prepared" if candidates else "no_candidates"
        write_json(run_dir / "status.json", {"run_id": run_id, "status": run_status, "updated_at": now_iso()})
        if not candidates:
            release_lock(workspace, run_id)
        return manifest
    except Exception:
        state_paths(workspace)["lock"].unlink(missing_ok=True)
        raise


def load_run(workspace: Path, run_id: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    assert_lock(workspace, run_id)
    run_dir = state_paths(workspace)["runs"] / run_id
    manifest = read_json(run_dir / "manifest.json", None)
    decisions = read_json(run_dir / "decisions.json", None)
    if not manifest:
        raise CuratorError(f"missing manifest for run {run_id}")
    if not decisions:
        raise CuratorError(f"missing decisions.json for run {run_id}")
    return run_dir, manifest, decisions


def atomic_write_text(path: Path, text: str, run_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode if path.exists() else None
    temp = path.with_name(f".{path.name}.memory-curator-{run_id}.tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    if mode is not None:
        os.chmod(temp, mode)
    os.replace(temp, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def append_under_heading(text: str, heading: str, entry: str) -> str:
    if entry.strip() in text:
        return text
    lines = text.splitlines(keepends=True)
    heading_idx = next((idx for idx, line in enumerate(lines) if line.rstrip("\r\n") == heading), None)
    if heading_idx is None:
        base = text.rstrip()
        return f"{base}\n\n{heading}\n\n{entry.strip()}\n"
    end = next((idx for idx in range(heading_idx + 1, len(lines)) if lines[idx].startswith("## ")), len(lines))
    lines.insert(end, ("" if end > 0 and lines[end - 1].endswith("\n\n") else "\n") + entry.strip() + "\n")
    return "".join(lines)


def remove_empty_promotion_sections(text: str) -> str:
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    idx = 0
    while idx < len(lines):
        if PROMOTION_HEADING_RE.match(lines[idx].rstrip("\r\n")):
            end = next((row for row in range(idx + 1, len(lines)) if lines[row].startswith("## ")), len(lines))
            body = "".join(lines[idx + 1 : end]).strip()
            if not body:
                while output and not output[-1].strip():
                    output.pop()
                if output and end < len(lines):
                    output.append("\n")
                idx = end
                continue
        output.append(lines[idx])
        idx += 1
    return "".join(output).rstrip() + "\n"


def apply_decisions(workspace: Path, run_id: str) -> dict[str, Any]:
    run_dir, manifest, decisions = load_run(workspace, run_id)
    errors = validate_decisions(manifest, decisions)
    if errors:
        raise CuratorError("invalid decisions: " + "; ".join(errors))
    for snapshot in manifest["snapshots"]:
        relative = snapshot["path"]
        if file_fingerprint(workspace / relative) != snapshot.get("fingerprint"):
            raise CuratorError(f"apply conflict; {relative} changed after prepare")
    memory_path = workspace / "MEMORY.md"
    user_path = workspace / "USER.md"
    memory_text = memory_path.read_text(encoding="utf-8")
    user_text = user_path.read_text(encoding="utf-8")
    candidate_map = {candidate["marker"]: candidate for candidate in manifest["candidates"]}
    counts: dict[str, int] = {action: 0 for action in ALLOWED_ACTIONS}
    for row in decisions["decisions"]:
        marker = row["marker"]
        action = row["action"]
        candidate = candidate_map[marker]
        raw = candidate["raw"]
        if raw not in memory_text:
            raise CuratorError(f"candidate body changed or missing before apply: {marker}")
        entry = ""
        if action in {"keep", "rewrite"}:
            entry = (
                f"<!-- openclaw-memory-promotion:{marker} -->\n"
                f"- {row['claim'].strip()} Source: {row['source_citation'].strip()}"
            )
        memory_text = memory_text.replace(raw, "", 1)
        if entry:
            if row.get("destination") == "USER.md":
                observed = dt.date.today().isoformat()
                user_entry = (
                    f"- [active; observed {observed}] {row['claim'].strip()} "
                    f"Source: {row['source_citation'].strip()}"
                )
                user_text = append_under_heading(user_text, "## Automatically Curated Directives", user_entry)
            else:
                memory_text = append_under_heading(memory_text, "## Curated Dreaming Memories", entry)
        counts[action] += 1
    memory_text = remove_empty_promotion_sections(memory_text)
    atomic_write_text(memory_path, memory_text, run_id)
    if user_text != user_path.read_text(encoding="utf-8"):
        atomic_write_text(user_path, user_text, run_id)
    write_json(
        run_dir / "status.json",
        {"run_id": run_id, "status": "applied", "updated_at": now_iso(), "counts": counts},
    )
    return {"run_id": run_id, "status": "applied", "counts": counts}


def validate_decisions(manifest: dict[str, Any], decisions: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if decisions.get("version") != 1:
        errors.append("decisions.version must be 1")
    if decisions.get("run_id") != manifest.get("run_id"):
        errors.append("decisions.run_id does not match manifest")
    rows = decisions.get("decisions")
    if not isinstance(rows, list):
        return errors + ["decisions.decisions must be an array"]
    expected = {item["marker"] for item in manifest["candidates"]}
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"decision {index} must be an object")
            continue
        marker = row.get("marker")
        action = row.get("action")
        if marker not in expected:
            errors.append(f"decision {index} references unknown marker: {marker}")
        if marker in seen:
            errors.append(f"duplicate decision for marker: {marker}")
        if isinstance(marker, str):
            seen.add(marker)
        if action not in ALLOWED_ACTIONS:
            errors.append(f"decision {index} has invalid action: {action}")
        if not isinstance(row.get("reason"), str) or not row["reason"].strip():
            errors.append(f"decision {index} requires a reason")
        if action in {"keep", "rewrite"}:
            claim = row.get("claim")
            if not isinstance(claim, str) or not claim.strip():
                errors.append(f"decision {index} action {action} requires claim")
            elif len(claim) > 700:
                errors.append(f"decision {index} claim exceeds 700 characters")
            citation = row.get("source_citation")
            if not isinstance(citation, str) or not re.match(r"^memory/.+#L\d+(?:-L\d+)?$", citation):
                errors.append(f"decision {index} requires source_citation like memory/file.md#L1-L2")
    missing = expected - seen
    extra = seen - expected
    if missing:
        errors.append(f"missing decisions for {len(missing)} candidate(s)")
    if extra:
        errors.append(f"unexpected decisions for {len(extra)} candidate(s)")
    return errors


def current_entry_for_marker(memory_text: str, marker: str) -> str | None:
    for candidate in parse_promotions(memory_text):
        if candidate["marker"] == marker:
            return candidate["raw"]
    marker_text = f"<!-- openclaw-memory-promotion:{marker} -->"
    idx = memory_text.find(marker_text)
    if idx < 0:
        return None
    tail = memory_text[idx:]
    next_marker = tail.find("<!-- openclaw-memory-promotion:", len(marker_text))
    next_heading = tail.find("\n## ", len(marker_text))
    ends = [value for value in (next_marker, next_heading) if value >= 0]
    return tail[: min(ends) if ends else len(tail)].strip()


def validate(workspace: Path, run_id: str) -> dict[str, Any]:
    run_dir, manifest, decisions = load_run(workspace, run_id)
    errors = validate_decisions(manifest, decisions)
    memory_path = workspace / "MEMORY.md"
    user_path = workspace / "USER.md"
    memory_text = memory_path.read_text(encoding="utf-8") if memory_path.exists() else ""
    user_text = user_path.read_text(encoding="utf-8") if user_path.exists() else ""
    if len(memory_text) > 20_000:
        errors.append(f"MEMORY.md is {len(memory_text)} characters; exceeds 20000-character safety limit")
    marker_counts = {item["marker"]: len(re.findall(re.escape(f"<!-- openclaw-memory-promotion:{item['marker']} -->"), memory_text)) for item in manifest["candidates"]}
    if any(count > 1 for count in marker_counts.values()):
        errors.append("one or more promotion markers are duplicated")
    decision_map = {row.get("marker"): row for row in decisions.get("decisions", []) if isinstance(row, dict)}
    for candidate in manifest["candidates"]:
        marker = candidate["marker"]
        row = decision_map.get(marker, {})
        action = row.get("action")
        current = current_entry_for_marker(memory_text, marker)
        if action in {"keep", "rewrite"}:
            if current is None:
                errors.append(f"{action} marker missing from MEMORY.md: {marker}")
                continue
            if METRIC_RE.search(current):
                errors.append(f"visible score metadata remains for curated marker: {marker}")
            if BANNED_RE.search(current):
                errors.append(f"raw conversation metadata remains for curated marker: {marker}")
            claim = row.get("claim", "").strip()
            citation = row.get("source_citation", "").strip()
            if claim and claim not in current:
                errors.append(f"declared claim not found beside marker: {marker}")
            if citation and citation not in current:
                errors.append(f"source citation not found beside marker: {marker}")
        elif action == "remove":
            if candidate["raw"] in memory_text:
                errors.append(f"raw promoted entry still present after {action}: {marker}")
            if marker_counts.get(marker, 0) != 0:
                errors.append(f"promotion marker must be removed after {action}: {marker}")
    if BANNED_RE.search(user_text):
        errors.append("USER.md contains raw conversation metadata after curation")
    result = {
        "run_id": run_id,
        "valid": not errors,
        "errors": errors,
        "marker_counts": marker_counts,
        "after_fingerprints": {relative: file_fingerprint(workspace / relative) for relative in TRACKED},
        "validated_at": now_iso(),
    }
    write_json(run_dir / "validation.json", result)
    return result


def rollback(workspace: Path, run_id: str) -> dict[str, Any]:
    assert_lock(workspace, run_id)
    run_dir = state_paths(workspace)["runs"] / run_id
    manifest = read_json(run_dir / "manifest.json", None)
    if not manifest:
        raise CuratorError(f"missing manifest for run {run_id}")
    validation = read_json(run_dir / "validation.json", None)
    allowed: dict[str, set[str | None]] = {}
    for snapshot in manifest["snapshots"]:
        allowed[snapshot["path"]] = {snapshot.get("fingerprint", {}).get("sha256")}
    if validation:
        for relative, fingerprint in validation.get("after_fingerprints", {}).items():
            allowed.setdefault(relative, set()).add(fingerprint.get("sha256"))
    conflicts = []
    for relative in TRACKED:
        current = file_fingerprint(workspace / relative).get("sha256")
        if current not in allowed.get(relative, {None}):
            conflicts.append(relative)
    if conflicts:
        raise CuratorError(
            "rollback conflict; files changed outside the recorded transaction: "
            f"{', '.join(conflicts)}. Restore them by hand from "
            f"{(run_dir / 'backup').relative_to(workspace)} after reviewing the differences."
        )
    backup_dir = run_dir / "backup"
    for snapshot in manifest["snapshots"]:
        relative = snapshot["path"]
        destination = workspace / relative
        backup = backup_dir / relative
        if snapshot["existed"]:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, destination)
        else:
            destination.unlink(missing_ok=True)
    write_json(run_dir / "status.json", {"run_id": run_id, "status": "rolled_back", "updated_at": now_iso()})
    release_lock(workspace, run_id)
    return {"run_id": run_id, "status": "rolled_back"}


def commit(workspace: Path, run_id: str) -> dict[str, Any]:
    validation = validate(workspace, run_id)
    if not validation["valid"]:
        raise CuratorError("validation failed; run rollback before retrying")
    run_dir, manifest, decisions = load_run(workspace, run_id)
    recorded_validation = read_json(run_dir / "validation.json", {})
    for relative, expected in recorded_validation.get("after_fingerprints", {}).items():
        if file_fingerprint(workspace / relative) != expected:
            raise CuratorError(f"commit conflict; {relative} changed after validation")
    ledger = load_ledger(workspace)
    for row in decisions["decisions"]:
        ledger["entries"][row["marker"]] = {
            "action": row["action"],
            "reason": row["reason"],
            "claim": row.get("claim"),
            "source_citation": row.get("source_citation"),
            "run_id": run_id,
            "curated_at": now_iso(),
            "source_body_sha256": next(
                (candidate["raw_sha256"] for candidate in manifest["candidates"] if candidate["marker"] == row["marker"]),
                None,
            ),
        }
    ledger["updated_at"] = now_iso()
    write_json(state_paths(workspace)["ledger"], ledger)
    write_json(run_dir / "status.json", {"run_id": run_id, "status": "committed", "updated_at": now_iso(), "candidate_count": manifest["candidate_count"]})
    release_lock(workspace, run_id)
    return {"run_id": run_id, "status": "committed", "candidate_count": manifest["candidate_count"]}


def status(workspace: Path) -> dict[str, Any]:
    paths = state_paths(workspace)
    ledger = load_ledger(workspace)
    return {
        "active_run": read_json(paths["lock"], None),
        "processed_count": len(ledger.get("entries", {})),
        "unprocessed_count": len(discover(workspace, False)),
        "state_root": str(paths["root"]),
    }


def archive_reports(workspace: Path, requested_archive_id: str | None = None) -> dict[str, Any]:
    source_root = workspace / "memory" / "dreaming"
    files = sorted(path for path in source_root.rglob("*") if path.is_file()) if source_root.exists() else []
    if not files:
        return {"archive_id": None, "archived_count": 0, "archive_root": None, "files": []}
    archive_id = requested_archive_id or run_id_now()
    archive_root = workspace / "state" / "memory-curator" / "dreaming-reports-archive" / archive_id
    if archive_root.exists():
        raise CuratorError(f"archive directory already exists: {archive_root}")
    manifest_files = []
    for source in files:
        relative = source.relative_to(source_root)
        destination = archive_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        fingerprint = file_fingerprint(source)
        shutil.move(str(source), str(destination))
        manifest_files.append({"path": str(relative), "fingerprint": fingerprint})
    for directory in sorted((path for path in source_root.rglob("*") if path.is_dir()), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    try:
        source_root.rmdir()
    except OSError:
        pass
    result = {
        "archive_id": archive_id,
        "archived_at": now_iso(),
        "archived_count": len(manifest_files),
        "source_root": str(source_root),
        "archive_root": str(archive_root),
        "files": manifest_files,
    }
    write_json(archive_root / "archive.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=str(Path(__file__).resolve().parents[1]))
    sub = parser.add_subparsers(dest="command", required=True)
    discover_parser = sub.add_parser("discover")
    discover_parser.add_argument("--all", action="store_true")
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--all", action="store_true")
    prepare_parser.add_argument("--run-id")
    archive_parser = sub.add_parser("archive-reports")
    archive_parser.add_argument("--archive-id")
    for name in ("apply", "validate", "commit", "rollback"):
        command_parser = sub.add_parser(name)
        command_parser.add_argument("--run-id", required=True)
    sub.add_parser("status")
    args = parser.parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    try:
        if args.command == "discover":
            result = {"candidates": discover(workspace, args.all)}
        elif args.command == "prepare":
            result = prepare(workspace, args.all, args.run_id)
        elif args.command == "archive-reports":
            result = archive_reports(workspace, args.archive_id)
        elif args.command == "apply":
            result = apply_decisions(workspace, args.run_id)
        elif args.command == "validate":
            result = validate(workspace, args.run_id)
        elif args.command == "commit":
            result = commit(workspace, args.run_id)
        elif args.command == "rollback":
            result = rollback(workspace, args.run_id)
        else:
            result = status(workspace)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if not isinstance(result, dict) or result.get("valid", True) else 2
    except (CuratorError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
