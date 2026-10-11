#!/usr/bin/env python3
"""Build full evaluated isotope research references, preserving review boundaries."""

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
    from .fit_isotope_properties import coordinates
    from .import_isotope_ame import load_records as load_ame
    from .import_isotope_nist import load_records as load_nist
    from .import_isotope_nubase import load_records as load_nubase
else:
    from fit_isotope_properties import coordinates
    from import_isotope_ame import load_records as load_ame
    from import_isotope_nist import load_records as load_nist
    from import_isotope_nubase import load_records as load_nubase

ROOT = Path(__file__).resolve().parents[1]
UNITS = {
    "atomic_mass": "u",
    "mass_excess": "keV",
    "binding_energy_per_nucleon": "keV",
    "isotopic_abundance": "1",
    "half_life": "s",
    "stability": "1",
    "spin_parity": "hbar",
    "decay_modes": "1",
    "excitation_energy": "keV",
}
SCHEMA = """
PRAGMA foreign_keys=ON;
PRAGMA user_version=1;
CREATE TABLE unverified_isotope_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) STRICT;
CREATE TABLE unverified_isotope_source(
 source_id TEXT PRIMARY KEY,title TEXT NOT NULL,url TEXT NOT NULL,version TEXT NOT NULL,
 retrieved_at TEXT NOT NULL,license_note TEXT NOT NULL,input_json TEXT NOT NULL) STRICT;
CREATE TABLE unverified_isotope_nuclide(
 z INTEGER NOT NULL CHECK(z>=0),a INTEGER NOT NULL CHECK(a>=1 AND a>=z),
 isomer INTEGER NOT NULL CHECK(isomer>=0),PRIMARY KEY(z,a,isomer)) STRICT;
CREATE TABLE unverified_isotope_identity(
 source_id TEXT NOT NULL REFERENCES unverified_isotope_source,
 z INTEGER NOT NULL,a INTEGER NOT NULL,isomer INTEGER NOT NULL,
 label TEXT NOT NULL,source_locator TEXT NOT NULL,note TEXT NOT NULL,input_json TEXT NOT NULL,
 PRIMARY KEY(source_id,z,a,isomer),
 FOREIGN KEY(z,a,isomer) REFERENCES unverified_isotope_nuclide) STRICT;
CREATE TABLE unverified_isotope_observation(
 observation_id TEXT PRIMARY KEY,z INTEGER NOT NULL,a INTEGER NOT NULL,isomer INTEGER NOT NULL,
 property TEXT NOT NULL,unit TEXT NOT NULL,
 value_numerator TEXT,value_denominator TEXT,uncertainty_numerator TEXT,uncertainty_denominator TEXT,
 text_value TEXT,estimated INTEGER NOT NULL CHECK(estimated IN (0,1)),
 value_kind TEXT NOT NULL CHECK(value_kind IN ('point','bound','text')),
 provenance_class TEXT NOT NULL CHECK(provenance_class='curated'),
 source_id TEXT NOT NULL REFERENCES unverified_isotope_source,source_locator TEXT NOT NULL,
 method TEXT NOT NULL,note TEXT NOT NULL,input_json TEXT NOT NULL,
 review_status TEXT NOT NULL CHECK(review_status='pending_human_review'),
 FOREIGN KEY(z,a,isomer) REFERENCES unverified_isotope_nuclide,
 CHECK((value_numerator IS NULL)=(value_denominator IS NULL)),
 CHECK((uncertainty_numerator IS NULL)=(uncertainty_denominator IS NULL))) STRICT;
CREATE TABLE unverified_isotope_gap(
 gap_id INTEGER PRIMARY KEY,source_id TEXT NOT NULL REFERENCES unverified_isotope_source,
 z INTEGER NOT NULL,a INTEGER NOT NULL,isomer INTEGER NOT NULL,
 property TEXT NOT NULL,reason TEXT NOT NULL,input_json TEXT NOT NULL,
 FOREIGN KEY(z,a,isomer) REFERENCES unverified_isotope_nuclide) STRICT;
CREATE INDEX unverified_isotope_coordinate_property
 ON unverified_isotope_observation(z,a,isomer,property);
"""


def ratio(value):
    if value is None:
        return None, None
    if type(value) not in (str, int):
        raise ValueError("isotope numbers must be exact strings or integers")
    number = Fraction(value)
    # Decimal-encoded integer ratios avoid SQLite's 64-bit limit for long lives.
    return str(number.numerator), str(number.denominator)


