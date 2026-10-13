import copy
import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from io import StringIO
from pathlib import Path

from scripts.build_crystal_evidence import build, validate_structure
from scripts.export_release import import_alloys


def fixture():
    return {
        "sources": [
            {
                "id": "test",
                "title": "Synthetic schema fixture",
                "url": "https://example.org/test",
                "version": "1",
                "retrieved_at": "2026-10-12",
                "license_note": "Test only, not scientific evidence",
            }
        ],
        "structures": [
            {
                "id": "fixture",
                "name": "Test deuterated structure",
                "formula": "[2H]2O",
                "phase": "fixture only",
                "crystal_system": "cubic",
                "space_group_number": 225,
                "space_group_symbol": "F m -3 m",
                "cell_convention": "source fixture",
                "site_convention": "asymmetric_unit",
                "cell_formula_units": 1,
                "temperature_k": None,
                "pressure_pa": "0",
                "lattice_parameters": {
                    key: {"value": "3.001", "uncertainty": "0.002", "unit": "angstrom"}
                    for key in ("a", "b", "c")
                },
                "sites": [
                    {
                        "label": "D1",
                        "element": "H",
                        "isotope_mass_number": 2,
                        "x": "-0.125",
                        "y": "0.25",
                        "z": "0.5",
                        "occupancy": "0.5",
                        "multiplicity": None,
                        "wyckoff": None,
                        "coordinate_uncertainties": {"x": "0.001"},
                    }
                ],
                "source_id": "test",
                "source_locator": "fixture",
                "method": None,
                "provenance_class": "curated",
                "kind": "evaluated_reference",
                "review_status": "pending_human_review",
                "note": "Synthetic schema test",
            }
        ],
        "gaps": [],
    }


class CrystalEvidenceTests(unittest.TestCase):
    def create(self, directory, document):
        sources = directory / "sources"
        sources.mkdir(exist_ok=True)
        (sources / "fixture.json").write_text(json.dumps(document), encoding="utf-8")
        output = directory / "crystals.db"
        with redirect_stdout(StringIO()):
            build(output, sources)
        return output

    def test_exact_metrics_isotopes_and_incomplete_context_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            output = self.create(directory, fixture())
            with closing(sqlite3.connect(output)) as db:
                self.assertEqual(
                    (3001, 1000, 1, 500),
                    db.execute(
                        "SELECT value_numerator,value_denominator,uncertainty_numerator,uncertainty_denominator FROM unverified_crystal_lattice_parameter WHERE parameter='a'"
                    ).fetchone(),
                )
                self.assertEqual(
                    (None, None, "asymmetric_unit", "[2H]2O"),
                    db.execute(
                        "SELECT temperature_k_numerator,method,site_convention,formula FROM unverified_crystal_structure"
                    ).fetchone(),
                )
                isotope, x, denominator, raw = db.execute(
                    "SELECT isotope_mass_number,x_numerator,x_denominator,input_json FROM unverified_crystal_site"
                ).fetchone()
                self.assertEqual((2, -1, 8), (isotope, x, denominator))
                self.assertEqual(
                    "0.001", json.loads(raw)["coordinate_uncertainties"]["x"]
                )

    def test_rejects_promotion_nonphysical_geometry_and_false_measurements(self):
        original = fixture()["structures"][0]
        for mutation in (
            {"review_status": "reviewed"},
            {"kind": "computed", "provenance_class": "measured"},
            {"space_group_number": 231},
            {"crystal_system": "hexagonal"},
            {"temperature_k": "0"},
            {"cell_formula_units": 1.5},
            {"site_convention": None},
            {"pressure_pa": "-1"},
        ):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_structure(dict(original, **mutation))
        changed = copy.deepcopy(original)
        changed["lattice_parameters"].update(
            {key: {"value": "130", "unit": "deg"} for key in ("alpha", "beta", "gamma")}
        )
        with self.assertRaisesRegex(ValueError, "geometry"):
            validate_structure(changed)
        changed = copy.deepcopy(original)
        changed["sites"][0]["occupancy"] = "1.01"
        with self.assertRaisesRegex(ValueError, "occupancy"):
            validate_structure(changed)

    def test_reproducible_build_and_release_namespace(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            output = self.create(directory, fixture())
            original = output.read_bytes()
            self.create(directory, fixture())
            self.assertEqual(original, output.read_bytes())
            target = directory / "combined.db"
            import_alloys(target, output, prefix="")
            with closing(sqlite3.connect(target)) as db:
                self.assertEqual([], db.execute("PRAGMA foreign_key_check").fetchall())
                self.assertEqual(
                    "pending_human_review",
                    db.execute(
                        "SELECT review_status FROM unverified_crystal_structure"
                    ).fetchone()[0],
                )
                self.assertTrue(
                    db.execute(
                        "SELECT 1 FROM sqlite_schema WHERE name='unverified_crystal_formula'"
                    ).fetchone()
                )

    def test_changed_raw_cif_or_bad_source_cannot_replace_artifact(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            raw = directory / "native.cif"
            raw.write_bytes(b"original source fixture")
            document = fixture()
            document["sources"][0].update(
                raw_file=str(raw), sha256=hashlib.sha256(raw.read_bytes()).hexdigest()
            )
            output = self.create(directory, document)
            original = output.read_bytes()
            raw.write_bytes(b"changed source")
            with self.assertRaisesRegex(ValueError, "digest"):
                self.create(directory, document)
            self.assertEqual(original, output.read_bytes())
            bad = fixture()
            bad["structures"][0]["source_id"] = "missing"
            with self.assertRaises(sqlite3.IntegrityError):
                self.create(directory, bad)
            self.assertEqual(original, output.read_bytes())


if __name__ == "__main__":
    unittest.main()
