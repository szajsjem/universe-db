"""Fictional numerical fixtures, never scientific training evidence."""

import copy
import unittest
from fractions import Fraction

from scripts.alloy_mechanical_properties import (
    fit_mechanical_properties,
    mechanical_properties,
)
from scripts.calculate_stats import calculate_stats
from scripts.fit_alloy_properties import FitError

STATE = {
    "temperature_k": "300",
    "phase": "solid",
    "state": "fictional common fixture state",
}


def records(prop, unit, first, second):
    return [
        {
            "id": f"fixture-{prop}-{i}",
            "property": prop,
            "unit": unit,
            "value": value,
            "composition_mass_fractions": composition,
            "conditions": STATE,
            "source": "fictional test fixture, not scientific evidence",
            "provenance_class": "fictional",
            "review_status": "unverified",
        }
        for i, (composition, value) in enumerate(
            [({"Fe": "3/4", "Ni": "1/4"}, first), ({"Fe": "1/4", "Ni": "3/4"}, second)]
        )
    ]


class MechanicalTests(unittest.TestCase):
    def fit(self, rows):
        return fit_mechanical_properties(
            rows, allow_unverified=True, allow_synthetic=True
        )

    def test_independent_strength_and_proxy(self):
        profile = self.fit(
            records("tensile_strength", "Pa", "100", "200")
            + records("elongation_at_break", "1", "1/20", "3/20")
        )
        result = calculate_stats(
            profile,
            {
                "kind": "alloy",
                "composition_mass_fractions": {"Fe": "1/2", "Ni": "1/2"},
                "conditions": STATE,
            },
        )
        strength = result["values"]["tensile_strength"]
        self.assertEqual(
            Fraction(150), Fraction(strength["numerator"], strength["denominator"])
        )
        brittle = result["values"]["brittleness_index"]
        self.assertEqual(
            Fraction(1, 3), Fraction(brittle["numerator"], brittle["denominator"])
        )
        self.assertEqual("fictional", brittle["provenance_class"])
        self.assertIn("compressive_strength", result["unavailable"])
        self.assertIn("fracture_toughness", result["unavailable"])

    def test_state_domain_and_evidence_gates(self):
        rows = records("tensile_strength", "Pa", "100", "200")
        with self.assertRaises(FitError):
            fit_mechanical_properties(rows)
        profile = self.fit(rows)
        result = mechanical_properties(profile, {"Fe": "1"}, conditions=STATE)
        self.assertIn("tensile_strength", result["unavailable"])
        with self.assertRaises(FitError):
            mechanical_properties(
                profile, {"Fe": "1"}, conditions=dict(STATE, state="different")
            )
        changed = copy.deepcopy(rows)
        changed[0]["unit"] = "MPa"
        with self.assertRaises(FitError):
            self.fit(changed)

    def test_nonphysical_negative_prediction_abstains(self):
        profile = self.fit(records("tensile_strength", "Pa", "100", "200"))
        for coefficient in profile["models"]["tensile_strength"]["coefficients"]:
            coefficient["numerator"] = -1
            coefficient["denominator"] = 1
        result = mechanical_properties(
            profile, {"Fe": "1/2", "Ni": "1/2"}, conditions=STATE
        )
        self.assertIn("nonphysical", result["unavailable"]["tensile_strength"])

    def test_mixed_target_states_and_duplicate_ids_rejected(self):
        rows = records("tensile_strength", "Pa", "100", "200")
        with self.assertRaises(FitError):
            self.fit(rows + rows)
        rows += records("compressive_strength", "Pa", "110", "210")
        rows[-1] = dict(rows[-1], conditions=dict(STATE, temperature_k="400"))
        with self.assertRaises(FitError):
            self.fit(rows)
