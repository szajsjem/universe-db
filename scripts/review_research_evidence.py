#!/usr/bin/env python3
"""Plan elemental evidence admission; apply only explicit human review decisions."""

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
CHECKS = (
    "source",
    "license",
    "identity",
    "value",
    "units",
    "uncertainty",
    "conditions",
    "transformation",
)
SI_UNITS = {
    "density": "kg/m3",
    "specific_heat_capacity": "J/(kg*K)",
    "melting_point": "K",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def ratio(value):
    return [value.numerator, value.denominator]


def exact_number(value):
    """Accept authoritative strings/integers or explicit numerator/denominator pairs."""
    if isinstance(value, dict) and set(value) == {"numerator", "denominator"}:
        if any(
            isinstance(value[k], bool) or not isinstance(value[k], int) for k in value
        ):
            raise ValueError("rational components must be integers")
        if value["denominator"] <= 0:
            raise ValueError("rational denominator must be positive")
        return Fraction(value["numerator"], value["denominator"])
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("source numbers must be exact strings or integers")
    return Fraction(value)


def make_plan(core=ROOT / "universe.db", research=ROOT / "elements.db"):
    """Return immutable-source proposals; unsupported families/properties stay blocked."""
    result = {
        "version": 1,
        "family": "element",
        "core_sha256": digest(core),
        "research_sha256": digest(research),
        "proposals": [],
    }
    with closing(sqlite3.connect(core)) as c, closing(sqlite3.connect(research)) as r:
        c.row_factory = r.row_factory = sqlite3.Row
        entities = dict(c.execute("SELECT symbol,entity_id FROM element"))
        properties = {
            x["property_id"]: dict(x)
            for x in c.execute("SELECT * FROM property_definition")
        }
        units = {x["unit_id"]: dict(x) for x in c.execute("SELECT * FROM unit")}
        sources = {
            x["source_id"]: dict(x)
            for x in r.execute("SELECT * FROM unverified_element_source")
        }
        for item in r.execute(
            "SELECT * FROM unverified_element_observation ORDER BY observation_id"
        ):
            row = dict(item)
            raw = json.loads(row["input_json"])
            source = sources[row["source_id"]]
            reasons = []
            prop = properties.get("property:" + row["property"])
            if not prop or SI_UNITS.get(row["property"]) != row["unit"]:
                reasons.append("unsupported canonical property/unit mapping")
            if row["element"] not in entities:
                reasons.append("missing canonical element")
            if raw.get("composition_basis") != "elemental_reference":
                reasons.append(
                    "requires specimen identity rather than elemental endpoint"
                )
            if (
                row["value_numerator"] is None
                or row["min_numerator"] is not None
                or row["max_numerator"] is not None
            ):
                reasons.append(
                    "bounded evidence requires a range-aware admission extension"
                )
            if any(
                raw.get(k) is not None
                for k in (
                    "expanded_relative_uncertainty_percent",
                    "uncertainty_coverage_probability",
                )
            ):
                reasons.append(
                    "reported uncertainty requires reviewed normalization extension"
                )
            pressure = None
            if raw.get("pressure_pa") is not None:
                try:
                    pressure = exact_number(raw["pressure_pa"])
                    if pressure < 0:
                        raise ValueError("negative pressure")
                    pressure_unit = units.get("unit:pascal")
                    if (
                        not pressure_unit
                        or pressure_unit["quantity_kind"] != "pressure"
                    ):
                        raise ValueError("missing canonical pressure unit")
                except (ValueError, ZeroDivisionError):
                    reasons.append("invalid or unsupported exact pressure condition")
            if (
                not source["url"].startswith("https://")
                or "wikipedia.org" in source["url"].lower()
            ):
                reasons.append("accepted upstream source required")
            proposal = {
                "research_id": row["observation_id"],
                "source": source,
                "research_record": row,
                "blocked_reasons": reasons,
                "context": {
                    k: raw.get(k)
                    for k in (
                        "phase",
                        "state",
                        "note",
                        "composition_basis",
                        "pressure_pa",
                    )
                },
                "warnings": [
                    "No temperature assumption is made. Missing uncertainty is not zero."
                ],
            }
            if not reasons:
                unit = units[prop["canonical_unit_id"]]
                scale = (
                    Fraction(unit["si_scale_numerator"], unit["si_scale_denominator"])
                    * Fraction(10) ** unit["si_scale_power10"]
                )
                offset = Fraction(
                    unit["si_offset_numerator"], unit["si_offset_denominator"]
                )
                proposal["mapping"] = {
                    "subject_entity_id": entities[row["element"]],
                    "property_id": prop["property_id"],
                    "unit_id": unit["unit_id"],
                    "value": ratio(
                        (
                            Fraction(row["value_numerator"], row["value_denominator"])
                            - offset
                        )
                        / scale
                    ),
                }
                if pressure is not None:
                    pressure_scale = (
                        Fraction(
                            pressure_unit["si_scale_numerator"],
                            pressure_unit["si_scale_denominator"],
                        )
                        * Fraction(10) ** pressure_unit["si_scale_power10"]
                    )
                    pressure_offset = Fraction(
                        pressure_unit["si_offset_numerator"],
                        pressure_unit["si_offset_denominator"],
                    )
                    proposal["mapping"]["pressure"] = {
                        "unit_id": "unit:pascal",
                        "value": ratio((pressure - pressure_offset) / pressure_scale),
                    }
            result["proposals"].append(proposal)
    result["plan_sha256"] = hashlib.sha256(encoded(result).encode()).hexdigest()
    return result


def apply_decisions(core, research, plan, manifest, output):
    """Write a new reviewed copy atomically; never mutate either input database."""
    if Path(output).exists():
        raise ValueError("output already exists")
    current = make_plan(core, research)
    if plan != current or manifest.get("plan_sha256") != current["plan_sha256"]:
        raise ValueError("stale or modified plan/decision manifest")
    if not manifest.get("reviewer") or not manifest.get("reviewed_at"):
        raise ValueError("reviewer and reviewed_at are required")
    proposals = {p["research_id"]: p for p in current["proposals"]}
    accepted = []
    seen = set()
    for decision in manifest.get("decisions", []):
        identifier = decision.get("research_id")
        if identifier in seen or identifier not in proposals:
            raise ValueError("duplicate or unknown research ID")
        seen.add(identifier)
        if decision.get("decision") not in ("approve", "reject", "defer"):
            raise ValueError("explicit decision required")
        if decision["decision"] != "approve":
            continue
        p = proposals[identifier]
        if p["blocked_reasons"]:
            raise ValueError("blocked evidence cannot be approved")
        if any(decision.get("checks", {}).get(k) is not True for k in CHECKS):
            raise ValueError(
                "all source/license/context checks require explicit true attestations"
            )
        if decision.get("provenance_class") not in ("measured", "curated", "modeled"):
            raise ValueError("reviewed provenance class required")
        if not decision.get("rationale") or not decision.get("license_determination"):
            raise ValueError("rationale and redistribution determination required")
        accepted.append((p, decision))
    if not accepted:
        raise ValueError("no approved observations")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=output.parent, suffix=".db")
    os.close(fd)
    try:
        with (
            closing(sqlite3.connect(core)) as source_db,
            closing(sqlite3.connect(temporary)) as db,
        ):
            source_db.backup(db)
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS evidence_review (observation_id TEXT PRIMARY KEY REFERENCES observation, research_id TEXT NOT NULL, plan_sha256 TEXT NOT NULL, decision_json TEXT NOT NULL, manifest_json TEXT NOT NULL) STRICT"
                )
                for p, decision in accepted:
                    row, mapping, source = (
                        p["research_record"],
                        p["mapping"],
                        p["source"],
                    )
                    key = (
                        "admission:"
                        + hashlib.sha256(
                            (current["plan_sha256"] + p["research_id"]).encode()
                        ).hexdigest()[:24]
                    )
                    provenance = decision["provenance_class"]
                    db.execute(
                        "INSERT INTO license VALUES (?,?,?,?,?,?)",
                        (
                            key,
                            "Reviewed factual evidence determination",
                            None,
                            source["url"],
                            1,
                            decision["license_determination"],
                        ),
                    )
                    db.execute(
                        "INSERT INTO source VALUES (?,?,?,?,?,?)",
                        (
                            key,
                            source["title"],
                            source["title"] + "; " + row["source_locator"],
                            source["url"],
                            key,
                            source["retrieved_at"][:10],
                        ),
                    )
                    db.execute(
                        "INSERT INTO dataset VALUES (?,?,?,?,?,?,?)",
                        (
                            key,
                            "Reviewed elemental evidence " + p["research_id"],
                            source["version"],
                            key,
                            provenance,
                            1,
                            row["note"],
                        ),
                    )
                    db.execute(
                        "INSERT INTO condition_set VALUES (?,?)",
                        (key, encoded(p["context"])),
                    )
                    if row["temperature_k_numerator"] is not None:
                        db.execute(
                            "INSERT INTO condition_value VALUES (?,?,?,?,?)",
                            (
                                key,
                                "temperature",
                                row["temperature_k_numerator"] * 1000,
                                row["temperature_k_denominator"],
                                "unit:millikelvin",
                            ),
                        )
                    if "pressure" in mapping:
                        db.execute(
                            "INSERT INTO condition_value VALUES (?,?,?,?,?)",
                            (
                                key,
                                "pressure",
                                *mapping["pressure"]["value"],
                                mapping["pressure"]["unit_id"],
                            ),
                        )
                    db.execute(
                        "INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            key,
                            mapping["subject_entity_id"],
                            mapping["property_id"],
                            *mapping["value"],
                            mapping["unit_id"],
                            None,
                            None,
                            provenance,
                            key,
                            key,
                            key,
                            row["method"],
                            1,
                        ),
                    )
                    db.execute(
                        "INSERT INTO evidence_review VALUES (?,?,?,?,?)",
                        (
                            key,
                            p["research_id"],
                            current["plan_sha256"],
                            encoded(decision),
                            encoded(manifest),
                        ),
                    )
                if db.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("foreign key validation failed")
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("integrity check failed")
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return len(accepted)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, default=ROOT / "universe.db")
    parser.add_argument("--research", type=Path, default=ROOT / "elements.db")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.decisions:
        if not args.output:
            parser.error("--output is required for application")
        count = apply_decisions(
            args.core,
            args.research,
            json.loads(args.plan.read_text(encoding="utf-8")),
            json.loads(args.decisions.read_text(encoding="utf-8")),
            args.output,
        )
        print(f"Admitted {count} reviewed observations to {args.output}")
    else:
        plan = make_plan(args.core, args.research)
        args.plan.parent.mkdir(parents=True, exist_ok=True)
        args.plan.write_text(
            json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(
            f"Planned {len(plan['proposals'])} evidence records; no observations promoted"
        )


if __name__ == "__main__":
    main()
