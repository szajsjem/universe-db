from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from scripts.build_db import build
from scripts.download_wikipedia_chemistry import render_archive
from scripts.parse_wikipedia_archive import (
    chat_completions_url,
    chat_request_payload,
    extract_page_with_retries,
    insert_candidate,
    is_local_base_url,
    load_archive,
    load_zim_archive,
    normalize_result,
    verification_request_payload,
)


def candidate(kind: str, name: str, proposed_id: str) -> dict:
    return {
        "candidate_kind": kind,
        "name": name,
        "proposed_id": proposed_id,
        "existing_id": None,
        "formula": None,
        "electric_charge": None,
        "atomic_number": None,
        "proton_count": None,
        "neutron_count": None,
        "isomer_index": None,
        "observed": None,
        "confidence": "medium",
        "evidence_text": f"The page identifies {name}.",
        "aliases": [],
        "composition": [],
        "facts": [],
        "relations": [],
    }


class WikipediaImportTest(unittest.TestCase):
    def test_zim_loader_selects_canonical_html_pages_sequentially(self) -> None:
        class Item:
            def __init__(self, mimetype: str, content: bytes) -> None:
                self.mimetype = mimetype
                self.content = memoryview(content)

        class Entry:
            def __init__(
                self, title: str, path: str, item: Item, redirect: bool = False
            ) -> None:
                self.title = title
                self.path = path
                self._item = item
                self.is_redirect = redirect

            def get_item(self) -> Item:
                return self._item

        html = (
            b'<html><head><link rel="canonical" '
            b'href="https://en.wikipedia.org/wiki/Iron"></head></html>'
        )
        entries = [
            Entry("Iron", "Iron", Item("text/html", html)),
            Entry("Redirect", "Fe", Item("text/html", b""), True),
            Entry("Style", "_res/style.css", Item("text/css", b"body{}")),
        ]

        class Archive:
            all_entry_count = len(entries)
            article_count = 2

            def __init__(self, _path: Path) -> None:
                pass

            def check(self) -> bool:
                return True

            def get_metadata(self, key: str) -> bytes:
                self.assert_key(key)
                return b"2026-07-16"

            @staticmethod
            def assert_key(key: str) -> None:
                if key != "Date":
                    raise KeyError(key)

            def _get_entry_by_id(self, entry_id: int) -> Entry:
                return entries[entry_id]

        package = types.ModuleType("libzim")
        reader = types.ModuleType("libzim.reader")
        reader.Archive = Archive
        with patch.dict(
            sys.modules, {"libzim": package, "libzim.reader": reader}
        ):
            manifest, pages = load_zim_archive(Path("fixture.zim"))

        self.assertEqual("openzim-wikipedia-chemistry", manifest["archive_format"])
        self.assertEqual(1, manifest["page_count"])
        self.assertEqual("Iron", pages[0]["title"])
        self.assertEqual("html", pages[0]["_input_format"])
        self.assertEqual(0, pages[0]["_sequence_index"])

    def test_snapshot_archive_is_deterministic_and_revision_pinned(self) -> None:
        page = {
            "canonical_url": "https://en.wikipedia.org/wiki/Iron",
            "content_model": "wikitext",
            "discovered_in": ["Category:Chemical elements"],
            "page_id": 14533,
            "parent_revision_id": 100,
            "revision_id": 101,
            "revision_sha1": "source-sha1",
            "revision_timestamp": "2026-07-29T00:00:00Z",
            "revision_url": "https://en.wikipedia.org/w/index.php?oldid=101",
            "roots": ["Category:Chemical elements"],
            "title": "Iron",
            "wikitext": "{{Infobox element|name=Iron|symbol=Fe}}",
        }
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.zip"
            second = Path(directory) / "second.zip"
            for destination in (first, second):
                render_archive(
                    destination,
                    [page],
                    roots=("Category:Chemical elements",),
                    max_depth=0,
                    per_root=1,
                    max_pages=1,
                    retrieved_at="2026-07-29T00:00:00+00:00",
                )
            self.assertEqual(first.read_bytes(), second.read_bytes())
            manifest, pages = load_archive(first)
        self.assertEqual(1, manifest["page_count"])
        self.assertEqual(101, pages[0]["revision_id"])
        self.assertEqual(page["wikitext"], pages[0]["wikitext"])

    def test_structured_response_requires_explicit_candidates(self) -> None:
        result = {
            "page_relevance": "relevant",
            "notes": None,
            "entities": [candidate("molecule", "water", "chem:water")],
        }
        payload = {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": json.dumps(result)}
                    ],
                }
            ],
        }
        self.assertEqual("water", normalize_result(payload)["entities"][0]["name"])

    def test_lm_studio_chat_payload_and_response(self) -> None:
        page = {
            "_source_entry_key": "page:14533:revision:101",
            "_source_path": "pages/14533.json",
            "_source_url": "https://en.wikipedia.org/w/index.php?oldid=101",
            "_input_format": "wikitext",
            "page_id": 14533,
            "revision_id": 101,
            "revision_timestamp": "2026-07-29T00:00:00Z",
            "revision_url": "https://en.wikipedia.org/w/index.php?oldid=101",
            "title": "Iron",
        }
        request = chat_request_payload(
            "qwen/qwen3.6-27b",
            page,
            "{{Infobox element|name=Iron|symbol=Fe}}",
            1000,
        )
        self.assertEqual("json_schema", request["response_format"]["type"])
        self.assertEqual(
            "wikipedia_scientific_candidates",
            request["response_format"]["json_schema"]["name"],
        )
        self.assertEqual(1000, request["max_tokens"])
        self.assertEqual(
            "http://localhost:12355/v1/chat/completions",
            chat_completions_url("http://localhost:12355/v1/"),
        )
        self.assertTrue(is_local_base_url("http://localhost:12355/v1"))
        self.assertTrue(is_local_base_url("http://[::1]:12355/v1"))
        self.assertFalse(is_local_base_url("http://localhost.example/v1"))

        result = {
            "page_relevance": "relevant",
            "notes": None,
            "entities": [candidate("element", "iron", "element:iron")],
        }
        payload = {
            "id": "chatcmpl-test",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(result),
                    },
                }
            ],
        }
        self.assertEqual("iron", normalize_result(payload)["entities"][0]["name"])

    def test_verification_payload_includes_source_and_proposal(self) -> None:
        page = {
            "_source_entry_key": "page:14533:revision:101",
            "_source_path": "pages/14533.json",
            "_source_url": "https://en.wikipedia.org/w/index.php?oldid=101",
            "_input_format": "wikitext",
            "page_id": 14533,
            "revision_id": 101,
            "revision_timestamp": "2026-07-29T00:00:00Z",
            "revision_url": "https://en.wikipedia.org/w/index.php?oldid=101",
            "title": "Iron",
        }
        proposal = {
            "page_relevance": "relevant",
            "notes": None,
            "entities": [candidate("element", "iron", "element:iron")],
        }
        request = verification_request_payload(
            "qwen/qwen3.5-9b",
            page,
            "{{Infobox element|name=Iron|symbol=Fe}}",
            proposal,
            1000,
        )
        user_input = json.loads(request["messages"][1]["content"])
        self.assertEqual(proposal, user_input["proposed_extraction"])
        self.assertIn("Infobox element", user_input["source_document"])
        self.assertEqual(
            "verified_wikipedia_scientific_candidates",
            request["response_format"]["json_schema"]["name"],
        )

    def test_page_retry_restarts_extraction_and_verification(self) -> None:
        page = {
            "_source_entry_key": "page:14533:revision:101",
            "_source_path": "pages/14533.json",
            "_source_url": "https://en.wikipedia.org/w/index.php?oldid=101",
            "_input_format": "wikitext",
            "page_id": 14533,
            "revision_id": 101,
            "revision_timestamp": "2026-07-29T00:00:00Z",
            "revision_url": "https://en.wikipedia.org/w/index.php?oldid=101",
            "title": "Iron",
        }
        result = {
            "page_relevance": "relevant",
            "notes": None,
            "entities": [candidate("element", "iron", "element:iron")],
        }
        valid_payload = {
            "id": "chatcmpl-valid",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": json.dumps(result)},
                }
            ],
        }
        malformed_payload = {
            "id": "chatcmpl-broken",
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {"content": '{"page_relevance":'},
                }
            ],
        }
        with (
            patch(
                "scripts.parse_wikipedia_archive.call_model",
                side_effect=[malformed_payload, valid_payload, valid_payload],
            ) as model_call,
            patch("scripts.parse_wikipedia_archive.time.sleep") as sleep,
        ):
            payload, verified = extract_page_with_retries(
                "http://localhost:12355/v1",
                None,
                "qwen/qwen3.5-9b",
                page,
                "{{Infobox element|name=Iron|symbol=Fe}}",
                verify=True,
                page_retries=1,
                max_output_tokens=1000,
                retries=0,
                timeout=30,
            )
        self.assertEqual(valid_payload, payload)
        self.assertEqual("iron", verified["entities"][0]["name"])
        self.assertEqual(3, model_call.call_count)
        self.assertNotIn("proposed_result", model_call.call_args_list[1].kwargs)
        self.assertEqual(
            result,
            model_call.call_args_list[2].kwargs["proposed_result"],
        )
        sleep.assert_called_once_with(1)

    def test_stages_new_nuclide_molecule_and_reaction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.db"
            build(database)
            nuclide = candidate(
                "nuclide", "iron-99", "candidate:nuclide:iron-99"
            )
            nuclide.update(
                {
                    "proton_count": 26,
                    "neutron_count": 73,
                    "isomer_index": 0,
                    "observed": False,
                }
            )
            nuclide["facts"] = [
                {
                    "field_key": "half_life",
                    "value_decimal": "0.0015",
                    "value_text": None,
                    "unit": "s",
                    "uncertainty_decimal": None,
                    "conditions": [],
                    "evidence_text": "The page reports 1.5 ms.",
                }
            ]

            molecule = candidate(
                "molecule", "test oxide", "candidate:molecule:test_oxide"
            )
            molecule["formula"] = "FeO"
            molecule["composition"] = [
                {
                    "component_kind": "element",
                    "component_name": "iron",
                    "component_proposed_id": "element:iron",
                    "atom_count": 1,
                    "evidence_text": "Formula FeO.",
                },
                {
                    "component_kind": "element",
                    "component_name": "oxygen",
                    "component_proposed_id": "element:oxygen",
                    "atom_count": 1,
                    "evidence_text": "Formula FeO.",
                },
            ]

            reaction = candidate(
                "reaction", "test oxidation", "candidate:reaction:test_oxidation"
            )
            reaction["relations"] = [
                {
                    "relation_kind": "participant",
                    "object_name": "iron",
                    "object_proposed_id": "element:iron",
                    "role": "reactant",
                    "coefficient_decimal": "1",
                    "phase": "solid",
                    "details": None,
                    "evidence_text": "Iron is a reactant.",
                }
            ]

            with closing(sqlite3.connect(database)) as connection:
                with connection:
                    connection.execute(
                        """
                        INSERT INTO wikipedia_parse_run(
                            run_id, started_at, model, archive_name,
                            archive_format, archive_sha256, archive_page_count,
                            license_spdx_id, status
                        ) VALUES (
                            'wiki:test', '2026-07-29T00:00:00+00:00',
                            'test-model', 'test.zip',
                            'universe-db-wikipedia-category-snapshot-v1',
                            ?, 1, 'CC-BY-SA-4.0', 'running'
                        )
                        """,
                        ("0" * 64,),
                    )
                    connection.execute(
                        """
                        INSERT INTO wikipedia_page_parse(
                            page_parse_id, run_id, sequence_index,
                            source_entry_key, source_path, input_format,
                            page_id, revision_id, title, source_url,
                            source_timestamp, content_sha256, content_chars,
                            submitted_chars, status, created_at
                        ) VALUES (
                            'page:test', 'wiki:test', 0, 'page:1:revision:2',
                            'pages/test.json', 'wikitext', 1, 2, 'Test',
                            'https://example.test/?oldid=2',
                            '2026-07-29T00:00:00Z', ?, 10, 10, 'pending',
                            '2026-07-29T00:00:00+00:00'
                        )
                        """,
                        ("1" * 64,),
                    )
                    for index, value in enumerate((nuclide, molecule, reaction)):
                        insert_candidate(connection, "page:test", index, value)
                    kinds = connection.execute(
                        """
                        SELECT candidate_kind, existing_entity_id,
                               existing_reaction_id
                        FROM unverified_entity_candidate
                        ORDER BY candidate_index
                        """
                    ).fetchall()
                    facts = connection.execute(
                        "SELECT value_numerator, value_denominator "
                        "FROM unverified_candidate_fact"
                    ).fetchall()
                    components = connection.execute(
                        "SELECT count(*) FROM unverified_candidate_composition"
                    ).fetchone()[0]
                    relations = connection.execute(
                        "SELECT count(*) FROM unverified_candidate_relation"
                    ).fetchone()[0]
        self.assertEqual(
            [("nuclide", None, None), ("molecule", None, None), ("reaction", None, None)],
            kinds,
        )
        self.assertEqual([(3, 2000)], facts)
        self.assertEqual(2, components)
        self.assertEqual(1, relations)


if __name__ == "__main__":
    unittest.main()
