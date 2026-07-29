#!/usr/bin/env python3
"""Web-research missing scientific fields into an unverified SQLite overlay.

This script deliberately does not promote model output into reviewed tables.
Every result remains in the unverified_* staging tables until a human verifies
the source, license, identity mapping, units, conditions, and transformation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
import urllib.error
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "universe.db"
DEFAULT_OUTPUT = ROOT / ".build" / "unverified.db"
DEFAULT_MODEL = "gpt-5.4-nano"
API_URL = "https://api.openai.com/v1/responses"
SCHEMA_VERSION = 1
MAX_SQLITE_INTEGER = 2**63 - 1


@dataclass(frozen=True)
class FieldSpec:
    scope: str
    key: str
    label: str
    guidance: str
    authoritative_property_id: str | None = None


@dataclass(frozen=True)
class Target:
    kind: str
    target_id: str
    label: str
    entity_id: str | None


@dataclass(frozen=True)
class Task:
    target: Target
    field: FieldSpec
    prompt: str


FIELDS = (
    FieldSpec(
        "elements",
        "melting_point",
        "melting temperature",
        "Return separate facts for distinct pressure conditions, in kelvin.",
        "property:melting_point",
    ),
    FieldSpec(
        "elements",
        "boiling_point",
        "boiling temperature",
        "Return separate facts for distinct pressure conditions, in kelvin.",
        "property:boiling_point",
    ),
    FieldSpec(
        "elements",
        "electron_configuration",
        "ground-state electron configuration and shell placement",
        "Use source notation verbatim as text; do not infer a configuration.",
    ),
    FieldSpec(
        "elements",
        "spectra",
        "experimentally reported electron, visible, ultraviolet, and X-ray spectra",
        "Return individual sourced lines, peaks, edges, or compact curve points with axis and intensity units.",
    ),
    FieldSpec(
        "elements",
        "electronegativity",
        "electronegativity",
        "Name the scale (for example Pauling) as a condition; do not mix scales.",
        "property:electronegativity",
    ),
    FieldSpec(
        "elements",
        "molar_mass",
        "molar mass",
        "Report the source-specific value and its compositional basis.",
        "property:molar_mass",
    ),
    FieldSpec(
        "nuclides",
        "relative_atomic_mass",
        "relative atomic mass",
        "Return the nuclide-specific measured value, not the element standard atomic weight.",
        "property:relative_atomic_mass",
    ),
    FieldSpec(
        "nuclides",
        "natural_abundance",
        "natural isotopic abundance",
        "Include sample or terrestrial-composition conditions and uncertainty.",
        "property:isotopic_composition",
    ),
    FieldSpec(
        "nuclides",
        "nuclear_spin",
        "nuclear spin and parity",
        "Preserve parity in value_text and put a numeric spin in value_decimal when possible.",
        "property:nuclear_spin",
    ),
    FieldSpec(
        "nuclides",
        "half_life",
        "half-life",
        "Use seconds for numeric values. Mark stable nuclides as text, not as an invented infinite number.",
        "property:half_life",
    ),
    FieldSpec(
        "nuclides",
        "mass_excess_energy",
        "mass excess energy",
        "Use electronvolts and preserve the source uncertainty.",
        "property:mass_excess_energy",
    ),
    FieldSpec(
        "nuclides",
        "nuclear_binding_energy",
        "total nuclear binding energy and binding energy per nucleon",
        "Return total and per-nucleon values as separate facts in electronvolts.",
    ),
    FieldSpec(
        "nuclides",
        "decay_channels",
        "alpha, beta-minus, beta-plus/positron, electron-capture, proton, neutron, gamma, and fission decay probabilities and partial half-lives",
        "Return one fact per sourced channel; include channel type, daughter, branch probability, and partial half-life when reported.",
    ),
    FieldSpec(
        "nuclides",
        "spectra",
        "experimentally reported nuclear, gamma, X-ray, visible, and ultraviolet spectra",
        "Return individual sourced lines, peaks, edges, or compact curve points with units.",
    ),
    FieldSpec(
        "nuclides",
        "fusion_cross_sections",
        "measured fusion reaction cross sections involving this nuclide",
        "Return one fact per energy-or-relative-speed/cross-section point and identify target, projectile, products, axis frame, and units.",
    ),
    FieldSpec(
        "molecules",
        "melting_point",
        "melting temperature",
        "Return distinct polymorph, pressure, and sample conditions separately.",
        "property:melting_point",
    ),
    FieldSpec(
        "molecules",
        "boiling_point",
        "boiling temperature",
        "Return separate facts for distinct pressure conditions.",
        "property:boiling_point",
    ),
    FieldSpec(
        "molecules",
        "molar_mass",
        "molar mass",
        "Verify the exact molecular identity or isotopologue.",
        "property:molar_mass",
    ),
    FieldSpec(
        "molecules",
        "spectra",
        "radio, infrared, visible, ultraviolet, and X-ray spectra",
        "Return individual sourced lines, peaks, bands, or compact curve points with sample conditions.",
    ),
    FieldSpec(
        "reactions",
        "energy_change",
        "reaction energy or enthalpy change",
        "Include direction, phases, temperature, pressure, and units.",
    ),
    FieldSpec(
        "reactions",
        "equilibrium",
        "equilibrium constant",
        "Include equilibrium-constant definition and all conditions.",
    ),
    FieldSpec(
        "reactions",
        "rate_law",
        "rate law and rate constants",
        "Keep each temperature, pressure, phase, catalyst, and kinetic regime separate.",
    ),
    FieldSpec(
        "reactions",
        "conditions",
        "experimentally reported reaction conditions, catalysts, selectivity, and yield",
        "Do not treat yield as stoichiometry; preserve the experimental setup.",
    ),
)


RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {
            "type": "string",
            "enum": ["found", "not_found", "ambiguous"],
        },
        "notes": {"type": ["string", "null"]},
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "value_decimal": {"type": ["string", "null"]},
                    "value_text": {"type": ["string", "null"]},
                    "unit": {"type": ["string", "null"]},
                    "uncertainty_decimal": {"type": ["string", "null"]},
                    "relation_kind": {"type": ["string", "null"]},
                    "related_entity": {"type": ["string", "null"]},
                    "method_notes": {"type": ["string", "null"]},
                    "conditions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "quantity_kind": {"type": "string"},
                                "value_decimal": {"type": ["string", "null"]},
                                "value_text": {"type": ["string", "null"]},
                                "unit": {"type": ["string", "null"]},
                            },
                            "required": [
                                "quantity_kind",
                                "value_decimal",
                                "value_text",
                                "unit",
                            ],
                        },
                    },
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "url": {"type": "string"},
                                "title": {"type": ["string", "null"]},
                                "supporting_text": {"type": ["string", "null"]},
                            },
                            "required": ["url", "title", "supporting_text"],
                        },
                    },
                },
                "required": [
                    "value_decimal",
                    "value_text",
                    "unit",
                    "uncertainty_decimal",
                    "relation_kind",
                    "related_entity",
                    "method_notes",
                    "conditions",
                    "sources",
                ],
            },
        },
    },
    "required": ["status", "notes", "facts"],
}


SYSTEM_INSTRUCTIONS = """You research one narrowly specified scientific field.
You must use web search. Prefer primary databases, standards bodies, evaluated
data libraries, and papers. Wikipedia may help discovery but is not sufficient
as the only source. Never calculate or guess a missing measurement. Preserve
conflicting results as separate facts. A number must be copied from a cited
source, with its units, uncertainty, applicable conditions, and identity
qualifiers. Return not_found when no reliable value is located. This output is
unverified staging data and must not be described as reviewed or measured by
the database project."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_csv(value: str) -> set[str]:
    return {part.strip() for part in value.split(",") if part.strip()}


