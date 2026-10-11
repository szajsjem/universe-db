from __future__ import annotations

import copy
import json
import unittest
from fractions import Fraction

from scripts.calculate_properties import (
    CalculationError,
    DeterministicPropertyCalculator,
)
from scripts.mixture_properties import structure_from_prototype


def rational(result):
    return Fraction(result["numerator"], result["denominator"])


class MixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.calculator = DeterministicPropertyCalculator.load()

    def setUp(self):
        self.conditions = {"temperature_k": "300"}
        self.components = []
        for formula, mass, density, cp, k, bulk, shear in [
            ("Fe", "50", "1000", "100", "10", "100", "40"),
            ("C", "10", "2000", "200", "20", "200", "80"),
        ]:
            stats = {}
            for name, value, unit in [
                ("density", density, "kg/m3"),
                ("specific_heat_capacity", cp, "J/(kg*K)"),
                ("thermal_conductivity", k, "W/(m*K)"),
                ("electrical_conductivity", k, "S/m"),
                ("bulk_modulus", bulk, "Pa"),
                ("shear_modulus", shear, "Pa"),
            ]:
                stats[name] = {
                    "value": value,
                    "unit": unit,
                    "phase": "solid",
                    "source": "synthetic test fixture",
                    "conditions": self.conditions.copy(),
                }
            self.components.append(
                {"formula": formula, "molar_mass_g_mol": mass, "stats": stats}
            )

    def calculate(self, counts=(1, 1), **options):
        return self.calculator.calculate_mixture(
            self.components, list(counts), **options
        )

    def test_mass_fractions_are_not_count_fractions(self):
        result = self.calculate()
        self.assertEqual(
            Fraction(1, 2),
            rational(result["component_fractions"][0]["number_fraction"]),
        )
        self.assertEqual(
            Fraction(5, 6), rational(result["component_fractions"][0]["mass_fraction"])
        )
        self.assertEqual(
            Fraction(3, 100),
            rational(result["properties"]["mean_component_molar_mass"]),
        )
        self.assertEqual({"C": 1, "Fe": 1}, result["element_counts"])
        self.assertFalse(result["models"])

    def test_density_uses_additive_volumes_not_linear_mass_average(self):
        result = self.calculate(models=["additive_volume"], conditions=self.conditions)
        self.assertEqual(Fraction(12000, 11), rational(result["models"]["density"]))
        self.assertEqual(Fraction(10, 11), rational(result["volume_fractions"][0]))

    def test_heat_capacity_is_mass_weighted(self):
        result = self.calculate(
            models=["ideal_heat_capacity"], conditions=self.conditions
        )
        self.assertEqual(
            Fraction(350, 3), rational(result["models"]["specific_heat_capacity"])
        )

    def test_conductivity_and_elastic_bounds(self):
        result = self.calculate(
            models=["thermal_bounds", "electrical_bounds", "elastic_bounds"],
            conditions=self.conditions,
        )
        for name in ["thermal_conductivity", "electrical_conductivity"]:
            self.assertEqual(
                Fraction(220, 21), rational(result["models"][name]["series"])
            )
            self.assertEqual(
                Fraction(120, 11), rational(result["models"][name]["parallel"])
            )
        for name in ["bulk_modulus", "shear_modulus", "youngs_modulus"]:
            self.assertLessEqual(
                rational(result["models"]["elastic_bounds"]["reuss"][name]),
                rational(result["models"]["elastic_bounds"]["voigt"][name]),
            )

    def test_scaling_counts_preserves_intensive_values(self):
        a = self.calculate(models=["additive_volume"], conditions=self.conditions)
        b = self.calculate(
            counts=(10, 10), models=["additive_volume"], conditions=self.conditions
        )
        self.assertEqual(a["models"], b["models"])
        self.assertEqual(
            rational(a["properties"]["batch_molar_mass"]) * 10,
            rational(b["properties"]["batch_molar_mass"]),
        )

    def test_molecules_and_ions_preserve_atom_counts_and_charge(self):
        result = self.calculator.calculate_mixture(
            [{"formula": "H2O"}, {"species_id": "chem:carbonate"}], [2, 1]
        )
        self.assertEqual({"C": 1, "H": 4, "O": 5}, result["element_counts"])
        self.assertEqual(-2, result["properties"]["net_charge_elementary"])
        self.assertEqual(52, result["properties"]["electron_count"])

    def test_invalid_counts_and_stats_fail(self):
        for counts in [(0, 0), (-1, 2), (True, 1), (1.5, 2), (1,)]:
            with self.subTest(counts=counts), self.assertRaises(CalculationError):
                self.calculate(counts=counts)
        self.components[0]["stats"]["density"]["unit"] = "g/cm3"
        with self.assertRaisesRegex(CalculationError, "kg/m3"):
            self.calculate(models=["additive_volume"], conditions=self.conditions)

    def test_conditions_cannot_be_silently_mixed(self):
        self.components[0]["stats"]["density"]["conditions"]["temperature_k"] = "400"
        with self.assertRaisesRegex(CalculationError, "conditions differ"):
            self.calculate(models=["additive_volume"], conditions=self.conditions)
        with self.assertRaisesRegex(CalculationError, "temperature_k"):
            self.calculate(models=["ideal_heat_capacity"])

    def test_zero_count_does_not_require_stats(self):
        self.components[1] = {"formula": "invalid ignored formula"}
        result = self.calculate(
            counts=(1, 0), models=["additive_volume"], conditions=self.conditions
        )
        self.assertEqual(Fraction(1000), rational(result["models"]["density"]))

    def test_ceramic_cell_density_and_composition_guard(self):
        structure = {
            "lattice_angstrom": {
                "a": "4",
                "b": "4",
                "c": "4",
                "alpha": "90",
                "beta": "90",
                "gamma": "90",
            },
            "cell_counts": [4],
            "phase": "synthetic rocksalt test cell",
        }
        result = self.calculator.calculate_mixture(
            [{"formula": "NaCl", "molar_mass_g_mol": "58.44"}], [1], structure=structure
        )
        density = float(result["models"]["crystal_density"]["value"])
        self.assertAlmostEqual(density, 6065.1186, places=3)
        structure["cell_counts"] = [2, 1]
        with self.assertRaisesRegex(CalculationError, "match"):
            self.calculate(structure=structure)
        structure["cell_counts"] = [1, 1]
        structure["lattice_angstrom"]["gamma"] = "179"
        structure["lattice_angstrom"]["alpha"] = "1"
        structure["lattice_angstrom"]["beta"] = "1"
        with self.assertRaisesRegex(CalculationError, "geometry"):
            self.calculate(structure=structure)

    def test_repeatability_and_no_input_mutation(self):
        before = copy.deepcopy(self.components)
        first = json.dumps(self.calculate(), sort_keys=True)
        second = json.dumps(self.calculate(), sort_keys=True)
        self.assertEqual(first, second)
        self.assertEqual(before, self.components)

    def test_prototype_conventional_cells_and_ceramic_roles(self):
        bcc = structure_from_prototype("bcc", "3")
        self.assertEqual([2], bcc["cell_counts"])
        self.assertEqual(2, len(bcc["sites"]))
        fcc = structure_from_prototype("fcc", "4")
        self.assertEqual([4], fcc["cell_counts"])
        rocksalt = structure_from_prototype("rocksalt", "5")
        result = self.calculator.calculate_mixture(
            [{"formula": "Mg"}, {"formula": "O"}], [1, 1], structure=rocksalt
        )
        self.assertEqual([4, 4], result["models"]["crystal_density"]["cell_counts"])
        self.assertEqual("225", str(rocksalt["space_group_number"]))
        with self.assertRaisesRegex(CalculationError, "one integer"):
            self.calculate(structure=bcc)

    def test_fraction_inputs_return_json_serializable_results(self):
        self.components[0]["molar_mass_g_mol"] = Fraction(50)
        json.dumps(self.calculate())

    def test_crystal_site_counts_and_porosity_are_not_ignored(self):
        cell = structure_from_prototype("bcc", "3")
        cell["porosity_fraction"] = "0.2"
        result = self.calculator.calculate_mixture(
            [{"formula": "Fe"}], [1], structure=cell
        )
        solid = Fraction(result["models"]["crystal_density"]["value"])
        self.assertEqual(
            solid * Fraction(4, 5), rational(result["models"]["porous_bulk_density"])
        )
        cell["sites"][1] = cell["sites"][0]
        with self.assertRaisesRegex(CalculationError, "occupied"):
            self.calculator.calculate_mixture([{"formula": "Fe"}], [1], structure=cell)


if __name__ == "__main__":
    unittest.main()
