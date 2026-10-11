"""Source-native NUBASE2020 nuclear-property importer; never invent missing values."""

from __future__ import annotations

import hashlib
import json
import re
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "sources/isotopes/nubase2020_4.mas20.txt"
SOURCE_ID = "nubase2020"
SOURCE_URL = "https://www-nds.iaea.org/amdc/ame2020/nubase_4.mas20.txt"
NUMBER = re.compile(r"[0-9]+(?:\.[0-9]*)?|\.[0-9]+")
SIGNED_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")
SECOND_FACTORS = {
    "ys": Fraction(1, 10**24),
    "zs": Fraction(1, 10**21),
    "as": Fraction(1, 10**18),
    "fs": Fraction(1, 10**15),
    "ps": Fraction(1, 10**12),
    "ns": Fraction(1, 10**9),
    "us": Fraction(1, 10**6),
    "ms": Fraction(1, 1000),
    "s": Fraction(1),
    "m": Fraction(60),
    "h": Fraction(3600),
    "d": Fraction(86400),
    "y": Fraction(31557600),
}
for _prefix, _exponent in {
    "k": 3,
    "M": 6,
    "G": 9,
    "T": 12,
    "P": 15,
    "E": 18,
    "Z": 21,
    "Y": 24,
}.items():
    SECOND_FACTORS[_prefix + "y"] = SECOND_FACTORS["y"] * 10**_exponent


def exact_seconds(value: str, unit: str) -> str:
    """Convert an unqualified decimal point to exact rational seconds.

    A year is represented using the explicit Julian-year convention, 365.25 days.
    This convention is recorded in every affected observation's method.
    """
    if not NUMBER.fullmatch(value) or unit not in SECOND_FACTORS:
        raise ValueError(f"Not a supported unqualified half-life: {value!r} {unit!r}")
    result = Fraction(value) * SECOND_FACTORS[unit]
    if result <= 0:
        raise ValueError("Half-life must be positive")
    return str(result)


