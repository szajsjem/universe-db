#!/usr/bin/env python3
"""Conservatively consolidate Wikipedia candidates in a copied SQLite DB.

The Wikipedia importer intentionally records one candidate per page mention.
This post-processing pass turns repeated mentions into a smaller review queue
without discarding the original page, wording, or evidence.  It never edits
the input database, which makes it safe to run while an importer is writing.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import unicodedata
import uuid


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / ".build" / "wikipedia-unverified.db"
DEFAULT_OUTPUT = ROOT / ".build" / "wikipedia-cleaned.db"
NORMAL_TEMPERATURE_K = Decimal("293.15")
NORMAL_PRESSURE_PA = Decimal("101325")
CHEMICAL_KINDS = {"molecule", "ion", "formula_unit", "complex"}
PHASE_FIELDS = {
    "phase_at_normal_conditions",
    "phase_at_room_temperature",
    "phase_at_stp",
    "physical_state_at_room_temperature",
    "standard_state",
}
MELTING_FIELDS = {"melting_point", "melting_temperature"}
BOILING_FIELDS = {"boiling_point", "boiling_temperature"}

SUBSCRIPT_TRANSLATION = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
SUPERSCRIPT_TRANSLATION = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-")
PHASE_SUFFIX_RE = re.compile(
    r"(?:\s+|[-,])(?:gas(?:eous)?|vapou?r|liquid|solid|aqueous)(?:\s+phase)?$",
    re.IGNORECASE,
)
PAREN_PHASE_RE = re.compile(
    r"\s*\((?:g|l|s|aq|gas|vapou?r|liquid|solid|aqueous)\)\s*$",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)")


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    candidate_kind: str
    name: str
    formula: str | None
    electric_charge: int | None
    atomic_number: int | None
    existing_entity_id: str | None
    proposed_id: str | None
    confidence: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class CleanupPlan:
    groups: tuple[tuple[str, ...], ...]
    kind_corrections: dict[str, tuple[str, int | None, str]]

    @property
    def merged_candidates(self) -> int:
        return sum(len(group) - 1 for group in self.groups)


class UnionFind:
    def __init__(self, values: list[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        root = value
        while self.parent[root] != root:
            root = self.parent[root]
        while value != root:
            parent = self.parent[value]
            self.parent[value] = root
            value = parent
        return root

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().strip()
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def identity_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip()
    value = PAREN_PHASE_RE.sub("", value)
    value = PHASE_SUFFIX_RE.sub("", value)
    return normalize_text(value)


def normalize_formula(value: str | None) -> str | None:
    if value is None:
        return None
    value = unicodedata.normalize("NFKC", value).translate(SUBSCRIPT_TRANSLATION)
    value = value.translate(SUPERSCRIPT_TRANSLATION)
    value = re.sub(r"\s+", "", value)
    return value or None


def formula_charge(value: str | None) -> int | None:
    """Read only unambiguous terminal charge notation.

    A bare terminal sign is always +/-1.  A magnitude is accepted when it is
    separated by ^/space, enclosed in parentheses, follows a closing bracket,
    or belongs to a single-element ion (Al3+).  This avoids reading NH4+ as +4.
    """

    if value is None:
        return None
    raw = unicodedata.normalize("NFKC", value).translate(SUBSCRIPT_TRANSLATION)
    raw = raw.translate(SUPERSCRIPT_TRANSLATION).strip()
    match = re.search(r"(?:\s+|\^\{?)(\d+)([+-])\}?$", raw)
    if match:
        magnitude, sign = match.groups()
        return int(magnitude) * (1 if sign == "+" else -1)
    match = re.search(r"\^\{?([+-])\}?$", raw)
    if match:
        return 1 if match.group(1) == "+" else -1
    formula = normalize_formula(raw)
    if not formula:
        return None
    match = re.search(r"\((\d+)([+-])\)$", formula)
    if match:
        magnitude, sign = match.groups()
        return int(magnitude) * (1 if sign == "+" else -1)
    match = re.search(r"(?:\^|\])([0-9]+)([+-])$", formula)
    if match:
        magnitude, sign = match.groups()
        return int(magnitude) * (1 if sign == "+" else -1)
    match = re.fullmatch(r"[A-Z][a-z]?(\d+)([+-])", formula)
    if match:
        magnitude, sign = match.groups()
        return int(magnitude) * (1 if sign == "+" else -1)
    if formula.endswith("+"):
        return 1
    if formula.endswith("-"):
        return -1
    return None


def corrected_identity(candidate: Candidate) -> tuple[str, int | None, str | None]:
    charge = candidate.electric_charge
    kind = candidate.candidate_kind
    reason = None
    if kind not in CHEMICAL_KINDS:
        return kind, charge, reason
    parsed_charge = formula_charge(candidate.formula)
    if charge is None and parsed_charge is not None:
        charge = parsed_charge
    if kind == "molecule" and charge not in (None, 0):
        kind = "ion"
        reason = "charged molecule reclassified as ion"
    return kind, charge, reason


def load_candidates(connection: sqlite3.Connection) -> list[Candidate]:
    aliases: dict[str, list[str]] = defaultdict(list)
    for candidate_id, value in connection.execute(
        "SELECT candidate_id, value FROM unverified_candidate_alias"
    ):
        aliases[candidate_id].append(value)
    rows = connection.execute(
        """
        SELECT candidate_id, candidate_kind, name, formula, electric_charge,
               atomic_number, existing_entity_id, proposed_id, confidence
        FROM unverified_entity_candidate
        WHERE candidate_kind IN (
            'element', 'molecule', 'ion', 'formula_unit', 'complex'
        )
        ORDER BY candidate_id
        """
    )
    return [
        Candidate(*row, tuple(aliases[row[0]]))
        for row in rows
    ]


def compatible_formulas(left: Candidate, right: Candidate) -> bool:
    left_formula = normalize_formula(left.formula)
    right_formula = normalize_formula(right.formula)
    if not left_formula or not right_formula:
        return True
    return left_formula.casefold() == right_formula.casefold()


def candidate_names(candidate: Candidate) -> set[str]:
    # Model-produced aliases are useful output, but not strong enough to join
    # identities by themselves (for example, an isotopologue may list the
    # parent compound as an alias).  Phase wording is normalized on the
    # primary name, so "water vapour" still joins "water" safely.
    name = identity_name(candidate.name)
    return {name} if name else set()


def name_is_formula(candidate: Candidate) -> bool:
    formula = normalize_formula(candidate.formula)
    return bool(formula and identity_name(candidate.name) == normalize_text(formula))


def dominant_formula_outliers(candidates: list[Candidate]) -> set[tuple[str, str]]:
    """Return same-name outlier pairs safe enough to absorb.

    This handles one-off extraction/OCR variants such as water H20 when at
    least three other mentions agree on H2O.  Requiring a 3:1 consensus keeps
    same-name families with genuinely different formulae separate.
    """

    by_name: dict[tuple[str, str], list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        kind, charge, _ = corrected_identity(candidate)
        name = identity_name(candidate.name)
        if name:
            by_name[(kind, name)].append(candidate)
    allowed: set[tuple[str, str]] = set()
    for values in by_name.values():
        counts = Counter(
            normalize_formula(value.formula).casefold()
            for value in values
            if normalize_formula(value.formula)
        )
        if not counts:
            continue
        dominant, count = counts.most_common(1)[0]
        if count < 3:
            continue
        for value in values:
            formula = normalize_formula(value.formula)
            if not formula:
                continue
            outlier = formula.casefold()
            zero_o_equivalent = outlier.replace("0", "o") == dominant.replace(
                "0", "o"
            )
            if outlier != dominant and counts[outlier] == 1 and zero_o_equivalent:
                allowed.add((value.candidate_id, dominant))
    return allowed


def build_plan(connection: sqlite3.Connection) -> CleanupPlan:
    candidates = load_candidates(connection)
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    union = UnionFind(list(by_id))
    corrections: dict[str, tuple[str, int | None, str]] = {}
    identities: dict[str, tuple[str, int | None]] = {}
    for candidate in candidates:
        kind, charge, reason = corrected_identity(candidate)
        # A neutral molecule is frequently emitted with NULL rather than 0.
        # They are equivalent for identity matching; standalone rows retain
        # NULL unless another correction is actually required.
        identity_charge = 0 if kind == "molecule" and charge is None else charge
        identities[candidate.candidate_id] = (kind, identity_charge)
        if reason or charge != candidate.electric_charge:
            corrections[candidate.candidate_id] = (
                kind,
                charge,
                reason or "charge parsed from formula",
            )

    # Existing authoritative mappings are the strongest possible identity key.
    indexes: list[dict[tuple[object, ...], list[str]]] = [defaultdict(list) for _ in range(3)]
    outliers = dominant_formula_outliers(candidates)
    for candidate in candidates:
        kind, charge = identities[candidate.candidate_id]
        if candidate.existing_entity_id:
            indexes[0][("existing", candidate.existing_entity_id)].append(candidate.candidate_id)
        if candidate.candidate_kind == "element" and candidate.atomic_number:
            indexes[1][("element", candidate.atomic_number)].append(candidate.candidate_id)
        for name in candidate_names(candidate):
            indexes[2][("name", kind, charge, name)].append(candidate.candidate_id)
    for index_number, index in enumerate(indexes):
        for values in index.values():
            if len(values) < 2:
                continue
            for left_id in values:
                for right_id in values:
                    if left_id >= right_id:
                        continue
                    left = by_id[left_id]
                    right = by_id[right_id]
                    left_kind, left_charge = identities[left_id]
                    right_kind, right_charge = identities[right_id]
                    if left_kind != right_kind or left_charge != right_charge:
                        continue
                    compatible = compatible_formulas(left, right)
                    if not compatible and index_number == 2:
                        left_formula = normalize_formula(left.formula)
                        right_formula = normalize_formula(right.formula)
                        compatible = bool(
                            (left_id, (right_formula or "").casefold()) in outliers
                            or (right_id, (left_formula or "").casefold()) in outliers
                        )
                    if compatible or index_number in (0, 1):
                        union.union(left_id, right_id)

    # Formula-only labels such as "H2O" (and consensus-backed H20) may join a
    # well-established named cluster. This bridge is enabled only when at
    # least three candidates agree on one formula and all non-formula primary
    # names in the bucket resolve to one identity, so it cannot join isomers.
    formula_buckets: dict[tuple[str, int | None, str], list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        formula = normalize_formula(candidate.formula)
        if not formula:
            continue
        kind, charge = identities[candidate.candidate_id]
        formula_buckets[(kind, charge, formula.casefold().replace("0", "o"))].append(
            candidate
        )
    for values in formula_buckets.values():
        exact_formulas = Counter(
            normalize_formula(candidate.formula).casefold()  # type: ignore[union-attr]
            for candidate in values
        )
        dominant_formula, dominant_count = exact_formulas.most_common(1)[0]
        named = {
            identity_name(candidate.name)
            for candidate in values
            if not name_is_formula(candidate)
        }
        if dominant_count < 3 or len(named) != 1:
            continue
        anchors = [
            candidate
            for candidate in values
            if not name_is_formula(candidate)
            and (normalize_formula(candidate.formula) or "").casefold()
            == dominant_formula
        ]
        if not anchors:
            continue
        anchor_id = anchors[0].candidate_id
        for candidate in values:
            if not name_is_formula(candidate):
                continue
            formula = normalize_formula(candidate.formula)
            if formula and (
                formula.casefold() == dominant_formula
                or exact_formulas[formula.casefold()] == 1
            ):
                union.union(anchor_id, candidate.candidate_id)

    grouped: dict[str, list[str]] = defaultdict(list)
    for candidate_id in by_id:
        grouped[union.find(candidate_id)].append(candidate_id)
    groups = tuple(
        tuple(sorted(values))
        for values in grouped.values()
        if len(values) > 1
    )
    return CleanupPlan(tuple(sorted(groups)), corrections)


def ensure_cleanup_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS wikipedia_candidate_cleanup_run (
            cleanup_run_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            normal_temperature_k TEXT NOT NULL,
            normal_pressure_pa TEXT NOT NULL,
            merged_candidates INTEGER NOT NULL CHECK (merged_candidates >= 0),
            corrected_kinds INTEGER NOT NULL CHECK (corrected_kinds >= 0),
            inferred_phases INTEGER NOT NULL CHECK (inferred_phases >= 0)
        ) STRICT;

        CREATE TABLE IF NOT EXISTS wikipedia_candidate_mention (
            original_candidate_id TEXT PRIMARY KEY,
            canonical_candidate_id TEXT NOT NULL
                REFERENCES unverified_entity_candidate(candidate_id) ON DELETE CASCADE,
            page_parse_id TEXT NOT NULL
                REFERENCES wikipedia_page_parse(page_parse_id) ON DELETE CASCADE,
            original_kind TEXT NOT NULL,
            original_name TEXT NOT NULL,
            original_formula TEXT,
            original_electric_charge INTEGER,
            original_evidence_text TEXT NOT NULL,
            merge_reason TEXT NOT NULL,
            cleanup_run_id TEXT NOT NULL
                REFERENCES wikipedia_candidate_cleanup_run(cleanup_run_id)
        ) STRICT;

        CREATE TABLE IF NOT EXISTS unverified_candidate_derived_fact (
            derived_fact_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL
                REFERENCES unverified_entity_candidate(candidate_id) ON DELETE CASCADE,
            field_key TEXT NOT NULL,
            value_text TEXT NOT NULL,
            normal_temperature_k TEXT NOT NULL,
            normal_pressure_pa TEXT NOT NULL,
            method TEXT NOT NULL,
            source_candidate_fact_ids_json TEXT NOT NULL,
            cleanup_run_id TEXT NOT NULL
                REFERENCES wikipedia_candidate_cleanup_run(cleanup_run_id),
            UNIQUE (
                candidate_id, field_key,
                normal_temperature_k, normal_pressure_pa
            )
        ) STRICT;
        """
    )


