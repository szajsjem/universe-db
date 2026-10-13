#!/usr/bin/env python3
"""Write a deterministic, read-only identity/provenance queue for manual research.

Matches are discovery leads, never automatic merges, corrections or promotion.
Composition equality is not structural or polymorph identity. Text differences
are potential disagreements, not proof that either claim is false.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path
from urllib.parse import urlparse

try:
    from scripts.import_manual_chemistry import formula_composition
except ModuleNotFoundError:
    from import_manual_chemistry import formula_composition

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_name(value: str) -> str:
    """Normalize typography only; keep positions, stereochemistry and charge punctuation."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def composition_key(formula: str | None) -> tuple | None:
    if not formula:
        return None
    try:
        # Whitespace removal is a report-only lead (e.g. HOOC COOH), not an edit
        # of candidate data or permission to reinterpret other formula notation.
        return tuple(sorted(formula_composition("".join(formula.split())).items()))
    except ValueError:
        return None


def compare_identity(entry: dict, target: dict, evidence: set[str]) -> dict:
    expected = tuple(sorted(entry["composition"].items()))
    actual = composition_key(target["formula"])
    composition = (
        "unknown"
        if actual is None
        else "match"
        if actual == expected
        else "disagreement"
    )
    charge = (
        "unknown"
        if target["charge"] is None
        else "match"
        if target["charge"] == entry["charge"]
        else "disagreement"
    )
    return {
        **{
            key: target[key]
            for key in ("id", "name", "kind", "formula", "charge", "origin")
        },
        "evidence": sorted(evidence),
        "composition_status": composition,
        "charge_status": charge,
        "identity_verified": False,
        "source_url": target.get("source_url"),
        "source_title": target.get("source_title"),
        "formula_interpretation": "whitespace-normalized lead"
        if target["formula"] and any(c.isspace() for c in target["formula"])
        else "original formula",
    }


def read_identities(db: sqlite3.Connection) -> list[dict]:
    targets = []
    aliases: dict[str, set[str]] = defaultdict(set)
    for row in db.execute(
        "SELECT entity_id, value FROM alias ORDER BY entity_id, alias_id"
    ):
        aliases["reviewed:" + row[0]].add(normalized_name(row[1]))
    for row in db.execute(
        "SELECT candidate_id, value FROM unverified_candidate_alias ORDER BY candidate_id, alias_index"
    ):
        aliases["candidate:" + row[0]].add(normalized_name(row[1]))
    for row in db.execute("""SELECT e.entity_id, e.name, c.species_kind, c.formula, c.electric_charge, s.url, s.title
                             FROM chemical_species c JOIN entity e ON e.entity_id=c.entity_id
                             JOIN dataset d ON d.dataset_id=e.dataset_id JOIN source s ON s.source_id=d.source_id
                             ORDER BY e.entity_id"""):
        targets.append(
            dict(
                zip(
                    (
                        "id",
                        "name",
                        "kind",
                        "formula",
                        "charge",
                        "source_url",
                        "source_title",
                    ),
                    row,
                )
            )
            | {"origin": "reviewed"}
        )
    for row in db.execute("""SELECT c.candidate_id, c.name, c.candidate_kind, c.formula, c.electric_charge, p.source_url, p.title
                             FROM unverified_entity_candidate c JOIN wikipedia_page_parse p ON p.page_parse_id=c.page_parse_id
                             ORDER BY c.candidate_id"""):
        targets.append(
            dict(
                zip(
                    (
                        "id",
                        "name",
                        "kind",
                        "formula",
                        "charge",
                        "source_url",
                        "source_title",
                    ),
                    row,
                )
            )
            | {"origin": "candidate"}
        )
    for target in targets:
        target["labels"] = aliases[target["origin"] + ":" + target["id"]] | {
            normalized_name(target["name"])
        }
    return targets


