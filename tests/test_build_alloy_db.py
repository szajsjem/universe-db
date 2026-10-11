import copy
import unittest
from fractions import Fraction

from scripts.build_alloy_db import percentage, validate_alloy, validate_property


class AlloyValidationTests(unittest.TestCase):
    def setUp(self):
        self.alloy = {
            "id": "test",
            "family": "nickel",
            "base_element": "Ni",
            "source_ids": ["source"],
            "composition": [
                {"element": "Ni", "role": "balance", "source_id": "source"},
                {
                    "element": "Cr",
                    "role": "specified",
                    "source_id": "source",
                    "min_wt_pct": "20",
                    "max_wt_pct": "23",
                },
            ],
        }

    def test_exact_percentages_and_unknowns(self):
        self.assertEqual(percentage("0.015"), Fraction(3, 200))
        self.assertIsNone(percentage(None))
        validate_alloy(self.alloy)

    def test_impossible_and_reversed_compositions(self):
        for lower, upper in [("24", "23"), ("101", None)]:
            alloy = copy.deepcopy(self.alloy)
            alloy["composition"][1].update(min_wt_pct=lower, max_wt_pct=upper)
            with self.assertRaises(ValueError):
                validate_alloy(alloy)

    def test_balance_is_not_a_nominal_percentage(self):
        self.alloy["composition"][0]["nominal_wt_pct"] = "77"
        with self.assertRaises(ValueError):
            validate_alloy(self.alloy)

    def test_combined_analyte_is_preserved(self):
        self.alloy["composition"][0].update(
            element="Ni+Co", role="specified", min_wt_pct="50"
        )
        validate_alloy(self.alloy)
        self.alloy["composition"][0]["element"] = "Ni+Imaginary"
        with self.assertRaises(ValueError):
            validate_alloy(self.alloy)

    def test_unattached_source_rejected(self):
        self.alloy["composition"][1]["source_id"] = "other"
        with self.assertRaises(ValueError):
            validate_alloy(self.alloy)


class PropertyValidationTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "id": "density-test",
            "alloy_id": "test",
            "property": "density",
            "unit": "g/cm3",
            "value": "4.42",
            "temperature_c": "22",
            "condition": "Source-reported physical value; product form unspecified",
            "method": "not specified by source",
            "source_id": "source",
            "source_locator": "Table 2, page 1",
            "value_kind": "typical",
        }

    def test_units_and_exact_source_value(self):
        self.assertEqual(validate_property(self.row)["value"], Fraction(221, 50))
        self.row["unit"] = "MPa"
        with self.assertRaisesRegex(ValueError, "dimension"):
            validate_property(self.row)

    def test_missing_temperature_is_not_room_temperature(self):
        del self.row["temperature_c"]
        self.assertIsNone(validate_property(self.row)["temperature_c"])

    def test_invalid_uncertainty_and_temperature(self):
        self.row["uncertainty"] = "-0.1"
        with self.assertRaisesRegex(ValueError, "uncertainty"):
            validate_property(self.row)
        del self.row["uncertainty"]
        self.row["temperature_c"] = "-273.16"
        with self.assertRaisesRegex(ValueError, "absolute zero"):
            validate_property(self.row)

    def test_minimum_and_range_keep_their_semantics(self):
        self.row.update(value_kind="minimum")
        with self.assertRaisesRegex(ValueError, "lower bound"):
            validate_property(self.row)
        self.row.update(value=None, min="4.42")
        validate_property(self.row)
        self.row.update(value_kind="range", max="4.40")
        with self.assertRaisesRegex(ValueError, "reversed"):
            validate_property(self.row)

    def test_context_and_locator_are_required(self):
        self.row["source_locator"] = ""
        with self.assertRaisesRegex(ValueError, "context"):
            validate_property(self.row)


if __name__ == "__main__":
    unittest.main()
