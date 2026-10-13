import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from fractions import Fraction
from pathlib import Path

from scripts.build_spectral_evidence import SNAPSHOT, build, load_snapshot, parse_html


class SpectralEvidenceTests(unittest.TestCase):
    def test_exact_medium_stage_and_markers(self):
        document = """<pre>Intensity Wavelength (&Aring;) Spectrum Ref.
Vacuum
1000 <a href="persistent#1215.66824">P</a>,c 1215.66824 H I <a href="refs#MK00a">MK00a</a>
Air
20 6562.71 H II <a href="refs#R1">R1</a>
</pre>"""
        rows = parse_html(document, "H", "https://example.org/table")
        self.assertEqual(rows[0]["medium"], "vacuum")
        self.assertEqual(rows[0]["marker_text"], "P,c")
        self.assertEqual(rows[1]["spectrum_stage"], 2)
        self.assertEqual(rows[1]["medium"], "air")
        self.assertEqual(
            Fraction(rows[0]["wavelength_angstrom"]) / 10, Fraction("121.566824")
        )
        self.assertEqual(rows[0]["reference_url"], "https://example.org/refs#MK00a")

    def test_ambiguity_and_identity_guards(self):
        for row in [
            "30 123.4 H I R1",
            '30 123.4 He I <a href="ref#R1">R1</a>',
            '30 ? H I <a href="ref#R1">R1</a>',
        ]:
            with self.assertRaises(ValueError):
                parse_html(
                    "<pre>Intensity Wavelength\nAir\n" + row + "</pre>",
                    "H",
                    "https://example.org",
                )
        with self.assertRaises(ValueError):
            parse_html(
                '<pre>Intensity Wavelength\n30 123.4 H I <a href="ref#R1">R1</a></pre>',
                "H",
                "https://example.org",
            )

    def test_pinned_build_determinism_and_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            a = build(Path(directory) / "a.db")
            b = build(Path(directory) / "b.db")
            self.assertEqual(a.read_bytes(), b.read_bytes())
            with closing(sqlite3.connect(a)) as db:
                self.assertEqual(
                    db.execute("PRAGMA integrity_check").fetchone()[0], "ok"
                )
                self.assertFalse(db.execute("PRAGMA foreign_key_check").fetchall())
                self.assertEqual(
                    db.execute(
                        "SELECT count(*) FROM unverified_spectral_line"
                    ).fetchone()[0],
                    1871,
                )
                self.assertEqual(
                    db.execute(
                        "SELECT count(DISTINCT element_symbol) FROM unverified_spectral_line"
                    ).fetchone()[0],
                    16,
                )
                row = db.execute(
                    "SELECT wavelength_numerator,wavelength_denominator,medium FROM unverified_spectral_line WHERE element_symbol='H' AND reported_wavelength_angstrom='1215.66824'"
                ).fetchone()
                self.assertEqual(Fraction(row[0], row[1]), Fraction("121.566824"))
                self.assertEqual(row[2], "vacuum")
                self.assertEqual(
                    db.execute(
                        "SELECT DISTINCT review_status FROM unverified_spectral_line"
                    ).fetchall(),
                    [("pending_human_review",)],
                )
                self.assertFalse(
                    db.execute(
                        "SELECT name FROM sqlite_master WHERE name='observation'"
                    ).fetchall()
                )

    def test_tamper_and_atomic_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            p = directory / "snapshot.json"
            p.write_bytes(SNAPSHOT.read_bytes())
            p.with_suffix(".sha256").write_text(
                hashlib.sha256(p.read_bytes()).hexdigest()
            )
            data = load_snapshot(p)
            p.write_text("{}")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                load_snapshot(p)
            data["sources"][0]["rows"][0]["medium"] = "unknown"
            p.write_text(json.dumps(data))
            p.with_suffix(".sha256").write_text(
                hashlib.sha256(p.read_bytes()).hexdigest()
            )
            target = directory / "output.db"
            target.write_bytes(b"previous release")
            with self.assertRaises(sqlite3.IntegrityError):
                build(target, p)
            self.assertEqual(target.read_bytes(), b"previous release")


if __name__ == "__main__":
    unittest.main()