def load_records(source_path: Path = DEFAULT_SOURCE) -> dict:
    """Parse official fixed-width columns, preserving bounds and assignment flags."""
    source_path = Path(source_path)
    metadata_path = source_path.with_suffix(".metadata.json")
    metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata_path.exists()
        else {}
    )
    source = {
        "id": SOURCE_ID,
        "title": "F.G. Kondev et al., The NUBASE2020 evaluation of nuclear physics properties, Chinese Physics C 45, 030001 (2021)",
        "url": SOURCE_URL,
        "version": "NUBASE2020; published 2021, DOI 10.1088/1674-1137/abddae",
        "retrieved_at": metadata.get("retrieved_at", "unknown"),
        "license_note": "Publicly distributed AMDC evaluated numerical facts. AMDC requests citation of the paper; no blanket software/content license is inferred. Publication is open access; retained source-native table has its original attribution.",
        "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
    }
    result = {"sources": [source], "nuclides": [], "observations": [], "gaps": []}
    seen = set()
    for line_number, raw in enumerate(
        source_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not raw.strip() or raw.startswith("#"):
            continue
        if len(raw) < 17 or not raw[:3].isdigit() or not raw[4:8].isdigit():
            raise ValueError(f"Malformed NUBASE record at line {line_number}")
        a, z, state = int(raw[:3]), int(raw[4:7]), int(raw[7])
        key = (z, a, state)
        if key in seen:
            raise ValueError(f"Duplicate NUBASE state {key}")
        seen.add(key)
        locator = f"line {line_number}; A={a}, Z={z}, state_index={state}"
        notes = []
        if state:
            notes.append(
                "NUBASE state index: may identify an isomer, level, resonance, or isobaric analogue state; not interchangeable with ground state."
            )
        if raw[67:68] == "*":
            notes.append("Ground/isomer ordering uncertain in source.")
        if raw[68:69] == "&":
            notes.append("Ground/isomer ordering reversed compared with ENSDF.")
        nonexistent = "non-exist" in raw[42:65]
        if nonexistent:
            notes.append(
                "Source marks this historical state assignment non-exist; excluded from property import."
            )
        note = " ".join(notes)
        base = {
            "z": z,
            "a": a,
            "isomer": state,
            "source_id": SOURCE_ID,
            "source_locator": locator,
        }
        result["nuclides"].append({**base, "label": raw[11:17].strip(), "note": note})
        if nonexistent:
            result["gaps"].append(
                {
                    **base,
                    "property": "all",
                    "reason": "withdrawn_nonexistent_state_assignment",
                }
            )
            continue

        def observation(
            prop,
            unit,
            *,
            value=None,
            text=None,
            uncertainty=None,
            estimated=False,
            value_kind="point",
            extra_note="",
        ):
            result["observations"].append(
                {
                    **base,
                    "id": f"nubase2020-z{z}-a{a}-i{state}-{prop}",
                    "property": prop,
                    "unit": unit,
                    "value": value,
                    "text_value": text,
                    "uncertainty": uncertainty,
                    "estimated": estimated,
                    "provenance_class": "curated",
                    "value_kind": value_kind,
                    "source_record": raw,
                    "method": "NUBASE2020 evaluated recommendation; fixed-width source-native import. Year conversion uses 365.25 days exactly (Julian year).",
                    "note": " ".join(filter(None, [note, extra_note])),
                }
            )

        for prop, field, uncertainty_field in [
            ("mass_excess", raw[18:31].strip(), raw[31:42].strip()),
            ("excitation_energy", raw[42:54].strip(), raw[54:65].strip()),
        ]:
            if not field:
                if prop == "mass_excess" or state:
                    result["gaps"].append(
                        {**base, "property": prop, "reason": "not_reported"}
                    )
                continue
            point = field.replace("#", "")
            numeric_uncertainty = uncertainty_field.replace("#", "")
            value = point if SIGNED_NUMBER.fullmatch(point) else None
            converted_uncertainty = (
                numeric_uncertainty if NUMBER.fullmatch(numeric_uncertainty) else None
            )
            observation(
                prop,
                "keV",
                value=value,
                text=" ".join(filter(None, [field, uncertainty_field, "keV"])),
                uncertainty=converted_uncertainty,
                estimated="#" in field or "#" in uncertainty_field,
                value_kind="point" if value is not None else "bound",
                extra_note=(
                    "State-specific source-native energy in keV; no atomic mass is inferred. "
                    + (
                        f"Excitation origin code: {raw[65:67].strip() or 'not supplied'}. "
                        if prop == "excitation_energy"
                        else ""
                    )
                    + "Original decimal precision and systematic (#) flags are retained."
                ),
            )

        lifetime, unit, uncertainty = (
            raw[69:78].strip(),
            raw[78:80].strip(),
            raw[81:88].strip(),
        )
        if lifetime == "stbl":
            observation("stability", "1", text="stable", value_kind="text")
        elif lifetime == "p-unst":
            observation("stability", "1", text="particle unstable", value_kind="text")
        elif lifetime:
            point = lifetime.replace("#", "")
            estimated = "#" in lifetime or "#" in uncertainty
            value = exact_seconds(point, unit) if NUMBER.fullmatch(point) else None
            numeric_uncertainty = uncertainty.replace("#", "")
            converted_uncertainty = (
                exact_seconds(numeric_uncertainty, unit)
                if NUMBER.fullmatch(numeric_uncertainty)
                and Fraction(numeric_uncertainty) > 0
                else None
            )
            observation(
                "half_life",
                "s",
                value=value,
                text=" ".join(filter(None, [lifetime, unit, uncertainty])),
                uncertainty=converted_uncertainty,
                estimated=estimated,
                value_kind="point" if value is not None else "bound",
                extra_note="Uncertainty/qualifier text is retained verbatim; bounds are not point measurements.",
            )
        else:
            result["gaps"].append(
                {
                    **base,
                    "property": "half_life",
                    "reason": "not_reported",
                    "source_text": uncertainty,
                }
            )
        spin = raw[88:102].strip()
        decay = raw[119:209].strip()
        for prop, text, dimension in [
            ("spin_parity", spin, "hbar"),
            ("decay_modes", decay, "1"),
        ]:
            if text:
                observation(
                    prop,
                    dimension,
                    text=text,
                    estimated="#" in text,
                    value_kind="text",
                    extra_note="Assignments, alternatives, measured (*), systematic (#), and branching qualifiers are preserved; no numeric spin or branch is fabricated.",
                )
            else:
                result["gaps"].append(
                    {**base, "property": prop, "reason": "not_reported"}
                )
    return result


if __name__ == "__main__":
    records = load_records()
    print(json.dumps({key: len(value) for key, value in records.items()}, indent=2))
