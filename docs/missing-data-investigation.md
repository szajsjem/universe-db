# Missing data and capability investigation

Investigated on 2026-10-12 against the six local database artifacts, current
schemas/importers/models, source-audit reports, roadmap, and release workflow.
This distinguishes missing records, missing context, pending review, and
missing calculation support. It is not a claim of completeness over every
known substance or nuclear state.

Reproduce the quantitative inventory:

The first remediation pass adds three reproducible review aids, bundled by
the release exporter. [Element admission](research-review.md) now maps 82 of
187 proposals, including exact pressure conditions, and requires explicit
source-review decisions before writing a new core copy.
[Crystal-cell validation](crystal-cell-validation.md) expands 22 of 36 records,
has occupancy-known composition for eight, and checks six against formula/Z.
[Nuclear normalization](nuclear-normalization.md) produces 11,952 typed records
and 8,273 explicit syntax/uncertainty gaps. These tools do not resolve missing
source data or constitute scientific approval. The NIST provenance discrepancy,
specimen/composition gaps and broad coverage gaps below remain open.

```powershell
python scripts/investigate_coverage.py
```

The complete report is `.build/missing-data-investigation.json`. It includes
database SHA-256 digests, every table count, empty tables, integrity checks,
and exact IDs for missing alloy/element/isotope/crystal records. No source
values or review decisions are changed by this investigation.

## Main finding

The repository has a useful research catalog and narrowly scoped calculators.
Its greatest remaining gap is turning source-backed research into canonical,
reviewed, condition-compatible observations. Adding more names alone will not
make general alloy or material prediction possible.

All six databases pass SQLite integrity and foreign-key checks. Structural
validity does not prove scientific completeness or correctness. In particular,
the reviewed core's 793 observations comprise 576 rows labeled measured and
217 curated rows; reviewed coverage must not be interpreted as 793 independent
experimental measurements.

## 1. Reviewed core coverage

| Area | Existing reviewed records | Missing capability/data |
|---|---:|---|
| Element identities | 118 | Broad physical-property coverage, ionization/electronegativity/magnetic/optical observations |
| Nuclides | 288 representative terrestrial isotopes | Broader admitted isotope/isomer evidence and nuclear-state lifecycle |
| Chemical species | 49 | Canonical graphs, stereochemistry and isotope-specific compositions |
| Molecule graphs/atoms/bonds | 0 / 0 / 0 | Ten species explicitly classed as molecules still have no molecular graph |
| Materials | 15 | Reviewed alloys/ceramics/glasses/polymers/composites and specimen/process identities |
| Mixtures | 0 | Source-observed mixtures and concentration-dependent interaction data |
| Crystal structures/space groups | 0 / 0 | Admission of staged crystallography and canonical structure/material links |
| Spectra/features/points | 0 / 0 / 0 | IR/visible/UV/X-ray/gamma data, transitions and calibration |
| Nuclear channels/cross-section points | 0 / 0 | Typed decay/capture/scattering branches and energy-dependent reaction data |

Six defined properties have no observations: electronegativity, half-life,
mass excess, binding energy, binding energy per nucleon, and nuclear spin.
Their presence in the schema is not data coverage.

The 25 core density and 25 heat-capacity observations have no attached
condition set or uncertainty. They include authored engineering values and
cannot be silently treated as matched-temperature experimental training data.
Only four melting and four boiling observations exist, also without condition
sets or uncertainty. Of the 49 species, 24 have no stored molar-mass observation;
formula-based masses can still be derived and labeled as such.

Twenty-six of 38 reactions lack condition links. The existing reactions are
stoichiometric/process definitions: balanced reactants do not supply rate
constants, equilibrium constants, thermodynamic functions, activation energy,
selectivity, catalysts, solvents, residence times or competing pathways.

The particle bootstrap contains six quarks and six leptons. It lacks canonical
proton/neutron/photon identities and the wider boson/hadron/antiparticle catalog.
Explicit emitted/incident particle identities will be needed for nuclear
channel normalization; formula/nucleon counts are not a substitute.

## 2. Alloy evidence and fit readiness

There are 59 grades and 177 property observations, but only 30 grades have any
property record. **29 grades have none**:

