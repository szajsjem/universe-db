from __future__ import annotations

import unittest

from scripts.report_manual_review import (
    composition_key,
    differing_claims,
    match_entries,
    normalized_name,
)


def entry() -> dict:
    return {
        "id": "chem:ethylene_carbonate",
        "name": "Ethylene carbonate",
        "formula": "C3H4O3",
        "kind": "molecule",
        "charge": 0,
        "composition": {"C": 3, "H": 4, "O": 3},
        "aliases": [],
        "existing_candidate_ids": [],
        "facts": [],
        "slice": "one.json",
        "scope": "batteries",
    }


def target(
    name: str = "Pyruvic acid", charge: int | None = 0, formula: str | None = "C3H4O3"
) -> dict:
    return {
        "id": "candidate:other",
        "name": name,
        "kind": "molecule",
        "formula": formula,
        "charge": charge,
        "origin": "candidate",
        "labels": {normalized_name(name)},
    }


class ManualReviewReportTest(unittest.TestCase):
    def test_equal_composition_does_not_merge_distinct_molecules(self) -> None:
        row = match_entries([entry()], [target()])[0]
        self.assertIn("composition_only_identity_leads", row["flags"])
        self.assertEqual("chem:ethylene_carbonate", row["target_id"])
        self.assertFalse(row["matches"][0]["identity_verified"])
        self.assertEqual("Pyruvic acid", row["matches"][0]["name"])

    def test_named_charge_disagreement_is_retained(self) -> None:
        row = match_entries([entry()], [target("Ethylene carbonate", -1)])[0]
        self.assertIn("charge_disagreement", row["flags"])
        self.assertEqual(-1, row["matches"][0]["charge"])

    def test_formula_missing_or_hydrate_notation_remains_unknown(self) -> None:
        for formula in (None, "C3H4O3.H2O"):
            row = match_entries(
                [entry()], [target("Ethylene carbonate", None, formula)]
            )[0]
            self.assertIn(
                "matched_identity_formula_unknown_or_unsupported", row["flags"]
            )
            self.assertEqual("unknown", row["matches"][0]["composition_status"])

    def test_names_preserve_position_and_stereochemistry(self) -> None:
        self.assertNotEqual(
            normalized_name("1,2-propanediol"), normalized_name("1,3-propanediol")
        )
        self.assertNotEqual(
            normalized_name("cis-butene"), normalized_name("trans-butene")
        )
        self.assertEqual(
            normalized_name("  Ethylene   Carbonate "),
            normalized_name("ethylene carbonate"),
        )

    def test_conflicting_text_preserves_both_sources_and_values(self) -> None:
        first = entry() | {
            "facts": [
                {
                    "key": "application",
                    "value": "First source claim",
                    "sources": [{"url": "https://one.example/"}],
                }
            ]
        }
        second = entry() | {
            "slice": "two.json",
            "facts": [
                {
                    "key": "application",
                    "value": "Different source claim",
                    "sources": [{"url": "https://two.example/"}],
                }
            ],
        }
        result = differing_claims([first, second])
        self.assertEqual(1, len(result))
        self.assertEqual(
            {"First source claim", "Different source claim"},
            {claim["value"] for claim in result[0]["claims"]},
        )
        self.assertEqual(2, len(result[0]["claims"]))

    def test_missing_citations_and_dangling_links_stay_visible(self) -> None:
        data = entry() | {
            "existing_candidate_ids": ["missing"],
            "provenance_flags": ["missing_fact_citations"],
            "facts": [{"key": "formula", "value": "C3H4O3"}],
        }
        row = match_entries([data], [])[0]
        self.assertIn("missing_fact_citations", row["flags"])
        self.assertEqual(["missing"], row["missing_candidate_links"])
        self.assertEqual([], row["source_urls"])

    def test_condensed_spaced_formula_is_only_a_composition_lead(self) -> None:
        self.assertEqual(composition_key("HOOC COOH"), composition_key("C2H2O4"))
        self.assertIsNone(composition_key("?"))

    def test_incorrect_candidate_classification_is_not_silently_corrected(self) -> None:
        data = target("Ethylene carbonate") | {"kind": "element"}
        row = match_entries([entry()], [data])[0]
        self.assertIn("candidate_classification_differs", row["flags"])
        self.assertEqual("element", row["matches"][0]["kind"])
