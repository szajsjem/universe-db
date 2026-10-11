import json
import tempfile
import unittest
from pathlib import Path

from scripts.import_isotope_nist import DEFAULT_SOURCE, load_records, parse_value


class IsotopeNistTests(unittest.TestCase):
    def test_last_digit_uncertainties_and_estimates(self):
        self.assertEqual(
            parse_value("1.00782503223(9)"), ("1.00782503223", "0.00000000009", False)
        )
        self.assertEqual(parse_value("294.21392(71#)"), ("294.21392", "0.00071", True))
        self.assertEqual(parse_value("12"), ("12", None, False))
        self.assertEqual(parse_value("0.000115(70)"), ("0.000115", "0.000070", False))
        with self.assertRaises(ValueError):
            parse_value("[12,13]")

    def test_full_archive_and_citation_vintage(self):
        data = load_records()
        self.assertEqual(len(data["nuclides"]), 3352)
        masses = [o for o in data["observations"] if o["property"] == "atomic_mass"]
        abundance = [
            o for o in data["observations"] if o["property"] == "isotopic_abundance"
        ]
        self.assertEqual(len(masses), 3352)
        self.assertEqual(len(abundance), 288)
        self.assertEqual(sum(o["estimated"] for o in masses), 915)
        self.assertEqual(len({o["id"] for o in data["observations"]}), 3640)
        self.assertIn("AME2012", data["sources"][0]["version"])
        carbon = next(o for o in masses if (o["z"], o["a"]) == (6, 12))
        self.assertEqual(
            (carbon["value"], carbon["uncertainty"], carbon["unit"]),
            ("12.0000000", "0.0000000", "u"),
        )
        self.assertTrue(all(o["provenance_class"] == "curated" for o in masses))

    def fixture(self, mutate):
        source = json.loads(DEFAULT_SOURCE.read_text(encoding="utf-8"))
        source["records"] = source["records"][:1]
        mutate(source["records"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nist.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            return load_records(path)

    def test_missing_mass_is_gap_not_zero(self):
        data = self.fixture(lambda rows: rows[0].update({"Relative Atomic Mass": ""}))
        self.assertEqual(len(data["nuclides"]), 1)
        self.assertFalse(
            any(o["property"] == "atomic_mass" for o in data["observations"])
        )
        self.assertEqual(data["gaps"][0]["property"], "atomic_mass")

    def test_duplicate_and_invalid_abundance_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.fixture(lambda rows: rows.append(rows[0].copy()))
        with self.assertRaisesRegex(ValueError, "Abundance"):
            self.fixture(lambda rows: rows[0].update({"Isotopic Composition": "1.1"}))


if __name__ == "__main__":
    unittest.main()
