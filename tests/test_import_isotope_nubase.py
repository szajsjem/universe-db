"""Checks against published NUBASE points and source qualification semantics."""

import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from scripts.import_isotope_nubase import exact_seconds, load_records


class NubaseImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_records()
        cls.observations = {
            (row["z"], row["a"], row["isomer"], row["property"]): row
            for row in cls.records["observations"]
        }

    def test_full_source_and_distinct_states(self):
        self.assertEqual(len(self.records["nuclides"]), 5843)
        self.assertEqual(
            len({(r["z"], r["a"], r["isomer"]) for r in self.records["nuclides"]}), 5843
        )
        self.assertIn((43, 99, 0, "half_life"), self.observations)
        self.assertIn((43, 99, 1, "half_life"), self.observations)
        self.assertNotEqual(
            self.observations[(43, 99, 0, "half_life")]["value"],
            self.observations[(43, 99, 1, "half_life")]["value"],
        )

    def test_stable_does_not_mean_zero_lifetime(self):
        self.assertEqual(
            self.observations[(1, 1, 0, "stability")]["text_value"], "stable"
        )
        self.assertNotIn((1, 1, 0, "half_life"), self.observations)
        self.assertEqual(
            self.observations[(3, 3, 0, "stability")]["text_value"], "particle unstable"
        )

    def test_seconds_uncertainty_and_year_convention(self):
        neutron = self.observations[(0, 1, 0, "half_life")]
        self.assertEqual(Fraction(neutron["value"]), Fraction("609.8"))
        self.assertEqual(Fraction(neutron["uncertainty"]), Fraction("0.6"))
        tritium = self.observations[(1, 3, 0, "half_life")]
        self.assertEqual(Fraction(tritium["value"]), Fraction("12.32") * 31557600)
        self.assertIn("Julian year", tritium["method"])

    def test_tiny_lifetime_preserves_exact_nonzero(self):
        value = self.observations[(1, 4, 0, "half_life")]["value"]
        self.assertEqual(Fraction(value), Fraction(139, 10**24))
        self.assertEqual(Fraction(exact_seconds("1", "Yy")), 31557600 * 10**24)

    def test_state_mass_excess_and_excitation_preserve_source_precision(self):
        mass = self.observations[(43, 99, 1, "mass_excess")]
        self.assertEqual(mass["unit"], "keV")
        self.assertEqual(mass["value"], "-87185.2")
        self.assertEqual(mass["uncertainty"], "0.9")
        self.assertFalse(mass["estimated"])
        excitation = self.observations[(43, 99, 1, "excitation_energy")]
        self.assertEqual(excitation["value"], "142.6836")
        self.assertEqual(excitation["uncertainty"], "0.0011")
        self.assertNotIn((43, 99, 1, "atomic_mass"), self.observations)
        self.assertNotIn((43, 99, 0, "excitation_energy"), self.observations)

    def test_energy_systematics_and_withdrawn_assignments(self):
        mass = self.observations[(3, 3, 0, "mass_excess")]
        self.assertTrue(mass["estimated"])
        self.assertEqual(mass["value"], "28670")
        self.assertEqual(mass["uncertainty"], "2000")
        self.assertIn("28670#", mass["text_value"])
        self.assertNotIn((29, 76, 1, "mass_excess"), self.observations)
        self.assertNotIn((29, 76, 1, "excitation_energy"), self.observations)
        self.assertEqual(
            sum(
                r["property"] == "excitation_energy"
                for r in self.records["observations"]
            ),
            2269,
        )

    def test_bounds_and_spin_alternatives_remain_text(self):
        lifetime = self.observations[(18, 30, 0, "half_life")]
        self.assertIsNone(lifetime["value"])
        self.assertEqual(lifetime["value_kind"], "bound")
        self.assertIn("<10", lifetime["text_value"])
        spin = self.observations[(1, 5, 0, "spin_parity")]
        self.assertEqual(spin["text_value"], "(1/2+)")
        self.assertIsNone(spin["value"])
        self.assertEqual(
            self.observations[(1, 1, 0, "spin_parity")]["text_value"], "1/2+*"
        )

    def test_estimates_missing_and_withdrawn_are_not_measurements(self):
        self.assertTrue(
            any(
                row["estimated"] and "#" in row["text_value"]
                for row in self.records["observations"]
                if row["property"] == "half_life"
            )
        )
        self.assertTrue(
            any(
                row["reason"] == "not_reported" and row["property"] == "half_life"
                for row in self.records["gaps"]
            )
        )
        self.assertNotIn((29, 76, 1, "half_life"), self.observations)
        self.assertTrue(
            any(
                r["reason"] == "withdrawn_nonexistent_state_assignment"
                and r["z"] == 29
                and r["a"] == 76
                for r in self.records["gaps"]
            )
        )

    def test_unsupported_or_qualified_values_rejected(self):
        for value, unit in [("<10", "s"), ("1#", "s"), ("0", "s"), ("1", "fortnight")]:
            with self.assertRaises(ValueError):
                exact_seconds(value, unit)

    def test_duplicate_state_rejected(self):
        raw = self.observations[(0, 1, 0, "half_life")]["source_record"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.txt"
            path.write_text(raw + "\n" + raw + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_records(path)


if __name__ == "__main__":
    unittest.main()
