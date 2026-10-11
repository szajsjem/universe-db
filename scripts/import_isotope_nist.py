#!/usr/bin/env python3
"""Transform the archived full NIST isotope compilation into research evidence.

No reviewed database is changed. Relative atomic masses are numerically equal
to atomic masses expressed in u; representative abundances are mole fractions.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

try:
    from .import_nist_isotopes import (
        DEFAULT_SOURCE,
        NUMBER_WITH_UNCERTAINTY,
        REQUIRED_FIELDS,
        SOURCE_URL,
        parse_number,
    )
except ImportError:
    from import_nist_isotopes import (
        DEFAULT_SOURCE,
        NUMBER_WITH_UNCERTAINTY,
        REQUIRED_FIELDS,
        SOURCE_URL,
        parse_number,
    )

SOURCE_ID = "nist-full-isotopes-2026-07-28"
SOURCE_VERSION = (
    "NIST compilation last updated January 2015; isotope masses AME2012; "
    "representative isotopic compositions 2009; atomic weights 2013"
)


def parse_value(text: str) -> tuple[str, str | None, bool]:
    """Retain decimal precision and expand parenthesized last-digit uncertainty."""
    compact = text.replace(" ", "")
    _, _, estimated = parse_number(compact)
    match = NUMBER_WITH_UNCERTAINTY.fullmatch(compact)
    assert match is not None
    central = match.group("value")
    digits = match.group("uncertainty")
    uncertainty = None
    if digits is not None:
        places = len(central.partition(".")[2])
        uncertainty = format(Decimal(int(digits)).scaleb(-places), "f")
    return central, uncertainty, estimated


def load_records(source_path: Path = DEFAULT_SOURCE) -> dict:
    """Load all archived identities and nonempty observations without promotion.

    Missing values are gaps, never zeros. Duplicate identities and unsupported
    numeric formats fail rather than silently drop source evidence.
    """
    source_path = Path(source_path)
    raw = source_path.read_bytes()
    snapshot = json.loads(raw)
    if snapshot.get("source_url") != SOURCE_URL:
        raise ValueError("Unexpected NIST source URL")
    retrieved = snapshot.get("retrieved_on")
    if retrieved != "2026-07-28":
        raise ValueError("Unexpected NIST snapshot retrieval date")
    response_digest = snapshot.get("source_response_sha256", "")
    if len(response_digest) != 64 or any(
        c not in "0123456789abcdef" for c in response_digest
    ):
        raise ValueError("Malformed source response SHA-256")
    source = {
        "id": SOURCE_ID,
        "title": "NIST Atomic Weights and Isotopic Compositions, full isotope archive",
        "url": SOURCE_URL,
        "version": SOURCE_VERSION,
        "retrieved_at": retrieved,
        "license_note": (
            "Only uncopyrightable numerical facts and nuclide identities are represented; "
            "original citations and source row attribution are retained."
        ),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_response_sha256": response_digest,
        "references": [
            "https://www.nist.gov/pml/atomic-weights-and-isotopic-compositions-relative-atomic-masses",
            "https://physics.nist.gov/PhysRefData/Compositions/notes.html",
        ],
    }
    nuclides, observations, gaps = [], [], []
    seen = set()
    for index, record in enumerate(snapshot["records"]):
        missing = REQUIRED_FIELDS.difference(record)
        if missing:
            raise ValueError(f"Source record {index} missing fields: {sorted(missing)}")
        z, a = int(record["Atomic Number"]), int(record["Mass Number"])
        if not 1 <= z <= 118 or a < z:
            raise ValueError(f"Invalid nuclide identity Z={z}, A={a}")
        key = z, a, 0
        if key in seen:
            raise ValueError(f"Duplicate nuclide identity {key}")
        seen.add(key)
        symbol = "H" if z == 1 else record["Atomic Symbol"]
        locator = f"records[{index}]; Z={z}, A={a}"
        identity = {
            "z": z,
            "a": a,
            "isomer": 0,
            "label": f"{symbol}-{a}",
            "source_id": SOURCE_ID,
            "source_locator": locator,
            "note": "NIST isotope entry; no separate isomer state is identified in this compilation.",
            "source_record": record.copy(),
        }
        nuclides.append(identity)
        for field, prop, unit in (
            ("Relative Atomic Mass", "atomic_mass", "u"),
            ("Isotopic Composition", "isotopic_abundance", "1"),
        ):
            text = record[field].strip()
            if not text:
                gaps.append(
                    {
                        **key_fields(z, a),
                        "property": prop,
                        "reason": "Not reported by NIST",
                        "source_id": SOURCE_ID,
                    }
                )
                continue
            value, uncertainty, estimated = parse_value(text)
            if prop == "atomic_mass" and Decimal(value) <= 0:
                raise ValueError("Atomic mass must be positive")
            if prop == "isotopic_abundance" and not 0 <= Decimal(value) <= 1:
                raise ValueError("Abundance must be a fraction between zero and one")
            note = (
                "AME2012 value as compiled by NIST; numerical relative atomic mass "
                "expressed as atomic mass in u, including atomic electrons."
                if prop == "atomic_mass"
                else "Representative terrestrial mole fraction from the 2009 composition evaluation; "
                "uncertainty includes probable material variation and experimental errors. "
                f"Source composition/atomic-weight notes: {record['Notes'] or 'none'}."
            )
            if estimated:
                note += " Source # flag: value and error derived at least partly from systematic trends."
            observations.append(
                {
                    "id": f"nist:{prop}:{z}:{a}:0",
                    **key_fields(z, a),
                    "property": prop,
                    "unit": unit,
                    "value": value,
                    "uncertainty": uncertainty,
                    "estimated": estimated,
                    "provenance_class": "curated",
                    "source_id": SOURCE_ID,
                    "source_locator": f"{locator}; {field}",
                    "method": "Reproducible transcription of NIST compiled evaluated values",
                    "note": note,
                    "source_record": record.copy(),
                }
            )
    return {
        "sources": [source],
        "nuclides": nuclides,
        "observations": observations,
        "gaps": gaps,
    }


def key_fields(z: int, a: int) -> dict:
    return {"z": z, "a": a, "isomer": 0}