def load_targets(connection: sqlite3.Connection, scope: str) -> list[Target]:
    if scope == "elements":
        rows = connection.execute(
            """
            SELECT e.entity_id, e.name || ' (' || element.symbol || ')' AS label
            FROM entity AS e JOIN element ON element.entity_id = e.entity_id
            ORDER BY element.atomic_number
            """
        )
        return [Target("element", row[0], row[1], row[0]) for row in rows]
    if scope == "nuclides":
        rows = connection.execute(
            """
            SELECT e.entity_id,
                   element.symbol || '-' ||
                   (nuclide.proton_count + nuclide.neutron_count) ||
                   CASE WHEN nuclide.isomer_index = 0 THEN ''
                        ELSE 'm' || nuclide.isomer_index END AS label
            FROM entity AS e
            JOIN nuclide ON nuclide.entity_id = e.entity_id
            JOIN element ON element.entity_id = nuclide.element_id
            ORDER BY nuclide.proton_count, nuclide.neutron_count,
                     nuclide.isomer_index
            """
        )
        return [Target("nuclide", row[0], row[1], row[0]) for row in rows]
    if scope == "molecules":
        rows = connection.execute(
            """
            SELECT e.entity_id, e.name || ' (' || cs.formula || ')' AS label
            FROM entity AS e
            JOIN chemical_species AS cs ON cs.entity_id = e.entity_id
            JOIN molecule ON molecule.species_id = e.entity_id
            ORDER BY e.entity_id
            """
        )
        return [Target("molecule", row[0], row[1], row[0]) for row in rows]
    if scope == "reactions":
        rows = connection.execute(
            "SELECT reaction_id, name FROM reaction ORDER BY reaction_id"
        )
        return [Target("reaction", row[0], row[1], None) for row in rows]
    raise ValueError(f"unsupported scope: {scope}")


