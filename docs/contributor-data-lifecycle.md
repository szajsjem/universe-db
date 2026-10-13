# Contributor data lifecycle

This workflow completes the contributor documentation for imports, review,
corrections, deprecation, preferred-value selection and source/license admission.
The current schema and implemented tools are the authority for what can be
executed; the steps below do not add a promotion engine or manufacture a human
review decision. See [DATA_POLICY.md](../DATA_POLICY.md) for the admission rules.

## 1. Choose the authoring boundary

| Input | Destination before scientific review | Reproducible authoring input |
| --- | --- | --- |
| Primary scientific dataset | Source-specific staging/evidence database or a proposed reviewed seed after independent review | Dated source snapshot, checksum and versioned importer |
| Manually selected chemistry leads | `research_run`, `research_task`, `unverified_fact`, `unverified_fact_source` | Immutable dated `sources/manual-chemistry/*.json` |
| Wikipedia extraction | `unverified_*` candidate tables | Revision-pinned archive, parser run and page provenance |
| New reviewed scientific slice | Canonical entities/observations and typed scientific tables | New numbered migration if needed, then new numbered seed |
| Gameplay balance or artistic presentation | Consumer-owned configuration or an explicitly curated/fictional dataset | Mod/profile change with its own rationale |

Schema coverage, a successful import, an agent's source inspection and passing
integrity checks do not establish scientific review. Missing observations remain
absent. A qualitative engineering application does not imply a numeric capacity,
operating temperature, reaction yield, planet abundance or gameplay multiplier.

Describe source/version, redistribution basis, data families, expected counts
and transformation in the reviewable contribution or a linked issue.

## 2. Admit source and license evidence

Before a reviewed seed creates scientific rows, identify these records:

- `license`: redistribution permission, SPDX identifier when applicable,
  source terms URL and the factual-only determination if that is the basis.
- `source`: primary citation, persistent URL/identifier, retrieval date and
  the accepted `license_id`.
- `dataset`: immutable upstream version or dated snapshot identity, source,
  schema version, provenance class and transformation notes.

Commit license/attribution text and required notices alongside a redistributed
source snapshot. Keep differently licensed archives distinguishable from project
code. For live pages without a released version, retain the retrieval date,
product/document identifier and immutable authored input hash; do not invent a
release number. Where terms are unknown and a factual-only basis cannot be
justified, leave the record out of the reviewed import pending evidence.

Manual-input `license_basis` is a research claim for review, not automatic legal
or scientific acceptance. Verify exactly what is redistributed: short original
factual paraphrases, numerical source tables, images and full page archives are
different kinds of content. The existing validator rejects a reviewed source
whose license record has `redistribution_allowed` other than 1.

Preserve provenance on admission: `measured` for a source-reported experiment,
`modeled` for a source/model output with algorithm and input context, `curated`
for an authored identity or engineering selection, and `fictional` for an
explicitly invented namespace. A model-assisted discovery process itself is
not a measurement source. In particular, the oxalic-acid equilibrium-study
leads must not be promoted as measured precipitation capacities.

## 3. Review identities and claims separately

Generate the [manual review queue](manual-review-workflow.md) when applicable:

```sh
python3 scripts/report_manual_review.py
```

Pin the exact database, source-input and queue hashes in the review record.
Inspect the primary source independently and record the locator/page/table
supporting each accepted claim. Review canonical identity, aliases, formula,
charge, isotope/hydrate/polymorph/stereochemical scope and pure-compound versus
mixture/grade scope. Same composition is not proof of identical structures.
Do not accept a candidate merely because a name, text ID or formula matches.

Review each fact separately. Preserve units, pressure/temperature, material form,
method, uncertainty and provenance when present. Distinguish an unsupported
claim from an unresolved mapping; both can remain pending without silently
replacing source evidence. A source's promotional product claim is not a
universal pure-compound property.

The [calcium-hydroxide draft](../examples/reviews/calcium-hydroxide.draft.json)
shows how to bind a record to actual current inputs. It contains no reviewer,
accepted decision or verified checklist. Copy it into a separately versioned
review record and fill it only when an actual reviewer has inspected the
sources. Never treat the example's existence as an approval.