def survivor_score(connection: sqlite3.Connection, candidate: Candidate) -> tuple[object, ...]:
    child_count = sum(
        connection.execute(
            f"SELECT count(*) FROM {table} WHERE candidate_id = ?",
            (candidate.candidate_id,),
        ).fetchone()[0]
        for table in (
            "unverified_candidate_alias",
            "unverified_candidate_composition",
            "unverified_candidate_fact",
            "unverified_candidate_relation",
        )
    )
    return (
        candidate.existing_entity_id is not None,
        candidate.proposed_id is not None,
        {"low": 0, "medium": 1, "high": 2}[candidate.confidence],
        candidate.formula is not None,
        child_count,
        candidate.candidate_id,
    )


def choose_canonical_text(values: list[str], *, phase_sensitive: bool = False) -> str:
    normalized = identity_name if phase_sensitive else normalize_text
    counts = Counter(normalized(value) for value in values if normalized(value))
    best_key = max(counts, key=lambda key: (counts[key], -len(key), key))
    spellings = Counter(value.strip() for value in values if normalized(value) == best_key)
    return max(
        spellings,
        key=lambda value: (
            spellings[value],
            value[:1].islower(),
            -len(value),
            value,
        ),
    )


def next_index(connection: sqlite3.Connection, table: str, column: str, candidate_id: str) -> int:
    return connection.execute(
        f"SELECT COALESCE(MAX({column}) + 1, 0) FROM {table} WHERE candidate_id = ?",
        (candidate_id,),
    ).fetchone()[0]


