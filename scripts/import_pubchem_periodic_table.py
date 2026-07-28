#!/usr/bin/env python3
"""Vendor and transform PubChem's complete periodic table deterministically."""

from __future__ import annotations

import argparse
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/periodictable/JSON"
DEFAULT_SOURCE = ROOT / "sources" / "pubchem-periodic-table-2026-07-28.json"
DEFAULT_OUTPUT = ROOT / "seed" / "004_periodic_table.sql"
RETRIEVED_ON = "2026-07-28"
REQUIRED_COLUMNS = {
    "AtomicNumber",
    "Symbol",
    "Name",
    "AtomicMass",
    "ElectronConfiguration",
    "StandardState",
    "GroupBlock",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sql_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def slug(name: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not result:
        raise ValueError(f"cannot create an ID from {name!r}")
    return result


def download_snapshot(destination: Path) -> None:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "universe-db periodic-table importer"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    payload = json.loads(raw)
    snapshot = {
        "payload": payload,
        "retrieved_on": RETRIEVED_ON,
        "source_response_sha256": sha256(raw),
        "source_url": SOURCE_URL,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_rows(source: Path) -> list[dict[str, str]]:
    snapshot = json.loads(source.read_text(encoding="utf-8"))
    if snapshot["source_url"] != SOURCE_URL:
        raise ValueError(f"unexpected source URL: {snapshot['source_url']}")
    if snapshot["retrieved_on"] != RETRIEVED_ON:
        raise ValueError(f"unexpected retrieval date: {snapshot['retrieved_on']}")
    if not re.fullmatch(r"[0-9a-f]{64}", snapshot["source_response_sha256"]):
        raise ValueError("source response SHA-256 is malformed")
    payload = snapshot["payload"]
    columns = payload["Table"]["Columns"]["Column"]
    missing = REQUIRED_COLUMNS.difference(columns)
    if missing:
        raise ValueError(f"source is missing columns: {sorted(missing)}")
    rows = [
        dict(zip(columns, row["Cell"], strict=True))
        for row in payload["Table"]["Row"]
    ]
    atomic_numbers = [int(row["AtomicNumber"]) for row in rows]
    if atomic_numbers != list(range(1, 119)):
        raise ValueError("expected exactly one ordered row for atomic numbers 1–118")
    if len({row["Symbol"] for row in rows}) != 118:
        raise ValueError("element symbols are not unique")
    if len({row["Name"] for row in rows}) != 118:
        raise ValueError("element names are not unique")
    for row in rows:
        if not row["AtomicMass"]:
            raise ValueError(f"element {row['AtomicNumber']} has no AtomicMass")
    return rows


def relative_atomic_mass_ratio(mass: str) -> tuple[int, int]:
    relative_atomic_mass = Fraction(Decimal(mass))
    return relative_atomic_mass.numerator, relative_atomic_mass.denominator


def comma_rows(rows: list[str]) -> str:
    return ",\n".join(f"    {row}" for row in rows)


def render_seed(source: Path) -> str:
    rows = load_rows(source)
    source_digest = sha256(source.read_bytes())
    entities: list[str] = []
    elements: list[str] = []
    observations: list[str] = []
    for row in rows:
        element_slug = slug(row["Name"])
        entity_id = f"element:{element_slug}"
        entities.append(
            "("
            + ", ".join(
                (
                    sql_text(entity_id),
                    "'element'",
                    sql_text(row["Name"].lower()),
                    "'dataset:pubchem-periodic-table-2026-07-28'",
                    "'active'",
                    "2",
                )
            )
            + ")"
        )
        elements.append(
            "("
            + ", ".join(
                (
                    sql_text(entity_id),
                    row["AtomicNumber"],
                    sql_text(row["Symbol"]),
                    sql_text(row["GroupBlock"]),
                    sql_text(row["ElectronConfiguration"]),
                    sql_text(row["StandardState"]),
                )
            )
            + ")"
        )
        numerator, denominator = relative_atomic_mass_ratio(row["AtomicMass"])
        observations.append(
            "("
            + ", ".join(
                (
                    sql_text(f"observation:pubchem:relative_atomic_mass:{element_slug}"),
                    sql_text(entity_id),
                    "'property:relative_atomic_mass'",
                    str(numerator),
                    str(denominator),
                    "'unit:one'",
                    "'curated'",
                    "'dataset:pubchem-periodic-table-2026-07-28'",
                    "'pubchem-periodic-table-2026-07-28'",
                    "'PubChem AtomicMass field represented as relative atomic mass; source-specific value, not relabeled as a CIAAW standard atomic weight.'",
                    "2",
                )
            )
            + ")"
        )

    return f"""-- Generated by scripts/import_pubchem_periodic_table.py.
-- Source snapshot SHA-256: {source_digest}
-- Do not edit this file by hand.

INSERT INTO entity(
    entity_id, entity_type, name, dataset_id, lifecycle_state, schema_version
) VALUES
{comma_rows(entities)}
ON CONFLICT(entity_id) DO UPDATE SET
    name = excluded.name,
    dataset_id = excluded.dataset_id,
    schema_version = excluded.schema_version;

INSERT INTO element(
    entity_id, atomic_number, symbol, group_block, electron_configuration,
    standard_state
) VALUES
{comma_rows(elements)}
ON CONFLICT(entity_id) DO UPDATE SET
    atomic_number = excluded.atomic_number,
    symbol = excluded.symbol,
    group_block = excluded.group_block,
    electron_configuration = excluded.electron_configuration,
    standard_state = excluded.standard_state;

INSERT INTO observation(
    observation_id, subject_entity_id, property_id, value_numerator,
    value_denominator, unit_id, provenance_class, dataset_id, source_id,
    method, schema_version
) VALUES
{comma_rows(observations)};
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--download",
        action="store_true",
        help="refresh the vendored source snapshot before generating SQL",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the generated SQL does not match the checked-in file",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    if arguments.download:
        download_snapshot(arguments.source)
    rendered = render_seed(arguments.source)
    if arguments.check:
        if not arguments.output.exists() or arguments.output.read_text(
            encoding="utf-8"
        ) != rendered:
            raise SystemExit(f"{arguments.output} is not current")
        print(f"verified {arguments.output}")
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
        print(f"generated {arguments.output}")
