from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from scripts.import_isotope_ame import (
    DEFAULT_SOURCE,
    WIDTHS,
    load_records,
    numeric,
    parse_table,
    split_fields,
)


class AMEImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_records()
        cls.text = DEFAULT_SOURCE.read_text(encoding="ascii")
        cls.header = "\n".join(cls.text.splitlines()[:36]) + "\n"

    def observation(self, z, a, prop="atomic_mass"):
        return next(
            row
            for row in self.records["observations"]
            if (row["z"], row["a"], row["property"]) == (z, a, prop)
        )

    def test_complete_pinned_release_counts_and_identity(self):
        self.assertEqual(3558, len(self.records["nuclides"]))
        self.assertEqual(10674, len(self.records["observations"]))
        self.assertEqual([], self.records["gaps"])
        self.assertEqual(
            2550,
            sum(
                not row["estimated"]
                for row in self.records["observations"]
                if row["property"] == "atomic_mass"
            ),
        )
        keys = {(row["z"], row["a"], row["isomer"]) for row in self.records["nuclides"]}
        self.assertEqual(3558, len(keys))
        self.assertIn((0, 1, 0), keys)
        self.assertIn((118, 295, 0), keys)

    def test_atomic_mass_split_fields_and_micro_u_scale(self):
        hydrogen = self.observation(1, 1)
        self.assertEqual(Decimal("1.007825031898"), Decimal(hydrogen["value"]))
        self.assertEqual(Decimal("0.000000000014"), Decimal(hydrogen["uncertainty"]))
        self.assertEqual(Decimal(12), Decimal(self.observation(6, 12)["value"]))
        self.assertEqual(
            Decimal(0), Decimal(self.observation(6, 12, "mass_excess")["value"])
        )
        self.assertEqual(
            Decimal("7073.9156"),
            Decimal(self.observation(2, 4, "binding_energy_per_nucleon")["value"]),
        )

    def test_estimates_remain_curated_flagged_and_not_direct_measurements(self):
        lithium = self.observation(3, 3)
        self.assertTrue(lithium["estimated"])
        self.assertEqual(Decimal("3.030775"), Decimal(lithium["value"]))
        self.assertEqual("curated", lithium["provenance_class"])
        self.assertIn("evaluated", lithium["method"])
        self.assertIn("line:", lithium["source_locator"])
        self.assertEqual(
            Decimal("-2267"),
            Decimal(self.observation(3, 3, "binding_energy_per_nucleon")["value"]),
        )

    def test_unavailable_fields_are_absent_not_zero(self):
        line = self.observation(1, 1)["source_record"]
        fields = split_fields(line)
        fields[9], fields[10] = "*", ""
        mutated = "".join(field.rjust(width) for field, width in zip(fields, WIDTHS))
        nuclides, observations, gaps = parse_table(self.header + mutated)
        self.assertEqual(1, len(nuclides))
        self.assertEqual(2, len(observations))
        self.assertEqual("mass_excess", gaps[0]["property"])
        self.assertEqual((None, False), numeric("*"))
        self.assertEqual((Decimal(0), False), numeric("0.0"))

    def test_format_corruption_duplicates_and_truncation_rejected(self):
        with self.assertRaises(ValueError):
            parse_table(self.text.replace("f14.6", "f13.6", 1))
        line = self.observation(1, 1)["source_record"]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            parse_table(self.header + line + "\n" + line)
        with self.assertRaisesRegex(ValueError, "Truncated"):
            parse_table(self.header + line[:70])
        for field in ("NaN", "Infinity", "wrong"):
            with self.assertRaises(ValueError):
                numeric(field)

    def test_checksum_pins_source_native_bytes(self):
        source = self.records["sources"][0]
        self.assertEqual(64, len(source["sha256"]))
        self.assertIn("doi.org", source["references"][0])
        with tempfile.TemporaryDirectory() as temporary:
            corrupt = Path(temporary) / "corrupt.mas20"
            corrupt.write_bytes(DEFAULT_SOURCE.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "checksum"):
                load_records(corrupt)


if __name__ == "__main__":
    unittest.main()
