#!/usr/bin/env python3
"""Extract openclaw session transcripts for a given date.

Uses two data sources:
1. Active sessions via `openclaw sessions --json` (current sessions in the index)
2. Archived JSONL files (*.jsonl.reset.*) for sessions cleared via /new or /reset

Usage:
    uv run skills/digest-day/scripts/extract_sessions.py [--date YYYY-MM-DD] [--days N] [--agent main]

With --days N, outputs sessions for N consecutive days ending on --date (default today).
Each day is a separate entry in the output JSON array.
"""

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def get_local_tz():
    """Get the local timezone offset."""
    now = datetime.now()
    utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
    offset = now - utc_now
    total_seconds = round(offset.total_seconds() / 60) * 60
    return timezone(timedelta(seconds=total_seconds))


def date_range_ms(target_date, local_tz):
    """Return (start_ms, end_ms) for a calendar date in local time."""
    day_start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=local_tz)
    day_end = day_start + timedelta(days=1)
    return int(day_start.timestamp() * 1000), int(day_end.timestamp() * 1000)


def run_openclaw_sessions(agent: str) -> dict:
    """Run `openclaw sessions --json` and return parsed output."""
    cmd = ["openclaw", "sessions", "--json"]
    if agent != "main":
        cmd += ["--agent", agent]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"openclaw sessions failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def extract_messages(session_file: str, max_messages: int = 800) -> list:
    """Extract user and assistant text messages from a JSONL transcript."""
    path = Path(session_file)
    if not path.exists():
        return []

    messages = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if event.get("type") != "message":
                continue

            msg = event.get("message", {})
            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue

            content = msg.get("content", [])
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                text = "\n".join(text_parts)
            else:
                continue

            if not text.strip():
                continue

            messages.append({
                "role": role,
                "text": text.strip(),
                "ts": event.get("timestamp", ""),
            })

    # Cap only truly massive sessions. 800 msgs ≈ ~80k tokens, well within Sonnet's 200k context.
    if len(messages) > max_messages:
        messages = messages[:100] + messages[-(max_messages - 100):]

    return messages


def read_jsonl_header(path: Path) -> dict | None:
    """Read the first line of a JSONL file (session header event)."""
    try:
        with open(path) as f:
            first_line = f.readline().strip()
            if first_line:
                return json.loads(first_line)
    except (json.JSONDecodeError, OSError):
        pass
    return None


def parse_reset_date(filename: str, local_tz) -> date | None:
    """Extract the reset timestamp from an archived session filename.
    
    Filename pattern: {id}.jsonl.reset.{ISO-ish timestamp}
    e.g. abc.jsonl.reset.2026-04-13T16-09-14.653Z
    """
    if '.reset.' not in filename:
        return None
    reset_part = filename.split('.reset.')[-1]
    # Remove trailing .jsonl if present
    reset_part = reset_part.replace('.jsonl', '')
    # Parse: 2026-04-13T16-09-14.653Z -> 2026-04-13T16:09:14+00:00
    parts = reset_part.rstrip('Z').split('T')
    if len(parts) != 2:
        return None
    time_part = parts[1].split('.')[0]  # drop milliseconds
    time_part = time_part.replace('-', ':')
    try:
        reset_ts = datetime.fromisoformat(f'{parts[0]}T{time_part}+00:00')
        return reset_ts.astimezone(local_tz).date()
    except ValueError:
        return None


def filter_messages_by_date(messages: list, target_date, local_tz) -> list:
    """Filter messages to only those whose timestamp falls on target_date in local time."""
    filtered = []
    for m in messages:
        ts_str = m.get('ts', '')
        if not ts_str:
            filtered.append(m)  # keep messages without timestamps (rare)
            continue
        try:
            msg_ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            if msg_ts.astimezone(local_tz).date() == target_date:
                filtered.append(m)
        except ValueError:
            filtered.append(m)  # keep unparseable timestamps
    return filtered


