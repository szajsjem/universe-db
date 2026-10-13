#!/usr/bin/env python3
"""Investigate record, evidence, context and calculation-readiness gaps."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

if __package__:
    from .build_isotope_evidence import audit as audit_isotopes
    from .fit_alloy_properties import (
        FitError,
        audit_database_evidence,
        exact_alloy_composition,
        load_element_training_records,
    )
else:
    from build_isotope_evidence import audit as audit_isotopes
    from fit_alloy_properties import (
        FitError,
        audit_database_evidence,
        exact_alloy_composition,
        load_element_training_records,
    )

ROOT = Path(__file__).resolve().parents[1]
DATABASES = (
    "universe.db",
    "universe-unverified.db",
    "alloys.db",
    "elements.db",
    "isotopes.db",
    "crystals.db",
)


def connect(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return closing(db)


def rows(db, sql, parameters=()):
    return [dict(row) for row in db.execute(sql, parameters)]


def scalar(db, sql, parameters=()):
    return db.execute(sql, parameters).fetchone()[0]


def investigate(root=ROOT):
    root = Path(root)
    report = {
        "scope": "Current local reviewed core and authored research references; not a completeness claim over all known substances",
        "databases": {},
        "limitations": [
            "Record presence is not scientific verification",
            "Missing data is measured against explicit local target corpora",
            "Primary papers were not rereviewed by this computational audit",
        ],
    }
    for filename in DATABASES:
        path = root / filename
        with connect(path) as db:
            tables = [
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            counts = {
                name: scalar(db, 'SELECT count(*) FROM "' + name + '"')
                for name in tables
            }
            report["databases"][filename] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "row_counts": counts,
                "empty_tables": [name for name, count in counts.items() if count == 0],
                "integrity": scalar(db, "PRAGMA integrity_check"),
                "foreign_key_violations": len(
                    db.execute("PRAGMA foreign_key_check").fetchall()
                ),
            }
    with connect(root / "universe.db") as db:
        report["reviewed_core"] = {
            "properties": rows(
                db,
                "SELECT property_id,count(*) AS records,count(condition_set_id) AS with_condition_set,count(uncertainty_numerator) AS with_uncertainty FROM observation GROUP BY property_id ORDER BY property_id",
            ),
            "unpopulated_property_definitions": rows(
                db,
                "SELECT p.property_id FROM property_definition p WHERE NOT EXISTS(SELECT 1 FROM observation o WHERE o.property_id=p.property_id)",
            ),
            "provenance": rows(
                db,
                "SELECT provenance_class,count(*) AS records FROM observation GROUP BY provenance_class",
            ),
            "species_kinds": rows(
                db,
                "SELECT species_kind,count(*) AS records FROM chemical_species GROUP BY species_kind",
            ),
            "species_without_molar_mass": rows(
                db,
                "SELECT c.entity_id,c.formula FROM chemical_species c WHERE NOT EXISTS(SELECT 1 FROM observation o WHERE o.subject_entity_id=c.entity_id AND o.property_id='property:molar_mass')",
            ),
            "molecule_kind_without_graph": rows(
                db,
                "SELECT c.entity_id,c.formula FROM chemical_species c WHERE species_kind='molecule' AND NOT EXISTS(SELECT 1 FROM molecule m WHERE m.species_id=c.entity_id)",
            ),
            "reactions_without_condition_links": scalar(
                db,
                "SELECT count(*) FROM reaction r WHERE NOT EXISTS(SELECT 1 FROM reaction_condition c WHERE c.reaction_id=r.reaction_id)",
            ),
            "particle_names": [
                row[0]
                for row in db.execute(
                    "SELECT e.name FROM particle p JOIN entity e USING(entity_id) ORDER BY e.name"
                )
            ],
            "unit_registry": rows(
                db, "SELECT unit_id,symbol,quantity_kind FROM unit ORDER BY unit_id"
            ),
        }
    with connect(root / "alloys.db") as db:
        blocked, exact = [], []
        for row in db.execute(
            "SELECT alloy_id,name,family FROM alloy ORDER BY alloy_id"
        ):
            try:
                composition = exact_alloy_composition(db, row["alloy_id"])
                exact.append(
                    {
                        **dict(row),
                        "nominal_mass_fractions": {
                            key: str(value) for key, value in composition.items()
                        },
                    }
                )
            except FitError as error:
                blocked.append({**dict(row), "reason": str(error)})
        report["alloys"] = {
            "total_grades": scalar(db, "SELECT count(*) FROM alloy"),
            "grades_with_any_property": scalar(
                db, "SELECT count(DISTINCT alloy_id) FROM property_observation"
            ),
            "grades_without_properties": rows(
                db,
                "SELECT alloy_id,name,family FROM alloy WHERE NOT EXISTS(SELECT 1 FROM property_observation p WHERE p.alloy_id=alloy.alloy_id) ORDER BY family,alloy_id",
            ),
            "properties": rows(
                db,
                "SELECT property,count(*) AS records,count(DISTINCT alloy_id) AS grades,count(value_numerator) AS point_values,count(temperature_c_numerator) AS temperature_known,count(uncertainty_numerator) AS uncertainty_known FROM property_observation GROUP BY property ORDER BY property",
            ),
            "value_kinds": rows(
                db,
                "SELECT value_kind,count(*) AS records FROM property_observation GROUP BY value_kind",
            ),
            "nominal_exact_recipes": exact,
            "unresolved_recipes": blocked,
            "reviewed_records": scalar(
                db,
                "SELECT count(*) FROM property_observation WHERE review_status='reviewed'",
            ),
            "records_without_temperature": scalar(
                db,
                "SELECT count(*) FROM property_observation WHERE temperature_c_numerator IS NULL",
            ),
            "records_without_uncertainty": scalar(
                db,
                "SELECT count(*) FROM property_observation WHERE uncertainty_numerator IS NULL",
            ),
        }
    element_audit = audit_database_evidence(
        root / "universe.db", root / "alloys.db", root / "elements.db"
    )
    report["elements"] = {
        "summary": element_audit["summary"],
        "remaining_property_gaps_including_pending": element_audit[
            "remaining_constituent_property_gaps_including_pending"
        ],
        "reviewed_context_gaps": {
            symbol: entry["missing_temperature_context"]
            for symbol, entry in element_audit["elements"].items()
            if entry["used_in_alloys"]
        },
    }
    with connect(root / "elements.db") as db:
        report["elements"]["research_properties"] = rows(
            db,
            "SELECT property,count(*) AS records,count(DISTINCT element) AS elements,count(temperature_k_numerator) AS temperature_known FROM unverified_element_observation GROUP BY property",
        )
    report["elements"]["endpoint_context_selection"] = {}
    for prop in (
        "density",
        "specific_heat_capacity",
        "thermal_conductivity",
        "electrical_resistivity",
        "youngs_modulus",
        "shear_modulus",
        "poisson_ratio",
    ):
        result = load_element_training_records(
            prop, database=root / "universe.db", evidence_database=root / "elements.db"
        )
        report["elements"]["endpoint_context_selection"][prop] = {
            "extractable_pending_records": len(result["records"]),
            "element_symbols": sorted(
                {
                    next(iter(row["composition_mass_fractions"]))
                    for row in result["records"]
                }
            ),
            "excluded": result["excluded"],
            "caution": "Extraction is not review, matched-state fit eligibility or independent model validation",
        }
    report["isotopes"] = audit_isotopes(root / "isotopes.db", root / "universe.db")
    with connect(root / "isotopes.db") as db:
        report["isotopes"]["ame_mass_estimate_counts"] = rows(
            db,
            "SELECT estimated,count(*) AS records FROM unverified_isotope_observation WHERE source_id='amdc-ame2020' AND property='atomic_mass' GROUP BY estimated",
        )
        report["isotopes"]["half_life_kinds"] = rows(
            db,
            "SELECT value_kind,estimated,count(*) AS records FROM unverified_isotope_observation WHERE property='half_life' GROUP BY value_kind,estimated",
        )
        report["isotopes"]["missing_ground_state_half_life_or_stable_designation"] = (
            rows(
                db,
                "SELECT z,a FROM unverified_isotope_nuclide n WHERE isomer=0 AND NOT EXISTS(SELECT 1 FROM unverified_isotope_observation o WHERE o.z=n.z AND o.a=n.a AND o.isomer=0 AND (o.property='half_life' OR (o.property='stability' AND o.text_value='stable'))) ORDER BY z,a",
            )
        )
        report["isotopes"]["missing_ground_state_spin_parity"] = rows(
            db,
            "SELECT z,a FROM unverified_isotope_nuclide n WHERE isomer=0 AND NOT EXISTS(SELECT 1 FROM unverified_isotope_observation o WHERE o.z=n.z AND o.a=n.a AND o.isomer=0 AND o.property='spin_parity') ORDER BY z,a",
        )
        matches = identical = provenance_differences = 0
        with connect(root / "universe.db") as core:
            for row in core.execute(
                "SELECT n.proton_count,n.neutron_count,o.property_id,o.value_numerator,o.value_denominator,o.provenance_class FROM nuclide n JOIN observation o ON o.subject_entity_id=n.entity_id WHERE o.property_id IN ('property:relative_atomic_mass','property:isotopic_composition')"
            ):
                mapped = (
                    "atomic_mass"
                    if row["property_id"].endswith("relative_atomic_mass")
                    else "isotopic_abundance"
                )
                staged = db.execute(
                    "SELECT value_numerator,value_denominator,provenance_class FROM unverified_isotope_observation WHERE source_id='nist-full-isotopes-2026-07-28' AND z=? AND a=? AND isomer=0 AND property=?",
                    (
                        row["proton_count"],
                        row["proton_count"] + row["neutron_count"],
                        mapped,
                    ),
                ).fetchone()
                if staged:
                    matches += 1
                    identical += (
                        row["value_numerator"] * int(staged["value_denominator"])
                        == int(staged["value_numerator"]) * row["value_denominator"]
                    )
                    provenance_differences += (
                        row["provenance_class"] != staged["provenance_class"]
                    )
        report["isotopes"]["nist_core_vs_research_provenance"] = {
            "matched_records": matches,
            "identical_numeric_values": identical,
            "different_provenance_labels": provenance_differences,
            "issue": "Reviewed seed uses measured; full NIST importer uses curated for identical evaluated-source values. Needs explicit provenance-policy reconciliation.",
        }
    with connect(root / "crystals.db") as db:
        report["crystals"] = {
            "structures": scalar(
                db, "SELECT count(*) FROM unverified_crystal_structure"
            ),
            "crystal_systems": rows(
                db,
                "SELECT crystal_system,count(*) AS records FROM unverified_crystal_structure GROUP BY crystal_system",
            ),
            "structure_records": rows(
                db,
                "SELECT structure_id,name,formula,phase,site_convention,space_group_number,cell_formula_units FROM unverified_crystal_structure ORDER BY structure_id",
            ),
            "site_conventions": rows(
                db,
                "SELECT site_convention,count(*) AS records FROM unverified_crystal_structure GROUP BY site_convention",
            ),
            "missing_condition_fields": {
                field: scalar(
                    db,
                    "SELECT count(*) FROM unverified_crystal_structure WHERE "
                    + field
                    + " IS NULL",
                )
                for field in (
                    "temperature_k_numerator",
                    "pressure_pa_numerator",
                    "method",
                    "space_group_number",
                    "cell_formula_units",
                )
            },
            "site_fields_missing": {
                field: scalar(
                    db,
                    "SELECT count(*) FROM unverified_crystal_site WHERE "
                    + field
                    + " IS NULL",
                )
                for field in ("occupancy_numerator", "multiplicity", "wyckoff")
            },
            "incomplete_lattice_metrics": rows(
                db,
                "SELECT c.structure_id,c.name,count(p.parameter) AS parameters FROM unverified_crystal_structure c LEFT JOIN unverified_crystal_lattice_parameter p USING(structure_id) GROUP BY c.structure_id HAVING count(p.parameter)<6 ORDER BY c.structure_id",
            ),
            "complete_geometry_with_cell_formula_units": scalar(
                db,
                "SELECT count(*) FROM unverified_crystal_structure c WHERE cell_formula_units IS NOT NULL AND (SELECT count(*) FROM unverified_crystal_lattice_parameter p WHERE p.structure_id=c.structure_id)=6",
            ),
            "structures_without_sites": rows(
                db,
                "SELECT structure_id,name FROM unverified_crystal_structure c WHERE NOT EXISTS(SELECT 1 FROM unverified_crystal_site s WHERE s.structure_id=c.structure_id)",
            ),
            "isotope_specific_sites": scalar(
                db,
                "SELECT count(*) FROM unverified_crystal_site WHERE isotope_mass_number IS NOT NULL",
            ),
            "declared_gaps": [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT input_json FROM unverified_crystal_gap ORDER BY position"
                )
            ],
        }
    with connect(root / "universe-unverified.db") as db:
        report["wikipedia"] = {
            "candidate_kinds": rows(
                db,
                "SELECT candidate_kind,count(*) AS records FROM unverified_entity_candidate GROUP BY candidate_kind",
            ),
            "candidates_without_formula": scalar(
                db,
                "SELECT count(*) FROM unverified_entity_candidate WHERE formula IS NULL OR formula=''",
            ),
            "candidate_facts_missing_units": scalar(
                db,
                "SELECT count(*) FROM unverified_candidate_fact WHERE (value_numerator IS NOT NULL OR value_decimal_text IS NOT NULL) AND (unit_text IS NULL OR unit_text='')",
            ),
            "candidate_facts_without_condition_rows": scalar(
                db,
                "SELECT count(*) FROM unverified_candidate_fact f WHERE (value_numerator IS NOT NULL OR value_decimal_text IS NOT NULL) AND NOT EXISTS(SELECT 1 FROM unverified_candidate_fact_condition c WHERE c.candidate_fact_id=f.candidate_fact_id)",
            ),
            "successful_candidate_review_actions": scalar(
                db,
                "SELECT count(DISTINCT candidate_id) FROM wikipedia_candidate_agent_review WHERE action!='error'",
            ),
            "active_candidates_without_successful_action": scalar(
                db,
                "SELECT count(*) FROM unverified_entity_candidate c WHERE NOT EXISTS(SELECT 1 FROM wikipedia_candidate_agent_review r WHERE r.candidate_id=c.candidate_id AND r.action!='error')",
            ),
            "numeric_candidate_facts": scalar(
                db,
                "SELECT count(*) FROM unverified_candidate_fact WHERE value_numerator IS NOT NULL OR value_decimal_text IS NOT NULL",
            ),
            "numeric_candidate_facts_without_uncertainty": scalar(
                db,
                "SELECT count(*) FROM unverified_candidate_fact WHERE (value_numerator IS NOT NULL OR value_decimal_text IS NOT NULL) AND uncertainty_numerator IS NULL AND uncertainty_decimal_text IS NULL",
            ),
            "audit_metadata": {
                row["audit_id"]: json.loads(row["metadata_json"])
                for row in db.execute(
                    "SELECT audit_id,metadata_json FROM unverified_wikipedia_source_audit"
                )
            },
        }
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".build/missing-data-investigation.json"
    )
    args = parser.parse_args()
    report = investigate(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("Investigation written:", args.output)
