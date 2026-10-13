"""Regenerate metals.json from the selected, revision-pinned COD CIFs.

This deliberately reads only the scalar tags and simple four-column site loop
used by these eleven records. It is not a general-purpose CIF parser.
"""

import hashlib
import json
import re
import shlex
from pathlib import Path

HERE = Path(__file__).resolve().parent


def scalar(text, tag):
    match = re.search(r"^" + re.escape(tag) + r"[ \t]+(.+)$", text, re.M)
    return shlex.split(match.group(1))[0] if match else None


def parameter(text, tag, unit):
    value = scalar(text, tag)
    if value is None:
        return None
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)(?:\((\d+)\))?", value)
    if not match:
        raise ValueError(f"Unsupported number {value}")
    uncertainty = None
    if match.group(2):
        places = len(match.group(1).partition(".")[2])
        from decimal import Decimal

        uncertainty = str(Decimal(match.group(2)).scaleb(-places))
    return {"value": match.group(1), "unit": unit, "uncertainty": uncertainty}


def build():
    records = json.loads((HERE / "metals-selected-cod-records.txt").read_text())
    sources = []
    structures = []
    for record in records:
        code = record["file"]
        path = HERE / f"metals-{code}.cif"
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        element = scalar(text, "_chemical_formula_sum")
        revision = re.search(r"\$Revision: (\d+) \$", text).group(1)
        assert revision == record["svnrevision"]
        source_id = f"metals-cod-{code}"
        sources.append(
            {
                "id": source_id,
                "title": f"{record['authors']} ({record['year']}), {record['title']}; "
                f"{record['journal']} {record['volume']}, "
                f"{record['firstpage']}â€“{record['lastpage']}; COD {code}",
                "url": f"https://crystallography.net/cod/{code}.cif@{revision}",
                "version": f"COD revision {revision}; original paper {record['year']}",
                "retrieved_at": "2026-10-12",
                "license_note": "COD data and database dedicated to public domain under CC0; "
                "original authors acknowledged. https://www.crystallography.net/cod/",
                "doi": record.get("doi"),
                "source_file": f"sources/crystals/{path.name}",
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
        group = int(scalar(text, "_space_group_IT_number"))
        phase = {
            "Fe": "alpha (bcc)" if group == 229 else "gamma (fcc)",
            "Ti": "alpha (hcp)",
            "Mg": "hcp",
            "C": "diamond",
            "Si": "diamond cubic",
        }.get(element, "fcc")
        site_rows = (
            text.split("_atom_site_fract_z", 1)[1]
            .split("loop_", 1)[0]
            .strip()
            .splitlines()
        )
        sites = []
        for row in site_rows:
            fields = shlex.split(row)
            if len(fields) != 4:
                raise ValueError(f"Unsupported atom loop in {code}")
            label, x, y, z = fields
            sites.append(
                {
                    "label": label,
                    "element": element,
                    "x": x,
                    "y": y,
                    "z": z,
                    "occupancy": None,
                    "multiplicity": None,
                    "wyckoff": None,
                }
            )
        note = "Coordinates are source-native asymmetric-unit values, not an expanded full cell. "
        note += "Missing occupancy, Wyckoff label, multiplicity, uncertainty or pressure is not inferred. "
        if group == 194:
            note += "Source decimals 0.33333/0.66667 retained; not silently replaced by exact thirds. "
        if element == "Ti":
            note += "Natural mineral specimen from Luobusha ophiolite; not a certified pure-metal standard. Temperature unreported. "
        method = (
            "X-ray diffraction (publication title)"
            if "X-ray" in record["title"]
            else None
        )
        structures.append(
            {
                "id": f"metals-{element.lower()}-{code}",
                "name": f"{record.get('mineral') or record.get('commonname') or element}, COD {code}",
                "formula": element,
                "phase": phase,
                "crystal_system": "hexagonal" if group == 194 else "cubic",
                "space_group_number": group,
                "space_group_symbol": scalar(text, "_symmetry_space_group_name_H-M"),
                "cell_convention": "conventional hexagonal"
                if group == 194
                else "conventional cubic",
                "site_convention": "asymmetric_unit",
                "cell_formula_units": int(scalar(text, "_cell_formula_units_Z")),
                "lattice_parameters": {
                    **{
                        key: parameter(text, f"_cell_length_{key}", "angstrom")
                        for key in ("a", "b", "c")
                    },
                    **{
                        key: parameter(text, f"_cell_angle_{key}", "deg")
                        for key in ("alpha", "beta", "gamma")
                    },
                },
                "temperature_k": scalar(text, "_diffrn_ambient_temperature"),
                "pressure_pa": (
                    "0" if scalar(text, "_diffrn_ambient_pressure") == "0" else None
                ),
                "sites": sites,
                "source_id": source_id,
                "source_locator": f"data_{code}; _cell_length_*; _cell_angle_*; _atom_site_*; "
                "_diffrn_ambient_*; original publication citation in CIF",
                "method": method,
                "provenance_class": "measured",
                "kind": "experimental",
                "review_status": "pending_human_review",
                "note": note,
            }
        )
    return {
        "sources": sources,
        "structures": structures,
        "gaps": [
            {
                "id": "metals-ti-hull-z-conflict",
                "formula": "Ti",
                "reason": "Excluded historical "
                "COD 9011600 (Hull 1921): CIF Z=4 and diffraction density8.820 conflict with its "
                "one-site hcp basis. Raw pinned CIF retained for review; no automatic correction.",
                "source_file": "sources/crystals/metals-9011600.cif",
            },
            {
                "id": "metals-ti-temperature",
                "formula": "Ti",
                "reason": "Natural alpha-Ti "
                "COD9017383 does not provide measurement temperature or pressure.",
            },
            {
                "id": "metals-site-metadata",
                "reason": "Selected COD/AMCSD CIFs omit site occupancy, "
                "Wyckoff labels and multiplicities; source decimal coordinates retained. "
                "Symmetry operators available in raw CIFs; expansion requires reviewed handling "
                "of rounded special positions.",
            },
        ],
    }


if __name__ == "__main__":
    (HERE / "metals.json").write_text(
        json.dumps(build(), indent=2) + "\n", encoding="utf-8"
    )
