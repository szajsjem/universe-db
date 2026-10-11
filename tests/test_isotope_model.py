import copy
import json
import math
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from fractions import Fraction
from io import StringIO
from pathlib import Path

from scripts.build_isotope_evidence import build, ratio
from scripts.export_release import import_alloys
from scripts.fit_isotope_properties import (
    IsotopeFitError,
    basis,
    fit_isotope_model,
    least_squares,
    load_core_masses,
    local_correction,
    predict_isotope,
)


class IsotopeModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_core_masses()
        cls.model = fit_isotope_model(cls.records)

    def test_qr_recovers_known_coefficients_and_rejects_rank_deficiency(self):
        # Mathematical fixture only, never claimed as physical observations.
        coefficients = [15.8, 18.3, 0.7, 23.2, 12.0]
        design = [
            basis(z, 2 * z + excess) for z in range(8, 30) for excess in range(0, 8)
        ]
        targets = [
            math.fsum(a * b for a, b in zip(row, coefficients)) for row in design
        ]
        actual = least_squares(design, targets)
        for expected, result in zip(coefficients, actual):
            self.assertAlmostEqual(expected, result, places=9)
        with self.assertRaisesRegex(IsotopeFitError, "rank deficient"):
            least_squares([[1, 1], [2, 2]], [1, 2])

    def test_holdout_is_disjoint_and_local_model_improves_current_core(self):
        diagnostics = self.model["diagnostics"]
        held = set(diagnostics["coordinate_holdout"]["holdout_ids"])
        trained = set(diagnostics["coordinate_holdout"]["training_ids"])
        self.assertFalse(held & trained)
        self.assertEqual(len(self.model["training_records"]), len(held | trained))
        self.assertLess(
            diagnostics["coordinate_holdout"]["rmse_mev"],
            diagnostics["baseline_coordinate_holdout"]["rmse_mev"],
        )
        self.assertGreater(diagnostics["coordinate_holdout"]["rmse_mev"], 0)

    def test_known_reference_precedes_model(self):
        result = predict_isotope(self.model, 26, 56)
        original = next(r for r in self.records if (r["z"], r["a"]) == (26, 56))
        self.assertEqual("source_reference", result["status"])
        self.assertEqual(original["value"], result["atomic_mass_u"])
        self.assertNotIn("binding_energy_proxy_mev", result)

    def test_unknown_ground_state_outputs_only_supported_stats(self):
        result = predict_isotope(self.model, 26, 61)
        self.assertEqual("approximation", result["status"])
        self.assertEqual("modeled", result["provenance_class"])
        self.assertGreater(result["atomic_mass_u"], 60)
        self.assertLess(result["atomic_mass_u"], 62)
        self.assertIn("half_life", result["unavailable"])
        self.assertIn("existence_or_stability", result["unavailable"])
        self.assertEqual(
            "empirical known-isotope holdout error; not predictive uncertainty",
            result["error_context"]["kind"],
        )
        json.dumps(result)

    def test_extrapolation_light_nuclei_and_isomers_are_gated(self):
        with self.assertRaisesRegex(IsotopeFitError, "outside fitted domain"):
            predict_isotope(self.model, 26, 300)
        result = predict_isotope(self.model, 26, 300, allow_extrapolation=True)
        self.assertTrue(result["extrapolated"])
        self.assertIsNone(result["error_context"])
        self.assertFalse(result["local_correction_supported"])
        with self.assertRaisesRegex(IsotopeFitError, "unsupported"):
            predict_isotope(self.model, 3, 5)
        with self.assertRaisesRegex(IsotopeFitError, "excited"):
            predict_isotope(self.model, 26, 56, isomer=1)
        with self.assertRaisesRegex(IsotopeFitError, "integers"):
            predict_isotope(self.model, True, 56)

    def test_source_estimates_are_excluded_and_pending_requires_opt_in(self):
        records = copy.deepcopy(self.records)
        row = next(r for r in records if (r["z"], r["a"]) == (26, 56))
        row["estimated"] = True
        model = fit_isotope_model(records)
        self.assertNotIn("26:56", model["known_atomic_masses"])
        self.assertNotIn(row["id"], {r["id"] for r in model["training_records"]})
        for r in records:
            r["review_status"] = "pending_human_review"
        with self.assertRaises(IsotopeFitError):
            fit_isotope_model(records)
        model = fit_isotope_model(records, allow_unverified=True)
        self.assertEqual("pending_human_review", model["training_review_status"])

    def test_duplicate_masses_floats_and_missing_sources_rejected(self):
        with self.assertRaisesRegex(IsotopeFitError, "duplicate"):
            fit_isotope_model(self.records + [self.records[0]])
        records = copy.deepcopy(self.records)
        records[0]["value"] = 1.0078
        with self.assertRaisesRegex(IsotopeFitError, "exact"):
            fit_isotope_model(records)
        records[0]["value"] = "1.0078"
        records[0]["source"] = ""
        with self.assertRaisesRegex(IsotopeFitError, "citation"):
            fit_isotope_model(records)

    def test_local_kernel_never_self_corrects_or_uses_far_values(self):
        self.assertEqual(
            (0.0, []),
            local_correction(
                26,
                56,
                [
                    {"id": "self", "z": 26, "n": 30, "residual_mev": 100},
                    {"id": "far", "z": 90, "n": 140, "residual_mev": 100},
                ],
            ),
        )


