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
UNVERIFIED_OUTPUT = ROOT / "universe-unverified.db"
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


def database_metadata(path: Path) -> dict:
    with sqlite3.connect(path) as connection:
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
    return {
        "application_id": f"0x{APPLICATION_ID:08X}",
        "row_counts": row_counts,
        "schema_version": schema_version,
        "sha256": sha256(path),
    }


def unverified_metadata(path: Path, base_digest: str) -> dict:
    with sqlite3.connect(path) as connection:
        stored_base_digest = connection.execute(
            """
            SELECT value
            FROM database_metadata
            WHERE key = 'unverified_base_sha256'
            """
        ).fetchone()
        if stored_base_digest is None or stored_base_digest[0] != base_digest:
            raise RuntimeError(
                "universe-unverified.db is not based on the current universe.db"
            )
        articles_reached, articles_total = connection.execute(
            """
            SELECT
                COALESCE(MAX(page.sequence_index) + 1, 0),
                COALESCE(MAX(run.archive_page_count), 0)
            FROM wikipedia_parse_run AS run
            LEFT JOIN wikipedia_page_parse AS page USING (run_id)
            """
        ).fetchone()
        status_counts = dict(
            connection.execute(
                """
                SELECT status, count(*)
                FROM wikipedia_page_parse
                GROUP BY status
                ORDER BY status
                """
            )
        )
    metadata = database_metadata(path)
    metadata.update(
        {
            "artifact": path.name,
            "base_artifact_sha256": base_digest,
            "data_status": "unverified",
            "wikipedia_parsing": {
                "articles_reached": articles_reached,
                "articles_total": articles_total,
                "page_attempt_status_counts": status_counts,
                "status": f"{articles_reached}/{articles_total}",
            },
        }
    )
    return metadata


def write_release_files(output: Path) -> None:
    if output.resolve() != DEFAULT_OUTPUT.resolve():
        return
    manifest = database_metadata(output)
    manifest["artifact"] = output.name
    digest = manifest["sha256"]
    (ROOT / "universe.db.sha256").write_text(
        f"{digest}  universe.db\n", encoding="utf-8"
    )
    if UNVERIFIED_OUTPUT.exists():
        companion = unverified_metadata(UNVERIFIED_OUTPUT, digest)
        unverified_digest = companion["sha256"]
        (ROOT / "universe-unverified.db.sha256").write_text(
            f"{unverified_digest}  universe-unverified.db\n", encoding="utf-8"
        )
        manifest["companion_artifacts"] = [companion]
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