def authoritative_value_exists(
    connection: sqlite3.Connection, target: Target, field: FieldSpec
) -> bool:
    if target.entity_id and field.authoritative_property_id:
        exists = connection.execute(
            """
            SELECT 1 FROM observation
            WHERE subject_entity_id = ? AND property_id = ?
            LIMIT 1
            """,
            (target.entity_id, field.authoritative_property_id),
        ).fetchone()
        if exists:
            return True
    if field.key == "electron_configuration" and target.kind == "element":
        value = connection.execute(
            "SELECT electron_configuration FROM element WHERE entity_id = ?",
            (target.target_id,),
        ).fetchone()
        return bool(value and value[0])
    if field.key == "spectra" and target.entity_id:
        return (
            connection.execute(
                "SELECT 1 FROM spectrum WHERE subject_entity_id = ? LIMIT 1",
                (target.entity_id,),
            ).fetchone()
            is not None
        )
    if field.key == "decay_channels" and target.kind == "nuclide":
        return (
            connection.execute(
                "SELECT 1 FROM nuclear_channel WHERE parent_nuclide_id = ? LIMIT 1",
                (target.target_id,),
            ).fetchone()
            is not None
        )
    if field.key == "fusion_cross_sections" and target.kind == "nuclide":
        return (
            connection.execute(
                """
                SELECT 1
                FROM nuclear_cross_section_point AS point
                JOIN nuclear_channel AS channel USING (channel_id)
                LEFT JOIN nuclear_channel_nuclide AS participant
                  ON participant.channel_id = channel.channel_id
                WHERE channel.parent_nuclide_id = ?
                   OR participant.nuclide_id = ?
                LIMIT 1
                """,
                (target.target_id, target.target_id),
            ).fetchone()
            is not None
        )
    if target.kind == "reaction":
        if field.key == "energy_change":
            row = connection.execute(
                "SELECT energy_change_numerator FROM reaction WHERE reaction_id = ?",
                (target.target_id,),
            ).fetchone()
            return bool(row and row[0] is not None)
        if field.key == "conditions":
            return (
                connection.execute(
                    "SELECT 1 FROM reaction_condition WHERE reaction_id = ? LIMIT 1",
                    (target.target_id,),
                ).fetchone()
                is not None
            )
    return False


def staged_value_exists(
    connection: sqlite3.Connection, target: Target, field: FieldSpec
) -> bool:
    try:
        return (
            connection.execute(
                """
                SELECT 1
                FROM research_task
                WHERE target_kind = ? AND target_id = ? AND field_key = ?
                  AND status = 'found'
                LIMIT 1
                """,
                (target.kind, target.target_id, field.key),
            ).fetchone()
            is not None
        )
    except sqlite3.OperationalError:
        return False


