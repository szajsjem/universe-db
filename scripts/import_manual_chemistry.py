#!/usr/bin/env python3
"""Load cited, hand-selected research into existing unverified staging tables only.

No network access, schema changes, reviewed promotion, or fabricated Wikipedia
parse records. Input files are immutable dated research slices; replay is a no-op.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from build_db import write_release_files

ROOT = Path(__file__).resolve().parents[1]
MODEL = "Codex browser-assisted manual source research; pending human review"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def formula_composition(formula: str) -> dict[str, int]:
    """Admit elemental formulas and parenthesized groups, not hydrate/complex notation."""
    tokens = re.findall(r"[A-Z][a-z]?|[1-9][0-9]*|[()]", formula)
    if not tokens or "".join(tokens) != formula:
        raise ValueError(f"Unsupported plain formula: {formula}")
    cursor = 0

    def group(depth: int = 0) -> Counter[str]:
        nonlocal cursor
        if depth > 8:
            raise ValueError("Formula nesting limit exceeded")
        result: Counter[str] = Counter()
        while cursor < len(tokens):
            token = tokens[cursor]
            cursor += 1
            if token == ")":
                if depth == 0 or not result:
                    raise ValueError(f"Unmatched or empty formula group: {formula}")
                return result
            if token == "(":
                component = group(depth + 1)
            elif token[0].isupper():
                component = Counter({token: 1})
            else:
                raise ValueError(f"Unexpected formula coefficient: {formula}")
            multiplier = 1
            if cursor < len(tokens) and tokens[cursor].isdigit():
                multiplier = int(tokens[cursor])
                cursor += 1
            for symbol, count in component.items():
                result[symbol] += count * multiplier
                if result[symbol] > 1_000_000:
                    raise ValueError("Formula atom-count limit exceeded")
        if depth:
            raise ValueError(f"Unclosed formula group: {formula}")
        return result

    return dict(group())


def load_slice(path: Path, db: sqlite3.Connection) -> dict:
    data = json.loads(path.read_text(encoding="utf8"))
    if data["schema_version"] != 1 or not data["entries"]:
        raise ValueError(f"Invalid or empty research slice: {path}")
    date.fromisoformat(data["retrieved_on"])
    symbols = {row[0] for row in db.execute("SELECT symbol FROM element")}
    seen = set()
    for entry in data["entries"]:
        identity = entry["id"]
        if not re.fullmatch(r"chem:[a-z0-9_\-]+", identity) or identity in seen:
            raise ValueError(f"Invalid/duplicate identity in {path}: {identity}")
        seen.add(identity)
        if entry["kind"] not in {"molecule", "formula_unit"}:
            raise ValueError(f"Unsupported compound kind: {identity}")
        if type(entry["charge"]) is not int:
            raise ValueError(f"Missing integral charge: {identity}")
        composition = entry["composition"]
        if any(
            symbol not in symbols or type(count) is not int or count <= 0
            for symbol, count in composition.items()
        ):
            raise ValueError(f"Invalid elemental composition: {identity}")
        if formula_composition(entry["formula"]) != composition:
            raise ValueError(f"Formula/composition disagreement: {identity}")
        existing = db.execute(
            "SELECT formula, electric_charge FROM chemical_species WHERE entity_id = ?",
            (identity,),
        ).fetchone()
        if existing is not None:
            if (
                formula_composition(existing[0]) != composition
                or existing[1] != entry["charge"]
            ):
                raise ValueError(f"Reviewed species identity disagreement: {identity}")
        elif db.execute(
            "SELECT 1 FROM entity WHERE entity_id = ?", (identity,)
        ).fetchone():
            raise ValueError(
                f"Proposed compound ID belongs to another entity: {identity}"
            )
        if not entry["name"] or not entry["usefulness"]:
            raise ValueError(f"Missing identity or proposed usefulness: {identity}")
        for candidate in entry.get("existing_candidate_ids", []):
            row = db.execute(
                "SELECT formula, electric_charge FROM unverified_entity_candidate WHERE candidate_id = ?",
                (candidate,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown existing candidate: {candidate}")
            if row[0] and formula_composition(row[0]) != composition:
                raise ValueError(f"Candidate composition disagreement: {candidate}")
            if row[1] is not None and row[1] != entry["charge"]:
                raise ValueError(f"Candidate charge disagreement: {candidate}")
        keys = set()
        for fact in entry["facts"]:
            if (
                not fact["key"]
                or fact["key"] in keys
                or not isinstance(fact["value"], str)
                or not fact["value"]
            ):
                raise ValueError(f"Invalid/duplicate textual fact: {identity}")
            keys.add(fact["key"])
            if not fact["sources"]:
                raise ValueError(f"Unsourced fact: {identity}/{fact['key']}")
            for source in fact["sources"]:
                parsed = urlparse(source["url"])
                if parsed.scheme != "https" or not parsed.netloc:
                    raise ValueError(f"Invalid source URL: {source['url']}")
                if not all(
                    source.get(key)
                    for key in (
                        "title",
                        "supporting_text",
                        "license_basis",
                        "retrieved_on",
                    )
                ):
                    raise ValueError(f"Incomplete source provenance: {identity}")
                date.fromisoformat(source["retrieved_on"])
        formula_facts = [f for f in entry["facts"] if f["key"] == "formula"]
        if len(formula_facts) != 1 or formula_facts[0]["value"] != entry["formula"]:
            raise ValueError(f"A cited matching formula fact is required: {identity}")
    return data


def insert_slice(
    db: sqlite3.Connection, path: Path, data: dict, base_digest: str
) -> None:
    run_id = f"manual-chemistry:{path.stem}:{digest(path)}"
    if db.execute("SELECT 1 FROM research_run WHERE run_id = ?", (run_id,)).fetchone():
        return
    prefix = f"manual-chemistry:{path.stem}:"
    if db.execute(
        "SELECT 1 FROM research_run WHERE substr(run_id, 1, ?) = ?",
        (len(prefix), prefix),
    ).fetchone():
        raise ValueError(
            f"Existing dated slice changed: publish a newly named revision of {path.name}"
        )
    timestamp = data["retrieved_on"] + "T00:00:00Z"
    notes = {
        "input_path": str(path.relative_to(ROOT)),
        "input_sha256": digest(path),
        "schema_version": 1,
        "review_status": "pending_human_review",
        "date_precision": "day; midnight is normalized metadata, not a claimed retrieval instant",
        "identity_policy": "No reviewed entities or Wikipedia candidates created; linked candidates are research leads",
        "gameplay_proposals": {e["id"]: e["usefulness"] for e in data["entries"]},
    }
    db.execute(
        """INSERT INTO research_run(run_id, started_at, completed_at, model,
           base_database_sha256, requested_scopes, status, notes)
           VALUES (?, ?, ?, ?, ?, ?, 'completed', ?)""",
        (
            run_id,
            timestamp,
            timestamp,
            MODEL,
            base_digest,
            data["scope"],
            json.dumps(notes, sort_keys=True),
        ),
    )
    for entry in sorted(data["entries"], key=lambda e: e["id"]):
        existing = db.execute(
            "SELECT entity_id FROM entity WHERE entity_id = ?", (entry["id"],)
        ).fetchone()
        existing_id = existing[0] if existing else None
        facts = [
            {
                "key": "compound_identity",
                "value": json.dumps(
                    {
                        key: entry[key]
                        for key in (
                            "id",
                            "name",
                            "formula",
                            "kind",
                            "charge",
                            "composition",
                            "aliases",
                        )
                    }
                    | {
                        "existing_candidate_ids": entry.get(
                            "existing_candidate_ids", []
                        )
                    },
                    sort_keys=True,
                ),
                "sources": next(
                    f["sources"] for f in entry["facts"] if f["key"] == "formula"
                ),
            }
        ] + entry["facts"]
        for fact in sorted(facts, key=lambda f: f["key"]):
            task_id = f"{run_id}:{entry['id']}:{fact['key']}"
            # The existing task index's 'molecule' scope covers compounds; the fact
            # and identity JSON retain the exact molecule/formula-unit distinction.
            db.execute(
                """INSERT INTO research_task(task_id, run_id, target_kind, target_id,
                   target_label, field_key, prompt, status, created_at, completed_at)
                   VALUES (?, ?, 'molecule', ?, ?, ?, ?, 'found', ?, ?)""",
                (
                    task_id,
                    run_id,
                    entry["id"],
                    entry["name"],
                    fact["key"],
                    "Manually inspect cited primary sources; preserve unverified status.",
                    timestamp,
                    timestamp,
                ),
            )
            method = {
                "review_status": "pending_human_review",
                "input_sha256": digest(path),
                "source_metadata": [
                    {
                        "url": s["url"],
                        "retrieved_on": s["retrieved_on"],
                        "license_basis": s["license_basis"],
                    }
                    for s in fact["sources"]
                ],
            }
            db.execute(
                """INSERT INTO unverified_fact(fact_id, task_id, target_entity_id,
                   target_kind, target_id, field_key, value_text, method_notes, schema_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    task_id,
                    task_id,
                    existing_id,
                    entry["kind"],
                    entry["id"],
                    fact["key"],
                    fact["value"],
                    json.dumps(method, sort_keys=True),
                ),
            )
            for index, source in enumerate(fact["sources"]):
                db.execute(
                    """INSERT INTO unverified_fact_source(fact_id, source_index, url, title, supporting_text)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        task_id,
                        index,
                        source["url"],
                        source["title"],
                        source["supporting_text"],
                    ),
                )


def import_slices(database: Path, paths: list[Path]) -> None:
    base_digest = digest(ROOT / "universe.db")
    with tempfile.TemporaryDirectory(
        prefix="manual-chemistry-", dir=database.parent
    ) as temporary:
        staged = Path(temporary) / "universe-unverified.db"
        shutil.copyfile(database, staged)
        with closing(sqlite3.connect(staged)) as db:
            db.execute("PRAGMA foreign_keys = ON")
            row = db.execute(
                "SELECT value FROM database_metadata WHERE key = 'unverified_base_sha256'"
            ).fetchone()
            if row is None or row[0] != base_digest:
                raise ValueError(
                    "Companion database must match the checked-in reviewed base"
                )
            slices = [(path, load_slice(path, db)) for path in sorted(paths)]
            identities = {}
            for _, data in slices:
                for entry in data["entries"]:
                    identity = (entry["kind"], entry["charge"], entry["composition"])
                    if (
                        entry["id"] in identities
                        and identities[entry["id"]] != identity
                    ):
                        raise ValueError(
                            f"Conflicting cross-slice identity: {entry['id']}"
                        )
                    identities[entry["id"]] = identity
            with db:
                for path, data in slices:
                    insert_slice(db, path, data, base_digest)
            if (
                db.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                or db.execute("PRAGMA foreign_key_check").fetchall()
            ):
                raise ValueError("Staged SQLite integrity or foreign-key failure")
            db.execute("VACUUM")
        os.replace(staged, database)
    if database.resolve() == (ROOT / "universe-unverified.db").resolve():
        write_release_files(ROOT / "universe.db")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=ROOT / "universe-unverified.db"
    )
    parser.add_argument("slices", nargs="*", type=Path)
    args = parser.parse_args()
    files = args.slices or sorted((ROOT / "sources/manual-chemistry").glob("*.json"))
    if not files:
        parser.error("No manual chemistry slices found")
    import_slices(args.database, files)
    print(
        f"Imported {len(files)} research slices into {args.database}; no reviewed promotion"
    )
