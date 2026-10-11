#!/usr/bin/env python3
"""Integer-composition accounting and opt-in mixture/crystal models."""

from __future__ import annotations

import argparse
import json
import math
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

try:
    from scripts.calculate_properties import (
        AVOGADRO_CONSTANT,
        DEFAULT_DATABASE,
        CalculationError,
        DeterministicPropertyCalculator,
    )
except ModuleNotFoundError:
    from calculate_properties import (
        AVOGADRO_CONSTANT,
        DEFAULT_DATABASE,
        CalculationError,
        DeterministicPropertyCalculator,
    )

ALGORITHM_VERSION = "1.0.0"
MODELS = {
    "additive_volume",
    "ideal_heat_capacity",
    "thermal_bounds",
    "electrical_bounds",
    "elastic_bounds",
}
STAT_UNITS = {
    "density": "kg/m3",
    "specific_heat_capacity": "J/(kg*K)",
    "thermal_conductivity": "W/(m*K)",
    "electrical_conductivity": "S/m",
    "bulk_modulus": "Pa",
    "shear_modulus": "Pa",
}
REFERENCES = [
    "https://it.iucr.org/Cb/ch1o1v0001/",
    "https://journals.iucr.org/services/cif/checking/DENSD01.html",
    "https://doc.comsol.com/6.3/doc/com.comsol.help.acdc/acdc_ug_theory.05.39.html",
]
PROTOTYPE_FILE = Path(__file__).resolve().parents[1] / "sources/crystal_prototypes.json"


def structure_from_prototype(prototype, lattice_a_angstrom, *, conditions=None):
    """Expand an ideal conventional cubic cell; does not assert phase stability."""
    catalog = json.loads(PROTOTYPE_FILE.read_text(encoding="utf-8"))
    if prototype not in catalog["prototypes"]:
        raise CalculationError(f"unknown crystal prototype: {prototype}")
    a = number(lattice_a_angstrom, "lattice_a_angstrom")
    if a <= 0:
        raise CalculationError("lattice parameter must be positive")
    row = catalog["prototypes"][prototype]
    return {
        "prototype": prototype,
        "prototype_version": catalog["version"],
        "lattice_angstrom": {
            "a": str(a),
            "b": str(a),
            "c": str(a),
            "alpha": "90",
            "beta": "90",
            "gamma": "90",
        },
        "cell_counts": row["component_counts"],
        "sites": row["sites"],
        "space_group_number": row["space_group_number"],
        "source": row["source"],
        "conditions": conditions or {},
        "phase_status": "user-selected ideal geometry, not equilibrium prediction",
    }


def number(value, name):
    if isinstance(value, bool) or not isinstance(value, (str, int, Fraction, Decimal)):
        raise CalculationError(
            f"{name} must be a finite decimal string, integer, Decimal or Fraction"
        )
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError, OverflowError) as error:
        raise CalculationError(f"invalid {name}") from error


