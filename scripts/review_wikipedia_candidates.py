#!/usr/bin/env python3
"""Agentically review merged Wikipedia atom and molecule candidates.

The model is given three bounded tools: read-only SQL, local Wikipedia snapshot
search, and one transactional staging write.  Output remains in the unverified
database; this workflow does not promote Wikipedia/model claims to reviewed
tables.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid

try:
    from scripts.parse_wikipedia_archive import (
        ENTITY_SCHEMA,
        MAX_SQLITE_INTEGER,
        load_archive,
        load_zim_archive,
        normalize_result,
    )
except ModuleNotFoundError:  # Direct `python scripts/...py` execution.
    from parse_wikipedia_archive import (  # type: ignore[no-redef]
        ENTITY_SCHEMA,
        MAX_SQLITE_INTEGER,
        load_archive,
        load_zim_archive,
        normalize_result,
    )


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "universe-unverified.db"
DEFAULT_OUTPUT = ROOT / ".build" / "wikipedia-agent-reviewed.db"
DEFAULT_ARCHIVE = (
    ROOT / "sources" / "wikipedia-chemistry-category-snapshot-2026-07-29.zip"
)
DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"
DEFAULT_MODEL = "qwen3.6-35b-a3b-mtp"
ALLOWED_TARGET_KINDS = {"atom", "molecule"}
ALLOWED_REWRITE_KINDS = {"atom", "molecule", "ion", "formula_unit", "complex"}
TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


SYSTEM_INSTRUCTIONS = """You are the conservative review agent for an
unverified chemistry staging database. Review exactly one candidate. You have
three tools: select_db reads the database, search_wikipedia searches the local
revision-pinned Wikipedia scrape, and insert_db records your final decision.

Required workflow:
1. Call select_db to inspect the candidate, its aliases/composition/facts, its
   source-page metadata and plausible duplicates. Never guess database state.
2. Call search_wikipedia for at least one source_entry_key attached to this
   candidate. Search again when excerpts are insufficient. Use global search
   only to investigate duplicates.
3. Check reviewed entity mappings and staging duplicates with select_db.
4. Call insert_db exactly once. Use keep when the row is already faithful,
   rewrite with a complete replacement candidate when source-supported cleanup
   is needed, duplicate only when identity is unambiguous, or reject when the
   source does not support the candidate.

Wikipedia and model output remain unverified. Do not promote into entity,
chemical_species, molecule, observation, or other reviewed tables. Never add a
claim from general knowledge. Every evidence_text in a rewrite must be a short
verbatim excerpt from one of the candidate's attached source pages. Formula
equality alone never proves molecular identity because isomers exist. Prefer
abstention over an unsafe merge. Finish by calling insert_db, not by narrating.