def make_prompt(target: Target, field: FieldSpec) -> str:
    return (
        f"Find on the internet {field.label} of {target.label}. "
        f"Canonical database ID: {target.target_id}. {field.guidance} "
        "Return every fact only in the requested JSON structure and attach at "
        "least one direct supporting source URL to each fact."
    )


def plan_tasks(
    connection: sqlite3.Connection,
    scopes: set[str],
    requested_fields: set[str],
    include_existing: bool,
    refresh_staged: bool,
    limit_targets: int,
) -> list[Task]:
    tasks: list[Task] = []
    for scope in sorted(scopes):
        fields = [
            field
            for field in FIELDS
            if field.scope == scope
            and (not requested_fields or field.key in requested_fields)
        ]
        targets = load_targets(connection, scope)
        if limit_targets:
            targets = targets[:limit_targets]
        for target in targets:
            for field in fields:
                if not include_existing and authoritative_value_exists(
                    connection, target, field
                ):
                    continue
                if not refresh_staged and staged_value_exists(
                    connection, target, field
                ):
                    continue
                tasks.append(Task(target, field, make_prompt(target, field)))
    return tasks


def response_text(payload: dict) -> str:
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                return content["text"]
    raise ValueError("API response has no output_text")


def response_sources(payload: dict) -> list[dict]:
    sources: list[dict] = []
    seen: set[str] = set()
    for item in payload.get("output", []):
        if item.get("type") != "web_search_call":
            continue
        for source in item.get("action", {}).get("sources", []):
            url = source.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            sources.append(
                {
                    "url": url,
                    "title": source.get("title"),
                    "supporting_text": None,
                }
            )
    return sources


def request_payload(model: str, task: Task) -> dict:
    return {
        "model": model,
        "reasoning": {"effort": "low"},
        "tools": [{"type": "web_search"}],
        "tool_choice": "auto",
        "include": ["web_search_call.action.sources"],
        "input": [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": task.prompt},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "scientific_web_research",
                "strict": True,
                "schema": RESPONSE_SCHEMA,
            },
            "verbosity": "low",
        },
        "max_output_tokens": 3000,
        "store": False,
    }


