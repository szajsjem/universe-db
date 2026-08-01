#!/usr/bin/env python3
"""Sequentially parse a Wikipedia chemistry snapshot into unverified candidates.

Each page is submitted in archive order as one independent structured-output
request. Candidate nuclides, molecules, reactions, compositions, facts, and
relations remain isolated from reviewed tables pending human source review.
"""

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import closing
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
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "universe.db"
DEFAULT_OUTPUT = ROOT / ".build" / "wikipedia-unverified.db"
DEFAULT_MODEL = "qwen/qwen3.5-9b"
DEFAULT_BASE_URL = "http://localhost:12355/v1"
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
        "atom_count": {"type": ["integer", "null"], "minimum": 1},
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
        "atomic_number": {"type": ["integer", "null"], "minimum": 1},
        "proton_count": {"type": ["integer", "null"], "minimum": 1},
        "neutron_count": {"type": ["integer", "null"], "minimum": 0},
        "isomer_index": {"type": ["integer", "null"], "minimum": 0},
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

VERIFICATION_INSTRUCTIONS = """Act as a conservative second-pass scientific
reviewer. Compare the proposed structured extraction with the supplied English
Wikipedia source document and return a complete corrected extraction using the
same schema.

Keep only candidates, aliases, compositions, facts, conditions, and relations
that are explicitly supported by the source. Correct transcription mistakes,
units, conditions, entity kinds, and evidence excerpts. Remove unsupported or
inferred content. You may restore an important omission only when the source
states it explicitly. Do not browse, calculate, balance reactions, invent IDs,
or rely on outside knowledge. evidence_text must be a short excerpt from the
source. Return no_data when no suitable supported content remains. This is
verification of unverified Wikipedia candidates, not promotion to reviewed
database data."""


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
    choices = payload.get("choices")
    if choices:
        choice = choices[0]
        message = choice.get("message", {})
        refusal = message.get("refusal")
        if refusal:
            raise ValueError(f"model refusal: {refusal}")
        content = message.get("content")
        if content:
            return content
        raise ValueError(
            "Chat Completions response has no message content "
            f"(finish_reason={choice.get('finish_reason')!r})"
        )
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


def source_page_input(page: dict, submitted_wikitext: str) -> dict:
    return {
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


def structured_chat_payload(
    model: str,
    system_instructions: str,
    user_input: dict,
    max_output_tokens: int,
    schema_name: str,
) -> dict:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_instructions},
            {
                "role": "user",
                "content": json.dumps(user_input, ensure_ascii=False),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": RESPONSE_SCHEMA,
            }
        },
        "temperature": 0,
        "max_tokens": max_output_tokens,
        "stream": True,
    }


def chat_request_payload(
    model: str,
    page: dict,
    submitted_wikitext: str,
    max_output_tokens: int,
) -> dict:
    return structured_chat_payload(
        model,
        SYSTEM_INSTRUCTIONS,
        source_page_input(page, submitted_wikitext),
        max_output_tokens,
        "wikipedia_scientific_candidates",
    )


def verification_request_payload(
    model: str,
    page: dict,
    submitted_wikitext: str,
    proposed_result: dict,
    max_output_tokens: int,
) -> dict:
    user_input = source_page_input(page, submitted_wikitext)
    user_input["proposed_extraction"] = proposed_result
    return structured_chat_payload(
        model,
        VERIFICATION_INSTRUCTIONS,
        user_input,
        max_output_tokens,
        "verified_wikipedia_scientific_candidates",
    )


def chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return normalized + "/chat/completions"


def is_local_base_url(base_url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(base_url)
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    )


def lm_studio_models_url(base_url: str) -> str:
    parsed = urllib.parse.urlsplit(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"invalid model API base URL: {base_url!r}")
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, "/api/v1/models", "", "")
    )


def parallel_slots_from_models(payload: dict, model: str) -> int:
    matching_instances: list[dict] = []
    for model_record in payload.get("models", []):
        instances = model_record.get("loaded_instances") or []
        matching_instances.extend(
            instance for instance in instances if instance.get("id") == model
        )
        if model_record.get("key") == model:
            matching_instances.extend(instances)
    for instance in matching_instances:
        slots = instance.get("config", {}).get("parallel")
        if isinstance(slots, int) and 1 <= slots <= 64:
            return slots
    raise ValueError(f"LM Studio has no loaded instance with parallel slots for {model}")