Useful tables are unverified_entity_candidate, unverified_candidate_alias,
unverified_candidate_composition, unverified_candidate_fact,
unverified_candidate_fact_condition, unverified_candidate_relation,
wikipedia_page_parse, wikipedia_candidate_mention, entity, chemical_species,
element, and molecule. Join child staging tables on candidate_id. Search likely
duplicates by normalized-looking name, aliases, formula, atomic number,
proposed_id, and existing_entity_id, but apply the conservative identity rules
above. Use ? placeholders and put their scalar values in parameters.
"""


INSERT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "candidate_id": {"type": "string"},
        "action": {
            "type": "string",
            "enum": ["keep", "rewrite", "duplicate", "reject"],
        },
        "duplicate_of_candidate_id": {"type": ["string", "null"]},
        "candidate": {"anyOf": [ENTITY_SCHEMA, {"type": "null"}]},
        "reason": {"type": "string"},
    },
    "required": [
        "candidate_id",
        "action",
        "duplicate_of_candidate_id",
        "candidate",
        "reason",
    ],
}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "select_db",
            "description": (
                "Run one read-only parameterized SELECT or WITH query against "
                "the staging and reviewed database. Results are capped."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "sql": {"type": "string"},
                    "parameters": {
                        "type": "array",
                        "items": {"type": ["string", "integer", "number", "null"]},
                    },
                },
                "required": ["sql", "parameters"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_wikipedia",
            "description": (
                "Search excerpts in the local revision-pinned Wikipedia scrape. "
                "Pass an attached source_entry_key for source verification; omit "
                "it only for global duplicate discovery."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "query": {"type": "string"},
                    "source_entry_key": {"type": ["string", "null"]},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 8},
                },
                "required": ["query", "source_entry_key", "limit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "insert_db",
            "description": (
                "Make the single final transactional staging decision for the "
                "current candidate. This never writes reviewed scientific tables."
            ),
            "parameters": INSERT_SCHEMA,
        },
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(value.split())


def identity_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", value).split())


def exact_ratio(value: str | None) -> tuple[int | None, int | None]:
    if value is None:
        return None, None
    try:
        ratio = Fraction(Decimal(value))
    except (InvalidOperation, ValueError, OverflowError) as error:
        raise ValueError(f"invalid exact decimal {value!r}") from error
    if abs(ratio.numerator) > MAX_SQLITE_INTEGER or ratio.denominator > MAX_SQLITE_INTEGER:
        raise ValueError(f"exact decimal is outside SQLite integer range: {value!r}")
    return ratio.numerator, ratio.denominator


def is_local_base_url(base_url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(base_url)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }


def chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return normalized + "/chat/completions"


def snapshot_database(source: Path, destination: Path) -> None:
    source = source.resolve()
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="candidate-agent-", dir=destination.parent) as tmp:
        staged = Path(tmp) / destination.name
        source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
        target_connection = sqlite3.connect(staged)
        try:
            source_connection.backup(target_connection)
        finally:
            target_connection.close()
            source_connection.close()
        os.replace(staged, destination)


def ensure_agent_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS wikipedia_candidate_agent_run (
            agent_run_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            model TEXT NOT NULL,
            base_url TEXT NOT NULL,
            archive_name TEXT NOT NULL,
            archive_sha256 TEXT NOT NULL CHECK(length(archive_sha256) = 64),
            target_kinds_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed')),
            target_count INTEGER NOT NULL CHECK(target_count >= 0),
            completed_count INTEGER NOT NULL DEFAULT 0 CHECK(completed_count >= 0),
            error_count INTEGER NOT NULL DEFAULT 0 CHECK(error_count >= 0)
        ) STRICT;

        CREATE TABLE IF NOT EXISTS wikipedia_candidate_agent_review (
            review_id TEXT PRIMARY KEY,
            agent_run_id TEXT NOT NULL
                REFERENCES wikipedia_candidate_agent_run(agent_run_id),
            candidate_id TEXT NOT NULL,
            canonical_candidate_id TEXT,
            action TEXT NOT NULL CHECK(
                action IN ('keep', 'rewrite', 'duplicate', 'reject', 'error')
            ),
            reason TEXT NOT NULL,
            source_entry_keys_json TEXT NOT NULL,
            before_json TEXT,
            after_json TEXT,
            tool_trace_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        ) STRICT;

        CREATE INDEX IF NOT EXISTS idx_wikipedia_candidate_agent_review_candidate
        ON wikipedia_candidate_agent_review(candidate_id, action);
        """
    )


class WikipediaIndex:
    def __init__(self, archive: Path) -> None:
        if archive.suffix.casefold() == ".zim":
            self.manifest, pages = load_zim_archive(archive)
        else:
            self.manifest, pages = load_archive(archive)
        self.pages = {page["_source_entry_key"]: page for page in pages}
        self._documents = {
            key: str(page.get("wikitext") or "") for key, page in self.pages.items()
        }

    def document(self, key: str) -> str | None:
        return self._documents.get(key)

    def search(self, query: str, source_entry_key: str | None, limit: int) -> list[dict]:
        terms = [term.casefold() for term in TOKEN_RE.findall(query) if len(term) > 1]
        if not terms:
            raise ValueError("Wikipedia search query has no searchable terms")
        if source_entry_key is not None:
            if source_entry_key not in self.pages:
                raise ValueError(f"source entry is absent from archive: {source_entry_key}")
            candidates = [(source_entry_key, self.pages[source_entry_key])]
        else:
            candidates = list(self.pages.items())
        ranked: list[tuple[int, str, dict, int]] = []
        for key, page in candidates:
            document = self._documents[key]
            folded = document.casefold()
            title = str(page.get("title") or "").casefold()
            offsets = [folded.find(term) for term in terms]
            found = [offset for offset in offsets if offset >= 0]
            score = sum(min(folded.count(term), 8) for term in terms)
            score += 10 * sum(term in title for term in terms)
            if not found and source_entry_key is None:
                continue
            offset = min(found) if found else 0
            ranked.append((score, key, page, offset))
        ranked.sort(key=lambda item: (-item[0], str(item[2].get("title")), item[1]))
        results = []
        for score, key, page, offset in ranked[:limit]:
            document = self._documents[key]
            start = max(0, offset - 1200)
            end = min(len(document), start + 5000)
            results.append(
                {
                    "source_entry_key": key,
                    "title": page.get("title"),
                    "revision_id": page.get("revision_id"),
                    "source_url": page.get("_source_url") or page.get("revision_url"),
                    "score": score,
                    "excerpt_start": start,
                    "excerpt": document[start:end],
                }
            )
        return results


