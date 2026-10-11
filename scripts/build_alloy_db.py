#!/usr/bin/env python3
"""Build the separate sourced alloy research reference from authored JSON."""

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

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = {
    "iron-carbon",
    "copper",
    "gold",
    "silver",
    "aluminum",
    "magnesium",
    "titanium",
    "nickel",
}
ELEMENTS = set(
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og".split()
)
PROPERTY_UNITS = {
    "density": "g/cm3",
    "melting_range": "degC",
    "tensile_strength": "MPa",
    "yield_strength_0_2": "MPa",
    "elongation": "%",
    "vickers_hardness": "HV",
    "thermal_conductivity": "W/(m*K)",
    "specific_heat_capacity": "J/(g*K)",
    "electrical_resistivity": "microohm*m",
    "youngs_modulus": "GPa",
    "shear_modulus": "GPa",
    "poisson_ratio": "1",
}

SCHEMA = """
PRAGMA foreign_keys=ON;
PRAGMA user_version=2;
CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) STRICT;
CREATE TABLE source(
 source_id TEXT PRIMARY KEY,title TEXT NOT NULL,url TEXT NOT NULL,
 publisher TEXT NOT NULL,retrieved_at TEXT NOT NULL,version TEXT NOT NULL,
 license_note TEXT NOT NULL) STRICT;
CREATE TABLE alloy(
 alloy_id TEXT PRIMARY KEY,name TEXT NOT NULL,family TEXT NOT NULL,
 base_element TEXT NOT NULL,designation TEXT NOT NULL,description TEXT NOT NULL,
 provenance_class TEXT NOT NULL DEFAULT 'curated' CHECK(provenance_class='curated'),
 review_status TEXT NOT NULL DEFAULT 'pending_human_review'
 CHECK(review_status='pending_human_review')) STRICT;
CREATE TABLE alloy_source(
 alloy_id TEXT NOT NULL REFERENCES alloy,source_id TEXT NOT NULL REFERENCES source,
 PRIMARY KEY(alloy_id,source_id)) STRICT;
CREATE TABLE application(
 alloy_id TEXT NOT NULL REFERENCES alloy,position INTEGER NOT NULL,value TEXT NOT NULL,
 PRIMARY KEY(alloy_id,position)) STRICT;
CREATE TABLE note(
 alloy_id TEXT NOT NULL REFERENCES alloy,position INTEGER NOT NULL,value TEXT NOT NULL,
 PRIMARY KEY(alloy_id,position)) STRICT;
CREATE TABLE composition(
 alloy_id TEXT NOT NULL REFERENCES alloy,element TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('specified','balance','unspecified')),
 min_numerator INTEGER,min_denominator INTEGER,
 max_numerator INTEGER,max_denominator INTEGER,
 nominal_numerator INTEGER,nominal_denominator INTEGER,
 source_id TEXT NOT NULL REFERENCES source,note TEXT NOT NULL,
 PRIMARY KEY(alloy_id,element),
 CHECK((min_numerator IS NULL)=(min_denominator IS NULL)),
 CHECK((max_numerator IS NULL)=(max_denominator IS NULL)),
 CHECK((nominal_numerator IS NULL)=(nominal_denominator IS NULL)),
 CHECK(min_denominator IS NULL OR min_denominator>0),
 CHECK(max_denominator IS NULL OR max_denominator>0),
 CHECK(nominal_denominator IS NULL OR nominal_denominator>0)) STRICT;
CREATE VIEW composition_wt_percent AS
 SELECT alloy_id,element,role,
 1.0*min_numerator/min_denominator AS min_wt_pct,
 1.0*max_numerator/max_denominator AS max_wt_pct,
 1.0*nominal_numerator/nominal_denominator AS nominal_wt_pct,
 source_id,note FROM composition;
CREATE VIEW alloy_summary AS
 SELECT a.*,group_concat(DISTINCT c.element) AS elements
 FROM alloy a LEFT JOIN composition c USING(alloy_id) GROUP BY alloy_id;
CREATE TABLE property_observation(
 observation_id TEXT PRIMARY KEY,alloy_id TEXT NOT NULL REFERENCES alloy,
 property TEXT NOT NULL,unit TEXT NOT NULL,
 value_numerator INTEGER,value_denominator INTEGER,
 min_numerator INTEGER,min_denominator INTEGER,
 max_numerator INTEGER,max_denominator INTEGER,
 uncertainty_numerator INTEGER,uncertainty_denominator INTEGER,
 temperature_c_numerator INTEGER,temperature_c_denominator INTEGER,
 condition TEXT NOT NULL,method TEXT NOT NULL,
 source_id TEXT NOT NULL REFERENCES source,source_locator TEXT NOT NULL,
 note TEXT NOT NULL,value_kind TEXT NOT NULL
 CHECK(value_kind IN ('typical','minimum','maximum','range')),
 provenance_class TEXT NOT NULL DEFAULT 'curated' CHECK(provenance_class='curated'),
 review_status TEXT NOT NULL DEFAULT 'pending_human_review'
 CHECK(review_status='pending_human_review'),
 CHECK((value_numerator IS NULL)=(value_denominator IS NULL)),
 CHECK((min_numerator IS NULL)=(min_denominator IS NULL)),
 CHECK((max_numerator IS NULL)=(max_denominator IS NULL)),
 CHECK((uncertainty_numerator IS NULL)=(uncertainty_denominator IS NULL)),
 CHECK((temperature_c_numerator IS NULL)=(temperature_c_denominator IS NULL)),
 CHECK(value_denominator IS NULL OR value_denominator>0),
 CHECK(min_denominator IS NULL OR min_denominator>0),
 CHECK(max_denominator IS NULL OR max_denominator>0),
 CHECK(uncertainty_denominator IS NULL OR uncertainty_denominator>0),
 CHECK(temperature_c_denominator IS NULL OR temperature_c_denominator>0)
) STRICT;
CREATE VIEW property_values AS
 SELECT observation_id,alloy_id,property,unit,
 1.0*value_numerator/value_denominator AS value,
 1.0*min_numerator/min_denominator AS min,
 1.0*max_numerator/max_denominator AS max,
 1.0*uncertainty_numerator/uncertainty_denominator AS uncertainty,
 1.0*temperature_c_numerator/temperature_c_denominator AS temperature_c,
 condition,method,source_id,source_locator,note,value_kind,
 provenance_class,review_status FROM property_observation;
"""


