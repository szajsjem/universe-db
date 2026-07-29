# Future data roadmap

Scope: database releases after the initial reviewed element/nuclide slice.
These database tasks were moved from Inorganic Engineering. Algorithms and
gameplay remain in the mod; reference data, benchmark corpora, schema, and
deterministic exports live here.

## Cross-cutting data contracts

- [ ] Give every scientific value a unit, uncertainty representation,
  provenance class, source/license, applicable conditions, and schema version.
- [ ] Keep identity/structure fields separate from scientific observations,
  while versioning and auditing both.
- [ ] Treat measured rows as conditional observations rather than universal
  constants; keep conflicting measurements as separate rows.
- [ ] Store modeled values with model/version, input snapshot, parameters,
  domain, uncertainty, and validation evidence.
- [ ] Require fictional data to use an explicit fictional namespace.
- [ ] Never invent a value to fill a gap; preserve a missing/unknown reason.
- [ ] Record upstream release, retrieval date, transformation, citation, and
  redistribution license for every third-party import.
- [ ] Make every benchmark/model output identify database snapshot, algorithm
  version, configuration, random seed, and fallback/extrapolation paths.

## Normalized schema expansion

- [ ] Add reviewed preference/rationale and observation supersession edges.
- [ ] Expand charge states, solvation, dissociation, isotopologues, isomers,
  excitation states, and decay daughter relationships.
- [ ] Add functional groups, tautomers, conformers, stereochemistry, polymer
  repeat units, cross-links, and structure aliases.
- [ ] Add material forms, phase regions, crystals, ceramics, glasses,
  composites, defects, orientation, grains, and microstructure.
- [ ] Add crystallization experiments, solution composition, solubility,
  supersaturation, seeds, nucleation/growth, polymorphic transitions, and
  particle-size distributions.
- [ ] Add ceramic precursor, powder, binder/slurry, forming, drying,
  debinding, firing, sintering, vitrification, glaze, porosity, grain-boundary,
  and process-schedule relationships.
- [ ] Add reaction mechanisms, rate laws, equilibria, catalysts, competing
  pathways, and typed reaction-condition observations.
- [ ] Expand spectrum calibration, resolution, sample conditions, transitions,
  features, and radio/visible/UV/X-ray/gamma coverage.
- [ ] Expand nuclear parent/incident/emitted participants, daughters,
  branching, energy distributions, partial half-lives, and cross-section
  curves.
- [ ] Add validation cases, benchmarks, expected results, tolerances,
  model-runs, outputs, and comparison results without mixing predictions into
  reference observations.

## Source and data milestones

### Elements, nuclides, properties, and spectra

- [ ] Reconcile periodic-table observations across independent licensed
  sources while retaining disagreement.
- [ ] Expand beyond naturally representative nuclides to known nuclides and
  isomers with observed/stable status, mass, abundance, half-life, and spin.
- [ ] Populate condition-dependent phase transitions, molar mass,
  electronegativity, electron configurations, and spectra.
- [ ] Add coverage and quality matrices and independent cross-checks.

### Ions, molecules, reactions, and crystallization

- [ ] Import successive ionization energies and licensed electron
  configurations.
- [ ] Model acid/base, salt, solvent, complex-ion, redox, thermal, and
  photolytic dissociation as condition-dependent graph edges.
- [ ] Add reaction equilibrium, kinetics, catalysts, solvents, selectivity,
  competing pathways, and phase-dependent products.
- [ ] Import canonical molecular graphs, bonds, charge, stereochemistry,
  tautomers, conformers, isotopologues, salts, and solvates.
- [ ] Seed reviewed organic datasets for industrial solvents, fuels,
  extractants, surfactants, binders, polymers, and representative reactions.
- [ ] Add crystal structures, polymorphs, hydrates/solvates, phase diagrams,
  solubility, nucleation, growth, and conserved crystallization benchmarks.

### Materials, ceramics, polymers, and engineering observations

- [ ] Populate ceramics, crystals, glasses, alloys, composites, polymers,
  fuels, moderators, coolants, and structural materials incrementally.
- [ ] Store precursor purity, particle distributions, morphology, moisture,
  additives, process graphs, atmosphere, temperature/pressure profiles,
  shrinkage, phase evolution, porosity, grain structure, and defects.
- [ ] Store condition-dependent mechanical, electrical, dielectric, magnetic,
  optical, thermal, corrosion, creep, fatigue, wear, permeability, and
  radiation-response observations.
- [ ] Store energy-dependent neutron scattering/absorption data with isotope
  composition, temperature, phase, uncertainty, and material form.
- [ ] Add mixture/effective-property, crystal-growth, ceramic phase,
  densification, heat-flow, stress, and fracture benchmark corpora.

### Nuclear, accelerators, and fusion

- [ ] Populate all typed decay modes, daughters, probabilities, half-lives,
  delayed channels, metastable states, decay heat, and decay-chain benchmarks.
- [ ] Add energy-dependent scattering, absorption, activation, shielding,
  moderation, and transport reference data.
- [ ] Add beam species/charge states, targets, energy windows, stopping data,
  cross sections, yields, byproducts, and activation observations.
- [ ] Add fusion reactants/products, cross-section/reactivity curves, plasma
  domains, impurities, losses, tritium breeding, blanket reactions, neutron
  damage, activation, and heat-transport benchmarks.

### Unknown and fictional matter

- [ ] Separate candidate/model namespaces from accepted measured identities for
  elements above 118 and unobserved nuclides.
- [ ] Store pluggable mass, shell, stability, decay, reaction,
  electron-structure, chemistry, and material-property models with explicit
  domains and versions.
- [ ] Require holdout tests and cross-model comparison before extrapolation.
- [ ] Mark unknown-nuclide/superheavy outputs as modeled until a reviewed
  measured dataset supersedes them.
- [ ] Keep explicitly fictional materials separate from measured and modeled
  scientific data.

## Export integrity gates

- [ ] Validate identity uniqueness and lifecycles; atom, nuclide, mass, charge,
  nucleon, and reaction conservation; and source/license completeness.
- [ ] Validate nuclear parent/daughter/participant changes and mutually
  exclusive branch sums only under compatible conditions.
- [ ] Validate unit dimensions, conversions, bounds, uncertainty shapes,
  condition compatibility, and energy/cross-section ordering.
- [ ] Validate molecular graphs, crystallographic references, occupancies,
  compositions, process schedules, distributions, and graph cycles.
- [ ] Produce all-or-nothing deterministic exports with manifests, hashes, row
  counts, schema version, source/license inventory, and rejected-record report.
- [ ] Bound curve points, row counts, traversal, numeric magnitude, and export
  size.

## Stable 1.0 contract

- [ ] Freeze stable IDs, normalized schema v1, snapshot manifest, export
  schemas, unit registry, provenance rules, and migration policy.
- [ ] Require every production algorithm to declare data dependencies,
  validity domain, fallback policy, precision, and benchmark evidence.
- [ ] Publish reproducible database builds, hash-addressed releases, supported
  migrations, rollback instructions, known limitations, coverage, citations,
  licenses, and correction workflows.
