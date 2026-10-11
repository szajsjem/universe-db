#!/usr/bin/env python3
"""Fit and validate a ground-state liquid-drop atomic-mass approximation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from contextlib import closing
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASS_ENERGY_MEV = 931.49410372  # CODATA 2022, u*c^2
HYDROGEN_MASS_U = 1.00782503223  # archived NIST ground-state H-1
NEUTRON_MASS_U = 1.00866491606  # CODATA 2022
TERMS = ["volume", "surface", "coulomb", "asymmetry", "pairing"]
REFERENCES = [
    "https://doi.org/10.1007/s41365-019-0718-8",
    "https://physics.nist.gov/cuu/pdf/wall_2022.pdf",
]


class IsotopeFitError(ValueError):
    pass


def coordinates(z, a, isomer=0):
    if any(type(value) is not int for value in (z, a, isomer)):
        raise IsotopeFitError("Z, A and isomer must be integers")
    if z < 0 or a < 1 or a < z or isomer < 0:
        raise IsotopeFitError("invalid isotope coordinates")
    return z, a, a - z


def basis(z, a):
    _, _, n = coordinates(z, a)
    pair = 1 if z % 2 == 0 and n % 2 == 0 else -1 if z % 2 and n % 2 else 0
    return [
        float(a),
        -(a ** (2 / 3)),
        -z * (z - 1) / a ** (1 / 3),
        -((n - z) ** 2) / a,
        pair / math.sqrt(a),
    ]


def least_squares(design, targets):
    """Column-scaled, twice-reorthogonalized QR; no dependency or normal equations."""
    size = len(design[0])
    scales = [math.sqrt(math.fsum(row[j] ** 2 for row in design)) for j in range(size)]
    q, r = [], [[0.0] * size for _ in range(size)]
    for j in range(size):
        if scales[j] == 0:
            raise IsotopeFitError("rank deficient isotope training design")
        v = [row[j] / scales[j] for row in design]
        for _ in range(2):
            for i in range(j):
                correction = math.fsum(x * y for x, y in zip(q[i], v))
                r[i][j] += correction
                v = [x - correction * y for x, y in zip(v, q[i])]
        norm = math.sqrt(math.fsum(x * x for x in v))
        if norm < 1e-12:
            raise IsotopeFitError("rank deficient isotope training design")
        r[j][j] = norm
        q.append([x / norm for x in v])
    projected = [math.fsum(x * y for x, y in zip(column, targets)) for column in q]
    solution = [0.0] * size
    for i in reversed(range(size)):
        solution[i] = (
            projected[i] - math.fsum(r[i][j] * solution[j] for j in range(i + 1, size))
        ) / r[i][i]
    return [value / scale for value, scale in zip(solution, scales)]


def energy_target(record, constants):
    return (
        record["z"] * constants["hydrogen_mass_u"]
        + (record["a"] - record["z"]) * constants["neutron_mass_u"]
        - float(Fraction(record["value"]))
    ) * MASS_ENERGY_MEV


def fit_coefficients(records, constants):
    if len(records) < 10:
        raise IsotopeFitError(
            "at least ten independent ground-state masses are required"
        )
    return least_squares(
        [basis(r["z"], r["a"]) for r in records],
        [energy_target(r, constants) for r in records],
    )


def energy(coefficients, z, a):
    return math.fsum(x * y for x, y in zip(coefficients, basis(z, a)))


def residual_references(records, coefficients, constants):
    return [
        {
            "id": row["id"],
            "z": row["z"],
            "n": row["a"] - row["z"],
            "residual_mev": energy_target(row, constants)
            - energy(coefficients, row["z"], row["a"]),
        }
        for row in records
    ]


def local_correction(z, a, references):
    """Fixed local kernel, max distance five in (Z,N), at least four neighbors.

    Validation uses only the corresponding training fold's residuals.
    Excluding the queried coordinate prevents self-correction in diagnostics.
    """
    n = a - z
    neighbors = []
    for row in references:
        distance_squared = (z - row["z"]) ** 2 + (n - row["n"]) ** 2
        if 0 < distance_squared <= 25:
            neighbors.append((distance_squared, row))
    neighbors.sort(key=lambda item: (item[0], item[1]["id"]))
    neighbors = neighbors[:12]
    if len(neighbors) < 4:
        return 0.0, []
    weights = [(1 + distance) ** -2 for distance, _ in neighbors]
    correction = math.fsum(
        weight * row["residual_mev"] for weight, (_, row) in zip(weights, neighbors)
    ) / math.fsum(weights)
    return correction, [row["id"] for _, row in neighbors]


def error_summary(records, coefficients, constants, residuals_from=None):
    residuals = [
        energy(coefficients, r["z"], r["a"])
        + (
            local_correction(r["z"], r["a"], residuals_from)[0]
            if residuals_from is not None
            else 0
        )
        - energy_target(r, constants)
        for r in records
    ]
    ordered = sorted(abs(value) for value in residuals)
    return {
        "records": len(records),
        "rmse_mev": math.sqrt(math.fsum(x * x for x in residuals) / len(records)),
        "mae_mev": math.fsum(ordered) / len(records),
        "max_absolute_error_mev": ordered[-1],
        "absolute_error_p90_mev": ordered[math.ceil(0.9 * len(ordered)) - 1],
        "rmse_atomic_mass_u": math.sqrt(
            math.fsum(x * x for x in residuals) / len(records)
        )
        / MASS_ENERGY_MEV,
    }


def fit_isotope_model(records, *, minimum_a=16, allow_unverified=False):
    """Fit binding-energy proxy using nonestimated evaluated neutral atomic masses.

    SEMF alone cannot establish an isotope's existence, half-life or spin.
    The complete source records and validation split IDs are retained.
    """
    if type(minimum_a) is not int or minimum_a < 2:
        raise IsotopeFitError("minimum A must be an integer >=2")
    usable, excluded, known = [], [], {}
    constants = {
        "hydrogen_mass_u": HYDROGEN_MASS_U,
        "neutron_mass_u": NEUTRON_MASS_U,
        "mass_energy_mev_per_u": MASS_ENERGY_MEV,
        "reference_mass_policy": "dataset H-1/neutron when available, otherwise archived NIST H-1 and CODATA 2022 neutron",
    }
    seen = set()
    for row in records:
        z, a, _ = coordinates(row["z"], row["a"], row.get("isomer", 0))
        reason = None
        if (
            row.get("property", "atomic_mass") != "atomic_mass"
            or row.get("unit", "u") != "u"
        ):
            reason = "not a neutral atomic mass in u"
        elif row.get("isomer", 0) != 0:
            reason = "excited state"
        elif row.get("estimated", False):
            reason = "source mass estimated from systematics"
        elif row.get("provenance_class") not in ("measured", "curated"):
            reason = "not observed/evaluated evidence"
        elif row.get("review_status") != "reviewed" and not allow_unverified:
            reason = "pending scientific review"
        if reason:
            excluded.append({"id": row.get("id"), "reason": reason})
            continue
        if not row.get("id") or not row.get("source"):
            raise IsotopeFitError(
                "every training mass requires an ID and source citation"
            )
        if type(row["value"]) not in (str, int):
            raise IsotopeFitError(
                "training masses require exact numeric strings or integers"
            )
        value = Fraction(row["value"])
        if value <= 0:
            raise IsotopeFitError("atomic masses must be positive")
        key = f"{z}:{a}"
        if key in seen:
            raise IsotopeFitError(
                "duplicate isotope masses; select one evaluation before fitting"
            )
        seen.add(key)
        known[key] = row
        if (z, a) == (1, 1):
            constants["hydrogen_mass_u"] = float(value)
        if (z, a) == (0, 1):
            constants["neutron_mass_u"] = float(value)
        if z == 0 or a < minimum_a:
            excluded.append(
                {
                    "id": row["id"],
                    "reason": "outside fitted light-nucleus range; retained as reference",
                }
            )
        else:
            usable.append(row)
    usable.sort(key=lambda row: (row["z"], row["a"]))
    if len(usable) < 30:
        raise IsotopeFitError(
            "at least thirty eligible masses needed for fit plus holdout validation"
        )
    holdout = [
        row
        for row in usable
        if int(
            hashlib.sha256(
                f"isotope-fit-v1:{row['z']}:{row['a']}".encode()
            ).hexdigest(),
            16,
        )
        % 5
        == 0
    ]
    held_ids = {row["id"] for row in holdout}
    training = [row for row in usable if row["id"] not in held_ids]
    if len(holdout) < 5 or len(training) < 10:
        raise IsotopeFitError("insufficient independent holdout design")
    validation_coefficients = fit_coefficients(training, constants)
    validation_residuals = residual_references(
        training, validation_coefficients, constants
    )
    chains = {}
    for row in usable:
        chains.setdefault(row["z"], []).append(row)
    edges = [
        row
        for chain in chains.values()
        if len(chain) >= 5
        for row in (chain[0], chain[-1])
    ]
    edge_ids = {row["id"] for row in edges}
    inner = [row for row in usable if row["id"] not in edge_ids]
    edge_validation = None
    if len(edges) >= 5 and len(inner) >= 10:
        edge_coefficients = fit_coefficients(inner, constants)
        edge_residuals = residual_references(inner, edge_coefficients, constants)
        edge_validation = dict(
            error_summary(edges, edge_coefficients, constants, edge_residuals),
            holdout_ids=sorted(edge_ids),
        )
    coefficients = fit_coefficients(usable, constants)
    final_residuals = residual_references(usable, coefficients, constants)
    return {
        "algorithm": "liquid_drop_with_local_residual_atomic_mass",
        "algorithm_version": "1.0.0",
        "provenance_class": "modeled",
        "model_review_status": "unreviewed",
        "training_review_status": "reviewed"
        if all(r["review_status"] == "reviewed" for r in usable)
        else "pending_human_review",
        "terms": TERMS,
        "coefficients_mev": dict(zip(TERMS, coefficients)),
        "constants": constants,
        "residual_correction": {
            "method": "local weighted interpolation in Z,N; no correction with fewer than four neighbors within distance five",
            "maximum_neighbors": 12,
            "maximum_distance": 5,
            "weight": "1/(1+distance_squared)^2",
            "references": final_residuals,
        },
        "minimum_a": minimum_a,
        "training_records": usable,
        "training_sha256": hashlib.sha256(
            json.dumps(usable, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "known_atomic_masses": known,
        "excluded": excluded,
        "domain": {
            "z_min": min(r["z"] for r in usable),
            "z_max": max(r["z"] for r in usable),
            "a_min": min(r["a"] for r in usable),
            "a_max": max(r["a"] for r in usable),
            "n_over_z_min": min((r["a"] - r["z"]) / r["z"] for r in usable),
            "n_over_z_max": max((r["a"] - r["z"]) / r["z"] for r in usable),
        },
        "diagnostics": {
            "training": error_summary(usable, coefficients, constants, final_residuals),
            "baseline_training": error_summary(usable, coefficients, constants),
            "baseline_coordinate_holdout": error_summary(
                holdout, validation_coefficients, constants
            ),
            "coordinate_holdout": dict(
                error_summary(
                    holdout, validation_coefficients, constants, validation_residuals
                ),
                holdout_ids=sorted(held_ids),
                training_ids=sorted(r["id"] for r in training),
            ),
            "isotope_chain_edge_holdout": edge_validation,
        },
        "limitations": [
            "Atomic binding-energy proxy neglects total electronic binding correction; not exact nuclear binding energy",
            "No prediction of half-life, decay branches, spin, radius, excited levels or natural abundance",
            "A fitted mass does not demonstrate that a nucleus exists or is bound",
            "Known-mass holdout errors do not calibrate unknown far-extrapolation error",
            "Local residual interpolation only approximates observed shell/deformation trends; abrupt drip-line behavior remains unsupported",
        ],
        "references": REFERENCES,
    }


def predict_isotope(model, z, a, *, isomer=0, allow_extrapolation=False):
    z, a, n = coordinates(z, a, isomer)
    if isomer:
        raise IsotopeFitError("ground-state model cannot predict excited-state masses")
    known = model["known_atomic_masses"].get(f"{z}:{a}")
    if known is not None:
        return {
            "z": z,
            "a": a,
            "n": n,
            "status": "source_reference",
            "atomic_mass_u": known["value"],
            "source_record": known,
            "provenance_class": known["provenance_class"],
            "review_status": known["review_status"],
        }
    if z == 0 or z > 118 or a > 400 or a < model["minimum_a"]:
        raise IsotopeFitError(
            "unsupported coordinates: unknown light nuclei, neutron clusters, Z>118 or A>400"
        )
    domain = model["domain"]
    extrapolated = not (
        domain["z_min"] <= z <= domain["z_max"]
        and domain["a_min"] <= a <= domain["a_max"]
        and domain["n_over_z_min"] <= n / z <= domain["n_over_z_max"]
    )
    if extrapolated and not allow_extrapolation:
        raise IsotopeFitError(
            "outside fitted domain; explicit allow_extrapolation required"
        )
    coefficients = [model["coefficients_mev"][term] for term in TERMS]
    correction, neighbor_ids = local_correction(
        z, a, model["residual_correction"]["references"]
    )
    b = energy(coefficients, z, a) + correction
    atomic_mass = (
        z * model["constants"]["hydrogen_mass_u"]
        + n * model["constants"]["neutron_mass_u"]
        - b / MASS_ENERGY_MEV
    )
    if not math.isfinite(atomic_mass) or atomic_mass <= 0:
        raise IsotopeFitError("model produced a nonphysical mass")
    separation = {}
    if a - 1 >= model["minimum_a"] and n > 0:
        separation["neutron_mev"] = (
            b
            - energy(coefficients, z, a - 1)
            - local_correction(z, a - 1, model["residual_correction"]["references"])[0]
        )
    if a - 1 >= model["minimum_a"] and z > 1:
        separation["proton_proxy_mev"] = (
            b
            - energy(coefficients, z - 1, a - 1)
            - local_correction(
                z - 1, a - 1, model["residual_correction"]["references"]
            )[0]
        )
    return {
        "z": z,
        "a": a,
        "n": n,
        "isomer": 0,
        "status": "approximation",
        "provenance_class": "modeled",
        "atomic_mass_u": atomic_mass,
        "atomic_mass_kg": atomic_mass * 1.66053906892e-27,
        "mass_excess_mev": (atomic_mass - a) * MASS_ENERGY_MEV,
        "binding_energy_proxy_mev": b,
        "binding_energy_proxy_per_nucleon_mev": b / a,
        "separation_energy_proxy": separation,
        "local_residual_correction_mev": correction,
        "local_neighbor_ids": neighbor_ids,
        "local_correction_supported": bool(neighbor_ids),
        "extrapolated": extrapolated,
        "error_context": None
        if extrapolated
        else {
            "kind": "empirical known-isotope holdout error; not predictive uncertainty",
            "atomic_mass_absolute_error_p90_u": model["diagnostics"][
                "coordinate_holdout" if neighbor_ids else "baseline_coordinate_holdout"
            ]["absolute_error_p90_mev"]
            / MASS_ENERGY_MEV,
        },
        "unavailable": [
            "half_life",
            "decay_modes",
            "spin_parity",
            "radius",
            "abundance",
            "existence_or_stability",
        ],
        "training_sha256": model["training_sha256"],
        "limitations": model["limitations"],
    }


def load_core_masses(database=ROOT / "universe.db"):
    with closing(
        sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)
    ) as db:
        return [
            {
                "id": identifier,
                "z": z,
                "a": z + n,
                "isomer": isomer,
                "property": "atomic_mass",
                "unit": "u",
                "value": str(Fraction(numerator, denominator)),
                "source": url,
                "provenance_class": provenance,
                "review_status": "reviewed",
                "estimated": False,
                "method": method,
            }
            for identifier, z, n, isomer, numerator, denominator, url, provenance, method in db.execute(
                "SELECT o.observation_id,n.proton_count,n.neutron_count,n.isomer_index,o.value_numerator,o.value_denominator,s.url,o.provenance_class,o.method FROM nuclide n JOIN observation o ON n.entity_id=o.subject_entity_id JOIN source s USING(source_id) WHERE o.property_id='property:relative_atomic_mass' ORDER BY n.proton_count,n.neutron_count"
            )
        ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "universe.db")
    parser.add_argument("--research-database", type=Path)
    parser.add_argument("--allow-unverified", action="store_true")
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".build/isotope-model.json"
    )
    parser.add_argument("--predict", nargs=2, type=int, metavar=("Z", "A"))
    parser.add_argument("--allow-extrapolation", action="store_true")
    args = parser.parse_args()
    if args.research_database:
        try:
            from scripts.build_isotope_evidence import load_training_masses
        except ModuleNotFoundError:
            from build_isotope_evidence import load_training_masses
        records = load_training_masses(args.research_database)
    else:
        records = load_core_masses(args.database)
    model = fit_isotope_model(records, allow_unverified=args.allow_unverified)
    result = {"model": model}
    if args.predict:
        result["prediction"] = predict_isotope(
            model, *args.predict, allow_extrapolation=args.allow_extrapolation
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                name: None
                if values is None
                else {
                    key: value
                    for key, value in values.items()
                    if not key.endswith("_ids")
                }
                for name, values in model["diagnostics"].items()
            },
            indent=2,
        )
    )
    print("Model:", args.output)


if __name__ == "__main__":
    main()
