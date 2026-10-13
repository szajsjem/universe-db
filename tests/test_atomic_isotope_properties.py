"""Combined property profiles preserve independent source/model outcomes."""

import unittest
from unittest.mock import patch

from scripts.atomic_isotope_properties import atomic_properties
from scripts.fit_isotope_properties import IsotopeFitError


class AtomicProfileTests(unittest.TestCase):
    def test_missing_mass_preserves_decay_and_integer_composition(self):
        profile = {"mass_model": {}, "decay_model": {}}
        decay = {"status": "source_reference", "half_life": {"value": "1/2"}}
        with (
            patch("scripts.atomic_isotope_properties.predict", return_value=decay),
            patch(
                "scripts.atomic_isotope_properties.predict_isotope",
                side_effect=IsotopeFitError("unsupported mass domain"),
            ),
        ):
            result = atomic_properties(profile, 2, 1, 2)
        self.assertEqual(result["mass"]["status"], "unavailable")
        self.assertEqual(result["decay"], decay)
        self.assertEqual(result["composition"]["mass_number"], 3)
        self.assertEqual(result["composition"]["electrons"], 2)

    def test_ion_failure_is_not_suppressed_by_mass_fallback(self):
        profile = {"mass_model": {}, "decay_model": {}}
        with patch(
            "scripts.atomic_isotope_properties.predict",
            side_effect=ValueError("ion training unsupported"),
        ):
            with self.assertRaisesRegex(ValueError, "ion"):
                atomic_properties(profile, 26, 30, 25)


if __name__ == "__main__":
    unittest.main()
