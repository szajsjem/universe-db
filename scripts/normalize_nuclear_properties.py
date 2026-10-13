"""Conservative typed NUBASE normalization; all outputs remain unverified."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from fractions import Fraction
from pathlib import Path

if __package__:
    from .import_isotope_nubase import SECOND_FACTORS
else:
    from import_isotope_nubase import SECOND_FACTORS

VERSION = "nubase-normalization-2"
NUM = r"(?:\d+(?:\.\d*)?|\.\d+)"
MODES = {
    "B-": (1, 0),
    "B+": (-1, 0),
    "EC": (-1, 0),
    "A": (-2, -4),
    "n": (0, -1),
    "p": (-1, -1),
    "2n": (0, -2),
    "2p": (-2, -2),
}
MODE_SEMANTICS = {
    "B-": "beta_minus_inclusive",
    "B+": "positron_emission_or_electron_capture_inclusive",
    "EC": "electron_capture",
    "A": "alpha",
    "n": "neutron",
    "p": "proton",
    "2n": "two_neutron",
    "2p": "two_proton",
}
DECAY_NOTATION_SOURCE = "https://www-nds.iaea.org/amdc/ame2020/NUBASE2020.pdf#page=11"


def ratio(value):
    value = Fraction(value)
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def spin_assignment(text):
    match = re.fullmatch(r"(\d+(?:/2)?)([+-])([*#]?)", text)
    if not match:
        return None
    return {
        "spin_hbar": ratio(match[1]),
        "parity": 1 if match[2] == "+" else -1,
        "source_assignment_flag": match[3] or None,
    }


def lifetime(value, unit, uncertainty=""):
    """Read source-native columns; unsupported qualifiers remain explicit."""
    result = {
        "unit": "s",
        "raw_value": value,
        "raw_unit": unit,
        "raw_uncertainty": uncertainty,
        "estimated": "#" in value or "#" in uncertainty,
    }
    match = re.fullmatch(rf"([<>]?)({NUM})#?", value)
    if not match or unit not in SECOND_FACTORS:
        return None
    factor = SECOND_FACTORS[unit]
    point = Fraction(match[2]) * factor
    if point <= 0:
        return None
    result.update(
        value=ratio(point),
        relation=match[1] or "=",
        value_kind="bound" if match[1] else "point",
    )
    cleaned = uncertainty.replace("#", "")
    if not cleaned:
        result["uncertainty_kind"] = "not_reported"
    elif re.fullmatch(NUM, cleaned):
        result.update(
            uncertainty_kind="symmetric", uncertainty=ratio(Fraction(cleaned) * factor)
        )
    else:
        asymmetric = re.fullmatch(rf"\+({NUM})-({NUM})", cleaned)
        if asymmetric:
            result.update(
                uncertainty_kind="asymmetric",
                uncertainty_plus=ratio(Fraction(asymmetric[1]) * factor),
                uncertainty_minus=ratio(Fraction(asymmetric[2]) * factor),
            )
        else:
            result["uncertainty_kind"] = "unsupported"
    return result


def decay_token(text, z, a):
    """Only explicit simple modes; never assign a daughter nuclear state."""
    match = re.fullmatch(rf"(B-|B\+|EC|A|2n|2p|n|p)([=<>])({NUM})(#?)", text)
    if not match:
        return None
    probability = Fraction(match[3]) / 100
    if not 0 <= probability <= 1:
        return None
    dz, da = MODES[match[1]]
    daughter_z, daughter_a = z + dz, a + da
    if daughter_z < 0 or daughter_a < 1 or daughter_z > daughter_a:
        return None
    return {
        "mode": match[1],
        "mode_semantics": MODE_SEMANTICS[match[1]],
        "notation_source": DECAY_NOTATION_SOURCE,
        "disjoint_branch_guaranteed": False,
        "branch_fraction": ratio(probability),
        "branch_relation": match[2],
        "estimated": bool(match[4]),
        "daughter_z": daughter_z,
        "daughter_a": daughter_a,
        "daughter_state": None,
        "daughter_coordinates_basis": "mode conservation only",
        "daughter_role": "primary daughter; later particle emission unresolved"
        if match[1] in ("B-", "B+")
        else "mode daughter; nuclear state unresolved",
        "channel_complete": False,
        "raw_token": text,
    }


def normalize_database(database):
    database = Path(database).resolve()
    records, gaps, states = [], [], []
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        sources = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM unverified_isotope_source WHERE source_id='nubase2020' ORDER BY source_id"
            )
        ]
        if not sources:
            raise ValueError("NUBASE source metadata is required")
        for row in conn.execute(
            "SELECT * FROM unverified_isotope_identity WHERE source_id='nubase2020' ORDER BY z,a,isomer"
        ):
            states.append(
                {
                    "z": row["z"],
                    "a": row["a"],
                    "state_index": row["isomer"],
                    "source_id": row["source_id"],
                    "source_locator": row["source_locator"],
                    "label": row["label"],
                    "note": row["note"],
                    "withdrawn": "non-exist" in row["note"],
                    "state_kind": "unspecified",
                }
            )
        for row in conn.execute(
            "SELECT * FROM unverified_isotope_observation WHERE source_id='nubase2020' AND property IN ('spin_parity','half_life','stability','decay_modes') ORDER BY observation_id"
        ):
            raw = json.loads(row["input_json"])
            source_record = raw.get("source_record", "")
            try:
                source_coordinates = (
                    int(source_record[4:7]),
                    int(source_record[:3]),
                    int(source_record[7]),
                )
            except (ValueError, IndexError) as error:
                raise ValueError(
                    "Missing or malformed source-native state record"
                ) from error
            if source_coordinates != (row["z"], row["a"], row["isomer"]):
                raise ValueError(
                    "Observation identity conflicts with source-native record"
                )
            base = {
                "observation_id": row["observation_id"],
                "source_id": row["source_id"],
                "source_locator": row["source_locator"],
                "z": row["z"],
                "a": row["a"],
                "state_index": row["isomer"],
                "property": row["property"],
                "raw_text": row["text_value"],
                "source_record": raw.get("source_record"),
                "estimated": bool(row["estimated"]),
                "review_status": "pending_human_review",
                "provenance_class": "curated",
            }
            prop, text = row["property"], row["text_value"] or ""
            if prop == "spin_parity":
                typed = spin_assignment(text)
            elif prop == "half_life":
                line = raw.get("source_record", "")
                typed = lifetime(
                    line[69:78].strip(), line[78:80].strip(), line[81:88].strip()
                )
                if typed and typed["uncertainty_kind"] == "unsupported":
                    gaps.append({**base, "reason": "unsupported_uncertainty_qualifier"})
            elif prop == "stability":
                typed = (
                    {"stability": text}
                    if text in ("stable", "particle unstable")
                    else None
                )
            else:
                for token in text.split(";"):
                    token = token.strip()
                    channel = decay_token(token, row["z"], row["a"])
                    if channel:
                        records.append({**base, "typed": channel})
                    else:
                        gaps.append(
                            {
                                **base,
                                "raw_token": token,
                                "reason": "unsupported_decay_or_abundance_syntax",
                            }
                        )
                continue
            if typed is None:
                gaps.append(
                    {**base, "reason": "unsupported_assignment_or_value_syntax"}
                )
            else:
                records.append({**base, "typed": typed})
    return {
        "algorithm": VERSION,
        "input_sha256": hashlib.sha256(database.read_bytes()).hexdigest(),
        "status": "unverified",
        "sources": sources,
        "states": states,
        "records": records,
        "gaps": gaps,
        "counts": {
            "states": len(states),
            "withdrawn_states": sum(s["withdrawn"] for s in states),
            "records": len(records),
            "gaps": len(gaps),
            "records_by_property": dict(
                sorted(Counter(r["property"] for r in records).items())
            ),
        },
        "limitations": [
            "No complete decay channels or daughter state assignments",
            "No branch renormalization or lifetime inferred from stability",
            "Unsupported source syntax retained as gaps",
        ],
    }


def write_report(report, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        dir=output.parent, prefix=output.name, suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(name, output)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("isotopes.db"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.database.resolve() == args.output.resolve():
        parser.error("output must differ from input database")
    report = normalize_database(args.database)
    write_report(report, args.output)
    print(json.dumps(report["counts"], sort_keys=True))


if __name__ == "__main__":
    main()
