import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.export_release import (
    export_release,
    import_research,
    prefixed_schema,
    snapshot,
    verify_equivalent_core,
)


class ReleaseTests(unittest.TestCase):
    def test_core_equivalence_rejects_changed_rows_and_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / "a.db", Path(folder) / "b.db"
            for path in (a, b):
                with closing(sqlite3.connect(path)) as db:
                    db.execute("CREATE TABLE observation(id TEXT,value INTEGER)")
                    db.execute("INSERT INTO observation VALUES ('density',10)")
                    db.commit()
            verify_equivalent_core(a, b)
            with closing(sqlite3.connect(b)) as db:
                db.execute("UPDATE observation SET value=11")
                db.commit()
            with self.assertRaisesRegex(ValueError, "rows differ"):
                verify_equivalent_core(a, b)
            with closing(sqlite3.connect(b)) as db:
                db.execute("CREATE TABLE extra(value INTEGER)")
            with self.assertRaisesRegex(ValueError, "schema differs"):
                verify_equivalent_core(a, b)

    def test_snapshot_includes_committed_wal_only(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "live.db", Path(folder) / "snapshot.db"
            with closing(sqlite3.connect(source)) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("CREATE TABLE data(value INTEGER)")
                db.execute("INSERT INTO data VALUES (1)")
                db.commit()
                db.execute("INSERT INTO data VALUES (2)")
                snapshot(source, target)
                with closing(sqlite3.connect(target)) as copied:
                    self.assertEqual(
                        copied.execute("SELECT * FROM data").fetchall(), [(1,)]
                    )

    def test_incompatible_research_does_not_modify_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "wrong.db", Path(folder) / "core.db"
            with closing(sqlite3.connect(source)) as db:
                db.execute("CREATE TABLE database_metadata(key TEXT,value TEXT)")
                db.execute(
                    "INSERT INTO database_metadata VALUES ('unverified_base_sha256','wrong')"
                )
                db.commit()
            with closing(sqlite3.connect(target)) as db:
                db.execute("CREATE TABLE core(value INTEGER)")
            original = target.read_bytes()
            with self.assertRaisesRegex(ValueError, "base digest"):
                import_research(target, source, "expected")
            self.assertEqual(original, target.read_bytes())

    def test_namespace_preserves_equally_named_column(self):
        sql = (
            "CREATE TABLE note(note TEXT, source_id TEXT REFERENCES source(source_id))"
        )
        renamed = prefixed_schema(
            sql, {"note": "unverified_alloy_note", "source": "unverified_alloy_source"}
        )
        self.assertIn('CREATE TABLE "unverified_alloy_note"(note TEXT', renamed)
        self.assertIn('REFERENCES "unverified_alloy_source"', renamed)

    def test_release_cannot_overwrite_or_escape_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            (output / "existing").mkdir()
            with self.assertRaises(FileExistsError):
                export_release("existing", output, output / "missing.db", False)
            with self.assertRaises(ValueError):
                export_release("../escape", output, output / "missing.db", False)


if __name__ == "__main__":
    unittest.main()
