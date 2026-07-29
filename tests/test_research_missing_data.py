from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from scripts.build_db import build
from scripts.research_missing_data import (
    FIELDS,
    Target,
    Task,
    insert_result,
    insert_task,
    normalize_result,
    plan_tasks,
)


ROOT = Path(__file__).resolve().parents[1]


def fake_payload() -> dict:
    result = {
        "status": "found",
        "notes": None,
        "facts": [
            {
                "value_decimal": "1811.000",
                "value_text": None,
                "unit": "K",
                "uncertainty_decimal": "1.5",
                "relation_kind": None,
                "related_entity": None,
                "method_notes": "At the reported pressure.",
                "conditions": [
                    {
                        "quantity_kind": "pressure",
                        "value_decimal": "101325",
                        "value_text": None,
                        "unit": "Pa",
                    }
                ],
                "sources": [],
            }
        ],
    }
    return {
        "id": "resp_test",
        "output": [
            {
                "type": "web_search_call",
                "action": {
                    "sources": [
                        {
                            "url": "https://example.test/source",
                            "title": "Example source",
                        }
                    ]
                },
            },
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": json.dumps(result)}
                ],
            },
        ],
    }


class ResearchMissingDataTest(unittest.TestCase):
    def test_planner_skips_existing_reviewed_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.db"
            build(database)
            with sqlite3.connect(database) as connection:
                tasks = plan_tasks(
                    connection,
                    {"nuclides"},
                    {"relative_atomic_mass", "nuclear_spin"},
                    include_existing=False,
                    refresh_staged=False,
                    limit_targets=1,
                )
            self.assertEqual(["nuclear_spin"], [task.field.key for task in tasks])

    def test_normalize_uses_web_search_sources_as_fallback(self) -> None:
        result, sources = normalize_result(fake_payload())
        self.assertEqual("found", result["status"])
        self.assertEqual("https://example.test/source", sources[0]["url"])
        self.assertEqual(sources, result["facts"][0]["sources"])

    def test_inserts_exact_unverified_fact_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.db"
            build(database)
            target = Target(
                "element",
                "element:iron",
                "iron (Fe)",
                "element:iron",
            )
            field = next(
                field
                for field in FIELDS
                if field.scope == "elements" and field.key == "melting_point"
            )
            task = Task(target, field, "Find melting temperature of iron.")
            payload = fake_payload()
            result, _ = normalize_result(payload)
            with sqlite3.connect(database) as connection:
                connection.execute(
                    """
                    INSERT INTO research_run(
                        run_id, started_at, model, base_database_sha256,
                        requested_scopes, status
                    ) VALUES (
                        'run:test', '2026-07-29T00:00:00+00:00', 'test-model',
                        ?, 'elements', 'running'
                    )
                    """,
                    ("0" * 64,),
                )
                insert_task(connection, "run:test", "task:test", task)
                insert_result(connection, "task:test", task, payload, result)
                fact = connection.execute(
                    """
                    SELECT value_numerator, value_denominator,
                           uncertainty_numerator, uncertainty_denominator
                    FROM unverified_fact
                    """
                ).fetchone()
                condition = connection.execute(
                    """
                    SELECT value_numerator, value_denominator
                    FROM unverified_fact_condition
                    """
                ).fetchone()
                source = connection.execute(
                    "SELECT url FROM unverified_fact_source"
                ).fetchone()
            self.assertEqual((1811, 1, 3, 2), fact)
            self.assertEqual((101325, 1), condition)
            self.assertEqual(("https://example.test/source",), source)


if __name__ == "__main__":
    unittest.main()
