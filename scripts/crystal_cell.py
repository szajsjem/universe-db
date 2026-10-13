#!/usr/bin/env python3
"""Conservative, exact symmetry expansion of unreviewed crystal evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shlex
import sqlite3
from collections import defaultdict
from contextlib import closing
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "crystal-cell-v1"


def parse_operation(operation):
    """Parse three rational affine coordinates without evaluating Python code."""
    coordinates = operation.replace(" ", "").lower().split(",")
    if len(coordinates) != 3:
        raise ValueError("symmetry operation requires three coordinates")
    result = []
    for expression in coordinates:
        terms = re.findall(r"[+-]?[^+-]+", expression)
        if not terms or "".join(terms) != expression:
            raise ValueError("invalid symmetry expression")
        coefficients = [Fraction(0)] * 3
        offset = Fraction(0)
        for term in terms:
            match = re.fullmatch(r"([+-]?)(?:(\d+(?:/\d+)?)\*?)?([xyz])", term)
            if match:
                coefficient = Fraction(match[2] or "1")
                if match[1] == "-":
                    coefficient = -coefficient
                coefficients["xyz".index(match[3])] += coefficient
            elif re.fullmatch(r"[+-]?\d+(?:/\d+)?", term):
                offset += Fraction(term)
            else:
                raise ValueError("unsupported symmetry term: " + term)
        result.append((tuple(coefficients), offset))
    matrix = [row[0] for row in result]
    determinant = sum(
        matrix[0][i]
        * (
            matrix[1][(i + 1) % 3] * matrix[2][(i + 2) % 3]
            - matrix[1][(i + 2) % 3] * matrix[2][(i + 1) % 3]
        )
        for i in range(3)
    )
    if abs(determinant) != 1 or any(v.denominator != 1 for row in matrix for v in row):
        raise ValueError("operation must have an integer unimodular linear part")
    return tuple(result)


def apply_operation(operation, coordinates):
    return tuple(
        (sum(c * v for c, v in zip(coefficients, coordinates)) + offset) % 1
        for coefficients, offset in operation
    )


def cif_operations(text):
    """Read explicit symmetry loops in the pinned simple CIF subset only."""
    lines = text.splitlines()
    found = []
    index = 0
    while index < len(lines):
        if lines[index].strip().lower() != "loop_":
            index += 1
            continue
        index += 1
        tags = []
        while index < len(lines) and lines[index].strip().startswith("_"):
            tags.append(lines[index].strip().lower())
            index += 1
        relevant = [
            i
            for i, tag in enumerate(tags)
            if tag in ("_symmetry_equiv_pos_as_xyz", "_space_group_symop_operation_xyz")
        ]
        tokens = []
        while index < len(lines):
            line = lines[index].strip()
            if line.startswith(("_", "loop_", "data_", "save_")):
                break
            if line.startswith(";") and relevant:
                raise ValueError("multiline symmetry loops are unsupported")
            if relevant:
                tokens.extend(shlex.split(line, comments=True))
            index += 1
        if relevant:
            if len(tokens) % len(tags):
                raise ValueError("incomplete symmetry loop")
            found.extend(tokens[i] for i in range(relevant[0], len(tokens), len(tags)))
    return found


def formula_counts(formula):
    """Accept only unambiguous flat integral formulas; reject unsupported notation."""
    tokens = re.findall(r"([A-Z][a-z]?)(\d*)", formula)
    if not tokens or "".join(symbol + count for symbol, count in tokens) != formula:
        raise ValueError("unsupported formula notation")
    counts = defaultdict(int)
    for element, count in tokens:
        amount = int(count or "1")
        if amount <= 0:
            raise ValueError("formula counts must be positive")
        counts[{"D": "H-2", "T": "H-3"}.get(element, element)] += amount
    return dict(counts)


def audit_structure(structure, operations=None, masses=None):
    """Return an unverified derived audit; masses are cited exact u values by key.

    Isotope keys use e.g. H-2, natural-composition masses use H. A mass entry is
    {'value': exact-string, 'source': citation}; isotope A is never used as mass.
    """
    report = {
        "structure_id": structure.get("id"),
        "algorithm": VERSION,
        "review_status": "pending_human_review",
        "blocked_reasons": [],
        "conflicts": [],
        "expanded_sites": [],
        "cell_composition": None,
        "formula_z_matches": None,
        "density": None,
    }
    blocked = report["blocked_reasons"]
    sites = structure.get("sites", [])
    convention = structure.get("site_convention")
    ops = operations if operations is not None else structure.get("symmetry_operations")
    if not sites:
        blocked.append("no atomic sites")
        return report
    if convention == "full_cell":
        parsed = [parse_operation("x,y,z")]
    elif convention == "asymmetric_unit" and ops:
        parsed = [parse_operation(operation) for operation in ops]
    else:
        blocked.append("explicit symmetry operations/site convention required")
        return report
    report["operation_count"] = len(parsed)
    composition = defaultdict(Fraction)
    positions = defaultdict(list)
    for site in sites:
        coordinates = tuple(Fraction(site[key]) for key in "xyz")
        orbit = sorted(
            {apply_operation(operation, coordinates) for operation in parsed}
        )
        multiplicity = site.get("multiplicity")
        if multiplicity is not None and len(orbit) != multiplicity:
            report["conflicts"].append("multiplicity mismatch: " + site["label"])
        isotope = site.get("isotope_mass_number")
        key = site["element"] + ("-" + str(isotope) if isotope is not None else "")
        occupancy = site.get("occupancy")
        if occupancy is None:
            blocked.append("unknown occupancy: " + site["label"])
        else:
            occupancy = Fraction(occupancy)
            if not 0 <= occupancy <= 1:
                raise ValueError("occupancy outside [0,1]")
            composition[key] += occupancy * len(orbit)
        for position in orbit:
            positions[position].append((site["label"], occupancy))
            report["expanded_sites"].append(
                {
                    "label": site["label"],
                    "element": site["element"],
                    "isotope_mass_number": isotope,
                    "position": [str(v) for v in position],
                    "occupancy": None if occupancy is None else str(occupancy),
                }
            )
    for entries in positions.values():
        if len(entries) > 1:
            report["conflicts"].append(
                "overlapping independent site orbits: "
                + ", ".join(label for label, _ in entries)
            )
        if (
            all(occupancy is not None for _, occupancy in entries)
            and sum(occupancy for _, occupancy in entries) > 1
        ):
            report["conflicts"].append("position total occupancy exceeds one")
    if any(reason.startswith("unknown occupancy") for reason in blocked):
        return report
    report["cell_composition"] = {
        key: str(value) for key, value in sorted(composition.items())
    }
    z = structure.get("cell_formula_units")
    if z is None:
        blocked.append("unknown cell formula units Z")
    else:
        try:
            expected = {
                key: Fraction(value * z)
                for key, value in formula_counts(structure["formula"]).items()
            }
            actual = defaultdict(Fraction)
            for key, value in composition.items():
                actual[key if key in expected else key.split("-")[0]] += value
            report["formula_z_matches"] = dict(actual) == expected
            if not report["formula_z_matches"]:
                report["conflicts"].append(
                    "expanded composition differs from formula times Z"
                )
        except ValueError as error:
            blocked.append(str(error))
    lattice = structure.get("lattice_parameters", {})
    if not all(key in lattice for key in ("a", "b", "c", "alpha", "beta", "gamma")):
        blocked.append("incomplete cell metrics")
    elif any(
        lattice[key].get("unit") != ("angstrom" if key in "abc" else "deg")
        for key in lattice
    ):
        blocked.append("unsupported cell metric units")
    elif any(Fraction(lattice[key]["value"]) <= 0 for key in "abc") or any(
        not 0 < Fraction(lattice[key]["value"]) < 180
        for key in ("alpha", "beta", "gamma")
    ):
        report["conflicts"].append("invalid cell metric")
    else:
        ca, cb, cg = [
            math.cos(math.radians(float(Fraction(lattice[key]["value"]))))
            for key in ("alpha", "beta", "gamma")
        ]
        determinant = 1 + 2 * ca * cb * cg - ca * ca - cb * cb - cg * cg
        if determinant <= 0:
            report["conflicts"].append("nonpositive cell Gram determinant")
        else:
            volume = math.prod(
                float(Fraction(lattice[key]["value"])) for key in "abc"
            ) * math.sqrt(determinant)
            report["volume_angstrom3"] = volume
            if masses is None or any(
                key not in masses or not masses[key].get("source")
                for key in composition
            ):
                blocked.append(
                    "cited isotope/natural-composition atomic masses required"
                )
            elif not blocked and not report["conflicts"]:
                mass_u = sum(
                    value * Fraction(masses[key]["value"])
                    for key, value in composition.items()
                )
                if mass_u <= 0 or any(
                    Fraction(masses[key]["value"]) <= 0 for key in composition
                ):
                    raise ValueError("atomic masses must be positive")
                report["density"] = {
                    "value": float(mass_u) * 1.66053906892 / volume,
                    "unit": "g/cm3",
                    "provenance_class": "modeled",
                    "atomic_mass_constant_kg": "1.66053906892e-27",
                    "constant_source": "CODATA 2022; repository scripts/calculate_properties.py",
                    "mass_inputs": {key: masses[key] for key in sorted(composition)},
                    "temperature_k": structure.get("temperature_k"),
                    "pressure_pa": structure.get("pressure_pa"),
                    "uncertainty": None,
                    "approximation": "floating trigonometry; uncertainties not propagated",
                }
    return report


def audit_database(path, root=ROOT):
    results = []
    with closing(
        sqlite3.connect(f"file:{Path(path).resolve().as_posix()}?mode=ro", uri=True)
    ) as connection:
        sources = {
            key: json.loads(raw)
            for key, raw in connection.execute(
                "SELECT source_id,input_json FROM unverified_crystal_source"
            )
        }
        for (raw,) in connection.execute(
            "SELECT input_json FROM unverified_crystal_structure ORDER BY structure_id"
        ):
            structure = json.loads(raw)
            source = sources[structure["source_id"]]
            try:
                ops = structure.get("symmetry_operations")
                if source.get("source_file"):
                    pinned = (Path(root) / source["source_file"]).resolve()
                    if not pinned.is_relative_to(Path(root).resolve()):
                        raise ValueError("source path outside repository")
                    content = pinned.read_bytes()
                    if hashlib.sha256(content).hexdigest() != source.get("sha256"):
                        raise ValueError("source SHA256 mismatch")
                    source_ops = cif_operations(content.decode("utf-8"))
                    if ops and source_ops and set(ops) != set(source_ops):
                        raise ValueError("structure operations differ from source CIF")
                    ops = source_ops or ops
                results.append(audit_structure(structure, operations=ops))
            except (ValueError, OSError, ZeroDivisionError) as error:
                results.append(
                    {
                        "structure_id": structure["id"],
                        "algorithm": VERSION,
                        "blocked_reasons": [str(error)],
                        "density": None,
                    }
                )
    return {
        "algorithm": VERSION,
        "structures": results,
        "summary": {
            "structures": len(results),
            "expanded": sum(bool(row.get("expanded_sites")) for row in results),
            "composition_known": sum(
                row.get("cell_composition") is not None for row in results
            ),
            "formula_z_matches": sum(
                row.get("formula_z_matches") is True for row in results
            ),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "crystals.db")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = json.dumps(audit_database(args.db), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