def fetch_lm_studio_parallel_slots(
    base_url: str,
    api_key: str | None,
    model: str,
    timeout: int,
) -> int:
    headers = {"User-Agent": "universe-db-wikipedia-parser/3"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        lm_studio_models_url(base_url),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except (urllib.error.HTTPError, urllib.error.URLError) as error:
        raise RuntimeError(f"could not read LM Studio model slots: {error}") from error
    return parallel_slots_from_models(payload, model)


class RequestRateLimiter:
    def __init__(self, requests_per_minute: int) -> None:
        self.interval = 60 / requests_per_minute
        self.next_request = 0.0
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_request - now)
            self.next_request = max(now, self.next_request) + self.interval
        if delay:
            time.sleep(delay)


class StreamResponseError(ValueError):
    """A streamed model response cannot become a valid JSON object."""


class StreamServerError(StreamResponseError):
    """The server reported an internal error while producing an SSE stream."""


class IncrementalJsonObject:
    """Recognize one JSON object without waiting for the end of an SSE stream."""

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.stack: list[str] = []
        self.started = False
        self.in_string = False
        self.escaped = False
        self.complete = False

    def feed(self, fragment: str) -> str | None:
        if self.complete:
            if fragment.strip():
                raise StreamResponseError("model streamed text after its JSON object")
            return "".join(self.parts)
        for offset, character in enumerate(fragment):
            if not self.started:
                if character.isspace():
                    self.parts.append(character)
                    continue
                if character != "{":
                    raise StreamResponseError(
                        "model output does not begin with a JSON object"
                    )
                self.started = True
                self.stack.append("}")
                self.parts.append(character)
                continue

            self.parts.append(character)
            if self.in_string:
                if self.escaped:
                    self.escaped = False
                elif character == "\\":
                    self.escaped = True
                elif character == '"':
                    self.in_string = False
                continue
            if character == '"':
                self.in_string = True
            elif character == "{":
                self.stack.append("}")
            elif character == "[":
                self.stack.append("]")
            elif character in "}]":
                if not self.stack or character != self.stack.pop():
                    raise StreamResponseError(
                        "model output has mismatched JSON delimiters"
                    )
                if not self.stack:
                    trailing = fragment[offset + 1 :]
                    if trailing.strip():
                        raise StreamResponseError(
                            "model streamed text after its JSON object"
                        )
                    self.complete = True
                    text = "".join(self.parts)
                    try:
                        json.loads(text)
                    except json.JSONDecodeError as error:
                        raise StreamResponseError(
                            f"model completed malformed JSON: {error}"
                        ) from error
                    return text
        return None


def iter_sse_data(response):
    data_lines: list[str] = []
    for raw_line in response:
        try:
            line = raw_line.decode("utf-8").rstrip("\r\n")
        except UnicodeDecodeError as error:
            raise StreamResponseError("model stream is not UTF-8") from error
        if not line:
            if data_lines:
                yield "\n".join(data_lines)
                data_lines.clear()
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            value = line[5:]
            if value.startswith(" "):
                value = value[1:]
            data_lines.append(value)
    if data_lines:
        yield "\n".join(data_lines)


def streamed_chat_completion(response) -> dict:
    parser = IncrementalJsonObject()
    response_id: str | None = None
    finish_reason: str | None = None
    for event_text in iter_sse_data(response):
        if event_text == "[DONE]":
            break
        try:
            event = json.loads(event_text)
        except json.JSONDecodeError as error:
            raise StreamResponseError(f"malformed SSE data event: {error}") from error
        if event.get("error"):
            raise StreamServerError(
                "model stream returned an error: "
                + json.dumps(event["error"], ensure_ascii=False)
            )
        response_id = event.get("id") or response_id
        choices = event.get("choices") or []
        if not choices:
            continue
        choice = choices[0]
        delta = choice.get("delta") or {}
        if delta.get("refusal"):
            raise StreamResponseError(f"model refusal: {delta['refusal']}")
        content = delta.get("content")
        if content is not None and not isinstance(content, str):
            raise StreamResponseError("model streamed non-text message content")
        if content:
            complete_text = parser.feed(content)
            if complete_text is not None:
                return {
                    "id": response_id,
                    "choices": [
                        {
                            "finish_reason": choice.get("finish_reason") or "stop",
                            "message": {
                                "role": "assistant",
                                "content": complete_text,
                            },
                        }
                    ],
                }
        finish_reason = choice.get("finish_reason") or finish_reason
        if finish_reason is not None:
            raise StreamResponseError(
                "model stream finished before a complete JSON object "
                f"(finish_reason={finish_reason!r})"
            )
    raise StreamResponseError("model stream ended before a complete JSON object")


