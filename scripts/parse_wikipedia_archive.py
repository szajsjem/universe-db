#!/usr/bin/env python3
"""Sequentially parse a Wikipedia chemistry snapshot into unverified candidates.

Each page is submitted in archive order as one independent structured-output
request. Candidate nuclides, molecules, reactions, compositions, facts, and
relations remain isolated from reviewed tables pending human source review.
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
import shutil
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "universe.db"
DEFAULT_OUTPUT = ROOT / ".build" / "wikipedia-unverified.db"
DEFAULT_MODEL = "gpt-5.4-nano"
API_URL = "https://api.openai.com/v1/responses"
ZIP_ARCHIVE_FORMAT = "universe-db-wikipedia-category-snapshot-v1"
ZIM_ARCHIVE_FORMAT = "openzim-wikipedia-chemistry"
MAX_SQLITE_INTEGER = 2**63 - 1


CONDITION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "quantity_kind": {"type": "string"},
        "value_decimal": {"type": ["string", "null"]},
        "value_text": {"type": ["string", "null"]},
        "unit": {"type": ["string", "null"]},
    },
    "required": ["quantity_kind", "value_decimal", "value_text", "unit"],
}

FACT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "field_key": {"type": "string"},
        "value_decimal": {"type": ["string", "null"]},
        "value_text": {"type": ["string", "null"]},
        "unit": {"type": ["string", "null"]},
        "uncertainty_decimal": {"type": ["string", "null"]},
        "conditions": {"type": "array", "items": CONDITION_SCHEMA},
        "evidence_text": {"type": "string"},
    },
    "required": [
        "field_key",
        "value_decimal",
        "value_text",
        "unit",
        "uncertainty_decimal",
        "conditions",
        "evidence_text",
    ],
}

COMPOSITION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "component_kind": {
            "type": "string",
            "enum": ["element", "nuclide", "species", "material", "other"],
        },
        "component_name": {"type": "string"},
        "component_proposed_id": {"type": ["string", "null"]},
        "atom_count": {"type": ["integer", "null"]},
        "evidence_text": {"type": "string"},
    },
    "required": [
        "component_kind",
        "component_name",
        "component_proposed_id",
        "atom_count",
        "evidence_text",
    ],
}

RELATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "relation_kind": {"type": "string"},
        "object_name": {"type": "string"},
        "object_proposed_id": {"type": ["string", "null"]},
        "role": {"type": ["string", "null"]},
        "coefficient_decimal": {"type": ["string", "null"]},
        "phase": {"type": ["string", "null"]},
        "details": {"type": ["string", "null"]},
        "evidence_text": {"type": "string"},
    },
    "required": [
        "relation_kind",
        "object_name",
        "object_proposed_id",
        "role",
        "coefficient_decimal",
        "phase",
        "details",
        "evidence_text",
    ],
}

ENTITY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "candidate_kind": {
            "type": "string",
            "enum": [
                "particle",
                "element",
                "nuclide",
                "atom",
                "molecule",
                "ion",
                "formula_unit",
                "complex",
                "polymer",
                "material",
                "mixture",
                "reaction",
            ],
        },
        "name": {"type": "string"},
        "proposed_id": {"type": ["string", "null"]},
        "existing_id": {"type": ["string", "null"]},
        "formula": {"type": ["string", "null"]},
        "electric_charge": {"type": ["integer", "null"]},
        "atomic_number": {"type": ["integer", "null"]},
        "proton_count": {"type": ["integer", "null"]},
        "neutron_count": {"type": ["integer", "null"]},
        "isomer_index": {"type": ["integer", "null"]},
        "observed": {"type": ["boolean", "null"]},
        "confidence": {
            "type": "string",
            "enum": ["low", "medium", "high"],
        },
        "evidence_text": {"type": "string"},
        "aliases": {"type": "array", "items": {"type": "string"}},
        "composition": {"type": "array", "items": COMPOSITION_SCHEMA},
        "facts": {"type": "array", "items": FACT_SCHEMA},
        "relations": {"type": "array", "items": RELATION_SCHEMA},
    },
    "required": [
        "candidate_kind",
        "name",
        "proposed_id",
        "existing_id",
        "formula",
        "electric_charge",
        "atomic_number",
        "proton_count",
        "neutron_count",
        "isomer_index",
        "observed",
        "confidence",
        "evidence_text",
        "aliases",
        "composition",
        "facts",
        "relations",
    ],
}

RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "page_relevance": {
            "type": "string",
            "enum": ["relevant", "no_data"],
        },
        "notes": {"type": ["string", "null"]},
        "entities": {"type": "array", "items": ENTITY_SCHEMA},
    },
    "required": ["page_relevance", "notes", "entities"],
}

SYSTEM_INSTRUCTIONS = """Extract structured scientific candidate data from one
English Wikipedia source document. Use only claims explicitly present in the
supplied wikitext or HTML. Do not browse, calculate, infer missing values, balance
unstated reactions, or invent canonical IDs. Preserve uncertainty, units,
pressure, temperature, phase, isotope state, sample form, and other conditions.

