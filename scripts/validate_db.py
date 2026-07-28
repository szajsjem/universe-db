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


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            errors.append("SQLite integrity_check failed")
        for row in connection.execute("PRAGMA foreign_key_check"):
            errors.append(f"foreign key violation: {tuple(row)}")

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

        for reaction in connection.execute(
            "SELECT reaction_id FROM reaction ORDER BY reaction_id"
        ):
            balances: dict[str, Fraction] = defaultdict(Fraction)
            charge = Fraction(0)
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
        }
        for label, (table, parent, numerator, denominator) in ordered_series.items():
            current_parent = None
            previous = None
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
                value = Fraction(row[numerator], row[denominator])
                if previous is not None and value <= previous:
                    errors.append(
                        f"{label} {row[parent]} axes are not strictly increasing"
                    )
                    break
                previous = value
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
