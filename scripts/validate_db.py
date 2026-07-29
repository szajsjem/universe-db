#!/usr/bin/env python3
"""Validate structural integrity and domain invariants in universe.db."""

from __future__ import annotations

import argparse
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
import sqlite3


def scalar(connection: sqlite3.Connection, sql: str) -> int:
    return int(connection.execute(sql).fetchone()[0])


def exact_si_value(
    connection: sqlite3.Connection,
    numerator: int,
    denominator: int,
    unit_id: str,
) -> Fraction:
    unit = connection.execute(
        """
        SELECT si_scale_numerator, si_scale_denominator, si_scale_power10,
               si_offset_numerator, si_offset_denominator
        FROM unit
        WHERE unit_id = ?
        """,
        (unit_id,),
    ).fetchone()
    if unit is None:
        raise ValueError(f"unknown unit {unit_id}")
    power = unit["si_scale_power10"]
    power_factor = (
        Fraction(10**power, 1)
        if power >= 0
        else Fraction(1, 10 ** (-power))
    )
    return (
        Fraction(numerator, denominator)
        * Fraction(unit["si_scale_numerator"], unit["si_scale_denominator"])
        * power_factor
        + Fraction(
            unit["si_offset_numerator"],
            unit["si_offset_denominator"],
        )
    )


def quantity_family(quantity_kind: str) -> str:
    for suffix in ("_min", "_max"):
        if quantity_kind.endswith(suffix):
            return quantity_kind[: -len(suffix)]
    return quantity_kind


def directed_cycles(edges: dict[str, str]) -> list[tuple[str, ...]]:
    cycles: set[tuple[str, ...]] = set()
    complete: set[str] = set()
    for start in sorted(edges):
        if start in complete:
            continue
        path: list[str] = []
        positions: dict[str, int] = {}
        current: str | None = start
        while current is not None and current not in complete:
            if current in positions:
                cycle = path[positions[current] :]
                rotations = [
                    tuple(cycle[index:] + cycle[:index])
                    for index in range(len(cycle))
                ]
                cycles.add(min(rotations))
                break
            positions[current] = len(path)
            path.append(current)
            current = edges.get(current)
        complete.update(path)
    return sorted(cycles)


