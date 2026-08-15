from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from scripts.build_db import build
from scripts.clean_wikipedia_candidates import apply_cleanup, build_plan, formula_charge


def seed_page(connection: sqlite3.Connection) -> str:
    run_id = "run:test-cleanup"
    page_id = "page:test-cleanup"
    connection.execute(
        """
        INSERT INTO wikipedia_parse_run(
            run_id, started_at, completed_at, model, archive_name,
            archive_format, archive_sha256, archive_page_count,
            license_spdx_id, status, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            "2026-08-15T00:00:00+00:00",
            "2026-08-15T00:01:00+00:00",
            "test-model",
            "fixture.zip",
            "universe-db-wikipedia-category-snapshot-v1",
            "a" * 64,
            1,
            "CC-BY-SA-4.0",
            "completed",
            None,
        ),
    )
    connection.execute(
        """
        INSERT INTO wikipedia_page_parse(
            page_parse_id, run_id, sequence_index, source_entry_key,
            source_path, input_format, page_id, revision_id, title,
            source_url, source_timestamp, content_sha256, content_chars,
            submitted_chars, status, response_id, error_text, created_at,
            completed_at
        ) VALUES (?, ?, 0, ?, ?, 'wikitext', 1, 1, ?, ?, ?, ?, 100, 100,
                  'parsed', NULL, NULL, ?, ?)
        """,
        (
            page_id,
            run_id,
            "page:1:revision:1",
            "pages/1.json",
            "Fixture",
            "https://example.test/fixture",
            "2026-08-15T00:00:00Z",
            "b" * 64,
            "2026-08-15T00:00:00+00:00",
            "2026-08-15T00:01:00+00:00",
        ),
    )
    return page_id


def add_candidate(
    connection: sqlite3.Connection,
    page_id: str,
    index: int,
    candidate_id: str,
    kind: str,
    name: str,
    formula: str | None,
    charge: int | None,
    atomic_number: int | None = None,
    proton_count: int | None = None,
    neutron_count: int | None = None,
    isomer_index: int | None = None,
    existing_entity_id: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO unverified_entity_candidate(
            candidate_id, page_parse_id, candidate_index, candidate_kind,
            name, proposed_id, existing_entity_id, existing_reaction_id,
            formula, electric_charge, atomic_number, proton_count,
            neutron_count, isomer_index, observed, confidence, evidence_text
        ) VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, ?, ?, ?, ?, ?,
                  ?, NULL, 'high', ?)
        """,
        (
            candidate_id,
            page_id,
            index,
            kind,
            name,
            existing_entity_id,
            formula,
            charge,
            atomic_number,
            proton_count,
            neutron_count,
            isomer_index,
            f"Evidence for {name}.",
        ),
    )


def add_temperature_fact(
    connection: sqlite3.Connection,
    candidate_id: str,
    index: int,
    fact_id: str,
    field: str,
    value: str,
    unit: str,
) -> None:
    connection.execute(
        """
        INSERT INTO unverified_candidate_fact(
            candidate_fact_id, candidate_id, fact_index, field_key,
            value_decimal_text, value_numerator, value_denominator,
            value_text, unit_text, uncertainty_decimal_text,
            uncertainty_numerator, uncertainty_denominator, evidence_text
        ) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, ?, NULL, NULL, NULL, ?)
        """,
        (fact_id, candidate_id, index, field, value, unit, f"{field}: {value} {unit}"),
    )


def add_text_temperature_fact(
    connection: sqlite3.Connection,
    candidate_id: str,
    index: int,
    fact_id: str,
    field: str,
    value: str,
    unit: str,
) -> None:
    connection.execute(
        """
        INSERT INTO unverified_candidate_fact(
            candidate_fact_id, candidate_id, fact_index, field_key,
            value_decimal_text, value_numerator, value_denominator,
            value_text, unit_text, uncertainty_decimal_text,
            uncertainty_numerator, uncertainty_denominator, evidence_text
        ) VALUES (?, ?, ?, ?, NULL, NULL, NULL, ?, ?, NULL, NULL, NULL, ?)
        """,
        (fact_id, candidate_id, index, field, value, unit, f"{field}: {value} {unit}"),
    )


class CleanWikipediaCandidatesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "fixture.db"
        build(self.database)
        self.connection = sqlite3.connect(self.database)
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.page_id = seed_page(self.connection)

    def tearDown(self) -> None:
        self.connection.close()
        self.directory.cleanup()

    def test_formula_charge_avoids_polyatomic_subscript_ambiguity(self) -> None:
        self.assertEqual(1, formula_charge("NH4+"))
        self.assertEqual(3, formula_charge("Al3+"))
        self.assertEqual(-2, formula_charge("SO4 2-"))
        self.assertEqual(-2, formula_charge("[PtCl4]^2-"))
        self.assertEqual(-2, formula_charge("HOPO_3^{2-}"))

    def test_merges_phase_names_and_consensus_formula_but_not_isomers(self) -> None:
        values = [
            ("water-1", "Water", "H2O", 0),
            ("water-2", "water", "H2O", None),
            ("water-3", "water vapor", "H2O", 0),
            ("water-4", "water vapour", "H2O", None),
            ("water-typo", "H20", "H20", None),
            ("heavy-water", "heavy water", "D2O", 0),
            ("xylene-meta", "m-xylene", "C8H10", 0),
            ("xylene-para", "p-xylene", "C8H10", 0),
        ]
        for index, (candidate_id, name, formula, charge) in enumerate(values):
            add_candidate(
                self.connection,
                self.page_id,
                index,
                candidate_id,
                "molecule",
                name,
                formula,
                charge,
            )
        self.connection.commit()

        plan = build_plan(self.connection)
        with self.connection:
            merged, corrected, _mapping_corrections, inferred = apply_cleanup(
                self.connection, plan
            )

        self.assertEqual(4, merged)
        self.assertEqual(0, corrected)
        self.assertEqual(0, inferred)
        water = self.connection.execute(
            """
            SELECT candidate_id, name, formula, electric_charge
            FROM unverified_entity_candidate
            WHERE lower(name) = 'water'
            """
        ).fetchone()
        self.assertIsNotNone(water)
        self.assertEqual("H2O", water[2])
        self.assertEqual(0, water[3])
        self.assertEqual(
            5,
            self.connection.execute(
                """
                SELECT count(*) FROM wikipedia_candidate_mention
                WHERE canonical_candidate_id = ?
                """,
                (water[0],),
            ).fetchone()[0],
        )
        remaining = set(
            self.connection.execute(
                "SELECT name FROM unverified_entity_candidate"
            )
        )
        self.assertIn(("heavy water",), remaining)
        self.assertIn(("m-xylene",), remaining)
        self.assertIn(("p-xylene",), remaining)

    def test_reclassifies_charged_molecule_and_merges_with_ion(self) -> None:
        add_candidate(
            self.connection,
            self.page_id,
            0,
            "hydronium-molecule",
            "molecule",
            "hydronium",
            "H3O+",
            None,
        )
        add_candidate(
            self.connection,
            self.page_id,
            1,
            "hydronium-ion",
            "ion",
            "Hydronium",
            "H3O+",
            1,
        )
        self.connection.commit()

        plan = build_plan(self.connection)
        with self.connection:
            merged, _corrected, _mapping_corrections, _inferred = apply_cleanup(
                self.connection, plan
            )

        self.assertEqual(1, merged)
        row = self.connection.execute(
            "SELECT candidate_kind, electric_charge FROM unverified_entity_candidate"
        ).fetchone()
        self.assertEqual(("ion", 1), row)

    def test_merges_nuclides_but_rejects_incredible_existing_mapping(self) -> None:
        values = [
            ("helium-4-a", "Helium-4", "4He", 0),
            ("helium-4-b", "helium-4", "He-4", 0),
            ("helium-4-c", "Helium", "He", 0),
            ("helium-4-alpha", "alpha particle", "α", 2),
            ("bad-dineutron", "Dineutron", "2n", 0),
        ]
        for index, (candidate_id, name, formula, charge) in enumerate(values):
            add_candidate(
                self.connection,
                self.page_id,
                index,
                candidate_id,
                "nuclide",
                name,
                formula,
                charge,
                2,
                2,
                2,
                0,
                "nuclide:helium-4",
            )
        self.connection.commit()

        plan = build_plan(self.connection)
        with self.connection:
            merged, _corrected, mapping_corrections, _inferred = apply_cleanup(
                self.connection, plan
            )

        self.assertEqual(3, merged)
        self.assertEqual(1, mapping_corrections)
        rows = self.connection.execute(
            "SELECT name FROM unverified_entity_candidate ORDER BY name"
        ).fetchall()
        self.assertEqual(2, len(rows))
        self.assertIn(("Dineutron",), rows)

    def test_merges_safe_elemental_diatomic_synonyms(self) -> None:
        names = [
            "oxygen",
            "dioxygen",
            "molecular oxygen",
            "oxygen molecule",
            "diatomic oxygen",
        ]
        for index, name in enumerate(names):
            add_candidate(
                self.connection,
                self.page_id,
                index,
                f"oxygen-{index}",
                "molecule",
                name,
                "O2",
                0,
            )
        add_candidate(
            self.connection,
            self.page_id,
            len(names),
            "singlet-oxygen",
            "molecule",
            "singlet oxygen",
            "O2",
            0,
        )
        add_candidate(
            self.connection,
            self.page_id,
            len(names) + 1,
            "atomic-oxygen-misplaced",
            "molecule",
            "oxygen",
            "O",
            0,
        )
        add_candidate(
            self.connection,
            self.page_id,
            len(names) + 2,
            "unknown-oxygen",
            "molecule",
            "oxygen",
            None,
            None,
        )
        self.connection.commit()

        plan = build_plan(self.connection)
        with self.connection:
            merged, _corrected, _mapping_corrections, _inferred = apply_cleanup(
                self.connection, plan
            )

        self.assertEqual(4, merged)
        rows = self.connection.execute(
            "SELECT name FROM unverified_entity_candidate ORDER BY name"
        ).fetchall()
        self.assertEqual(4, len(rows))
        self.assertIn(("singlet oxygen",), rows)

    def test_derives_solid_liquid_and_gas_phases_for_molecules(self) -> None:
        molecules = [
            ("solid", "Solid sample", "X", "melting_point", "140 to 142"),
            ("liquid", "Liquid sample", "Y", "melting_point", "-48"),
            ("gas", "Gas sample", "Z", "boiling_point", "-161.5"),
        ]
        for index, (candidate_id, name, formula, field, value) in enumerate(molecules):
            add_candidate(
                self.connection,
                self.page_id,
                index,
                candidate_id,
                "molecule",
                name,
                formula,
                0,
            )
            add_text_temperature_fact(
                self.connection,
                candidate_id,
                0,
                f"fact:{candidate_id}:first",
                field,
                value,
                "°C",
            )
        add_text_temperature_fact(
            self.connection,
            "liquid",
            1,
            "fact:liquid:boiling",
            "boiling_point",
            "50.8",
            "°C",
        )
        self.connection.commit()

        plan = build_plan(self.connection)
        with self.connection:
            _merged, _corrected, _mapping_corrections, inferred = apply_cleanup(
                self.connection, plan
            )

        self.assertEqual(3, inferred)
        phases = dict(
            self.connection.execute(
                """
                SELECT entity.name, fact.value_text
                FROM unverified_candidate_derived_fact AS fact
                JOIN unverified_entity_candidate AS entity USING(candidate_id)
                """
            )
        )
        self.assertEqual("solid", phases["Solid sample"])
        self.assertEqual("liquid", phases["Liquid sample"])
        self.assertEqual("gas", phases["Gas sample"])

    def test_derives_element_phase_after_element_mentions_are_merged(self) -> None:
        add_candidate(
            self.connection,
            self.page_id,
            0,
            "indium-melting",
            "element",
            "Indium",
            "In",
            None,
            49,
        )
        add_candidate(
            self.connection,
            self.page_id,
            1,
            "indium-boiling",
            "element",
            "indium",
            "In",
            None,
            49,
        )
        add_temperature_fact(
            self.connection,
            "indium-melting",
            0,
            "fact:indium-melting",
            "melting_point",
            "156.6",
            "°C",
        )
        add_temperature_fact(
            self.connection,
            "indium-boiling",
            0,
            "fact:indium-boiling",
            "boiling_point",
            "2080",
            "°C",
        )
        self.connection.commit()

        plan = build_plan(self.connection)
        with self.connection:
            merged, _corrected, _mapping_corrections, inferred = apply_cleanup(
                self.connection, plan
            )

        self.assertEqual(1, merged)
        self.assertEqual(1, inferred)
        row = self.connection.execute(
            """
            SELECT field_key, value_text, normal_temperature_k,
                   source_candidate_fact_ids_json
            FROM unverified_candidate_derived_fact
            """
        ).fetchone()
        self.assertEqual("phase_at_normal_conditions", row[0])
        self.assertEqual("solid", row[1])
        self.assertEqual("293.15", row[2])
        self.assertIn("fact:indium-melting", row[3])
        self.assertIn("fact:indium-boiling", row[3])


if __name__ == "__main__":
    unittest.main()
