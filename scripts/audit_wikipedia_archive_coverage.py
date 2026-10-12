#!/usr/bin/env python3
"""Inventory every revision-pinned page and preserve recoverable research leads.

Read-only database audit; text matches are discovery hints, never review decisions.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sqlite3
from pathlib import Path

from build_alloy_db import ELEMENTS
from parse_wikipedia_archive import load_archive, sha256

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = ROOT / "sources/wikipedia-chemistry-category-snapshot-2026-07-29.zip"
SUCCESS = {"parsed", "parsed_partial", "no_data"}


def read_history(path, digest):
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        tables = {
            r[0]
            for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        pages = [
            dict(r)
            for r in db.execute(
                "SELECT p.* FROM wikipedia_page_parse p JOIN wikipedia_parse_run r USING(run_id) WHERE r.archive_sha256=? ORDER BY p.created_at,p.page_parse_id",
                (digest,),
            )
        ]
        ids = {p["page_parse_id"]: p["source_entry_key"] for p in pages}
        evidence = collections.defaultdict(list)
        for r in db.execute(
            "SELECT * FROM unverified_entity_candidate ORDER BY candidate_id"
        ):
            if r["page_parse_id"] in ids:
                evidence[ids[r["page_parse_id"]]].append(
                    {
                        "relation": "direct",
                        "candidate_id": r["candidate_id"],
                        "name": r["name"],
                        "formula": r["formula"],
                        "kind": r["candidate_kind"],
                    }
                )
        if "wikipedia_candidate_mention" in tables:
            for r in db.execute(
                "SELECT * FROM wikipedia_candidate_mention ORDER BY original_candidate_id"
            ):
                if r["page_parse_id"] in ids:
                    evidence[ids[r["page_parse_id"]]].append(
                        {
                            "relation": "cleanup_mention",
                            "candidate_id": r["canonical_candidate_id"],
                            "name": r["original_name"],
                            "formula": r["original_formula"],
                            "kind": r["original_kind"],
                            "reason": r["merge_reason"],
                        }
                    )
        reviews = collections.defaultdict(list)
        if "wikipedia_candidate_agent_review" in tables:
            for r in db.execute(
                "SELECT * FROM wikipedia_candidate_agent_review ORDER BY created_at,review_id"
            ):
                for key in json.loads(r["source_entry_keys_json"]):
                    reviews[key].append(
                        {
                            "candidate_id": r["candidate_id"],
                            "action": r["action"],
                            "reason": r["reason"],
                        }
                    )
        return pages, evidence, reviews


def text_hints(text):
    # Preserve the exact parameter value, including template syntax and qualifiers.
    formula = [
        {"field": m.group(1), "raw": m.group(2).strip()}
        for m in re.finditer(
            r"(?mi)^\s*\|\s*(Formula|ChemicalFormula|MolecularFormula|SMILES|StdInChI|CASNo)\s*=\s*([^\n]+)",
            text,
        )
    ]
    elements = [
        {"field": m.group(1), "raw": m.group(2)}
        for m in re.finditer(r"(?m)^\s*\|\s*([A-Z][a-z]?)\s*=\s*(\d+)\s*$", text)
        if m.group(1) in ELEMENTS
    ]
    urls = sorted(set(re.findall(r"https?://[^\s<>{}\[\]|]+", text)))
    doi = sorted(
        set(
            m.group(1).strip()
            for m in re.finditer(r"(?i)\|\s*doi\s*=\s*([^|}\n]+)", text)
        )
    )
    signals = sorted(
        {
            word
            for word in (
                "isotope",
                "alloy",
                "crystal",
                "lattice",
                "ceramic",
                "polymorph",
                "mineral",
            )
            if re.search(r"\b" + word + r"s?\b", text, re.I)
        }
    )
    return {
        "identity_parameters": formula + elements,
        "reference_urls": urls,
        "reference_dois": doi,
        "material_signals": signals,
    }


def audit(archive, databases):
    manifest, pages = load_archive(archive)
    digest = sha256(archive)
    history = collections.defaultdict(list)
    evidence = collections.defaultdict(list)
    reviews = collections.defaultdict(list)
    for path in databases:
        attempts, represented, decisions = read_history(path, digest)
        label = (
            path.relative_to(ROOT).as_posix()
            if path.is_relative_to(ROOT)
            else path.name
        )
        for row in attempts:
            history[row["source_entry_key"]].append(
                {
                    "database": label,
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "error": row["error_text"],
                    "submitted_chars": row["submitted_chars"],
                    "content_chars": row["content_chars"],
                }
            )
        for key, rows in represented.items():
            evidence[key].extend({"database": label, **r} for r in rows)
        for key, rows in decisions.items():
            reviews[key].extend({"database": label, **r} for r in rows)
    inventory = []
    for page in pages:
        key = page["_source_entry_key"]
        attempts = sorted(history[key], key=lambda r: (r["created_at"], r["database"]))
        successful = [r for r in attempts if r["status"] in SUCCESS]
        status = (
            successful[-1]["status"]
            if successful
            else attempts[-1]["status"]
            if attempts
            else "unparsed"
        )
        relations = {r["relation"] for r in evidence[key]}
        coverage = (
            "direct_candidates"
            if "direct" in relations
            else "cleanup_mentions_only"
            if relations
            else "no_candidate_evidence"
        )
        hints = text_hints(page["wikitext"])
        identity_signal = bool(hints["identity_parameters"])
        reasons = []
        if not successful:
            reasons.append("parse_incomplete")
        if status == "no_data" and identity_signal:
            reasons.append("no_data_with_identity_parameters")
        if not evidence[key] and identity_signal:
            reasons.append("identity_parameters_without_candidate_evidence")
        if any(r["submitted_chars"] < r["content_chars"] for r in attempts):
            reasons.append("truncated_parse_input")
        if any(r["action"] == "reject" for r in reviews[key]):
            reasons.append("has_rejected_review_history")
        if coverage == "cleanup_mentions_only":
            reasons.append("merged_page_mentions_preserved")
        priority = (
            1
            if identity_signal and (not successful or not evidence[key])
            else 2
            if not successful or reasons
            else 3
        )
        inventory.append(
            {
                "sequence_index": page["_sequence_index"],
                "source_entry_key": key,
                "page_id": page["page_id"],
                "revision_id": page["revision_id"],
                "title": page["title"],
                "revision_url": page["revision_url"],
                "content_sha256": page["_content_sha256"],
                "parse_status": status,
                "coverage": coverage,
                "priority": priority,
                "review_reasons": reasons,
                "attempts": attempts,
                "candidate_evidence": evidence[key],
                "review_history": reviews[key],
                **hints,
            }
        )
    return {
        "archive_sha256": digest,
        "archive_page_count": manifest["page_count"],
        "license": manifest["license"],
        "policy": "All matches are unverified secondary-source discovery leads; primary-source confirmation required. Cleanup-only pages are represented mentions, not missing pages. Historical reject actions do not establish current rejection status.",
        "summary": {
            "parse_status": dict(
                sorted(
                    collections.Counter(r["parse_status"] for r in inventory).items()
                )
            ),
            "coverage": dict(
                sorted(collections.Counter(r["coverage"] for r in inventory).items())
            ),
            "priority": dict(
                sorted(
                    collections.Counter(str(r["priority"]) for r in inventory).items()
                )
            ),
        },
        "pages": inventory,
    }


# Curated selectors inspected against archived text; primary papers require review.
INSPECTED_LEADS = [
    (
        512,
        "Dirubidium",
        "molecule",
        "Rb2",
        "'''Dirubidium'''",
        "10.1088/0953-4075/22/16/005",
        "Recover identity and NIST gas thermochemistry source; distinguish the rubidium trimer mentioned separately.",
    ),
    (
        828,
        "Isocyanic acid",
        "molecule",
        "HNCO",
        "|Formula = HNCO",
        None,
        "Keep isocyanic acid distinct from cyanic acid despite shared elemental formula and aliases.",
    ),
    (
        911,
        "Manganese heptoxide",
        "molecule",
        "Mn2O7",
        "'''Manganese(VII) oxide'''",
        None,
        "Recover molecular identity and separately verify monoclinic solid structure; liquid and solid facts must not be conflated.",
    ),
    (
        1075,
        "Phosphorus pentoxide",
        "molecule_and_polymorphs",
        "P4O10",
        "Phosphorus pentoxide crystallizes",
        "10.1107/S0365110X64001669",
        "Separate molecular hexagonal form from polymeric polymorphs; do not collapse empirical and molecular formulas.",
    ),
    (
        1118,
        "Red phosphorus",
        "elemental_material",
        "P",
        "'''Red phosphorus'''",
        "10.1021/ed021p522",
        "Recover amorphous polymeric material; formula P is not an isolated monatomic molecule.",
    ),
    (
        1189,
        "Tetrabromoauric acid",
        "compound",
        "H[AuBr4]",
        "'''Tetrabromoauric acid'''",
        "10.1021/ic50038a018",
        "Keep neutral acid and tetrabromoaurate conjugate anion distinct.",
    ),
    (
        1207,
        "Triatomic hydrogen",
        "molecule",
        "H3",
        "'''Triatomic hydrogen'''",
        "10.1063/1.456434",
        "Recover neutral molecule separately from trihydrogen cation; verify transient lifetime against primary paper.",
    ),
    (
        1222,
        "White phosphorus",
        "elemental_material",
        "P4",
        "'''White phosphorus'''",
        None,
        "Recover tetraphosphorus material and phase distinctions; source cites ACS and inorganic chemistry references.",
    ),
    (
        739,
        "CrMnFeCoNi alloy",
        "alloy",
        None,
        "The predominant phase was",
        "10.1016/j.msea.2003.10.257",
        "Recover named multicomponent solid-solution alloy; composition basis and experimental state require paper review.",
    ),
    (
        822,
        "Dihydridoiron",
        "molecule",
        "FeH2",
        "* [[iron(II) hydride#dihydridoiron|Dihydridoiron]]",
        None,
        "Recover low-temperature molecule distinctly from high-pressure polymeric hydrides.",
    ),
    (
        822,
        "Iron pentahydride",
        "high_pressure_material",
        "FeH5",
        "* [[Iron pentahydride]]",
        None,
        "Recover polyhydride and verify pressure and structure in cited synthesis paper.",
    ),
    (
        841,
        "Actinium-203",
        "isotope",
        None,
        "|-id=Actinium-203",
        "10.1016/j.physletb.2024.138503",
        "2024 discovery newer than NUBASE2020; inspect paper before adding measurements.",
    ),
    (
        842,
        "Aluminium-20",
        "isotope",
        None,
        "|-id=Aluminium-20",
        "10.1103/hkmy-yfdk",
        "2025 three-proton-emitter discovery; table lower bounds and spin qualifiers must remain qualified.",
    ),
    (
        842,
        "Aluminium-21",
        "isotope",
        None,
        "|-id=Aluminium-21",
        "10.1103/PhysRevC.110.L031301",
        "2024 proton-unbound nucleus spectroscopy; primary-source confirmation required.",
    ),
]


def inspected_leads(archive, report):
    _, pages = load_archive(archive)
    inventory = {r["sequence_index"]: r for r in report["pages"]}
    represented = [e for row in report["pages"] for e in row["candidate_evidence"]]
    leads = []
    for index, name, kind, formula, selector, doi, note in INSPECTED_LEADS:
        page = pages[index]
        row = inventory[index]
        offset = page["wikitext"].index(selector)
        excerpt = page["wikitext"][offset : offset + 700]
        name_matches = [
            e for e in represented if e["name"].casefold() == name.casefold()
        ]
        formula_matches = [
            e for e in represented if formula and e["formula"] == formula
        ]
        leads.append(
            {
                "name": name,
                "candidate_class": kind,
                "discovered_formula": formula,
                "source_entry_key": row["source_entry_key"],
                "page_id": row["page_id"],
                "revision_id": row["revision_id"],
                "revision_url": row["revision_url"],
                "archive_sha256": report["archive_sha256"],
                "review_method": "source_inspection",
                "evidence_text": excerpt,
                "evidence_offset": offset,
                "source_selector": selector,
                "parse_status": row["parse_status"],
                "page_coverage": row["coverage"],
                "global_exact_name_matches": name_matches,
                "global_formula_matches": formula_matches,
                "identity_coverage_note": "Matching formulas do not establish identical species. Exact-name matches may indicate representation on another page.",
                "primary_reference_lead": "https://doi.org/" + doi if doi else None,
                "page_reference_urls": row["reference_urls"],
                "page_reference_dois": row["reference_dois"],
                "followup": note,
                "review_status": "pending_primary_source_confirmation",
            }
        )
    return {
        "archive_sha256": report["archive_sha256"],
        "policy": report["policy"],
        "leads": leads,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--database", type=Path, action="append")
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".build/wiki-subagents/archive-rest"
    )
    args = parser.parse_args()
    report = audit(
        args.archive,
        args.database
        or [
            ROOT / ".build/wikipedia-glm-full-reviewed.db",
            ROOT / "universe-unverified.db",
        ],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with args.output.with_suffix(".csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        fields = [
            "priority",
            "sequence_index",
            "title",
            "source_entry_key",
            "page_id",
            "revision_id",
            "revision_url",
            "parse_status",
            "coverage",
            "review_reasons",
            "identity_parameters",
            "reference_urls",
            "reference_dois",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in sorted(
            report["pages"], key=lambda r: (r["priority"], r["sequence_index"])
        ):
            writer.writerow(
                {
                    k: json.dumps(row[k], ensure_ascii=False)
                    if isinstance(row[k], list)
                    else row[k]
                    for k in fields
                }
            )
    args.output.with_name(args.output.name + ".leads.json").write_text(
        json.dumps(inspected_leads(args.archive, report), indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