- Aluminum: 1100, 2024, 3003, 5052, 5083, 7075 and A356 casting.
- Copper: C11000, C17200, C36000, C65500, C70600, C71500 and C75200.
- Iron/carbon: Aero 1045; cast irons 65-45-12, 80-55-06 and G2; Interlloy
  4140; SAE1018; stainless 304, 316, 430 and 440C.
- Magnesium: AM60B, AZ91D and ZK60A.
- Silver: Argentium960 millform and traditional copper sterling silver.

| Alloy readiness check | Result |
|---|---:|
| Observations without explicit temperature | 121 / 177 |
| Observations without numeric uncertainty field | 165 / 177 |
| Typical values / ranges / minimum requirements | 120 / 32 / 25 |
| Density records with known temperature | 7 / 24 |
| Exact extractable nominal recipes | 2 / 59 |
| Reviewed property observations | 0 |

The two exact nominal recipes are traditional Ag/Cu sterling silver and
Cooksongold 18ct SW white gold. They are nominal definitions, not measured
specimen compositions. The other 57 grades have ranges, maximum-only limits,
unspecified components, combined analytes, or incomplete totals. Midpoints
and zero impurities cannot resolve these gaps honestly.

The 12 populated uncertainty fields concern hardness and include source
tolerances; they must not automatically become statistical confidence intervals.
Property counts are also uneven: yield strength covers eight grades, shear
modulus five, hardness four, and density 24.

**What blocks a useful fitted alloy model:** actual sample compositions;
consistent temperature, phase, processing and microstructure; compatible
units; reviewed source observations; independent mixed-composition samples;
and held-out validation. Pure-element endpoints alone cannot establish
precipitation, phase separation, strength, hardness or heat-treatment response.

## 3. Element physical-property gaps

The research reference has 187 observations for 33 constituents. Density source
coverage is complete when pending references are included, but context is not.
The endpoint loader extracts only 27 density, 70 mass-heat-capacity and 13
conductivity records after its basic composition/context checks. These are
still pending review and span different temperatures/states.

It extracts **zero suitable endpoints** for electrical resistivity, Young's
modulus, shear modulus and Poisson ratio. Some observations exist, but they
describe finite-purity specimens, omit conditions, or fail other endpoint
requirements. "Exists in a table" is therefore not "usable pure endpoint."

Selected remaining source-coverage gaps, including pending research:

| Constituent | Missing source rows, including pending evidence |
|---|---|
| Fe | Shear modulus |
| Cu | Resistivity, Young's/shear modulus, Poisson ratio |
| Ag | Thermal conductivity, Poisson ratio |
| Au | Resistivity, Young's/shear modulus, Poisson ratio |
| Al, Mg | Thermal conductivity, resistivity, Young's/shear modulus, Poisson ratio |
| Ti | Resistivity, Young's/shear modulus, Poisson ratio |
| Ni | Thermal conductivity, Young's/shear modulus, Poisson ratio |
| C | Thermal conductivity, resistivity, Young's/shear modulus, Poisson ratio, melting point |

Carbon/allotrope and transition-pressure distinctions are essential; a single
melting/property number for every elemental form is not the objective. The
matrix in the JSON report lists all 33 constituents. The remaining 85 elements
are outside this authored physical-property research corpus, although their
core identities and source atomic masses exist.

Normalize material-state and measurement qualifiers into a controlled contract
before combining sources. Published reference constants, finite-purity
specimens, solids, gases and liquid densities at boiling points remain distinct.
Molar-to-mass heat-capacity conversion retains its atomic-mass assumptions;
its uncertainty is not currently propagated automatically.

## 4. Crystallography gaps

There are 36 source-specific structures, 182 lattice parameters and 66 site
records. They cover six crystal systems; no triclinic example is present.

| Missing field/capability | Count |
|---|---:|
| Incomplete six-parameter cell metrics | 8 / 36 structures |
| No sites | 8 / 36 |
| Unknown space-group number | 8 / 36 |
| Unknown cell formula-unit count | 9 / 36 |
| Unknown temperature / pressure / method | 15 / 34 / 11 structures |
| Unknown site occupancy / multiplicity / Wyckoff label | 26 / 48 / 50 of 66 sites |
| Full-cell site lists | 0 |

