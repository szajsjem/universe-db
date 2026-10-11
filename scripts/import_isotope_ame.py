#!/usr/bin/env python3
"""Parse AME2020's native fixed-width evaluated mass table without promoting it."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "sources/isotopes/ame2020_mass_1.mas20.txt"
METADATA = ROOT / "sources/isotopes/ame2020_metadata.json"
# Exactly the Fortran format printed in the source header, including spacer fields.
WIDTHS = (1, 3, 5, 5, 5, 1, 3, 4, 1, 14, 12, 13, 1, 10, 1, 2, 13, 11, 1, 3, 1, 13, 12)
FORMAT = "a1,i3,i5,i5,i5,1x,a3,a4,1x,f14.6,f12.6,f13.5,1x,f10.5,1x,a2,f13.5,f11.5,1x,i3,1x,f13.6,f12.6"


def split_fields(line: str) -> list[str]:
    """Fixed fields; whitespace splitting would lose unavailable/empty columns."""
    # Upstream trims trailing blanks in the final f12.6 field.
    if len(line) <= sum(WIDTHS[:-1]):
        raise ValueError("Truncated AME data record")
    if line[sum(WIDTHS) :].strip():
        raise ValueError("Unexpected trailing AME data")
    fields = []
    start = 0
    for width in WIDTHS:
        fields.append(line[start : start + width].strip())
        start += width
    return fields


def numeric(field: str) -> tuple[Decimal | None, bool]:
    """'#' replaces a decimal point upstream; '*' means absent, never zero."""
    text = field.strip()
    if text in {"", "*"}:
        return None, False
    try:
        value = Decimal(text.replace("#", "."))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid AME numeric field: {field!r}") from exc
    if not value.is_finite():
        raise ValueError("Nonfinite AME number")
    return value, "#" in text


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


def parse_table(text: str) -> tuple[list[dict], list[dict], list[dict]]:
    if f"format    :  {FORMAT}" not in text:
        raise ValueError("Unrecognized AME fixed-column format")
    if "MASS LIST" not in text:
        raise ValueError("Missing AME MASS LIST marker")
    started = False
    nuclides, observations, gaps = [], [], []
    seen = set()
    for lineno, line in enumerate(text.splitlines(), 1):
        if "(micro-u)" in line and "(keV)" in line:
            started = True
            continue
        if not started or not line.strip():
            continue
        fields = split_fields(line)
        nz, n, z, a = map(int, fields[1:5])
        if n < 0 or z < 0 or a != n + z or nz != n - z:
            raise ValueError(f"Inconsistent AME nuclide at line {lineno}")
        if (z, a) in seen:
            raise ValueError(f"Duplicate AME nuclide at line {lineno}")
        seen.add((z, a))
        symbol = fields[6]
        label = "neutron" if z == 0 else f"{symbol}-{a}"
        locator = f"ame2020_mass_1.mas20.txt:line:{lineno}"
        identity = {"z": z, "a": a, "isomer": 0}
        nuclides.append(
            {
                **identity,
                "label": label,
                "source_id": "amdc-ame2020",
                "source_locator": locator,
                "note": f"Ground state; upstream origin flag {fields[7]!r}.",
            }
        )
        for prop, value_index, uncertainty_index, unit, scale in (
            ("mass_excess", 9, 10, "keV", Decimal(1)),
            ("binding_energy_per_nucleon", 11, 13, "keV", Decimal(1)),
            ("atomic_mass", 21, 22, "u", Decimal("0.000001")),
        ):
            value, estimated = numeric(fields[value_index])
            uncertainty, unc_estimated = numeric(fields[uncertainty_index])
            if value is None:
                gaps.append(
                    {
                        **identity,
                        "property": prop,
                        "source_locator": locator,
                        "reason": "Upstream unavailable value",
                    }
                )
                continue
            if uncertainty is not None and uncertainty < 0:
                raise ValueError(f"Negative AME uncertainty at line {lineno}")
            # Atomic mass is i3 integral-u plus the micro-u field; not A + micro-u.
            value *= scale
            if prop == "atomic_mass":
                value += Decimal(fields[19])
            observations.append(
                {
                    "id": f"ame2020-z{z}-a{a}-{prop}",
                    **identity,
                    "property": prop,
                    "unit": unit,
                    "value": decimal_text(value),
                    "uncertainty": None
                    if uncertainty is None
                    else decimal_text(uncertainty * scale),
                    "estimated": estimated or unc_estimated,
                    "provenance_class": "curated",
                    "source_id": "amdc-ame2020",
                    "source_locator": locator,
                    "method": "AME2020 evaluated least-squares mass adjustment; upstream estimates flagged separately",
                    "note": "Evaluated reference value, not a claim of direct measurement. Atomic mass includes electrons for neutral atoms.",
                    "source_record": line,
                }
            )
    if not nuclides:
        raise ValueError("AME table contains no nuclides")
    return nuclides, observations, gaps


def load_records(source_path: Path = DEFAULT_SOURCE) -> dict:
    path = Path(source_path)
    raw = path.read_bytes()
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    digest = hashlib.sha256(raw).hexdigest()
    if digest != metadata["sha256"]:
        raise ValueError("AME source checksum does not match pinned release metadata")
    nuclides, observations, gaps = parse_table(raw.decode("ascii"))
    return {
        "sources": [metadata],
        "nuclides": nuclides,
        "observations": observations,
        "gaps": gaps,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = load_records(args.source)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: len(value) for key, value in result.items()}))


if __name__ == "__main__":
    main()