def match_entries(entries: list[dict], targets: list[dict]) -> list[dict]:
    by_name: dict[str, list[int]] = defaultdict(list)
    by_formula: dict[tuple, list[int]] = defaultdict(list)
    by_id = {}
    for index, target in enumerate(targets):
        by_id[(target["origin"], target["id"])] = index
        for label in target["labels"]:
            by_name[label].append(index)
        key = composition_key(target["formula"])
        if key:
            by_formula[key].append(index)
    rows = []
    for entry in sorted(entries, key=lambda e: (e["id"], e["slice"])):
        hits: dict[int, set[str]] = defaultdict(set)
        for label in {normalized_name(entry["name"])} | {
            normalized_name(a) for a in entry["aliases"]
        }:
            for index in by_name[label]:
                hits[index].add("name_or_alias")
        for index in by_formula[tuple(sorted(entry["composition"].items()))]:
            hits[index].add("composition_only_lead")
        for candidate in entry.get("existing_candidate_ids", []):
            index = by_id.get(("candidate", candidate))
            if index is not None:
                hits[index].add("declared_candidate_link")
        reviewed_index = by_id.get(("reviewed", entry["id"]))
        if reviewed_index is not None:
            hits[reviewed_index].add("declared_reviewed_id")
        matches = [
            compare_identity(entry, targets[i], evidence)
            for i, evidence in hits.items()
        ]
        matches.sort(key=lambda m: (m["origin"], m["id"]))
        flags = set(entry.get("provenance_flags", []))
        for match in matches:
            if match["origin"] == "candidate" and match["kind"] != entry["kind"]:
                flags.add("candidate_classification_differs")
            if match["composition_status"] == "disagreement":
                flags.add("name_or_link_composition_disagreement")
            if match["charge_status"] == "disagreement":
                flags.add("charge_disagreement")
            if match["composition_status"] == "unknown":
                flags.add("matched_identity_formula_unknown_or_unsupported")
            if match["charge_status"] == "unknown":
                flags.add("matched_identity_charge_unknown")
            if match["evidence"] == ["composition_only_lead"]:
                flags.add("composition_only_identity_leads")
        missing = sorted(
            set(entry.get("existing_candidate_ids", []))
            - {m["id"] for m in matches if m["origin"] == "candidate"}
        )
        if missing:
            flags.add("declared_candidate_missing_from_snapshot")
        state = (
            "existing_reviewed_id"
            if reviewed_index is not None
            else "candidate_identity_review"
            if matches
            else "new_identity_review"
        )
        rows.append(
            {
                "target_id": entry["id"],
                "name": entry["name"],
                "formula": entry["formula"],
                "kind": entry["kind"],
                "scope": entry["scope"],
                "source_slice": entry["slice"],
                "state": state,
                "fact_count": len(entry["facts"]),
                "flags": sorted(flags),
                "missing_candidate_links": missing,
                "matches": matches,
                "review_status": "pending_human_review",
                "source_urls": sorted(
                    {
                        s["url"]
                        for f in entry["facts"]
                        for s in (f.get("sources") or [])
                        if isinstance(s.get("url"), str) and s["url"]
                    }
                ),
            }
        )
    return rows