def read_chat_completion(response) -> dict:
    headers = getattr(response, "headers", {})
    content_type = headers.get("Content-Type", "") if headers else ""
    if "text/event-stream" in content_type.casefold():
        return streamed_chat_completion(response)
    try:
        return json.loads(response.read())
    except json.JSONDecodeError as error:
        raise StreamResponseError(f"malformed model API response: {error}") from error


def call_model(
    base_url: str,
    api_key: str | None,
    model: str,
    page: dict,
    submitted_wikitext: str,
    *,
    proposed_result: dict | None = None,
    rate_limiter: RequestRateLimiter | None = None,
    stream: bool = True,
    max_output_tokens: int,
    retries: int,
    timeout: int,
) -> dict:
    if proposed_result is None:
        request_payload = chat_request_payload(
            model, page, submitted_wikitext, max_output_tokens
        )
    else:
        request_payload = verification_request_payload(
            model,
            page,
            submitted_wikitext,
            proposed_result,
            max_output_tokens,
        )
    request_id = str(uuid.uuid4())
    stream_supported = stream
    for attempt in range(retries + 1):
        request_payload["stream"] = stream_supported
        body = json.dumps(request_payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "universe-db-wikipedia-parser/3",
            "X-Client-Request-Id": request_id,
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(
            chat_completions_url(base_url),
            data=body,
            method="POST",
            headers=headers,
        )
        try:
            if rate_limiter is not None:
                rate_limiter.wait()
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = read_chat_completion(response)
                try:
                    normalize_result(payload)
                except (ValueError, json.JSONDecodeError) as error:
                    raise StreamResponseError(
                        f"invalid structured model output: {error}"
                    ) from error
                return payload
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            internal_server_error = error.code == 400 and (
                "Engine protocol predict stream returned an error" in detail
                or '"type":"server_error"' in detail
            )
            retryable = (
                error.code == 429
                or 500 <= error.code < 600
                or internal_server_error
            )
            if internal_server_error:
                stream_supported = False
            if not retryable or attempt == retries:
                raise RuntimeError(f"model API HTTP {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            if attempt == retries:
                raise RuntimeError(f"model API request failed: {error}") from error
        except StreamResponseError as error:
            if attempt == retries:
                raise
            if isinstance(error, StreamServerError):
                stream_supported = False
            delay = min(2**attempt, 30)
            retry_mode = (
                " without streaming" if not stream_supported else " as a stream"
            )
            print(
                f"  model attempt {attempt + 1} failed early: {error}; "
                f"retrying{retry_mode} in {delay}s",
                flush=True,
            )
            time.sleep(delay)
            continue
        time.sleep(min(2**attempt, 30))
    raise AssertionError("unreachable")


def normalize_result(payload: dict) -> dict:
    result = json.loads(response_text(payload))
    if result["page_relevance"] == "relevant" and not result["entities"]:
        result["page_relevance"] = "no_data"
        result["notes"] = "Model returned no candidates."
    for entity_index, entity in enumerate(result["entities"]):
        if not entity["name"].strip() or not entity["evidence_text"].strip():
            raise ValueError("candidate lacks name or evidence")
        candidate_label = f"candidate {entity_index} ({entity['name']!r})"
        for field, minimum in (
            ("atomic_number", 1),
            ("proton_count", 1),
            ("neutron_count", 0),
            ("isomer_index", 0),
        ):
            value = entity[field]
            if value is not None and not minimum <= value <= MAX_SQLITE_INTEGER:
                raise ValueError(
                    f"{candidate_label} has invalid {field}: {value}; "
                    f"expected {minimum}..{MAX_SQLITE_INTEGER} or null"
                )
        electric_charge = entity["electric_charge"]
        if electric_charge is not None and not (
            -MAX_SQLITE_INTEGER <= electric_charge <= MAX_SQLITE_INTEGER
        ):
            raise ValueError(
                f"{candidate_label} has invalid electric_charge: "
                f"{electric_charge}"
            )
        for fact in entity["facts"]:
            if fact["value_decimal"] is None and fact["value_text"] is None:
                raise ValueError("candidate fact has no value")
            fact["conditions"] = [
                condition
                for condition in fact["conditions"]
                if condition["value_decimal"] is not None
                or condition["value_text"] is not None
            ]
        for composition in entity["composition"]:
            count = composition["atom_count"]
            if count is not None and not 1 <= count <= MAX_SQLITE_INTEGER:
                raise ValueError(
                    "composition atom_count must fit a positive SQLite integer"
                )
    return result


def extract_page_with_retries(
    base_url: str,
    api_key: str | None,
    model: str,
    page: dict,
    submitted_wikitext: str,
    *,
    verify: bool,
    page_retries: int,
    rate_limiter: RequestRateLimiter | None = None,
    stream: bool = True,
    max_output_tokens: int,
    retries: int,
    timeout: int,
) -> tuple[dict, dict]:
    for page_attempt in range(page_retries + 1):
        try:
            extraction_payload = call_model(
                base_url,
                api_key,
                model,
                page,
                submitted_wikitext,
                rate_limiter=rate_limiter,
                stream=stream,
                max_output_tokens=max_output_tokens,
                retries=retries,
                timeout=timeout,
            )
            result = normalize_result(extraction_payload)
            if not verify:
                return extraction_payload, result
            verification_payload = call_model(
                base_url,
                api_key,
                model,
                page,
                submitted_wikitext,
                proposed_result=result,
                rate_limiter=rate_limiter,
                stream=stream,
                max_output_tokens=max_output_tokens,
                retries=retries,
                timeout=timeout,
            )
            return verification_payload, normalize_result(verification_payload)
        except (RuntimeError, ValueError, json.JSONDecodeError) as error:
            if page_attempt >= page_retries:
                raise
            delay = min(2**page_attempt, 30)
            print(
                f"  page attempt {page_attempt + 1} failed: {error}; "
                f"retrying in {delay}s",
                flush=True,
            )
            time.sleep(delay)
    raise AssertionError("unreachable")


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
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="OpenAI-compatible API base URL (default: local LM Studio)",
    )
    parser.add_argument(
        "--api-key-env",
        default="LM_STUDIO_API_KEY",
        help="optional environment variable containing an API token",
    )
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
    parser.add_argument(
        "--parallel-requests",
        type=int,
        default=0,
        help="concurrent page workers; zero reads the loaded LM Studio slots",
    )
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="disable SSE streaming for incompatible model runtimes",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="HTTP retries for each model call",
    )
    parser.add_argument(
        "--page-retries",
        type=int,
        default=2,
        help="retry the full extraction/verification sequence after model errors",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="make a second model call that corrects claims against the source",
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--accept-cost",
        action="store_true",
        help="required only when --base-url is not localhost",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if (
        args.start_page < 0
        or args.max_pages < 0
        or args.max_page_chars <= 0
        or args.max_output_tokens <= 0
        or args.requests_per_minute < 0
        or args.parallel_requests < 0
        or args.retries < 0
        or args.page_retries < 0
    ):
        raise SystemExit("numeric limits are invalid")
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
        print("dry-run only; add --execute to call the local model API")
        return 0
    if not is_local_base_url(args.base_url) and not args.accept_cost:
        raise SystemExit("non-local --base-url requires --accept-cost")
    api_key = os.environ.get(args.api_key_env)
    if args.parallel_requests:
        parallel_requests = args.parallel_requests
        slot_source = "command line"
    else:
        try:
            parallel_requests = fetch_lm_studio_parallel_slots(
                args.base_url,
                api_key,
                args.model,
                min(args.timeout, 15),
            )
            slot_source = "LM Studio"
        except (RuntimeError, ValueError, json.JSONDecodeError) as error:
            parallel_requests = 1
            slot_source = f"fallback ({error})"
    print(
        f"parallel page workers: {parallel_requests} [{slot_source}]",
        flush=True,
    )
    print(
        "structured response mode: "
        + ("non-streaming" if args.no_stream else "streaming with fallback"),
        flush=True,
    )
    rate_limiter = (
        RequestRateLimiter(args.requests_per_minute)
        if args.requests_per_minute
        else None
    )

    prepare_output(args.database, args.output)
    run_id = str(uuid.uuid4())
    completed = 0
    skipped = 0
    failed = 0
    interrupted = False
    base_digest = sha256(args.database)
    with closing(sqlite3.connect(args.output)) as connection:
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
        page_iterator = iter(enumerate(selected, start=1))
        futures: dict[Future, tuple[str, dict, int, int]] = {}

        def submit_next(executor: ThreadPoolExecutor) -> bool:
            nonlocal skipped
            for selected_index, page in page_iterator:
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
                    f"[{selected_index}/{len(selected)}] queued "
                    f"{page['title']} ({len(submitted)} chars)",
                    flush=True,
                )
                future = executor.submit(
                    extract_page_with_retries,
                    args.base_url,
                    api_key,
                    args.model,
                    page,
                    submitted,
                    verify=args.verify,
                    page_retries=args.page_retries,
                    rate_limiter=rate_limiter,
                    stream=not args.no_stream,
                    max_output_tokens=args.max_output_tokens,
                    retries=args.retries,
                    timeout=args.timeout,
                )
                futures[future] = (
                    page_parse_id,
                    page,
                    len(wikitext),
                    len(submitted),
                )
                return True
            return False

        def persist_future(future: Future) -> None:
            nonlocal completed, failed
            page_parse_id, page, content_chars, submitted_chars = futures.pop(
                future
            )
            try:
                payload, result = future.result()
                if result["page_relevance"] == "no_data":
                    page_status = "no_data"
                elif submitted_chars < content_chars:
                    page_status = "parsed_partial"
                else:
                    page_status = "parsed"
                with connection:
                    for candidate_index, candidate in enumerate(result["entities"]):
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
                            page_status,
                            payload.get("id"),
                            utc_now(),
                            page_parse_id,
                        ),
                    )
                completed += 1
                print(
                    f"  completed [{page['_sequence_index']}] "
                    f"{page['title']} ({page_status})",
                    flush=True,
                )
            except (
                RuntimeError,
                ValueError,
                json.JSONDecodeError,
                sqlite3.IntegrityError,
            ) as error:
                if isinstance(error, sqlite3.IntegrityError):
                    error = RuntimeError(
                        f"database rejected staged model output: {error}"
                    )
                with connection:
                    connection.execute(
                        """
                        UPDATE wikipedia_page_parse
                        SET status = 'error', error_text = ?, completed_at = ?
                        WHERE page_parse_id = ?
                        """,
                        (str(error), utc_now(), page_parse_id),
                    )
                failed += 1
                print(f"  error [{page['_sequence_index']}]: {error}", flush=True)

        try:
            with ThreadPoolExecutor(max_workers=parallel_requests) as executor:
                for _ in range(parallel_requests):
                    if not submit_next(executor):
                        break
                while futures:
                    finished, _ = wait(futures, return_when=FIRST_COMPLETED)
                    for future in sorted(
                        finished,
                        key=lambda item: futures[item][1]["_sequence_index"],
                    ):
                        persist_future(future)
                        submit_next(executor)
        except KeyboardInterrupt:
            interrupted = True
            for future in futures:
                future.cancel()
            print(
                "stopping; completed pages are committed and active pages may "
                "remain pending",
                flush=True,
            )
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
                            f"endpoint {chat_completions_url(args.base_url)}; "
                            f"parallel workers {parallel_requests} ({slot_source}); "
                            f"verification {'enabled' if args.verify else 'disabled'}; "
                            f"streaming {'disabled' if args.no_stream else 'enabled'}; "
                            f"page retries {args.page_retries}; "
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