def candidate_source_keys(connection: sqlite3.Connection, candidate_id: str) -> list[str]:
    rows = connection.execute(
        """
        SELECT page.source_entry_key
        FROM unverified_entity_candidate AS candidate
        JOIN wikipedia_page_parse AS page USING(page_parse_id)
        WHERE candidate.candidate_id = ?
        UNION
        SELECT page.source_entry_key
        FROM wikipedia_candidate_mention AS mention
        JOIN wikipedia_page_parse AS page USING(page_parse_id)
        WHERE mention.canonical_candidate_id = ?
        ORDER BY 1
        """,
        (candidate_id, candidate_id),
    ).fetchall()
    return [row[0] for row in rows]


def candidate_json(connection: sqlite3.Connection, candidate_id: str) -> dict | None:
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        "SELECT * FROM unverified_entity_candidate WHERE candidate_id = ?",
        (candidate_id,),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    for table, key in (
        ("unverified_candidate_alias", "aliases"),
        ("unverified_candidate_composition", "composition"),
        ("unverified_candidate_fact", "facts"),
        ("unverified_candidate_relation", "relations"),
    ):
        rows = connection.execute(
            f"SELECT * FROM {table} WHERE candidate_id = ? ORDER BY 1, 2",
            (candidate_id,),
        ).fetchall()
        result[key] = [dict(child) for child in rows]
    for fact in result["facts"]:
        conditions = connection.execute(
            """
            SELECT * FROM unverified_candidate_fact_condition
            WHERE candidate_fact_id = ? ORDER BY condition_index
            """,
            (fact["candidate_fact_id"],),
        ).fetchall()
        fact["conditions"] = [dict(condition) for condition in conditions]
    return result


def select_db(connection: sqlite3.Connection, sql: str, parameters: list) -> dict:
    statement = sql.strip().rstrip(";").strip()
    if not re.match(r"^(SELECT|WITH)\b", statement, re.IGNORECASE):
        raise ValueError("select_db accepts only SELECT or WITH statements")
    if ";" in statement:
        raise ValueError("select_db accepts exactly one SQL statement")
    if len(statement) > 8000 or len(parameters) > 50:
        raise ValueError("select_db query is too large")
    readonly = sqlite3.connect(
        f"file:{Path(connection.execute('PRAGMA database_list').fetchone()[2]).as_posix()}?mode=ro",
        uri=True,
        timeout=30,
    )
    readonly.row_factory = sqlite3.Row
    readonly.set_progress_handler(lambda: 1, 1_000_000)
    try:
        cursor = readonly.execute(statement, parameters)
        columns = [item[0] for item in cursor.description or ()]
        rows = [dict(row) for row in cursor.fetchmany(101)]
    finally:
        readonly.close()
    truncated = len(rows) > 100
    return {"columns": columns, "rows": rows[:100], "truncated": truncated}


def all_evidence(candidate: dict) -> list[str]:
    evidence = [candidate.get("evidence_text")]
    for key in ("composition", "facts", "relations"):
        evidence.extend(item.get("evidence_text") for item in candidate.get(key, []))
    return [value for value in evidence if isinstance(value, str) and value.strip()]


def validate_evidence(candidate: dict, documents: list[str]) -> None:
    normalized_documents = [normalize_text(document) for document in documents]
    evidence = all_evidence(candidate)
    if not evidence:
        raise ValueError("rewrite has no evidence_text")
    for excerpt in evidence:
        normalized = normalize_text(excerpt)
        if len(normalized) < 8:
            raise ValueError(f"evidence excerpt is too short: {excerpt!r}")
        if not any(normalized in document for document in normalized_documents):
            raise ValueError(f"evidence is not verbatim in an attached source: {excerpt!r}")


def normalize_rewrite(candidate: dict) -> dict:
    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {"page_relevance": "relevant", "notes": None, "entities": [candidate]}
                    )
                }
            }
        ]
    }
    normalized = normalize_result(payload)["entities"][0]
    if normalized["candidate_kind"] not in ALLOWED_REWRITE_KINDS:
        raise ValueError(
            f"agent cannot rewrite target as {normalized['candidate_kind']!r}"
        )
    return normalized


