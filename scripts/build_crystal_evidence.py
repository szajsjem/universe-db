#!/usr/bin/env python3
"""Build exact, sourced crystallographic research records without core promotion."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
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
PARAMETERS = {
    "a": "angstrom",
    "b": "angstrom",
    "c": "angstrom",
    "alpha": "deg",
    "beta": "deg",
    "gamma": "deg",
}
SYSTEMS = {
    "triclinic",
    "monoclinic",
    "orthorhombic",
    "tetragonal",
    "trigonal",
    "hexagonal",
    "cubic",
}
SCHEMA = """
PRAGMA foreign_keys=ON;
PRAGMA user_version=1;
CREATE TABLE unverified_crystal_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) STRICT;
CREATE TABLE unverified_crystal_source(
 source_id TEXT PRIMARY KEY,title TEXT NOT NULL,url TEXT NOT NULL,version TEXT NOT NULL,
 retrieved_at TEXT NOT NULL,license_note TEXT NOT NULL,input_json TEXT NOT NULL) STRICT;
CREATE TABLE unverified_crystal_structure(
 structure_id TEXT PRIMARY KEY,name TEXT NOT NULL,formula TEXT NOT NULL,phase TEXT,
 crystal_system TEXT,space_group_number INTEGER CHECK(space_group_number BETWEEN 1 AND 230),
 space_group_symbol TEXT,cell_convention TEXT,site_convention TEXT
 CHECK(site_convention IN ('asymmetric_unit','full_cell') OR site_convention IS NULL),
 cell_formula_units INTEGER CHECK(cell_formula_units>0),
 temperature_k_numerator INTEGER,temperature_k_denominator INTEGER,
 pressure_pa_numerator INTEGER,pressure_pa_denominator INTEGER,
 source_id TEXT NOT NULL REFERENCES unverified_crystal_source,source_locator TEXT NOT NULL,
 method TEXT,provenance_class TEXT NOT NULL CHECK(provenance_class IN ('measured','curated','modeled')),
 kind TEXT NOT NULL CHECK(kind IN ('experimental','evaluated_reference','ideal_prototype','computed')),
 review_status TEXT NOT NULL CHECK(review_status='pending_human_review'),note TEXT NOT NULL,input_json TEXT NOT NULL,
 CHECK((temperature_k_numerator IS NULL)=(temperature_k_denominator IS NULL)),
 CHECK(temperature_k_denominator IS NULL OR temperature_k_denominator>0),
 CHECK((pressure_pa_numerator IS NULL)=(pressure_pa_denominator IS NULL)),
 CHECK(pressure_pa_denominator IS NULL OR pressure_pa_denominator>0)) STRICT;
CREATE TABLE unverified_crystal_lattice_parameter(
 structure_id TEXT NOT NULL REFERENCES unverified_crystal_structure,
 parameter TEXT NOT NULL CHECK(parameter IN ('a','b','c','alpha','beta','gamma')),
 value_numerator INTEGER NOT NULL,value_denominator INTEGER NOT NULL CHECK(value_denominator>0),
 unit TEXT NOT NULL,uncertainty_numerator INTEGER,uncertainty_denominator INTEGER,
 PRIMARY KEY(structure_id,parameter),
 CHECK((uncertainty_numerator IS NULL)=(uncertainty_denominator IS NULL)),
 CHECK(uncertainty_denominator IS NULL OR uncertainty_denominator>0)) STRICT;
CREATE TABLE unverified_crystal_site(
 structure_id TEXT NOT NULL REFERENCES unverified_crystal_structure,position INTEGER NOT NULL,
 label TEXT NOT NULL,element TEXT NOT NULL,isotope_mass_number INTEGER,
 x_numerator INTEGER NOT NULL,x_denominator INTEGER NOT NULL CHECK(x_denominator>0),
 y_numerator INTEGER NOT NULL,y_denominator INTEGER NOT NULL CHECK(y_denominator>0),
 z_numerator INTEGER NOT NULL,z_denominator INTEGER NOT NULL CHECK(z_denominator>0),
 occupancy_numerator INTEGER,occupancy_denominator INTEGER,
 multiplicity INTEGER CHECK(multiplicity>0),wyckoff TEXT,input_json TEXT NOT NULL,
 PRIMARY KEY(structure_id,position),
 CHECK((occupancy_numerator IS NULL)=(occupancy_denominator IS NULL)),
 CHECK(occupancy_denominator IS NULL OR occupancy_denominator>0)) STRICT;
