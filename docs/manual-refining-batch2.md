# Refining and mineral-processing research — batch 2, 2026-10-13

This slice contains six defined compounds and 16 cited textual facts in
[`refining-batch2-2026-10-13.json`](../sources/manual-chemistry/refining-batch2-2026-10-13.json).
All are unverified research pending human inspection under
[DATA_POLICY.md](../DATA_POLICY.md). The proposed ICM roles are design ideas,
kept in `usefulness`, separately from the source-backed facts. No mineral
deposits, extraction yields, operating recipes or quantitative measurements
have been added.

| Compound | Formula | Source-backed engineering role |
| --- | --- | --- |
| Methyl isobutyl carbinol | C6H14O | Mining frother; coatings solvent |
| Potassium ethyl xanthate | C3H5KOS2 | Copper, lead and zinc sulfide flotation collector |
| Sodium sulfide, anhydrous | Na2S | Oxide-ore sulfiding, flotation and metal precipitation |
| Sodium cyanide | NaCN | Gold extraction reagent |
| Oxalic acid, anhydrous | C2H2O4 | Rare-earth precipitation and contaminant interference examined by equilibrium modeling |
| Sodium metasilicate, anhydrous | Na2SiO3 | Alkaline cleaning and corrosion inhibition |

The flotation roles deliberately distinguish a frother from a collector and a
surface-treatment reagent. The sources do not establish an interchangeable
reagent, generic performance multiplier, universal ore separation or game recipe.
Hydrates, variable-ratio waterglass mixtures, polysulfides, hydrosulfides and
alternative alkyl xanthates are distinct identities. Formula units carry net
charge zero; their component ions are not entered as neutral molecules.

Primary sources inspected include [NOAA's MIBC identity](https://cameochemicals.noaa.gov/chemical/3942),
[Solvay's own MIBC applications](https://www.solvay.com/en/product/methylisobutylcarbinol),
[Aladdin's own collector guide, dated 2025-12-14](https://www.aladdinsci.com/us_en/faqs/guide-to-mineral-processing-reagents-flotation-collectors-en.html),
[Thermo Scientific's anhydrous sodium sulfide product](https://www.fishersci.com/shop/products/sodium-sulfide-anhydrous-thermo-scientific/AA6512206),
[Sigma-Aldrich's sodium cyanide identity](https://www.sigmaaldrich.com/US/en/product/sigald/205222),
[Orica's sodium cyanide information sheet](https://www.orica.com/ArticleDocuments/1475/Sodium%20Cyanide%20Brochure.pdf.aspx),
[Sigma-Aldrich's oxalic acid identity](https://www.sigmaaldrich.com/US/en/product/aldrich/194131),
[the original Zhang/Noble/Ji/Li study, repository dated 2022-01-01](https://vtechworks.lib.vt.edu/items/d09d8713-d788-4612-b146-6502fed8f138),
and [Silmaco's own anhydrous metasilicate reference](https://silmaco.com/en/product/metasilicate-anhydrous).
Live product pages without a declared revision retain their product identifiers
and retrieval date rather than an invented release. Only factual identities and
original short paraphrases are represented; manufacturer tables, promotional
performance guarantees and substantial source text are not redistributed.

The two oxalic-acid engineering facts explicitly describe **modeled**
solution-equilibrium evidence; they are not measured capacities or universally
valid precipitation outcomes. Any future scientific promotion must preserve
that distinction and review the original model, species and conditions.

## Identity and duplication checks

Read-only queries inspected `entity`, `alias`, `unverified_entity_candidate`,
`unverified_candidate_alias` and `unverified_fact` in both checked-in databases.
Names, engineering aliases and formulas were compared with all previous manual
JSON entries. No reviewed entity or previous manual fact for these six targets
was found by these bounded searches; this is not proof of exhaustive synonym
coverage.

Four existing compatible research leads are linked:

- Sodium sulfide: `71880bec-517e-4be8-8cc6-54e7ee05de39`, formula Na2S.
- Sodium cyanide: `bedddab9-4e1b-4485-a3c4-290dffbea381`, formula NaCN, charge zero.
- Oxalic acid: `3288057a-f194-47ad-99e3-84df49125afb` and
  `fa59dca1-1975-42ae-b898-a19638d4200f`, exact-name leads without recorded formulas.

Candidate scientific classifications are not copied: sodium cyanide's existing
`molecule` lead is represented here as an ionic formula unit. Oxalic-acid candidate
`878eb527-b398-44c9-a930-fd184a5eac16` carries `HOOC COOH`, a spaced structural
formula that has the right elemental counts but is unsupported by the current
plain-formula importer. It is recorded here for reviewer reconciliation and
not passed as a link that would fail validation. Generic sodium-silicate lead
`43f5b798-cc35-4ef9-b257-fae72d4a10d2` is not equated with the exact anhydrous
metasilicate stoichiometry.

This authoring slice changes only its JSON and this document. It does not edit
any database, shared importer, schema, mod code or pinned catalog. No compilation
or tests were run.
