#!/usr/bin/env python3
"""Pinned NIST ASD ground-state electronic evidence; no core promotion."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import tempfile
from contextlib import closing
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources/atomic/nist-asd-metadata.json"
SCHEMA = """
PRAGMA foreign_keys=ON;
PRAGMA user_version=1;
CREATE TABLE unverified_atomic_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) STRICT;
CREATE TABLE unverified_atomic_source(source_id TEXT PRIMARY KEY,title TEXT NOT NULL,url TEXT NOT NULL,version TEXT NOT NULL,retrieved_at TEXT NOT NULL,license_note TEXT NOT NULL,input_json TEXT NOT NULL) STRICT;
CREATE TABLE unverified_atomic_state(state_id TEXT PRIMARY KEY,z INTEGER NOT NULL CHECK(z BETWEEN 1 AND 118),element TEXT NOT NULL,ion_charge INTEGER NOT NULL CHECK(ion_charge>=0 AND ion_charge<z),electron_count INTEGER NOT NULL CHECK(electron_count=z-ion_charge),isotope_mass_number INTEGER CHECK(isotope_mass_number IS NULL),state TEXT NOT NULL CHECK(state='electronic_ground_state'),ground_shells TEXT,ground_configuration TEXT,ground_level TEXT,source_id TEXT NOT NULL REFERENCES unverified_atomic_source,source_locator TEXT NOT NULL,input_json TEXT NOT NULL,review_status TEXT NOT NULL CHECK(review_status='pending_human_review')) STRICT;
CREATE TABLE unverified_atomic_observation(observation_id TEXT PRIMARY KEY,state_id TEXT NOT NULL REFERENCES unverified_atomic_state,property TEXT NOT NULL CHECK(property='ionization_energy'),unit TEXT NOT NULL CHECK(unit='eV'),value_numerator TEXT NOT NULL,value_denominator TEXT NOT NULL,uncertainty_numerator TEXT,uncertainty_denominator TEXT,source_qualifier TEXT NOT NULL CHECK(source_qualifier IN ('evaluated_experimental','semiempirical','theoretical')),provenance_class TEXT NOT NULL CHECK(provenance_class IN ('curated','modeled')),source_id TEXT NOT NULL REFERENCES unverified_atomic_source,source_locator TEXT NOT NULL,reference_ids TEXT NOT NULL,input_json TEXT NOT NULL,review_status TEXT NOT NULL CHECK(review_status='pending_human_review'),CHECK((uncertainty_numerator IS NULL)=(uncertainty_denominator IS NULL))) STRICT;
CREATE TABLE unverified_atomic_gap(state_id TEXT,property TEXT NOT NULL,reason TEXT NOT NULL,input_json TEXT NOT NULL) STRICT;
"""


def cell(value):
    """Decode ASD's spreadsheet text wrapper without evaluating formulas."""
    if value is None:
        return ""
    value = value.strip()
    return value[2:-1] if value.startswith('="') and value.endswith('"') else value


def decimal(value):
    if not re.fullmatch(
        r"[+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?", value
    ):
        raise ValueError("invalid nonnegative decimal")
    return Fraction(value)


def parse_snapshot(text):
    reader = csv.DictReader(io.StringIO(text))
    names = reader.fieldnames or []
    energy = next(
        (n for n in names if n.startswith("Ionization Energy") and n.endswith("(eV)")),
        None,
    )
    uncertainty = next(
        (n for n in names if n.startswith("Uncertainty") and n.endswith("(eV)")), None
    )
    if (
        not energy
        or not uncertainty
        or not {
            "At. num",
            "Sp. Name",
            "Ion Charge",
            "Prefix",
            "Suffix",
            "References",
        }.issubset(names)
    ):
        raise ValueError("unsupported ASD columns/units")
    states, observations, gaps = [], [], []
    seen = set()
    for row_number, raw in enumerate(reader, 2):
        if cell(raw.get("At. num")) == "Notes:":
            break
        row = {k: cell(v) for k, v in raw.items() if k is not None}
        if not row.get("At. num"):
            continue
        z, charge = int(row["At. num"]), int(row["Ion Charge"])
        spectrum = row["Sp. Name"]
        if (
            not 1 <= z <= 118
            or not 0 <= charge < z
            or not re.fullmatch(r"[A-Z][a-z]? [IVXLCDM]+", spectrum)
        ):
            raise ValueError("invalid state identity")
        identity = f"Z{z}-q{charge}"
        if identity in seen:
            raise ValueError("duplicate isotope-unspecified state")
        seen.add(identity)
        row.update(
            state_id=identity,
            z=z,
            ion_charge=charge,
            element=spectrum.split()[0],
            source_locator=f"CSV row {row_number}",
        )
        states.append(row)
        if not row[energy]:
            gaps.append(
                dict(
                    state_id=identity,
                    property="ionization_energy",
                    reason="NIST reports unknown ionization energy",
                    input_json=json.dumps(row, sort_keys=True),
                )
            )
            continue
        qualifiers = {
            ("", ""): "evaluated_experimental",
            ("[", "]"): "semiempirical",
            ("(", ")"): "theoretical",
        }
        qualifier = qualifiers.get((row["Prefix"], row["Suffix"]))
        if qualifier is None:
            raise ValueError("unsupported energy qualifier")
        value = decimal(row[energy])
        if value <= 0:
            raise ValueError("ionization energy must be positive")
        unc = decimal(row[uncertainty]) if row[uncertainty] else None
        observations.append(
            dict(
                state_id=identity,
                value=value,
                uncertainty=unc,
                qualifier=qualifier,
                raw=row,
            )
        )
    if not states:
        raise ValueError("empty source")
    return states, observations, gaps


