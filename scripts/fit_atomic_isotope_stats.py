"""Empirical neutral ground-state isotope lifetime and decay-vector approximation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path

if __package__:
    from .normalize_nuclear_properties import (
        decay_token,
        normalize_database,
        write_report,
    )
else:
    from normalize_nuclear_properties import (
        decay_token,
        normalize_database,
        write_report,
    )

VERSION = "neutral-isotope-local-kernel-1"
MODES = {
    "A": "alpha",
    "B-": "beta_minus",
    "B+": "beta_plus_or_electron_capture",
    "EC": "electron_capture",
    "n": "neutron",
    "p": "proton",
    "2n": "two_neutron",
    "2p": "two_proton",
}


def exact(value):
    return Fraction(int(value["numerator"]), int(value["denominator"]))


def complete_branches(text, z, a):
    """Require every source token, exact equalities, unique modes and exact unit sum."""
    tokens = [decay_token(token.strip(), z, a) for token in text.split(";")]
    if not tokens or any(
        t is None or t["estimated"] or t["branch_relation"] != "=" for t in tokens
    ):
        return None
    if len({t["mode"] for t in tokens}) != len(tokens) or {"B+", "EC"} <= {
        t["mode"] for t in tokens
    }:
        return None
    if sum((exact(t["branch_fraction"]) for t in tokens), Fraction()) != 1:
        return None
    return {MODES[t["mode"]]: t["branch_fraction"] for t in tokens}


def load_records(database):
    report = normalize_database(database)
    states = {
        (s["z"], s["a"]): s
        for s in report["states"]
        if s["state_index"] == 0 and not s["withdrawn"]
    }
    records = {
        key: {
            "z": key[0],
            "n": key[1] - key[0],
            "a": key[1],
            "state_index": 0,
            "half_life": None,
            "stability": None,
            "branches": None,
            "sources": [],
        }
        for key in states
    }
    for row in report["records"]:
        key = (row["z"], row["a"])
        if row["state_index"] != 0 or key not in records:
            continue
        target = records[key]
        prop, typed = row["property"], row["typed"]
        if prop == "half_life":
            target["half_life"] = typed
        elif prop == "stability":
            target["stability"] = typed["stability"]
        elif prop == "decay_modes" and not row["estimated"]:
            target["branches"] = complete_branches(row["raw_text"], row["z"], row["a"])
        else:
            continue
        target["sources"].append(
            {
                "observation_id": row["observation_id"],
                "source_id": row["source_id"],
                "source_locator": row["source_locator"],
                "raw_text": row["raw_text"],
            }
        )
    return list(records.values()), {
        "input_sha256": report["input_sha256"],
        "sources": report["sources"],
        "normalization_algorithm": report["algorithm"],
        "review_status": "pending_human_review",
    }


def lifetime_training(record):
    value = record.get("half_life")
    return bool(
        value
        and value["value_kind"] == "point"
        and not value["estimated"]
        and record.get("stability") != "stable"
    )


def fit_model(
    records,
    source_metadata=None,
    radius=5,
    k=12,
    min_neighbors=4,
    validate=True,
    allow_unverified=False,
):
    if (source_metadata or {}).get(
        "review_status"
    ) == "pending_human_review" and not allow_unverified:
        raise ValueError(
            "training source is unverified; explicitly allow unverified evidence"
        )
    if (
        not isinstance(radius, (int, float))
        or not math.isfinite(radius)
        or type(k) is not int
        or type(min_neighbors) is not int
        or radius <= 0
        or k < min_neighbors
        or min_neighbors < 2
    ):
        raise ValueError("invalid kernel parameters")
    for record in records:
        z, n = record["z"], record["n"]
        if (
            type(z) is not int
            or type(n) is not int
            or min(z, n) < 0
            or z + n < 1
            or type(record["a"]) is not int
            or record["a"] != z + n
            or type(record["state_index"]) is not int
            or record["state_index"] != 0
        ):
            raise ValueError("invalid ground-state training identity")
        if record.get("half_life") and exact(record["half_life"]["value"]) <= 0:
            raise ValueError("lifetime must be positive")
        if record.get("branches") is not None:
            branches = record["branches"]
            if (
                not branches
                or any(
                    mode not in MODES.values() or not 0 <= exact(value) <= 1
                    for mode, value in branches.items()
                )
                or sum((exact(value) for value in branches.values()), Fraction()) != 1
                or {"beta_plus_or_electron_capture", "electron_capture"}
                <= set(branches)
            ):
                raise ValueError("invalid complete decay vector")
    keys = [(r["z"], r["n"]) for r in records]
    if len(set(keys)) != len(keys) or not records:
        raise ValueError("training identities must be nonempty and unique")
    payload = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    model = {
        "algorithm": VERSION,
        "provenance_class": "modeled",
        "review_status": "unverified",
        "records_sha256": hashlib.sha256(payload).hexdigest(),
        "source_metadata": source_metadata or {},
        "kernel": {"radius": radius, "k": k, "min_neighbors": min_neighbors},
        "records": records,
        "domain": {
            axis: [min(r[axis] for r in records), max(r[axis] for r in records)]
            for axis in ("z", "n")
        },
        "electron_identifiability": "Only neutral atoms: electrons equal protons. Electron dependence is not fitted.",
        "limitations": [
            "No existence or stability prediction",
            "No isomers or ions",
            "No gamma probability: IT and photon yields are not gamma branch fractions",
            "Local interpolation is not a decay-law model; incomplete decay expressions are excluded",
            "Validation residuals are empirical errors, not prediction confidence intervals",
            "Absent modes in a modeled admitted complete vector have zero weight only within that represented vector",
        ],
    }
    if validate:
        model["validation"] = validate_model(records, model)
    return model


def neighbors(model, z, n, property_name):
    eligible = []
    for row in model["records"]:
        if (row["z"], row["n"]) == (z, n):
            continue
        if property_name == "half_life" and not lifetime_training(row):
            continue
        if property_name == "branches" and row.get("branches") is None:
            continue
        distance = math.hypot(row["z"] - z, row["n"] - n)
        if distance <= model["kernel"]["radius"]:
            eligible.append((distance, row))
    eligible.sort(key=lambda pair: (pair[0], pair[1]["z"], pair[1]["n"]))
    eligible = eligible[: model["kernel"]["k"]]
    if len(eligible) < model["kernel"]["min_neighbors"]:
        return []
    weights = [1 / distance**2 for distance, _ in eligible]
    total = math.fsum(weights)
    return [
        (row, weight / total, distance)
        for (distance, row), weight in zip(eligible, weights)
    ]


def predict(
    model,
    protons,
    neutrons,
    electrons=None,
    state_index=0,
    use_known=True,
    approximate_missing=False,
):
    electrons = protons if electrons is None else electrons
    if (
        any(type(x) is not int for x in (protons, neutrons, electrons, state_index))
        or min(protons, neutrons, electrons) < 0
        or protons + neutrons < 1
    ):
        raise ValueError("p, n, e and state index must be valid integers")
    if electrons != protons:
        raise ValueError(
            "ion lifetime/electron effects are not identifiable from neutral training data"
        )
    if state_index != 0:
        raise ValueError("isomer/state predictions are unsupported")
    result = {
        "composition": {
            "protons": protons,
            "neutrons": neutrons,
            "electrons": electrons,
            "state_index": 0,
        },
        "algorithm": model["algorithm"],
        "model_records_sha256": model["records_sha256"],
        "half_life": None,
        "decay_probabilities": None,
        "gamma_probability": None,
        "gamma_status": "unavailable",
        "existence_status": "not_predicted",
        "review_status": "unverified",
    }
    known = (
        next(
            (r for r in model["records"] if (r["z"], r["n"]) == (protons, neutrons)),
            None,
        )
        if use_known
        else None
    )
    if known:
        result.update(
            status="source_reference",
            provenance_class="curated",
            half_life=known["half_life"],
            stability=known["stability"],
            decay_probabilities=known["branches"],
            sources=known["sources"],
        )
        if known["stability"] == "stable":
            result["half_life"] = None
        result["half_life_status"] = (
            "stable"
            if known["stability"] == "stable"
            else "source_reference"
            if known["half_life"]
            else "missing_source_value"
        )
        result["decay_probabilities_status"] = (
            "source_complete_vector"
            if known["branches"] is not None
            else "unavailable_complete_vector"
        )
        if approximate_missing and (
            (known["half_life"] is None and known["stability"] != "stable")
            or known["branches"] is None
        ):
            modeled = predict(
                model, protons, neutrons, electrons, state_index, use_known=False
            )
            result["missing_stat_approximations"] = {
                "provenance_class": "modeled",
                "status": modeled["status"],
                "half_life": modeled["half_life"]
                if known["half_life"] is None and known["stability"] != "stable"
                else None,
                "decay_probabilities": modeled["decay_probabilities"]
                if known["branches"] is None and known["stability"] != "stable"
                else None,
                "neighbor_trace": modeled.get("neighbor_trace", {}),
            }
        return result
    if any(
        not model["domain"][axis][0] <= value <= model["domain"][axis][1]
        for axis, value in (("z", protons), ("n", neutrons))
    ):
        result.update(status="outside_training_domain", provenance_class="modeled")
        return result
    result.update(
        status="modeled",
        provenance_class="modeled",
        stability="not_predicted",
        neighbor_trace={},
    )
    for prop in ("half_life", "branches"):
        nearby = neighbors(model, protons, neutrons, prop)
        result["neighbor_trace"][prop] = [
            {
                "z": r["z"],
                "n": r["n"],
                "weight": w,
                "distance": d,
                "sources": r["sources"],
            }
            for r, w, d in nearby
        ]
        if not nearby:
            continue
        if prop == "half_life":
            log_value = math.fsum(
                w
                * (
                    math.log10(exact(r["half_life"]["value"]).numerator)
                    - math.log10(exact(r["half_life"]["value"]).denominator)
                )
                for r, w, _ in nearby
            )
            result["half_life"] = {
                "log10_seconds": log_value,
                "seconds": 10**log_value,
                "value_kind": "modeled_point",
                "unit": "s",
            }
        else:
            modes = sorted({mode for r, _, _ in nearby for mode in r["branches"]})
            result["decay_probabilities"] = {
                mode: math.fsum(
                    w * float(exact(r["branches"][mode]))
                    for r, w, _ in nearby
                    if mode in r["branches"]
                )
                for mode in modes
            }
    if result["half_life"] is None and result["decay_probabilities"] is None:
        result["status"] = "insufficient_local_support"
    return result


def validate_model(records, template):
    reports = {}
    splits = {
        "coordinate_holdout": lambda r: (r["z"] * 17 + r["n"] * 31) % 5 == 0,
        "leave_element_out": lambda r: r["z"] % 5 == 0,
    }
    for name, withheld in splits.items():
        training, heldout = (
            [r for r in records if not withheld(r)],
            [r for r in records if withheld(r)],
        )
        if not training:
            reports[name] = {"status": "insufficient_training"}
            continue
        model = fit_model(
            training,
            template["source_metadata"],
            **template["kernel"],
            validate=False,
            allow_unverified=True,
        )
        lifetime_errors, branch_errors, evaluated = [], [], []
        for row in heldout:
            prediction = predict(model, row["z"], row["n"], use_known=False)
            entry = {"z": row["z"], "n": row["n"], "status": prediction["status"]}
            if lifetime_training(row) and prediction["half_life"]:
                value = exact(row["half_life"]["value"])
                error = prediction["half_life"]["log10_seconds"] - (
                    math.log10(value.numerator) - math.log10(value.denominator)
                )
                lifetime_errors.append(error)
                entry["lifetime_log10_error"] = error
            if (
                row.get("branches") is not None
                and prediction["decay_probabilities"] is not None
            ):
                modes = set(row["branches"]) | set(prediction["decay_probabilities"])
                error = (
                    math.fsum(
                        abs(
                            prediction["decay_probabilities"].get(mode, 0)
                            - (
                                float(exact(row["branches"][mode]))
                                if mode in row["branches"]
                                else 0
                            )
                        )
                        for mode in modes
                    )
                    / 2
                )
                branch_errors.append(error)
                entry["branch_total_variation"] = error
            evaluated.append(entry)
        reports[name] = {
            "training_count": len(training),
            "heldout_count": len(heldout),
            "lifetime_predicted_count": len(lifetime_errors),
            "lifetime_log10_rmse": math.sqrt(
                math.fsum(e * e for e in lifetime_errors) / len(lifetime_errors)
            )
            if lifetime_errors
            else None,
            "branch_predicted_count": len(branch_errors),
            "branch_mean_total_variation": math.fsum(branch_errors) / len(branch_errors)
            if branch_errors
            else None,
            "heldout_results": evaluated,
            "heldout_identities": [[r["z"], r["n"]] for r in heldout],
            "training_records_sha256": model["records_sha256"],
        }
    return reports


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
    args = parser.parse_args()
    if args.command == "train":
        if args.database.resolve() == args.output.resolve():
            parser.error("output must differ from input database")
        records, metadata = load_records(args.database)
        model = fit_model(
            records, metadata, allow_unverified=args.allow_unverified_evidence
        )
        write_report(model, args.output)
        print(
            json.dumps(
                {
                    "records": len(records),
                    "lifetime_training": sum(map(lifetime_training, records)),
                    "complete_branch_vectors": sum(
                        r["branches"] is not None for r in records
                    ),
                    "validation": {
                        name: {
                            k: v
                            for k, v in report.items()
                            if k not in ("heldout_results", "heldout_identities")
                        }
                        for name, report in model["validation"].items()
                    },
                },
                indent=2,
            )
        )
    else:
        print(
            json.dumps(
                predict(
                    json.loads(args.model.read_text(encoding="utf-8")),
                    args.protons,
                    args.neutrons,
                    args.electrons,
                    approximate_missing=args.approximate_missing,
                ),
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
