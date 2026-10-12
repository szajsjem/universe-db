#!/usr/bin/env python3
"""Collect local Wikipedia triage and inspected leads without changing candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

if __package__:
    from .export_release import snapshot
else:
    from export_release import snapshot

ROOT = Path(__file__).resolve().parents[1]
REPORTS = (
    (
        "filtered.json",
        "candidate_results",
        "filtered_candidates",
        "deterministic_triage",
    ),
    ("filtered.findings.json", "findings", "filtered_findings", "source_inspection"),
    ("archive-rest.json", "pages", "archive_coverage", "deterministic_triage"),
    ("archive-rest.leads.json", "leads", "archive_leads", "source_inspection"),
    ("full-rest.json", "matches", "full_dump_title_discovery", "title_discovery"),
    ("full-rest.reads.json", "pages", "full_dump_page_reads", "local_page_read"),
    ("full-rest.findings.json", "findings", "full_dump_findings", "source_inspection"),
    (
        "primary-followup.json",
        "findings",
        "primary_source_followup",
        "primary_source_check",
    ),
)
SCHEMA = """
CREATE TABLE unverified_wikipedia_source_audit(
 audit_id TEXT PRIMARY KEY,input_filename TEXT NOT NULL,input_sha256 TEXT NOT NULL,
 scope TEXT NOT NULL,default_method TEXT NOT NULL,record_count INTEGER NOT NULL,
 metadata_json TEXT NOT NULL,review_status TEXT NOT NULL CHECK(review_status='pending_human_review')) STRICT;
CREATE TABLE unverified_wikipedia_source_audit_result(
 audit_id TEXT NOT NULL REFERENCES unverified_wikipedia_source_audit,
 position INTEGER NOT NULL,subject_id TEXT,title TEXT,source_entry_key TEXT,
 source_url TEXT,review_method TEXT NOT NULL,input_json TEXT NOT NULL,
 PRIMARY KEY(audit_id,position)) STRICT;
CREATE INDEX unverified_wikipedia_source_audit_subject
 ON unverified_wikipedia_source_audit_result(subject_id);
"""


def collect(base, report_dir, output, specifications=REPORTS):
    """Atomic copied artifact; input reports retain their original source context."""
    documents = []
    for filename, key, scope, method in specifications:
        path = Path(report_dir) / filename
        raw = path.read_bytes()
        document = json.loads(raw)
        if document.get("status") in ("running", "partial", "in_progress", "scanning"):
            raise ValueError(f"Incomplete report: {filename}")
        records = document.get(key)
        if not isinstance(records, list):
            raise ValueError(f"Expected record list {key!r} in {filename}")
        metadata = {name: value for name, value in document.items() if name != key}
        documents.append(
            (
                filename,
                scope,
                method,
                hashlib.sha256(raw).hexdigest(),
                metadata,
                records,
            )
        )
    output = Path(output)
    if Path(base).resolve() == output.resolve():
        raise ValueError("Audit output must differ from source database")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=output.parent, suffix=".db", delete=False
    ) as file:
        staged = Path(file.name)
    try:
        snapshot(Path(base), staged)
        with closing(sqlite3.connect(staged)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            original_candidates = db.execute(
                "SELECT count(*) FROM unverified_entity_candidate"
            ).fetchone()[0]
            db.executescript(SCHEMA)
            with db:
                for filename, scope, method, digest, metadata, records in documents:
                    db.execute(
                        "INSERT INTO unverified_wikipedia_source_audit VALUES (?,?,?,?,?,?,?,?)",
                        (
                            filename,
                            filename,
                            digest,
                            scope,
                            method,
                            len(records),
                            json.dumps(metadata, sort_keys=True),
                            "pending_human_review",
                        ),
                    )
                    for position, row in enumerate(records):
                        if not isinstance(row, dict):
                            raise ValueError("Audit records must be objects")
                        urls = row.get("source_urls") or []
                        if isinstance(urls, str):
                            urls = [urls]
                        entry_keys = row.get("source_entry_keys") or []
                        if isinstance(entry_keys, str):
                            entry_keys = [entry_keys]
                        url = (
                            row.get("revision_url")
                            or row.get("source_url")
                            or (urls[0] if urls else None)
                        )
                        subject = (
                            row.get("candidate_id")
                            or row.get("page_id")
                            or row.get("id")
                        )
                        db.execute(
                            "INSERT INTO unverified_wikipedia_source_audit_result VALUES (?,?,?,?,?,?,?,?)",
                            (
                                filename,
                                position,
                                None if subject is None else str(subject),
                                row.get("title") or row.get("name"),
                                row.get("source_entry_key")
                                or (entry_keys[0] if entry_keys else None),
                                url,
                                row.get("review_method") or method,
                                json.dumps(row, sort_keys=True),
                            ),
                        )
                if (
                    db.execute(
                        "SELECT count(*) FROM unverified_entity_candidate"
                    ).fetchone()[0]
                    != original_candidates
                ):
                    raise ValueError("Source audit changed candidate queue")
                if db.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("Audit foreign key validation failed")
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Audit integrity validation failed")
            counts = dict(
                db.execute(
                    "SELECT scope,record_count FROM unverified_wikipedia_source_audit"
                )
            )
        os.replace(staged, output)
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        output.with_suffix(output.suffix + ".sha256").write_text(
            digest + "  " + output.name + "\n", encoding="utf-8"
        )
        summary = {
            "database": str(output),
            "sha256": digest,
            "input_database": str(base),
            "candidate_count": original_candidates,
            "reports": counts,
            "review_status": "pending_human_review",
            "openrouter_calls": 0,
            "policy": "Triage and source inspection are discovery/review aids. No candidate actions or scientific promotions were applied.",
        }
        output.with_suffix(".summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(summary, indent=2))
        return summary
    finally:
        staged.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", type=Path, default=ROOT / ".build/wikipedia-codex-review-base.db"
    )
    parser.add_argument(
        "--report-dir", type=Path, default=ROOT / ".build/wiki-subagents"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".build/wikipedia-codex-source-audit.db"
    )
    args = parser.parse_args()
    collect(args.base, args.report_dir, args.output)
