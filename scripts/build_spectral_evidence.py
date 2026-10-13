#!/usr/bin/env python3
"""Pinned NIST Handbook spectral facts; offline builds never promote evidence."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sqlite3
import tempfile
import urllib.request
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "sources/spectra/nist-handbook-strong-lines.json"
MANIFEST = ROOT / "sources/spectra/nist-handbook-strong-lines.sha256"
ELEMENTS = [
    ("H", "hydrogen"),
    ("He", "helium"),
    ("Li", "lithium"),
    ("C", "carbon"),
    ("N", "nitrogen"),
    ("O", "oxygen"),
    ("Na", "sodium"),
    ("Mg", "magnesium"),
    ("Al", "aluminum"),
    ("Si", "silicon"),
    ("Fe", "iron"),
    ("Ni", "nickel"),
    ("Cu", "copper"),
    ("Ag", "silver"),
    ("Au", "gold"),
    ("Ti", "titanium"),
]
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8}
SCHEMA = """
PRAGMA foreign_keys=ON;
PRAGMA user_version=1;
CREATE TABLE unverified_spectral_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) STRICT;
CREATE TABLE unverified_spectral_source(source_id TEXT PRIMARY KEY,url TEXT NOT NULL,citation TEXT NOT NULL,version TEXT NOT NULL,retrieved_at TEXT NOT NULL,response_sha256 TEXT NOT NULL,license_note TEXT NOT NULL,input_json TEXT NOT NULL) STRICT;
CREATE TABLE unverified_spectral_line(line_id TEXT PRIMARY KEY,source_id TEXT NOT NULL REFERENCES unverified_spectral_source,element_symbol TEXT NOT NULL,spectrum_stage INTEGER NOT NULL CHECK(spectrum_stage>0),ion_charge INTEGER NOT NULL CHECK(ion_charge>=0),wavelength_numerator INTEGER NOT NULL CHECK(wavelength_numerator>0),wavelength_denominator INTEGER NOT NULL CHECK(wavelength_denominator>0),wavelength_unit TEXT NOT NULL CHECK(wavelength_unit='nm'),medium TEXT NOT NULL CHECK(medium IN ('air','vacuum')),reported_wavelength_angstrom TEXT NOT NULL,intensity_native TEXT NOT NULL,intensity_basis TEXT NOT NULL,marker_text TEXT NOT NULL,reference_code TEXT NOT NULL,reference_url TEXT NOT NULL,source_locator TEXT NOT NULL,provenance_class TEXT NOT NULL CHECK(provenance_class='curated'),review_status TEXT NOT NULL CHECK(review_status='pending_human_review'),input_json TEXT NOT NULL) STRICT;
CREATE TABLE unverified_spectral_gap(gap_id TEXT PRIMARY KEY,source_id TEXT REFERENCES unverified_spectral_source,description TEXT NOT NULL) STRICT;
"""


def parse_html(document: str, symbol: str, url: str) -> list[dict]:
    """Parse the accessible preformatted table, rejecting malformed numeric rows."""
    blocks = re.findall(r"<pre\b[^>]*>(.*?)</pre>", document, re.I | re.S)
    if len(blocks) != 1:
        raise ValueError("Expected one strong-line preformatted table")
    block = blocks[0]
    if "Wavelength" not in block or "Intensity" not in block:
        raise ValueError("Unexpected table header")
    medium = None
    rows = []
    for number, raw in enumerate(block.splitlines(), 1):
        text = html.unescape(re.sub(r"<[^>]*>", "", raw)).strip()
        if text in {"Air", "Vacuum"}:
            medium = text.lower()
            continue
        if not text or not re.match(r"^\d", text):
            continue
        match = re.fullmatch(
            r"(\d+[A-Za-z*]*)(.*?)\s+(\d+(?:\.\d+)?)\s+([A-Z][a-z]?)\s+([IVX]+)\s+(\S+)",
            text,
        )
        if not match or not medium:
            raise ValueError(f"Ambiguous spectral row {symbol}:{number}: {text}")
        intensity, markers, wavelength, element, roman, reference = match.groups()
        if element != symbol or roman not in ROMAN:
            raise ValueError("Unexpected element or spectrum stage")
        links = re.findall(r'href=["\']([^"\']+)["\']', raw, re.I)
        reference_links = [link for link in links if link.endswith("#" + reference)]
        if len(reference_links) != 1:
            raise ValueError("Missing unique upstream reference link")
        rows.append(
            dict(
                element_symbol=symbol,
                spectrum_stage=ROMAN[roman],
                medium=medium,
                wavelength_angstrom=wavelength,
                intensity_native=intensity,
                marker_text=markers.strip(),
                reference_code=reference,
                reference_url=urllib.request.urljoin(url, reference_links[0]),
                source_locator=f"preformatted table line {number}",
                row_text=text,
            )
        )
    if not rows:
        raise ValueError("No spectral facts parsed")
    return rows


def refresh(snapshot: Path = SNAPSHOT) -> None:
    sources = []
    for symbol, name in ELEMENTS:
        url = f"https://physics.nist.gov/PhysRefData/Handbook/Tables/{name}table2_a.htm"
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (source-backed scientific evidence snapshot)"
            },
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = response.read()
        rows = parse_html(payload.decode("utf-8"), symbol, url)
        sources.append(
            dict(
                source_id=f"nist-handbook-{symbol.lower()}-strong",
                url=url,
                citation="NIST Standard Reference Database 108, Handbook of Basic Atomic Spectroscopic Data, J. E. Sansonetti and W. C. Martin, DOI:10.18434/T4FW23; elemental strong-line table with original reference codes",
                version="NIST SRD 108; data content last updated November 2013; response pinned by SHA-256",
                retrieved_at=datetime.now(timezone.utc).isoformat(),
                response_sha256=hashlib.sha256(payload).hexdigest(),
                license_note="Only uncopyrightable numerical facts and factual reference/identity codes extracted; publisher prose, layout, and complete HTML are not redistributed.",
                rows=rows,
            )
        )
    body = (
        json.dumps(
            dict(schema_version=1, sources=sources), indent=2, ensure_ascii=False
        )
        + "\n"
    )
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(body, encoding="utf-8")
    snapshot.with_suffix(".sha256").write_text(
        hashlib.sha256(snapshot.read_bytes()).hexdigest() + "  " + snapshot.name + "\n",
        encoding="ascii",
    )


def load_snapshot(snapshot: Path = SNAPSHOT) -> dict:
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    if snapshot.with_suffix(".sha256").read_text().split()[0] != digest:
        raise ValueError("Spectral factual snapshot SHA-256 mismatch")
    data = json.loads(snapshot.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not data.get("sources"):
        raise ValueError("Unsupported spectral snapshot")
    return data


def build(output: Path | str, snapshot: Path = SNAPSHOT) -> Path:
    output = Path(output)
    data = load_snapshot(snapshot)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="spectra-", suffix=".db", dir=output.parent)
    os.close(fd)
    try:
        with sqlite3.connect(temporary) as db:
            db.executescript(SCHEMA)
            db.executemany(
                "INSERT INTO unverified_spectral_metadata VALUES (?,?)",
                [
                    ("schema_version", "1"),
                    (
                        "snapshot_sha256",
                        hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                    ),
                    ("review_status", "pending_human_review"),
                    (
                        "wavelength_conversion",
                        "exact reported angstrom / 10 -> nm; no air-vacuum conversion",
                    ),
                    (
                        "intensity_policy",
                        "Native arbitrary relative intensities; not decay/transition probabilities or cross-species comparison",
                    ),
                ],
            )
            for source in data["sources"]:
                sid = source["source_id"]
                for required in (
                    "url",
                    "citation",
                    "version",
                    "retrieved_at",
                    "response_sha256",
                    "license_note",
                ):
                    if not source.get(required):
                        raise ValueError("Missing source admission field: " + required)
                if not re.fullmatch("[0-9a-f]{64}", source["response_sha256"]):
                    raise ValueError("Invalid upstream response SHA")
                db.execute(
                    "INSERT INTO unverified_spectral_source VALUES (?,?,?,?,?,?,?,?)",
                    (
                        sid,
                        source["url"],
                        source["citation"],
                        source["version"],
                        source["retrieved_at"],
                        source["response_sha256"],
                        source["license_note"],
                        json.dumps(
                            {k: v for k, v in source.items() if k != "rows"},
                            sort_keys=True,
                        ),
                    ),
                )
                for i, row in enumerate(source["rows"], 1):
                    wavelength = Fraction(row["wavelength_angstrom"]) / 10
                    stage = row["spectrum_stage"]
                    if (
                        type(stage) is not int
                        or stage not in ROMAN.values()
                        or row["element_symbol"] not in {s for s, _ in ELEMENTS}
                    ):
                        raise ValueError("Invalid spectrum identity")
                    if (
                        not re.fullmatch(r"\d+(?:\.\d+)?", row["wavelength_angstrom"])
                        or wavelength <= 0
                    ):
                        raise ValueError("Invalid wavelength")
                    db.execute(
                        "INSERT INTO unverified_spectral_line VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            f"{sid}:{i:04}",
                            sid,
                            row["element_symbol"],
                            stage,
                            stage - 1,
                            wavelength.numerator,
                            wavelength.denominator,
                            "nm",
                            row["medium"],
                            row["wavelength_angstrom"],
                            row["intensity_native"],
                            "source-native relative arbitrary scale",
                            row["marker_text"],
                            row["reference_code"],
                            row["reference_url"],
                            row["source_locator"],
                            "curated",
                            "pending_human_review",
                            json.dumps(row, sort_keys=True),
                        ),
                    )
                db.execute(
                    "INSERT INTO unverified_spectral_gap VALUES (?,?,?)",
                    (
                        sid + ":context",
                        sid,
                        "Strong-line tables do not provide line uncertainty, isotope identity, excitation conditions, transition probabilities, complete spectral curves, or upper/lower level identities. Markers retained verbatim; no guessed assignments.",
                    ),
                )
            if (
                db.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                or db.execute("PRAGMA foreign_key_check").fetchall()
            ):
                raise ValueError("Spectral database validation failed")
        db.close()
        os.replace(temporary, output)
    finally:
        if "db" in locals():
            db.close()
        if os.path.exists(temporary):
            os.unlink(temporary)
    output.with_suffix(output.suffix + ".sha256").write_text(
        hashlib.sha256(output.read_bytes()).hexdigest() + "  " + output.name + "\n",
        encoding="ascii",
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "spectra.db")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Explicitly retrieve and replace the pinned NIST factual snapshot",
    )
    args = parser.parse_args()
    if args.refresh:
        refresh()
    print(build(args.output))


if __name__ == "__main__":
    main()