Create candidates for explicitly identified elements, nuclides/isomers,
particles, atoms, molecules, ions, formula units, complexes, polymers,
materials, mixtures, and chemical or nuclear reactions. A reaction is a
candidate with participant relations; use role reactant/product/catalyst/
solvent/incident/emitted when stated and retain rational coefficients as
decimal strings. Use facts for scalar or textual observations including phase
transitions, abundance, mass, spin/parity, half-life, decay branching,
binding/mass-excess energy, spectra, electronegativity, and cross sections.

Wikipedia is an unverified secondary source. evidence_text must be a short
page excerpt supporting that candidate, fact, composition, or relation. Return
no_data when the page contains nothing suitable for the database. Never label
these candidates reviewed or measured by the database project."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def exact_ratio(value: str | None) -> tuple[int | None, int | None]:
    if value is None:
        return None, None
    try:
        ratio = Fraction(Decimal(value))
    except (InvalidOperation, ValueError, OverflowError):
        return None, None
    if (
        abs(ratio.numerator) > MAX_SQLITE_INTEGER
        or ratio.denominator > MAX_SQLITE_INTEGER
    ):
        return None, None
    return ratio.numerator, ratio.denominator


def prepare_output(database: Path, output: Path) -> None:
    if database.resolve() == output.resolve():
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists():
        shutil.copy2(database, output)


def bind_overlay_to_base(
    connection: sqlite3.Connection,
    database: Path,
    output: Path,
    current_base_digest: str,
) -> str:
    row = connection.execute(
        "SELECT value FROM database_metadata WHERE key = 'unverified_base_sha256'"
    ).fetchone()
    if row is not None:
        if database.resolve() != output.resolve() and row[0] != current_base_digest:
            raise RuntimeError(
                "existing overlay belongs to another base database; remove it "
                "or choose another --output"
            )
        return row[0]
    connection.execute(
        """
        INSERT INTO database_metadata(key, value)
        VALUES ('unverified_base_sha256', ?)
        """,
        (current_base_digest,),
    )
    return current_base_digest


def ensure_schema(connection: sqlite3.Connection) -> None:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version < 5:
        raise RuntimeError(
            f"database schema is {version}; run `make build` to create schema 5"
        )
    connection.execute("SELECT 1 FROM wikipedia_parse_run LIMIT 1")


