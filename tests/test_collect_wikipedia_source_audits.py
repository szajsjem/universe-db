import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from io import StringIO
from pathlib import Path

from scripts.collect_wikipedia_source_audits import collect

SPEC = (("report.json", "findings", "test_audit", "deterministic_triage"),)


class SourceAuditTests(unittest.TestCase):
    def setup_files(self, directory):
        base = directory / "base.db"
        with closing(sqlite3.connect(base)) as db:
            db.execute(
                "CREATE TABLE unverified_entity_candidate(candidate_id TEXT PRIMARY KEY,name TEXT)"
            )
            db.execute(
                "INSERT INTO unverified_entity_candidate VALUES ('unchanged','Original')"
            )
            db.commit()
        report = {
            "scope": "test fixture",
            "findings": [
                {
                    "candidate_id": "unchanged",
                    "name": "Original",
                    "revision_url": "https://en.wikipedia.org/w/index.php?oldid=1",
                    "proposed_action": "inspect",
                    "evidence_text": "fixture",
                    "review_method": "source_inspection",
                }
            ],
        }
        (directory / "report.json").write_text(json.dumps(report), encoding="utf-8")
        return base, directory / "output.db"

    def test_collector_preserves_original_and_records_methods_and_proposals(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            base, output = self.setup_files(directory)
            original = base.read_bytes()
            with redirect_stdout(StringIO()):
                summary = collect(base, directory, output, SPEC)
            self.assertEqual(original, base.read_bytes())
            self.assertEqual(1, summary["candidate_count"])
            with closing(sqlite3.connect(output)) as db:
                self.assertEqual(
                    [("unchanged", "Original")],
                    db.execute("SELECT * FROM unverified_entity_candidate").fetchall(),
                )
                method, raw = db.execute(
                    "SELECT review_method,input_json FROM unverified_wikipedia_source_audit_result"
                ).fetchone()
                self.assertEqual("source_inspection", method)
                self.assertEqual("inspect", json.loads(raw)["proposed_action"])
                self.assertEqual(
                    "pending_human_review",
                    db.execute(
                        "SELECT review_status FROM unverified_wikipedia_source_audit"
                    ).fetchone()[0],
                )
                self.assertEqual([], db.execute("PRAGMA foreign_key_check").fetchall())

    def test_incomplete_report_cannot_replace_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            base, output = self.setup_files(directory)
            output.write_bytes(b"preserve existing artifact")
            (directory / "report.json").write_text(
                json.dumps({"status": "scanning", "findings": []}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                collect(base, directory, output, SPEC)
            self.assertEqual(b"preserve existing artifact", output.read_bytes())

    def test_collector_rejects_source_overwrite_and_bad_records(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            base, output = self.setup_files(directory)
            original = base.read_bytes()
            with self.assertRaisesRegex(ValueError, "differ"):
                collect(base, directory, base, SPEC)
            (directory / "report.json").write_text(
                json.dumps({"findings": ["bad record"]}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "objects"):
                collect(base, directory, output, SPEC)
            self.assertEqual(original, base.read_bytes())
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
