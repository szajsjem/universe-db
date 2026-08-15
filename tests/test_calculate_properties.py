from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from scripts.build_db import build
from scripts.calculate_properties import (
    CalculationError,
    DeterministicPropertyCalculator,
)


class DeterministicPropertyCalculatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.database = Path(cls.temporary_directory.name) / "test.db"
        build(cls.database)
        cls.calculator = DeterministicPropertyCalculator.load(cls.database)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary_directory.cleanup()

    def test_water_exact_composition_and_source_derived_mass(self) -> None:
        result = self.calculator.calculate_formula("H2O")
        self.assertEqual(
            "deterministic_composition_property_calculation",
            result["result_kind"],
        )
        self.assertEqual("H2O", result["normalized"]["hill_formula"])
        self.assertEqual(3, result["properties"]["atom_count"]["value"])
        self.assertEqual(10, result["properties"]["proton_count"]["value"])
        self.assertEqual(10, result["properties"]["electron_count"]["value"])
        self.assertEqual(
            "18.015", result["properties"]["relative_formula_mass"]["value"]
        )
        self.assertEqual(
            "1.602176634E-19",
            result["methodology"]["constants"]["elementary_charge_c"],
        )
        hydrogen = result["normalized"]["composition"][0]
        self.assertEqual(
            {"numerator": 2, "denominator": 3, "decimal": "0.666666666666667",
             "method_class": "exact_from_input"},
            hydrogen["atomic_fraction"],
        )
        self.assertNotIn("degree_of_unsaturation", result["properties"])

    def test_empirical_formula_and_degree_of_unsaturation(self) -> None:
        result = self.calculator.calculate_formula("C6H6")
        self.assertEqual("CH", result["normalized"]["empirical_formula"])
        self.assertEqual(4, result["properties"]["degree_of_unsaturation"]["value"])

    def test_reviewed_species_uses_authored_composition_and_charge(self) -> None:
        result = self.calculator.calculate_species("chem:carbonate")
        self.assertEqual(-2, result["input"]["charge"])
        self.assertEqual(32, result["properties"]["electron_count"]["value"])
        self.assertEqual("CO3^2-", result["input"]["reviewed_formula"])

    def test_ideal_gas_density_requires_and_records_conditions(self) -> None:
        result = self.calculator.calculate_formula(
            "O2", temperature_k=Decimal("273.15"), pressure_pa=Decimal("101325")
        )
        density = Decimal(result["properties"]["ideal_gas_density"]["value"])
        self.assertGreater(density, Decimal("1.42"))
        self.assertLess(density, Decimal("1.44"))
        with self.assertRaisesRegex(CalculationError, "requires both"):
            self.calculator.calculate_formula(
                "O2", temperature_k=Decimal("273.15")
            )

    def test_atomic_number_without_isotope_abstains_from_nuclear_model(self) -> None:
        result = self.calculator.calculate_atom(26, charge=2)
        self.assertEqual("Fe", result["identity"]["symbol"])
        self.assertEqual(24, result["properties"]["electron_count"]["value"])
        self.assertNotIn("mass_number", result["properties"])
        self.assertIn("source_relative_atomic_mass", result["properties"])
        reasons = json.dumps(result["not_identifiable_from_inputs"])
        self.assertIn("provide --neutrons", reasons)

    def test_isotope_nuclear_values_are_explicitly_semi_empirical(self) -> None:
        result = self.calculator.calculate_atom(26, neutrons=30)
        properties = result["properties"]
        self.assertEqual(56, properties["mass_number"]["value"])
        self.assertEqual(
            "semi_empirical_model",
            properties["nuclear_binding_energy"]["method_class"],
        )
        self.assertGreater(properties["nuclear_binding_energy"]["value"], 450)
        self.assertLess(properties["nuclear_binding_energy"]["value"], 550)
        self.assertTrue(properties["model_bound_indicator"]["value"])

    def test_output_is_byte_stable_for_same_database_and_input(self) -> None:
        first = json.dumps(
            self.calculator.calculate_formula("Al2(SO4)3"), sort_keys=True
        )
        second = json.dumps(
            self.calculator.calculate_formula("Al2(SO4)3"), sort_keys=True
        )
        self.assertEqual(first, second)

    def test_invalid_inputs_fail_instead_of_inventing_values(self) -> None:
        with self.assertRaisesRegex(CalculationError, "between 1 and 118"):
            self.calculator.calculate_atom(0)
        with self.assertRaisesRegex(CalculationError, "negative electron count"):
            self.calculator.calculate_formula("H", charge=2)


if __name__ == "__main__":
    unittest.main()