def move_indexed_children(
    connection: sqlite3.Connection,
    table: str,
    index_column: str,
    source_id: str,
    target_id: str,
) -> None:
    index = next_index(connection, table, index_column, target_id)
    rows = connection.execute(
        f"SELECT {index_column} FROM {table} WHERE candidate_id = ? ORDER BY {index_column}",
        (source_id,),
    ).fetchall()
    for (old_index,) in rows:
        connection.execute(
            f"UPDATE {table} SET candidate_id = ?, {index_column} = ? "
            f"WHERE candidate_id = ? AND {index_column} = ?",
            (target_id, index, source_id, old_index),
        )
        index += 1


def add_alias(connection: sqlite3.Connection, candidate_id: str, value: str | None) -> None:
    if not value or not value.strip():
        return
    normalized = normalize_text(value)
    existing = connection.execute(
        "SELECT value FROM unverified_candidate_alias WHERE candidate_id = ?",
        (candidate_id,),
    ).fetchall()
    if any(normalize_text(row[0]) == normalized for row in existing):
        return
    index = next_index(
        connection,
        "unverified_candidate_alias",
        "alias_index",
        candidate_id,
    )
    connection.execute(
        """
        INSERT INTO unverified_candidate_alias(candidate_id, alias_index, value)
        VALUES (?, ?, ?)
        """,
        (candidate_id, index, value.strip()),
    )


