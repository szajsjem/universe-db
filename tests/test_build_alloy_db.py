import copy
import unittest
from fractions import Fraction

from scripts.build_alloy_db import percentage, validate_alloy


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


if __name__ == "__main__":
    unittest.main()