def replace_candidate(
    connection: sqlite3.Connection, candidate_id: str, candidate: dict
) -> None:
    existing_id = candidate["existing_id"]
    if existing_id is not None:
        if connection.execute(
            "SELECT 1 FROM entity WHERE entity_id = ?", (existing_id,)
        ).fetchone() is None:
            raise ValueError(f"unknown reviewed existing_id {existing_id!r}")
    connection.execute(
        """
        UPDATE unverified_entity_candidate
        SET candidate_kind = ?, name = ?, proposed_id = ?,
            existing_entity_id = ?, existing_reaction_id = NULL,
            formula = ?, electric_charge = ?, atomic_number = ?,
            proton_count = ?, neutron_count = ?, isomer_index = ?,
            observed = ?, confidence = ?, evidence_text = ?
        WHERE candidate_id = ?
        """,
        (
            candidate["candidate_kind"], candidate["name"], candidate["proposed_id"],
            existing_id, candidate["formula"], candidate["electric_charge"],
            candidate["atomic_number"], candidate["proton_count"],
            candidate["neutron_count"], candidate["isomer_index"],
            None if candidate["observed"] is None else int(candidate["observed"]),
            candidate["confidence"], candidate["evidence_text"], candidate_id,
        ),
    )
    for table in (
        "unverified_candidate_alias",
        "unverified_candidate_composition",
        "unverified_candidate_fact",
        "unverified_candidate_relation",
    ):
        connection.execute(f"DELETE FROM {table} WHERE candidate_id = ?", (candidate_id,))
    for index, value in enumerate(candidate["aliases"]):
        connection.execute(
            "INSERT INTO unverified_candidate_alias VALUES (?, ?, ?)",
            (candidate_id, index, value),
        )
    for index, item in enumerate(candidate["composition"]):
        connection.execute(
            """
            INSERT INTO unverified_candidate_composition(
                candidate_id, component_index, component_kind, component_name,
                component_proposed_id, atom_count, evidence_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate_id, index, item["component_kind"], item["component_name"],
                item["component_proposed_id"], item["atom_count"], item["evidence_text"],
            ),
        )
    for index, item in enumerate(candidate["facts"]):
        fact_id = str(uuid.uuid4())
        numerator, denominator = exact_ratio(item["value_decimal"])
        uncertainty_numerator, uncertainty_denominator = exact_ratio(
            item["uncertainty_decimal"]
        )
        connection.execute(
            """
            INSERT INTO unverified_candidate_fact(
                candidate_fact_id, candidate_id, fact_index, field_key,
                value_decimal_text, value_numerator, value_denominator,
                value_text, unit_text, uncertainty_decimal_text,
                uncertainty_numerator, uncertainty_denominator, evidence_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fact_id, candidate_id, index, item["field_key"], item["value_decimal"],
                numerator, denominator, item["value_text"], item["unit"],
                item["uncertainty_decimal"], uncertainty_numerator,
                uncertainty_denominator, item["evidence_text"],
            ),
        )
        for condition_index, condition in enumerate(item["conditions"]):
            value_numerator, value_denominator = exact_ratio(condition["value_decimal"])
            connection.execute(
                """
                INSERT INTO unverified_candidate_fact_condition(
                    candidate_fact_id, condition_index, quantity_kind,
                    value_decimal_text, value_numerator, value_denominator,
                    value_text, unit_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fact_id, condition_index, condition["quantity_kind"],
                    condition["value_decimal"], value_numerator, value_denominator,
                    condition["value_text"], condition["unit"],
                ),
            )
    for index, item in enumerate(candidate["relations"]):
        numerator, denominator = exact_ratio(item["coefficient_decimal"])
        connection.execute(
            """
            INSERT INTO unverified_candidate_relation(
                relation_id, candidate_id, relation_index, relation_kind,
                object_name, object_proposed_id, role, coefficient_decimal_text,
                coefficient_numerator, coefficient_denominator, phase_text,
                details_text, evidence_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()), candidate_id, index, item["relation_kind"],
                item["object_name"], item["object_proposed_id"], item["role"],
                item["coefficient_decimal"], numerator, denominator, item["phase"],
                item["details"], item["evidence_text"],
            ),
        )


def candidate_names(connection: sqlite3.Connection, candidate_id: str) -> set[str]:
    row = connection.execute(
        "SELECT name FROM unverified_entity_candidate WHERE candidate_id = ?",
        (candidate_id,),
    ).fetchone()
    if row is None:
        return set()
    values = [row[0]] + [
        item[0]
        for item in connection.execute(
            "SELECT value FROM unverified_candidate_alias WHERE candidate_id = ?",
            (candidate_id,),
        )
    ]
    return {identity_text(value) for value in values if identity_text(value)}


