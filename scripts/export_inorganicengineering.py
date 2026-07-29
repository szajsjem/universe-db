#!/usr/bin/env python3
"""Export a deterministic Inorganic Engineering datapack from universe.db."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any
import zipfile

if __package__:
    from .validate_db import validate
else:
    from validate_db import validate


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "universe.db"
DEFAULT_PROFILE = ROOT / "profiles/inorganicengineering-0.1.json"
DEFAULT_OUTPUT = ROOT / "dist/inorganicengineering-0.1.zip"
JSON_SUFFIX = b"\n"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
PHASE_ORDER = ("solid", "liquid", "aqueous", "molten", "gas", "slurry")
HAZARD_FIELDS = (
    "corrosivity",
    "environmental_severity",
    "flammability",
    "oxidizing_strength",
    "toxicity",
)


class ExportError(RuntimeError):
    """Raised when database rows cannot be represented without guessing."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + JSON_SUFFIX


def load_profile(path: Path) -> dict[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ExportError(f"{path}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=unique_object,
        )
    except (OSError, json.JSONDecodeError) as exception:
        raise ExportError(f"cannot load profile {path}: {exception}") from exception
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ExportError(f"{path}: unsupported or missing profile schema_version")
    return value


def resource_id(namespace: str, database_id: str, prefix: str) -> str:
    expected = f"{prefix}:"
    if not database_id.startswith(expected) or database_id == expected:
        raise ExportError(f"expected {prefix} ID, found {database_id!r}")
    path = database_id.removeprefix(expected)
    if any(part in {"", ".", ".."} for part in path.split("/")):
        raise ExportError(f"invalid resource path in {database_id!r}")
    return f"{namespace}:{path}"


def integral(numerator: int, denominator: int, label: str) -> int:
    quotient, remainder = divmod(numerator, denominator)
    if remainder:
        raise ExportError(f"{label} is not an exact integer: {numerator}/{denominator}")
    return quotient


def one_row(
    connection: sqlite3.Connection,
    sql: str,
    parameters: tuple[Any, ...],
    label: str,
) -> sqlite3.Row:
    rows = connection.execute(sql, parameters).fetchall()
    if len(rows) != 1:
        raise ExportError(f"{label}: expected one row, found {len(rows)}")
    return rows[0]


def observation(
    connection: sqlite3.Connection,
    subject_id: str,
    property_id: str,
    unit_id: str,
    *,
    required: bool = True,
) -> int | None:
    rows = connection.execute(
        """
        SELECT value_numerator, value_denominator, unit_id
        FROM observation
        WHERE subject_entity_id = ? AND property_id = ?
          AND dataset_id = 'dataset:inorganic-engineering-bootstrap'
        ORDER BY observation_id
        """,
        (subject_id, property_id),
    ).fetchall()
    if not rows and not required:
        return None
    if len(rows) != 1:
        raise ExportError(
            f"{subject_id} {property_id}: expected one bootstrap observation, "
            f"found {len(rows)}"
        )
    row = rows[0]
    if row["unit_id"] != unit_id:
        raise ExportError(
            f"{subject_id} {property_id}: expected {unit_id}, found {row['unit_id']}"
        )
    return integral(
        row["value_numerator"],
        row["value_denominator"],
        f"{subject_id} {property_id}",
    )


def validate_profile(profile: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "profile_id",
        "description",
        "minecraft_version",
        "pack_format",
        "namespace",
        "species_dataset",
        "default_species_metadata",
        "species",
        "minerals",
        "materials",
        "reactions",
    }
    unknown = set(profile) - required
    missing = required - set(profile)
    if missing or unknown:
        raise ExportError(
            f"profile fields mismatch; missing={sorted(missing)}, unknown={sorted(unknown)}"
        )
    if not isinstance(profile["pack_format"], int) or profile["pack_format"] <= 0:
        raise ExportError("profile pack_format must be a positive integer")
    for field in ("species", "minerals", "materials", "reactions"):
        if not isinstance(profile[field], dict):
            raise ExportError(f"profile {field} must be an object")


def species_ids(
    connection: sqlite3.Connection,
    profile: dict[str, Any],
) -> list[str]:
    rows = connection.execute(
        """
        SELECT entity_id
        FROM entity
        WHERE entity_type = 'chemical_species' AND dataset_id = ?
          AND lifecycle_state = 'active'
        ORDER BY entity_id
        """,
        (profile["species_dataset"],),
    ).fetchall()
    database_ids = [row["entity_id"] for row in rows]
    configured_ids = sorted(profile["species"])
    if database_ids != configured_ids:
        raise ExportError(
            "profile species must exactly cover the selected dataset; "
            f"database_only={sorted(set(database_ids) - set(configured_ids))}, "
            f"profile_only={sorted(set(configured_ids) - set(database_ids))}"
        )
    return database_ids


def export_elements(
    connection: sqlite3.Connection,
    namespace: str,
    selected_species: list[str],
) -> dict[str, dict[str, Any]]:
    placeholders = ",".join("?" for _ in selected_species)
    rows = connection.execute(
        f"""
        SELECT DISTINCT e.entity_id, e.atomic_number, e.symbol
        FROM element AS e
        JOIN species_element AS se ON se.element_id = e.entity_id
        WHERE se.species_id IN ({placeholders})
        ORDER BY e.atomic_number
        """,
        tuple(selected_species),
    ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        output_id = resource_id(namespace, row["entity_id"], "element")
        path = output_id.split(":", 1)[1]
        result[path] = {
            "atomic_mass_micrograms_per_mole": observation(
                connection,
                row["entity_id"],
                "property:atomic_mass",
                "unit:microgram_per_mole",
            ),
            "atomic_number": row["atomic_number"],
            "id": output_id,
            "schema_version": 1,
            "symbol": row["symbol"],
            "translation_key": f"element.{namespace}.{path.replace('/', '.')}",
        }
    return result


def complete_hazards(
    defaults: Any,
    configured: Any,
    species_id: str,
) -> dict[str, int]:
    configured = {} if configured is None else configured
    if (
        not isinstance(defaults, dict)
        or set(defaults) != set(HAZARD_FIELDS)
        or not isinstance(configured, dict)
        or set(configured) - set(HAZARD_FIELDS)
    ):
        raise ExportError(f"{species_id}: invalid hazards object")
    result: dict[str, int] = {}
    for field in HAZARD_FIELDS:
        value = configured.get(field, defaults[field])
        if not isinstance(value, int) or not 0 <= value <= 10000:
            raise ExportError(f"{species_id}: invalid hazard {field}={value!r}")
        result[field] = value
    return result


def export_species(
    connection: sqlite3.Connection,
    namespace: str,
    selected_species: list[str],
    profile: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    phase_rank = {phase: index for index, phase in enumerate(PHASE_ORDER)}
    defaults = profile["default_species_metadata"]
    if (
        not isinstance(defaults, dict)
        or set(defaults) != {"emissive_color", "hazards"}
        or not isinstance(defaults["emissive_color"], int)
    ):
        raise ExportError("profile default_species_metadata is invalid")
    for species_id in selected_species:
        row = one_row(
            connection,
            """
            SELECT formula, electric_charge
            FROM chemical_species
            WHERE entity_id = ?
            """,
            (species_id,),
            species_id,
        )
        output_id = resource_id(namespace, species_id, "chem")
        path = output_id.split(":", 1)[1]
        metadata = profile["species"][species_id]
        if not isinstance(metadata, dict) or not isinstance(
            metadata.get("display_color"), int
        ):
            raise ExportError(f"{species_id}: display_color is required")
        composition_rows = connection.execute(
            """
            SELECT element_id, atom_count
            FROM species_element
            WHERE species_id = ?
            ORDER BY element_id
            """,
            (species_id,),
        ).fetchall()
        composition = {
            resource_id(namespace, item["element_id"], "element"): item["atom_count"]
            for item in composition_rows
        }
        phase_rows = connection.execute(
            """
            SELECT phase_id
            FROM species_phase
            WHERE species_id = ?
              AND dataset_id = 'dataset:inorganic-engineering-bootstrap'
            """,
            (species_id,),
        ).fetchall()
        phases = [item["phase_id"].removeprefix("phase:") for item in phase_rows]
        phases.sort(key=lambda phase: phase_rank.get(phase, len(phase_rank)))
        if "supported_phases" in metadata:
            phases = metadata["supported_phases"]
        if not isinstance(phases, list) or not phases or len(phases) != len(set(phases)):
            raise ExportError(f"{species_id}: supported phases must be a unique list")
        document: dict[str, Any] = {
            "density_milligrams_per_litre": observation(
                connection,
                species_id,
                "property:density",
                "unit:milligram_per_litre",
            ),
            "display_color": metadata["display_color"],
            "display_formula": row["formula"],
            "electric_charge": row["electric_charge"],
            "elemental_composition": composition,
            "emissive_color": metadata.get(
                "emissive_color", defaults["emissive_color"]
            ),
            "hazards": complete_hazards(
                defaults["hazards"],
                metadata.get("hazards"),
                species_id,
            ),
            "heat_capacity_microjoules_per_gram_kelvin": observation(
                connection,
                species_id,
                "property:specific_heat_capacity",
                "unit:microjoule_per_gram_kelvin",
            ),
            "id": output_id,
            "molar_mass_micrograms_per_mole": observation(
                connection,
                species_id,
                "property:molar_mass",
                "unit:microgram_per_mole",
            ),
            "schema_version": 1,
            "supported_phases": phases,
            "translation_key": f"species.{namespace}.{path.replace('/', '.')}",
        }
        for property_id, field in (
            ("property:melting_point", "melting_point_millikelvin"),
            ("property:boiling_point", "boiling_point_millikelvin"),
        ):
            value = observation(
                connection,
                species_id,
                property_id,
                "unit:millikelvin",
                required=False,
            )
            if value is not None:
                document[field] = value
        tags = metadata.get("compatibility_tags")
        if tags is not None:
            if (
                not isinstance(tags, list)
                or len(tags) != len(set(tags))
                or not all(isinstance(tag, str) and tag.startswith("c:") for tag in tags)
            ):
                raise ExportError(f"{species_id}: invalid compatibility_tags")
            document["compatibility_tags"] = tags
        result[path] = document
    return result


def material_components(
    connection: sqlite3.Connection,
    material_id: str,
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT species_id, amount_numerator, amount_denominator, basis, role
        FROM material_component
        WHERE material_id = ?
        ORDER BY species_id
        """,
        (material_id,),
    ).fetchall()


def export_minerals(
    connection: sqlite3.Connection,
    namespace: str,
    profile: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for material_id, metadata in sorted(profile["minerals"].items()):
        components = material_components(connection, material_id)
        mineral = [row for row in components if row["role"] == "mineral"]
        gangue = [row for row in components if row["role"] == "gangue"]
        if len(mineral) != 1 or len(gangue) != 1 or len(components) != 2:
            raise ExportError(
                f"{material_id}: mineral export needs one mineral and one gangue"
            )
        path = metadata["id"]
        output_id = f"{namespace}:{path}"
        mineral_id = resource_id(namespace, mineral[0]["species_id"], "chem")
        result[path] = {
            "gangue_species": resource_id(
                namespace, gangue[0]["species_id"], "chem"
            ),
            "id": output_id,
            "mineral_species": mineral_id,
            "schema_version": 1,
            "translation_key": metadata.get(
                "translation_key",
                f"species.{namespace}.{mineral_id.split(':', 1)[1].replace('/', '.')}",
            ),
        }
    return result


def export_materials(
    connection: sqlite3.Connection,
    namespace: str,
    profile: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for material_id, metadata in sorted(profile["materials"].items()):
        components = material_components(connection, material_id)
        if not components:
            raise ExportError(f"{material_id}: material has no components")
        composition: dict[str, int] = {}
        for row in components:
            if row["basis"] != "mass_fraction":
                raise ExportError(f"{material_id}: only exact mass fractions export")
            parts = integral(
                row["amount_numerator"] * 1_000_000,
                row["amount_denominator"],
                f"{material_id} {row['species_id']} mass fraction",
            )
            composition[resource_id(namespace, row["species_id"], "chem")] = parts
        if sum(composition.values()) != 1_000_000:
            raise ExportError(f"{material_id}: composition does not total 1,000,000 ppm")
        path = metadata["id"]
        result[path] = {
            "compatibility_tags": metadata.get("compatibility_tags", []),
            "composition_parts_per_million": composition,
            "id": f"{namespace}:{path}",
            "schema_version": 1,
            "translation_key": metadata.get(
                "translation_key",
                f"material.{namespace}.{path.replace('/', '.')}",
            ),
        }
    return result


def reaction_conditions(
    connection: sqlite3.Connection,
    reaction_id: str,
) -> dict[str, int]:
    rows = connection.execute(
        """
        SELECT cv.quantity_kind, cv.value_numerator, cv.value_denominator,
               cv.unit_id
        FROM reaction_condition AS rc
        JOIN condition_value AS cv USING (condition_set_id)
        WHERE rc.reaction_id = ? AND rc.relationship = 'valid_range'
        ORDER BY cv.quantity_kind
        """,
        (reaction_id,),
    ).fetchall()
    expected_units = {
        "temperature_min": "unit:millikelvin",
        "temperature_max": "unit:millikelvin",
        "pressure_min": "unit:pascal",
        "pressure_max": "unit:pascal",
    }
    values: dict[str, int] = {}
    for row in rows:
        kind = row["quantity_kind"]
        if kind not in expected_units or row["unit_id"] != expected_units[kind]:
            raise ExportError(f"{reaction_id}: unsupported condition {dict(row)}")
        values[kind] = integral(
            row["value_numerator"],
            row["value_denominator"],
            f"{reaction_id} {kind}",
        )
    if set(values) != set(expected_units):
        raise ExportError(f"{reaction_id}: incomplete process condition range")
    return values


def export_reactions(
    connection: sqlite3.Connection,
    namespace: str,
    profile: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for reaction_id, metadata in sorted(profile["reactions"].items()):
        reaction = one_row(
            connection,
            """
            SELECT reaction_kind, reversible, energy_change_numerator,
                   energy_change_denominator, energy_unit_id
            FROM reaction
            WHERE reaction_id = ?
            """,
            (reaction_id,),
            reaction_id,
        )
        if reaction["reaction_kind"] != "process" or reaction["reversible"]:
            raise ExportError(f"{reaction_id}: only irreversible process reactions export")
        if reaction["energy_unit_id"] != "unit:joule":
            raise ExportError(f"{reaction_id}: energy must use joules")
        participants = connection.execute(
            """
            SELECT role, species_id, phase_id, coefficient_numerator,
                   coefficient_denominator
            FROM reaction_participant
            WHERE reaction_id = ?
            ORDER BY role DESC, species_id, phase_id
            """,
            (reaction_id,),
        ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {"reactant": [], "product": []}
        for participant in participants:
            role = participant["role"]
            if role not in grouped:
                raise ExportError(f"{reaction_id}: unsupported participant role {role}")
            grouped[role].append(
                {
                    "micromoles": integral(
                        participant["coefficient_numerator"],
                        participant["coefficient_denominator"],
                        f"{reaction_id} coefficient",
                    ),
                    "phase": participant["phase_id"].removeprefix("phase:"),
                    "species": resource_id(
                        namespace, participant["species_id"], "chem"
                    ),
                }
            )
        if not grouped["reactant"] or not grouped["product"]:
            raise ExportError(f"{reaction_id}: inputs and outputs are required")
        conditions = reaction_conditions(connection, reaction_id)
        path = metadata["id"]
        machine = f"{namespace}:{metadata['machine']}"
        result[path] = {
            "definition": {
                "energy_change_joules": integral(
                    reaction["energy_change_numerator"],
                    reaction["energy_change_denominator"],
                    f"{reaction_id} energy",
                ),
                "id": f"{namespace}:{path}",
                "inputs": grouped["reactant"],
                "maximum_pressure_pascals": conditions["pressure_max"],
                "maximum_temperature_millikelvin": conditions["temperature_max"],
                "minimum_pressure_pascals": conditions["pressure_min"],
                "minimum_temperature_millikelvin": conditions["temperature_min"],
                "outputs": grouped["product"],
                "supported_machines": [machine],
                "throughput": metadata["throughput"],
            },
            "schema_version": 1,
            "type": machine,
        }
    return result


def build_files(
    database: Path,
    profile_path: Path,
) -> dict[str, bytes]:
    validation_failures = validate(database)
    if validation_failures:
        summary = "; ".join(validation_failures[:8])
        if len(validation_failures) > 8:
            summary += f"; and {len(validation_failures) - 8} more"
        raise ExportError(f"database validation failed: {summary}")
    profile = load_profile(profile_path)
    validate_profile(profile)
    namespace = profile["namespace"]
    files: dict[str, bytes] = {
        "pack.mcmeta": json_bytes(
            {
                "pack": {
                    "description": profile["description"],
                    "pack_format": profile["pack_format"],
                }
            }
        )
    }
    with sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
        if integrity != "ok":
            raise ExportError(f"database quick_check failed: {integrity}")
        selected_species = species_ids(connection, profile)
        families = (
            (
                f"data/{namespace}/{namespace}/elements",
                export_elements(connection, namespace, selected_species),
            ),
            (
                f"data/{namespace}/{namespace}/species",
                export_species(
                    connection, namespace, selected_species, profile
                ),
            ),
            (
                f"data/{namespace}/{namespace}/minerals",
                export_minerals(connection, namespace, profile),
            ),
            (
                f"data/{namespace}/{namespace}/materials",
                export_materials(connection, namespace, profile),
            ),
            (
                f"data/{namespace}/recipe",
                export_reactions(connection, namespace, profile),
            ),
        )
        schema_version = connection.execute("PRAGMA user_version").fetchone()[0]
    for root, documents in families:
        for path, document in documents.items():
            files[f"{root}/{path}.json"] = json_bytes(document)
    manifest = {
        "export_schema_version": 1,
        "files": {
            path: sha256_bytes(contents) for path, contents in sorted(files.items())
        },
        "minecraft_version": profile["minecraft_version"],
        "profile": profile["profile_id"],
        "profile_sha256": sha256_file(profile_path),
        "source_database": database.name,
        "source_database_schema_version": schema_version,
        "source_database_sha256": sha256_file(database),
    }
    files["universe-db-export.json"] = json_bytes(manifest)
    return files


def write_zip(files: dict[str, bytes], output: Path) -> None:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
        delete=False,
    ) as temporary:
        staged = Path(temporary.name)
    try:
        with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_STORED) as archive:
            for path, contents in sorted(files.items()):
                info = zipfile.ZipInfo(path, ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, contents)
        os.replace(staged, output)
    finally:
        staged.unlink(missing_ok=True)


def export(database: Path, profile: Path, output: Path) -> int:
    files = build_files(database, profile)
    write_zip(files, output)
    return len(files)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    try:
        count = export(arguments.database, arguments.profile, arguments.output)
    except (OSError, sqlite3.Error, ExportError) as exception:
        raise SystemExit(f"export failed: {exception}") from exception
    print(
        f"exported {count} deterministic files to {arguments.output} "
        f"({sha256_file(arguments.output)})"
    )