def call_openai(
    api_key: str,
    model: str,
    task: Task,
    retries: int,
    timeout: int,
) -> dict:
    body = json.dumps(request_payload(model, task)).encode("utf-8")
    request_id = str(uuid.uuid4())
    for attempt in range(retries + 1):
        request = urllib.request.Request(
            API_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "universe-db-unverified-research/1",
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


def normalize_result(payload: dict) -> tuple[dict, list[dict]]:
    result = json.loads(response_text(payload))
    if result["status"] not in {"found", "not_found", "ambiguous"}:
        raise ValueError(f"invalid result status: {result['status']}")
    fallback_sources = response_sources(payload)
    for fact in result["facts"]:
        if fact["value_decimal"] is None and fact["value_text"] is None:
            raise ValueError("fact has neither a numeric nor textual value")
        if not fact["sources"]:
            fact["sources"] = fallback_sources
    if result["status"] == "found" and not result["facts"]:
        result["status"] = "ambiguous"
        result["notes"] = "Model reported found without returning facts."
    return result, fallback_sources


def insert_task(
    connection: sqlite3.Connection,
    run_id: str,
    task_id: str,
    task: Task,
) -> None:
    connection.execute(
        """
        INSERT INTO research_task(
            task_id, run_id, target_kind, target_id, target_label, field_key,
            prompt, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """,
        (
            task_id,
            run_id,
            task.target.kind,
            task.target.target_id,
            task.target.label,
            task.field.key,
            task.prompt,
            utc_now(),
        ),
    )


def insert_result(
    connection: sqlite3.Connection,
    task_id: str,
    task: Task,
    api_payload: dict,
    result: dict,
) -> None:
    for fact in result["facts"]:
        fact_id = str(uuid.uuid4())
        value_num, value_den = exact_ratio(fact["value_decimal"])
        uncertainty_num, uncertainty_den = exact_ratio(
            fact["uncertainty_decimal"]
        )
        connection.execute(
            """
            INSERT INTO unverified_fact(
                fact_id, task_id, target_entity_id, target_kind, target_id,
                field_key, value_decimal_text, value_numerator,
                value_denominator, value_text, unit_text,
                uncertainty_decimal_text, uncertainty_numerator,
                uncertainty_denominator, relation_kind,
                related_entity_text, method_notes, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fact_id,
                task_id,
                task.target.entity_id,
                task.target.kind,
                task.target.target_id,
                task.field.key,
                fact["value_decimal"],
                value_num,
                value_den,
                fact["value_text"],
                fact["unit"],
                fact["uncertainty_decimal"],
                uncertainty_num,
                uncertainty_den,
                fact["relation_kind"],
                fact["related_entity"],
                fact["method_notes"],
                SCHEMA_VERSION,
            ),
        )
        for index, condition in enumerate(fact["conditions"]):
            condition_num, condition_den = exact_ratio(
                condition["value_decimal"]
            )
            connection.execute(
                """
                INSERT INTO unverified_fact_condition(
                    fact_id, condition_index, quantity_kind,
                    value_decimal_text, value_numerator, value_denominator,
                    value_text, unit_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fact_id,
                    index,
                    condition["quantity_kind"],
                    condition["value_decimal"],
                    condition_num,
                    condition_den,
                    condition["value_text"],
                    condition["unit"],
                ),
            )
        seen_urls: set[str] = set()
        for source in fact["sources"]:
            if source["url"] in seen_urls:
                continue
            source_index = len(seen_urls)
            seen_urls.add(source["url"])
            connection.execute(
                """
                INSERT INTO unverified_fact_source(
                    fact_id, source_index, url, title, supporting_text
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    fact_id,
                    source_index,
                    source["url"],
                    source["title"],
                    source["supporting_text"],
                ),
            )
    connection.execute(
        """
        UPDATE research_task
        SET status = ?, response_id = ?, completed_at = ?
        WHERE task_id = ?
        """,
        (result["status"], api_payload.get("id"), utc_now(), task_id),
    )


def ensure_research_schema(connection: sqlite3.Connection) -> None:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version < 4:
        raise RuntimeError(
            f"database schema is {version}; run `make build` to create schema 4"
        )
    connection.execute("SELECT 1 FROM research_run LIMIT 1")


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
        """
        SELECT value FROM database_metadata
        WHERE key = 'unverified_base_sha256'
        """
    ).fetchone()
    if row is not None:
        recorded = row[0]
        if database.resolve() != output.resolve() and recorded != current_base_digest:
            raise RuntimeError(
                "the existing unverified overlay belongs to a different base "
                "database; remove it or choose another --output"
            )
        return recorded
    prior_run = connection.execute(
        """
        SELECT base_database_sha256
        FROM research_run
        ORDER BY started_at, run_id
        LIMIT 1
        """
    ).fetchone()
    recorded = prior_run[0] if prior_run is not None else current_base_digest
    if database.resolve() != output.resolve() and recorded != current_base_digest:
        raise RuntimeError(
            "the existing unverified overlay belongs to a different base "
            "database; remove it or choose another --output"
        )
    connection.execute(
        """
        INSERT INTO database_metadata(key, value)
        VALUES ('unverified_base_sha256', ?)
        """,
        (recorded,),
    )
    return recorded


def print_plan(tasks: list[Task]) -> None:
    counts: dict[tuple[str, str], int] = {}
    for task in tasks:
        key = (task.field.scope, task.field.key)
        counts[key] = counts.get(key, 0) + 1
    print(f"planned requests: {len(tasks)}")
    for (scope, field), count in sorted(counts.items()):
        print(f"  {scope}.{field}: {count}")
    for task in tasks[:5]:
        print(f"  example: {task.prompt}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--scopes",
        default="elements,nuclides",
        help="comma-separated: elements,nuclides,molecules,reactions",
    )
    parser.add_argument(
        "--fields",
        default="",
        help="optional comma-separated field keys",
    )
    parser.add_argument(
        "--include-existing",
        action="store_true",
        help="research fields even when reviewed data already exists",
    )
    parser.add_argument(
        "--refresh-staged",
        action="store_true",
        help="research fields that already have a found unverified task",
    )
    parser.add_argument(
        "--limit-targets",
        type=int,
        default=0,
        help="limit targets per scope for a trial run; zero means all",
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        default=0,
        help="cap requests after planning; zero means all",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument(
        "--requests-per-minute",
        type=int,
        default=60,
        help="client-side pacing limit; zero disables pacing",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="call the API and write the unverified overlay; default is dry-run",
    )
    parser.add_argument(
        "--accept-cost",
        action="store_true",
        help="acknowledge model-token and web-search tool charges",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scopes = parse_csv(args.scopes)
    allowed_scopes = {"elements", "nuclides", "molecules", "reactions"}
    if not scopes or not scopes <= allowed_scopes:
        raise SystemExit(f"invalid scopes: {sorted(scopes - allowed_scopes)}")
    if args.limit_targets < 0 or args.max_requests < 0:
        raise SystemExit("limits cannot be negative")

    planning_database = args.output if args.output.exists() else args.database
    with sqlite3.connect(planning_database) as connection:
        ensure_research_schema(connection)
        tasks = plan_tasks(
            connection,
            scopes,
            parse_csv(args.fields),
            args.include_existing,
            args.refresh_staged,
            args.limit_targets,
        )
    if args.max_requests:
        tasks = tasks[: args.max_requests]
    print_plan(tasks)
    if not args.execute:
        print("dry-run only; add --execute --accept-cost to call the API")
        return 0
    if not args.accept_cost:
        raise SystemExit("--execute requires --accept-cost")
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        raise SystemExit(f"{args.api_key_env} is not set")
    if not tasks:
        return 0

    base_digest = sha256(args.database)
    prepare_output(args.database, args.output)
    run_id = str(uuid.uuid4())
    completed = 0
    failed = 0
    interrupted = False
    with sqlite3.connect(args.output) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        ensure_research_schema(connection)
        base_digest = bind_overlay_to_base(
            connection,
            args.database,
            args.output,
            base_digest,
        )
        connection.execute(
            """
            INSERT INTO research_run(
                run_id, started_at, model, base_database_sha256,
                requested_scopes, status
            ) VALUES (?, ?, ?, ?, ?, 'running')
            """,
            (
                run_id,
                utc_now(),
                args.model,
                base_digest,
                ",".join(sorted(scopes)),
            ),
        )
        connection.commit()
        try:
            for index, task in enumerate(tasks, start=1):
                task_id = str(uuid.uuid4())
                with connection:
                    insert_task(connection, run_id, task_id, task)
                print(
                    f"[{index}/{len(tasks)}] "
                    f"{task.target.label}: {task.field.key}",
                    flush=True,
                )
                started = time.monotonic()
                try:
                    payload = call_openai(
                        api_key,
                        args.model,
                        task,
                        args.retries,
                        args.timeout,
                    )
                    result, _ = normalize_result(payload)
                    with connection:
                        insert_result(connection, task_id, task, payload, result)
                    completed += 1
                except (RuntimeError, ValueError, json.JSONDecodeError) as error:
                    with connection:
                        connection.execute(
                            """
                            UPDATE research_task
                            SET status = 'error', error_text = ?, completed_at = ?
                            WHERE task_id = ?
                            """,
                            (str(error), utc_now(), task_id),
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
            print("stopping after current committed task", flush=True)
        finally:
            status = "stopped" if interrupted else "completed"
            with connection:
                connection.execute(
                    """
                    UPDATE research_run
                    SET status = ?, completed_at = ?,
                        notes = ?
                    WHERE run_id = ?
                    """,
                    (
                        status,
                        utc_now(),
                        f"{completed} tasks completed; {failed} tasks failed",
                        run_id,
                    ),
                )
    print(
        f"wrote {args.output}: {completed} completed, {failed} failed, "
        f"run {run_id}"
    )
    return 130 if interrupted else 0


if __name__ == "__main__":
    raise SystemExit(main())
