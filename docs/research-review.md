# Research review and admission

`review_research_evidence.py` produces hash-bound mapping proposals from elemental
research and writes a **new** core copy only when supplied explicit reviewer
decisions. It never marks source research as reviewed, overwrites an existing
output, or changes the input core. Generating a plan is not scientific approval.

```powershell
python scripts/review_research_evidence.py --plan .build/element-review-plan.json
python scripts/review_research_evidence.py --plan .build/element-review-plan.json --decisions decisions.json --output .build/reviewed-core.db
```

The manifest is a JSON object with `plan_sha256` copied from the generated plan,
`reviewer`, `reviewed_at`, and a `decisions` list. Each entry names a `research_id`
and chooses `approve`, `reject`, or `defer`. Approval additionally requires
`provenance_class`, `rationale`, `license_determination`, and `checks` containing
all eight explicit boolean attestations:

```json
{
  "source": true,
  "license": true,
  "identity": true,
  "value": true,
  "units": true,
  "uncertainty": true,
  "conditions": true,
  "transformation": true
}
```

These attestations mean the identified reviewer inspected the cited upstream
source and checked the admission requirements in [DATA_POLICY.md](../DATA_POLICY.md).
The tool cannot verify that inspection happened. Do not fill them automatically.
A license determination must explain redistribution permission or that only
uncopyrightable factual values are represented; a source license note alone is
not an approval. Wikipedia citations are blocked as accepted sources of record.

Supported admission currently covers exact elemental-reference point values for
density, specific heat capacity, and melting point, converted by exact rational
SI scale/offset to existing canonical core units. Existing element identities and
property definitions must match. Source version, retrieval date, locator, method,
phase/state, source notes and decisions are preserved. Known temperature is a
condition value; exact source pressure is retained in `unit:pascal`. Pressure
accepts integer/decimal or rational strings and explicit integer
`numerator`/`denominator` objects. Missing temperature stays missing and does not become room
temperature. Missing uncertainty stays NULL. No claim that an unspecified state
is suitable for a matched-condition alloy fit is made.

Bounded observations, finite-purity specimen identities, reported relative
uncertainty needing normalization currently produce
blocked proposals. Properties absent from the canonical vocabulary are also
blocked. These need source-specific mapping extensions before admission. The
plan retains every original research record and its reason, making extension
work concrete. Alloy, crystal and isotope families need separate adapters for
specimens, symmetry/site content, and nuclide/isomer identity; they must not be
recast as elemental observations.

Each approved observation has an `evidence_review` row containing the exact
manifest and decision, the research ID, and the plan hash. All approved rows are
inserted in one transaction into a temporary database; integrity and foreign
keys are checked before publishing the new file. A stale core, changed research
file, altered plan, duplicate ID or incomplete approval aborts admission.
No duplicate-conflict reconciliation is inferred: prior observations remain.
Keep the plan and manifest in version control with any subsequent seed/export
integration. This CLI does not edit reviewed seed inputs or publish a release.

## NIST provenance reconciliation

The existing 576 NIST isotope core values match research numerically but core
labels say `measured` while research labels say `curated`. Under DATA_POLICY,
representative isotopic abundances and evaluated/selected atomic masses should
be `curated` unless their individual cited experimental observations justify
`measured`. Numerical agreement alone does not establish measurement provenance.
A source-aware reviewer should prepare replacement/deprecation decisions and
update the reproducible NIST seed transformation in a dedicated migration.
Do not silently relabel published observations or bulk-promote all NIST rows.
This elemental adapter deliberately leaves those isotope rows unchanged.