def merge_group(
    connection: sqlite3.Connection,
    candidate_ids: tuple[str, ...],
    corrections: dict[str, tuple[str, int | None, str]],
    cleanup_run_id: str,
) -> str:
    placeholders = ",".join("?" for _ in candidate_ids)
    rows = connection.execute(
        f"""
        SELECT candidate_id, candidate_kind, name, formula, electric_charge,
               atomic_number, existing_entity_id, proposed_id, confidence
        FROM unverified_entity_candidate
        WHERE candidate_id IN ({placeholders})
        """,
        candidate_ids,
    ).fetchall()
    aliases = defaultdict(list)
    for candidate_id, value in connection.execute(
        f"SELECT candidate_id, value FROM unverified_candidate_alias "
        f"WHERE candidate_id IN ({placeholders})",
        candidate_ids,
    ):
        aliases[candidate_id].append(value)
    candidates = [Candidate(*row, tuple(aliases[row[0]])) for row in rows]
    survivor = max(candidates, key=lambda candidate: survivor_score(connection, candidate))
    kinds_and_charges = [corrected_identity(candidate)[:2] for candidate in candidates]
    canonical_kind = Counter(value[0] for value in kinds_and_charges).most_common(1)[0][0]
    charges = [value[1] for value in kinds_and_charges if value[1] is not None]
    canonical_charge = Counter(charges).most_common(1)[0][0] if charges else None
    canonical_name = choose_canonical_text(
        [candidate.name for candidate in candidates], phase_sensitive=True
    )
    formulas = [
        candidate.formula
        for candidate in candidates
        if normalize_formula(candidate.formula)
    ]
    canonical_formula = choose_canonical_text(formulas) if formulas else None

    connection.execute(
        """
        UPDATE unverified_entity_candidate
        SET candidate_kind = ?, name = ?, formula = ?, electric_charge = ?
        WHERE candidate_id = ?
        """,
        (
            canonical_kind,
            canonical_name,
            canonical_formula,
            canonical_charge,
            survivor.candidate_id,
        ),
    )
    for candidate in candidates:
        row = connection.execute(
            """
            SELECT page_parse_id, candidate_kind, name, formula,
                   electric_charge, evidence_text
            FROM unverified_entity_candidate WHERE candidate_id = ?
            """,
            (candidate.candidate_id,),
        ).fetchone()
        # The survivor row has already been canonicalized; use the loaded
        # values for its original spelling and type in the audit record.
        original_kind = candidate.candidate_kind
        original_name = candidate.name
        original_formula = candidate.formula
        original_charge = candidate.electric_charge
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
                candidate.candidate_id,
                survivor.candidate_id,
                row[0],
                original_kind,
                original_name,
                original_formula,
                original_charge,
                row[5],
                (
                    "same authoritative mapping or compatible primary-name identity"
                    + (
                        f"; {corrections[candidate.candidate_id][2]}"
                        if candidate.candidate_id in corrections
                        else ""
                    )
                ),
                cleanup_run_id,
            ),
        )
        if candidate.candidate_id == survivor.candidate_id:
            continue
        add_alias(connection, survivor.candidate_id, candidate.name)
        if (
            candidate.formula
            and normalize_formula(candidate.formula)
            != normalize_formula(canonical_formula)
        ):
            add_alias(connection, survivor.candidate_id, candidate.formula)
        move_indexed_children(
            connection,
            "unverified_candidate_alias",
            "alias_index",
            candidate.candidate_id,
            survivor.candidate_id,
        )
        move_indexed_children(
            connection,
            "unverified_candidate_composition",
            "component_index",
            candidate.candidate_id,
            survivor.candidate_id,
        )
        move_indexed_children(
            connection,
            "unverified_candidate_fact",
            "fact_index",
            candidate.candidate_id,
            survivor.candidate_id,
        )
        move_indexed_children(
            connection,
            "unverified_candidate_relation",
            "relation_index",
            candidate.candidate_id,
            survivor.candidate_id,
        )
        connection.execute(
            "DELETE FROM unverified_entity_candidate WHERE candidate_id = ?",
            (candidate.candidate_id,),
        )
    return survivor.candidate_id


