"""Conservative nuclear parsing and provenance regression checks."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.normalize_nuclear_properties import (
    decay_token,
    lifetime,
    normalize_database,
    spin_assignment,
    write_report,
)

ROOT = Path(__file__).resolve().parents[1]


class NuclearNormalizationTests(unittest.TestCase):
    def test_exact_lifetime_bounds_and_asymmetric_uncertainty(self):
        value = lifetime("12.32", "y", "0.02")
        self.assertEqual(
            value["value"], {"numerator": "9719533208", "denominator": "25"}
        )
        self.assertEqual(
            value["uncertainty"], {"numerator": "15778463", "denominator": "25"}
        )
        bound = lifetime("<0.1#", "ns")
        self.assertEqual(bound["relation"], "<")
        self.assertEqual(bound["value_kind"], "bound")
        self.assertTrue(bound["estimated"])
        self.assertEqual(bound["value"]["denominator"], "10000000000")
        asym = lifetime("1", "ms", "+0.2-0.1")
        self.assertEqual(asym["uncertainty_plus"]["denominator"], "5000")
        self.assertEqual(asym["uncertainty_minus"]["denominator"], "10000")
        self.assertEqual(lifetime("1", "s", "~1")["uncertainty_kind"], "unsupported")
        for text in ("stbl", "~1", "0", "1-2"):
            self.assertIsNone(lifetime(text, "s"))

    def test_spin_assignment_does_not_collapse_alternatives(self):
        self.assertEqual(
            spin_assignment("3/2-#")["spin_hbar"],
            {"numerator": "3", "denominator": "2"},
        )
        self.assertEqual(spin_assignment("0+*")["parity"], 1)
        for text in ("(3/2+)", "1/2+,3/2+", "1/2", "(0,1)-", "1/3+"):
            self.assertIsNone(spin_assignment(text))

    def test_decay_conservation_without_daughter_state(self):
        combined = decay_token("B+=100", 6, 11)
        self.assertEqual(
            combined["mode_semantics"],
            "positron_emission_or_electron_capture_inclusive",
        )
        self.assertFalse(combined["disjoint_branch_guaranteed"])
        for token, z, a, expected in [
            ("B-=100", 0, 1, (1, 1)),
            ("A=25#", 92, 238, (90, 234)),
            ("2n<10", 10, 22, (10, 20)),
            ("EC=100", 4, 7, (3, 7)),
        ]:
            record = decay_token(token, z, a)
            self.assertEqual((record["daughter_z"], record["daughter_a"]), expected)
            self.assertIsNone(record["daughter_state"])
            self.assertFalse(record["channel_complete"])
        for token in ("B-n=20", "B+=100 2", "IS=100", "SF=100", "IT=100", "A=101"):
            self.assertIsNone(decay_token(token, 3, 8))
        self.assertIsNone(decay_token("p=100", 0, 1))

    @unittest.skipUnless((ROOT / "isotopes.db").exists(), "reference database absent")
    def test_report_retains_state_and_source_review_boundary(self):
        report = normalize_database(ROOT / "isotopes.db")
        self.assertEqual(report["status"], "unverified")
        self.assertGreater(report["counts"]["withdrawn_states"], 0)
        self.assertTrue(
            all(
                row["review_status"] == "pending_human_review"
                for row in report["records"]
            )
        )
        self.assertTrue(all(row["source_record"] for row in report["records"]))
        self.assertTrue(any(row["state_index"] != 0 for row in report["records"]))
        withdrawn = {
            (s["z"], s["a"], s["state_index"])
            for s in report["states"]
            if s["withdrawn"]
        }
        self.assertFalse(
            any(
                (r["z"], r["a"], r["state_index"]) in withdrawn
                for r in report["records"]
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            write_report(report, output)
            original = output.read_bytes()
            write_report(report, output)
            self.assertEqual(original, output.read_bytes())
            self.assertEqual(json.loads(original)["counts"], report["counts"])


if __name__ == "__main__":
    unittest.main()
