from __future__ import annotations

from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from scripts.validate_db import validate
from scripts.export_inorganicengineering import (
    DEFAULT_PROFILE,
    ExportError,
    build_files,
)


ROOT = Path(__file__).resolve().parents[1]


class ValidatorRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary_directory.name) / "malformed.db"
        shutil.copyfile(ROOT / "universe.db", self.database)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def mutate(
        self,
        statement: str,
        parameters: tuple[object, ...] = (),
    ) -> None:
        with sqlite3.connect(self.database) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute(statement, parameters)

    def assert_rejected(self, expected: str) -> None:
        failures = validate(self.database)
        self.assertTrue(
            any(expected in failure for failure in failures),
            f"expected {expected!r} in validation failures: {failures}",
        )

    def test_rejects_formula_mass_disagreement(self) -> None:
        self.mutate(
            """
            UPDATE observation
            SET value_numerator = value_numerator + 1
            WHERE observation_id = 'observation:molar_mass:water'
            """
        )
        self.assert_rejected("formula-mass mismatch")

    def test_export_cannot_bypass_validation(self) -> None:
        self.mutate(
            """
            UPDATE observation
            SET value_numerator = value_numerator + 1
            WHERE observation_id = 'observation:molar_mass:water'
            """
        )
        with self.assertRaisesRegex(
            ExportError,
            "database validation failed:.*formula-mass mismatch",
        ):
            build_files(self.database, DEFAULT_PROFILE)

    def test_rejects_atom_imbalance(self) -> None:
        self.mutate(
            """
            UPDATE species_element
            SET atom_count = 2
            WHERE species_id = 'chem:water'
              AND element_id = 'element:oxygen'
            """
        )
        self.assert_rejected("has unbalanced elements")

    def test_rejects_charge_imbalance(self) -> None:
        self.mutate(
            """
            UPDATE chemical_species
            SET electric_charge = 1
            WHERE entity_id = 'chem:water'
            """
        )
        self.assert_rejected("has charge imbalance")

    def test_rejects_out_of_range_probability_even_when_group_sums_to_one(
        self,
    ) -> None:
        for channel_id, numerator in (
            ("channel:test-negative", -1),
            ("channel:test-over-one", 2),
        ):
            self.mutate(
                """
                INSERT INTO nuclear_channel(
                    channel_id, channel_type, parent_nuclide_id,
                    probability_numerator, probability_denominator,
                    dataset_id, source_id, schema_version
                ) VALUES (?, 'gamma', 'nuclide:hydrogen-1', ?, 1,
                          'dataset:inorganic-engineering-bootstrap',
                          'inorganic-engineering-af5a553', 1)
                """,
                (channel_id, numerator),
            )
        self.assert_rejected("has invalid probability")

    def test_rejects_wrong_unit_dimension(self) -> None:
        self.mutate(
            """
            UPDATE observation
            SET unit_id = 'unit:kelvin'
            WHERE observation_id = 'observation:molar_mass:water'
            """
        )
        self.assert_rejected("uses a unit of the wrong quantity kind")

    def test_rejects_unresolvable_deprecated_alias(self) -> None:
        self.mutate(
            """
            INSERT INTO alias(alias_id, entity_id, scheme, value, source_id)
            VALUES (
                'alias:test:old-copper', 'chem:copper', 'test', 'old-copper',
                'inorganic-engineering-af5a553'
            )
            """
        )
        self.mutate(
            """
            UPDATE entity
            SET lifecycle_state = 'deprecated'
            WHERE entity_id = 'chem:copper'
            """
        )
        self.assert_rejected("resolves to deprecated chem:copper without a replacement")

    def test_rejects_broken_foreign_key_reference(self) -> None:
        self.mutate("DELETE FROM phase WHERE phase_id = 'phase:solid'")
        self.assert_rejected("foreign key violation")

    def test_rejects_replacement_graph_cycle(self) -> None:
        self.mutate(
            """
            UPDATE entity
            SET lifecycle_state = 'deprecated',
                replaced_by_entity_id = CASE entity_id
                    WHEN 'chem:copper' THEN 'chem:iron'
                    WHEN 'chem:iron' THEN 'chem:copper'
                END
            WHERE entity_id IN ('chem:copper', 'chem:iron')
            """
        )
        self.assert_rejected("entity replacement cycle")

    def test_rejects_unsupported_reaction_phase_reference(self) -> None:
        self.mutate(
            """
            UPDATE reaction_participant
            SET phase_id = 'phase:gas'
            WHERE reaction_id = 'reaction:copper_oxide_leaching'
              AND species_id = 'chem:copper_oxide'
            """
        )
        self.assert_rejected("uses unsupported phase")

    def test_rejects_non_normalized_material_composition(self) -> None:
        self.mutate(
            """
            UPDATE material_component
            SET amount_numerator = 1, amount_denominator = 2
            WHERE material_id = 'material:cathode_copper'
            """
        )
        self.assert_rejected("mass_fraction components sum to 1/2")

    def test_rejects_reversed_condition_range(self) -> None:
        self.mutate(
            """
            UPDATE condition_value
            SET value_numerator = 1600000
            WHERE condition_set_id = 'condition:chalcopyrite_roasting_range'
              AND quantity_kind = 'temperature_min'
            """
        )
        self.assert_rejected("has reversed temperature bounds")

    def test_rejects_source_that_disagrees_with_dataset(self) -> None:
        self.mutate(
            """
            UPDATE reaction
            SET source_id = 'pubchem-periodic-table-2026-07-28'
            WHERE reaction_id = 'reaction:chalcopyrite_roasting'
            """
        )
        self.assert_rejected("uses a source different from its dataset")

    def test_rejects_non_redistributable_source(self) -> None:
        self.mutate(
            """
            UPDATE license
            SET redistribution_allowed = 0
            WHERE license_id = 'mit'
            """
        )
        self.assert_rejected("is not licensed for redistribution")


if __name__ == "__main__":
    unittest.main()