def load_archive(archive_path: Path) -> tuple[dict, list[dict]]:
    if archive_path.suffix.casefold() == ".zim":
        return load_zim_archive(archive_path)
    pages: list[dict] = []
    with zipfile.ZipFile(archive_path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("archive_format") != ZIP_ARCHIVE_FORMAT:
            raise ValueError("unsupported Wikipedia snapshot archive format")
        for sequence, entry in enumerate(manifest["pages"]):
            raw = archive.read(entry["filename"])
            if bytes_sha256(raw) != entry["content_sha256"]:
                raise ValueError(
                    f"{entry['filename']} does not match its manifest digest"
                )
            page = json.loads(raw)
            if (
                page["page_id"] != entry["page_id"]
                or page["revision_id"] != entry["revision_id"]
            ):
                raise ValueError(f"{entry['filename']} identity mismatch")
            page["_sequence_index"] = sequence
            page["_content_sha256"] = entry["content_sha256"]
            page["_source_entry_key"] = (
                f"page:{page['page_id']}:revision:{page['revision_id']}"
            )
            page["_source_path"] = entry["filename"]
            page["_source_url"] = page["revision_url"]
            page["_source_timestamp"] = page["revision_timestamp"]
            page["_input_format"] = "wikitext"
            pages.append(page)
    if len(pages) != manifest["page_count"]:
        raise ValueError("archive page count does not match manifest")
    return manifest, pages


def load_zim_archive(archive_path: Path) -> tuple[dict, list[dict]]:
    try:
        from libzim.reader import Archive
    except ImportError as error:
        raise RuntimeError(
            "reading .zim sources requires the optional `libzim` package "
            "(install with `python3 -m pip install -r "
            "requirements-wikipedia.txt`)"
        ) from error

    archive = Archive(archive_path)
    if not archive.check():
        raise ValueError("ZIM internal checksum verification failed")
    source_date = archive.get_metadata("Date").decode("utf-8")
    pages: list[dict] = []
    canonical_pattern = re.compile(
        rb'<link\s+rel="canonical"\s+href="([^"]+)"', re.IGNORECASE
    )
    for entry_id in range(archive.all_entry_count):
        entry = archive._get_entry_by_id(entry_id)
        if entry.is_redirect:
            continue
        item = entry.get_item()
        if not item.mimetype.casefold().startswith("text/html"):
            continue
        raw = bytes(item.content)
        match = canonical_pattern.search(raw)
        if not match:
            continue
        source_url = match.group(1).decode("utf-8", errors="replace")
        if not source_url.startswith("https://en.wikipedia.org/"):
            continue
        content = raw.decode("utf-8", errors="replace")
        pages.append(
            {
                "page_id": None,
                "revision_id": None,
                "revision_timestamp": None,
                "revision_url": source_url,
                "title": entry.title,
                "wikitext": content,
                "_sequence_index": len(pages),
                "_content_sha256": bytes_sha256(raw),
                "_source_entry_key": f"zim-entry:{entry_id}",
                "_source_path": entry.path,
                "_source_url": source_url,
                "_source_timestamp": source_date,
                "_input_format": "html",
            }
        )
    manifest = {
        "archive_format": ZIM_ARCHIVE_FORMAT,
        "page_count": len(pages),
        "license": {"spdx_id": "CC-BY-SA-4.0"},
        "source_date": source_date,
        "zim_all_entry_count": archive.all_entry_count,
        "zim_article_count": archive.article_count,
    }
    return manifest, pages


def response_text(payload: dict) -> str:
    if payload.get("status") != "completed":
        raise ValueError(
            "API response was not completed: "
            + json.dumps(payload.get("incomplete_details"))
        )
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "refusal":
                raise ValueError(f"model refusal: {content.get('refusal')}")
            if content.get("type") == "output_text":
                return content["text"]
    raise ValueError("API response has no output_text")


def request_payload(
    model: str,
    page: dict,
    submitted_wikitext: str,
    max_output_tokens: int,
) -> dict:
    page_input = {
        "source_entry_key": page["_source_entry_key"],
        "source_path": page["_source_path"],
        "source_url": page["_source_url"],
        "input_format": page["_input_format"],
        "page_id": page["page_id"],
        "revision_id": page["revision_id"],
        "revision_timestamp": page["revision_timestamp"],
        "revision_url": page["revision_url"],
        "title": page["title"],
        "source_document": submitted_wikitext,
    }
    return {
        "model": model,
        "reasoning": {"effort": "low"},
        "input": [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {
                "role": "user",
                "content": json.dumps(page_input, ensure_ascii=False),
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "wikipedia_scientific_candidates",
                "strict": True,
                "schema": RESPONSE_SCHEMA,
            },
            "verbosity": "low",
        },
        "max_output_tokens": max_output_tokens,
        "store": False,
    }


def call_openai(
    api_key: str,
    model: str,
    page: dict,
    submitted_wikitext: str,
    *,
    max_output_tokens: int,
    retries: int,
    timeout: int,
) -> dict:
    body = json.dumps(
        request_payload(model, page, submitted_wikitext, max_output_tokens)
    ).encode("utf-8")
    request_id = str(uuid.uuid4())
    for attempt in range(retries + 1):
        request = urllib.request.Request(
            API_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "universe-db-wikipedia-parser/2",
                "X-Client-Request-Id": request_id,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            retryable = error.code == 429 or 500 <= error.code < 600
            detail = error.read().decode("utf-8", errors="replace")
            if not retryable or attempt == retries:
                raise RuntimeError(f"OpenAI API HTTP {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            if attempt == retries:
                raise RuntimeError(f"OpenAI API request failed: {error}") from error
        time.sleep(min(2**attempt, 30))
    raise AssertionError("unreachable")


def normalize_result(payload: dict) -> dict:
    result = json.loads(response_text(payload))
    if result["page_relevance"] == "relevant" and not result["entities"]:
        result["page_relevance"] = "no_data"
        result["notes"] = "Model returned no candidates."
    for entity in result["entities"]:
        if not entity["name"].strip() or not entity["evidence_text"].strip():
            raise ValueError("candidate lacks name or evidence")
        for fact in entity["facts"]:
            if fact["value_decimal"] is None and fact["value_text"] is None:
                raise ValueError("candidate fact has no value")
        for composition in entity["composition"]:
            count = composition["atom_count"]
            if count is not None and count <= 0:
                raise ValueError("composition atom_count must be positive")
    return result


def resolve_authoritative_match(
    connection: sqlite3.Connection, candidate: dict
) -> tuple[str | None, str | None]:
    suggested = candidate["existing_id"]
    proposed = candidate["proposed_id"]
    for identity in (suggested, proposed):
        if not identity:
            continue
        if candidate["candidate_kind"] == "reaction":
            row = connection.execute(
                "SELECT reaction_id FROM reaction WHERE reaction_id = ?",
                (identity,),
            ).fetchone()
            if row:
                return None, row[0]
        else:
            row = connection.execute(
                "SELECT entity_id FROM entity WHERE entity_id = ?",
                (identity,),
            ).fetchone()
            if row:
                return row[0], None
    if candidate["candidate_kind"] == "element" and candidate["atomic_number"]:
        row = connection.execute(
            "SELECT entity_id FROM element WHERE atomic_number = ?",
            (candidate["atomic_number"],),
        ).fetchone()
        if row:
            return row[0], None
    if (
        candidate["candidate_kind"] == "nuclide"
        and candidate["proton_count"] is not None
        and candidate["neutron_count"] is not None
    ):
        row = connection.execute(
            """
            SELECT entity_id FROM nuclide
            WHERE proton_count = ? AND neutron_count = ?
              AND isomer_index = ?
            """,
            (
                candidate["proton_count"],
                candidate["neutron_count"],
                candidate["isomer_index"] or 0,
            ),
        ).fetchone()
        if row:
            return row[0], None
    return None, None


def insert_candidate(
    connection: sqlite3.Connection,
    page_parse_id: str,
    candidate_index: int,
    candidate: dict,
) -> None:
    candidate_id = str(uuid.uuid4())
    existing_entity_id, existing_reaction_id = resolve_authoritative_match(
        connection, candidate
    )
    connection.execute(
        """
        INSERT INTO unverified_entity_candidate(
            candidate_id, page_parse_id, candidate_index, candidate_kind,
            name, proposed_id, existing_entity_id, existing_reaction_id,
            formula, electric_charge, atomic_number, proton_count,
            neutron_count, isomer_index, observed, confidence, evidence_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            candidate_id,
            page_parse_id,
            candidate_index,
            candidate["candidate_kind"],
            candidate["name"],
            candidate["proposed_id"],
            existing_entity_id,
            existing_reaction_id,
            candidate["formula"],
            candidate["electric_charge"],
            candidate["atomic_number"],
            candidate["proton_count"],
            candidate["neutron_count"],
            candidate["isomer_index"],
            None if candidate["observed"] is None else int(candidate["observed"]),
            candidate["confidence"],
            candidate["evidence_text"],
        ),
    )
    for index, alias in enumerate(dict.fromkeys(candidate["aliases"])):
        connection.execute(
            """
            INSERT INTO unverified_candidate_alias(
                candidate_id, alias_index, value
            ) VALUES (?, ?, ?)
            """,
            (candidate_id, index, alias),
        )
    for index, component in enumerate(candidate["composition"]):
        connection.execute(
            """
            INSERT INTO unverified_candidate_composition(
                candidate_id, component_index, component_kind,
                component_name, component_proposed_id, atom_count,
                evidence_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate_id,
                index,
                component["component_kind"],
                component["component_name"],
                component["component_proposed_id"],
                component["atom_count"],
                component["evidence_text"],
            ),
        )
    for index, fact in enumerate(candidate["facts"]):
        fact_id = str(uuid.uuid4())
        value_num, value_den = exact_ratio(fact["value_decimal"])
        uncertainty_num, uncertainty_den = exact_ratio(
            fact["uncertainty_decimal"]
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
                fact_id,
                candidate_id,
                index,
                fact["field_key"],
                fact["value_decimal"],
                value_num,
                value_den,
                fact["value_text"],
                fact["unit"],
                fact["uncertainty_decimal"],
                uncertainty_num,
                uncertainty_den,
                fact["evidence_text"],
            ),
        )
        for condition_index, condition in enumerate(fact["conditions"]):
            condition_num, condition_den = exact_ratio(
                condition["value_decimal"]
            )
            connection.execute(
                """
                INSERT INTO unverified_candidate_fact_condition(
                    candidate_fact_id, condition_index, quantity_kind,
                    value_decimal_text, value_numerator, value_denominator,
                    value_text, unit_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fact_id,
                    condition_index,
                    condition["quantity_kind"],
                    condition["value_decimal"],
                    condition_num,
                    condition_den,
                    condition["value_text"],
                    condition["unit"],
                ),
            )
    for index, relation in enumerate(candidate["relations"]):
        coefficient_num, coefficient_den = exact_ratio(
            relation["coefficient_decimal"]
        )
        connection.execute(
            """
            INSERT INTO unverified_candidate_relation(
                relation_id, candidate_id, relation_index, relation_kind,
                object_name, object_proposed_id, role,
                coefficient_decimal_text, coefficient_numerator,
                coefficient_denominator, phase_text, details_text,
                evidence_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                candidate_id,
                index,
                relation["relation_kind"],
                relation["object_name"],
                relation["object_proposed_id"],
                relation["role"],
                relation["coefficient_decimal"],
                coefficient_num,
                coefficient_den,
                relation["phase"],
                relation["details"],
                relation["evidence_text"],
            ),
        )


def already_parsed(
    connection: sqlite3.Connection,
    archive_digest: str,
    page: dict,
) -> bool:
    return (
        connection.execute(
            """
            SELECT 1
            FROM wikipedia_page_parse AS page
            JOIN wikipedia_parse_run AS run USING (run_id)
            WHERE run.archive_sha256 = ?
              AND page.source_entry_key = ?
              AND page.status IN ('parsed', 'parsed_partial', 'no_data')
            LIMIT 1
            """,
            (archive_digest, page["_source_entry_key"]),
        ).fetchone()
        is not None
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--start-page", type=int, default=0)
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="maximum sequential pages; zero means all remaining pages",
    )
    parser.add_argument("--max-page-chars", type=int, default=500_000)
    parser.add_argument("--max-output-tokens", type=int, default=10_000)
    parser.add_argument("--requests-per-minute", type=int, default=30)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--accept-cost", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if (
        args.start_page < 0
        or args.max_pages < 0
        or args.max_page_chars <= 0
        or args.max_output_tokens <= 0
    ):
        raise SystemExit("page and token limits are invalid")
    manifest, pages = load_archive(args.archive)
    selected = pages[args.start_page :]
    if args.max_pages:
        selected = selected[: args.max_pages]
    archive_digest = sha256(args.archive)
    print(
        f"archive pages: {len(pages)}; selected sequential pages: {len(selected)}"
    )
    for page in selected[:5]:
        print(
            f"  [{page['_sequence_index']}] {page['title']} "
            f"({page['_input_format']}, {len(page['wikitext'])} chars)"
        )
    if not args.execute:
        print("dry-run only; add --execute --accept-cost to call the API")
        return 0
    if not args.accept_cost:
        raise SystemExit("--execute requires --accept-cost")
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        raise SystemExit(f"{args.api_key_env} is not set")

    prepare_output(args.database, args.output)
    run_id = str(uuid.uuid4())
    completed = 0
    skipped = 0
    failed = 0
    interrupted = False
    base_digest = sha256(args.database)
    with sqlite3.connect(args.output) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        ensure_schema(connection)
        bind_overlay_to_base(
            connection, args.database, args.output, base_digest
        )
        connection.execute(
            """
            INSERT INTO wikipedia_parse_run(
                run_id, started_at, model, archive_name, archive_format,
                archive_sha256, archive_page_count, license_spdx_id, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running')
            """,
            (
                run_id,
                utc_now(),
                args.model,
                args.archive.name,
                manifest["archive_format"],
                archive_digest,
                manifest["page_count"],
                manifest["license"]["spdx_id"],
            ),
        )
        connection.commit()
        try:
            for selected_index, page in enumerate(selected, start=1):
                if not args.refresh and already_parsed(
                    connection, archive_digest, page
                ):
                    skipped += 1
                    continue
                page_parse_id = str(uuid.uuid4())
                wikitext = page["wikitext"]
                submitted = wikitext[: args.max_page_chars]
                with connection:
                    connection.execute(
                        """
                        INSERT INTO wikipedia_page_parse(
                            page_parse_id, run_id, sequence_index,
                            source_entry_key, source_path, input_format,
                            page_id, revision_id, title, source_url,
                            source_timestamp, content_sha256, content_chars,
                            submitted_chars, status, created_at
                        ) VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            'pending', ?
                        )
                        """,
                        (
                            page_parse_id,
                            run_id,
                            page["_sequence_index"],
                            page["_source_entry_key"],
                            page["_source_path"],
                            page["_input_format"],
                            page["page_id"],
                            page["revision_id"],
                            page["title"],
                            page["_source_url"],
                            page["_source_timestamp"],
                            page["_content_sha256"],
                            len(wikitext),
                            len(submitted),
                            utc_now(),
                        ),
                    )
                print(
                    f"[{selected_index}/{len(selected)}] "
                    f"{page['title']} ({len(submitted)} chars)",
                    flush=True,
                )
                started = time.monotonic()
                try:
                    payload = call_openai(
                        api_key,
                        args.model,
                        page,
                        submitted,
                        max_output_tokens=args.max_output_tokens,
                        retries=args.retries,
                        timeout=args.timeout,
                    )
                    result = normalize_result(payload)
                    if result["page_relevance"] == "no_data":
                        status = "no_data"
                    elif len(submitted) < len(wikitext):
                        status = "parsed_partial"
                    else:
                        status = "parsed"
                    with connection:
                        for candidate_index, candidate in enumerate(
                            result["entities"]
                        ):
                            insert_candidate(
                                connection,
                                page_parse_id,
                                candidate_index,
                                candidate,
                            )
                        connection.execute(
                            """
                            UPDATE wikipedia_page_parse
                            SET status = ?, response_id = ?, completed_at = ?
                            WHERE page_parse_id = ?
                            """,
                            (
                                status,
                                payload.get("id"),
                                utc_now(),
                                page_parse_id,
                            ),
                        )
                    completed += 1
                except (RuntimeError, ValueError, json.JSONDecodeError) as error:
                    with connection:
                        connection.execute(
                            """
                            UPDATE wikipedia_page_parse
                            SET status = 'error', error_text = ?,
                                completed_at = ?
                            WHERE page_parse_id = ?
                            """,
                            (str(error), utc_now(), page_parse_id),
                        )
                    failed += 1
                    print(f"  error: {error}", flush=True)
                if args.requests_per_minute:
                    interval = 60 / args.requests_per_minute
                    remaining = interval - (time.monotonic() - started)
                    if remaining > 0:
                        time.sleep(remaining)
        except KeyboardInterrupt:
            interrupted = True
            print("stopping after current committed page", flush=True)
        finally:
            status = "stopped" if interrupted else "completed"
            with connection:
                connection.execute(
                    """
                    UPDATE wikipedia_parse_run
                    SET status = ?, completed_at = ?, notes = ?
                    WHERE run_id = ?
                    """,
                    (
                        status,
                        utc_now(),
                        (
                            f"{completed} pages completed; {skipped} skipped; "
                            f"{failed} failed"
                        ),
                        run_id,
                    ),
                )
    print(
        f"wrote {args.output}: {completed} completed, {skipped} skipped, "
        f"{failed} failed, run {run_id}"
    )
    return 130 if interrupted else 0


if __name__ == "__main__":
    raise SystemExit(main())