def build(output=ROOT / "atomic.db", metadata_path=SOURCE):
    metadata_path = Path(metadata_path)
    meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    for key in (
        "source_id",
        "title",
        "url",
        "version",
        "retrieved_at",
        "license_note",
        "file",
        "sha256",
    ):
        if not meta.get(key):
            raise ValueError(f"missing source {key}")
    payload = (metadata_path.parent / meta["file"]).read_bytes()
    if hashlib.sha256(payload).hexdigest() != meta["sha256"]:
        raise ValueError("pinned source checksum mismatch")
    states, observations, gaps = parse_snapshot(payload.decode("utf-8-sig"))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(suffix=".db", dir=output.parent)
    os.close(fd)
    try:
        with closing(sqlite3.connect(temporary)) as db:
            db.executescript(SCHEMA)
            db.execute(
                "INSERT INTO unverified_atomic_source VALUES(?,?,?,?,?,?,?)",
                tuple(
                    meta[k]
                    for k in (
                        "source_id",
                        "title",
                        "url",
                        "version",
                        "retrieved_at",
                        "license_note",
                    )
                )
                + (json.dumps(meta, sort_keys=True),),
            )
            for row in states:
                db.execute(
                    "INSERT INTO unverified_atomic_state VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        row["state_id"],
                        row["z"],
                        row["element"],
                        row["ion_charge"],
                        row["z"] - row["ion_charge"],
                        None,
                        "electronic_ground_state",
                        row.get("Ground Shells (a)") or None,
                        row.get("Ground Config.") or None,
                        row.get("Ground Level") or None,
                        meta["source_id"],
                        row["source_locator"],
                        json.dumps(row, sort_keys=True),
                        "pending_human_review",
                    ),
                )
            for obs in observations:
                value, unc, row = obs["value"], obs["uncertainty"], obs["raw"]
                db.execute(
                    "INSERT INTO unverified_atomic_observation VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        obs["state_id"] + "-IE",
                        obs["state_id"],
                        "ionization_energy",
                        "eV",
                        str(value.numerator),
                        str(value.denominator),
                        str(unc.numerator) if unc is not None else None,
                        str(unc.denominator) if unc is not None else None,
                        obs["qualifier"],
                        "curated"
                        if obs["qualifier"] == "evaluated_experimental"
                        else "modeled",
                        meta["source_id"],
                        row["source_locator"],
                        row["References"],
                        json.dumps(row, sort_keys=True),
                        "pending_human_review",
                    ),
                )
            db.executemany(
                "INSERT INTO unverified_atomic_gap VALUES(:state_id,:property,:reason,:input_json)",
                gaps,
            )
            # Neutral absent states are distinct from present states with unknown energy.
            neutral = {row["z"] for row in states if row["ion_charge"] == 0}
            db.executemany(
                "INSERT INTO unverified_atomic_gap VALUES(?,?,?,?)",
                (
                    (
                        f"Z{z}-q0",
                        "ionization_energy",
                        "No neutral-state row in pinned H-Ds query",
                        json.dumps({"z": z, "query_scope": "H-Ds"}),
                    )
                    for z in range(1, 119)
                    if z not in neutral
                ),
            )
            db.executemany(
                "INSERT INTO unverified_atomic_metadata VALUES(?,?)",
                [
                    ("schema_version", "1"),
                    ("source_sha256", meta["sha256"]),
                    (
                        "review_boundary",
                        "All rows pending human review; isotope unspecified, isolated electronic ground states; no ambient material context.",
                    ),
                    (
                        "transformation",
                        "build_atomic_evidence.py v1: exact ASD eV output, no native wavenumber conversion; source bracket qualifiers retained.",
                    ),
                ],
            )
            if (
                db.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                or db.execute("PRAGMA foreign_key_check").fetchall()
            ):
                raise ValueError("database integrity failure")
            db.commit()
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{digest}  {output.name}\n", encoding="ascii"
    )
    return {
        "states": len(states),
        "observations": len(observations),
        "source_gaps": len(gaps),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "atomic.db")
    args = parser.parse_args()
    print(json.dumps(build(args.output), sort_keys=True))


if __name__ == "__main__":
    main()
