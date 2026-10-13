import copy
import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from fractions import Fraction
from pathlib import Path

from scripts.review_research_evidence import (
    CHECKS,
    ROOT,
    apply_decisions,
    digest,
    make_plan,
)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.plan = make_plan()
        self.item = next(
            p
            for p in self.plan["proposals"]
            if not p["blocked_reasons"]
            and p["research_record"]["property"] == "density"
        )
        self.manifest = {
            "plan_sha256": self.plan["plan_sha256"],
            "reviewer": "test fixture only",
            "reviewed_at": "2026-10-12",
            "decisions": [
                {
                    "research_id": self.item["research_id"],
                    "decision": "approve",
                    "checks": dict.fromkeys(CHECKS, True),
                    "provenance_class": "curated",
                    "rationale": "Synthetic review fixture; not scientific approval",
                    "license_determination": "Test-only factual-value determination",
                }
            ],
        }
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "reviewed.db"

    def apply(self, manifest=None, plan=None):
        return apply_decisions(
            ROOT / "universe.db",
            ROOT / "elements.db",
            plan or self.plan,
            manifest or self.manifest,
            self.output,
        )

    def test_exact_mapping_atomic_copy_and_audit(self):
        before = digest(ROOT / "universe.db")
        self.assertEqual(self.item["mapping"]["unit_id"], "unit:milligram_per_litre")
        raw = self.item["research_record"]
        self.assertEqual(
            Fraction(*self.item["mapping"]["value"]),
            Fraction(raw["value_numerator"], raw["value_denominator"]) * 1000,
        )
        self.assertEqual(self.apply(), 1)
        self.assertEqual(before, digest(ROOT / "universe.db"))
        with closing(sqlite3.connect(self.output)) as db:
            row = db.execute(
                "SELECT value_numerator,value_denominator,provenance_class FROM observation WHERE observation_id LIKE ?",
                ("admission:%",),
            ).fetchone()
            self.assertEqual(
                Fraction(*row[:2]), Fraction(*self.item["mapping"]["value"])
            )
            self.assertEqual(row[2], "curated")
            self.assertEqual(
                db.execute("SELECT count(*) FROM evidence_review").fetchone()[0], 1
            )
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.apply()

    def test_pressure_exact_and_no_temperature_inference(self):
        research = Path(self.temp.name) / "elements.db"
        shutil.copyfile(ROOT / "elements.db", research)
        with closing(sqlite3.connect(research)) as db:
            raw = json.loads(self.item["research_record"]["input_json"])
            raw["pressure_pa"] = {"numerator": 101325, "denominator": 2}
            db.execute(
                "UPDATE unverified_element_observation SET input_json=?, temperature_k_numerator=NULL, temperature_k_denominator=NULL WHERE observation_id=?",
                (json.dumps(raw), self.item["research_id"]),
            )
            db.commit()
        plan = make_plan(ROOT / "universe.db", research)
        manifest = copy.deepcopy(self.manifest)
        manifest["plan_sha256"] = plan["plan_sha256"]
        apply_decisions(ROOT / "universe.db", research, plan, manifest, self.output)
        with closing(sqlite3.connect(self.output)) as db:
            rows = db.execute(
                "SELECT quantity_kind,value_numerator,value_denominator,unit_id FROM condition_value WHERE condition_set_id LIKE ?",
                ("admission:%",),
            ).fetchall()
            self.assertEqual(rows, [("pressure", 101325, 2, "unit:pascal")])
            self.assertEqual(
                db.execute(
                    "SELECT uncertainty_numerator,uncertainty_denominator FROM observation WHERE observation_id LIKE ?",
                    ("admission:%",),
                ).fetchone(),
                (None, None),
            )

    def test_attestation_required_and_no_partial_output(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["decisions"][0]["checks"]["license"] = False
        with self.assertRaisesRegex(ValueError, "attestations"):
            self.apply(manifest)
        self.assertFalse(self.output.exists())

    def test_tampered_plan_rejected(self):
        plan = copy.deepcopy(self.plan)
        plan["proposals"][0]["source"]["url"] = "https://example.invalid"
        with self.assertRaisesRegex(ValueError, "modified"):
            self.apply(plan=plan)

    def test_blocked_and_duplicate_decisions(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["decisions"][0]["research_id"] = next(
            p["research_id"] for p in self.plan["proposals"] if p["blocked_reasons"]
        )
        with self.assertRaisesRegex(ValueError, "blocked"):
            self.apply(manifest)
        manifest = copy.deepcopy(self.manifest)
        manifest["decisions"].append(copy.deepcopy(manifest["decisions"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.apply(manifest)


if __name__ == "__main__":
    unittest.main()
