# Universe Database TODO

This is the active database backlog moved from Inorganic Engineering. The
Minecraft repository owns gameplay and runtime integration; this repository
owns scientific schema, sources, imports, review, validation, the checked-in
SQLite artifact, and deterministic exports.

## Complete the reviewed authoring database

- [x] Write the initial normalized schema and data dictionary.
- [x] Implement SQLite migrations, foreign keys, strict tables, integrity
  constraints, and transaction-safe artifact creation.
- [x] Implement the common scientific value envelope: exact units,
  uncertainty, provenance, sources, conditions, and record schema versions.
- [x] Implement canonical elements, nuclides, chemical species, compounds,
  ions, phases, aliases, compositions, dissociation states, reactions,
  spectra, nuclear channels, and cross-section points.
- [x] Build a deterministic SQLite-to-datapack exporter that never requires a
  live SQLite connection at game runtime.
- [x] Validate exact mass, charge, atoms, probabilities, units, aliases,
  references, ordering, and graph integrity before export.
- [ ] Seed a deliberately small, fully reviewed dataset covering the current
  copper bootstrap as the end-to-end migration fixture.
- [x] Document contributor import, review, correction, deprecation, preferred
  value selection, and license-acceptance workflows, including implemented
  schema/export boundaries and an explicitly unreviewed snapshot-bound draft.
  See `docs/contributor-data-lifecycle.md`.

## Fill element and nuclide coverage

- [x] Import all 118 element identities and source-authored electron
  configurations from the vendored PubChem periodic-table snapshot.
- [x] Import NIST relative masses and representative natural abundances for the
  288 nuclides in its natural-composition set.
- [ ] Prefer reproducible bulk downloads from evaluated, redistributable
  sources before per-field web research. Assess evaluated nuclear data,
  spectra libraries, and source APIs independently; do not use Wikipedia as
  the accepted source of record.
- [x] Vendor a bounded, revision-pinned Wikipedia chemistry/category snapshot
  for source discovery, with per-page attribution and CC BY-SA licensing.
- [x] Vendor and checksum the official July 2026 Kiwix English Wikipedia
  chemistry mini release as a compact upstream offline snapshot.
- [ ] Import melting and boiling transitions as observations with explicit
  pressure and material-form conditions.
- [ ] Import electronegativity values with their named scale.
- [ ] Import nuclide spin/parity, half-life, mass excess, total binding energy,
  and binding energy per nucleon with uncertainties.
- [ ] Import typed alpha, beta-minus, beta-plus/positron, electron-capture,
  proton, neutron, gamma, and spontaneous-fission channels with daughters,
  branch probabilities, and partial half-lives.
- [ ] Import source-specific electron, radio, visible, ultraviolet, X-ray, and
  gamma spectra with axis/intensity units, resolution, sample state, and
  conditions.
- [ ] Import fusion and induced-reaction cross-section curves with target and
  projectile identities, laboratory/center-of-mass energy or relative speed,
  uncertainty, and conditions.
- [ ] Publish coverage and disagreement reports by source, element, nuclide,
  property, spectral region, channel, provenance, and license.

## Unverified research staging

- [x] Add an opt-in, resumable Responses API web-research script that asks for
  one field of one target per request and defaults to a low-cost model.
- [x] Keep model output in relational `unverified_*` staging tables, separate
  from reviewed observations and exports.
- [x] Preserve prompts, model/run identity, source URLs, decimal source text,
  exact ratios when representable, conditions, uncertainties, and relation
  hints.
- [ ] Add a review/promotion tool that maps staged values onto canonical units,
  entities, conditions, spectra, nuclear channels, and observations only after
  source/license verification.
- [ ] Add duplicate/conflict clustering and review queues without averaging or
  overwriting disagreement.
- [ ] Add molecule and reaction research profiles after reviewed canonical
  molecular graphs and broader reaction identities are populated.
- [x] Add a sequential page parser that stages new nuclides, molecules,
  reactions, compositions, facts, conditions, and participant relations from
  the Wikipedia snapshot without creating reviewed rows.

## Static consumer boundary

- [ ] Publish a stable export profile and manifest contract for Inorganic
  Engineering.
- [ ] Make the mod build statically import the pinned `universe.db` release (or
  its deterministic exported datapack) and package generated resources from
  it.
- [ ] Prove that runtime startup, reload, and game ticks require neither a
  SQLite connection nor network/model access.

Release readiness requires passing all integrity gates, an updated
source/license inventory, byte-for-byte reproducibility, and an honest
coverage report.


## Manual mod chemistry research

- [x] Add three browser-researched, source-cited chemistry slices (18 compounds,
  48 factual assertions plus identity records) to unverified research staging,
  retaining existing identity links, attribution and separate design rationale.
- [x] Add an offline staged importer and regenerate companion checksum/manifest.
- [ ] Locally exercise importer malformed-input/replay/rollback/regeneration
  cases; no project test suites or compilation ran on this server.
- [ ] Independently review source, classification, aliases, conditions and
  redistribution basis before reviewed promotion or mod-catalog integration.
  See `docs/manual-mod-chemistry.md`.

- [x] Add a second manual research batch: 18 other compounds / 52 sourced facts
  for refining, batteries and thermal materials; retain hydrate, polymorph,
  composite and modeled-evidence boundaries. See
  `docs/manual-mod-chemistry-batch2.md`.
- [x] Reject reused reviewed compound IDs with mismatching formula/charge or
  another entity kind during manual import (source implementation).


## Manual identity review queue

- [x] Generate an offline, read-only manual-chemistry identity/provenance review
  queue against reviewed species and Wikipedia candidates; preserve formula,
  charge, classification, aliases, source citations and existing link evidence.
- [x] Add manual label/composition overlap groups and source-preserving textual
  difference groups, with no automatic merges, averaging or promotion.
- [x] Publish deterministic coverage and Markdown/JSON reports bound to source,
  generator and database hashes; see `docs/manual-review-workflow.md`.
- [ ] Run the eight authored report regression cases locally and validate CLI
  reproducibility, read-only behavior and snapshot/input-change handling.
- [ ] Extend review clustering to numeric observations and nonmanual staging
  families, and implement the separately authorized human-decision/promotion
  workflow. Existing global review/promotion TODOs remain open.