def decimal_temperature(
    value_text: str | None,
    fallback_text: str | None,
    unit: str | None,
) -> Decimal | None:
    raw = value_text
    if raw is None:
        raw = fallback_text
        if raw is None:
            return None
        numbers = NUMBER_RE.findall(raw)
        if len(numbers) != 1:
            return None
        raw = numbers[0]
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    normalized_unit = unicodedata.normalize("NFKC", unit or "").casefold().replace(" ", "")
    if normalized_unit in {"k", "kelvin", "kelvins"}:
        return value
    if normalized_unit in {"c", "°c", "degc", "celsius"}:
        return value + Decimal("273.15")
    if normalized_unit in {"f", "°f", "degf", "fahrenheit"}:
        return (value - Decimal(32)) * Decimal(5) / Decimal(9) + Decimal("273.15")
    return None


def pressure_is_normal(
    connection: sqlite3.Connection,
    fact_id: str,
    normal_pressure: Decimal,
) -> bool:
    conditions = connection.execute(
        """
        SELECT value_decimal_text, value_text, unit_text
        FROM unverified_candidate_fact_condition
        WHERE candidate_fact_id = ? AND lower(quantity_kind) = 'pressure'
        """,
        (fact_id,),
    ).fetchall()
    for decimal_text, text_value, unit in conditions:
        raw = decimal_text
        if raw is None and text_value:
            numbers = NUMBER_RE.findall(text_value)
            if len(numbers) == 1:
                raw = numbers[0]
        if raw is None:
            return False
        try:
            pressure = Decimal(raw)
        except InvalidOperation:
            return False
        normalized_unit = normalize_text(unit or "")
        scale = {
            "pa": Decimal(1),
            "pascal": Decimal(1),
            "kpa": Decimal(1000),
            "bar": Decimal(100000),
            "atm": Decimal(101325),
        }.get(normalized_unit)
        if scale is None:
            return False
        pressure *= scale
        if abs(pressure - normal_pressure) / normal_pressure > Decimal("0.05"):
            return False
    return True


