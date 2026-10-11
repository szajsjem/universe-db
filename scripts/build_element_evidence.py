#!/usr/bin/env python3
"""Build source-backed elemental research evidence without promoting core rows."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from fractions import Fraction
from pathlib import Path

if __package__:
    from .build_alloy_db import ELEMENTS
else:
    from build_alloy_db import ELEMENTS

ROOT = Path(__file__).resolve().parents[1]
UNITS = {
    "density": "kg/m3",
    "specific_heat_capacity": "J/(kg*K)",
    "molar_heat_capacity": "J/(mol*K)",
    "thermal_conductivity": "W/(m*K)",
    "electrical_resistivity": "ohm*m",
    "youngs_modulus": "Pa",
    "shear_modulus": "Pa",
    "poisson_ratio": "1",
    "melting_point": "K",
}
SCHEMA = """
PRAGMA foreign_keys=ON;
PRAGMA user_version=1;
CREATE TABLE unverified_element_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) STRICT;
CREATE TABLE unverified_element_source(
 source_id TEXT PRIMARY KEY,title TEXT NOT NULL,url TEXT NOT NULL,
 version TEXT NOT NULL,retrieved_at TEXT NOT NULL,license_note TEXT NOT NULL) STRICT;
CREATE TABLE unverified_element_observation(
 observation_id TEXT PRIMARY KEY,element TEXT NOT NULL,property TEXT NOT NULL,unit TEXT NOT NULL,
 value_numerator INTEGER,value_denominator INTEGER,
 min_numerator INTEGER,min_denominator INTEGER,max_numerator INTEGER,max_denominator INTEGER,
 temperature_k_numerator INTEGER,temperature_k_denominator INTEGER,
 phase TEXT,state TEXT,method TEXT,source_id TEXT NOT NULL REFERENCES unverified_element_source,
 source_locator TEXT NOT NULL,provenance_class TEXT NOT NULL
 CHECK(provenance_class IN ('measured','curated','modeled')),
 note TEXT NOT NULL,review_status TEXT NOT NULL CHECK(review_status='pending_human_review'),
 input_json TEXT NOT NULL,
 CHECK((value_numerator IS NULL)=(value_denominator IS NULL)),
 CHECK((min_numerator IS NULL)=(min_denominator IS NULL)),
 CHECK((max_numerator IS NULL)=(max_denominator IS NULL)),
 CHECK((temperature_k_numerator IS NULL)=(temperature_k_denominator IS NULL)),
 CHECK(value_denominator IS NULL OR value_denominator>0),
 CHECK(min_denominator IS NULL OR min_denominator>0),
 CHECK(max_denominator IS NULL OR max_denominator>0),
 CHECK(temperature_k_denominator IS NULL OR temperature_k_denominator>0)
) STRICT;
CREATE TABLE unverified_element_gap(
 element TEXT NOT NULL,property TEXT NOT NULL,reason TEXT NOT NULL,
 PRIMARY KEY(element,property,reason)) STRICT;
