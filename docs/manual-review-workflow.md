# Manual chemistry review queue

The offline report [manual-review-queue.md](manual-review-queue.md) and its
[JSON companion](manual-review-queue.json) provide a reviewable next step after
manual chemistry discovery. They cover the six manual source slices and match
those targets against reviewed chemical species and all Wikipedia candidate
identities, including aliases and existing declared links.

This tool does not merge identities, average claims, edit a database, select
preferred observations or promote research. All manual facts remain unverified.

## Regenerate

```sh
python3 scripts/report_manual_review.py
```

Optional `--database` selects another companion snapshot; `--output` selects
the JSON report path, with Markdown written beside it. SQLite opens with
`mode=ro`. The default inputs are the versioned files under
`sources/manual-chemistry/`; there is no network or model access during reporting.

Report schema version 1 records the database SHA-256, generator SHA-256 and
source-file SHA-256 values. It checks whether each exact source digest appears
in an imported research run. Input bytes are read once and the database digest
is checked before and after processing; a changed artifact aborts reporting.
Ordering is deterministic and no wall-clock timestamp or random ID is emitted.
Run the report again after a database, source slice or generator change.

## Reading the queue

- `existing_reviewed_id`: the manual source uses an ID already owned by a
  reviewed chemical species. The new source facts still need review.
- `candidate_identity_review`: there are candidate/name/composition leads to
  reconcile. A composition-only lead may be an entirely different isomer or
  a particular polymorph; this state is not proof of an existing identity.
- `new_identity_review`: the report found no matching ID/name/alias/composition
  lead. This is bounded search coverage, not proof of chemical novelty.

Each match retains its original name, ID, kind, formula, charge and source
citation. Candidate citations point back to their revision-specific Wikipedia
source as discovery context, not an accepted primary scientific source. The
manual queue entry retains its independently researched primary-source URLs.

Flags expose missing/unsupported formulas, unknown or disagreeing charges,
name/link composition disagreements, candidate classification differences,
missing declared candidate IDs, incomplete citations/provenance and source
slices not imported into the chosen snapshot. Candidate classifications are
not silently corrected. A flag can be an expected difference between a generic
material and a neat compound; inspect its context before deciding what to do.
An empty flag list does not establish review, license acceptance or approval.

Name normalization changes case, Unicode typography and whitespace only; it
keeps positional numbers, punctuation and stereochemical labels. The formula
helper also recognizes simple spaced condensed formulas as report-only
composition leads. It does not edit that source notation, accept unsupported
hydrate/isotope/complex notation or infer a molecular graph.

The JSON report additionally groups manual targets sharing normalized labels
or composition/charge and lists differing text under the same target/field.
Original values and citations are retained. Textual differences may be harmless
paraphrases or differing conditions, so the tool does not call them proven
scientific conflicts and does not pick a winning value. Numeric-observation
conflicts and the broader nonmanual staging families remain outside this slice.

## Current snapshot result

The report covers **36 compound targets, 100 source-backed textual facts and
six slices**, with:

- 2 existing reviewed IDs;
- 19 entries with candidate identity leads;
- 15 entries needing new-identity review;
- 19 targets with one or more review flags.

All six source digests match imported research runs. There are no overlapping
manual name groups or differing same-target/field text claims in these inputs.
Those empty results do not rule out disagreement elsewhere in the database or
establish that all 36 identity mappings are correct.

Examples worth inspecting include same-formula isomer leads for carbonate
solvents, incomplete glycol formulas/charges, coarse material classifications,
and the pre-existing nitrous-oxide candidate classified as an element. The
queue leaves all those records unchanged for independent source review.

## Human review and later admission

For each queued target, inspect the primary source itself and its factual
redistribution basis. Verify the exact chemical identity, aliases, charge,
formula, hydrate/isotope/stereochemical/polymorph scope and whether an application
claim concerns a pure compound or a formulated derivative. Retain modeled
provenance for the oxalic-acid equilibrium-study leads. Preserve disagreements
and source conditions rather than averaging them away.

Record any human decision in a separate reviewed authoring change, citing the
source and rationale. The generated report is not a decision ledger, and editing
it does not authorize canonical identity creation or reviewed observation
promotion. The repository's broader promotion/preference tool and typed numeric
conflict review are still TODOs. No mod catalog or gameplay recipe was changed.

## Validation status

The report was generated against the checked-in database using read-only SQL.
The source files passed pinned Ruff 0.12.12 lint/format checks and Python AST
parsing. Report database/source/generator fingerprints match; database artifacts
and their manifests remain unchanged.

Eight regression cases were authored for distinct same-formula molecules,
charge disagreement, missing/hydrate formulas, positional/stereochemical names,
source-preserving textual differences, missing citations/dangling links,
spaced formulas and incorrect candidate classifications. They have **not been
executed** on this server. Compilation and project tests remain for local
validation, including read-only behavior, reproducibility, snapshot/source
changes and the generated-report CLI.


The [contributor data lifecycle](contributor-data-lifecycle.md) documents the
next authoring steps and provides an explicitly unreviewed, snapshot-bound
draft decision record. That record is separate from the generated queue and
is not executable promotion input.
