# Wikipedia archive coverage and recovered leads

Run the reproducible, read-only inventory:

```powershell
python scripts/audit_wikipedia_archive_coverage.py
```

The script verifies and inventories every one of the **1,239 revision-pinned pages**
in `sources/wikipedia-chemistry-category-snapshot-2026-07-29.zip`, matching its
archive SHA-256 and exact `page:{id}:revision:{id}` keys against parse history in
`.build/wikipedia-glm-full-reviewed.db` and `universe-unverified.db`. SQLite is opened
in read-only mode with a transaction for a consistent per-database snapshot. It
makes no OpenRouter calls and writes no candidate or review tables.

This inventory concerns the complete checked-in chemistry snapshot, including
pages outside the successful/filtered candidate queue. It does not claim to
review every article in the separate full English Wikipedia dump. July archive
revisions are preserved; source leads may require newer primary-source research.

Outputs under `.build/wiki-subagents/`:

- `archive-rest.json`: exhaustive page identity, parse history, source parameters,
  reference URL/DOI hints, candidate/cleanup coverage, and historical review actions.
- `archive-rest.csv`: every page in deterministic review priority order.
- `archive-rest.leads.json`: 14 manually inspected leads with exact source excerpts,
  offsets, selectors, source entry keys, permanent revision URLs and follow-up notes.

Audit at the time of this work:

| Parse outcome across either database | Pages |
| --- | ---: |
| Parsed | 444 |
| No data | 277 |
| Error with no successful parse | 96 |
| Pending with no successful parse | 1 |
| Unparsed | 421 |

A successful attempt in either database takes precedence over later unsuccessful
attempts. All attempts remain in the report. Coverage is a different question:
438 pages retain direct candidates, six retain cleanup mentions only, and 795
have neither. Cleanup-only pages remain represented through their canonical
candidate and must not be called omitted pages. Historical rejection actions
are preserved as reasons to inspect, not treated as current scientific judgments.
A parsed page does not establish that every identity/property on it was extracted.

Twenty-seven pages have incomplete parsing or no candidate evidence and explicit
chemical identity parameters. Those receive priority 1. Parameter and reference
matches are lexical discovery hints, not chemical identity validation. Actual
element symbols are checked, so engineering table columns such as `E` are not
mistaken for elemental composition. This is not a complete wikitext parser;
transcluded element/isotope templates and inline parameters need separate review.

Source inspection recovered these particularly useful leads:

- Isocyanic acid HNCO, manganese heptoxide Mn2O7 and neutral triatomic hydrogen H3
  have no exact-name or exact-formula candidate matches in this archive inventory.
  Isomer, phase and electric-charge distinctions need to remain explicit.
- The iron hydride article distinguishes molecular FeH2 and high-pressure FeH5
  from polymeric and complexed species. Both names/formulas lack exact candidate
  matches in this inventory.
- The high-entropy alloy article identifies the CrMnFeCoNi solid-solution alloy
  and cites Cantor et al., DOI `10.1016/j.msea.2003.10.257`. This needs primary-paper
  composition, processing and property-condition review.
- Unparsed actinium/aluminium isotope articles cite newer discoveries than the
  2020 evaluated data: Ac-203 (2024, `10.1016/j.physletb.2024.138503`), Al-20
  (2025, `10.1103/hkmy-yfdk`) and Al-21 (2024,
  `10.1103/PhysRevC.110.L031301`). No Wikipedia mass, lifetime or spin was imported.
- Dirubidium, phosphorus pentoxide, red/white phosphorus and tetrabromoauric acid
  already have exact-name evidence from other pages. Their source-page parse
  failure does not mean their identities are absent. These are additional
  thermochemistry, polymorph, molecularity and reference-coverage leads.

All 14 leads are marked `review_method=source_inspection` and
`pending_primary_source_confirmation`. The inspected text is the archived
Wikipedia page; the cited papers have not been claimed as inspected here. Matching
formulas alone never establish that two species, isomers or materials are equal.
Exact-name/formula matches count evidence occurrences across both databases, so
counts are not unique entity counts. They also do not audit every reviewed-core
or separate isotope/alloy reference record.

Wikipedia excerpt attribution is through the exact revision URL and archived
CC BY-SA 4.0 metadata. These secondary-source leads do not replace the project's
primary-source admission rules in `DATA_POLICY.md`. No reviewed core data or
existing agent decisions were modified.
