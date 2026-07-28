# Roadmap

The database grows in reviewed, redistributable slices. Coverage targets are
not permission to synthesize missing values.

## 0.1 — reproducible foundation

- [x] Standalone public repository and checked-in `universe.db`.
- [x] Deterministic migrations, seeds, checksum, and manifest.
- [x] Strict normalized tables with foreign keys.
- [x] Provenance, source, license, unit, uncertainty, and condition envelopes.
- [x] Quark/lepton identity bootstrap.
- [x] Inorganic Engineering element/species/material/reaction bootstrap.
- [x] Integrity, exact reaction-balance, ordering, and reproducibility checks.
- [ ] Deterministic SQLite-to-datapack exporter for Inorganic Engineering.

## 0.2 — elements, nuclides, and spectra

- [ ] Import reviewed identities for elements 1–118.
- [ ] Import known nuclides/isomers with masses, abundance, stability, and
  half-life observations where licensed data supports them.
- [ ] Add source-specific IR, visible, UV, and X-ray importers.
- [ ] Store axis/intensity units, resolution, sample state, uncertainty, and
  conditions for every spectrum.
- [ ] Publish coverage and disagreement reports by source and element.

## 0.3 — molecules, ions, mixtures, and crystals

- [ ] Import canonical molecular graphs, formal charges, bonds, and structure
  aliases from a redistribution-compatible source.
- [ ] Add condition-dependent ionization and dissociation relationships.
- [ ] Add reactions with equilibria, rate laws, catalysts, solvents, and
  competing pathways without mixing yield with stoichiometry.
- [ ] Import mixture observations with an explicit concentration basis.
- [ ] Import crystal systems, space groups, unit cells, lattice sites,
  occupancies, polymorphs, defects, and source conditions.
- [ ] Add crystallization experiments and conserved process benchmarks.

## 0.4 — nuclear channels and interactions

- [ ] Import typed alpha, beta-minus, beta-plus, electron-capture, gamma,
  spontaneous-fission, and particle-emission channels.
- [ ] Validate daughter identities and charge/nucleon conservation.
- [ ] Store mutually exclusive branching probabilities under compatible
  condition sets.
- [ ] Import neutron/proton capture and other induced channels.
- [ ] Import energy-ordered cross-section curves with units and uncertainty.
- [ ] Add decay-chain, activation, and capture benchmark cases.

## 0.5 — materials and engineering observations

- [ ] Add alloys, ceramics, glasses, composites, polymers, fuels, moderators,
  coolants, and structural materials without duplicating chemical identities.
- [ ] Add condition-dependent thermal, mechanical, electrical, optical,
  corrosion, and radiation-response observations.
- [ ] Represent material form, porosity, grain structure, orientation, defects,
  and processing history explicitly.

## Later — models and hypothetical matter

- [ ] Record model identities, versions, input snapshots, parameters,
  validity domains, uncertainty, and validation evidence.
- [ ] Keep model output separate from reference observations.
- [ ] Add holdout benchmarks for known values before extrapolating to unknown
  nuclides or elements.
- [ ] Require explicit namespaces and provenance for hypothetical and fictional
  matter.

Release readiness requires passing integrity gates, an updated source/license
inventory, byte-for-byte reproducibility, and an honest coverage report.