class IsotopeEvidenceBuildTests(unittest.TestCase):
    def document(self):
        source = {
            "id": "fixture",
            "title": "Builder fixture only",
            "url": "https://example.org/fixture",
            "version": "1",
            "retrieved_at": "2026-10-11",
            "license_note": "Synthetic structural test, not evidence",
        }
        identity = {
            "z": 1,
            "a": 3,
            "isomer": 0,
            "label": "fixture",
            "source_id": "fixture",
            "source_locator": "fixture",
            "note": "fixture",
        }
        observation = {
            "id": "fixture-life",
            "z": 1,
            "a": 3,
            "isomer": 0,
            "property": "half_life",
            "unit": "s",
            "value": "1000000000000000000000000000000",
            "estimated": False,
            "provenance_class": "curated",
            "source_id": "fixture",
            "source_locator": "fixture",
            "method": "synthetic fixture only",
        }
        return {
            "sources": [source],
            "nuclides": [identity],
            "observations": [observation],
            "gaps": [],
        }

    def test_arbitrary_precision_lives_and_namespace_index_survive_export(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "isotopes.db"
            with redirect_stdout(StringIO()):
                build(path, [self.document()])
            original = path.read_bytes()
            with redirect_stdout(StringIO()):
                build(path, [self.document()])
            self.assertEqual(original, path.read_bytes())
            target = Path(folder) / "combined.db"
            import_alloys(target, path, prefix="")
            with closing(sqlite3.connect(target)) as db:
                n, d, status = db.execute(
                    "SELECT value_numerator,value_denominator,review_status FROM unverified_isotope_observation"
                ).fetchone()
                self.assertEqual(Fraction(10**30), Fraction(int(n), int(d)))
                self.assertEqual("pending_human_review", status)
                self.assertTrue(
                    db.execute(
                        "SELECT 1 FROM sqlite_schema WHERE name='unverified_isotope_coordinate_property'"
                    ).fetchone()
                )
                self.assertEqual([], db.execute("PRAGMA foreign_key_check").fetchall())

    def test_invalid_import_keeps_existing_artifact(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "isotopes.db"
            document = self.document()
            with redirect_stdout(StringIO()):
                build(path, [document])
            original = path.read_bytes()
            document["observations"][0]["value"] = "0"
            with self.assertRaisesRegex(ValueError, "positive"):
                build(path, [document])
            self.assertEqual(original, path.read_bytes())
        with self.assertRaises(ValueError):
            ratio(1.2)


if __name__ == "__main__":
    unittest.main()
