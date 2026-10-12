# Filtered Wikipedia source triage

Run `python -m scripts.audit_wikipedia_filtered` from the repository root. It opens the reviewer database with SQLite `mode=ro`, verifies the pinned archive manifest/digests through the existing archive loader, and emits `.build/wiki-subagents/filtered.json`. It makes no OpenRouter calls and changes no candidates.

## Coverage

All 5,270 current candidates, 2,439 aliases, 4,614 composition rows, 4,548 facts, 3,241 relations, 877 fact conditions, 1,255 original merged mentions, 43 derived facts, and 758 prior model review records were enumerated. These are exhaustive computational checks, **not exhaustive scientific/manual review**. Prior keep/rewrite decisions remain untrusted history.

The audit compares normalized quotations to every attached revision-pinned page, checks name/alias identity collisions, formula/charge inconsistencies, obvious method/reference title names, numeric-unit/condition omissions, and page-wide reference markup. Derived facts remain calculations, never measured source evidence. Every input candidate remains unverified.

## Counts

| Check | Candidate count |
|---|---:|
| attached_pages_have_no_detected_reference_markup | 61 |
| candidate_evidence_not_verbatim_after_normalization | 2311 |
| composition_evidence_not_verbatim_after_normalization | 702 |
| element_formula_is_not_single_symbol | 15 |
| fact_evidence_not_verbatim_after_normalization | 1205 |
| formula_charge_disagrees_with_electric_charge | 43 |
| ion_has_zero_charge | 6 |
| numeric_fact_without_explicit_conditions | 309 |
| numeric_fact_without_unit_text | 148 |
| possible_nonphysical_entity_name | 3 |
| relation_evidence_not_verbatim_after_normalization | 522 |
| shared_alias_needs_identity_review | 516 |
| shared_normalized_name_needs_identity_review | 1581 |

Quotation mismatches include paraphrases, markup differences and ellipses: they are search priorities, not proof that the underlying claim is false. Shared names and formulas can denote distinct phases, isomers or contexts, so none is auto-merged. A missing unit can be legitimate for a dimensionless identifier or ratio. Reference markup is detected across the page and does not establish claim-level citation support. No flag permits automatic admission or rejection.

## Focused source inspections

Eleven high-risk rows were inspected substantively against their local page contexts. Proposals are in `.build/wiki-subagents/filtered.findings.json`, with exact IDs, revision keys, attributed excerpts and offsets. All remain `pending_human_review`; no rewrite/rejection was applied. Source inspections below establish extraction/identity problems, not authenticated physical measurements.

| Candidate ID | Identity | Proposed action and reason | Pinned source |
|---|---|---|
| `54b1fb93-11ca-4ee4-ad50-288c729452cd` | Birge–Sponer method | reject_entity_candidate: The lead explicitly defines a computational spectroscopy method, not a molecule. | [Birge–Sponer method](https://en.wikipedia.org/w/index.php?oldid=1290907794) |
| `1d7d1e38-c563-4e08-841c-343982fa7e07` | ASTM E2399 / E2399M - 19 Standard Test Method for Maximum Media Density for Dead Load Analysis of Vegetative (Green) Roof Systems | reject_entity_candidate: The identity is an ASTM reference title embedded in a citation, not a physical material. | [Engineered cellular magmatic](https://en.wikipedia.org/w/index.php?oldid=1347534225) |
| `fd4ac503-00e5-43e8-93ea-d32f57d39b21` | ASTM E2399 / E2399M - 19 Standard Test Method for Maximum Media Density for Dead Load Analysis of Vegetative (Green) Roof Systems | reject_entity_candidate: Duplicate extraction of the same reference title as a material; retain reference attribution, not an entity. | [Engineered cellular magmatic](https://en.wikipedia.org/w/index.php?oldid=1347534225) |
| `0e59f1d3-9480-452d-83f1-7def9182aeba` | acetic acid | review_kind_as_molecule: Source explicitly identifies acetic acid in a reaction; CH3COOH is not a single chemical element. | [Breathalyzer](https://en.wikipedia.org/w/index.php?oldid=1358712427) |
| `24fe60b0-7387-4d65-8f10-df69dd56500a` | electron | review_kind_as_particle: Source discusses electron mass; electron is a particle, not an element. | [Compton edge](https://en.wikipedia.org/w/index.php?oldid=1357860549) |
| `14fc3e08-b9c6-4f8a-98ea-faaca3eb3777` | Sodium tetrachloroaurate | review_kind_as_formula_unit: Source calls Na[AuCl4] the sodium salt; candidate is neutral and should not denote a free ion. | [Chloroauric acid](https://en.wikipedia.org/w/index.php?oldid=1364683651) |
| `42b7ae29-486e-42fa-a341-88a525063921` | Neutral sulfur | review_identity_and_charge: Evidence cites S II (singly ionized sulfur); candidate instead says neutral sulfur S I and zero charge. | [Forbidden mechanism](https://en.wikipedia.org/w/index.php?oldid=1356506233) |
| `9853296d-ca5c-4ffb-a774-c1bc9b3551af` | Neutral oxygen | review_kind_as_neutral_atom: Evidence supports neutral O I, but neutral atom is typed ion. Preserve spectroscopic state instead of treating O I as molecular formula. | [Forbidden mechanism](https://en.wikipedia.org/w/index.php?oldid=1356506233) |
| `22c48ce9-9780-453d-8719-a0cc5e268d26` | Hydrogen-1 | review_nuclide_assignment_and_kind: Source says neutral hydrogen gas; it does not explicitly assign isotope Hydrogen-1. Zero-charge candidate is also typed ion. | [Forbidden mechanism](https://en.wikipedia.org/w/index.php?oldid=1356506233) |
| `5f92e59f-4895-4ce3-b76b-350f1320b7b5` | methyl | review_bound_group_vs_free_entity: Caption describes a methyl group bound in pentamethylmolybdenum, not evidence for a free neutral methyl ion. | [Crystallographic disorder](https://en.wikipedia.org/w/index.php?oldid=1362261713) |
| `6409a706-1991-4b65-99c9-45a85e3abee2` | Calcium chloride | review_kind_as_formula_unit: Source describes calcium chloride as a chemosterilant. Whole neutral CaCl2 formula unit should not be an ion. | [Chemosterilant](https://en.wikipedia.org/w/index.php?oldid=1283331642) |

## Next review priorities

1. Resolve the three source-defined method/reference entities and six zero-charge ion assignments with an explicit deprecation/replacement trail. Inspect neutral sulfur and hydrogen isotope assignments before inheriting their children.
2. Inspect the 43 formula/charge disagreements and 15 nonsingle-symbol element formulas; neutral salts, electrons and formula-bearing elemental forms must retain distinct identities.
3. Resolve shared names/aliases with source context, phases, charge, isotope and stereochemistry; do not deduplicate solely by formula.
4. Recheck numeric observations against suitable primary/evaluated evidence, recording source-provided units, conditions and uncertainty.

The checked archive is `sources/wikipedia-chemistry-category-snapshot-2026-07-29.zip`, SHA256 `c1b4db37964c497f901343c706019324eac204af2973b9aaff71c24f781cdf29`. Wikipedia text/excerpts retain CC BY-SA 4.0 attribution via permanent revision URLs and remain license-distinguishable from MIT code. Wikipedia serves as a secondary-source discovery lead under DATA_POLICY.md, not the accepted source of record.
