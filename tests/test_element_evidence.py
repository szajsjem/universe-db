import copy
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from fractions import Fraction
from io import StringIO
from pathlib import Path

from scripts.build_element_evidence import build, validate_observation
from scripts.export_release import import_alloys
from scripts.fit_alloy_properties import load_element_training_records


def fixture():
    return {
        "sources": [
            {
                "id": "fixture",
                "title": "Synthetic builder fixture",
                "url": "https://example.org/fixture",
                "version": "1",
                "retrieved_at": "2026-10-11",
                "license_note": "Unit test only",
            }
        ],
        "observations": [
            {
                "id": "fixture-cp",
                "element": "Al",
                "property": "molar_heat_capacity",
                "unit": "J/(mol*K)",
                "value": "25",
                "min": None,
                "max": None,
                "temperature_k": "300",
                "phase": "solid",
                "state": "synthetic test state",
                "pressure_pa": "100000",
                "method": "unit test only",
                "source_id": "fixture",
                "source_locator": "fixture",
                "provenance_class": "curated",
                "composition_basis": "elemental_reference",
                "note": "unit test only",
                "review_status": "pending_human_review",
                "expanded_relative_uncertainty_percent": "1",
            }
        ],
        "gaps": [],
    }


class ElementEvidenceTests(unittest.TestCase):
    def make(self, directory, document=None):
        sources = directory / "sources"
        sources.mkdir(exist_ok=True)
        (sources / "fixture.json").write_text(
            json.dumps(document or fixture()), encoding="utf-8"
        )
        target = directory / "elements.db"
        with redirect_stdout(StringIO()):
            build(target, sources)
        return target

    def test_builder_preserves_exact_numbers_and_complete_context(self):
        with tempfile.TemporaryDirectory() as folder:
            target = self.make(Path(folder))
            original = target.read_bytes()
            self.make(Path(folder))
            self.assertEqual(original, target.read_bytes())
            with closing(sqlite3.connect(target)) as db:
                row = db.execute(
                    "SELECT value_numerator,value_denominator,input_json FROM unverified_element_observation"
                ).fetchone()
                self.assertEqual((25, 1), row[:2])
                self.assertEqual(
                    "1", json.loads(row[2])["expanded_relative_uncertainty_percent"]
                )
                self.assertEqual([], db.execute("PRAGMA foreign_key_check").fetchall())

    def test_rejects_promotion_floats_and_invalid_values(self):
        original = fixture()["observations"][0]
        for mutation in (
            {"review_status": "reviewed"},
            {"value": 25.0},
            {"value": "-1"},
            {"temperature_k": "0"},
            {"element": "Unknown"},
            {"unit": "J/kg"},
            {"min": "26"},
            {"uncertainty_coverage_probability": "2"},
        ):
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValueError):
                    validate_observation(dict(original, **mutation))

    def test_invalid_source_does_not_replace_existing_artifact(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            target = self.make(directory)
            original = target.read_bytes()
            document = fixture()
            document["observations"][0]["source_id"] = "missing-source"
            with self.assertRaises(sqlite3.IntegrityError):
                self.make(directory, document)
            self.assertEqual(original, target.read_bytes())

    def test_release_import_keeps_research_namespace_and_source_context(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            source = self.make(directory)
            target = directory / "combined.db"
            import_alloys(target, source, prefix="")
            with closing(sqlite3.connect(target)) as db:
                self.assertEqual(
                    "pending_human_review",
                    db.execute(
                        "SELECT review_status FROM unverified_element_observation"
                    ).fetchone()[0],
                )
                self.assertEqual([], db.execute("PRAGMA foreign_key_check").fetchall())

    def test_loader_exact_cp_conversion_retains_pending_review_and_pressure(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.make(Path(folder))
            result = load_element_training_records(
                "specific_heat_capacity", evidence_database=source
            )
            row = result["records"][0]
            # PubChem snapshot: Al atomic mass 26.9815385 g/mol.
            with closing(sqlite3.connect("universe.db")) as db:
                n, d = db.execute(
                    "SELECT o.value_numerator,o.value_denominator FROM observation o JOIN element e ON o.subject_entity_id=e.entity_id WHERE e.symbol='Al' AND o.dataset_id='dataset:pubchem-periodic-table-2026-07-28'"
                ).fetchone()
            self.assertEqual(Fraction(25000) / Fraction(n, d), Fraction(row["value"]))
            self.assertEqual("100000", row["conditions"]["pressure_pa"])
            self.assertEqual("pending_human_review", row["review_status"])
            self.assertEqual(
                "1", row["source_record"]["expanded_relative_uncertainty_percent"]
            )

    def test_loader_excludes_missing_context_and_modeled_endpoints(self):
        for mutation in (
            {"temperature_k": None},
            {"phase": None},
            {"state": None},
            {"provenance_class": "modeled"},
            {"composition_basis": "finite_purity_specimen"},
            {"composition_basis": "unspecified"},
        ):
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as folder,
            ):
                document = copy.deepcopy(fixture())
                document["observations"][0].update(mutation)
                source = self.make(Path(folder), document)
                result = load_element_training_records(
                    "molar_heat_capacity", evidence_database=source
                )
                self.assertEqual([], result["records"])
                self.assertEqual(1, len(result["excluded"]))


if __name__ == "__main__":
    unittest.main()
