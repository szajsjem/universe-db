from __future__ import annotations

from fractions import Fraction
from pathlib import Path
import sqlite3
import unittest


ROOT = Path(__file__).resolve().parents[1]
DATASET_ID = "dataset:industrial-chemistry-2026-08-01"


class IndustrialChemistrySeedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(ROOT / "universe.db")

    def tearDown(self) -> None:
        self.connection.close()

    def equation(
        self, reaction_id: str
    ) -> set[tuple[str, str, str, Fraction]]:
        return {
            (role, species_id, phase_id, Fraction(numerator, denominator))
            for role, species_id, phase_id, numerator, denominator
            in self.connection.execute(
                """
                SELECT role, species_id, phase_id,
                       coefficient_numerator, coefficient_denominator
                FROM reaction_participant
                WHERE reaction_id = ?
                """,
                (reaction_id,),
            )
        }

    def test_slice_has_expected_curated_scope(self) -> None:
        species = self.connection.execute(
            """
            SELECT count(*)
            FROM entity
            WHERE dataset_id = ? AND entity_type = 'chemical_species'
            """,
            (DATASET_ID,),
        ).fetchone()[0]
        reactions = self.connection.execute(
            "SELECT count(*) FROM reaction WHERE dataset_id = ?",
            (DATASET_ID,),
        ).fetchone()[0]
        observations = self.connection.execute(
            "SELECT count(*) FROM observation WHERE dataset_id = ?",
            (DATASET_ID,),
        ).fetchone()[0]
        self.assertEqual(24, species)
        self.assertEqual(35, reactions)
        self.assertEqual(0, observations)

    def test_complete_carbon_combustion_equation(self) -> None:
        self.assertEqual(
            {
                ("reactant", "chem:carbon", "phase:solid", Fraction(1)),
                ("reactant", "chem:oxygen", "phase:gas", Fraction(1)),
                ("product", "chem:carbon_dioxide", "phase:gas", Fraction(1)),
            },
            self.equation("reaction:carbon_complete_combustion"),
        )

    def test_hematite_reduction_equation(self) -> None:
        self.assertEqual(
            {
                ("reactant", "chem:hematite", "phase:solid", Fraction(1)),
                ("reactant", "chem:carbon_monoxide", "phase:gas", Fraction(3)),
                ("product", "chem:iron", "phase:solid", Fraction(2)),
                ("product", "chem:carbon_dioxide", "phase:gas", Fraction(3)),
            },
            self.equation("reaction:hematite_carbon_monoxide_reduction"),
        )

    def test_copper_electrowinning_equation(self) -> None:
        self.assertEqual(
            {
                ("reactant", "chem:copper_sulfate", "phase:aqueous", Fraction(2)),
                ("reactant", "chem:water", "phase:aqueous", Fraction(2)),
                ("product", "chem:copper", "phase:solid", Fraction(2)),
                ("product", "chem:oxygen", "phase:gas", Fraction(1)),
                ("product", "chem:sulfuric_acid", "phase:aqueous", Fraction(2)),
            },
            self.equation("reaction:copper_electrowinning"),
        )
        condition = self.connection.execute(
            """
            SELECT condition_set_id, relationship
            FROM reaction_condition
            WHERE reaction_id = 'reaction:copper_electrowinning'
            """
        ).fetchone()
        self.assertEqual(
            ("condition:direct_current_electrolysis", "required"), condition
        )

    def test_acids_and_salts_have_typed_dissociations(self) -> None:
        rows = dict(
            self.connection.execute(
                """
                SELECT parent_species_id, dissociation_type
                FROM dissociation
                WHERE reaction_id IN (
                    'reaction:hydrochloric_acid_dissociation',
                    'reaction:nitric_acid_dissociation',
                    'reaction:sulfuric_acid_dissociation',
                    'reaction:sodium_chloride_dissociation',
                    'reaction:sodium_sulfate_dissociation',
                    'reaction:calcium_chloride_dissociation'
                )
                """
            )
        )
        self.assertEqual(
            {
                "chem:hydrochloric_acid": "acid_base",
                "chem:nitric_acid": "acid_base",
                "chem:sulfuric_acid": "acid_base",
                "chem:halite": "salt",
                "chem:sodium_sulfate": "salt",
                "chem:calcium_chloride": "salt",
            },
            rows,
        )


if __name__ == "__main__":
    unittest.main()
