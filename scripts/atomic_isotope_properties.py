"""Combine fitted atomic-mass and decay models using integer p/n/e composition."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

if __package__:
    from .build_isotope_evidence import load_training_masses
    from .fit_atomic_isotope_stats import fit_model, load_records, predict
    from .fit_isotope_properties import (
        IsotopeFitError,
        fit_isotope_model,
        predict_isotope,
    )
    from .normalize_nuclear_properties import write_report
else:
    from build_isotope_evidence import load_training_masses
    from fit_atomic_isotope_stats import fit_model, load_records, predict
    from fit_isotope_properties import (
        IsotopeFitError,
        fit_isotope_model,
        predict_isotope,
    )
    from normalize_nuclear_properties import write_report


def fit_atomic_properties(database, *, allow_unverified=False):
    """Fit independent mass/decay targets; source provenance remains attached."""
    records, metadata = load_records(database)
    return {
        "algorithm": "atomic-composition-property-profile-1",
        "input": metadata,
        "mass_model": fit_isotope_model(
            load_training_masses(database), allow_unverified=allow_unverified
        ),
        "decay_model": fit_model(records, metadata, allow_unverified=allow_unverified),
    }


def atomic_properties(
    profile,
    protons,
    neutrons,
    electrons=None,
    *,
    state_index=0,
    approximate_missing=False,
):
    """Source-first neutral-atom statistics; unavailable mass does not hide decay."""
    decay = predict(
        profile["decay_model"],
        protons,
        neutrons,
        electrons,
        state_index,
        approximate_missing=approximate_missing,
    )
    try:
        mass = predict_isotope(
            profile["mass_model"], protons, protons + neutrons, isomer=state_index
        )
    except IsotopeFitError as error:
        mass = {"status": "unavailable", "reason": str(error)}
    return {
        "composition": {
            "protons": protons,
            "neutrons": neutrons,
            "electrons": protons if electrons is None else electrons,
            "mass_number": protons + neutrons,
            "charge_e": 0,
            "state_index": state_index,
        },
        "mass": mass,
        "decay": decay,
        "validation_context": {
            name: {
                key: value
                for key, value in report.items()
                if key not in ("heldout_results", "heldout_identities")
            }
            for name, report in profile["decay_model"].get("validation", {}).items()
        },
        "validation_meaning": "Known-isotope holdout errors, not target confidence intervals; lifetime errors are roughly three log10 units on current data",
        "limitations": [
            "Neutral ground-state training cannot identify independent electron-count effects",
            "Composition alone does not establish existence, stability or decay energetics",
            "Mass and lifetime use independent empirical models; no coupled physics fit",
            "Gamma photon yields, spectra and conversion probabilities require radiation data",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    train = sub.add_parser("train")
    train.add_argument("--database", type=Path, default=Path("isotopes.db"))
    train.add_argument("--output", type=Path, required=True)
    train.add_argument("--allow-unverified-evidence", action="store_true")
    query = sub.add_parser("predict")
    query.add_argument("--model", type=Path, required=True)
    query.add_argument("--protons", type=int, required=True)
    query.add_argument("--neutrons", type=int, required=True)
    query.add_argument("--electrons", type=int)
    query.add_argument("--approximate-missing", action="store_true")
    query.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "train":
        if args.database.resolve() == args.output.resolve():
            parser.error("output must differ from input database")
        profile = fit_atomic_properties(
            args.database, allow_unverified=args.allow_unverified_evidence
        )
        write_report(profile, args.output)
        print("Fitted atomic property profile:", args.output)
    else:
        profile = json.loads(args.model.read_text(encoding="utf-8"))
        result = atomic_properties(
            profile,
            args.protons,
            args.neutrons,
            args.electrons,
            approximate_missing=args.approximate_missing,
        )
        if args.output:
            if args.output.resolve() == args.model.resolve():
                parser.error("prediction output must differ from model file")
            write_report(result, args.output)
        else:
            print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