def build(output=ROOT / "isotopes.db", documents=None):
    documents = (
        documents if documents is not None else [load_nist(), load_ame(), load_nubase()]
    )
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
                    "INSERT INTO unverified_isotope_metadata VALUES ('review_status','pending_human_review')"
                )
                db.execute(
                    "INSERT INTO unverified_isotope_metadata VALUES ('ratio_encoding','decimal integer strings; exact arbitrary-precision numerator/denominator')"
                )
                for doc in documents:
                    for source in doc["sources"]:
                        fields = (
                            "id",
                            "title",
                            "url",
                            "version",
                            "retrieved_at",
                            "license_note",
                        )
                        if any(
                            not isinstance(source.get(field), str)
                            or not source[field].strip()
                            for field in fields
                        ):
                            raise ValueError(
                                "source citation, version, retrieval and license determination required"
                            )
                        db.execute(
                            "INSERT INTO unverified_isotope_source VALUES (?,?,?,?,?,?,?)",
                            (
                                *[source[field] for field in fields],
                                json.dumps(source, sort_keys=True),
                            ),
                        )
                    for nuclide in doc["nuclides"]:
                        z, a, _ = coordinates(
                            nuclide["z"], nuclide["a"], nuclide["isomer"]
                        )
                        key = (z, a, nuclide["isomer"])
                        db.execute(
                            "INSERT OR IGNORE INTO unverified_isotope_nuclide VALUES (?,?,?)",
                            key,
                        )
                        db.execute(
                            "INSERT INTO unverified_isotope_identity VALUES (?,?,?,?,?,?,?,?)",
                            (
                                nuclide["source_id"],
                                *key,
                                nuclide["label"],
                                nuclide["source_locator"],
                                nuclide.get("note") or "",
                                json.dumps(nuclide, sort_keys=True),
                            ),
                        )
                for doc in documents:
                    for row in doc["observations"]:
                        coordinates(row["z"], row["a"], row["isomer"])
                        if (
                            row["property"] not in UNITS
                            or row["unit"] != UNITS[row["property"]]
                        ):
                            raise ValueError("invalid isotope property/unit pair")
                        if (
                            type(row["estimated"]) is not bool
                            or row["provenance_class"] != "curated"
                        ):
                            raise ValueError(
                                "evaluated provenance and explicit estimate flag required"
                            )
                        value = ratio(row.get("value"))
                        uncertainty = ratio(row.get("uncertainty"))
                        kind = row.get(
                            "value_kind",
                            "point" if row.get("value") is not None else "text",
                        )
                        if kind == "point" and row.get("value") is None:
                            raise ValueError("point observation requires a number")
                        if kind != "point" and not row.get("text_value"):
                            raise ValueError(
                                "bound/text observation requires original text"
                            )
                        if (
                            row["property"] in ("atomic_mass", "half_life")
                            and row.get("value") is not None
                            and Fraction(row["value"]) <= 0
                        ):
                            raise ValueError(
                                "mass and finite half-life must be positive"
                            )
                        if (
                            row["property"] == "isotopic_abundance"
                            and not 0 <= Fraction(row["value"]) <= 1
                        ):
                            raise ValueError("abundance outside [0,1]")
                        if (
                            row.get("uncertainty") is not None
                            and Fraction(row["uncertainty"]) < 0
                        ):
                            raise ValueError("negative uncertainty")
                        db.execute(
                            "INSERT INTO unverified_isotope_observation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                row["id"],
                                row["z"],
                                row["a"],
                                row["isomer"],
                                row["property"],
                                row["unit"],
                                *value,
                                *uncertainty,
                                row.get("text_value"),
                                int(row["estimated"]),
                                kind,
                                row["provenance_class"],
                                row["source_id"],
                                row["source_locator"],
                                row["method"],
                                row.get("note") or "",
                                json.dumps(row, sort_keys=True),
                                "pending_human_review",
                            ),
                        )
                    for row in doc.get("gaps", []):
                        db.execute(
                            "INSERT INTO unverified_isotope_gap(source_id,z,a,isomer,property,reason,input_json) VALUES (?,?,?,?,?,?,?)",
                            (
                                row["source_id"],
                                row["z"],
                                row["a"],
                                row["isomer"],
                                row["property"],
                                row["reason"],
                                json.dumps(row, sort_keys=True),
                            ),
                        )
                if db.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("isotope foreign key validation failed")
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("isotope integrity validation failed")
            counts = dict(
                db.execute(
                    "SELECT property,count(*) FROM unverified_isotope_observation GROUP BY property"
                )
            )
            identities = db.execute(
                "SELECT count(*) FROM unverified_isotope_nuclide"
            ).fetchone()[0]
        os.replace(staged, output)
        output.with_suffix(output.suffix + ".sha256").write_text(
            hashlib.sha256(output.read_bytes()).hexdigest() + "  " + output.name + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "artifact": str(output),
                    "states": identities,
                    "observations": sum(counts.values()),
                    "properties": counts,
                },
                indent=2,
            )
        )
        return counts
    finally:
        staged.unlink(missing_ok=True)


