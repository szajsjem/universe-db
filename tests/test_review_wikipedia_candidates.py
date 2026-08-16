from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from scripts.build_db import build
from scripts.clean_wikipedia_candidates import ensure_cleanup_schema
from scripts.review_wikipedia_candidates import (
    AgentTools,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    WikipediaIndex,
    candidate_json,
    ensure_agent_schema,
    run_candidate_agent,
    safe_duplicate,
    select_db,
)


SOURCE_KEY = "page:1:revision:2"
SOURCE_TEXT = "Water is an inorganic compound with the chemical formula H2O."


def rewritten_water() -> dict:
    return {
        "candidate_kind": "molecule",
        "name": "water",
        "proposed_id": "chem:water",
        "existing_id": None,
        "formula": "H2O",
        "electric_charge": 0,
        "atomic_number": None,
        "proton_count": None,
        "neutron_count": None,
        "isomer_index": None,
        "observed": True,
        "confidence": "high",
        "evidence_text": SOURCE_TEXT,
        "aliases": ["oxidane"],
        "composition": [],
        "facts": [],
        "relations": [],
    }


class CandidateAgentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "test.db"
        build(self.database)
        self.connection = sqlite3.connect(self.database)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        ensure_cleanup_schema(self.connection)
        ensure_agent_schema(self.connection)
        self.connection.execute(
            """
            INSERT INTO wikipedia_parse_run(
                run_id, started_at, completed_at, model, archive_name,
                archive_format, archive_sha256, archive_page_count,
                license_spdx_id, status, notes
            ) VALUES ('parse', '2026-01-01T00:00:00Z', NULL, 'model', 'fixture.zip',
                      'fixture', ?, 1, 'CC-BY-SA-4.0', 'completed', NULL)
            """,
            ("0" * 64,),
        )
        self.connection.execute(
            """
            INSERT INTO wikipedia_page_parse(
                page_parse_id, run_id, sequence_index, source_entry_key,
                source_path, input_format, page_id, revision_id, title,
                source_url, source_timestamp, content_sha256, content_chars,
                submitted_chars, status, response_id, error_text, created_at,
                completed_at
            ) VALUES ('page', 'parse', 0, ?, 'pages/1.json', 'wikitext', 1, 2,
                      'Water', 'https://en.wikipedia.org/w/index.php?oldid=2',
                      NULL, ?, ?, ?, 'parsed', NULL, NULL,
                      '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
            """,
            (SOURCE_KEY, "1" * 64, len(SOURCE_TEXT), len(SOURCE_TEXT)),
        )
        self.connection.execute(
            """
            INSERT INTO wikipedia_candidate_agent_run(
                agent_run_id, started_at, model, base_url, archive_name,
                archive_sha256, target_kinds_json, status, target_count
            ) VALUES ('agent', '2026-01-01T00:00:00Z', ?, ?, 'fixture.zip', ?,
                      '["molecule"]', 'running', 1)
            """,
            (DEFAULT_MODEL, DEFAULT_BASE_URL, "2" * 64),
        )
        self._insert_candidate("candidate:water", "water?", "H20")
        self.connection.commit()
        self.wikipedia = WikipediaIndex.__new__(WikipediaIndex)
        self.wikipedia.manifest = {"archive_format": "fixture"}
        self.wikipedia.pages = {
            SOURCE_KEY: {
                "_source_entry_key": SOURCE_KEY,
                "title": "Water",
                "revision_id": 2,
                "_source_url": "https://en.wikipedia.org/w/index.php?oldid=2",
            }
        }
        self.wikipedia._documents = {SOURCE_KEY: SOURCE_TEXT}

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary.cleanup()

    def _insert_candidate(self, candidate_id: str, name: str, formula: str) -> None:
        self.connection.execute(
            """
            INSERT INTO unverified_entity_candidate(
                candidate_id, page_parse_id, candidate_index, candidate_kind,
                name, proposed_id, existing_entity_id, existing_reaction_id,
                formula, electric_charge, atomic_number, proton_count,
                neutron_count, isomer_index, observed, confidence, evidence_text
            ) VALUES (?, 'page',
                      (SELECT count(*) FROM unverified_entity_candidate),
                      'molecule', ?, NULL, NULL, NULL, ?, 0, NULL, NULL,
                      NULL, NULL, 1, 'low', ?)
            """,
            (candidate_id, name, formula, SOURCE_TEXT),
        )

    def test_defaults_target_requested_local_server(self) -> None:
        self.assertEqual("http://127.0.0.1:8080/v1", DEFAULT_BASE_URL)
        self.assertEqual("qwen3.6-35b-a3b-mtp", DEFAULT_MODEL)

    def test_select_db_is_read_only(self) -> None:
        result = select_db(
            self.connection,
            "SELECT name FROM unverified_entity_candidate WHERE candidate_id = ?",
            ["candidate:water"],
        )
        self.assertEqual("water?", result["rows"][0]["name"])
        with self.assertRaisesRegex(ValueError, "only SELECT or WITH"):
            select_db(
                self.connection,
                "UPDATE unverified_entity_candidate SET name = 'bad'",
                [],
            )

    def test_local_wikipedia_search_is_revision_scoped(self) -> None:
        results = self.wikipedia.search("chemical formula", SOURCE_KEY, 2)
        self.assertEqual(1, len(results))
        self.assertEqual(2, results[0]["revision_id"])
        self.assertIn("H2O", results[0]["excerpt"])

    def test_rewrite_requires_read_and_source_search_then_commits(self) -> None:
        tools = AgentTools(
            self.connection,
            self.wikipedia,
            "agent",
            "candidate:water",
            [SOURCE_KEY],
        )
        with self.assertRaisesRegex(ValueError, "select_db must be called"):
            tools.insert(
                {
                    "candidate_id": "candidate:water",
                    "action": "keep",
                    "duplicate_of_candidate_id": None,
                    "candidate": None,
                    "reason": "Source supports the current candidate.",
                }
            )
        tools.call(
            "select_db",
            {
                "sql": "SELECT * FROM unverified_entity_candidate WHERE candidate_id = ?",
                "parameters": ["candidate:water"],
            },
        )
        tools.call(
            "search_wikipedia",
            {"query": "water formula", "source_entry_key": SOURCE_KEY, "limit": 2},
        )
        result = tools.call(
            "insert_db",
            {
                "candidate_id": "candidate:water",
                "action": "rewrite",
                "duplicate_of_candidate_id": None,
                "candidate": rewritten_water(),
                "reason": "Corrected the name and formula from the pinned source.",
            },
        )
        self.assertTrue(result["committed"])
        stored = candidate_json(self.connection, "candidate:water")
        self.assertEqual("water", stored["name"])
        self.assertEqual("H2O", stored["formula"])
        self.assertEqual(["oxidane"], [row["value"] for row in stored["aliases"]])
        review = self.connection.execute(
            "SELECT action, before_json, after_json FROM wikipedia_candidate_agent_review"
        ).fetchone()
        self.assertEqual("rewrite", review["action"])
        self.assertEqual("water?", json.loads(review["before_json"])["name"])
        self.assertEqual("water", json.loads(review["after_json"])["name"])

    def test_rewrite_rejects_evidence_not_in_attached_source(self) -> None:
        bad = rewritten_water()
        bad["evidence_text"] = "Water freezes at exactly zero degrees Celsius."
        tools = AgentTools(
            self.connection,
            self.wikipedia,
            "agent",
            "candidate:water",
            [SOURCE_KEY],
        )
        tools.selected = True
        tools.searched_keys.add(SOURCE_KEY)
        with self.assertRaisesRegex(ValueError, "not verbatim"):
            tools.insert(
                {
                    "candidate_id": "candidate:water",
                    "action": "rewrite",
                    "duplicate_of_candidate_id": None,
                    "candidate": bad,
                    "reason": "This should fail source-evidence validation.",
                }
            )

    def test_agent_loop_executes_native_tool_calls_to_final_insert(self) -> None:
        responses = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "select-1",
                        "type": "function",
                        "function": {
                            "name": "select_db",
                            "arguments": json.dumps(
                                {
                                    "sql": "SELECT * FROM unverified_entity_candidate WHERE candidate_id = ?",
                                    "parameters": ["candidate:water"],
                                }
                            ),
                        },
                    }
                ],
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "search-1",
                        "type": "function",
                        "function": {
                            "name": "search_wikipedia",
                            "arguments": json.dumps(
                                {
                                    "query": "water formula",
                                    "source_entry_key": SOURCE_KEY,
                                    "limit": 2,
                                }
                            ),
                        },
                    }
                ],
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "insert-1",
                        "type": "function",
                        "function": {
                            "name": "insert_db",
                            "arguments": json.dumps(
                                {
                                    "candidate_id": "candidate:water",
                                    "action": "keep",
                                    "duplicate_of_candidate_id": None,
                                    "candidate": None,
                                    "reason": "The archived source supports the staged candidate.",
                                }
                            ),
                        },
                    }
                ],
            },
        ]
        with patch(
            "scripts.review_wikipedia_candidates.call_model", side_effect=responses
        ) as model_call:
            result = run_candidate_agent(
                self.connection,
                self.wikipedia,
                "agent",
                "candidate:water",
                DEFAULT_BASE_URL,
                None,
                DEFAULT_MODEL,
                5,
                1000,
                0,
                10,
            )
        self.assertTrue(result["committed"])
        self.assertEqual(3, model_call.call_count)
        self.assertEqual(
            "keep",
            self.connection.execute(
                "SELECT action FROM wikipedia_candidate_agent_review"
            ).fetchone()[0],
        )

    def test_duplicate_guard_needs_name_and_formula_for_molecules(self) -> None:
        self._insert_candidate("candidate:other", "oxidane", "H20")
        self.connection.commit()
        safe, reason = safe_duplicate(
            self.connection, "candidate:water", "candidate:other"
        )
        self.assertFalse(safe)
        self.assertIn("name/alias", reason)
        self.connection.execute(
            "INSERT INTO unverified_candidate_alias VALUES (?, 0, ?)",
            ("candidate:other", "water?"),
        )
        safe, _ = safe_duplicate(
            self.connection, "candidate:water", "candidate:other"
        )
        self.assertTrue(safe)

    def test_duplicate_insert_merges_staging_rows_and_keeps_provenance(self) -> None:
        self._insert_candidate("candidate:other", "oxidane", "H20")
        self.connection.execute(
            "INSERT INTO unverified_candidate_alias VALUES (?, 0, ?)",
            ("candidate:other", "water?"),
        )
        self.connection.commit()
        tools = AgentTools(
            self.connection,
            self.wikipedia,
            "agent",
            "candidate:water",
            [SOURCE_KEY],
        )
        tools.selected = True
        tools.searched_keys.add(SOURCE_KEY)
        result = tools.insert(
            {
                "candidate_id": "candidate:water",
                "action": "duplicate",
                "duplicate_of_candidate_id": "candidate:other",
                "candidate": None,
                "reason": "The formula and shared source name identify the same molecule.",
            }
        )
        self.assertEqual("candidate:other", result["canonical_candidate_id"])
        self.assertIsNone(candidate_json(self.connection, "candidate:water"))
        mention = self.connection.execute(
            "SELECT canonical_candidate_id FROM wikipedia_candidate_mention "
            "WHERE original_candidate_id = 'candidate:water'"
        ).fetchone()
        self.assertEqual("candidate:other", mention[0])


if __name__ == "__main__":
    unittest.main()