CREATE TABLE unverified_crystal_gap(
 position INTEGER PRIMARY KEY,source_document TEXT NOT NULL,input_json TEXT NOT NULL) STRICT;
CREATE INDEX unverified_crystal_formula ON unverified_crystal_structure(formula);
"""


def number(value):
    if value is None:
        return None
    if type(value) not in (str, int):
        raise ValueError("crystal numbers must be exact strings or integers")
    return Fraction(value)


def pair(value):
    return (None, None) if value is None else (value.numerator, value.denominator)


def validate_structure(row):
    for key in ("id", "name", "formula", "source_id", "source_locator"):
        if not isinstance(row.get(key), str) or not row[key].strip():
            raise ValueError("missing crystal " + key)
    if row.get("review_status") != "pending_human_review":
        raise ValueError("research structure cannot be automatically promoted")
    if row.get("crystal_system") is not None and row["crystal_system"] not in SYSTEMS:
        raise ValueError("unknown crystal system")
    if row.get("kind") not in (
        "experimental",
        "evaluated_reference",
        "ideal_prototype",
        "computed",
    ):
        raise ValueError("explicit structure evidence kind required")
    if row.get("provenance_class") not in ("measured", "curated", "modeled"):
        raise ValueError("invalid crystal provenance")
    if (
        row["kind"] in ("computed", "ideal_prototype")
        and row["provenance_class"] == "measured"
    ):
        raise ValueError("ideal/computed structures are not measurements")
    group = row.get("space_group_number")
    if group is not None and (type(group) is not int or not 1 <= group <= 230):
        raise ValueError("space-group number outside 1..230")
    if group is not None and row.get("crystal_system") is not None:
        expected_system = next(
            system
            for system, low, high in (
                ("triclinic", 1, 2),
                ("monoclinic", 3, 15),
                ("orthorhombic", 16, 74),
                ("tetragonal", 75, 142),
                ("trigonal", 143, 167),
                ("hexagonal", 168, 194),
                ("cubic", 195, 230),
            )
            if low <= group <= high
        )
        if row["crystal_system"] != expected_system:
            raise ValueError("space group and crystal system disagree")
    formula_units = row.get("cell_formula_units")
    if formula_units is not None and (
        type(formula_units) is not int or formula_units <= 0
    ):
        raise ValueError("cell formula units must be a positive integer")
    if row.get("sites") and row.get("site_convention") not in (
        "asymmetric_unit",
        "full_cell",
    ):
        raise ValueError("sites require an explicit convention")
    temperature = number(row.get("temperature_k"))
    pressure = number(row.get("pressure_pa"))
    if (
        temperature is not None
        and temperature <= 0
        or pressure is not None
        and pressure < 0
    ):
        raise ValueError("invalid crystal conditions")
    lattice = {}
    for key, item in row.get("lattice_parameters", {}).items():
        if key not in PARAMETERS or item.get("unit") != PARAMETERS[key]:
            raise ValueError("invalid lattice parameter/unit")
        value = number(item["value"])
        uncertainty = number(item.get("uncertainty"))
        if (
            value is None
            or value <= 0
            or key in ("alpha", "beta", "gamma")
            and value >= 180
        ):
            raise ValueError("invalid lattice metric")
        if uncertainty is not None and uncertainty < 0:
            raise ValueError("negative lattice uncertainty")
        lattice[key] = value
    if all(key in lattice for key in PARAMETERS):
        ca, cb, cg = [
            math.cos(math.radians(float(lattice[key])))
            for key in ("alpha", "beta", "gamma")
        ]
        if 1 - ca * ca - cb * cb - cg * cg + 2 * ca * cb * cg <= 1e-12:
            raise ValueError("degenerate lattice geometry")
    for site in row.get("sites", []):
        if site.get("element") not in ELEMENTS or not site.get("label"):
            raise ValueError("invalid site element/label")
        if any(number(site.get(key)) is None for key in ("x", "y", "z")):
            raise ValueError("site coordinates required")
        occupancy = number(site.get("occupancy"))
        if occupancy is not None and not 0 <= occupancy <= 1:
            raise ValueError("site occupancy outside [0,1]")
        for key in ("multiplicity", "isotope_mass_number"):
            if site.get(key) is not None and (
                type(site[key]) is not int or site[key] <= 0
            ):
                raise ValueError("invalid site " + key)
    return temperature, pressure


def build(output=ROOT / "crystals.db", source_dir=ROOT / "sources/crystals"):
    paths = sorted(Path(source_dir).glob("*.json"))
    documents = [(path, json.loads(path.read_text(encoding="utf-8"))) for path in paths]
    if not documents or not any(doc.get("structures") for _, doc in documents):
        raise ValueError("no crystallographic evidence documents")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=output.parent, suffix=".db", delete=False
    ) as file:
        staged = Path(file.name)
    try:
        with closing(sqlite3.connect(staged)) as db:
            db.executescript(SCHEMA)
            with db:
                db.execute(
                    "INSERT INTO unverified_crystal_metadata VALUES ('review_status','pending_human_review')"
                )
                for path, doc in documents:
                    db.execute(
                        "INSERT INTO unverified_crystal_metadata VALUES (?,?)",
                        (
                            "input_sha256:" + path.name,
                            hashlib.sha256(path.read_bytes()).hexdigest(),
                        ),
                    )
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
                                "crystal source requires citation/version/retrieval/license determination"
                            )
                        raw_path = source.get("source_file") or source.get("raw_file")
                        if raw_path is not None:
                            raw_path = ROOT / raw_path
                            if (
                                not source.get("sha256")
                                or hashlib.sha256(raw_path.read_bytes()).hexdigest()
                                != source["sha256"]
                            ):
                                raise ValueError("crystal source file digest mismatch")
                        db.execute(
                            "INSERT INTO unverified_crystal_source VALUES (?,?,?,?,?,?,?)",
                            (
                                *[source[key] for key in fields],
                                json.dumps(source, sort_keys=True),
                            ),
                        )
                for path, doc in documents:
                    for row in doc.get("structures", []):
                        temperature, pressure = validate_structure(row)
                        db.execute(
                            "INSERT INTO unverified_crystal_structure VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                row["id"],
                                row["name"],
                                row["formula"],
                                row.get("phase"),
                                row.get("crystal_system"),
                                row.get("space_group_number"),
                                row.get("space_group_symbol"),
                                row.get("cell_convention"),
                                row.get("site_convention"),
                                row.get("cell_formula_units"),
                                *pair(temperature),
                                *pair(pressure),
                                row["source_id"],
                                row["source_locator"],
                                row.get("method"),
                                row["provenance_class"],
                                row["kind"],
                                row["review_status"],
                                row.get("note") or "",
                                json.dumps(row, sort_keys=True),
                            ),
                        )
                        for key, item in row.get("lattice_parameters", {}).items():
                            db.execute(
                                "INSERT INTO unverified_crystal_lattice_parameter VALUES (?,?,?,?,?,?,?)",
                                (
                                    row["id"],
                                    key,
                                    *pair(number(item["value"])),
                                    item["unit"],
                                    *pair(number(item.get("uncertainty"))),
                                ),
                            )
                        for i, site in enumerate(row.get("sites", [])):
                            db.execute(
                                "INSERT INTO unverified_crystal_site VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (
                                    row["id"],
                                    i,
                                    site["label"],
                                    site["element"],
                                    site.get("isotope_mass_number"),
                                    *pair(number(site["x"])),
                                    *pair(number(site["y"])),
                                    *pair(number(site["z"])),
                                    *pair(number(site.get("occupancy"))),
                                    site.get("multiplicity"),
                                    site.get("wyckoff"),
                                    json.dumps(site, sort_keys=True),
                                ),
                            )
                    for gap in doc.get("gaps", []):
                        db.execute(
                            "INSERT INTO unverified_crystal_gap(source_document,input_json) VALUES (?,?)",
                            (path.name, json.dumps(gap, sort_keys=True)),
                        )
                if db.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("crystal source foreign key check failed")
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("crystal integrity check failed")
            counts = {
                table: db.execute(
                    "SELECT count(*) FROM unverified_crystal_" + table
                ).fetchone()[0]
                for table in ("source", "structure", "lattice_parameter", "site", "gap")
            }
        os.replace(staged, output)
        output.with_suffix(output.suffix + ".sha256").write_text(
            hashlib.sha256(output.read_bytes()).hexdigest() + "  " + output.name + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"artifact": str(output), **counts}, indent=2))
        return counts
    finally:
        staged.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "crystals.db")
    parser.add_argument("--source-dir", type=Path, default=ROOT / "sources/crystals")
    args = parser.parse_args()
    build(args.output, args.source_dir)