def has_explicit_phase(connection: sqlite3.Connection, candidate_id: str) -> bool:
    rows = connection.execute(
        """
        SELECT field_key, value_text
        FROM unverified_candidate_fact
        WHERE candidate_id = ?
        """,
        (candidate_id,),
    )
    for field_key, value_text in rows:
        if normalize_text(field_key).replace(" ", "_") not in PHASE_FIELDS:
            continue
        value = normalize_text(value_text or "")
        if any(phase in value.split() for phase in ("solid", "liquid", "gas", "gaseous")):
            return True
    return False


def infer_phase(
    connection: sqlite3.Connection,
    candidate_id: str,
    temperature: Decimal,
    pressure: Decimal,
) -> tuple[str, list[str]] | None:
    if has_explicit_phase(connection, candidate_id):
        return None
    melting: list[tuple[Decimal, str]] = []
    boiling: list[tuple[Decimal, str]] = []
    rows = connection.execute(
        """
        SELECT candidate_fact_id, field_key, value_decimal_text,
               value_text, unit_text
        FROM unverified_candidate_fact
        WHERE candidate_id = ?
        """,
        (candidate_id,),
    )
    for fact_id, field_key, decimal_text, text_value, unit in rows:
        key = normalize_text(field_key).replace(" ", "_")
        target = melting if key in MELTING_FIELDS else boiling if key in BOILING_FIELDS else None
        if target is None or not pressure_is_normal(connection, fact_id, pressure):
            continue
        value = decimal_temperature(decimal_text, text_value, unit)
        if value is not None:
            target.append((value, fact_id))
    melting_values = [value for value, _ in melting]
    boiling_values = [value for value, _ in boiling]
    if melting_values and min(melting_values) > temperature:
        if boiling_values and min(boiling_values) <= temperature:
            return None
        return "solid", [fact_id for _, fact_id in melting + boiling]
    if boiling_values and max(boiling_values) < temperature:
        if melting_values and max(melting_values) >= temperature:
            return None
        return "gas", [fact_id for _, fact_id in melting + boiling]
    if (
        melting_values
        and boiling_values
        and max(melting_values) < temperature
        and min(boiling_values) > temperature
    ):
        return "liquid", [fact_id for _, fact_id in melting + boiling]
    return None


