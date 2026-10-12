#!/usr/bin/env python3
"""Export a versioned Universe release with current research snapshots."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from .build_alloy_db import build as build_alloys
    from .build_db import build, sha256
    from .build_element_evidence import build as build_elements
    from .build_isotope_evidence import build as build_isotopes
    from .validate_db import validate
else:
    from build_alloy_db import build as build_alloys
    from build_db import build, sha256
    from build_element_evidence import build as build_elements
    from build_isotope_evidence import build as build_isotopes
    from validate_db import validate

ROOT = Path(__file__).resolve().parents[1]
RESEARCH_PREFIXES = ("unverified_", "wikipedia_", "research_")


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def snapshot(source: Path, destination: Path):
    """SQLite backup sees one consistent snapshot, including committed WAL data."""
    if not source.is_file():
        raise FileNotFoundError(source)
    with closing(
        sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
    ) as src:
        with closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)


def inspect(path: Path):
    with closing(sqlite3.connect(path)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError(f"SQLite integrity check failed: {path.name}")
        violations = db.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise ValueError(f"foreign key check failed: {path.name}: {violations[:3]}")
        counts = {
            name: db.execute(f"SELECT count(*) FROM {quote(name)}").fetchone()[0]
            for (name,) in db.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        }
        result = {
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
            "schema_version": db.execute("PRAGMA user_version").fetchone()[0],
            "application_id": db.execute("PRAGMA application_id").fetchone()[0],
            "row_counts": counts,
        }
        if "wikipedia_candidate_agent_review" in counts:
            result["successful_candidate_reviews"] = db.execute(
                "SELECT count(DISTINCT candidate_id) FROM wikipedia_candidate_agent_review WHERE action!='error'"
            ).fetchone()[0]
        return result


def import_research(destination: Path, source: Path, base_digest: str):
    with closing(sqlite3.connect(source)) as src:
        recorded = src.execute(
            "SELECT value FROM database_metadata WHERE key='unverified_base_sha256'"
        ).fetchone()
        if recorded is None or recorded[0] != base_digest:
            raise ValueError(
                "Research database base digest does not match rebuilt reviewed database"
            )
        schemas = src.execute(
            "SELECT name,sql FROM sqlite_schema WHERE type='table' ORDER BY rowid"
        ).fetchall()
    with closing(sqlite3.connect(destination)) as dst:
        dst.execute("PRAGMA foreign_keys=ON")
        dst.execute("ATTACH DATABASE ? AS incoming", (str(source),))
        with dst:
            dst.execute("PRAGMA defer_foreign_keys=ON")
            for name, sql in schemas:
                if not name.startswith(RESEARCH_PREFIXES):
                    continue
                exists = dst.execute(
                    "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (name,)
                ).fetchone()
                if not exists:
                    dst.execute(sql)
                if dst.execute(f"SELECT count(*) FROM {quote(name)}").fetchone()[0]:
                    raise ValueError(
                        f"Refusing to overwrite populated research table: {name}"
                    )
                columns = [
                    row[1]
                    for row in dst.execute(f"PRAGMA incoming.table_info({quote(name)})")
                ]
                names = ",".join(map(quote, columns))
                dst.execute(
                    f"INSERT INTO main.{quote(name)} ({names}) SELECT {names} FROM incoming.{quote(name)}"
                )
        dst.execute("DETACH DATABASE incoming")


def prefixed_schema(sql: str, names: dict[str, str]):
    # Replace table/view references, never equally named columns (e.g. note).
    pattern = r'\b(CREATE TABLE|CREATE VIEW|REFERENCES|FROM|JOIN)\s+("?[A-Za-z_][A-Za-z_0-9]*"?)'

    def replace(match):
        name = match[2].strip('"')
        return match[1] + " " + quote(names.get(name, name))

    result = re.sub(pattern, replace, sql, flags=re.IGNORECASE)
    if re.match(r"CREATE\s+(?:UNIQUE\s+)?INDEX\b", sql, re.IGNORECASE):
        result = re.sub(
            r'\b(CREATE\s+(?:UNIQUE\s+)?INDEX|ON)\s+("?[A-Za-z_][A-Za-z_0-9]*"?)',
            replace,
            result,
            flags=re.IGNORECASE,
        )
    return result


def import_alloys(destination: Path, source: Path, prefix="unverified_alloy_"):
    with closing(sqlite3.connect(source)) as src:
        schemas = src.execute(
            "SELECT type,name,sql FROM sqlite_schema WHERE type IN ('table','view','index') AND name NOT LIKE 'sqlite_%' ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'view' THEN 1 ELSE 2 END,rowid"
        ).fetchall()
    names = {name: prefix + name for _, name, _ in schemas}
    with closing(sqlite3.connect(destination)) as dst:
        dst.execute("PRAGMA foreign_keys=ON")
        dst.execute("ATTACH DATABASE ? AS incoming", (str(source),))
        with dst:
            dst.execute("PRAGMA defer_foreign_keys=ON")
            for kind, name, sql in schemas:
                dst.execute(prefixed_schema(sql, names))
                if kind == "table":
                    dst.execute(
                        f"INSERT INTO main.{quote(names[name])} SELECT * FROM incoming.{quote(name)}"
                    )
        dst.execute("DETACH DATABASE incoming")


def export_release(version: str, output_dir: Path, wikipedia: Path, archive=True):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", version) or version in {
        ".",
        "..",
    }:
        raise ValueError("Version must be a plain filename label")
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / version
    archive_path = output_dir / f"universe-{version}.zip"
    if target.exists() or (archive and archive_path.exists()):
        raise FileExistsError(
            f"Release already exists: {version}; choose a new version"
        )
    with tempfile.TemporaryDirectory(prefix="release-", dir=output_dir) as temporary:
        stage = Path(temporary)
        reviewed = stage / "universe-reviewed.db"
        build(reviewed)
        failures = validate(reviewed)
        if failures:
            raise ValueError(
                "Reviewed database validation failed: " + "; ".join(failures[:5])
            )
        base_digest = sha256(reviewed)
        wikipedia_snapshot = stage / "universe-wikipedia.db"
        snapshot(wikipedia, wikipedia_snapshot)
        inspect(wikipedia_snapshot)
        failures = validate(wikipedia_snapshot)
        if failures:
            raise ValueError(
                "Research database validation failed: " + "; ".join(failures[:5])
            )
        alloys = stage / "alloys.db"
        build_alloys(alloys)
        elements = stage / "elements.db"
        build_elements(elements)
        isotopes = stage / "isotopes.db"
        build_isotopes(isotopes)
        research = stage / "universe-unverified.db"
        snapshot(reviewed, research)
        import_research(research, wikipedia_snapshot, base_digest)
        import_alloys(research, alloys)
        import_alloys(research, elements, prefix="")
        import_alloys(research, isotopes, prefix="")
        with closing(sqlite3.connect(research)) as db:
            with db:
                db.executemany(
                    "INSERT OR REPLACE INTO database_metadata(key,value) VALUES (?,?)",
                    [
                        ("release_version", version),
                        (
                            "release_data_status",
                            "unverified_research_with_reviewed_reference_core",
                        ),
                        ("reviewed_base_sha256", base_digest),
                        ("unverified_base_sha256", base_digest),
                        ("alloy_review_status", "pending_human_review"),
                        ("element_evidence_review_status", "pending_human_review"),
                        ("isotope_evidence_review_status", "pending_human_review"),
                    ],
                )
        failures = validate(research)
        if failures:
            raise ValueError(
                "Unverified database validation failed: " + "; ".join(failures[:5])
            )
        combined = stage / "universe.db"
        snapshot(research, combined)
        with closing(sqlite3.connect(combined)) as db:
            with db:
                db.execute(
                    "UPDATE database_metadata SET value='reviewed_core_with_unverified_research' WHERE key='release_data_status'"
                )
        failures = validate(combined)
        if failures:
            raise ValueError(
                "Combined database validation failed: " + "; ".join(failures[:5])
            )
        artifacts = {}
        statuses = {
            "universe-reviewed.db": "reviewed",
            "universe-unverified.db": "unverified",
            "universe-wikipedia.db": "unverified_wikipedia_snapshot",
            "alloys.db": "pending_human_review",
            "elements.db": "pending_human_review",
            "isotopes.db": "pending_human_review",
            "universe.db": "reviewed_core_with_unverified_research",
        }
        for name, status in statuses.items():
            details = inspect(stage / name)
            details["data_status"] = status
            artifacts[name] = details
            (stage / (name + ".sha256")).write_text(
                f"{details['sha256']}  {name}\n", encoding="utf-8"
            )
        manifest = {
            "version": version,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "reviewed_base_sha256": base_digest,
            "research_source": str(wikipedia.resolve()),
            "artifacts": artifacts,
            "review_boundary": "AI-reviewed Wikipedia and imported alloy/element/isotope evidence remain unverified; no automatic promotion.",
            "full_wikipedia_dump_included": False,
        }
        (stage / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (stage / "README.txt").write_text(
            "Universe release " + version + "\n\n"
            "universe.db: combined database; reviewed scientific core plus research tables.\n"
            "universe-reviewed.db: reviewed core only, rebuilt from migrations and seed.\n"
            "universe-wikipedia.db: consistent snapshot of current Wikipedia candidates and source audits, with their reference core.\n"
            "universe-unverified.db: all pending Wikipedia/alloy/element/isotope research with its reviewed reference core.\n"
            "alloys.db: sourced alloy reference, pending human review.\n"
            "elements.db: sourced elemental properties, pending human review.\n"
            "Elemental research tables begin unverified_element_.\n"
            "isotopes.db: full evaluated NIST/AME/NUBASE isotope reference, pending human review.\n"
            "Isotope research tables begin unverified_isotope_. Source estimates stay flagged.\n"
            "In universe.db, alloy tables/views begin unverified_alloy_. Wikipedia candidates\n"
            "remain in unverified_* tables; wikipedia_* tables retain provenance and audit.\n"
            "Model decisions do not constitute scientific verification. NULL means unknown.\n"
            "Manifest records checksums, row counts and input identity. Full Wikipedia is not bundled.\n",
            encoding="utf-8",
        )
        os.rename(stage, target)
    if archive:
        with tempfile.NamedTemporaryFile(
            prefix="release-", suffix=".zip", dir=output_dir, delete=False
        ) as file:
            temporary_zip = Path(file.name)
        try:
            with zipfile.ZipFile(
                temporary_zip, "w", compression=zipfile.ZIP_DEFLATED
            ) as package:
                for file in sorted(target.iterdir()):
                    package.write(file, arcname=f"{version}/{file.name}")
            os.replace(temporary_zip, archive_path)
            archive_path.with_suffix(".zip.sha256").write_text(
                f"{sha256(archive_path)}  {archive_path.name}\n", encoding="utf-8"
            )
        finally:
            temporary_zip.unlink(missing_ok=True)
    print(f"Exported {target}")
    if archive:
        print(f"Archive: {archive_path}")
    return target


if __name__ == "__main__":
    latest_review = next(
        (
            path
            for path in (
                ROOT / ".build/wikipedia-codex-source-audit.db",
                ROOT / ".build/wikipedia-glm-full-reviewed.db",
                ROOT / "universe-unverified.db",
            )
            if path.exists()
        ),
        ROOT / "universe-unverified.db",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version", default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist/releases")
    parser.add_argument(
        "--wikipedia-db",
        type=Path,
        default=latest_review
        if latest_review.exists()
        else ROOT / "universe-unverified.db",
    )
    parser.add_argument("--no-zip", action="store_true")
    args = parser.parse_args()
    export_release(args.version, args.output_dir, args.wikipedia_db, not args.no_zip)
