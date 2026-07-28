#!/usr/bin/env python3
"""Build the checked-in SQLite artifact from migrations and seed SQL."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "universe.db"
APPLICATION_ID = 0x554E4956  # "UNIV"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sql_files(directory: Path) -> list[Path]:
    files = sorted(directory.glob("*.sql"))
    if not files:
        raise RuntimeError(f"no SQL files found in {directory}")
    return files


def build(output: Path) -> None:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="universe-db-", dir=output.parent) as tmp:
        staged = Path(tmp) / "universe.db"
        connection = sqlite3.connect(staged)
        try:
            connection.execute("PRAGMA page_size = 4096")
            connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
            connection.execute("PRAGMA encoding = 'UTF-8'")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = DELETE")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA secure_delete = ON")
            with connection:
                for migration in sql_files(ROOT / "migrations"):
                    migration_hash = hashlib.sha256(migration.read_bytes()).hexdigest()
                    connection.executescript(migration.read_text(encoding="utf-8"))
                    version = int(migration.name.split("_", 1)[0])
                    connection.execute(
                        """
                        INSERT INTO schema_migration(version, filename, sha256)
                        VALUES (?, ?, ?)
                        """,
                        (version, migration.name, migration_hash),
                    )
                for seed in sql_files(ROOT / "seed"):
                    connection.executescript(seed.read_text(encoding="utf-8"))
            connection.execute("VACUUM")
            connection.execute("PRAGMA foreign_keys = ON")
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(f"integrity check failed: {integrity}")
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_keys:
                raise RuntimeError(f"foreign key check failed: {foreign_keys[:5]}")
        finally:
            connection.close()
        os.replace(staged, output)


def write_release_files(output: Path) -> None:
    if output.resolve() != DEFAULT_OUTPUT.resolve():
        return
    digest = sha256(output)
    (ROOT / "universe.db.sha256").write_text(
        f"{digest}  universe.db\n", encoding="utf-8"
    )
    with sqlite3.connect(output) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_schema
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            )
        ]
        row_counts = {
            table: connection.execute(
                f'SELECT count(*) FROM "{table}"'
            ).fetchone()[0]
            for table in tables
        }
        schema_version = connection.execute("PRAGMA user_version").fetchone()[0]
    manifest = {
        "artifact": "universe.db",
        "application_id": f"0x{APPLICATION_ID:08X}",
        "schema_version": schema_version,
        "sha256": digest,
        "sqlite_version": sqlite3.sqlite_version,
        "row_counts": row_counts,
    }
    (ROOT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="database path (default: repository/universe.db)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    build(arguments.output)
    write_release_files(arguments.output)
    print(f"built {arguments.output} ({sha256(arguments.output)})")
