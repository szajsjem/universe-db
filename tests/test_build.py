from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from scripts.build_db import build
from scripts.validate_db import validate


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BuildTest(unittest.TestCase):
    def test_build_is_byte_for_byte_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.db"
            second = Path(directory) / "second.db"
            build(first)
            build(second)
            self.assertEqual(digest(first), digest(second))

    def test_built_artifact_is_current_and_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            rebuilt = Path(directory) / "rebuilt.db"
            build(rebuilt)
            self.assertEqual(digest(ROOT / "universe.db"), digest(rebuilt))
            self.assertEqual([], validate(ROOT / "universe.db"))

    def test_foreign_keys_are_clean(self) -> None:
        with sqlite3.connect(ROOT / "universe.db") as connection:
            self.assertEqual([], connection.execute("PRAGMA foreign_key_check").fetchall())


if __name__ == "__main__":
    unittest.main()