def add_phase_inferences(
    connection: sqlite3.Connection,
    cleanup_run_id: str,
    temperature: Decimal,
    pressure: Decimal,
) -> int:
    inserted = 0
    candidate_ids = [
        row[0]
        for row in connection.execute(
            "SELECT candidate_id FROM unverified_entity_candidate "
            "WHERE candidate_kind = 'element' ORDER BY candidate_id"
        )
    ]
    for candidate_id in candidate_ids:
        result = infer_phase(connection, candidate_id, temperature, pressure)
        if result is None:
            continue
        phase, fact_ids = result
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO unverified_candidate_derived_fact(
                derived_fact_id, candidate_id, field_key, value_text,
                normal_temperature_k, normal_pressure_pa, method,
                source_candidate_fact_ids_json, cleanup_run_id
            ) VALUES (?, ?, 'phase_at_normal_conditions', ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                candidate_id,
                phase,
                str(temperature),
                str(pressure),
                "Compared source-extracted melting/boiling temperatures with "
                "the configured normal temperature; pressure-specific facts "
                "were accepted only within 5% of the configured pressure.",
                json.dumps(sorted(fact_ids)),
                cleanup_run_id,
            ),
        )
        inserted += cursor.rowcount
    return inserted


def apply_cleanup(
    connection: sqlite3.Connection,
    plan: CleanupPlan,
    temperature: Decimal = NORMAL_TEMPERATURE_K,
    pressure: Decimal = NORMAL_PRESSURE_PA,
) -> tuple[int, int, int]:
    ensure_cleanup_schema(connection)
    cleanup_run_id = str(uuid.uuid4())
    connection.execute(
        """
        INSERT INTO wikipedia_candidate_cleanup_run(
            cleanup_run_id, created_at, normal_temperature_k,
            normal_pressure_pa, merged_candidates, corrected_kinds,
            inferred_phases
        ) VALUES (?, ?, ?, ?, 0, 0, 0)
        """,
        (cleanup_run_id, utc_now(), str(temperature), str(pressure)),
    )
    merged = 0
    merged_ids: set[str] = set()
    for group in plan.groups:
        surviving_group = tuple(
            candidate_id
            for candidate_id in group
            if connection.execute(
                "SELECT 1 FROM unverified_entity_candidate WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
        )
        if len(surviving_group) > 1:
            survivor = merge_group(
                connection, surviving_group, plan.kind_corrections, cleanup_run_id
            )
            merged += len(surviving_group) - 1
            merged_ids.update(surviving_group)
            merged_ids.discard(survivor)

    for candidate_id, (kind, charge, reason) in plan.kind_corrections.items():
        if candidate_id in merged_ids:
            continue
        row = connection.execute(
            """
            SELECT page_parse_id, candidate_kind, name, formula,
                   electric_charge, evidence_text
            FROM unverified_entity_candidate WHERE candidate_id = ?
            """,
            (candidate_id,),
        ).fetchone()
        if row is None or (row[1] == kind and row[4] == charge):
            continue
        connection.execute(
            """
            UPDATE unverified_entity_candidate
            SET candidate_kind = ?, electric_charge = ?
            WHERE candidate_id = ?
            """,
            (kind, charge, candidate_id),
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
                candidate_id,
                candidate_id,
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
                reason,
                cleanup_run_id,
            ),
        )
    # Count corrected input mentions, including those absorbed by a merge.
    corrected = len(plan.kind_corrections)
    inferred = add_phase_inferences(connection, cleanup_run_id, temperature, pressure)
    connection.execute(
        """
        UPDATE wikipedia_candidate_cleanup_run
        SET merged_candidates = ?, corrected_kinds = ?, inferred_phases = ?
        WHERE cleanup_run_id = ?
        """,
        (merged, corrected, inferred, cleanup_run_id),
    )
    return merged, corrected, inferred