All 28 populated site lists are asymmetric units. Twenty-seven records have
complete metric geometry and a cell formula-unit count, but that does not
validate composition, occupancy, isotope mass, symmetry expansion or density.
There is no general verified adapter from these records into the cell-density
calculator. Symmetry operators and source settings retained in JSON/CIFs need
explicit parsing and validation before expansion.

The missing implementation includes symmetry/setting/origin handling,
periodic-coordinate equivalence, full-cell multiplicities, composition/occupancy
conservation and isotope-aware mass assignment. Displacement parameters,
anisotropic tensors, defects/disorder, orientation, grain structure, porosity,
phase fractions and thermal expansion are not normalized into calculation-ready
models. Deuterated ice must never acquire ordinary-hydrogen mass implicitly.

Immediate source gaps: NaCl; composition-matched tetragonal/cubic zirconia;
resolution of the beta-Si3N4 CIF/card formula-unit disagreement. The excluded
historical Ti CIF should remain excluded until its inconsistency is resolved.
For alloy use, cementite/other Fe-C phases, solid solutions, ordered compounds,
precipitates and composition-dependent phase diagrams also need source-specific
research; elemental metal cells alone cannot describe a commercial alloy.

NIST symmetry-implied metrics are already kept separate from measured axes.
Validation should continue preserving that distinction and add independent
cell-volume/stoichiometry/density benchmark cases.

## 5. Isotope and nuclear gaps

The research reference has 39,114 observations across 5,843 source state
assignments. Every ground state has an AME reference mass entry, but **1,008
of 3,558 AME masses are upstream estimates**; only 2,550 are nonestimated
(including the neutron). "No missing mass entry" does not mean complete
experimental mass coverage.

- 87 ground states lack a reported half-life or stable designation.
- 185 ground states lack spin/parity.
- Across all source states, 359 lack reported half-life/stable designation,
  297 lack spin/parity, and 172 lack decay text.
- 16 withdrawn assignments have neither admitted atomic mass nor mass excess.
- Half-life records comprise 4,689 nonestimated points, 421 estimated points,
  100 nonestimated bounds and 20 estimated bounds; those categories must remain
  distinct. Stable nuclei have no zero-valued lifetime.

All ground states have decay text, but **zero typed nuclear channels exist in
the reviewed core**. Raw decay descriptions are not a usable decay network.
Missing pieces include daughter/state resolution, emitted/incident particles,
branching qualifiers/probabilities, mutually exclusive groups, conservation
checks, Q-values, correlations, partial half-lives, delayed emissions and
capture/cross-section curves. Spin/parity strings and asymmetric uncertainty
qualifiers similarly need safe normalization before numerical consumers.

The staging nuclide table has no first-class observed/estimated-identity/
withdrawn lifecycle field. A mass-estimate flag must not be confused with
whether a nucleus has been observed. References from 2024/2025 discoveries in
[the source follow-up](wikipedia-source-followup.md) require newer primary-data
review beyond the 2020 evaluated snapshot.

**Provenance inconsistency:** all 576 matched NIST core/research isotope values
are numerically identical, but the seed calls them `measured` while the full
importer calls them `curated`. This is a labeling-policy issue, not evidence
that the values differ. Reconcile the treatment of evaluated compilations and
record that decision before promoting additional isotope rows.

The fitted mass model remains limited to ground states and its declared domain.
It does not predict lifetime, spin, branching, radius, abundance, excited-state
energies, existence or stability. Electronic binding corrections, local-error
calibration and farther extrapolation remain limitations. Its validated errors
on known isotope holdouts are not calibrated uncertainty for an unknown nucleus.

## 6. Wikipedia and review backlog

Of the 1,239 pinned archive pages, 421 are unparsed, 96 have only error outcomes,
one is pending, 277 have no-data outcomes and 444 are parsed. A no-data result is
not proof that a page contains no scientific information.

The active queue has 4,594 candidates without a successful previous agent
action. Historical successful actions number 677 distinct IDs; one no longer
appears as an active candidate after consolidation. All candidates still
require scientific source confirmation regardless of previous keep/rewrite.

Of 717 numeric candidate facts, 223 lack unit text, 512 lack linked condition
rows and 614 lack reported numeric uncertainty. Some are dimensionless
identifiers or source facts whose conditions are not applicable; these are
triage counts, not automatic errors. Likewise, 2,077 formula-less candidates
include legitimate material/process/particle descriptions.