def load_training_masses(database=ROOT / "isotopes.db", source_id="amdc-ame2020"):
    """Select ONE evaluation to avoid duplicate/vintage leakage in validation."""
    with closing(
        sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)
    ) as db:
        db.row_factory = sqlite3.Row
        records = []
        for row in db.execute(
            "SELECT o.*,s.url,s.input_json AS source_json FROM unverified_isotope_observation o JOIN unverified_isotope_source s USING(source_id) WHERE property='atomic_mass' AND source_id=? ORDER BY z,a,isomer",
            (source_id,),
        ):
            record = json.loads(row["input_json"])
            record.update(
                source=row["url"],
                review_status=row["review_status"],
                source_metadata=json.loads(row["source_json"]),
            )
            records.append(record)
        if not records:
            raise ValueError("selected mass evaluation has no atomic masses")
        return records


def audit(database=ROOT / "isotopes.db", core=ROOT / "universe.db"):
    with (
        closing(sqlite3.connect(database)) as db,
        closing(sqlite3.connect(core)) as reviewed,
    ):
        core_states = reviewed.execute("SELECT count(*) FROM nuclide").fetchone()[0]
        core_stats = dict(
            reviewed.execute(
                "SELECT o.property_id,count(*) FROM observation o JOIN nuclide n ON n.entity_id=o.subject_entity_id GROUP BY property_id"
            )
        )
        properties = dict(
            db.execute(
                "SELECT property,count(*) FROM unverified_isotope_observation GROUP BY property"
            )
        )
        ground_missing = {}
        missing = {}
        for prop in ("atomic_mass", "half_life", "spin_parity", "decay_modes"):
            missing[prop] = db.execute(
                "SELECT count(*) FROM unverified_isotope_nuclide n WHERE NOT EXISTS (SELECT 1 FROM unverified_isotope_observation o WHERE o.z=n.z AND o.a=n.a AND o.isomer=n.isomer AND (o.property=? OR (?='half_life' AND o.property='stability' AND o.text_value='stable')))",
                (prop, prop),
            ).fetchone()[0]
            ground_missing[prop] = db.execute(
                "SELECT count(*) FROM unverified_isotope_nuclide n WHERE isomer=0 AND NOT EXISTS (SELECT 1 FROM unverified_isotope_observation o WHERE o.z=n.z AND o.a=n.a AND o.isomer=n.isomer AND (o.property=? OR (?='half_life' AND o.property='stability' AND o.text_value='stable')))",
                (prop, prop),
            ).fetchone()[0]
        return {
            "core_states": core_states,
            "core_observation_counts": core_stats,
            "research_states": db.execute(
                "SELECT count(*) FROM unverified_isotope_nuclide"
            ).fetchone()[0],
            "research_properties": properties,
            "research_states_without_property": missing,
            "ground_states_without_property": ground_missing,
            "states_without_atomic_mass_or_mass_excess": db.execute(
                "SELECT count(*) FROM unverified_isotope_nuclide n WHERE NOT EXISTS (SELECT 1 FROM unverified_isotope_observation o WHERE o.z=n.z AND o.a=n.a AND o.isomer=n.isomer AND o.property IN ('atomic_mass','mass_excess'))"
            ).fetchone()[0],
            "source_state_index_note": "NUBASE indices identify isomers and other levels/assignments; they are not all observed long-lived isomers",
            "estimated_atomic_mass_records": db.execute(
                "SELECT count(*) FROM unverified_isotope_observation WHERE property='atomic_mass' AND estimated=1"
            ).fetchone()[0],
            "review_status": "pending_human_review",
            "database_sha256": hashlib.sha256(Path(database).read_bytes()).hexdigest(),
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "isotopes.db")
    parser.add_argument(
        "--audit-output", type=Path, default=ROOT / ".build/isotope-evidence-audit.json"
    )
    args = parser.parse_args()
    build(args.output)
    report = audit(args.output)
    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    args.audit_output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
