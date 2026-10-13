import json
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from scripts.audit_data_types import audit, inventory


@contextmanager
def connection(path):
    db = sqlite3.connect(path)
    try:
        with db:
            yield db
    finally:
        db.close()


class DataTypeAuditTests(unittest.TestCase):
    def test_empty_supported_and_missing_types(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with connection(root / "universe.db") as db:
                db.execute("CREATE TABLE spectrum(spectrum_id TEXT)")
            report = audit(root)
            self.assertEqual(
                report["families"]["spectra"]["databases"]["universe.db"]["status"],
                "empty",
            )
            self.assertEqual(
                report["families"]["phonons_diffraction"]["status"], "missing"
            )
            self.assertIn(
                "database_missing", report["inventories"]["isotopes.db"]["diagnostics"]
            )

    def test_reviewed_and_staged_counts_without_snapshot_duplication(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with connection(root / "universe.db") as db:
                db.execute("CREATE TABLE observation(property_id TEXT)")
                db.execute("INSERT INTO observation VALUES ('property:density')")
            with connection(root / "elements.db") as db:
                db.execute("CREATE TABLE unverified_element_observation(property TEXT)")
                db.executemany(
                    "INSERT INTO unverified_element_observation VALUES (?)",
                    [("density",), ("density",), ("unmapped_new_property",)],
                )
            with connection(root / "universe-unverified.db") as db:
                db.execute("CREATE TABLE observation(property_id TEXT)")
                db.execute("INSERT INTO observation VALUES ('property:density')")
            report = audit(root)
            family = report["families"]["thermodynamics"]
            self.assertEqual(
                (family["reviewed_records"], family["staged_records"]), (1, 2)
            )
            self.assertEqual(
                report["inventories"]["elements.db"]["unmapped_properties"],
                ["unmapped_new_property"],
            )
            json.dumps(report)

    def test_staged_only_and_unknown_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with connection(root / "isotopes.db") as db:
                db.execute("CREATE TABLE unverified_isotope_observation(property TEXT)")
                db.execute(
                    "INSERT INTO unverified_isotope_observation VALUES ('half_life')"
                )
            self.assertEqual(
                audit(root)["families"]["nuclear_lifetime_spin"]["status"],
                "staged_only",
            )
            path = root / "odd.db"
            with connection(path) as db:
                db.execute("CREATE TABLE observation(unexpected TEXT)")
            self.assertEqual(
                inventory(path)["diagnostics"], ["missing_property_column:observation"]
            )

    def test_read_only_inventory(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "empty.db"
            sqlite3.connect(path).close()
            before = path.read_bytes()
            self.assertEqual(inventory(path)["diagnostics"], ["empty_schema"])
            self.assertEqual(path.read_bytes(), before)

    def test_new_source_families_are_staged_not_reviewed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, table in (
                ("spectra.db", "unverified_spectral_line"),
                ("molecules.db", "unverified_molecular_molecule"),
            ):
                with connection(root / name) as db:
                    db.execute(f"CREATE TABLE {table}(id TEXT)")
                    db.execute(f"INSERT INTO {table} VALUES ('source-record')")
            with connection(root / "atomic.db") as db:
                db.execute("CREATE TABLE unverified_atomic_observation(property TEXT)")
                db.execute(
                    "INSERT INTO unverified_atomic_observation VALUES ('ionization_energy')"
                )
            report = audit(root)
            for family in ("spectra", "molecular_graphs", "atomic_electronic"):
                self.assertEqual(report["families"][family]["reviewed_records"], 0)
                self.assertEqual(report["families"][family]["staged_records"], 1)
                self.assertEqual(report["families"][family]["status"], "staged_only")


if __name__ == "__main__":
    unittest.main()
