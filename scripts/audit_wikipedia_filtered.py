"""Read-only, exhaustive computational triage of the filtered Wikipedia queue.

These checks prioritize source review; they do not authenticate scientific claims.
Source snippets retain their revision URL and CC-BY-SA-4.0 attribution.
"""

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from scripts.clean_wikipedia_candidates import formula_charge, normalize_text
from scripts.parse_wikipedia_archive import load_archive


def quote_present(quote, documents):
    normalized = normalize_text(quote)
    return bool(normalized) and any(normalized in document for document in documents)


def audit(database, archive):
    manifest, pages = load_archive(archive)
    pages = {page["_source_entry_key"]: page for page in pages}
    documents = {key: normalize_text(page["wikitext"]) for key, page in pages.items()}
    db = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    tables = [
        "unverified_entity_candidate",
        "unverified_candidate_alias",
        "unverified_candidate_composition",
        "unverified_candidate_fact",
        "unverified_candidate_relation",
        "unverified_candidate_fact_condition",
        "wikipedia_candidate_mention",
        "wikipedia_candidate_agent_review",
        "unverified_candidate_derived_fact",
    ]
    rows = {
        table: [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY 1,2")]
        for table in tables
    }
    parsed = {
        row["page_parse_id"]: dict(row)
        for row in db.execute("SELECT * FROM wikipedia_page_parse")
    }
    children = {}
    for table in tables[1:]:
        grouped = defaultdict(list)
        for row in rows[table]:
            key = (
                row.get("canonical_candidate_id")
                if table == "wikipedia_candidate_mention"
                else row.get("candidate_id")
            )
            grouped[key].append(row)
        children[table] = grouped
    conditions = defaultdict(list)
    for row in rows["unverified_candidate_fact_condition"]:
        conditions[row["candidate_fact_id"]].append(row)
    identity_groups = defaultdict(list)
    alias_groups = defaultdict(set)
    for candidate in rows[tables[0]]:
        identity_groups[normalize_text(candidate["name"])].append(candidate)
        alias_groups[normalize_text(candidate["name"])].add(candidate["candidate_id"])
    for alias in rows["unverified_candidate_alias"]:
        alias_groups[normalize_text(alias["value"])].add(alias["candidate_id"])
    results = []
    for candidate in rows[tables[0]]:
        cid = candidate["candidate_id"]
        mentions = children["wikipedia_candidate_mention"][cid]
        keys = sorted(
            {
                parsed[pid]["source_entry_key"]
                for pid in [candidate["page_parse_id"]]
                + [m["page_parse_id"] for m in mentions]
            }
        )
        source_documents = [documents[key] for key in keys if key in documents]
        flags = []
        if any(key not in pages for key in keys):
            flags.append("source_entry_missing_from_pinned_archive")
        if not quote_present(candidate["evidence_text"], source_documents):
            flags.append("candidate_evidence_not_verbatim_after_normalization")
        if any(
            parsed[pid]["submitted_chars"] < parsed[pid]["content_chars"]
            for pid in [candidate["page_parse_id"]]
            + [m["page_parse_id"] for m in mentions]
        ):
            flags.append("source_parser_received_partial_page")
        charge = formula_charge(candidate["formula"])
        if (
            charge is not None
            and candidate["electric_charge"] is not None
            and charge != candidate["electric_charge"]
        ):
            flags.append("formula_charge_disagrees_with_electric_charge")
        if candidate["candidate_kind"] == "ion" and candidate["electric_charge"] == 0:
            flags.append("ion_has_zero_charge")
        if (
            candidate["candidate_kind"] == "element"
            and candidate["formula"]
            and not re.fullmatch("[A-Z][a-z]?", candidate["formula"])
        ):
            flags.append("element_formula_is_not_single_symbol")
        if (
            re.search(
                r"\b(method|algorithm|software|equation|standard test|plot)\b",
                candidate["name"],
                re.I,
            )
            and candidate["candidate_kind"] != "reaction"
        ):
            flags.append("possible_nonphysical_entity_name")
        if "\ufffd" in candidate["name"]:
            flags.append("replacement_character_in_identity")
        peers = identity_groups[normalize_text(candidate["name"])]
        if len(peers) > 1:
            flags.append("shared_normalized_name_needs_identity_review")
        aliases = children["unverified_candidate_alias"][cid]
        alias_peer_ids = (
            sorted(
                set().union(
                    *(alias_groups[normalize_text(alias["value"])] for alias in aliases)
                )
                - {cid}
            )
            if aliases
            else []
        )
        if alias_peer_ids:
            flags.append("shared_alias_needs_identity_review")
        mention_checks = [
            {
                "original_candidate_id": mention["original_candidate_id"],
                "original_kind": mention["original_kind"],
                "original_name": mention["original_name"],
                "source_entry_key": parsed[mention["page_parse_id"]][
                    "source_entry_key"
                ],
                "evidence_matches": quote_present(
                    mention["original_evidence_text"],
                    [
                        documents.get(
                            parsed[mention["page_parse_id"]]["source_entry_key"], ""
                        )
                    ],
                ),
            }
            for mention in mentions
        ]
        facts = children["unverified_candidate_fact"][cid]
        fact_checks = []
        for fact in facts:
            found = quote_present(fact["evidence_text"], source_documents)
            fact_checks.append(
                {
                    "candidate_fact_id": fact["candidate_fact_id"],
                    "field_key": fact["field_key"],
                    "evidence_matches": found,
                    "condition_count": len(conditions[fact["candidate_fact_id"]]),
                    "unit_text": fact["unit_text"],
                }
            )
        if any(not check["evidence_matches"] for check in fact_checks):
            flags.append("fact_evidence_not_verbatim_after_normalization")
        if any(
            f["value_decimal_text"] is not None and not f["unit_text"] for f in facts
        ):
            flags.append("numeric_fact_without_unit_text")
        if any(
            f["value_decimal_text"] is not None
            and not conditions[f["candidate_fact_id"]]
            for f in facts
        ):
            flags.append("numeric_fact_without_explicit_conditions")
        component_checks = [
            {
                "component_index": component["component_index"],
                "evidence_matches": quote_present(
                    component["evidence_text"], source_documents
                ),
            }
            for component in children["unverified_candidate_composition"][cid]
        ]
        relation_checks = [
            {
                "relation_id": relation["relation_id"],
                "evidence_matches": quote_present(
                    relation["evidence_text"], source_documents
                ),
            }
            for relation in children["unverified_candidate_relation"][cid]
        ]
        if any(not check["evidence_matches"] for check in component_checks):
            flags.append("composition_evidence_not_verbatim_after_normalization")
        if any(not check["evidence_matches"] for check in relation_checks):
            flags.append("relation_evidence_not_verbatim_after_normalization")
        citations = {
            key: len(
                re.findall(r"<ref\b|\bdoi\s*=|\bpmid\s*=", pages[key]["wikitext"], re.I)
            )
            for key in keys
            if key in pages
        }
        if not any(citations.values()):
            flags.append("attached_pages_have_no_detected_reference_markup")
        reviews = children["wikipedia_candidate_agent_review"][cid]
        results.append(
            {
                "review_method": "deterministic_triage",
                "candidate_id": cid,
                "name": candidate["name"],
                "kind": candidate["candidate_kind"],
                "formula": candidate["formula"],
                "source_entry_keys": keys,
                "source_urls": [
                    pages[key]["revision_url"] for key in keys if key in pages
                ],
                "flags": sorted(flags),
                "fact_checks": fact_checks,
                "composition_checks": component_checks,
                "relation_checks": relation_checks,
                "alias_count": len(children["unverified_candidate_alias"][cid]),
                "mention_count": len(mentions),
                "mention_checks": mention_checks,
                "alias_identity_peer_ids": alias_peer_ids,
                "derived_fact_count": len(
                    children["unverified_candidate_derived_fact"][cid]
                ),
                "prior_agent_reviews": [
                    {
                        "action": r["action"],
                        "reason": r["reason"],
                        "review_id": r["review_id"],
                    }
                    for r in reviews
                ],
                "identity_peer_ids": [
                    p["candidate_id"] for p in peers if p["candidate_id"] != cid
                ],
                "reference_markup_counts": citations,
                "proposed_action": "inspect_source_and_primary_evidence"
                if flags
                else "retain_unverified_secondary_source_lead",
            }
        )
    db.close()
    return {
        "algorithm": "filtered-wikipedia-triage-v1",
        "scope": "exhaustive computational checks; not exhaustive manual scientific review",
        "database": str(database),
        "archive": str(archive),
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "license": manifest.get("license_spdx_id", "CC-BY-SA-4.0"),
        "counts": {table: len(items) for table, items in rows.items()},
        "candidate_kind_counts": dict(
            Counter(row["candidate_kind"] for row in rows[tables[0]])
        ),
        "flag_counts": dict(
            sorted(Counter(flag for row in results for flag in row["flags"]).items())
        ),
        "prior_review_action_counts": dict(
            Counter(row["action"] for row in rows["wikipedia_candidate_agent_review"])
        ),
        "candidate_results": results,
        "limitations": [
            "Quotation mismatch is a search flag, not proof of unsupported content: markup, paraphrase, ellipses and rewritten evidence can differ.",
            "Reference markup is page-wide and does not establish which citation supports a candidate.",
            "No measurement is promoted; every row still requires suitable primary/evaluated evidence.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=Path(".build/wikipedia-glm-full-reviewed.db")
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=Path("sources/wikipedia-chemistry-category-snapshot-2026-07-29.zip"),
    )
    parser.add_argument(
        "--output", type=Path, default=Path(".build/wiki-subagents/filtered.json")
    )
    args = parser.parse_args()
    result = audit(args.database, args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"counts": result["counts"], "flag_counts": result["flag_counts"]}, indent=2
        )
    )


if __name__ == "__main__":
    main()