def validate_input(connection: sqlite3.Connection) -> None:
    required = {
        "unverified_entity_candidate",
        "unverified_candidate_alias",
        "unverified_candidate_composition",
        "unverified_candidate_fact",
        "unverified_candidate_fact_condition",
        "unverified_candidate_relation",
        "wikipedia_page_parse",
    }
    present = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type = 'table'"
        )
    }
    missing = sorted(required - present)
    if missing:
        raise RuntimeError(f"not a Wikipedia candidate database; missing: {', '.join(missing)}")


def snapshot_database(source: Path, destination: Path) -> None:
    destination = destination.resolve()
    source = source.resolve()
    if source == destination:
        raise ValueError(
            "input and output must differ; in-place cleanup is intentionally "
            "unsupported"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="wikipedia-cleanup-", dir=destination.parent
    ) as directory:
        staged = Path(directory) / destination.name
        source_connection = sqlite3.connect(
            f"file:{source.as_posix()}?mode=ro", uri=True, timeout=30
        )
        target_connection = sqlite3.connect(staged)
        try:
            source_connection.backup(target_connection)
        finally:
            target_connection.close()
            source_connection.close()
        os.replace(staged, destination)


def parse_decimal_argument(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise argparse.ArgumentTypeError(f"invalid decimal: {value}") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", nargs="?", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="write the cleaned snapshot; otherwise only print a plan",
    )
    parser.add_argument(
        "--normal-temperature-k",
        type=parse_decimal_argument,
        default=NORMAL_TEMPERATURE_K,
        help="normal-condition temperature in kelvin (default: 293.15)",
    )
    parser.add_argument(
        "--normal-pressure-pa",
        type=parse_decimal_argument,
        default=NORMAL_PRESSURE_PA,
        help="normal-condition pressure in pascals (default: 101325)",
    )
    return parser.parse_args()


def print_plan(plan: CleanupPlan) -> None:
    kind_counts = Counter(value[0] for value in plan.kind_corrections.values())
    print(f"candidate groups to consolidate: {len(plan.groups)}")
    print(f"candidate rows to merge: {plan.merged_candidates}")
    print(
        "candidate rows needing kind/charge correction: "
        f"{len(plan.kind_corrections)}"
    )
    if kind_counts:
        print(
            "corrected target kinds: "
            + ", ".join(
                f"{key}={value}" for key, value in sorted(kind_counts.items())
            )
        )


def main() -> None:
    arguments = parse_args()
    database = arguments.database.resolve()
    if not database.exists():
        raise SystemExit(f"database does not exist: {database}")
    if not arguments.execute:
        with sqlite3.connect(
            f"file:{database.as_posix()}?mode=ro", uri=True
        ) as connection:
            # Pin all planning queries to one view while the importer writes.
            connection.execute("BEGIN")
            validate_input(connection)
            plan = build_plan(connection)
            print_plan(plan)
        print("plan only; pass --execute to write a cleaned snapshot")
        return

    output = arguments.output.resolve()
    snapshot_database(database, output)
    with sqlite3.connect(output) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        validate_input(connection)
        # Build the actionable plan from the snapshot itself. New rows written
        # to the live importer DB after backup starts cannot race this plan.
        plan = build_plan(connection)
        print_plan(plan)
        with connection:
            result = apply_cleanup(
                connection,
                plan,
                arguments.normal_temperature_k,
                arguments.normal_pressure_pa,
            )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        if integrity != "ok" or foreign_keys:
            raise RuntimeError(
                "cleaned database validation failed: "
                f"integrity={integrity}, foreign_keys={foreign_keys[:5]}"
            )
    print(f"wrote {output}")
    print(f"merged={result[0]} corrected={result[1]} inferred_phases={result[2]}")


if __name__ == "__main__":
    main()
