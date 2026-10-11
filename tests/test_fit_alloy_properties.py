from __future__ import annotations

import copy
import json
import sqlite3
import unittest
from fractions import Fraction

from scripts.fit_alloy_properties import (
    FitError,
    audit_database_evidence,
    exact_alloy_composition,
    fit_alloy_approximation,
    predict_alloy,
    predict_integer_mixture,
)

STATE = {
    "temperature_k": "300",
    "phase": "solid",
    "state": "synthetic common test state",
}


def record(identifier, composition, value):
    return {
        "id": identifier,
        "composition_mass_fractions": composition,
        "value": value,
        "property": "density",
        "unit": "kg/m3",
        "conditions": STATE.copy(),
        "source": "synthetic unit-test data, not scientific measurements",
        "provenance_class": "fictional",
        "review_status": "reviewed",
    }


def value(result):
    return Fraction(result["numerator"], result["denominator"])


class ApproximationTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            record("pure-fe", {"Fe": "1"}, "100"),
            record("pure-c", {"C": "1"}, "200"),
        ]

    def fit(self, records=None, **options):
        return fit_alloy_approximation(
            records or self.records, allow_synthetic=True, **options
        )

    def test_linear_fit_and_quadratic_interaction(self):
        model = self.fit()
        prediction = predict_alloy(model, {"Fe": "0.25", "C": "0.75"}, conditions=STATE)
        self.assertEqual(Fraction(175), value(prediction))
        self.records.append(record("blend", {"Fe": "0.5", "C": "0.5"}, "170"))
        model = self.fit(degree=2)
        self.assertEqual(
            Fraction(190),
            value(predict_alloy(model, {"Fe": "0.25", "C": "0.75"}, conditions=STATE)),
        )
        self.assertEqual("fictional", model["provenance_class"])
        self.assertIsNone(prediction["prediction_uncertainty"])

    def test_reciprocal_density_fit(self):
        model = self.fit(transform="reciprocal")
        result = predict_alloy(model, {"Fe": "0.5", "C": "0.5"}, conditions=STATE)
        self.assertEqual(Fraction(400, 3), value(result))

    def test_integer_counts_use_mass_not_atomic_fraction(self):
        model = self.fit()
        result = predict_integer_mixture(
            model, [{"formula": "Fe"}, {"formula": "C"}], [1, 1], conditions=STATE
        )
        # PubChem snapshot in this repository reports Fe=55.84, C=12.011.
        expected = (100 * Fraction("55.84") + 200 * Fraction("12.011")) / (
            Fraction("55.84") + Fraction("12.011")
        )
        self.assertEqual(expected, value(result))

    def test_missing_pure_evidence_and_insufficient_design(self):
        blend = record("blend", {"Fe": "0.5", "C": "0.5"}, "150")
        with self.assertRaisesRegex(FitError, "missing pure-element"):
            self.fit([self.records[0], blend])
        with self.assertRaisesRegex(FitError, "insufficient"):
            self.fit(degree=2)
        duplicates = self.records + [record("pure-fe-2", {"Fe": "1"}, "100")]
        with self.assertRaisesRegex(FitError, "rank deficient"):
            self.fit(duplicates, degree=2)

    def test_state_source_and_review_gates(self):
        with self.assertRaisesRegex(FitError, "fictional"):
            fit_alloy_approximation(self.records)
        changed = copy.deepcopy(self.records)
        changed[0]["review_status"] = "pending_human_review"
        with self.assertRaisesRegex(FitError, "unverified"):
            self.fit(changed)
        changed = copy.deepcopy(self.records)
        changed[0]["conditions"]["temperature_k"] = "400"
        with self.assertRaisesRegex(FitError, "must match"):
            self.fit(changed)
        changed = copy.deepcopy(self.records)
        changed[0]["source"] = ""
        with self.assertRaisesRegex(FitError, "source"):
            self.fit(changed)

    def test_prediction_rejects_unknown_elements_and_states(self):
        model = self.fit()
        with self.assertRaisesRegex(FitError, "absent"):
            predict_alloy(model, {"Ni": "1"}, conditions=STATE)
        with self.assertRaisesRegex(FitError, "differ"):
            predict_alloy(
                model, {"Fe": "1"}, conditions=dict(STATE, temperature_k="400")
            )
        with self.assertRaisesRegex(FitError, "sum exactly"):
            predict_alloy(model, {"Fe": "0.99"}, conditions=STATE)

    def test_exact_nominal_recipe_only_not_midpoints(self):
        db = sqlite3.connect("alloys.db")
        db.row_factory = sqlite3.Row
        try:
            self.assertEqual(
                Fraction("0.751"),
                exact_alloy_composition(db, "au-cookson-18ct-sw")["Au"],
            )
            with self.assertRaisesRegex(FitError, "ranges"):
                exact_alloy_composition(db, "al-6061")
        finally:
            db.close()

    def test_database_audit_does_not_promote_commercial_purity(self):
        report = audit_database_evidence()
        self.assertEqual(118, report["summary"]["total_elements"])
        self.assertIn(
            "nickel-200", report["elements"]["Ni"]["commercial_grade_proxies"]
        )
        self.assertIn("density", report["elements"]["Ni"]["missing_properties"])
        self.assertEqual(0, report["summary"]["eligible_reviewed_alloy_point_records"])

    def test_model_is_serializable_deterministic_and_saturated_warning(self):
        original = copy.deepcopy(self.records)
        a = self.fit()
        b = self.fit()
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertEqual(original, self.records)
        self.assertEqual(0, a["diagnostics"]["residual_degrees_of_freedom"])
        self.assertEqual("not performed", a["diagnostics"]["independent_validation"])


if __name__ == "__main__":
    unittest.main()
