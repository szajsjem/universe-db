#!/usr/bin/env python3
"""Audit elemental evidence and fit explicit-state composition approximations."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import sqlite3
from contextlib import closing
from fractions import Fraction
from pathlib import Path

try:
    from scripts.mixture_properties import calculate_mixture, json_safe, number, packed
except ModuleNotFoundError:
    from mixture_properties import calculate_mixture, json_safe, number, packed

ROOT = Path(__file__).resolve().parents[1]
try:
    from scripts.build_alloy_db import ELEMENTS
except ModuleNotFoundError:
    from build_alloy_db import ELEMENTS
PROPERTIES = (
    "density",
    "specific_heat_capacity",
    "thermal_conductivity",
    "electrical_resistivity",
    "youngs_modulus",
    "shear_modulus",
    "poisson_ratio",
    "melting_point",
)
REFERENCE = "https://www.itl.nist.gov/div898/handbook/pri/section5/pri542.htm"


class FitError(ValueError):
    pass


def composition_fractions(composition):
    if not isinstance(composition, dict) or not composition:
        raise FitError("exact elemental mass fractions are required")
    values = {key: number(value, "mass fraction") for key, value in composition.items()}
    if set(values) - ELEMENTS:
        raise FitError("unknown elemental symbols in composition")
    if any(v < 0 for v in values.values()) or sum(values.values()) != 1:
        raise FitError("mass fractions must be nonnegative and sum exactly to one")
    return {key: value for key, value in values.items() if value}


def state_signature(conditions):
    if not isinstance(conditions, dict):
        raise FitError("conditions must specify temperature_k, phase and state")
    temperature = number(conditions.get("temperature_k"), "temperature_k")
    if (
        temperature <= 0
        or not isinstance(conditions.get("phase"), str)
        or not conditions["phase"].strip()
        or not isinstance(conditions.get("state"), str)
        or not conditions["state"].strip()
    ):
        raise FitError(
            "explicit positive temperature, phase and material state are required"
        )
    result = dict(conditions, temperature_k=str(temperature))
    return json.dumps(json_safe(result), sort_keys=True, separators=(",", ":"))


def solve(matrix, rhs):
    size = len(rhs)
    augmented = [list(row) + [value] for row, value in zip(matrix, rhs)]
    for col in range(size):
        pivot = next((row for row in range(col, size) if augmented[row][col]), None)
        if pivot is None:
            raise FitError(
                "training design is rank deficient; additional independent alloy evidence is needed"
            )
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        divisor = augmented[col][col]
        augmented[col] = [value / divisor for value in augmented[col]]
        for row in range(size):
            if row == col:
                continue
            multiplier = augmented[row][col]
            augmented[row] = [
                a - multiplier * b for a, b in zip(augmented[row], augmented[col])
            ]
    return [row[-1] for row in augmented]


def features(composition, terms):
    return [
        math.prod(composition.get(element, Fraction(0)) for element in term)
        for term in terms
    ]


def fit_alloy_approximation(
    records,
    *,
    degree=1,
    transform="identity",
    allow_unverified=False,
    require_pure_elements=True,
    allow_synthetic=False,
):
    """Exact-rational least squares for linear/quadratic Scheffe mixture models.

    Each record: id, property, unit, value, composition_mass_fractions,
    conditions {temperature_k,phase,state}, source, review_status, provenance_class.
    Ranges/nominal recipes must be resolved explicitly before calling this API.
    """
    if (
        not isinstance(records, list)
        or not records
        or type(degree) is not int
        or degree not in (1, 2)
    ):
        raise FitError("provide training records and degree 1 or 2")
    if transform not in ("identity", "reciprocal"):
        raise FitError("transform must be identity or reciprocal")
    compositions = []
    values = []
    weights = []
    ids = set()
    signatures = set()
    pure = set()
    symbols = set()
    synthetic = False
    for row in records:
        if not isinstance(row, dict):
            raise FitError("each training record must be an object")
        if not row.get("id") or row["id"] in ids or not row.get("source"):
            raise FitError("training records need unique IDs and source citations")
        ids.add(row["id"])
        if row.get("review_status") != "reviewed" and not allow_unverified:
            raise FitError(
                "unverified training evidence requires explicit allow_unverified=True"
            )
        provenance = row.get("provenance_class")
        if provenance not in ("measured", "curated", "fictional"):
            raise FitError(
                "training evidence must declare measured, curated or fictional provenance"
            )
        if provenance == "fictional":
            synthetic = True
            if not allow_synthetic:
                raise FitError(
                    "fictional training requires explicit allow_synthetic=True"
                )
        if not row.get("property") or not row.get("unit"):
            raise FitError("property and unit are required")
        signatures.add(
            (row["property"], row["unit"], state_signature(row.get("conditions")))
        )
        x = composition_fractions(row.get("composition_mass_fractions"))
        symbols.update(x)
        if len(x) == 1:
            pure.update(x)
        y = number(row.get("value"), "training value")
        if transform == "reciprocal":
            if y <= 0:
                raise FitError("reciprocal transform requires positive values")
            y = 1 / y
        weight = number(row.get("weight", "1"), "weight")
        if weight <= 0:
            raise FitError("training weights must be positive")
        compositions.append(x)
        values.append(y)
        weights.append(weight)
    if len(signatures) != 1:
        raise FitError(
            "property, unit, temperature, phase and state must match across training evidence"
        )
    missing = sorted(symbols - pure)
    if missing and require_pure_elements:
        raise FitError("missing pure-element property evidence: " + ", ".join(missing))
    elements = sorted(symbols)
    terms = [(element,) for element in elements]
    if degree == 2:
        terms.extend(itertools.combinations(elements, 2))
    if len(terms) > 256 or len(records) < len(terms):
        raise FitError(
            f"insufficient evidence or too many parameters: {len(records)} records, {len(terms)} coefficients"
        )
    design = [features(x, terms) for x in compositions]
    matrix = [
        [
            sum(w * row[i] * row[j] for row, w in zip(design, weights))
            for j in range(len(terms))
        ]
        for i in range(len(terms))
    ]
    rhs = [
        sum(w * row[i] * y for row, y, w in zip(design, values, weights))
        for i in range(len(terms))
    ]
    coefficients = solve(matrix, rhs)
    residuals = [
        y - sum(a * b for a, b in zip(row, coefficients))
        for row, y in zip(design, values)
    ]
    mse = sum(w * r * r for w, r in zip(weights, residuals)) / sum(weights)
    property_name, unit, _ = next(iter(signatures))
    record_digest = hashlib.sha256(
        json.dumps(json_safe(records), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "model_kind": "scheffe_composition_approximation",
        "algorithm_version": "1.0.0",
        "provenance_class": "fictional" if synthetic else "modeled",
        "property": property_name,
        "unit": unit,
        "conditions": json_safe(records[0]["conditions"]),
        "degree": degree,
        "transform": transform,
        "basis": "mass_fraction",
        "terms": [list(term) for term in terms],
        "coefficients": [
            packed(value, "regression coefficient", "fitted_from_training_evidence")
            for value in coefficients
        ],
        "training_evidence": json_safe(records),
        "training_sha256": record_digest,
        "element_evidence": {
            "elements": elements,
            "pure_elements": sorted(pure),
            "missing_pure_elements": missing,
        },
        "domain": {
            element: {
                "min": str(min(x.get(element, Fraction(0)) for x in compositions)),
                "max": str(max(x.get(element, Fraction(0)) for x in compositions)),
            }
            for element in elements
        },
        "diagnostics": {
            "training_records": len(records),
            "coefficients": len(terms),
            "residual_degrees_of_freedom": len(records) - len(terms),
            "weighted_training_rmse_transformed": math.sqrt(float(mse)),
            "independent_validation": "not performed",
            "prediction_uncertainty": None,
        },
        "limitations": [
            "Training residual is not an independently validated error estimate",
            "No prediction across temperatures, phases, material states or unknown elements",
            "Polynomial composition dependence does not identify equilibrium phases or microstructure",
            "Domain limits are coordinate limits, not a convex-hull check",
        ],
        "reference": REFERENCE,
    }


def predict_alloy(
    model, composition_mass_fractions, *, conditions, allow_extrapolation=False
):
    if state_signature(conditions) != state_signature(model["conditions"]):
        raise FitError("prediction conditions differ from fitted state")
    x = composition_fractions(composition_mass_fractions)
    unknown = set(x) - set(model["domain"])
    if unknown:
        raise FitError("elements absent from training: " + ", ".join(sorted(unknown)))
    extrapolated = any(
        not number(bounds["min"], "min")
        <= x.get(e, Fraction(0))
        <= number(bounds["max"], "max")
        for e, bounds in model["domain"].items()
    )
    if extrapolated and not allow_extrapolation:
        raise FitError("prediction outside training composition limits")
    coefficients = [
        Fraction(row["numerator"], row["denominator"]) for row in model["coefficients"]
    ]
    response = sum(a * b for a, b in zip(features(x, model["terms"]), coefficients))
    if model["transform"] == "reciprocal":
        if response <= 0:
            raise FitError("fitted reciprocal response is nonphysical")
        response = 1 / response
    if (
        model["property"]
        in (
            "density",
            "specific_heat_capacity",
            "thermal_conductivity",
            "electrical_resistivity",
            "youngs_modulus",
            "shear_modulus",
        )
        and response <= 0
    ):
        raise FitError("fitted property is nonphysical")
    return dict(
        packed(response, model["unit"], "fitted_approximation"),
        property=model["property"],
        conditions=json_safe(conditions),
        provenance_class=model["provenance_class"],
        training_sha256=model["training_sha256"],
        extrapolated=extrapolated,
        prediction_uncertainty=None,
    )


def predict_integer_mixture(
    model, components, counts, *, conditions, database=ROOT / "universe.db"
):
    # Expand molecules first: regression features are elemental MASS fractions.
    mixture = calculate_mixture(components, counts, database=database)
    if any(
        "molar_mass_g_mol" in row for row, count in zip(components, counts) if count
    ):
        raise FitError(
            "elemental mass regression does not support unknown isotope/mass overrides"
        )
    with closing(
        sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)
    ) as db:
        masses = {
            symbol: Fraction(numerator, denominator)
            for symbol, numerator, denominator in db.execute(
                "SELECT e.symbol,o.value_numerator,o.value_denominator FROM element e JOIN observation o ON o.subject_entity_id=e.entity_id WHERE o.property_id='property:relative_atomic_mass' AND o.dataset_id='dataset:pubchem-periodic-table-2026-07-28'"
            )
        }
    contributions = {
        e: count * masses[e] for e, count in mixture["element_counts"].items()
    }
    total = sum(contributions.values())
    return predict_alloy(
        model,
        {e: value / total for e, value in contributions.items()},
        conditions=conditions,
    )


def exact_alloy_composition(db, alloy_id):
    rows = db.execute(
        "SELECT * FROM composition WHERE alloy_id=?", (alloy_id,)
    ).fetchall()
    composition = {}
    balance = None
    for row in rows:
        if "+" in row["element"]:
            raise FitError("combined analyte cannot be split into elemental fractions")
        if row["role"] == "balance":
            if balance is not None:
                raise FitError("multiple balance components")
            balance = row["element"]
            continue
        if row["nominal_numerator"] is not None:
            value = Fraction(row["nominal_numerator"], row["nominal_denominator"])
        elif (
            row["min_numerator"] is not None
            and row["max_numerator"] is not None
            and Fraction(row["min_numerator"], row["min_denominator"])
            == Fraction(row["max_numerator"], row["max_denominator"])
        ):
            value = Fraction(row["min_numerator"], row["min_denominator"])
        else:
            raise FitError(
                "composition contains ranges, unspecified amounts or maximum-only limits"
            )
        composition[row["element"]] = value / 100
    if balance is not None:
        composition[balance] = 1 - sum(composition.values())
    return composition_fractions(composition)


def load_element_training_records(
    property_name,
    *,
    elements=None,
    evidence_database=ROOT / "elements.db",
    database=ROOT / "universe.db",
):
    """Extract source-backed endpoints; return records plus explicit exclusions.

    Records keep pending review status. Molar Cp is converted to mass Cp with
    exact PubChem atomic masses and the transformation recorded in each input.
    No temperature, material state or experimental purity is synthesized.
    """
    records, exclusions = [], []
    with closing(
        sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)
    ) as core:
        masses = {
            symbol: Fraction(n, d)
            for symbol, n, d in core.execute(
                "SELECT e.symbol,o.value_numerator,o.value_denominator FROM element e JOIN observation o ON o.subject_entity_id=e.entity_id WHERE o.property_id='property:relative_atomic_mass' AND o.dataset_id='dataset:pubchem-periodic-table-2026-07-28'"
            )
        }
    with closing(
        sqlite3.connect(
            Path(evidence_database).resolve().as_uri() + "?mode=ro", uri=True
        )
    ) as db:
        db.row_factory = sqlite3.Row
        for row in db.execute(
            "SELECT o.*,s.url FROM unverified_element_observation o JOIN unverified_element_source s USING(source_id) ORDER BY observation_id"
        ):
            conversion = (
                property_name == "specific_heat_capacity"
                and row["property"] == "molar_heat_capacity"
            )
            if row["property"] != property_name and not conversion:
                continue
            if elements is not None and row["element"] not in elements:
                continue
            reasons = []
            original = json.loads(row["input_json"])
            if original.get("composition_basis") != "elemental_reference":
                reasons.append(
                    "finite or unspecified specimen composition is not a pure-element endpoint"
                )
            if row["value_numerator"] is None:
                reasons.append("range or bound has no point response")
            for key in ("temperature_k_numerator", "phase", "state"):
                if row[key] is None or row[key] == "":
                    reasons.append("missing " + key.removesuffix("_numerator"))
            if conversion and row["element"] not in masses:
                reasons.append("missing atomic mass for molar Cp conversion")
            if row["provenance_class"] == "modeled":
                reasons.append(
                    "modeled source response is not an observed training endpoint"
                )
            if reasons:
                exclusions.append(
                    {"observation_id": row["observation_id"], "reasons": reasons}
                )
                continue
            value = Fraction(row["value_numerator"], row["value_denominator"])
            transformation = None
            if conversion:
                mass = masses[row["element"]]
                value = value * 1000 / mass
                transformation = {
                    "kind": "molar_to_mass_heat_capacity",
                    "atomic_mass_g_mol": str(mass),
                    "atomic_mass_dataset": "dataset:pubchem-periodic-table-2026-07-28",
                    "source_molar_value": str(
                        Fraction(row["value_numerator"], row["value_denominator"])
                    ),
                    "uncertainty": "not propagated; source uncertainty and atomic mass uncertainty not supplied",
                }
            record = {
                "id": row["observation_id"],
                "property": property_name,
                "unit": "J/(kg*K)" if conversion else row["unit"],
                "value": str(value),
                "composition_mass_fractions": {row["element"]: "1"},
                "conditions": {
                    "temperature_k": str(
                        Fraction(
                            row["temperature_k_numerator"],
                            row["temperature_k_denominator"],
                        )
                    ),
                    "phase": row["phase"],
                    "state": row["state"],
                },
                "source": row["url"],
                "source_id": row["source_id"],
                "source_locator": row["source_locator"],
                "provenance_class": row["provenance_class"],
                "review_status": row["review_status"],
                "method": row["method"],
                "note": row["note"],
            }
            if transformation:
                record["transformation"] = transformation
            record["source_record"] = original
            if original.get("pressure_pa") is not None:
                record["conditions"]["pressure_pa"] = original["pressure_pa"]
            records.append(record)
    return {"records": records, "excluded": exclusions}


def audit_database_evidence(
    database=ROOT / "universe.db",
    alloys=ROOT / "alloys.db",
    element_evidence=ROOT / "elements.db",
):
    report = {
        "result_kind": "alloy_element_evidence_audit",
        "properties_checked": list(PROPERTIES),
        "numeric_fit_policy": "No midpoint, impurity zero, unspecified balance, or commercial-purity proxy is invented",
        "elements": {},
        "alloy_fit_candidates": [],
        "excluded_alloy_properties": [],
    }
    with (
        closing(sqlite3.connect(database)) as db,
        closing(sqlite3.connect(alloys)) as alloy_db,
    ):
        db.row_factory = sqlite3.Row
        alloy_db.row_factory = sqlite3.Row
        elements = {
            row["symbol"]: row["entity_id"]
            for row in db.execute("SELECT symbol,entity_id FROM element")
        }
        constituent_elements = {
            part
            for row in alloy_db.execute("SELECT element FROM composition")
            for part in row[0].split("+")
        }
        for symbol, entity_id in elements.items():
            evidence = {prop: [] for prop in PROPERTIES}
            subjects = [entity_id] + [
                row[0]
                for row in db.execute(
                    "SELECT cs.entity_id FROM chemical_species cs JOIN species_element se ON cs.entity_id=se.species_id WHERE se.element_id=? AND cs.electric_charge=0 AND (SELECT count(*) FROM species_element s WHERE s.species_id=cs.entity_id)=1",
                    (entity_id,),
                )
            ]
            for subject in subjects:
                for row in db.execute(
                    "SELECT o.*,s.url FROM observation o JOIN source s USING(source_id) WHERE subject_entity_id=?",
                    (subject,),
                ):
                    prop = row["property_id"].removeprefix("property:")
                    if prop not in evidence:
                        continue
                    temperature = False
                    if row["condition_set_id"]:
                        temperature = bool(
                            db.execute(
                                "SELECT 1 FROM condition_value WHERE condition_set_id=? AND quantity_kind='temperature'",
                                (row["condition_set_id"],),
                            ).fetchone()
                        )
                    evidence[prop].append(
                        {
                            "observation_id": row["observation_id"],
                            "subject_entity_id": subject,
                            "source_id": row["source_id"],
                            "url": row["url"],
                            "provenance_class": row["provenance_class"],
                            "has_temperature": temperature,
                            "has_method": bool(row["method"]),
                            "condition_set_id": row["condition_set_id"],
                            "unit_id": row["unit_id"],
                        }
                    )
            report["elements"][symbol] = {
                "used_in_alloys": symbol in constituent_elements,
                "has_atomic_mass_evidence": bool(
                    db.execute(
                        "SELECT 1 FROM observation WHERE subject_entity_id=? AND property_id='property:relative_atomic_mass'",
                        (entity_id,),
                    ).fetchone()
                ),
                "evidence": evidence,
                "missing_properties": [
                    prop for prop, rows in evidence.items() if not rows
                ],
                "missing_temperature_context": [
                    prop
                    for prop, rows in evidence.items()
                    if rows and not any(r["has_temperature"] for r in rows)
                ],
                "commercial_grade_proxies": [
                    row[0]
                    for row in alloy_db.execute(
                        "SELECT alloy_id FROM alloy WHERE base_element=? AND alloy_id IN ('nickel-200','nickel-201','cu-c11000','al-1050a','al-1100','ti-grade-1','ti-grade-2')",
                        (symbol,),
                    )
                ],
            }
        for row in alloy_db.execute("SELECT * FROM property_values"):
            reasons = []
            try:
                composition = exact_alloy_composition(alloy_db, row["alloy_id"])
            except FitError as error:
                composition = None
                reasons.append(str(error))
            if row["value"] is None:
                reasons.append("property is a range or bound, not a point response")
            if row["temperature_c"] is None:
                reasons.append("measurement temperature unspecified")
            if row["review_status"] != "reviewed":
                reasons.append("pending human review")
            entry = {
                "observation_id": row["observation_id"],
                "alloy_id": row["alloy_id"],
                "property": row["property"],
                "source_id": row["source_id"],
                "reasons": reasons,
            }
            if composition is not None:
                entry["nominal_mass_fractions"] = json_safe(composition)
            report[
                "excluded_alloy_properties" if reasons else "alloy_fit_candidates"
            ].append(entry)
        used = [
            symbol
            for symbol, row in report["elements"].items()
            if row["used_in_alloys"]
        ]
        report["summary"] = {
            "total_elements": len(elements),
            "alloy_constituent_elements": len(used),
            "elements_without_atomic_mass_evidence": sorted(
                symbol
                for symbol, row in report["elements"].items()
                if not row["has_atomic_mass_evidence"]
            ),
            "constituents_missing_any_property": sorted(
                e for e in used if report["elements"][e]["missing_properties"]
            ),
            "constituents_without_density_evidence": sorted(
                e
                for e in used
                if "density" in report["elements"][e]["missing_properties"]
            ),
            "eligible_reviewed_alloy_point_records": len(
                report["alloy_fit_candidates"]
            ),
            "excluded_alloy_point_records": len(report["excluded_alloy_properties"]),
        }
    report["database_sha256"] = hashlib.sha256(Path(database).read_bytes()).hexdigest()
    report["alloys_database_sha256"] = hashlib.sha256(
        Path(alloys).read_bytes()
    ).hexdigest()
    if element_evidence is not None and Path(element_evidence).is_file():
        with closing(
            sqlite3.connect(
                Path(element_evidence).resolve().as_uri() + "?mode=ro", uri=True
            )
        ) as db:
            db.row_factory = sqlite3.Row
            pending = {}
            for row in db.execute(
                "SELECT * FROM unverified_element_observation ORDER BY observation_id"
            ):
                pending.setdefault(row["element"], {}).setdefault(
                    row["property"], []
                ).append(
                    {
                        "observation_id": row["observation_id"],
                        "source_id": row["source_id"],
                        "has_temperature": row["temperature_k_numerator"] is not None,
                        "has_state": bool(row["phase"] and row["state"]),
                        "review_status": row["review_status"],
                        "provenance_class": row["provenance_class"],
                    }
                )
            report["pending_element_evidence"] = pending
            report["element_evidence_sha256"] = hashlib.sha256(
                Path(element_evidence).read_bytes()
            ).hexdigest()
            report["summary"]["pending_element_observations"] = sum(
                len(rows) for props in pending.values() for rows in props.values()
            )
            report["summary"][
                "constituents_without_density_evidence_including_pending"
            ] = [
                e
                for e in report["summary"]["constituents_without_density_evidence"]
                if not pending.get(e, {}).get("density")
            ]
            report["remaining_constituent_property_gaps_including_pending"] = {
                e: [
                    prop
                    for prop in report["elements"][e]["missing_properties"]
                    if not pending.get(e, {}).get(prop)
                    and not (
                        prop == "specific_heat_capacity"
                        and pending.get(e, {}).get("molar_heat_capacity")
                    )
                ]
                for e, entry in report["elements"].items()
                if entry["used_in_alloys"]
            }
            report["declared_element_research_gaps"] = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM unverified_element_gap ORDER BY element,property"
                )
            ]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "universe.db")
    parser.add_argument("--alloys", type=Path, default=ROOT / "alloys.db")
    parser.add_argument("--element-evidence", type=Path, default=ROOT / "elements.db")
    parser.add_argument(
        "--training",
        type=Path,
        help="explicit-state exact-composition JSON training records",
    )
    parser.add_argument("--degree", type=int, choices=[1, 2], default=1)
    parser.add_argument(
        "--transform", choices=["identity", "reciprocal"], default="identity"
    )
    parser.add_argument("--allow-unverified", action="store_true")
    parser.add_argument("--allow-synthetic", action="store_true")
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".build/alloy-evidence-audit.json"
    )
    args = parser.parse_args()
    audit = audit_database_evidence(args.database, args.alloys, args.element_evidence)
    result = {"audit": audit, "fit": {"status": "not_requested"}}
    if args.training:
        try:
            records = json.loads(args.training.read_text(encoding="utf-8"))
            result["fit"] = {
                "status": "fitted",
                "model": fit_alloy_approximation(
                    records,
                    degree=args.degree,
                    transform=args.transform,
                    allow_unverified=args.allow_unverified,
                    allow_synthetic=args.allow_synthetic,
                ),
            }
        except (FitError, ValueError, TypeError) as error:
            result["fit"] = {"status": "blocked", "reason": str(error)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_safe(result), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit["summary"], indent=2))
    print("Fit:", result["fit"]["status"], "Report:", args.output)
    if result["fit"]["status"] == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
