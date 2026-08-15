#!/usr/bin/env python3
"""Calculate deterministic properties from atomic and molecular composition.

The calculator intentionally separates exact composition invariants, values
derived from reviewed database observations, and explicit physical models.  It
does not fit data, use randomness, or turn a composition into properties that
also require structure, phase, conditions, or experimental evidence.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import Iterable

try:
    from scripts.describe_material import DescriptorError, FormulaParser
except ModuleNotFoundError:  # Direct execution: python scripts/calculate_properties.py
    from describe_material import DescriptorError, FormulaParser


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "universe.db"
SCHEMA_VERSION = 1
ALGORITHM_ID = "deterministic-composition-properties"
ALGORITHM_VERSION = "1.0.0"

# 2022 CODATA values. Decimal strings make the implemented constants explicit
# and keep composition/mass calculations independent of binary floating point.
ELEMENTARY_CHARGE_C = Decimal("1.602176634e-19")  # exact
AVOGADRO_CONSTANT = Decimal("6.02214076e23")  # exact
ATOMIC_MASS_CONSTANT_KG = Decimal("1.66053906892e-27")
ATOMIC_MASS_ENERGY_MEV = Decimal("931.49410372")
MOLAR_MASS_CONSTANT_G_MOL = Decimal("1.00000000105")
ELECTRON_MASS_U = Decimal("0.0005485799090441")
PROTON_MASS_U = Decimal("1.0072764665789")
NEUTRON_MASS_U = Decimal("1.00866491606")
MOLAR_GAS_CONSTANT = Decimal("8.31446261815324")  # N_A * k, exact in SI

# Benzaid et al. (2020), fit to all 2,497 AME2016 nuclides, equation (6).
# Their convention uses Z**2 and a pairing term a_p/sqrt(A).
SEMF_VOLUME_MEV = 14.9297
SEMF_SURFACE_MEV = 15.0580
SEMF_COULOMB_MEV = 0.6615
SEMF_ASYMMETRY_MEV = 21.6091
SEMF_PAIRING_MEV = 10.1744
NUCLEAR_RADIUS_R0_FM = 1.2257

CODATA_URL = "https://physics.nist.gov/cuu/pdf/wall_2022.pdf"
IUPAC_RELATIVE_MASS_URL = "https://goldbook.iupac.org/terms/view/R05271"
SEMF_URL = "https://doi.org/10.1007/s41365-019-0718-8"
DBE_URL = "https://doi.org/10.1038/2001202a0"


class CalculationError(ValueError):
    """Raised when the requested calculation is undefined or unsafe."""


@dataclass(frozen=True)
class ElementRecord:
    entity_id: str
    atomic_number: int
    symbol: str
    name: str
    relative_atomic_mass: Fraction
    observation_id: str
    dataset_id: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decimal_from_fraction(value: Fraction) -> Decimal:
    return Decimal(value.numerator) / Decimal(value.denominator)


def decimal_text(value: Decimal, significant_digits: int = 15) -> str:
    """Return a stable, compact decimal representation."""
    if not value.is_finite():
        raise CalculationError("calculation produced a non-finite value")
    if value == 0:
        return "0"
    with localcontext() as context:
        context.prec = significant_digits
        rounded = +value
    text = format(rounded, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def rounded_float(value: float, digits: int = 9) -> float:
    return round(value, digits)


def exact_integer(value: int, formula: str) -> dict:
    return {
        "value": value,
        "unit": "1",
        "method_class": "exact_from_input",
        "formula": formula,
    }


def hill_formula(elements: dict[str, int]) -> str:
    if "C" in elements:
        order = ["C"]
        if "H" in elements:
            order.append("H")
        order.extend(sorted(symbol for symbol in elements if symbol not in {"C", "H"}))
    else:
        order = sorted(elements)
    return "".join(
        symbol + (str(elements[symbol]) if elements[symbol] != 1 else "")
        for symbol in order
    )


def empirical_formula(elements: dict[str, int]) -> str:
    divisor = 0
    for count in elements.values():
        divisor = math.gcd(divisor, count)
    return hill_formula(
        {symbol: count // divisor for symbol, count in elements.items()}
    )


def pairing_sign(protons: int, neutrons: int) -> int:
    if protons % 2 == 0 and neutrons % 2 == 0:
        return 1
    if protons % 2 == 1 and neutrons % 2 == 1:
        return -1
    return 0


def semi_empirical_binding_energy(protons: int, neutrons: int) -> float:
    """Return Bethe-Weizsaecker binding energy in MeV."""
    mass_number = protons + neutrons
    if mass_number == 1:
        return 0.0
    a_third = mass_number ** (1.0 / 3.0)
    return (
        SEMF_VOLUME_MEV * mass_number
        - SEMF_SURFACE_MEV * a_third**2
        - SEMF_COULOMB_MEV * protons**2 / a_third
        - SEMF_ASYMMETRY_MEV * (mass_number - 2 * protons) ** 2 / mass_number
        + pairing_sign(protons, neutrons)
        * SEMF_PAIRING_MEV
        / math.sqrt(mass_number)
    )


class DeterministicPropertyCalculator:
    def __init__(self, database: Path, elements: Iterable[ElementRecord]):
        self.database = database
        self.database_sha256 = sha256_file(database)
        records = list(elements)
        self.by_symbol = {record.symbol: record for record in records}
        self.by_atomic_number = {record.atomic_number: record for record in records}
        if set(self.by_atomic_number) != set(range(1, 119)):
            raise CalculationError("database must provide elements 1 through 118")
        self.formula_parser = FormulaParser(self.by_symbol)

    @classmethod
    def load(
        cls, database: Path = DEFAULT_DATABASE
    ) -> "DeterministicPropertyCalculator":
        if not database.is_file():
            raise CalculationError(f"database does not exist: {database}")
        connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """
                SELECT element.entity_id, element.atomic_number, element.symbol,
                       entity.name, observation.observation_id,
                       observation.value_numerator, observation.value_denominator,
                       observation.dataset_id
                FROM element
                JOIN entity ON entity.entity_id = element.entity_id
                JOIN observation
                  ON observation.subject_entity_id = element.entity_id
                 AND observation.property_id = 'property:relative_atomic_mass'
                 AND observation.dataset_id =
                     'dataset:pubchem-periodic-table-2026-07-28'
                ORDER BY element.atomic_number
                """
            ).fetchall()
            elements = [
                ElementRecord(
                    entity_id=row["entity_id"],
                    atomic_number=row["atomic_number"],
                    symbol=row["symbol"],
                    name=row["name"],
                    relative_atomic_mass=Fraction(
                        row["value_numerator"], row["value_denominator"]
                    ),
                    observation_id=row["observation_id"],
                    dataset_id=row["dataset_id"],
                )
                for row in rows
            ]
        finally:
            connection.close()
        return cls(database, elements)

    def common_metadata(self) -> dict:
        return {
            "algorithm_id": ALGORITHM_ID,
            "algorithm_version": ALGORITHM_VERSION,
            "deterministic": True,
            "random_seed": None,
            "training_data": None,
            "database_sha256": self.database_sha256,
            "numeric_policy": (
                "exact integers and rational composition; decimal arithmetic for "
                "mass aggregation; binary64 only for fractional-power nuclear models"
            ),
            "constants": {
                "elementary_charge_c": str(ELEMENTARY_CHARGE_C),
                "avogadro_constant_per_mol": str(AVOGADRO_CONSTANT),
                "atomic_mass_constant_kg": str(ATOMIC_MASS_CONSTANT_KG),
                "atomic_mass_energy_mev": str(ATOMIC_MASS_ENERGY_MEV),
                "molar_mass_constant_g_mol": str(MOLAR_MASS_CONSTANT_G_MOL),
                "electron_mass_u": str(ELECTRON_MASS_U),
                "proton_mass_u": str(PROTON_MASS_U),
                "neutron_mass_u": str(NEUTRON_MASS_U),
                "molar_gas_constant_j_mol_k": str(MOLAR_GAS_CONSTANT),
                "nuclear_model": {
                    "volume_mev": SEMF_VOLUME_MEV,
                    "surface_mev": SEMF_SURFACE_MEV,
                    "coulomb_mev": SEMF_COULOMB_MEV,
                    "asymmetry_mev": SEMF_ASYMMETRY_MEV,
                    "pairing_mev": SEMF_PAIRING_MEV,
                    "radius_r0_fm": NUCLEAR_RADIUS_R0_FM,
                },
            },
            "references": [
                {
                    "title": "2022 CODATA recommended constants",
                    "url": CODATA_URL,
                    "used_for": "physical constants and ideal-gas relation",
                },
                {
                    "title": "IUPAC relative molecular mass definition",
                    "url": IUPAC_RELATIVE_MASS_URL,
                    "used_for": "relative formula/molecular mass",
                },
                {
                    "title": "Benzaid et al. Bethe-Weizsaecker update",
                    "url": SEMF_URL,
                    "used_for": (
                        "semi-empirical nuclear binding and radius coefficients"
                    ),
                },
                {
                    "title": "Laws, Molecular Formula and Degree of Unsaturation",
                    "url": DBE_URL,
                    "used_for": "organic-formula DBE screening relation",
                },
            ],
        }

    def calculate_formula(
        self,
        formula: str,
        charge: int = 0,
        temperature_k: Decimal | None = None,
        pressure_pa: Decimal | None = None,
    ) -> dict:
        try:
            elements = self.formula_parser.parse(formula)
        except DescriptorError as exception:
            raise CalculationError(str(exception)) from exception
        return self.calculate_composition(
            elements,
            input_kind="formula",
            input_value=formula,
            charge=charge,
            temperature_k=temperature_k,
            pressure_pa=pressure_pa,
        )

    def calculate_species(
        self,
        species_id: str,
        temperature_k: Decimal | None = None,
        pressure_pa: Decimal | None = None,
    ) -> dict:
        connection = sqlite3.connect(
            f"{self.database.resolve().as_uri()}?mode=ro", uri=True
        )
        connection.row_factory = sqlite3.Row
        try:
            species = connection.execute(
                """
                SELECT chemical_species.entity_id, chemical_species.formula,
                       chemical_species.electric_charge, entity.name
                FROM chemical_species
                JOIN entity ON entity.entity_id = chemical_species.entity_id
                WHERE chemical_species.entity_id = ?
                  AND entity.lifecycle_state = 'active'
                """,
                (species_id,),
            ).fetchone()
            if species is None:
                raise CalculationError(f"unknown active species ID: {species_id}")
            nuclide_component_count = connection.execute(
                """
                SELECT count(*)
                FROM species_nuclide
                WHERE species_id = ?
                """,
                (species_id,),
            ).fetchone()[0]
            if nuclide_component_count:
                raise CalculationError(
                    "isotopically specified species require nuclide-specific mass "
                    "aggregation; use --atomic-number and --neutrons for one atom"
                )
            rows = connection.execute(
                """
                SELECT element.symbol, species_element.atom_count
                FROM species_element
                JOIN element ON element.entity_id = species_element.element_id
                WHERE species_element.species_id = ?
                ORDER BY element.atomic_number
                """,
                (species_id,),
            ).fetchall()
            if not rows:
                raise CalculationError(
                    f"species has no elemental composition: {species_id}"
                )
            elements = {row["symbol"]: row["atom_count"] for row in rows}
        finally:
            connection.close()
        result = self.calculate_composition(
            elements,
            input_kind="species_id",
            input_value=species_id,
            charge=species["electric_charge"],
            temperature_k=temperature_k,
            pressure_pa=pressure_pa,
        )
        result["input"].update(
            {"name": species["name"], "reviewed_formula": species["formula"]}
        )
        return result

    def calculate_composition(
        self,
        elements: dict[str, int],
        *,
        input_kind: str,
        input_value: str,
        charge: int,
        temperature_k: Decimal | None,
        pressure_pa: Decimal | None,
    ) -> dict:
        if not elements or any(count <= 0 for count in elements.values()):
            raise CalculationError("composition counts must be positive integers")
        unknown = sorted(set(elements) - set(self.by_symbol))
        if unknown:
            raise CalculationError("unknown element symbols: " + ", ".join(unknown))
        if (temperature_k is None) != (pressure_pa is None):
            raise CalculationError(
                "ideal-gas density requires both temperature and pressure"
            )
        if temperature_k is not None and temperature_k <= 0:
            raise CalculationError("temperature must be greater than zero kelvin")
        if pressure_pa is not None and pressure_pa <= 0:
            raise CalculationError("pressure must be greater than zero pascal")

        atom_count = sum(elements.values())
        total_protons = sum(
            self.by_symbol[symbol].atomic_number * count
            for symbol, count in elements.items()
        )
        electron_count = total_protons - charge
        if electron_count < 0:
            raise CalculationError(
                f"charge {charge} requires a negative electron count for this "
                "composition"
            )

        mass_contributions: dict[str, Fraction] = {}
        total_relative_mass = Fraction()
        for symbol, count in elements.items():
            contribution = self.by_symbol[symbol].relative_atomic_mass * count
            mass_contributions[symbol] = contribution
            total_relative_mass += contribution
        relative_mass_decimal = decimal_from_fraction(total_relative_mass)
        molar_mass = relative_mass_decimal * MOLAR_MASS_CONSTANT_G_MOL
        particle_mass = relative_mass_decimal * ATOMIC_MASS_CONSTANT_KG
        ion_mass_correction = -Decimal(charge) * ELECTRON_MASS_U

        composition_rows = []
        for symbol in sorted(
            elements, key=lambda item: self.by_symbol[item].atomic_number
        ):
            record = self.by_symbol[symbol]
            count = elements[symbol]
            atomic_fraction = Fraction(count, atom_count)
            mass_fraction = mass_contributions[symbol] / total_relative_mass
            composition_rows.append(
                {
                    "element": symbol,
                    "element_id": record.entity_id,
                    "atomic_number": record.atomic_number,
                    "atom_count": count,
                    "atomic_fraction": {
                        "numerator": atomic_fraction.numerator,
                        "denominator": atomic_fraction.denominator,
                        "decimal": decimal_text(decimal_from_fraction(atomic_fraction)),
                        "method_class": "exact_from_input",
                    },
                    "mass_fraction": {
                        "numerator": mass_fraction.numerator,
                        "denominator": mass_fraction.denominator,
                        "decimal": decimal_text(decimal_from_fraction(mass_fraction)),
                        "method_class": "derived_from_source_observations",
                    },
                    "relative_atomic_mass": {
                        "numerator": record.relative_atomic_mass.numerator,
                        "denominator": record.relative_atomic_mass.denominator,
                        "decimal": decimal_text(
                            decimal_from_fraction(record.relative_atomic_mass)
                        ),
                        "observation_id": record.observation_id,
                        "dataset_id": record.dataset_id,
                    },
                }
            )

        properties = {
            "atom_count": exact_integer(atom_count, "sum(n_i)"),
            "distinct_element_count": exact_integer(
                len(elements), "count(i where n_i > 0)"
            ),
            "proton_count": exact_integer(total_protons, "sum(n_i * Z_i)"),
            "electron_count": exact_integer(
                total_protons - charge, "sum(n_i * Z_i) - q"
            ),
            "net_charge_elementary": exact_integer(charge, "q"),
            "net_charge_coulomb": {
                "value": decimal_text(Decimal(charge) * ELEMENTARY_CHARGE_C),
                "unit": "C",
                "method_class": "derived_from_exact_constant",
                "formula": "q * e",
            },
            "mean_atomic_number": {
                "value": decimal_text(Decimal(total_protons) / Decimal(atom_count)),
                "unit": "1",
                "method_class": "exact_from_input",
                "formula": "sum(n_i * Z_i) / sum(n_i)",
            },
            "relative_formula_mass": {
                "value": decimal_text(relative_mass_decimal),
                "unit": "1",
                "method_class": "derived_from_source_observations",
                "formula": "sum(n_i * A_r,i)",
                "exact_input_rational": {
                    "numerator": total_relative_mass.numerator,
                    "denominator": total_relative_mass.denominator,
                },
            },
            "molar_mass": {
                "value": decimal_text(molar_mass),
                "unit": "g/mol",
                "method_class": "derived_from_source_observations_and_codata",
                "formula": "M = M_r * M_u",
            },
            "neutral_constituent_mass": {
                "value": decimal_text(particle_mass),
                "unit": "kg per formula unit",
                "method_class": "derived_from_source_observations_and_codata",
                "formula": "m = M_r * m_u",
            },
            "ion_electron_mass_correction": {
                "value": decimal_text(ion_mass_correction),
                "unit": "u",
                "method_class": "codata_approximation",
                "formula": "-q * m_e; ionization/bond energy mass is neglected",
            },
        }

        dbe, dbe_reason = self.degree_of_unsaturation(elements, charge)
        if dbe is not None:
            properties["degree_of_unsaturation"] = {
                "value": dbe,
                "unit": "1",
                "method_class": "formula_screening_relation",
                "formula": "C + 1 + (N - H - F - Cl - Br - I) / 2",
                "validity": "neutral, closed-shell CHN/O/S/halogen organic formulas",
            }

        if temperature_k is not None and pressure_pa is not None:
            molar_mass_kg = molar_mass / Decimal(1000)
            density = pressure_pa * molar_mass_kg / (
                MOLAR_GAS_CONSTANT * temperature_k
            )
            properties["ideal_gas_density"] = {
                "value": decimal_text(density),
                "unit": "kg/m^3",
                "method_class": "conditional_ideal_model",
                "formula": "rho = p * M / (R * T)",
                "conditions": {
                    "temperature_k": decimal_text(temperature_k),
                    "pressure_pa": decimal_text(pressure_pa),
                },
                "validity": "ideal-gas limit only; not a condensed-phase density",
            }

        unavailable = [
            {
                "properties": ["connectivity", "geometry", "stereochemistry", "isomer"],
                "reason": (
                    "an elemental formula does not uniquely determine molecular "
                    "structure"
                ),
            },
            {
                "properties": ["phase", "density", "melting_point", "boiling_point"],
                "reason": (
                    "these require structure, phase, pressure, temperature, and/or "
                    "measurements"
                ),
            },
            {
                "properties": ["heat_capacity", "enthalpy", "entropy", "free_energy"],
                "reason": (
                    "these are state functions requiring a defined state and "
                    "molecular model or evidence"
                ),
            },
            {
                "properties": [
                    "spectra",
                    "dipole_moment",
                    "polarizability",
                    "electronic_levels",
                ],
                "reason": (
                    "these require electronic/nuclear structure, geometry, and "
                    "often environment"
                ),
            },
            {
                "properties": [
                    "solubility",
                    "reactivity",
                    "toxicity",
                    "mechanical_properties",
                ],
                "reason": (
                    "composition alone is not an identifying physical model for "
                    "these properties"
                ),
            },
        ]
        if dbe is None:
            unavailable.append(
                {"properties": ["degree_of_unsaturation"], "reason": dbe_reason}
            )

        return {
            "schema_version": SCHEMA_VERSION,
            "result_kind": "deterministic_composition_property_calculation",
            "input": {
                "kind": input_kind,
                "value": input_value,
                "charge": charge,
            },
            "normalized": {
                "hill_formula": hill_formula(elements),
                "empirical_formula": empirical_formula(elements),
                "composition": composition_rows,
            },
            "properties": properties,
            "not_identifiable_from_inputs": unavailable,
            "methodology": self.common_metadata(),
        }

    @staticmethod
    def degree_of_unsaturation(
        elements: dict[str, int], charge: int
    ) -> tuple[float | int | None, str | None]:
        allowed = {"C", "H", "N", "O", "S", "F", "Cl", "Br", "I"}
        if charge != 0:
            return None, "the implemented DBE relation assumes a neutral formula"
        if "C" not in elements:
            return None, "the implemented DBE relation is scoped to carbon compounds"
        unsupported = sorted(set(elements) - allowed)
        if unsupported:
            return None, "DBE assumptions do not cover: " + ", ".join(unsupported)
        halogens = sum(elements.get(symbol, 0) for symbol in ("F", "Cl", "Br", "I"))
        twice_dbe = (
            2 * elements["C"]
            + 2
            + elements.get("N", 0)
            - elements.get("H", 0)
            - halogens
        )
        if twice_dbe < 0:
            return (
                None,
                "the formula violates the valence assumptions of the DBE relation",
            )
        value = twice_dbe / 2
        return (int(value) if value.is_integer() else value), None

    def calculate_atom(
        self, atomic_number: int, neutrons: int | None = None, charge: int = 0
    ) -> dict:
        record = self.by_atomic_number.get(atomic_number)
        if record is None:
            raise CalculationError("atomic number must be between 1 and 118")
        if neutrons is not None and neutrons < 0:
            raise CalculationError("neutron count cannot be negative")
        electron_count = atomic_number - charge
        if electron_count < 0:
            raise CalculationError("charge requires a negative electron count")

        properties = {
            "atomic_number": exact_integer(atomic_number, "Z"),
            "proton_count": exact_integer(atomic_number, "Z"),
            "electron_count": exact_integer(electron_count, "Z - q"),
            "net_charge_elementary": exact_integer(charge, "q"),
            "net_charge_coulomb": {
                "value": decimal_text(Decimal(charge) * ELEMENTARY_CHARGE_C),
                "unit": "C",
                "method_class": "derived_from_exact_constant",
                "formula": "q * e",
            },
        }

        limitations = []
        if neutrons is None:
            relative_mass = decimal_from_fraction(record.relative_atomic_mass)
            properties["source_relative_atomic_mass"] = {
                "value": decimal_text(relative_mass),
                "unit": "1",
                "method_class": "source_observation",
                "observation_id": record.observation_id,
                "dataset_id": record.dataset_id,
                "note": "elemental source value; not the mass of a specified isotope",
            }
            properties["source_element_molar_mass"] = {
                "value": decimal_text(relative_mass * MOLAR_MASS_CONSTANT_G_MOL),
                "unit": "g/mol",
                "method_class": "derived_from_source_observation_and_codata",
                "formula": "M = A_r * M_u",
            }
            limitations.append(
                {
                    "properties": [
                        "mass_number",
                        "nuclear_mass",
                        "nuclear_radius",
                        "binding_energy",
                    ],
                    "reason": (
                        "atomic number does not select an isotope; provide --neutrons"
                    ),
                }
            )
        else:
            mass_number = atomic_number + neutrons
            binding_mev = semi_empirical_binding_energy(atomic_number, neutrons)
            radius_fm = NUCLEAR_RADIUS_R0_FM * mass_number ** (1.0 / 3.0)
            binding_decimal = Decimal(str(binding_mev))
            mass_defect_u = binding_decimal / ATOMIC_MASS_ENERGY_MEV
            nuclear_mass_u = (
                Decimal(atomic_number) * PROTON_MASS_U
                + Decimal(neutrons) * NEUTRON_MASS_U
                - mass_defect_u
            )
            ion_mass_u = nuclear_mass_u + Decimal(electron_count) * ELECTRON_MASS_U
            if mass_number == 1:
                validity = "special-case exact free-nucleon binding"
            elif mass_number < 50:
                validity = (
                    "semi-empirical liquid-drop estimate outside the source's "
                    "strongest A >= 50 fit region; shell and deformation effects "
                    "omitted"
                )
            else:
                validity = (
                    "semi-empirical liquid-drop estimate; shell and deformation "
                    "effects omitted"
                )
            properties.update(
                {
                    "neutron_count": exact_integer(neutrons, "N"),
                    "mass_number": exact_integer(mass_number, "A = Z + N"),
                    "neutron_to_proton_ratio": {
                        "value": decimal_text(
                            Decimal(neutrons) / Decimal(atomic_number)
                        ),
                        "unit": "1",
                        "method_class": "exact_from_input",
                        "formula": "N / Z",
                    },
                    "nuclear_radius": {
                        "value": rounded_float(radius_fm),
                        "unit": "fm",
                        "method_class": "semi_empirical_model",
                        "formula": "R = 1.2257 fm * A^(1/3)",
                        "validity": (
                            "characteristic liquid-drop radius, not a measured "
                            "charge radius"
                        ),
                    },
                    "nuclear_binding_energy": {
                        "value": rounded_float(binding_mev),
                        "unit": "MeV",
                        "method_class": (
                            "exact_free_nucleon_identity"
                            if mass_number == 1
                            else "semi_empirical_model"
                        ),
                        "formula": (
                            "a_v*A - a_s*A^(2/3) - a_c*Z^2/A^(1/3) "
                            "- a_a*(A-2Z)^2/A + delta*a_p/A^(1/2)"
                        ),
                        "validity": validity,
                    },
                    "nuclear_binding_energy_per_nucleon": {
                        "value": rounded_float(binding_mev / mass_number),
                        "unit": "MeV",
                        "method_class": "derived_from_nuclear_model",
                        "formula": "B / A",
                    },
                    "mass_defect": {
                        "value": decimal_text(mass_defect_u),
                        "unit": "u",
                        "method_class": "derived_from_nuclear_model_and_codata",
                        "formula": "Delta m = B / (m_u*c^2)",
                    },
                    "estimated_nuclear_mass": {
                        "value": decimal_text(nuclear_mass_u),
                        "unit": "u",
                        "method_class": "derived_from_nuclear_model_and_codata",
                        "formula": "Z*m_p + N*m_n - Delta m",
                    },
                    "estimated_atomic_or_ion_mass": {
                        "value": decimal_text(ion_mass_u),
                        "unit": "u",
                        "method_class": "derived_from_nuclear_model_and_codata",
                        "formula": "m_nucleus + (Z-q)*m_e",
                        "validity": "electronic binding energy is neglected",
                    },
                    "model_bound_indicator": {
                        "value": binding_mev >= 0,
                        "unit": "boolean",
                        "method_class": "derived_from_nuclear_model",
                        "formula": "B >= 0",
                        "validity": (
                            "not an experimental stability or half-life prediction"
                        ),
                    },
                }
            )

        limitations.extend(
            [
                {
                    "properties": ["half_life", "decay_modes", "branching_ratios"],
                    "reason": (
                        "Z and N do not provide transition matrix elements or "
                        "measured decay data"
                    ),
                },
                {
                    "properties": [
                        "nuclear_spin",
                        "magnetic_moment",
                        "quadrupole_moment",
                    ],
                    "reason": "these require a nuclear structure model or observations",
                },
                {
                    "properties": [
                        "ionization_energy",
                        "electron_affinity",
                        "electronegativity",
                        "atomic_spectrum",
                    ],
                    "reason": (
                        "multi-electron quantum structure is not uniquely supplied "
                        "by count identities alone"
                    ),
                },
            ]
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "result_kind": "deterministic_atomic_property_calculation",
            "input": {
                "atomic_number": atomic_number,
                "neutrons": neutrons,
                "charge": charge,
            },
            "identity": {
                "element_id": record.entity_id,
                "name": record.name,
                "symbol": record.symbol,
            },
            "properties": properties,
            "not_identifiable_from_inputs": limitations,
            "methodology": self.common_metadata(),
        }


def decimal_argument(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except Exception as exception:
        raise argparse.ArgumentTypeError(
            f"invalid decimal value: {value!r}"
        ) from exception
    if not parsed.is_finite():
        raise argparse.ArgumentTypeError("value must be finite")
    return parsed


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Calculate deterministic composition invariants and explicitly scoped "
            "physical-model estimates."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--formula", help="neutral formula text; set ionic charge separately"
    )
    mode.add_argument("--species", help="reviewed chem: species ID")
    mode.add_argument("--atomic-number", type=int, help="number of protons, Z")
    parser.add_argument(
        "--neutrons", type=int, help="neutron count for isotope calculations"
    )
    parser.add_argument(
        "--charge",
        type=int,
        default=0,
        help="net charge in elementary-charge units (positive for a cation)",
    )
    parser.add_argument("--temperature-k", type=decimal_argument)
    parser.add_argument("--pressure-pa", type=decimal_argument)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main() -> None:
    parser = build_argument_parser()
    arguments = parser.parse_args()
    if arguments.atomic_number is None and arguments.neutrons is not None:
        parser.error("--neutrons is only valid with --atomic-number")
    if arguments.atomic_number is not None and (
        arguments.temperature_k is not None or arguments.pressure_pa is not None
    ):
        parser.error("ideal-gas conditions are only valid with --formula or --species")
    if arguments.species is not None and arguments.charge != 0:
        parser.error("--species uses the reviewed charge; do not also pass --charge")
    try:
        calculator = DeterministicPropertyCalculator.load(arguments.database)
        if arguments.atomic_number is not None:
            result = calculator.calculate_atom(
                arguments.atomic_number, arguments.neutrons, arguments.charge
            )
        elif arguments.species is not None:
            result = calculator.calculate_species(
                arguments.species, arguments.temperature_k, arguments.pressure_pa
            )
        else:
            result = calculator.calculate_formula(
                arguments.formula,
                arguments.charge,
                arguments.temperature_k,
                arguments.pressure_pa,
            )
    except CalculationError as exception:
        parser.error(str(exception))
    print(json.dumps(result, indent=arguments.indent, sort_keys=True))


if __name__ == "__main__":
    main()
