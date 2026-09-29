#!/usr/bin/env python3
"""List archive pages that have not yet reached a successful parse status."""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

from parse_wikipedia_archive import load_archive, sha256

SUCCESS = {"parsed", "parsed_partial", "no_data"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("database", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    manifest, pages = load_archive(args.archive)
    archive_digest = sha256(args.archive)
    with sqlite3.connect(args.database) as connection:
        connection.row_factory = sqlite3.Row
        attempts: dict[str, list[sqlite3.Row]] = {}
        for row in connection.execute(
            """
            SELECT page.source_entry_key, page.status, page.error_text,
                   page.created_at, page.completed_at
            FROM wikipedia_page_parse AS page
            JOIN wikipedia_parse_run AS run USING (run_id)
            WHERE run.archive_sha256 = ?
            ORDER BY page.created_at
            """,
            (archive_digest,),
        ):
            attempts.setdefault(row["source_entry_key"], []).append(row)

    rows = []
    for page in pages:
        history = attempts.get(page["_source_entry_key"], [])
        if any(item["status"] in SUCCESS for item in history):
            continue
        latest = history[-1] if history else None
        status = latest["status"] if latest else "untouched"
        rows.append(
            {
                "sequence_index": page["_sequence_index"],
                "missing_status": status,
                "title": page["title"],
                "source_url": page["_source_url"],
                "source_entry_key": page["_source_entry_key"],
                "attempt_count": len(history),
                "latest_error": (latest["error_text"] or "") if latest else "",
                "latest_attempt_at": (latest["created_at"] or "") if latest else "",
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=rows[0].keys()
            if rows
            else [
                "sequence_index",
                "missing_status",
                "title",
                "source_url",
                "source_entry_key",
                "attempt_count",
                "latest_error",
                "latest_attempt_at",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["missing_status"]] = counts.get(row["missing_status"], 0) + 1
    print(f"archive pages: {manifest['page_count']}")
    print(f"missing pages: {len(rows)}")
    for status, count in sorted(counts.items()):
        print(f"  {status}: {count}")
    print(args.output)


if __name__ == "__main__":
    main()
