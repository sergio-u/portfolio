#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("memory_curator.py")
SPEC = importlib.util.spec_from_file_location("memory_curator", MODULE_PATH)
assert SPEC and SPEC.loader
mc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mc)


class MemoryCuratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        (self.workspace / "memory").mkdir()
        (self.workspace / "memory" / "2026-08-01.md").write_text(
            "Header\nSergio explicitly prefers local-first tools.\nFooter\n", encoding="utf-8"
        )
        (self.workspace / "USER.md").write_text("# User\n", encoding="utf-8")
        (self.workspace / "MEMORY.md").write_text(
            "# Memory\n\n## Promoted From Short-Term Memory (2026-08-02)\n\n"
            "<!-- openclaw-memory-promotion:memory:memory/2026-08-01.md:2:2 -->\n"
            "- Sender (untrusted metadata): raw junk [score=0.900 recalls=5 avg=0.700 source=memory/2026-08-01.md:2-2]\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_discover_rehydrates_source(self) -> None:
        rows = mc.discover(self.workspace, include_all=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"]["start_line"], 2)
        self.assertIn("local-first", json.dumps(rows[0]["source_evidence"]))

    def test_promotion_section_stops_at_next_heading(self) -> None:
        memory_path = self.workspace / "MEMORY.md"
        memory_path.write_text(memory_path.read_text(encoding="utf-8") + "\n## Manual Section\n- Preserve me.\n", encoding="utf-8")
        rows = mc.discover(self.workspace, include_all=True)
        self.assertNotIn("Preserve me", rows[0]["raw"])

    def test_inline_marker_is_not_treated_as_boundary(self) -> None:
        text = "## Promoted From Short-Term Memory (2026-08-02)\n- prose <!-- openclaw-memory-promotion:memory:x:1:1 -->\n"
        self.assertEqual(mc.parse_promotions(text), [])

    def test_prepare_with_no_candidates_releases_lock(self) -> None:
        (self.workspace / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
        manifest = mc.prepare(self.workspace, include_all=True, requested_run_id="empty-run")
        self.assertEqual(manifest["candidate_count"], 0)
        self.assertIsNone(mc.status(self.workspace)["active_run"])

    def test_archive_reports_moves_files_out_of_memory_tree(self) -> None:
        report = self.workspace / "memory" / "dreaming" / "light" / "2026-08-02.md"
        report.parent.mkdir(parents=True)
        report.write_text("# Light Sleep\nnoise\n", encoding="utf-8")
        result = mc.archive_reports(self.workspace, requested_archive_id="archive-test")
        self.assertEqual(result["archived_count"], 1)
        self.assertFalse(report.exists())
        archived = self.workspace / "state" / "memory-curator" / "dreaming-reports-archive" / "archive-test" / "light" / "2026-08-02.md"
        self.assertTrue(archived.exists())
        self.assertEqual(mc.archive_reports(self.workspace)["archived_count"], 0)

    def test_transaction_rewrite_commit(self) -> None:
        manifest = mc.prepare(self.workspace, include_all=True, requested_run_id="test-run")
        marker = manifest["candidates"][0]["marker"]
        decisions = {
            "version": 1,
            "run_id": "test-run",
            "decisions": [
                {
                    "marker": marker,
                    "action": "rewrite",
                    "reason": "Explicit stable preference",
                    "claim": "Sergio explicitly prefers local-first tools.",
                    "source_citation": "memory/2026-08-01.md#L2-L2",
                    "destination": "MEMORY.md",
                }
            ],
        }
        run_dir = self.workspace / "state" / "memory-curator" / "runs" / "test-run"
        mc.write_json(run_dir / "decisions.json", decisions)
        applied = mc.apply_decisions(self.workspace, "test-run")
        self.assertEqual(applied["status"], "applied")
        result = mc.validate(self.workspace, "test-run")
        self.assertTrue(result["valid"], result["errors"])
        committed = mc.commit(self.workspace, "test-run")
        self.assertEqual(committed["status"], "committed")
        self.assertEqual(mc.status(self.workspace)["processed_count"], 1)

    def test_rewrite_moves_claim_into_curated_section(self) -> None:
        manifest = mc.prepare(self.workspace, include_all=True, requested_run_id="rewrite-run")
        marker = manifest["candidates"][0]["marker"]
        run_dir = self.workspace / "state" / "memory-curator" / "runs" / "rewrite-run"
        claim = "Sergio explicitly prefers local-first tools."
        mc.write_json(
            run_dir / "decisions.json",
            {
                "version": 1,
                "run_id": "rewrite-run",
                "decisions": [
                    {
                        "marker": marker,
                        "action": "rewrite",
                        "reason": "Canonical durable preference",
                        "claim": claim,
                        "source_citation": "memory/2026-08-01.md#L2-L2",
                        "destination": "MEMORY.md",
                    }
                ],
            },
        )
        mc.apply_decisions(self.workspace, "rewrite-run")
        text = (self.workspace / "MEMORY.md").read_text(encoding="utf-8")
        self.assertNotIn("## Promoted From Short-Term Memory", text)
        self.assertIn("# Memory\n\n## Curated Dreaming Memories", text)
        self.assertIn("## Curated Dreaming Memories", text)
        self.assertIn(marker, text)
        self.assertTrue(mc.validate(self.workspace, "rewrite-run")["valid"])
        mc.rollback(self.workspace, "rewrite-run")

    def test_validation_rejects_metadata(self) -> None:
        manifest = mc.prepare(self.workspace, include_all=True, requested_run_id="bad-run")
        marker = manifest["candidates"][0]["marker"]
        run_dir = self.workspace / "state" / "memory-curator" / "runs" / "bad-run"
        mc.write_json(
            run_dir / "decisions.json",
            {
                "version": 1,
                "run_id": "bad-run",
                "decisions": [
                    {
                        "marker": marker,
                        "action": "rewrite",
                        "reason": "Bad test",
                        "claim": "raw junk",
                        "source_citation": "memory/2026-08-01.md#L2-L2",
                    }
                ],
            },
        )
        result = mc.validate(self.workspace, "bad-run")
        self.assertFalse(result["valid"])
        self.assertTrue(any("metadata" in error for error in result["errors"]))
        mc.rollback(self.workspace, "bad-run")

    def test_rollback_refuses_untracked_concurrent_change(self) -> None:
        mc.prepare(self.workspace, include_all=True, requested_run_id="conflict-run")
        (self.workspace / "USER.md").write_text("# User\nConcurrent change\n", encoding="utf-8")
        with self.assertRaises(mc.CuratorError):
            mc.rollback(self.workspace, "conflict-run")
        # The concurrent edit must survive: there is no force escape hatch.
        self.assertIn(
            "Concurrent change",
            (self.workspace / "USER.md").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
