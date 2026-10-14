"""Fit independent, explicit-state mechanical targets without inventing evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from .fit_alloy_properties import (
        FitError,
        composition_fractions,
        fit_alloy_approximation,
        predict_alloy,
        state_signature,
    )
    from .mixture_properties import number, packed
else:
    from fit_alloy_properties import (
        FitError,
        composition_fractions,
        fit_alloy_approximation,
        predict_alloy,
        state_signature,
    )
    from mixture_properties import number, packed

UNITS = {
    "tensile_strength": "Pa",
    "compressive_strength": "Pa",
    "yield_strength": "Pa",
    "fracture_toughness": "Pa*sqrt(m)",
    "energy_toughness": "J/m3",
    "elongation_at_break": "1",
}
ALGORITHM = "alloy-mechanical-profile-1"


def fit_mechanical_properties(
    records, *, degree=1, allow_unverified=False, allow_synthetic=False
):
    """Fit each target separately; all targets must describe the same material state.

    Pure constituent endpoints are not required: mechanical alloy specimens do
    not share pure-element microstructure. Rank and source gates still apply.
    No automatic extraction of nominal grade recipes or composition midpoints.
    """
    if not isinstance(records, list) or not records:
        raise FitError("provide mechanical training records")
    if len(records) > 4096:
        raise FitError("mechanical profile supports at most 4096 records")
    groups = {}
    states = set()
    identifiers = set()
    for row in records:
        if not isinstance(row, dict):
            raise FitError("training record must be an object")
        prop = row.get("property")
        if prop not in UNITS or row.get("unit") != UNITS[prop]:
            raise FitError("unsupported mechanical target or unit")
        identifier = row.get("id")
        if (
            not isinstance(identifier, str)
            or not identifier
            or identifier in identifiers
        ):
            raise FitError("profile requires globally unique observation IDs")
        identifiers.add(identifier)
        value = number(row.get("value"), "mechanical value")
        if value < 0 or (prop != "elongation_at_break" and value == 0):
            raise FitError("nonphysical mechanical training value")
        states.add(state_signature(row.get("conditions")))
        groups.setdefault(prop, []).append(row)
    if len(states) != 1:
        raise FitError(
            "profile targets must describe the same processing and measurement state"
        )
    models = {
        prop: fit_alloy_approximation(
            sorted(rows, key=lambda row: row["id"]),
            degree=degree,
            require_pure_elements=False,
            allow_unverified=allow_unverified,
            allow_synthetic=allow_synthetic,
        )
        for prop, rows in sorted(groups.items())
    }
    # Digest covers the portable payload, including all citations and diagnostics.
    payload = {
        "schema_version": 1,
        "algorithm": ALGORITHM,
        "conditions": models[next(iter(models))]["conditions"],
        "models": models,
        "brittleness_policy": {
            "algorithm": "inverse-ductility-index-1",
            "reference_strain": "1/20",
            "meaning": "Authored dimensionless index, not measured brittleness",
        },
    }
    payload["profile_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return payload


def mechanical_properties(profile, mass_fractions, *, conditions):
    if profile.get("schema_version") != 1 or profile.get("algorithm") != ALGORITHM:
        raise FitError("unsupported mechanical profile")
    composition_fractions(mass_fractions)
    if state_signature(conditions) != state_signature(profile["conditions"]):
        raise FitError("prediction conditions differ from fitted state")
    values, unavailable = {}, {}
    for prop, unit in UNITS.items():
        model = profile["models"].get(prop)
        if model is None:
            unavailable[prop] = "no fitted evidence for this target"
            continue
        if model["property"] != prop or model["unit"] != unit:
            raise FitError("model target or unit differs from profile contract")
        try:
            result = predict_alloy(model, mass_fractions, conditions=conditions)
            value = number(f"{result['numerator']}/{result['denominator']}", prop)
            if value < 0 or (prop != "elongation_at_break" and value == 0):
                raise FitError("nonphysical fitted mechanical response")
            values[prop] = result
        except FitError as error:
            unavailable[prop] = str(error)
    strain = values.get("elongation_at_break")
    if strain:
        policy = profile["brittleness_policy"]
        if policy["algorithm"] != "inverse-ductility-index-1":
            raise FitError("unsupported brittleness policy")
        reference = number(policy["reference_strain"], "reference strain")
        if reference <= 0:
            raise FitError("reference strain must be positive")
        epsilon = number(f"{strain['numerator']}/{strain['denominator']}", "strain")
        values["brittleness_index"] = dict(
            packed(reference / (reference + epsilon), "1", policy["algorithm"]),
            provenance_class=strain["provenance_class"],
            meaning=policy["meaning"],
            training_sha256=strain["training_sha256"],
            prediction_uncertainty=None,
            extrapolated=False,
        )
    else:
        unavailable["brittleness_index"] = "requires supported elongation-at-break fit"
    return {
        "profile_sha256": profile["profile_sha256"],
        "values": values,
        "unavailable": unavailable,
        "conditions": conditions,
        "composition_mass_fractions": {
            k: str(v) for k, v in composition_fractions(mass_fractions).items()
        },
        "limitations": [
            "Composition limits are not a phase diagram or a convex-hull check",
            "Processing, heat treatment and measurement conditions must match training",
            "Tensile and compressive strength are independent; neither fills the other",
            "Fracture toughness and energy toughness have different dimensions",
            "Brittleness index is an authored ductility proxy; no uncertainty is inferred",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    train = sub.add_parser("train")
    train.add_argument("--training", type=Path, required=True)
    train.add_argument("--degree", type=int, choices=(1, 2), default=1)
    train.add_argument("--allow-unverified", action="store_true")
    train.add_argument("--allow-synthetic", action="store_true")
    query = sub.add_parser("predict")
    query.add_argument("--model", type=Path, required=True)
    query.add_argument(
        "--input",
        type=Path,
        required=True,
        help="JSON: composition_mass_fractions and conditions",
    )
    for command in (train, query):
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inputs = [args.training] if args.command == "train" else [args.model, args.input]
    if args.output.resolve() in [p.resolve() for p in inputs]:
        parser.error("output must differ from input files")
    if args.command == "train":
        result = fit_mechanical_properties(
            json.loads(args.training.read_text()),
            degree=args.degree,
            allow_unverified=args.allow_unverified,
            allow_synthetic=args.allow_synthetic,
        )
    else:
        profile = json.loads(args.model.read_text())
        query = json.loads(args.input.read_text())
        result = mechanical_properties(
            profile, query["composition_mass_fractions"], conditions=query["conditions"]
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
