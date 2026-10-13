"""Read-only, versioned inventory of scientific data types, not completeness certification."""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "scientific-types-2"
DATABASES = (
    "universe.db",
    "alloys.db",
    "elements.db",
    "isotopes.db",
    "crystals.db",
    "atomic.db",
    "spectra.db",
    "molecules.db",
)
# Explicit vocabulary: unknown properties are reported rather than guessed.
FAMILIES = {
    "spectra": (
        (),
        ("spectrum", "spectrum_point", "spectral_feature", "unverified_spectral_line"),
    ),
    "molecular_graphs": (
        (),
        (
            "molecule",
            "molecular_atom",
            "molecular_bond",
            "unverified_molecular_molecule",
            "unverified_molecular_atom",
            "unverified_molecular_bond",
        ),
    ),
    "atomic_electronic": (
        (
            "ionization_energy",
            "electron_affinity",
            "polarizability",
            "electronegativity",
            "atomic_energy_level",
        ),
        (),
    ),
    "mass_composition": (
        (
            "atomic_mass",
            "relative_atomic_mass",
            "molar_mass",
            "isotopic_composition",
            "isotopic_abundance",
        ),
        (),
    ),
    "nuclear_mass_energy": (
        (
            "mass_excess",
            "mass_excess_energy",
            "binding_energy_per_nucleon",
            "nuclear_binding_energy",
            "nuclear_binding_energy_per_nucleon",
            "excitation_energy",
        ),
        (),
    ),
    "nuclear_lifetime_spin": (
        ("half_life", "spin_parity", "nuclear_spin", "stability"),
        (),
    ),
    "nuclear_decay": (
        ("decay_modes", "decay_probability", "branching_ratio", "decay_q_value"),
        ("nuclear_channel", "nuclear_channel_particle", "nuclear_channel_nuclide"),
    ),
    "nuclear_radii": (
        (
            "charge_radius",
            "nuclear_radius",
            "magnetic_dipole_moment",
            "electric_quadrupole_moment",
        ),
        (),
    ),
    "nuclear_cross_sections": (
        (),
        ("nuclear_cross_section_point", "nuclear_cross_section_velocity_point"),
    ),
    "crystallography": (
        (),
        (
            "crystal_structure",
            "crystal_lattice_parameter",
            "crystal_lattice_site",
            "unverified_crystal_structure",
            "unverified_crystal_lattice_parameter",
            "unverified_crystal_site",
        ),
    ),
    "thermodynamics": (
        (
            "density",
            "melting_point",
            "melting_range",
            "boiling_point",
            "specific_heat_capacity",
            "molar_heat_capacity",
            "enthalpy_formation",
            "entropy",
            "gibbs_energy",
            "thermal_expansion",
            "vapor_pressure",
        ),
        (),
    ),
    "transport": (
        (
            "thermal_conductivity",
            "electrical_resistivity",
            "electrical_conductivity",
            "diffusion_coefficient",
            "viscosity",
        ),
        (),
    ),
    "elastic_mechanical": (
        (
            "youngs_modulus",
            "shear_modulus",
            "bulk_modulus",
            "poisson_ratio",
            "tensile_strength",
            "yield_strength_0_2",
            "elongation",
            "vickers_hardness",
            "fracture_toughness",
            "fatigue_strength",
            "creep_rate",
        ),
        (),
    ),
    "magnetic_optical": (
        (
            "magnetic_susceptibility",
            "magnetization",
            "curie_temperature",
            "refractive_index",
            "dielectric_constant",
            "band_gap",
            "absorption_coefficient",
        ),
        (),
    ),
    "kinetics": (("reaction_rate_constant", "activation_energy", "reaction_order"), ()),
    "phonons_diffraction": (
        (
            "phonon_frequency",
            "diffraction_intensity",
            "structure_factor",
            "debye_temperature",
        ),
        (),
    ),
}
LIMITS = {
    "spectra": "Generic spectrum/axis/intensity/resolution and feature-position schema exists. No dedicated per-line width, oscillator strength, calibration or response-function fields; generic observations could represent scalar quantities after property definitions are added.",
    "molecular_graphs": "Graph tables support bonds and formal charge; no dedicated orbitals, wavefunctions, conformer coordinates or stereochemical assignment tables.",
    "crystallography": "Lattice/site records do not establish validated complete unit cells. No dedicated disorder, ADP tensor, defect or orientation schema; source-native JSON may retain these details.",
    "nuclear_decay": "Raw decay text is evidence of a source statement, not automatically a numerical branching probability. Dedicated core channels remain distinct from normalization sidecars.",
    "kinetics": "Reaction identities and stoichiometry do not count as rate or equilibrium observations.",
}


