import csv
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from fractions import Fraction
from pathlib import Path

from scripts import build_atomic_evidence as atomic


class AtomicEvidenceTests(unittest.TestCase):
    def fixture(
        self, energy="13.6", uncertainty="0.1", prefix="", suffix="", charge="0"
    ):
        fields = [
            "At. num",
            "Sp. Name",
            "Ion Charge",
            "Ground Config.",
            "Prefix",
            "Ionization Energy (eV)",
            "Suffix",
            "Uncertainty (eV)",
            "References",
        ]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            dict(
                zip(
                    fields,
                    [
                        "1",
                        "H I",
                        charge,
                        "1s",
                        prefix,
                        energy,
                        suffix,
                        uncertainty,
                        "HDEL",
                    ],
                )
            )
        )
        return output.getvalue()

    def test_exact_qualifiers_and_unknown_uncertainty(self):
        states, obs, gaps = atomic.parse_snapshot(
            self.fixture("13.598434599702", "", "(", ")")
        )
        self.assertEqual(obs[0]["value"], Fraction("13.598434599702"))
        self.assertEqual(obs[0]["qualifier"], "theoretical")
        self.assertIsNone(obs[0]["uncertainty"])
        self.assertEqual(states[0]["ion_charge"], 0)
        self.assertFalse(gaps)
        self.assertEqual(
            atomic.parse_snapshot(self.fixture(prefix="[", suffix="]"))[1][0][
                "qualifier"
            ],
            "semiempirical",
        )

    def test_missing_energy_is_gap_not_zero(self):
        states, obs, gaps = atomic.parse_snapshot(self.fixture("", ""))
        self.assertEqual(len(states), 1)
        self.assertEqual(obs, [])
        self.assertEqual(len(gaps), 1)

    def test_context_unit_and_qualifier_guards(self):
        for text in (
            self.fixture(charge="1"),
            self.fixture(prefix="[", suffix=")"),
            self.fixture(energy="0"),
            self.fixture(uncertainty="-1"),
            self.fixture().replace("(eV)", "(K)"),
        ):
            with self.assertRaises(ValueError):
                atomic.parse_snapshot(text)
        self.assertEqual(atomic.cell('="1s"'), "1s")
        with self.assertRaises(ValueError):
            atomic.decimal("=1+2")

    def test_pinned_build_deterministic_and_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "first.db", Path(directory) / "second.db"
            stats = atomic.build(first)
            atomic.build(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(stats["states"], 6019)
            with closing(sqlite3.connect(first)) as db:
                self.assertEqual(
                    db.execute(
                        "select count(*) from unverified_atomic_observation"
                    ).fetchone()[0],
                    5847,
                )
                self.assertEqual(
                    db.execute(
                        "select count(*) from unverified_atomic_state where isotope_mass_number is not null"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    db.execute(
                        "select count(*) from unverified_atomic_observation where source_qualifier!='evaluated_experimental' and provenance_class!='modeled'"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(db.execute("pragma foreign_key_check").fetchall(), [])
                hydrogen = db.execute(
                    "select uncertainty_numerator,uncertainty_denominator from unverified_atomic_observation where state_id='Z1-q0'"
                ).fetchone()
                self.assertEqual(
                    Fraction(int(hydrogen[0]), int(hydrogen[1])),
                    Fraction("0.000000000012"),
                )

    def test_checksum_failure_preserves_output(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            meta = json.loads(atomic.SOURCE.read_text())
            meta["sha256"] = "0" * 64
            (directory / meta["file"]).write_bytes(
                (atomic.SOURCE.parent / meta["file"]).read_bytes()
            )
            metadata = directory / "metadata.json"
            metadata.write_text(json.dumps(meta))
            output = directory / "out.db"
            output.write_bytes(b"preserved")
            with self.assertRaisesRegex(ValueError, "checksum"):
                atomic.build(output, metadata)
            self.assertEqual(output.read_bytes(), b"preserved")


if __name__ == "__main__":
    unittest.main()