def graph_cycles(edges: dict[str, set[str]]) -> list[tuple[str, ...]]:
    cycles: set[tuple[str, ...]] = set()

    def visit(
        current: str,
        path: list[str],
        positions: dict[str, int],
    ) -> None:
        if current in positions:
            cycle = path[positions[current] :]
            rotations = [
                tuple(cycle[index:] + cycle[:index])
                for index in range(len(cycle))
            ]
            cycles.add(min(rotations))
            return
        positions[current] = len(path)
        path.append(current)
        for target in sorted(edges.get(current, ())):
            visit(target, path, positions)
        path.pop()
        positions.pop(current)

    for node in sorted(edges):
        visit(node, [], {})
    return sorted(cycles)


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        structural_failure = False
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            errors.append("SQLite integrity_check failed")
            structural_failure = True
        foreign_key_failures = list(
            connection.execute("PRAGMA foreign_key_check")
        )
        for row in foreign_key_failures:
            errors.append(f"foreign key violation: {tuple(row)}")
        if foreign_key_failures:
            structural_failure = True
        if structural_failure:
            return errors

        for row in connection.execute(
            """
            SELECT s.source_id
            FROM source AS s
            JOIN license AS l USING (license_id)
            WHERE l.redistribution_allowed <> 1
            ORDER BY s.source_id
            """
        ):
            errors.append(
                f"{row['source_id']} is not licensed for redistribution"
            )

        sourced_tables = (
            ("observation", "observation_id"),
            ("reaction", "reaction_id"),
            ("spectrum", "spectrum_id"),
            ("nuclear_channel", "channel_id"),
        )
        for table, identity_column in sourced_tables:
            for row in connection.execute(
                f"""
                SELECT authored.{identity_column}
                FROM {table} AS authored
                JOIN dataset AS d USING (dataset_id)
                WHERE authored.source_id <> d.source_id
                ORDER BY authored.{identity_column}
                """
            ):
                errors.append(
                    f"{table} {row[identity_column]} uses a source "
                    "different from its dataset"
                )

        entity_tables = {
            "particle": "particle",
            "element": "element",
            "nuclide": "nuclide",
            "chemical_species": "chemical_species",
            "material": "material",
            "crystal_structure": "crystal_structure",
            "mixture": "mixture",
        }
        for entity_type, table in entity_tables.items():
            count = scalar(
                connection,
                f"""
                SELECT count(*)
                FROM {table} AS specialized
                JOIN entity USING (entity_id)
                WHERE entity.entity_type <> '{entity_type}'
                """,
            )
            if count:
                errors.append(f"{count} {table} rows have the wrong entity type")
            missing = scalar(
                connection,
                f"""
                SELECT count(*)
                FROM entity
                WHERE entity_type = '{entity_type}'
                  AND NOT EXISTS (
                      SELECT 1 FROM {table}
                      WHERE {table}.entity_id = entity.entity_id
                  )
                """,
            )
            if missing:
                errors.append(
                    f"{missing} {entity_type} entities lack a {table} row"
                )

        replacement_edges = {
            row["entity_id"]: row["replaced_by_entity_id"]
            for row in connection.execute(
                """
                SELECT entity_id, replaced_by_entity_id
                FROM entity
                WHERE replaced_by_entity_id IS NOT NULL
                ORDER BY entity_id
                """
            )
        }
        for cycle in directed_cycles(replacement_edges):
            errors.append(
                "entity replacement cycle: " + " -> ".join((*cycle, cycle[0]))
            )
        for row in connection.execute(
            """
            SELECT old.entity_id, old.lifecycle_state,
                   old.entity_type AS old_type,
                   replacement.entity_type AS replacement_type
            FROM entity AS old
            JOIN entity AS replacement
              ON replacement.entity_id = old.replaced_by_entity_id
            WHERE old.lifecycle_state <> 'deprecated'
               OR old.entity_type <> replacement.entity_type
            ORDER BY old.entity_id
            """
        ):
            errors.append(
                f"{row['entity_id']} has an invalid replacement lifecycle or type"
            )
        entity_lifecycle = {
            row["entity_id"]: row["lifecycle_state"]
            for row in connection.execute(
                "SELECT entity_id, lifecycle_state FROM entity ORDER BY entity_id"
            )
        }
        for alias in connection.execute(
            "SELECT alias_id, entity_id FROM alias ORDER BY alias_id"
        ):
            target = alias["entity_id"]
            visited: set[str] = set()
            while target in replacement_edges and target not in visited:
                visited.add(target)
                target = replacement_edges[target]
            if (
                target not in visited
                and entity_lifecycle.get(target) == "deprecated"
            ):
                errors.append(
                    f"{alias['alias_id']} resolves to deprecated {target} "
                    "without a replacement"
                )

        element_numbers = [
            row[0]
            for row in connection.execute(
                "SELECT atomic_number FROM element ORDER BY atomic_number"
            )
        ]
        if element_numbers != list(range(1, 119)):
            errors.append("element table must contain atomic numbers 1 through 118")
        incomplete_elements = scalar(
            connection,
            """
            SELECT count(*)
            FROM element
            WHERE group_block IS NULL OR group_block = ''
               OR electron_configuration IS NULL OR electron_configuration = ''
               OR standard_state IS NULL OR standard_state = ''
            """,
        )
        if incomplete_elements:
            errors.append(
                f"{incomplete_elements} elements lack periodic-table metadata"
            )

        invalid_nuclide_coordinates = scalar(
            connection,
            """
            SELECT count(*)
            FROM nuclide AS n
            JOIN element AS e ON e.entity_id = n.element_id
            WHERE n.proton_count <> e.atomic_number
            """
        )
        if invalid_nuclide_coordinates:
            errors.append(
                f"{invalid_nuclide_coordinates} nuclides disagree with element atomic numbers"
            )

        natural_nuclides = [
            row["nuclide_id"]
            for row in connection.execute(
                """
                SELECT nuclide_id
                FROM nuclide_designation
                WHERE designation = 'natural_isotopic_composition'
                ORDER BY nuclide_id
                """
            )
        ]
        abundance_totals: dict[str, Fraction] = defaultdict(Fraction)
        for nuclide_id in natural_nuclides:
            properties = {
                row["property_id"]: row
                for row in connection.execute(
                    """
                    SELECT property_id, value_numerator, value_denominator
                    FROM observation
                    WHERE subject_entity_id = ?
                      AND property_id IN (
                          'property:relative_atomic_mass',
                          'property:isotopic_composition'
                      )
                    """,
                    (nuclide_id,),
                )
            }
            required = {
                "property:relative_atomic_mass",
                "property:isotopic_composition",
            }
            if properties.keys() != required:
                errors.append(
                    f"{nuclide_id} lacks exactly one mass and abundance observation"
                )
                continue
            abundance_row = properties["property:isotopic_composition"]
            abundance = Fraction(
                abundance_row["value_numerator"],
                abundance_row["value_denominator"],
            )
            if not 0 < abundance <= 1:
                errors.append(f"{nuclide_id} has invalid isotopic composition {abundance}")
                continue
            element_id = connection.execute(
                "SELECT element_id FROM nuclide WHERE entity_id = ?",
                (nuclide_id,),
            ).fetchone()[0]
            abundance_totals[element_id] += abundance
        for element_id, total in sorted(abundance_totals.items()):
            if total != 1:
                errors.append(
                    f"representative isotopic compositions for {element_id} sum to {total}"
                )

        for mass in connection.execute(
            """
            SELECT o.observation_id, o.subject_entity_id, o.value_numerator,
                   o.value_denominator, o.unit_id, o.source_id
            FROM observation AS o
            JOIN chemical_species AS cs
              ON cs.entity_id = o.subject_entity_id
            WHERE o.property_id = 'property:molar_mass'
              AND cs.species_kind <> 'unresolved'
            ORDER BY o.observation_id
            """
        ):
            expected = Fraction(0)
            verifiable = True
            for component in connection.execute(
                """
                SELECT element_id, atom_count
                FROM species_element
                WHERE species_id = ?
                ORDER BY element_id
                """,
                (mass["subject_entity_id"],),
            ):
                atomic_masses = list(
                    connection.execute(
                        """
                        SELECT value_numerator, value_denominator, unit_id
                        FROM observation
                        WHERE subject_entity_id = ?
                          AND property_id = 'property:atomic_mass'
                          AND source_id = ?
                        ORDER BY observation_id
                        """,
                        (component["element_id"], mass["source_id"]),
                    )
                )
                if len(atomic_masses) != 1:
                    errors.append(
                        f"{mass['observation_id']} cannot be verified: "
                        f"{component['element_id']} has {len(atomic_masses)} "
                        "same-source atomic-mass observations"
                    )
                    verifiable = False
                    continue
                atomic_mass = atomic_masses[0]
                expected += component["atom_count"] * exact_si_value(
                    connection,
                    atomic_mass["value_numerator"],
                    atomic_mass["value_denominator"],
                    atomic_mass["unit_id"],
                )
            if verifiable:
                actual = exact_si_value(
                    connection,
                    mass["value_numerator"],
                    mass["value_denominator"],
                    mass["unit_id"],
                )
                if actual != expected:
                    errors.append(
                        f"{mass['observation_id']} has formula-mass mismatch: "
                        f"stored {actual}, composed {expected} in SI units"
                    )

        for reaction in connection.execute(
            "SELECT reaction_id FROM reaction ORDER BY reaction_id"
        ):
            balances: dict[str, Fraction] = defaultdict(Fraction)
            charge = Fraction(0)
            roles: set[str] = set()
            for participant in connection.execute(
                """
                SELECT rp.role, rp.species_id, rp.coefficient_numerator,
                       rp.coefficient_denominator, cs.electric_charge
                FROM reaction_participant AS rp
                JOIN chemical_species AS cs ON cs.entity_id = rp.species_id
                WHERE rp.reaction_id = ?
                """,
                (reaction["reaction_id"],),
            ):
                roles.add(participant["role"])
                direction = {
                    "reactant": -1,
                    "product": 1,
                    "catalyst": 0,
                    "solvent": 0,
                }[participant["role"]]
                coefficient = direction * Fraction(
                    participant["coefficient_numerator"],
                    participant["coefficient_denominator"],
                )
                charge += coefficient * participant["electric_charge"]
                for component in connection.execute(
                    """
                    SELECT element_id, atom_count
                    FROM species_element
                    WHERE species_id = ?
                    """,
                    (participant["species_id"],),
                ):
                    balances[component["element_id"]] += (
                        coefficient * component["atom_count"]
                    )

            unbalanced = {
                element_id: amount
                for element_id, amount in balances.items()
                if amount
            }
            if unbalanced:
                errors.append(
                    f"{reaction['reaction_id']} has unbalanced elements: "
                    + ", ".join(
                        f"{element_id}={amount}"
                        for element_id, amount in sorted(unbalanced.items())
                    )
                )
            if charge:
                errors.append(f"{reaction['reaction_id']} has charge imbalance {charge}")
            if not {"reactant", "product"} <= roles:
                errors.append(
                    f"{reaction['reaction_id']} must have reactants and products"
                )

        for row in connection.execute(
            """
            SELECT rp.reaction_id, rp.species_id, rp.phase_id
            FROM reaction_participant AS rp
            WHERE NOT EXISTS (
                SELECT 1
                FROM species_phase AS supported
                WHERE supported.species_id = rp.species_id
                  AND supported.phase_id = rp.phase_id
            )
            ORDER BY rp.reaction_id, rp.species_id, rp.phase_id
            """
        ):
            errors.append(
                f"{row['reaction_id']} uses unsupported phase "
                f"{row['phase_id']} for {row['species_id']}"
            )

        for row in connection.execute(
            """
            SELECT observation_id
            FROM observation AS o
            JOIN property_definition AS p USING (property_id)
            JOIN unit AS u USING (unit_id)
            WHERE p.quantity_kind <> u.quantity_kind
            """
        ):
            errors.append(
                f"{row['observation_id']} uses a unit of the wrong quantity kind"
            )

        for row in connection.execute(
            """
            SELECT p.property_id
            FROM property_definition AS p
            JOIN unit AS u ON u.unit_id = p.canonical_unit_id
            WHERE p.quantity_kind <> u.quantity_kind
            ORDER BY p.property_id
            """
        ):
            errors.append(
                f"{row['property_id']} has a canonical unit of the wrong quantity kind"
            )

        for row in connection.execute(
            """
            SELECT unit_id
            FROM unit
            WHERE si_scale_numerator = 0
               OR (
                   quantity_kind <> 'temperature'
                   AND si_offset_numerator <> 0
               )
            ORDER BY unit_id
            """
        ):
            errors.append(f"{row['unit_id']} has an invalid SI conversion")

        for row in connection.execute(
            """
            SELECT cv.condition_set_id, cv.quantity_kind, u.quantity_kind AS unit_kind
            FROM condition_value AS cv
            JOIN unit AS u USING (unit_id)
            ORDER BY cv.condition_set_id, cv.quantity_kind
            """
        ):
            if quantity_family(row["quantity_kind"]) != row["unit_kind"]:
                errors.append(
                    f"{row['condition_set_id']} condition "
                    f"{row['quantity_kind']} uses {row['unit_kind']} units"
                )

        typed_unit_references = (
            (
                "reaction energy",
                """
                SELECT reaction_id AS identity, u.quantity_kind
                FROM reaction
                JOIN unit AS u ON u.unit_id = energy_unit_id
                WHERE energy_unit_id IS NOT NULL
                """,
                "energy",
            ),
            (
                "nuclide excitation energy",
                """
                SELECT entity_id AS identity, u.quantity_kind
                FROM nuclide
                JOIN unit AS u ON u.unit_id = excitation_energy_unit_id
                WHERE excitation_energy_unit_id IS NOT NULL
                """,
                "energy",
            ),
            (
                "cross-section energy axis",
                """
                SELECT channel_id || ':' || point_index AS identity,
                       u.quantity_kind
                FROM nuclear_cross_section_point
                JOIN unit AS u ON u.unit_id = energy_unit_id
                """,
                "energy",
            ),
            (
                "nuclear cross section",
                """
                SELECT channel_id || ':' || point_index AS identity,
                       u.quantity_kind
                FROM nuclear_cross_section_point
                JOIN unit AS u ON u.unit_id = cross_section_unit_id
                """,
                "cross_section",
            ),
            (
                "cross-section velocity axis",
                """
                SELECT channel_id || ':' || point_index AS identity,
                       u.quantity_kind
                FROM nuclear_cross_section_velocity_point
                JOIN unit AS u ON u.unit_id = speed_unit_id
                """,
                "speed",
            ),
            (
                "velocity-indexed nuclear cross section",
                """
                SELECT channel_id || ':' || point_index AS identity,
                       u.quantity_kind
                FROM nuclear_cross_section_velocity_point
                JOIN unit AS u ON u.unit_id = cross_section_unit_id
                """,
                "cross_section",
            ),
        )
        for label, query, expected_kind in typed_unit_references:
            for row in connection.execute(query):
                if row["quantity_kind"] != expected_kind:
                    errors.append(
                        f"{label} {row['identity']} uses "
                        f"{row['quantity_kind']} units"
                    )

        for row in connection.execute(
            """
            SELECT clp.crystal_structure_id, clp.parameter, u.quantity_kind
            FROM crystal_lattice_parameter AS clp
            JOIN unit AS u USING (unit_id)
            ORDER BY clp.crystal_structure_id, clp.parameter
            """
        ):
            expected_kind = (
                "length"
                if row["parameter"] in {"a", "b", "c"}
                else "angle"
            )
            if row["quantity_kind"] != expected_kind:
                errors.append(
                    f"{row['crystal_structure_id']} lattice parameter "
                    f"{row['parameter']} uses {row['quantity_kind']} units"
                )

        for row in connection.execute(
            """
            SELECT spectrum_id, axis_unit_id, intensity_unit_id
            FROM spectrum
            ORDER BY spectrum_id
            """
        ):
            axis_kind = connection.execute(
                "SELECT quantity_kind FROM unit WHERE unit_id = ?",
                (row["axis_unit_id"],),
            ).fetchone()[0]
            intensity_kind = connection.execute(
                "SELECT quantity_kind FROM unit WHERE unit_id = ?",
                (row["intensity_unit_id"],),
            ).fetchone()[0]
            if axis_kind not in {"frequency", "wavelength", "wavenumber", "energy", "length"}:
                errors.append(
                    f"spectrum {row['spectrum_id']} uses invalid axis units "
                    f"{row['axis_unit_id']}"
                )
            if intensity_kind not in {
                "relative_intensity",
                "dimensionless",
                "spectral_intensity",
            }:
                errors.append(
                    f"spectrum {row['spectrum_id']} uses invalid intensity units "
                    f"{row['intensity_unit_id']}"
                )

        condition_bounds: dict[tuple[str, str], dict[str, Fraction]] = defaultdict(dict)
        for row in connection.execute(
            """
            SELECT condition_set_id, quantity_kind, value_numerator,
                   value_denominator, unit_id
            FROM condition_value
            WHERE quantity_kind LIKE '%_min'
               OR quantity_kind LIKE '%_max'
            ORDER BY condition_set_id, quantity_kind
            """
        ):
            family = quantity_family(row["quantity_kind"])
            bound = row["quantity_kind"][-3:]
            condition_bounds[(row["condition_set_id"], family)][bound] = (
                exact_si_value(
                    connection,
                    row["value_numerator"],
                    row["value_denominator"],
                    row["unit_id"],
                )
            )
        for (condition_set_id, family), bounds in sorted(condition_bounds.items()):
            if bounds.keys() != {"min", "max"}:
                errors.append(
                    f"{condition_set_id} has an incomplete {family} range"
                )
            elif bounds["min"] > bounds["max"]:
                errors.append(
                    f"{condition_set_id} has reversed {family} bounds"
                )

        for row in connection.execute(
            """
            SELECT entity_id
            FROM chemical_species AS cs
            WHERE cs.species_kind <> 'unresolved'
              AND NOT EXISTS (
                  SELECT 1 FROM species_element
                  WHERE species_id = cs.entity_id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM species_nuclide
                  WHERE species_id = cs.entity_id
              )
            """
        ):
            errors.append(f"{row['entity_id']} has no authored composition")

        for row in connection.execute(
            """
            SELECT cs.entity_id
            FROM chemical_species AS cs
            WHERE EXISTS (
                SELECT 1 FROM species_element
                WHERE species_id = cs.entity_id
            )
              AND EXISTS (
                SELECT 1 FROM species_nuclide
                WHERE species_id = cs.entity_id
            )
            ORDER BY cs.entity_id
            """
        ):
            errors.append(
                f"{row['entity_id']} mixes elemental and nuclidic composition"
            )

        for molecule in connection.execute(
            """
            SELECT m.species_id, m.total_formal_charge, cs.electric_charge
            FROM molecule AS m
            JOIN chemical_species AS cs ON cs.entity_id = m.species_id
            ORDER BY m.species_id
            """
        ):
            atoms = list(
                connection.execute(
                    """
                    SELECT atom_index, element_id, nuclide_id, formal_charge
                    FROM molecular_atom
                    WHERE species_id = ?
                    ORDER BY atom_index
                    """,
                    (molecule["species_id"],),
                )
            )
            indices = [row["atom_index"] for row in atoms]
            if indices != list(range(len(indices))):
                errors.append(
                    f"{molecule['species_id']} molecular atom indices are not contiguous"
                )
            formal_charge = sum(row["formal_charge"] for row in atoms)
            if (
                formal_charge != molecule["total_formal_charge"]
                or formal_charge != molecule["electric_charge"]
            ):
                errors.append(
                    f"{molecule['species_id']} molecular formal charge disagrees "
                    "with its species charge"
                )
            graph_elements: dict[str, int] = defaultdict(int)
            graph_nuclides: dict[str, int] = defaultdict(int)
            for atom in atoms:
                graph_elements[atom["element_id"]] += 1
                if atom["nuclide_id"] is not None:
                    graph_nuclides[atom["nuclide_id"]] += 1
                    nuclide_element = connection.execute(
                        "SELECT element_id FROM nuclide WHERE entity_id = ?",
                        (atom["nuclide_id"],),
                    ).fetchone()
                    if (
                        nuclide_element is not None
                        and nuclide_element[0] != atom["element_id"]
                    ):
                        errors.append(
                            f"{molecule['species_id']} atom {atom['atom_index']} "
                            "uses a nuclide of a different element"
                        )
            authored_elements = {
                row["element_id"]: row["atom_count"]
                for row in connection.execute(
                    """
                    SELECT element_id, atom_count
                    FROM species_element
                    WHERE species_id = ?
                    """,
                    (molecule["species_id"],),
                )
            }
            authored_nuclides = {
                row["nuclide_id"]: row["atom_count"]
                for row in connection.execute(
                    """
                    SELECT nuclide_id, atom_count
                    FROM species_nuclide
                    WHERE species_id = ?
                    """,
                    (molecule["species_id"],),
                )
            }
            if authored_elements and graph_elements != authored_elements:
                errors.append(
                    f"{molecule['species_id']} molecular graph disagrees with "
                    "elemental composition"
                )
            if authored_nuclides and graph_nuclides != authored_nuclides:
                errors.append(
                    f"{molecule['species_id']} molecular graph disagrees with "
                    "nuclidic composition"
                )

        for row in connection.execute(
            """
            SELECT material_id, count(DISTINCT basis) AS basis_count
            FROM material_component
            GROUP BY material_id
            HAVING count(DISTINCT basis) <> 1
            ORDER BY material_id
            """
        ):
            errors.append(
                f"{row['material_id']} mixes incompatible composition bases"
            )
        material_totals: dict[tuple[str, str], Fraction] = defaultdict(Fraction)
        for row in connection.execute(
            """
            SELECT material_id, basis, amount_numerator, amount_denominator
            FROM material_component
            WHERE basis <> 'unspecified'
            ORDER BY material_id, species_id
            """
        ):
            material_totals[(row["material_id"], row["basis"])] += Fraction(
                row["amount_numerator"],
                row["amount_denominator"],
            )
        for (material_id, basis), total in sorted(material_totals.items()):
            if total != 1:
                errors.append(
                    f"{material_id} {basis} components sum to {total}"
                )

        mixture_edges: dict[str, set[str]] = defaultdict(set)
        for row in connection.execute(
            """
            SELECT mc.mixture_id, mc.component_entity_id
            FROM mixture_component AS mc
            JOIN mixture AS nested
              ON nested.entity_id = mc.component_entity_id
            ORDER BY mc.mixture_id, mc.component_entity_id
            """
        ):
            mixture_edges[row["mixture_id"]].add(row["component_entity_id"])
        for cycle in graph_cycles(mixture_edges):
            errors.append(
                "mixture composition cycle: " + " -> ".join((*cycle, cycle[0]))
            )

        lattice_occupancies: dict[tuple[str, str], Fraction] = defaultdict(Fraction)
        for row in connection.execute(
            """
            SELECT crystal_structure_id, site_id, occupancy_numerator,
                   occupancy_denominator
            FROM crystal_lattice_site
            ORDER BY crystal_structure_id, site_id
            """
        ):
            lattice_occupancies[
                (row["crystal_structure_id"], row["site_id"])
            ] += Fraction(
                row["occupancy_numerator"],
                row["occupancy_denominator"],
            )
        for (structure_id, site_id), occupancy in sorted(
            lattice_occupancies.items()
        ):
            if occupancy <= 1:
                continue
            errors.append(
                f"{structure_id} site {site_id} has occupancy {occupancy} above one"
            )

        for row in connection.execute(
            """
            SELECT channel_id, probability_numerator, probability_denominator
            FROM nuclear_channel
            WHERE probability_numerator IS NOT NULL
            ORDER BY channel_id
            """
        ):
            probability = Fraction(
                row["probability_numerator"],
                row["probability_denominator"],
            )
            if not 0 <= probability <= 1:
                errors.append(
                    f"{row['channel_id']} has invalid probability {probability}"
                )

        for row in connection.execute(
            """
            SELECT channel.channel_id, channel.parent_nuclide_id,
                   observation.subject_entity_id, observation.property_id
            FROM nuclear_channel AS channel
            JOIN observation
              ON observation.observation_id =
                 channel.partial_half_life_observation_id
            WHERE observation.subject_entity_id <> channel.parent_nuclide_id
               OR observation.property_id <> 'property:half_life'
            ORDER BY channel.channel_id
            """
        ):
            errors.append(
                f"{row['channel_id']} has a partial half-life observation "
                "for the wrong subject or property"
            )

        branch_groups = connection.execute(
            """
            SELECT DISTINCT parent_nuclide_id, condition_set_id
            FROM nuclear_channel
            WHERE probability_numerator IS NOT NULL
            """
        )
        for group in branch_groups:
            clauses = ["parent_nuclide_id = ?", "probability_numerator IS NOT NULL"]
            parameters: list[str] = [group["parent_nuclide_id"]]
            if group["condition_set_id"] is None:
                clauses.append("condition_set_id IS NULL")
            else:
                clauses.append("condition_set_id = ?")
                parameters.append(group["condition_set_id"])
            total = sum(
                (
                    Fraction(row["probability_numerator"], row["probability_denominator"])
                    for row in connection.execute(
                        f"""
                        SELECT probability_numerator, probability_denominator
                        FROM nuclear_channel
                        WHERE {' AND '.join(clauses)}
                        """,
                        parameters,
                    )
                ),
                Fraction(0),
            )
            if total != 1:
                errors.append(
                    "nuclear branches for "
                    f"{group['parent_nuclide_id']} under "
                    f"{group['condition_set_id'] or 'unspecified conditions'} "
                    f"sum to {total}"
                )

        ordered_series = {
            "spectrum": (
                "spectrum_point",
                "spectrum_id",
                "axis_numerator",
                "axis_denominator",
            ),
            "nuclear cross section": (
                "nuclear_cross_section_point",
                "channel_id",
                "energy_numerator",
                "energy_denominator",
            ),
            "nuclear cross section velocity": (
                "nuclear_cross_section_velocity_point",
                "channel_id",
                "speed_numerator",
                "speed_denominator",
            ),
        }
        for label, (table, parent, numerator, denominator) in ordered_series.items():
            current_parent = None
            previous = None
            expected_index = 0
            for row in connection.execute(
                f"""
                SELECT {parent}, point_index, {numerator}, {denominator}
                FROM {table}
                ORDER BY {parent}, point_index
                """
            ):
                if row[parent] != current_parent:
                    current_parent = row[parent]
                    previous = None
                    expected_index = 0
                if row["point_index"] != expected_index:
                    errors.append(
                        f"{label} {row[parent]} point indices are not contiguous"
                    )
                    expected_index = row["point_index"]
                value = Fraction(row[numerator], row[denominator])
                if previous is not None and value <= previous:
                    errors.append(
                        f"{label} {row[parent]} axes are not strictly increasing"
                    )
                    break
                previous = value
                expected_index += 1
    finally:
        connection.close()
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    failures = validate(arguments.database)
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        raise SystemExit(1)
    print(f"validated {arguments.database}")
