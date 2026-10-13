import copy
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.build_molecular_evidence import SOURCE_DIR, build, extract


class MolecularEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.ref = json.loads((SOURCE_DIR / "manifest.json").read_text())["records"][4]
        self.compound = json.loads((SOURCE_DIR / self.ref["file"]).read_text())[
            "PC_Compounds"
        ][0]

    def test_charge_formula_endpoints(self):
        for mutation in ("charge", "formula", "endpoint"):
            d = copy.deepcopy(self.compound)
            if mutation == "charge":
                d["charge"] = 1
            elif mutation == "formula":
                d["atoms"]["element"][0] = 6
            else:
                d["bonds"]["aid2"][0] = 999
            with self.assertRaises(ValueError):
                extract(d, self.ref)

    def test_isotope_and_native_stereo(self):
        m = json.loads((SOURCE_DIR / "manifest.json").read_text())
        for ref in m["records"]:
            d = json.loads((SOURCE_DIR / ref["file"]).read_text())["PC_Compounds"][0]
            rec = extract(d, ref)
            if ref["name"] == "heavy_water":
                self.assertEqual([a["isotope"] for a in rec["atoms"]], [None, 2, 2])
            if ref["name"] == "l_alanine":
                self.assertTrue(rec["native_graph"]["stereo"])
            self.assertNotIn("coords", rec["native_graph"])

    def test_deterministic_and_counts(self):
        with tempfile.TemporaryDirectory() as td:
            a = build(Path(td) / "a.db")
            b = build(Path(td) / "b.db")
            self.assertEqual(a.read_bytes(), b.read_bytes())
            with closing(sqlite3.connect(a)) as db:
                self.assertEqual(
                    db.execute(
                        "select count(*) from unverified_molecular_molecule"
                    ).fetchone()[0],
                    19,
                )
                self.assertEqual(db.execute("pragma foreign_key_check").fetchall(), [])

    def test_stale_source_refused(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            m = {"retrieved_at": "2026-10-13", "records": [dict(self.ref)]}
            (p / self.ref["file"]).write_text("{}")
            (p / "manifest.json").write_text(json.dumps(m))
            output = p / "keep.db"
            output.write_bytes(b"previous")
            with self.assertRaisesRegex(ValueError, "SHA256"):
                build(output, p)
            self.assertEqual(output.read_bytes(), b"previous")


if __name__ == "__main__":
    unittest.main()