"""


def rational(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("evidence numbers must be strings or integers, never floats")
    return Fraction(value)


def validate_observation(row):
    if row.get("element") not in ELEMENTS:
        raise ValueError("unknown evidence element")
    if row.get("unit") != UNITS.get(row.get("property")):
        raise ValueError("unsupported property/unit pair")
    for key in ("id", "source_id", "source_locator"):
        if not isinstance(row.get(key), str) or not row[key].strip():
            raise ValueError(f"missing {key}")
    if row.get("review_status") != "pending_human_review":
        raise ValueError("element research cannot be promoted by this builder")
    if row.get("provenance_class") not in ("measured", "curated", "modeled"):
        raise ValueError("invalid provenance class")
    if row.get("composition_basis") not in (
        "elemental_reference",
        "finite_purity_specimen",
        "unspecified",
    ):
        raise ValueError("explicit composition basis required")
    for key in (
        "pressure_pa",
        "expanded_relative_uncertainty_percent",
        "uncertainty_coverage_probability",
    ):
        if row.get(key) is not None:
            extra = rational(row[key])
            if extra < 0:
                raise ValueError("negative condition or uncertainty")
            if key == "uncertainty_coverage_probability" and extra > 1:
                raise ValueError("invalid coverage probability")
    values = {
        key: rational(row.get(key)) for key in ("value", "min", "max", "temperature_k")
    }
    if all(values[key] is None for key in ("value", "min", "max")):
        raise ValueError("observation must have a value or bound")
    if (
        values["min"] is not None
        and values["max"] is not None
        and values["min"] > values["max"]
    ):
        raise ValueError("reversed bounds")
    for bound, operator in (("min", lambda a, b: a < b), ("max", lambda a, b: a > b)):
        if (
            values["value"] is not None
            and values[bound] is not None
            and operator(values["value"], values[bound])
        ):
            raise ValueError("point lies outside bounds")
    if values["temperature_k"] is not None and values["temperature_k"] <= 0:
        raise ValueError("temperature must be positive")
    for key in ("value", "min", "max"):
        value = values[key]
        if value is not None:
            if row["property"] == "poisson_ratio":
                if not -1 < value < Fraction(1, 2):
                    raise ValueError("invalid isotropic Poisson ratio")
            elif value <= 0:
                raise ValueError("physical property must be positive")
    return values


def build(output=ROOT / "elements.db", source_dir=ROOT / "sources/elements"):
    paths = sorted(Path(source_dir).glob("*.json"))
    if not paths:
        raise ValueError("no elemental source documents")
    documents = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=output.parent, suffix=".db", delete=False
    ) as file:
        temporary = Path(file.name)
    try:
        with closing(sqlite3.connect(temporary)) as db:
            db.executescript(SCHEMA)
            with db:
                db.execute(
                    "INSERT INTO unverified_element_metadata VALUES ('review_status','pending_human_review')"
                )
                for path in paths:
                    db.execute(
                        "INSERT INTO unverified_element_metadata VALUES (?,?)",
                        (
                            "input_sha256:" + path.name,
                            hashlib.sha256(path.read_bytes()).hexdigest(),
                        ),
                    )
                for doc in documents:
                    for source in doc.get("sources", []):
                        fields = (
                            "id",
                            "title",
                            "url",
                            "version",
                            "retrieved_at",
                            "license_note",
                        )
                        if any(
                            not isinstance(source.get(key), str)
                            or not source[key].strip()
                            for key in fields
                        ):
                            raise ValueError(
                                "source requires citation, version, retrieval and license determination"
                            )
                        if not source["url"].startswith("https://"):
                            raise ValueError("source URL must use HTTPS")
                        db.execute(
                            "INSERT INTO unverified_element_source VALUES (?,?,?,?,?,?)",
                            tuple(source[key] for key in fields),
                        )
                for doc in documents:
                    for row in doc.get("observations", []):
                        values = validate_observation(row)
                        numbers = []
                        for value in values.values():
                            numbers.extend(
                                (None, None)
                                if value is None
                                else (value.numerator, value.denominator)
                            )
                        db.execute(
                            "INSERT INTO unverified_element_observation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                row["id"],
                                row["element"],
                                row["property"],
                                row["unit"],
                                *numbers,
                                row.get("phase"),
                                row.get("state"),
                                row.get("method"),
                                row["source_id"],
                                row["source_locator"],
                                row["provenance_class"],
                                row.get("note") or "",
                                row["review_status"],
                                json.dumps(row, sort_keys=True, separators=(",", ":")),
                            ),
                        )
                    for gap in doc.get("gaps", []):
                        if (
                            gap["element"] not in ELEMENTS
                            or gap["property"] not in {*UNITS, "fit_ready_evidence"}
                            or not gap["reason"]
                        ):
                            raise ValueError("invalid gap record")
                        db.execute(
                            "INSERT OR IGNORE INTO unverified_element_gap VALUES (?,?,?)",
                            (gap["element"], gap["property"], gap["reason"]),
                        )
                if db.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("invalid source reference")
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("element database integrity check failed")
            counts = dict(
                db.execute(
                    "SELECT property,count(*) FROM unverified_element_observation GROUP BY property"
                )
            )
        os.replace(temporary, output)
        output.with_suffix(output.suffix + ".sha256").write_text(
            hashlib.sha256(output.read_bytes()).hexdigest() + "  " + output.name + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "artifact": str(output),
                    "observations": sum(counts.values()),
                    "properties": counts,
                },
                indent=2,
            )
        )
        return counts
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "elements.db")
    parser.add_argument("--source-dir", type=Path, default=ROOT / "sources/elements")
    args = parser.parse_args()
    build(args.output, args.source_dir)