def json_safe(value):
    if isinstance(value, (Fraction, Decimal)):
        return str(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def packed(value: Fraction, unit="1", method="derived_from_inputs"):
    with localcontext() as context:
        context.prec = 20
        text = str(Decimal(value.numerator) / Decimal(value.denominator))
    return {
        "value": text,
        "numerator": value.numerator,
        "denominator": value.denominator,
        "unit": unit,
        "method_class": method,
    }


def integer_counts(counts, size):
    if not isinstance(counts, (list, tuple)) or len(counts) != size:
        raise CalculationError("one integer count is required per component")
    if any(type(count) is not int or count < 0 for count in counts) or not any(counts):
        raise CalculationError(
            "counts must be nonnegative integers with a positive total"
        )
    return counts


def normalized_conditions(conditions):
    if not isinstance(conditions, dict):
        raise CalculationError("conditions must be an object")
    result = {}
    for key, value in conditions.items():
        if key in {"temperature_k", "pressure_pa"}:
            value = number(value, key)
            if value <= 0:
                raise CalculationError(f"{key} must be positive")
        result[key] = value
    return result


def crystal_density(masses, counts, structure):
    """Fully occupied integer cell contents; no assumed phase or lattice."""
    cell_counts = integer_counts(structure.get("cell_counts"), len(counts))
    if "sites" in structure:
        sites = structure["sites"]
        if not isinstance(sites, list):
            raise CalculationError("crystal sites must be a list")
        occupied = set()
        site_counts = [0] * len(counts)
        for site in sites:
            if (
                not isinstance(site, (list, tuple))
                or len(site) != 4
                or type(site[0]) is not int
                or not 0 <= site[0] < len(counts)
            ):
                raise CalculationError(
                    "sites need a component index and three fractional coordinates"
                )
            coordinates = tuple(
                number(value, "fractional coordinate") for value in site[1:]
            )
            if (
                any(not 0 <= coordinate < 1 for coordinate in coordinates)
                or coordinates in occupied
            ):
                raise CalculationError("invalid or multiply occupied crystal site")
            occupied.add(coordinates)
            site_counts[site[0]] += 1
        if site_counts != list(cell_counts):
            raise CalculationError("site occupancies differ from cell_counts")
    ratios = {
        Fraction(cell, count) for cell, count in zip(cell_counts, counts) if count
    }
    if (
        len(ratios) != 1
        or 0 in ratios
        or any(cell for cell, count in zip(cell_counts, counts) if not count)
    ):
        raise CalculationError(
            "unit-cell contents must match the requested mixture composition"
        )
    lattice = structure.get("lattice_angstrom")
    if not isinstance(lattice, dict):
        raise CalculationError(
            "structure needs lattice_angstrom with a,b,c,alpha,beta,gamma"
        )
    try:
        lengths = [float(number(lattice[key], key)) for key in ("a", "b", "c")]
        angles = [
            float(number(lattice[key], key)) for key in ("alpha", "beta", "gamma")
        ]
    except (KeyError, OverflowError) as error:
        raise CalculationError("invalid or incomplete cell geometry") from error
    if any(not math.isfinite(v) or v <= 0 for v in lengths) or any(
        not math.isfinite(v) or not 0 < v < 180 for v in angles
    ):
        raise CalculationError("invalid cell lengths or angles")
    ca, cb, cg = [math.cos(math.radians(angle)) for angle in angles]
    determinant = 1 - ca * ca - cb * cb - cg * cg + 2 * ca * cb * cg
    if determinant <= 1e-12:
        raise CalculationError("cell geometry is degenerate or impossible")
    volume = math.prod(lengths) * math.sqrt(determinant)
    if not math.isfinite(volume) or volume <= 0:
        raise CalculationError("invalid cell volume")
    mass_per_mole_cells = sum(mass * count for mass, count in zip(masses, cell_counts))
    # masses are kg/mol; one angstrom cubed is 1e-30 m3.
    density = float(mass_per_mole_cells) / (float(AVOGADRO_CONSTANT) * volume * 1e-30)
    if not math.isfinite(density):
        raise CalculationError("non-finite crystal density")
    return {
        "value": format(density, ".15g"),
        "unit": "kg/m3",
        "method_class": "crystal_cell_model",
        "cell_volume_angstrom3": format(volume, ".15g"),
        "cell_counts": cell_counts,
        "assumptions": [
            "Provided cell is fully occupied and has the specified composition",
            "Zero porosity; lattice parameters describe the supplied state",
        ],
        "formula": "sum(cell_count_i*M_i)/(N_A*V_cell)",
        "structure_input": structure,
        "numeric_policy": "binary64 trigonometry; source molar masses retained in input accounting",
    }


def calculate_mixture(
    components,
    counts,
    *,
    models=(),
    conditions=None,
    structure=None,
    database=DEFAULT_DATABASE,
    calculator=None,
):
    """Counts are numbers of atoms/molecules/formula units, never weight parts.

    Each component supplies formula or species_id, optional molar_mass_g_mol,
    charge, and stats. Model statistics require canonical SI units, an explicit
    phase, a source, and conditions equal to the target conditions.
    """
    if not isinstance(components, (list, tuple)) or not components:
        raise CalculationError("components must be a nonempty list")
    counts = integer_counts(counts, len(components))
    if not isinstance(models, (list, tuple, set)) or set(models) - MODELS:
        raise CalculationError(f"models must be selected from {sorted(MODELS)}")
    requested = set(models)
    conditions = {} if conditions is None else conditions
    target = normalized_conditions(conditions)
    if requested and "temperature_k" not in target:
        raise CalculationError(
            "mixture models require an explicit target temperature_k"
        )
    calculator = calculator or DeterministicPropertyCalculator.load(Path(database))
    active = []
    elements = {}
    charge_total = 0
    for index, (component, count) in enumerate(zip(components, counts)):
        if not count:
            continue
        if not isinstance(component, dict):
            raise CalculationError("each component must be an object")
        if ("formula" in component) == ("species_id" in component):
            raise CalculationError(
                "provide exactly one formula or species_id per component"
            )
        identity = component.get("formula", component.get("species_id"))
        if not isinstance(identity, str) or not identity.strip():
            raise CalculationError("component identity must be a nonempty string")
        if not isinstance(component.get("stats", {}), dict):
            raise CalculationError("component stats must be an object")
        if "species_id" in component:
            if "charge" in component:
                raise CalculationError("species_id uses its database charge")
            result = calculator.calculate_species(component["species_id"])
        else:
            charge = component.get("charge", 0)
            if type(charge) is not int:
                raise CalculationError("charge must be an integer")
            result = calculator.calculate_formula(component["formula"], charge=charge)
        mass = (
            number(
                component.get(
                    "molar_mass_g_mol", result["properties"]["molar_mass"]["value"]
                ),
                "molar_mass_g_mol",
            )
            / 1000
        )
        if mass <= 0:
            raise CalculationError("component molar mass must be positive")
        for row in result["normalized"]["composition"]:
            elements[row["element"]] = (
                elements.get(row["element"], 0) + count * row["atom_count"]
            )
        charge_total += count * result["input"]["charge"]
        active.append(
            {
                "index": index,
                "count": count,
                "mass": mass,
                "input": component,
                "identity": result["input"],
            }
        )
    total_count = sum(row["count"] for row in active)
    total_mass = sum(row["count"] * row["mass"] for row in active)
    atom_count = sum(elements.values())
    composition = calculator.calculate_composition(
        elements,
        charge=charge_total,
        input_kind="mixture_packet",
        input_value="integer component counts",
        temperature_k=None,
        pressure_pa=None,
    )
    output = {
        "result_kind": "mixture_property_calculation",
        "algorithm_version": ALGORITHM_VERSION,
        "database_sha256": calculator.database_sha256,
        "input": {
            "components": components,
            "counts": counts,
            "models": sorted(requested),
            "conditions": conditions,
            "structure": structure,
        },
        "component_fractions": [],
        "element_counts": dict(sorted(elements.items())),
        "element_atomic_fractions": {
            e: packed(Fraction(n, atom_count)) for e, n in sorted(elements.items())
        },
        "properties": {
            "atom_count": atom_count,
            "component_count": total_count,
            "net_charge_elementary": charge_total,
            "proton_count": composition["properties"]["proton_count"]["value"],
            "electron_count": composition["properties"]["electron_count"]["value"],
            "batch_molar_mass": packed(total_mass, "kg/mol of mixture packets"),
            "mean_component_molar_mass": packed(
                total_mass / total_count, "kg/mol of components"
            ),
        },
        "models": {},
        "not_identifiable_from_inputs": [
            "phase stability and reaction products",
            "alloy strength and hardness",
            "melting/boiling intervals",
            "defects, grain structure, ceramic sintering and porosity",
            "spectra, bonding and interfacial resistance",
        ],
        "provenance_class": "modeled",
        "references": REFERENCES,
        "numeric_policy": "Exact ratios over supplied or source-derived rounded molar masses; no uncertainty propagation",
    }
    for row in active:
        output["component_fractions"].append(
            {
                "component_index": row["index"],
                "number_fraction": packed(Fraction(row["count"], total_count)),
                "mass_fraction": packed(row["count"] * row["mass"] / total_mass),
                "molar_mass": packed(row["mass"], "kg/mol"),
                "mass_source": "user input"
                if "molar_mass_g_mol" in row["input"]
                else row["identity"],
            }
        )

    def stats(name):
        values = []
        for row in active:
            observation = row["input"].get("stats", {}).get(name)
            if (
                not isinstance(observation, dict)
                or observation.get("unit") != STAT_UNITS[name]
            ):
                raise CalculationError(
                    f"component {row['index']} needs {name} in {STAT_UNITS[name]}"
                )
            if not observation.get("source") or not observation.get("phase"):
                raise CalculationError(f"{name} needs source and component phase")
            if normalized_conditions(observation.get("conditions", {})) != target:
                raise CalculationError(
                    f"{name} conditions differ from target conditions"
                )
            value = number(observation.get("value"), name)
            if value <= 0:
                raise CalculationError(f"{name} must be positive")
            values.append(value)
        return values

    if requested & {
        "additive_volume",
        "thermal_bounds",
        "electrical_bounds",
        "elastic_bounds",
    }:
        densities = stats("density")
        volumes = [
            row["count"] * row["mass"] / density
            for row, density in zip(active, densities)
        ]
        total_volume = sum(volumes)
        fractions = [volume / total_volume for volume in volumes]
        output["volume_fractions"] = [
            dict(
                component_index=row["index"],
                **packed(fraction, "1", "additive_volume_model"),
            )
            for row, fraction in zip(active, fractions)
        ]
        if "additive_volume" in requested:
            output["models"]["density"] = dict(
                packed(total_mass / total_volume, "kg/m3", "additive_volume_model"),
                assumptions=[
                    "No reactions, excess mixing volume, or porosity; constituent phases retained"
                ],
                formula="sum(n_i*M_i)/sum(n_i*M_i/rho_i)",
            )
        for model, name in (
            ("thermal_bounds", "thermal_conductivity"),
            ("electrical_bounds", "electrical_conductivity"),
        ):
            if model in requested:
                values = stats(name)
                parallel = sum(
                    fraction * value for fraction, value in zip(fractions, values)
                )
                series = 1 / sum(
                    fraction / value for fraction, value in zip(fractions, values)
                )
                output["models"][name] = {
                    "series": packed(series, STAT_UNITS[name], "ideal_laminate_model"),
                    "parallel": packed(
                        parallel, STAT_UNITS[name], "ideal_laminate_model"
                    ),
                    "assumptions": [
                        "Isotropic positive constituent conductivities; perfect interfaces",
                        "Series/parallel phase geometry; no reaction, percolation or interfacial resistance",
                    ],
                }
        if "elastic_bounds" in requested:
            bulk, shear = stats("bulk_modulus"), stats("shear_modulus")
            bounds = {}
            for label, average in (
                ("voigt", lambda values: sum(f * v for f, v in zip(fractions, values))),
                (
                    "reuss",
                    lambda values: 1 / sum(f / v for f, v in zip(fractions, values)),
                ),
            ):
                k, g = average(bulk), average(shear)
                bounds[label] = {
                    "bulk_modulus": packed(k, "Pa", "elastic_bound_model"),
                    "shear_modulus": packed(g, "Pa", "elastic_bound_model"),
                    "youngs_modulus": packed(
                        9 * k * g / (3 * k + g), "Pa", "elastic_bound_model"
                    ),
                }
            output["models"]["elastic_bounds"] = dict(
                bounds,
                assumptions=[
                    "Linear elastic isotropic constituent phases; isotropic effective response",
                    "Uniform strain/stress bounds with perfect bonding; no alloy-strength prediction",
                ],
            )
    if "ideal_heat_capacity" in requested:
        capacity = (
            sum(
                row["count"] * row["mass"] * value
                for row, value in zip(active, stats("specific_heat_capacity"))
            )
            / total_mass
        )
        output["models"]["specific_heat_capacity"] = dict(
            packed(capacity, "J/(kg*K)", "ideal_heat_capacity_model"),
            assumptions=[
                "Mass-weighted constant-pressure heat capacities at the same state",
                "No excess heat capacity, reaction or phase transition",
            ],
            formula="sum(w_i*cp_i)",
        )
    if structure is not None:
        if not isinstance(structure, dict):
            raise CalculationError("structure must be an object")
        if normalized_conditions(structure.get("conditions", {})) != target:
            raise CalculationError(
                "crystal structure conditions differ from target conditions"
            )
        masses = [Fraction(0)] * len(counts)
        for row in active:
            masses[row["index"]] = row["mass"]
        output["models"]["crystal_density"] = crystal_density(masses, counts, structure)
        if "porosity_fraction" in structure:
            porosity = number(structure["porosity_fraction"], "porosity_fraction")
            if not 0 <= porosity < 1:
                raise CalculationError("porosity_fraction must be in [0,1)")
            solid = number(
                output["models"]["crystal_density"]["value"], "crystal density"
            )
            output["models"]["porous_bulk_density"] = dict(
                packed(solid * (1 - porosity), "kg/m3", "zero_mass_pore_model"),
                assumptions=["Specified void volume fraction; pore mass is negligible"],
                porosity_fraction=packed(porosity),
                formula="rho_bulk=(1-porosity)*rho_cell",
            )
    return json_safe(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        type=Path,
        help="JSON object with components, counts, optional models/conditions/structure",
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or set(payload) - {
            "components",
            "counts",
            "models",
            "conditions",
            "structure",
        }:
            raise CalculationError("unexpected mixture input fields")
        result = calculate_mixture(database=args.database, **payload)
    except (CalculationError, TypeError, OSError, json.JSONDecodeError) as error:
        parser.error(str(error))
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