The existing audit flags 2,311 quotation mismatches, 43 charge/formula
disagreements, 15 nonsingle-symbol element formulas, and substantial shared
name/alias collisions. Markup/paraphrase can explain quotation mismatches;
formula equality cannot establish identity. The 11 focused correction proposals
remain unapplied and require an auditable replacement/deprecation trail.

The 7,053 new full-dump title leads have not all been read. Fourteen priority
pages were inspected (including three redirects). Primary follow-up checked
seven references, found a P4O10 DOI mismatch and Ac-203 state/uncertainty caveats.
Those follow-ups are not bulk scientific verification.

## 7. Missing integration and validation

- The initial audit found no source/license-review and promotion CLI. The first
  remediation adds an elemental admission adapter with reviewer records;
  alloy specimens, crystal structures and nuclear channels still require
  family-specific admission adapters.
- The research references use separate IDs and unit strings. Entity/specimen
  crosswalks, canonical phase/process qualifiers, conflict selection and
  supersession rules need implementation rather than string-only matching.
- Core units/properties need extension or exact mapping for crystal angles,
  lattice lengths, elasticity, transport, magnetic and optical observations.
- The alloy fitter has no independent validation or predictive uncertainty;
  its training residuals alone do not establish predictive accuracy.
- The isotope model has coordinate/chain-edge holdouts, but still lacks
  independent later-evaluation validation and calibrated unknown-domain errors.
- The material descriptor trains on only 15 reviewed materials, mostly ores.
  Its taxonomy/nearest-neighbor benchmark is not a physical-property benchmark.
- Ideal mixture rules cannot determine phase diagrams, reaction equilibrium,
  microstructure, fracture, corrosion, creep, fatigue or processing history.
- Release integrity checks do not validate every staged physical claim or
  every crystal's full symmetry/content. Empty reviewed schema families also
  leave many otherwise valid validator paths without populated benchmarks.

Some roadmap checkboxes now lag implementation: research alloy/crystal/isotope
imports and model holdouts exist, while their reviewed admission remains open.
Track those as separate milestones instead of marking the entire topic done.

## 8. Release and deployment gap

GitHub currently exposes only the [recent release](https://github.com/szajsjem/universe-db/releases/tag/recent),
published 2026-08-01, with `universe.db`, its checksum and a manifest. Checked
through the GitHub CLI on 2026-10-12. The newer combined/Wikipedia/unverified
bundles and standalone references are local outputs, not assets on that public
release. A successful `main` database CI run does not publish them: the release
workflow requires a tag push or manual dispatch against an existing tag.

Crystallography and current README changes are also local/uncommitted at the
time of this audit. A new commit/tag and release run are required to publish
them. The local 2026.10.12 bundle predates crystallography; the later local
`crystallography-20261012` export includes it. Generated combined databases can
exceed regular GitHub Git file limits and belong in release assets; binary
snapshot history also needs a long-term storage policy.

## Recommended order

1. **Define canonical admission and provenance rules.** Resolve the 576 NIST
   labeling differences; build reviewed source/specimen/unit/condition mappings
   and an auditable promotion tool. This unlocks existing research safely.
2. **Make a small alloy benchmark genuinely usable.** Obtain exact sample
   compositions and matched-state density/Cp/transport/elastic measurements for
   representative Fe-C, Cu, Al, Mg, Ti and Ni systems. Validate held-out mixtures;
   do not start by filling every maximum-only impurity limit.
3. **Finish the crystal calculation bridge.** Expand/validate symmetry and cell
   content, isotope mass, occupancies and source settings for a small benchmark
   set; compare derived densities against independent references.
4. **Normalize nuclear properties and channels.** Admit one evaluated isotope
   slice with state-aware lifetime/spin/decay/uncertainty handling and a conserved
   decay-chain benchmark; then extend to capture/cross-section data.
5. **Resolve the selected Wikipedia corrections and primary leads.** Repair
   demonstrated type errors and citation issues, then prioritize remaining
   pages by missing scientific data rather than title count.
6. **Publish the reproducible new release.** Commit reviewed changes, choose a
   new tag, run release CI, verify assets and document reviewed versus research
   status. Continue molecular-graph, spectra, kinetics and wider engineering
   datasets as explicit additional milestones.