def safe_duplicate(
    connection: sqlite3.Connection, source_id: str, target_id: str
) -> tuple[bool, str]:
    connection.row_factory = sqlite3.Row
    source = connection.execute(
        "SELECT * FROM unverified_entity_candidate WHERE candidate_id = ?", (source_id,)
    ).fetchone()
    target = connection.execute(
        "SELECT * FROM unverified_entity_candidate WHERE candidate_id = ?", (target_id,)
    ).fetchone()
    if source is None or target is None or source_id == target_id:
        return False, "both distinct candidates must exist"
    if source["candidate_kind"] != target["candidate_kind"]:
        return False, "candidate kinds differ"
    if (
        source["existing_entity_id"] is not None
        and source["existing_entity_id"] == target["existing_entity_id"]
    ):
        return True, "same reviewed entity mapping"
    if source["proposed_id"] and source["proposed_id"] == target["proposed_id"]:
        return True, "same proposed identity"
    if source["candidate_kind"] == "atom":
        signature = ("atomic_number", "proton_count", "neutron_count", "isomer_index")
        if source["atomic_number"] is not None and all(
            source[key] == target[key] for key in signature
        ):
            return True, "same complete atomic signature"
        return False, "atoms lack a matching identity signature"
    source_formula = identity_text(source["formula"])
    target_formula = identity_text(target["formula"])
    shared_names = candidate_names(connection, source_id) & candidate_names(connection, target_id)
    if source_formula and source_formula == target_formula and shared_names:
        return True, "same formula and shared normalized name/alias"
    return False, "molecules require both formula and name/alias agreement"


def next_index(
    connection: sqlite3.Connection, table: str, column: str, candidate_id: str
) -> int:
    return connection.execute(
        f"SELECT COALESCE(MAX({column}) + 1, 0) FROM {table} WHERE candidate_id = ?",
        (candidate_id,),
    ).fetchone()[0]


def merge_duplicate(
    connection: sqlite3.Connection, source_id: str, target_id: str
) -> None:
    source = connection.execute(
        "SELECT page_parse_id, candidate_kind, name, formula, electric_charge, evidence_text "
        "FROM unverified_entity_candidate WHERE candidate_id = ?",
        (source_id,),
    ).fetchone()
    if source is None:
        raise ValueError(f"duplicate source no longer exists: {source_id}")
    existing_aliases = {identity_text(row[0]) for row in connection.execute(
        "SELECT value FROM unverified_candidate_alias WHERE candidate_id = ?", (target_id,)
    )}
    if identity_text(source[2]) not in existing_aliases:
        connection.execute(
            "INSERT INTO unverified_candidate_alias VALUES (?, ?, ?)",
            (
                target_id,
                next_index(connection, "unverified_candidate_alias", "alias_index", target_id),
                source[2],
            ),
        )
    for table, index_column in (
        ("unverified_candidate_alias", "alias_index"),
        ("unverified_candidate_composition", "component_index"),
        ("unverified_candidate_fact", "fact_index"),
        ("unverified_candidate_relation", "relation_index"),
    ):
        next_value = next_index(connection, table, index_column, target_id)
        rows = connection.execute(
            f"SELECT {index_column} FROM {table} WHERE candidate_id = ? ORDER BY {index_column}",
            (source_id,),
        ).fetchall()
        for (old_value,) in rows:
            connection.execute(
                f"UPDATE {table} SET candidate_id = ?, {index_column} = ? "
                f"WHERE candidate_id = ? AND {index_column} = ?",
                (target_id, next_value, source_id, old_value),
            )
            next_value += 1
    if connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='table' "
        "AND name='unverified_candidate_derived_fact'"
    ).fetchone():
        connection.execute(
            "UPDATE OR IGNORE unverified_candidate_derived_fact SET candidate_id = ? "
            "WHERE candidate_id = ?",
            (target_id, source_id),
        )
        connection.execute(
            "DELETE FROM unverified_candidate_derived_fact WHERE candidate_id = ?",
            (source_id,),
        )
    connection.execute(
        "UPDATE wikipedia_candidate_mention SET canonical_candidate_id = ? "
        "WHERE canonical_candidate_id = ?",
        (target_id, source_id),
    )
    # Existing deterministic cleanup already creates a mention for most merged
    # candidates. The current source still needs one when it had not been merged.
    cleanup_run_id = str(uuid.uuid4())
    connection.execute(
        """
        INSERT INTO wikipedia_candidate_cleanup_run(
            cleanup_run_id, created_at, normal_temperature_k,
            normal_pressure_pa, merged_candidates, corrected_kinds,
            corrected_mappings, inferred_phases
        ) VALUES (?, ?, '293.15', '101325', 1, 0, 0, 0)
        """,
        (cleanup_run_id, utc_now()),
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO wikipedia_candidate_mention(
            original_candidate_id, canonical_candidate_id, page_parse_id,
            original_kind, original_name, original_formula,
            original_electric_charge, original_evidence_text,
            merge_reason, cleanup_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_id, target_id, source[0], source[1], source[2], source[3],
            source[4], source[5], "agent-reviewed duplicate", cleanup_run_id,
        ),
    )
    connection.execute(
        "DELETE FROM unverified_entity_candidate WHERE candidate_id = ?", (source_id,)
    )