def exact_number(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("property numbers must be exact decimal strings")
    result = Fraction(value)
    if not -(2**63) <= result.numerator < 2**63 or result.denominator >= 2**63:
        raise ValueError("number exceeds SQLite integer representation")
    return result


def validate_property(row):
    if PROPERTY_UNITS.get(row["property"]) != row["unit"]:
        raise ValueError("property/unit dimension mismatch")
    values = {
        key: exact_number(row.get(key))
        for key in ("value", "min", "max", "uncertainty", "temperature_c")
    }
    if not any(values[key] is not None for key in ("value", "min", "max")):
        raise ValueError("property observation has no value or bounds")
    lo, hi, value = (values[key] for key in ("min", "max", "value"))
    if lo is not None and hi is not None and lo > hi:
        raise ValueError("reversed property interval")
    if value is not None and (
        (lo is not None and value < lo) or (hi is not None and value > hi)
    ):
        raise ValueError("value outside property interval")
    uncertainty = values["uncertainty"]
    if uncertainty is not None and (uncertainty < 0 or value is None):
        raise ValueError("uncertainty needs a central value and must be nonnegative")
    if values["temperature_c"] is not None and values["temperature_c"] < Fraction(
        "-273.15"
    ):
        raise ValueError("temperature below absolute zero")
    for key in ("condition", "method", "source_locator", "source_id"):
        if not row.get(key) or not row[key].strip():
            raise ValueError(f"missing property context: {key}")
    if row["value_kind"] == "range" and (lo is None or hi is None):
        raise ValueError("range requires two bounds")
    if row["value_kind"] == "minimum" and lo is None:
        raise ValueError("minimum requires a lower bound")
    if row["value_kind"] == "maximum" and hi is None:
        raise ValueError("maximum requires an upper bound")
    if row["property"] not in {"melting_range", "poisson_ratio"}:
        for number in (lo, hi, value):
            if number is not None and number < 0:
                raise ValueError("negative material property")
    return values


def percentage(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("percentages must be exact decimal strings")
    result = Fraction(value)
    if not 0 <= result <= 100:
        raise ValueError(f"percentage outside 0..100: {value}")
    return result


def validate_alloy(alloy):
    if alloy["family"] not in FAMILIES or alloy["base_element"] not in ELEMENTS:
        raise ValueError(f"invalid family/base: {alloy['id']}")
    if not alloy["composition"] or not alloy["source_ids"]:
        raise ValueError(f"composition/sources missing: {alloy['id']}")
    minima = Fraction(0)
    balance = 0
    seen = set()
    for row in alloy["composition"]:
        element = row["element"]
        parts = element.split("+")
        if (
            any(part not in ELEMENTS for part in parts)
            or len(set(parts)) != len(parts)
            or element in seen
        ):
            raise ValueError(f"invalid/duplicate element: {alloy['id']} {element}")
        seen.add(element)
        lo, hi, nominal = [
            percentage(row.get(key))
            for key in ("min_wt_pct", "max_wt_pct", "nominal_wt_pct")
        ]
        if lo is not None and hi is not None and lo > hi:
            raise ValueError("reversed composition interval")
        if nominal is not None and (
            (lo is not None and nominal < lo) or (hi is not None and nominal > hi)
        ):
            raise ValueError("nominal value outside composition interval")
        if row["role"] == "balance":
            balance += 1
            if any(v is not None for v in (lo, hi, nominal)):
                raise ValueError("balance must not have invented numeric amounts")
        if row["source_id"] not in alloy["source_ids"]:
            raise ValueError("composition source must be attached to alloy")
        # Combined analytes can overlap separately reported elemental limits.
        if len(parts) == 1:
            minima += lo if lo is not None else (nominal or 0)
    if balance > 1 or minima > 100:
        raise ValueError(f"impossible composition: {alloy['id']}")
    if not any(alloy["base_element"] in term.split("+") for term in seen):
        raise ValueError("base element absent from composition")


def build(output: Path, source_dir: Path = ROOT / "sources/alloys"):
    files = sorted(source_dir.glob("*.json"))
    if not files:
        raise ValueError("no authored alloy source files")
    documents = [json.loads(path.read_text(encoding="utf-8-sig")) for path in files]
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix="alloys-", suffix=".db", dir=output.parent)
    os.close(handle)
    staged = Path(name)
    try:
        with closing(sqlite3.connect(staged)) as db:
            db.executescript(SCHEMA)
            with db:
                metadata = {
                    "title": "Sourced metal alloy research reference",
                    "data_status": "pending_human_review",
                    "composition_basis": "mass percent (wt%); integer ratios encode percentages",
                    "scope": "Grade chemistry, nominal recipes and source-reported engineering properties",
                    "research_method": "Hand-authored entries with model-assisted primary-source research",
                    "missing_values": "NULL is unknown or unspecified; balance is not a fixed number",
                    "source_files_sha256": json.dumps(
                        {
                            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in files
                        },
                        sort_keys=True,
                    ),
                }
                db.executemany("INSERT INTO metadata VALUES (?,?)", metadata.items())
                for doc in documents:
                    for src in doc["sources"]:
                        db.execute(
                            "INSERT INTO source VALUES (?,?,?,?,?,?,?)",
                            tuple(
                                src[k]
                                for k in (
                                    "id",
                                    "title",
                                    "url",
                                    "publisher",
                                    "retrieved_at",
                                    "version",
                                    "license_note",
                                )
                            ),
                        )
                for doc in documents:
                    for alloy in doc.get("alloys", []):
                        validate_alloy(alloy)
                        db.execute(
                            "INSERT INTO alloy(alloy_id,name,family,base_element,designation,description) VALUES (?,?,?,?,?,?)",
                            tuple(
                                alloy[k]
                                for k in (
                                    "id",
                                    "name",
                                    "family",
                                    "base_element",
                                    "designation",
                                    "description",
                                )
                            ),
                        )
                        db.executemany(
                            "INSERT INTO alloy_source VALUES (?,?)",
                            [(alloy["id"], source) for source in alloy["source_ids"]],
                        )
                        for table, key in (
                            ("application", "applications"),
                            ("note", "notes"),
                        ):
                            db.executemany(
                                f"INSERT INTO {table} VALUES (?,?,?)",
                                [
                                    (alloy["id"], i, value)
                                    for i, value in enumerate(alloy.get(key, []))
                                ],
                            )
                        for row in alloy["composition"]:
                            numbers = []
                            for key in ("min_wt_pct", "max_wt_pct", "nominal_wt_pct"):
                                number = percentage(row.get(key))
                                numbers.extend(
                                    (number.numerator, number.denominator)
                                    if number is not None
                                    else (None, None)
                                )
                            db.execute(
                                "INSERT INTO composition VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                (
                                    alloy["id"],
                                    row["element"],
                                    row["role"],
                                    *numbers,
                                    row["source_id"],
                                    row.get("note") or "",
                                ),
                            )
                for doc in documents:
                    for row in doc.get("properties", []):
                        values = validate_property(row)
                        numbers = []
                        for key in (
                            "value",
                            "min",
                            "max",
                            "uncertainty",
                            "temperature_c",
                        ):
                            value = values[key]
                            numbers.extend(
                                (value.numerator, value.denominator)
                                if value is not None
                                else (None, None)
                            )
                        db.execute(
                            "INSERT INTO property_observation(observation_id,alloy_id,property,unit,"
                            "value_numerator,value_denominator,min_numerator,min_denominator,"
                            "max_numerator,max_denominator,uncertainty_numerator,uncertainty_denominator,"
                            "temperature_c_numerator,temperature_c_denominator,condition,method,"
                            "source_id,source_locator,note,value_kind) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                row["id"],
                                row["alloy_id"],
                                row["property"],
                                row["unit"],
                                *numbers,
                                row["condition"],
                                row["method"],
                                row["source_id"],
                                row["source_locator"],
                                row.get("note") or "",
                                row["value_kind"],
                            ),
                        )
                present = {
                    row[0] for row in db.execute("SELECT DISTINCT family FROM alloy")
                }
                if present != FAMILIES:
                    raise ValueError(f"missing alloy families: {FAMILIES - present}")
                if db.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("foreign key validation failed")
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("SQLite integrity validation failed")
            counts = dict(
                db.execute("SELECT family,count(*) FROM alloy GROUP BY family")
            )
            property_count = db.execute(
                "SELECT count(*) FROM property_observation"
            ).fetchone()[0]
        os.replace(staged, output)
        checksum = hashlib.sha256(output.read_bytes()).hexdigest()
        output.with_suffix(output.suffix + ".sha256").write_text(
            f"{checksum}  {output.name}\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "artifact": str(output),
                    "alloys": sum(counts.values()),
                    "families": counts,
                    "property_observations": property_count,
                },
                indent=2,
            )
        )
        return counts
    finally:
        staged.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "alloys.db")
    args = parser.parse_args()
    build(args.output)