def quoted(name):
    return '"' + name.replace('"', '""') + '"'


def inventory(path):
    result = {
        "tables": {},
        "columns": {},
        "properties": {},
        "property_definitions": [],
        "diagnostics": [],
    }
    if not path.exists():
        result["diagnostics"].append("database_missing")
        return result
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        names = [
            r[0]
            for r in db.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for name in names:
            result["tables"][name] = db.execute(
                "SELECT count(*) FROM " + quoted(name)
            ).fetchone()[0]
            columns = [
                r[1] for r in db.execute("PRAGMA table_info(" + quoted(name) + ")")
            ]
            result["columns"][name] = columns
            if name in (
                "observation",
                "property_observation",
                "unverified_element_observation",
                "unverified_isotope_observation",
                "unverified_atomic_observation",
            ):
                field = "property_id" if name == "observation" else "property"
                if field not in columns:
                    result["diagnostics"].append("missing_property_column:" + name)
                    continue
                for prop, count in db.execute(
                    "SELECT "
                    + quoted(field)
                    + ",count(*) FROM "
                    + quoted(name)
                    + " GROUP BY "
                    + quoted(field)
                ):
                    prop = prop.removeprefix("property:")
                    result["properties"][prop] = (
                        result["properties"].get(prop, 0) + count
                    )
        if (
            "property_definition" in names
            and "property_id" in result["columns"]["property_definition"]
        ):
            result["property_definitions"] = [
                r[0].removeprefix("property:")
                for r in db.execute(
                    "SELECT property_id FROM property_definition ORDER BY property_id"
                )
            ]
        if not names:
            result["diagnostics"].append("empty_schema")
    known = {p for props, _ in FAMILIES.values() for p in props}
    result["unmapped_properties"] = sorted(set(result["properties"]) - known)
    return result


def audit(root=ROOT):
    root = Path(root)
    inventories = {name: inventory(root / name) for name in DATABASES}
    matrix = {}
    for family, (properties, tables) in FAMILIES.items():
        by_database = {}
        for name, data in inventories.items():
            prop_counts = {
                p: data["properties"][p] for p in properties if p in data["properties"]
            }
            table_counts = {t: data["tables"][t] for t in tables if t in data["tables"]}
            supported = bool(
                prop_counts
                or table_counts
                or set(properties) & set(data["property_definitions"])
            )
            present = sum(prop_counts.values()) + sum(table_counts.values())
            by_database[name] = {
                "property_counts": prop_counts,
                "table_counts": table_counts,
                "record_count": present,
                "schema_support": supported,
                "status": "populated"
                if present
                else "empty"
                if supported
                else "no_dedicated_schema",
            }
        reviewed = by_database["universe.db"]["record_count"]
        staged = sum(
            v["record_count"] for k, v in by_database.items() if k != "universe.db"
        )
        matrix[family] = {
            "reviewed_records": reviewed,
            "staged_records": staged,
            "status": "reviewed_present"
            if reviewed
            else "staged_only"
            if staged
            else "missing",
            "databases": by_database,
            "limitation": LIMITS.get(
                family,
                "Counts do not establish coverage of all entities, conditions or source quality.",
            ),
        }
    return {
        "mapping_version": VERSION,
        "scope": "Reviewed core plus independent authored research databases; duplicate core snapshots and merged releases excluded.",
        "count_semantics": "Counts inventory rows, not distinct entities or independent measurements. Structural parent/child rows are counted separately. Raw Wikipedia claims and JSON sidecars are excluded from typed observation counts.",
        "limitations": [
            "no_dedicated_schema means no matching dedicated table/property definition; generic observations may be extensible",
            "Missing source context, uncertainty and review eligibility require the separate coverage investigation",
            "A family is not complete merely because records are present",
        ],
        "families": matrix,
        "inventories": inventories,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = json.dumps(audit(args.root), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(value, encoding="utf-8")
    else:
        print(value, end="")


if __name__ == "__main__":
    main()