Suggested record fields are versioned in that draft. An accepted record needs
an attributable reviewer/date, explicit identity resolution, per-fact decisions,
source/license findings and rationale. Rejected and needs-more-evidence records
retain the original target/claim IDs and explain the reason. Subsequent decisions
use new record IDs and a `supersedes_review_id` link; retain the older records.
This is an authoring ledger convention, not a SQLite schema or a cryptographic
proof that a named reviewer performed the work. Automated tooling must not
invent reviewer identities or accepted decisions.

## 4. Author the reviewed change

After independent review, add a new source/dataset identity and a small numbered
seed. Use a new numbered migration only when the existing typed schema cannot
represent the evidence; never edit a released migration. Match entity IDs and
specialization rows deliberately, then add composition, aliases, phases,
conditions and observations with their direct source references. Put atoms,
charges, reaction participants, spectra or nuclear channel facts into their
typed tables instead of a generic prose field when the schema supports them.

Represent numeric values as exact integer ratios and use a canonical unit with
its exact SI scale/offset. Keep uncertainty beside the value and retain source
conditions. Do not invent uncertainty, assume unspecified conditions, or put
zero in place of unknown. Add validation for new dimensional, conservation,
ordering, probability or identity invariants.

The draft ledger and review report are not executable promotion instructions.
The repository still needs a general tool for mapping approved staged records
onto canonical scientific tables. Until a reviewed seed and that admission work
exist, the 36 manual targets remain research, not active mod catalog additions.

## 5. Correct and deprecate without erasing evidence

For an observation correction, add a new observation under a new stable ID with
its source, dataset, condition and rationale. Retain the original observation
and disagreement. Record which review decision supersedes the earlier one.
The current schema has no general observation-supersession edge or preferred
observation table, so such relationships remain documented authoring decisions
until a versioned schema/tool contract is added. Do not invent those columns
or overwrite a published value to simulate supersession.

For an entity identity correction, use existing lifecycle metadata in a new
numbered seed. For example, after an actual review identifies valid IDs:

```sql
-- Placeholder IDs: this is documentation, not an executable published seed.
UPDATE entity
SET lifecycle_state = 'deprecated',
    replaced_by_entity_id = 'chem:reviewed_replacement'
WHERE entity_id = 'chem:reviewed_old_identity';
```

The old and replacement entities must have the same `entity_type`. The old
entity must be deprecated, replacement chains must be acyclic and an
alias must not resolve to a deprecated terminal identity without a replacement.
Those constraints are checked by the existing validator. Never recycle the old
ID for another substance. Retain old aliases and lineage according to their
source meaning; an alias correction is not a reason to duplicate the entity.

An unsupported candidate classification is still unverified evidence. Use a
separately authored, cited correction/review result rather than rewriting old
parser provenance or claiming a change to reviewed science happened automatically.

## 6. Select a preferred value explicitly

First compare identities, property definitions, units, conditions, material
forms and provenance. Values measured under different conditions are not
interchangeable disagreements. Keep conflicting same-context source observations
separately. A documented preference identifies the chosen observation, the
alternatives, applicable consumer/context and reviewer rationale; it does not
change other sources or relabel modeled/curated values as measured.

The current bootstrap exporter selects observations from
`dataset:inorganic-engineering-bootstrap` and requires exactly one observation
for its requested subject/property. It rejects ambiguity; it does not choose
the newest row, average sources or interpret an external preference ledger.
The existing profile's `species_dataset` selects an identity dataset, not a
general observation preference policy. Do not add unsupported profile keys and
claim they change exported scientific values.

For now, record a proposed preference in a review record and keep the consumer
blocked on a separate versioned preference/export contract when necessary.
General preference and observation-supersession schema/tools remain future work.

## 7. Regenerate and publish the reviewed artifact

On a permitted development machine, rebuild from versioned migrations/seeds,
run [validation gates](validation.md) and the appropriate regression suites,
then refresh the database checksums and manifest. If `universe.db` changes,
rebase/regenerate its companion so `unverified_base_sha256` matches that exact
reviewed artifact. Preserve previous unverified research runs and source data.
Regenerate snapshot-bound reports after artifact/source/generator changes.

A reviewed change includes source/license inventory, review rationale, authoring
inputs, expected counts, transformation, validation evidence and reproducibility
limits. [Release export](releases.md) keeps research families labelled unverified.
Publishing a combined artifact does not promote those families.

On this server the standing task constraint prohibits compilation and tests.
This documentation slice parsed the draft JSON, checked local links and verified
its current-input hashes only. It performed no scientific review, source
promotion, database rebuild or test execution. The draft/checklist records the information required for later review.