def differing_claims(entries: list[dict]) -> list[dict]:
    claims: dict[tuple, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for entry in entries:
        for fact in entry["facts"]:
            # Keep letter case and semantic punctuation: these are factual values.
            value = " ".join(fact["value"].split())
            claims[(entry["id"], fact["key"])][value].append(
                {
                    "slice": entry["slice"],
                    "source_urls": sorted(
                        {
                            s["url"]
                            for s in (fact.get("sources") or [])
                            if isinstance(s.get("url"), str) and s["url"]
                        }
                    ),
                }
            )
    return [
        {
            "target_id": key[0],
            "field_key": key[1],
            "classification": "textual_difference_requires_review",
            "claims": [
                {"value": value, "references": sorted(refs, key=lambda r: r["slice"])}
                for value, refs in sorted(values.items())
            ],
        }
        for key, values in sorted(claims.items())
        if len(values) > 1
    ]


def build_report(database: Path, paths: list[Path]) -> dict:
    database_digest = sha256(database)
    entries = []
    inputs = []
    domains: Counter[str] = Counter()
    with closing(
        sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    ) as db:
        for path in sorted(paths):
            source_bytes = path.read_bytes()
            data = json.loads(source_bytes)
            relative = str(path.resolve().relative_to(ROOT))
            fingerprint = hashlib.sha256(source_bytes).hexdigest()
            run_id = f"manual-chemistry:{path.stem}:{fingerprint}"
            imported = (
                db.execute(
                    "SELECT 1 FROM research_run WHERE run_id=?", (run_id,)
                ).fetchone()
                is not None
            )
            inputs.append(
                {
                    "path": relative,
                    "sha256": fingerprint,
                    "imported_in_snapshot": imported,
                }
            )
            for entry in data["entries"]:
                flags = [] if imported else ["source_slice_not_imported_in_snapshot"]
                for fact in entry["facts"]:
                    if not fact.get("sources"):
                        flags.append("missing_fact_citations")
                    for source in fact.get("sources") or []:
                        if any(
                            not source.get(k)
                            for k in (
                                "url",
                                "title",
                                "supporting_text",
                                "retrieved_on",
                                "license_basis",
                            )
                        ):
                            flags.append("incomplete_source_provenance")
                        url = source.get("url", "")
                        parsed = urlparse(url if isinstance(url, str) else "")
                        if parsed.scheme != "https" or not parsed.netloc:
                            flags.append("invalid_source_url")
                        domains[parsed.netloc.casefold() or "<missing>"] += 1
                entries.append(
                    entry
                    | {
                        "slice": relative,
                        "scope": data["scope"],
                        "provenance_flags": flags,
                    }
                )
        rows = match_entries(entries, read_identities(db))
    if sha256(database) != database_digest:
        raise ValueError(
            "Database artifact changed during report generation; retry against one snapshot"
        )
    counts = Counter(row["state"] for row in rows)
    scope_counts = Counter(row["scope"] for row in rows)
    label_groups: dict[str, set[str]] = defaultdict(set)
    formula_groups: dict[tuple, set[str]] = defaultdict(set)
    for entry in entries:
        for name in [entry["name"], *entry["aliases"]]:
            label_groups[normalized_name(name)].add(entry["id"])
        formula_groups[
            (tuple(sorted(entry["composition"].items())), entry["charge"])
        ].add(entry["id"])
    overlaps = [
        {"normalized_name": name, "targets": sorted(ids)}
        for name, ids in sorted(label_groups.items())
        if len(ids) > 1
    ]
    formula_overlaps = [
        {
            "composition": dict(key[0]),
            "charge": key[1],
            "targets": sorted(ids),
            "classification": "composition_not_identity",
        }
        for key, ids in sorted(formula_groups.items())
        if len(ids) > 1
    ]
    return {
        "report_schema_version": 1,
        "data_status": "unverified_review_queue",
        "database": {"artifact": database.name, "sha256": database_digest},
        "generator": {
            "path": "scripts/report_manual_review.py",
            "sha256": sha256(Path(__file__)),
        },
        "source_inputs": inputs,
        "coverage": {
            "slices": len(inputs),
            "targets": len({e["id"] for e in entries}),
            "target_records": len(entries),
            "textual_facts": sum(len(e["facts"]) for e in entries),
            "states": dict(sorted(counts.items())),
            "scopes": dict(sorted(scope_counts.items())),
            "citation_domains": dict(sorted(domains.items())),
            "targets_with_flags": len(
                {row["target_id"] for row in rows if row["flags"]}
            ),
        },
        "manual_name_overlap_groups": overlaps,
        "manual_composition_overlap_groups": formula_overlaps,
        "differing_textual_claims": differing_claims(entries),
        "queue": rows,
        "policy": "Read-only discovery leads; no merging, averaging, promotion or proof of identity. Human source/license/structure review required.",
    }


def markdown(report: dict) -> str:
    coverage = report["coverage"]
    lines = [
        "# Manual chemistry identity review queue",
        "",
        report["policy"],
        "",
        f"Snapshot SHA-256: `{report['database']['sha256']}`.",
        "",
        f"{coverage['targets']} targets; {coverage['textual_facts']} textual facts; {coverage['slices']} source slices.",
        "",
        "| Target | Formula | Queue state | Review flags | Identity leads |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report["queue"]:
        cells = [
            row["target_id"],
            row["formula"],
            row["state"],
            ", ".join(row["flags"]) or "none",
            str(len(row["matches"])),
        ]
        lines.append(
            "| "
            + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in cells)
            + " |"
        )
    lines += [
        "",
        "The JSON companion contains each match's original identity, formula, charge, evidence and source citations.",
        "Composition-only leads can be isomers, polymorphs, mixtures or wrongly classified candidates; they are never merged.",
        "An empty flag list does not establish scientific review or approval.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=ROOT / "universe-unverified.db"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/manual-review-queue.json"
    )
    args = parser.parse_args()
    report = build_report(
        args.database, sorted((ROOT / "sources/manual-chemistry").glob("*.json"))
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8"
    )
    args.output.with_suffix(".md").write_text(markdown(report), encoding="utf8")
    print(json.dumps(report["coverage"], sort_keys=True))
