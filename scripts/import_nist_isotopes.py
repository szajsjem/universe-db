#!/usr/bin/env python3
"""Vendor NIST isotope data and generate naturally representative nuclides."""

from __future__ import annotations

import argparse
from decimal import Decimal
from fractions import Fraction
import hashlib
import html
import json
from pathlib import Path
import re
import urllib.request

try:
    from .import_pubchem_periodic_table import (
        DEFAULT_SOURCE as PERIODIC_TABLE_SOURCE,
        load_rows as load_element_rows,
        slug,
        sql_text,
    )
except ImportError:
    from import_pubchem_periodic_table import (
        DEFAULT_SOURCE as PERIODIC_TABLE_SOURCE,
        load_rows as load_element_rows,
        slug,
        sql_text,
    )


ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = (
    "https://physics.nist.gov/cgi-bin/Compositions/stand_alone.pl"
    "?all=all&ascii=ascii2&isotype=all"
)
DEFAULT_SOURCE = ROOT / "sources" / "nist-isotopic-compositions-2026-07-28.json"
DEFAULT_OUTPUT = ROOT / "seed" / "005_common_isotopes.sql"
RETRIEVED_ON = "2026-07-28"
EXPECTED_SOURCE_RECORDS = 3352
EXPECTED_NATURAL_NUCLIDES = 288
EXPECTED_NATURAL_ELEMENTS = 84
REQUIRED_FIELDS = {
    "Atomic Number",
    "Atomic Symbol",
    "Mass Number",
    "Relative Atomic Mass",
    "Isotopic Composition",
    "Standard Atomic Weight",
    "Notes",
}
NUMBER_WITH_UNCERTAINTY = re.compile(
    r"^(?P<value>[0-9]+(?:\.[0-9]+)?)"
    r"(?:\((?P<uncertainty>[0-9]+)(?P<estimated>#)?\))?$"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_records(raw: bytes) -> list[dict[str, str]]:
    document = raw.decode("utf-8", errors="replace")
    match = re.search(r"<pre>(.*?)</pre>", document, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        raise ValueError("NIST response does not contain a preformatted data section")
    text = html.unescape(re.sub(r"<[^>]+>", "", match.group(1)))
    records: list[dict[str, str]] = []
    for block in re.split(r"\n\s*\n", text):
        record: dict[str, str] = {}
        for line in block.splitlines():
            if " = " in line:
                key, value = line.split(" = ", 1)
                record[key.strip()] = value.strip()
        if "Atomic Number" in record:
            missing = REQUIRED_FIELDS.difference(record)
            if missing:
                raise ValueError(f"NIST record is missing fields: {sorted(missing)}")
            records.append(record)
    return records


def download_snapshot(destination: Path) -> None:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={
            "User-Agent": (
                "universe-db isotope importer "
                "(https://github.com/szajsjem/universe-db)"
            )
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    records = extract_records(raw)
    snapshot = {
        "records": records,
        "retrieved_on": RETRIEVED_ON,
        "source_response_sha256": sha256(raw),
        "source_url": SOURCE_URL,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_natural_records(source: Path) -> list[dict[str, str]]:
    snapshot = json.loads(source.read_text(encoding="utf-8"))
    if snapshot["source_url"] != SOURCE_URL:
        raise ValueError(f"unexpected source URL: {snapshot['source_url']}")
    if snapshot["retrieved_on"] != RETRIEVED_ON:
        raise ValueError(f"unexpected retrieval date: {snapshot['retrieved_on']}")
    if not re.fullmatch(r"[0-9a-f]{64}", snapshot["source_response_sha256"]):
        raise ValueError("source response SHA-256 is malformed")
    records = snapshot["records"]
    if len(records) != EXPECTED_SOURCE_RECORDS:
        raise ValueError(
            f"expected {EXPECTED_SOURCE_RECORDS} NIST records, got {len(records)}"
        )
    natural = [record for record in records if record["Isotopic Composition"]]
    if len(natural) != EXPECTED_NATURAL_NUCLIDES:
        raise ValueError(
            f"expected {EXPECTED_NATURAL_NUCLIDES} natural nuclides, got {len(natural)}"
        )
    atomic_numbers = {int(record["Atomic Number"]) for record in natural}
    if len(atomic_numbers) != EXPECTED_NATURAL_ELEMENTS:
        raise ValueError(
            f"expected {EXPECTED_NATURAL_ELEMENTS} represented elements, "
            f"got {len(atomic_numbers)}"
        )
    identities = {
        (int(record["Atomic Number"]), int(record["Mass Number"]))
        for record in natural
    }
    if len(identities) != len(natural):
        raise ValueError("natural nuclide identities are not unique")
    return natural


def parse_number(value: str) -> tuple[Fraction, Fraction | None, bool]:
    compact = value.replace(" ", "")
    match = NUMBER_WITH_UNCERTAINTY.fullmatch(compact)
    if not match:
        raise ValueError(f"unsupported NIST numeric value: {value!r}")
    central_text = match.group("value")
    central = Fraction(Decimal(central_text))
    uncertainty_digits = match.group("uncertainty")
    if uncertainty_digits is None:
        return central, None, False
    decimals = len(central_text.partition(".")[2])
    uncertainty = Fraction(int(uncertainty_digits), 10**decimals)
    return central, uncertainty, match.group("estimated") is not None


def ratio_sql(value: Fraction | None) -> tuple[str, str]:
    if value is None:
        return "NULL", "NULL"
    return str(value.numerator), str(value.denominator)


def comma_rows(rows: list[str]) -> str:
    return ",\n".join(f"    {row}" for row in rows)


def render_seed(source: Path, periodic_source: Path = PERIODIC_TABLE_SOURCE) -> str:
    records = load_natural_records(source)
    element_rows = load_element_rows(periodic_source)
    elements = {
        int(row["AtomicNumber"]): {
            "entity_id": f"element:{slug(row['Name'])}",
            "name": row["Name"].lower(),
            "symbol": row["Symbol"],
        }
        for row in element_rows
    }
    source_digest = sha256(source.read_bytes())
    entities: list[str] = []
    nuclides: list[str] = []
    designations: list[str] = []
    observations: list[str] = []
    aliases: list[str] = []

    for record in records:
        atomic_number = int(record["Atomic Number"])
        mass_number = int(record["Mass Number"])
        element = elements[atomic_number]
        neutron_count = mass_number - atomic_number
        if neutron_count < 0:
            raise ValueError(
                f"invalid mass number {mass_number} for atomic number {atomic_number}"
            )
        nuclide_id = f"nuclide:{slug(element['name'])}-{mass_number}"
        short_id = f"{slug(element['name'])}-{mass_number}"
        entities.append(
            "("
            + ", ".join(
                (
                    sql_text(nuclide_id),
                    "'nuclide'",
                    sql_text(f"{element['name']}-{mass_number}"),
                    "'dataset:nist-natural-isotopes-2026-07-28'",
                    "'active'",
                    "3",
                )
            )
            + ")"
        )
        nuclides.append(
            "("
            + ", ".join(
                (
                    sql_text(nuclide_id),
                    sql_text(element["entity_id"]),
                    str(atomic_number),
                    str(neutron_count),
                    "0",
                    "NULL",
                    "NULL",
                    "NULL",
                    "1",
                )
            )
            + ")"
        )
        designations.append(
            "("
            + ", ".join(
                (
                    sql_text(nuclide_id),
                    "'natural_isotopic_composition'",
                    "'dataset:nist-natural-isotopes-2026-07-28'",
                    "'nist-isotopic-compositions-2026-07-28'",
                    "3",
                )
            )
            + ")"
        )

        relative_mass, mass_uncertainty, mass_estimated = parse_number(
            record["Relative Atomic Mass"]
        )
        mass_unc_num, mass_unc_den = ratio_sql(mass_uncertainty)
        mass_method = (
            "NIST Relative Atomic Mass field"
            + ("; source marks the uncertainty as estimated" if mass_estimated else "")
            + "."
        )
        observations.append(
            "("
            + ", ".join(
                (
                    sql_text(f"observation:nist:relative_atomic_mass:{short_id}"),
                    sql_text(nuclide_id),
                    "'property:relative_atomic_mass'",
                    str(relative_mass.numerator),
                    str(relative_mass.denominator),
                    "'unit:one'",
                    mass_unc_num,
                    mass_unc_den,
                    "'measured'",
                    "'dataset:nist-natural-isotopes-2026-07-28'",
                    "'nist-isotopic-compositions-2026-07-28'",
                    "NULL",
                    sql_text(mass_method),
                    "3",
                )
            )
            + ")"
        )

        abundance, abundance_uncertainty, abundance_estimated = parse_number(
            record["Isotopic Composition"]
        )
        abundance_unc_num, abundance_unc_den = ratio_sql(abundance_uncertainty)
        notes = record["Notes"] or "none"
        abundance_method = (
            "NIST representative isotopic composition; "
            f"source notes: {notes}"
            + ("; source marks the uncertainty as estimated" if abundance_estimated else "")
            + "."
        )
        observations.append(
            "("
            + ", ".join(
                (
                    sql_text(f"observation:nist:isotopic_composition:{short_id}"),
                    sql_text(nuclide_id),
                    "'property:isotopic_composition'",
                    str(abundance.numerator),
                    str(abundance.denominator),
                    "'unit:one'",
                    abundance_unc_num,
                    abundance_unc_den,
                    "'measured'",
                    "'dataset:nist-natural-isotopes-2026-07-28'",
                    "'nist-isotopic-compositions-2026-07-28'",
                    "'condition:nist_representative_terrestrial_composition'",
                    sql_text(abundance_method),
                    "3",
                )
            )
            + ")"
        )

        source_symbol = record["Atomic Symbol"]
        if source_symbol != element["symbol"]:
            aliases.append(
                "("
                + ", ".join(
                    (
                        sql_text(f"alias:nist:isotope_symbol:{source_symbol}"),
                        sql_text(nuclide_id),
                        "'isotope_symbol'",
                        sql_text(source_symbol),
                        "'nist-isotopic-compositions-2026-07-28'",
                    )
                )
                + ")"
            )

    alias_sql = ""
    if aliases:
        alias_sql = f"""

INSERT INTO alias(alias_id, entity_id, scheme, value, source_id) VALUES
{comma_rows(aliases)};
"""

    rendered = f"""-- Generated by scripts/import_nist_isotopes.py.
-- Source snapshot SHA-256: {source_digest}
-- Includes only rows with an authored representative isotopic composition.
-- Do not edit this file by hand.

INSERT INTO entity(
    entity_id, entity_type, name, dataset_id, lifecycle_state, schema_version
) VALUES
{comma_rows(entities)};

INSERT INTO nuclide(
    entity_id, element_id, proton_count, neutron_count, isomer_index,
    excitation_energy_numerator, excitation_energy_denominator,
    excitation_energy_unit_id, observed
) VALUES
{comma_rows(nuclides)};

INSERT INTO nuclide_designation(
    nuclide_id, designation, dataset_id, source_id, schema_version
) VALUES
{comma_rows(designations)};

INSERT INTO observation(
    observation_id, subject_entity_id, property_id, value_numerator,
    value_denominator, unit_id, uncertainty_numerator,
    uncertainty_denominator, provenance_class, dataset_id, source_id,
    condition_set_id, method, schema_version
) VALUES
{comma_rows(observations)};{alias_sql}
"""
    return rendered.rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--periodic-source", type=Path, default=PERIODIC_TABLE_SOURCE)
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
    rendered = render_seed(arguments.source, arguments.periodic_source)
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