def main():
    parser = argparse.ArgumentParser(description="Extract openclaw sessions for a date")
    parser.add_argument("--date", type=str, default=None,
                        help="Target date (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--days", type=int, default=1,
                        help="Number of days to extract (ending on --date). Defaults to 1.")
    parser.add_argument("--agent", type=str, default="main",
                        help="Agent ID. Defaults to 'main'.")
    parser.add_argument("--min-messages", type=int, default=3,
                        help="Minimum user messages to include a session. Defaults to 3.")
    args = parser.parse_args()

    local_tz = get_local_tz()

    if args.date:
        end_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        end_date = datetime.now(local_tz).date()

    dates = [end_date - timedelta(days=i) for i in range(args.days - 1, -1, -1)]

    # Phase 1: Active sessions from CLI
    cli_output = run_openclaw_sessions(args.agent)
    sessions_dir = Path(cli_output["path"]).parent

    # Build a map of session ID -> actual JSONL path on disk.
    active_jsonl_map: dict[str, Path] = {}
    for p in sessions_dir.glob("*.jsonl"):
        if ".reset." in p.name or p.name.endswith(".lock"):
            continue
        stem = p.name.split(".jsonl")[0]
        sid = stem.split("-topic-")[0]
        active_jsonl_map[sid] = p

    def extract_day(target_date):
        """Extract all sessions for a single calendar date."""
        start_ms, end_ms = date_range_ms(target_date, local_tz)
        sessions_out = []
        seen_ids = set()

        for entry in cli_output.get("sessions", []):
            key = entry.get("key", "")
            if ":cron:" in key:
                continue
            # updatedAt reflects last activity, not session start.
            # A session started Mon but active Tue appears under Tue. This is intentional.
            updated_at = entry.get("updatedAt", 0)
            if not (start_ms <= updated_at < end_ms):
                continue
            session_id = entry.get("sessionId", "")
            jsonl_path = active_jsonl_map.get(session_id, sessions_dir / f"{session_id}.jsonl")
            messages = extract_messages(str(jsonl_path))
            user_msg_count = sum(1 for m in messages if m["role"] == "user")
            if user_msg_count < args.min_messages:
                continue
            if session_id:
                seen_ids.add(session_id)
            topic_id = None
            if ":topic:" in key:
                topic_id = key.split(":topic:")[-1]
            session_entry = {
                "sessionId": session_id,
                "key": key,
                "kind": entry.get("kind", "unknown"),
                "source": "active",
                "messageCount": len(messages),
                "userMessageCount": user_msg_count,
                "messages": messages,
            }
            if topic_id:
                session_entry["topicId"] = topic_id
            sessions_out.append(session_entry)

        for reset_file in sessions_dir.glob("*.jsonl.reset.*"):
            header = read_jsonl_header(reset_file)
            if header is None:
                continue
            session_ts_str = header.get("timestamp", "")
            if not session_ts_str:
                continue
            try:
                session_start = datetime.fromisoformat(session_ts_str.replace("Z", "+00:00"))
            except ValueError:
                continue

            start_date_local = session_start.astimezone(local_tz).date()
            reset_date_local = parse_reset_date(reset_file.name, local_tz)

            # Include session if target_date falls between session start and reset date.
            # This catches multi-day sessions that span the target date.
            if reset_date_local:
                if not (start_date_local <= target_date <= reset_date_local):
                    continue
            else:
                # Fallback: no parseable reset date, use original start-date-only check
                if start_date_local != target_date:
                    continue

            session_id = header.get("id", "")
            if session_id in seen_ids:
                continue
            messages = extract_messages(str(reset_file))

            # For multi-day sessions, filter to only messages from the target date.
            if start_date_local != target_date or (reset_date_local and reset_date_local != start_date_local):
                messages = filter_messages_by_date(messages, target_date, local_tz)

            user_msg_count = sum(1 for m in messages if m["role"] == "user")
            if user_msg_count < args.min_messages:
                continue
            if session_id:
                seen_ids.add(session_id)
            kind = "unknown"
            for m in messages:
                if "group" in m.get("text", "").lower()[:100]:
                    kind = "group"
                    break
                if m["role"] == "user":
                    kind = "direct"
                    break
            topic_id = None
            fname = reset_file.name
            if "-topic-" in fname:
                topic_part = fname.split("-topic-")[1]
                topic_id = topic_part.split(".")[0]
            session_entry = {
                "sessionId": session_id,
                "key": "",
                "kind": kind,
                "source": "archived",
                "sessionStart": session_start.isoformat(),
                "messageCount": len(messages),
                "userMessageCount": user_msg_count,
                "messages": messages,
            }
            if topic_id:
                session_entry["topicId"] = topic_id
            sessions_out.append(session_entry)

        return {
            "date": target_date.isoformat(),
            "sessionCount": len(sessions_out),
            "sessions": sessions_out,
        }

    if args.days == 1:
        output = extract_day(dates[0])
        json.dump(output, sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        all_days = [extract_day(d) for d in dates]
        json.dump(all_days, sys.stdout, indent=2, ensure_ascii=False)
        print()


if __name__ == "__main__":
    main()
