from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from scripts.build_db import build
from scripts.import_pubchem_periodic_table import (
    DEFAULT_OUTPUT as PERIODIC_SEED,
    DEFAULT_SOURCE as PERIODIC_SOURCE,
    render_seed,
)
from scripts.import_nist_isotopes import (
    DEFAULT_OUTPUT as ISOTOPE_SEED,
    DEFAULT_SOURCE as ISOTOPE_SOURCE,
    render_seed as render_isotope_seed,
)
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

    def test_periodic_table_has_all_118_elements(self) -> None:
        with sqlite3.connect(ROOT / "universe.db") as connection:
            rows = connection.execute(
                "SELECT atomic_number, symbol FROM element ORDER BY atomic_number"
            ).fetchall()
            self.assertEqual(list(range(1, 119)), [row[0] for row in rows])
            self.assertEqual(118, len({row[1] for row in rows}))

    def test_generated_periodic_seed_is_current(self) -> None:
        self.assertEqual(
            PERIODIC_SEED.read_text(encoding="utf-8"),
            render_seed(PERIODIC_SOURCE),
        )

    def test_common_isotopes_have_complete_natural_compositions(self) -> None:
        with sqlite3.connect(ROOT / "universe.db") as connection:
            nuclides, represented_elements = connection.execute(
                """
                SELECT count(*), count(DISTINCT n.element_id)
                FROM nuclide AS n
                JOIN nuclide_designation AS nd
                  ON nd.nuclide_id = n.entity_id
                WHERE nd.designation = 'natural_isotopic_composition'
                """
            ).fetchone()
            self.assertEqual(288, nuclides)
            self.assertEqual(84, represented_elements)

    def test_generated_isotope_seed_is_current(self) -> None:
        self.assertEqual(
            ISOTOPE_SEED.read_text(encoding="utf-8"),
            render_isotope_seed(ISOTOPE_SOURCE),
        )


if __name__ == "__main__":
    unittest.main()