def insert_review_row(
    connection: sqlite3.Connection,
    run_id: str,
    candidate_id: str,
    canonical_id: str | None,
    action: str,
    reason: str,
    source_keys: list[str],
    before: dict | None,
    after: dict | None,
    trace: list[dict],
) -> None:
    connection.execute(
        """
        INSERT INTO wikipedia_candidate_agent_review(
            review_id, agent_run_id, candidate_id, canonical_candidate_id,
            action, reason, source_entry_keys_json, before_json, after_json,
            tool_trace_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()), run_id, candidate_id, canonical_id, action, reason,
            json.dumps(source_keys, ensure_ascii=False),
            json.dumps(before, ensure_ascii=False, sort_keys=True) if before else None,
            json.dumps(after, ensure_ascii=False, sort_keys=True) if after else None,
            json.dumps(trace, ensure_ascii=False), utc_now(),
        ),
    )


class AgentTools:
    def __init__(
        self,
        connection: sqlite3.Connection,
        wikipedia: WikipediaIndex,
        run_id: str,
        candidate_id: str,
        source_keys: list[str],
    ) -> None:
        self.connection = connection
        self.wikipedia = wikipedia
        self.run_id = run_id
        self.candidate_id = candidate_id
        self.source_keys = source_keys
        self.selected = False
        self.searched_keys: set[str] = set()
        self.finished = False
        self.trace: list[dict] = []

    def call(self, name: str, arguments: dict) -> dict:
        if self.finished:
            raise ValueError("insert_db was already called")
        if name == "select_db":
            result = select_db(
                self.connection, arguments.get("sql", ""), arguments.get("parameters", [])
            )
            self.selected = True
        elif name == "search_wikipedia":
            key = arguments.get("source_entry_key")
            results = self.wikipedia.search(
                arguments.get("query", ""), key, int(arguments.get("limit", 3))
            )
            self.searched_keys.update(item["source_entry_key"] for item in results)
            result = {"results": results}
        elif name == "insert_db":
            result = self.insert(arguments)
            self.finished = True
        else:
            raise ValueError(f"unknown tool {name!r}")
        self.trace.append({"tool": name, "arguments": arguments, "result": result})
        return result

    def insert(self, arguments: dict) -> dict:
        if arguments.get("candidate_id") != self.candidate_id:
            raise ValueError("insert_db may modify only the current candidate")
        if not self.selected:
            raise ValueError("select_db must be called before insert_db")
        if not (self.searched_keys & set(self.source_keys)):
            raise ValueError("an attached source article must be searched before insert_db")
        action = arguments.get("action")
        if action not in {"keep", "rewrite", "duplicate", "reject"}:
            raise ValueError(f"invalid review action {action!r}")
        reason = str(arguments.get("reason") or "").strip()
        if len(reason) < 8:
            raise ValueError("insert_db reason is too short")
        before = candidate_json(self.connection, self.candidate_id)
        if before is None:
            raise ValueError("current candidate no longer exists")
        canonical_id = self.candidate_id
        rewritten = arguments.get("candidate")
        duplicate_id = arguments.get("duplicate_of_candidate_id")
        with self.connection:
            if action == "rewrite":
                if not isinstance(rewritten, dict) or duplicate_id is not None:
                    raise ValueError("rewrite requires candidate and no duplicate target")
                normalized = normalize_rewrite(rewritten)
                documents = [
                    self.wikipedia.document(key) or "" for key in self.source_keys
                ]
                validate_evidence(normalized, documents)
                replace_candidate(self.connection, self.candidate_id, normalized)
            elif action == "duplicate":
                if rewritten is not None or not isinstance(duplicate_id, str):
                    raise ValueError("duplicate requires only duplicate_of_candidate_id")
                safe, safety_reason = safe_duplicate(
                    self.connection, self.candidate_id, duplicate_id
                )
                if not safe:
                    raise ValueError(f"unsafe duplicate merge: {safety_reason}")
                merge_duplicate(self.connection, self.candidate_id, duplicate_id)
                canonical_id = duplicate_id
                reason = f"{reason}; guard: {safety_reason}"
            elif rewritten is not None or duplicate_id is not None:
                raise ValueError(f"{action} accepts neither candidate nor duplicate target")
            after = candidate_json(self.connection, canonical_id)
            insert_review_row(
                self.connection, self.run_id, self.candidate_id, canonical_id,
                action, reason, self.source_keys, before, after, self.trace,
            )
        return {"committed": True, "action": action, "canonical_candidate_id": canonical_id}


def assistant_tool_calls(message: dict) -> list[dict]:
    calls = message.get("tool_calls") or []
    if calls:
        return calls
    if message.get("function_call"):
        return [{"id": str(uuid.uuid4()), "type": "function", "function": message["function_call"]}]
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        try:
            fallback = json.loads(content)
        except json.JSONDecodeError:
            return []
        if isinstance(fallback, dict) and fallback.get("tool"):
            return [
                {
                    "id": str(uuid.uuid4()),
                    "type": "function",
                    "function": {
                        "name": fallback["tool"],
                        "arguments": json.dumps(fallback.get("arguments", {})),
                    },
                }
            ]
    return []


def call_model(
    base_url: str,
    api_key: str | None,
    model: str,
    messages: list[dict],
    max_tokens: int,
    retries: int,
    timeout: int,
    enable_thinking: bool = False,
) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
        # llama.cpp and Qwen chat templates honor this extension. Keeping
        # reasoning off makes bounded tool selection much faster; servers that
        # do not use the template kwarg generally ignore it.
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "universe-db-candidate-agent/1",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    for attempt in range(retries + 1):
        request = urllib.request.Request(
            chat_completions_url(base_url),
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read())
            choices = result.get("choices") or []
            if not choices or not isinstance(choices[0].get("message"), dict):
                raise ValueError("model response has no assistant message")
            return choices[0]["message"]
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            if attempt >= retries:
                raise RuntimeError(f"model request failed after {attempt + 1} attempts: {error}") from error
            time.sleep(min(2**attempt, 8))
    raise AssertionError("unreachable")


def run_candidate_agent(
    connection: sqlite3.Connection,
    wikipedia: WikipediaIndex,
    run_id: str,
    candidate_id: str,
    base_url: str,
    api_key: str | None,
    model: str,
    max_steps: int,
    max_tokens: int,
    retries: int,
    timeout: int,
    enable_thinking: bool = False,
) -> dict:
    source_keys = candidate_source_keys(connection, candidate_id)
    if not source_keys:
        raise ValueError("candidate has no attached Wikipedia source")
    summary = connection.execute(
        "SELECT candidate_kind, name, formula FROM unverified_entity_candidate "
        "WHERE candidate_id = ?",
        (candidate_id,),
    ).fetchone()
    tools = AgentTools(connection, wikipedia, run_id, candidate_id, source_keys)
    messages = [
        {"role": "system", "content": SYSTEM_INSTRUCTIONS},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "candidate_id": candidate_id,
                    "candidate_kind": summary[0],
                    "name": summary[1],
                    "formula": summary[2],
                    "attached_source_entry_keys": source_keys,
                },
                ensure_ascii=False,
            ),
        },
    ]
    for _step in range(max_steps):
        message = call_model(
            base_url, api_key, model, messages, max_tokens, retries, timeout,
            enable_thinking,
        )
        calls = assistant_tool_calls(message)
        if not calls:
            raise ValueError("agent stopped without a tool call")
        messages.append(message)
        for call in calls:
            function = call.get("function") or {}
            raw_arguments = function.get("arguments", "{}")
            arguments = (
                raw_arguments if isinstance(raw_arguments, dict) else json.loads(raw_arguments)
            )
            try:
                result = tools.call(function.get("name", ""), arguments)
            except Exception as error:
                result = {"error": str(error)}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id") or str(uuid.uuid4()),
                    "name": function.get("name", ""),
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
            if tools.finished:
                return result
    raise ValueError(f"agent exceeded {max_steps} tool-call rounds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", nargs="?", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--kinds", default="atom,molecule")
    parser.add_argument("--max-candidates", type=int)
    parser.add_argument("--start-after")
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument(
        "--enable-thinking",
        action="store_true",
        help="enable Qwen reasoning during tool selection (disabled by default)",
    )
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--accept-cost", action="store_true")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> set[str]:
    kinds = {value.strip() for value in args.kinds.split(",") if value.strip()}
    if not kinds or not kinds <= ALLOWED_TARGET_KINDS:
        raise SystemExit("--kinds must contain atom and/or molecule")
    if args.max_candidates is not None and args.max_candidates < 1:
        raise SystemExit("--max-candidates must be positive")
    if args.max_steps < 3 or args.max_output_tokens < 256 or args.retries < 0:
        raise SystemExit("invalid agent request limits")
    if args.in_place:
        args.output = args.database
    elif args.database.resolve() == args.output.resolve():
        raise SystemExit("same input/output requires --in-place")
    if not is_local_base_url(args.base_url) and not args.accept_cost:
        raise SystemExit("non-local --base-url requires --accept-cost")
    return kinds


def planned_candidates(
    connection: sqlite3.Connection,
    kinds: set[str],
    start_after: str | None,
    max_candidates: int | None,
) -> list[str]:
    placeholders = ",".join("?" for _ in kinds)
    parameters: list[object] = sorted(kinds)
    sql = (
        "SELECT candidate_id FROM unverified_entity_candidate "
        f"WHERE candidate_kind IN ({placeholders}) "
        "AND NOT EXISTS (SELECT 1 FROM wikipedia_candidate_agent_review AS review "
        "WHERE review.candidate_id = unverified_entity_candidate.candidate_id "
        "AND review.action <> 'error') "
    )
    if start_after:
        sql += "AND candidate_id > ? "
        parameters.append(start_after)
    sql += "ORDER BY candidate_id"
    if max_candidates is not None:
        sql += " LIMIT ?"
        parameters.append(max_candidates)
    return [row[0] for row in connection.execute(sql, parameters)]


def main() -> None:
    args = parse_args()
    kinds = validate_args(args)
    if not args.database.exists():
        raise SystemExit(f"database does not exist: {args.database}")
    if not args.archive.exists():
        raise SystemExit(f"Wikipedia archive does not exist: {args.archive}")

    # The cost-free path inspects the source database without creating tables.
    if not args.execute:
        with sqlite3.connect(args.database) as connection:
            placeholders = ",".join("?" for _ in kinds)
            count_sql = (
                "SELECT count(*) FROM unverified_entity_candidate "
                f"WHERE candidate_kind IN ({placeholders})"
            )
            count_parameters: list[object] = sorted(kinds)
            if args.start_after:
                count_sql += " AND candidate_id > ?"
                count_parameters.append(args.start_after)
            count = connection.execute(count_sql, count_parameters).fetchone()[0]
            if args.max_candidates is not None:
                count = min(count, args.max_candidates)
        print(f"planned candidates: {count}")
        print(f"kinds: {','.join(sorted(kinds))}")
        print(f"model: {args.model}")
        print(f"base URL: {args.base_url}")
        print("dry run only; add --execute to copy/review/write the staging database")
        return

    if not args.in_place and not args.output.exists():
        snapshot_database(args.database, args.output)
    wikipedia = WikipediaIndex(args.archive)
    api_key = os.environ.get(args.api_key_env)
    run_id = str(uuid.uuid4())
    with sqlite3.connect(args.output, timeout=60) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.row_factory = sqlite3.Row
        ensure_agent_schema(connection)
        targets = planned_candidates(
            connection, kinds, args.start_after, args.max_candidates
        )
        connection.execute(
            """
            INSERT INTO wikipedia_candidate_agent_run(
                agent_run_id, started_at, model, base_url, archive_name,
                archive_sha256, target_kinds_json, status, target_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?)
            """,
            (
                run_id, utc_now(), args.model, args.base_url, args.archive.name,
                sha256(args.archive), json.dumps(sorted(kinds)), len(targets),
            ),
        )
        connection.commit()
        completed = 0
        errors = 0
        try:
            for index, candidate_id in enumerate(targets, 1):
                if candidate_json(connection, candidate_id) is None:
                    continue
                try:
                    result = run_candidate_agent(
                        connection, wikipedia, run_id, candidate_id, args.base_url,
                        api_key, args.model, args.max_steps, args.max_output_tokens,
                        args.retries, args.timeout, args.enable_thinking,
                    )
                    if not result.get("committed"):
                        raise ValueError(result.get("error") or "agent did not commit")
                    completed += 1
                    print(
                        f"[{index}/{len(targets)}] {candidate_id}: "
                        f"{result['action']} -> {result['canonical_candidate_id']}",
                        flush=True,
                    )
                except Exception as error:
                    errors += 1
                    with connection:
                        insert_review_row(
                            connection, run_id, candidate_id, candidate_id, "error",
                            str(error), candidate_source_keys(connection, candidate_id),
                            candidate_json(connection, candidate_id), None, [],
                        )
                    print(f"[{index}/{len(targets)}] {candidate_id}: ERROR {error}", flush=True)
                with connection:
                    connection.execute(
                        "UPDATE wikipedia_candidate_agent_run "
                        "SET completed_count = ?, error_count = ? WHERE agent_run_id = ?",
                        (completed, errors, run_id),
                    )
            with connection:
                connection.execute(
                    "UPDATE wikipedia_candidate_agent_run SET completed_at = ?, status = 'completed', "
                    "completed_count = ?, error_count = ? WHERE agent_run_id = ?",
                    (utc_now(), completed, errors, run_id),
                )
        except BaseException:
            with connection:
                connection.execute(
                    "UPDATE wikipedia_candidate_agent_run SET completed_at = ?, status = 'failed', "
                    "completed_count = ?, error_count = ? WHERE agent_run_id = ?",
                    (utc_now(), completed, errors, run_id),
                )
            raise
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        if integrity != "ok" or foreign_keys:
            raise RuntimeError(
                f"output validation failed: integrity={integrity}, foreign_keys={foreign_keys[:5]}"
            )
    print(f"reviewed {completed}/{len(targets)} candidates with {errors} errors")
    print(f"output: {args.output}")


if __name__ == "__main__":
    main()
