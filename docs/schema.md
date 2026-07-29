# Schema guide

The schema separates identity, evidence, composition, structure, and process.
That keeps one database queryable without collapsing unlike scientific claims
into a single universal value.

## Provenance and values

`license` → `source` → `dataset` records the legal and scientific origin of
each imported slice. `observation` attaches a rational value, unit, optional
uncertainty, optional condition set, method, provenance class, and source to an
entity. `property_definition` gives observations a typed quantity.

`unit` stores an SI conversion as:

```text
(si_scale_numerator / si_scale_denominator) × 10^si_scale_power10
```

All authoritative values use SQLite integers.

## Shared identities

`entity` is the stable identity registry. Specialized one-to-one tables add
meaning:

- `particle` distinguishes quarks, leptons, bosons, and composite particles;
- `element` records atomic number, symbol, PubChem chemical group/block,
  electron configuration, and source-authored standard-state label;
- `nuclide` records proton count, neutron count, and isomer index;
- `chemical_species` distinguishes atoms, molecules, ions, formula units,
  complexes, polymers, and unresolved placeholders;
- `material`, `mixture`, and `crystal_structure` describe larger-scale forms.

`alias` stores external identifiers and names without turning them into
canonical identities.

`nuclide_designation` records source-specific selection semantics. The initial
NIST import uses `natural_isotopic_composition`; it does not assert that every
selected nuclide is stable. Relative atomic mass and representative isotopic
composition are separate `observation` rows with rational uncertainty and
source conditions.

## Chemistry and matter

`species_element` and `species_nuclide` give exact composition.
`species_phase` records source-supported phases under a condition set.
`molecule`, `molecular_atom`, and `molecular_bond` hold explicit connectivity;
a formula alone is not treated as a molecular graph.

`material_component` can represent exact fractions or an explicitly
unspecified mineral/gangue relationship. `mixture_component` stores
condition-dependent amounts against any entity.

## Crystallography

`crystal_system` and `space_group` are controlled vocabularies.
`crystal_structure` links a structure to one species or material.
`crystal_lattice_parameter` stores cell lengths/angles and uncertainty;
`crystal_lattice_site` stores fractional coordinates and occupancy.

## Reactions and dissociation

`reaction` plus `reaction_participant` stores directed, rational
stoichiometry with phase. `reaction_condition` attaches required or measured
conditions. A dissociation is a typed reaction with an additional
`dissociation` row; reversible chemistry is represented explicitly, not as an
alias cycle.

## Spectra

`spectrum` identifies subject, region (including infrared, visible,
ultraviolet, and X-ray), spectrum type, axis/intensity units, conditions,
resolution, dataset, and source. `spectrum_point` stores ordered rational
points; `spectral_feature` stores reviewed peaks, edges, bands, and lines.

## Nuclear data

`nuclear_channel` links typed decay/capture processes to parent and daughter
nuclides with optional branch probability and conditions.
`nuclear_channel_particle` stores incident and emitted particles.
`nuclear_channel_nuclide` stores incident and emitted nuclides, allowing
target/projectile fusion and other nuclide–nuclide channels without pretending
that a nuclide is an elementary particle. A channel may reference a sourced
partial-half-life observation.
`nuclear_cross_section_point` and
`nuclear_cross_section_velocity_point` store energy- or speed-ordered
cross-section curves with units and uncertainty.

## Unverified research staging

`research_run` and `research_task` record opt-in model/web-search work.
`unverified_fact`, `unverified_fact_condition`, and
`unverified_fact_source` preserve the result, exact decimal-to-rational
conversion when it fits SQLite, conditions, relation hints, and supporting
URLs. These tables are a review queue, not scientific authority. Normal
builds create them empty, validators do not promote them, and exporters do not
read them.

The second staging path is page-oriented. `wikipedia_parse_run` identifies the
source archive and model; `wikipedia_page_parse` pins every parse to an archive
entry, source path/URL, input format, and content digest. MediaWiki snapshots
also retain the page ID, revision ID, permanent URL, and revision timestamp;
Kiwix entries retain the release date and canonical page URL.
`unverified_entity_candidate` may propose a new particle, element, nuclide,
atom, molecule, ion, formula unit, complex, polymer, material, mixture, or
reaction without first creating an authoritative entity. Candidate alias,
composition, fact/condition, and relation tables preserve structured output.
Reaction participants and nuclear incident/emitted entities are staged as
relations until reviewed identities and conservation checks are available.

Field placement for the current research target is:

- melting/boiling temperatures, electronegativity, molar mass, abundance,
  spin, half-life, mass excess, and binding energy are typed observations;
- pressure and other applicable state belong in condition sets;
- electron configuration is source-authored element metadata;
- spectra use spectrum/point/feature relationships;
- decay probabilities and daughters use nuclear channels;
- fusion and induced-reaction probabilities versus energy or relative speed
  use typed participants plus cross-section points.

## Migrations

`PRAGMA user_version` is the machine-readable schema version.
`schema_migration` records every applied migration and its SHA-256 digest.
The build is atomic: a failed migration, seed, or integrity check never
replaces the last accepted artifact.

## Datapack export boundary

The SQLite schema remains target-neutral. The
`profiles/inorganicengineering-0.1.json` export profile supplies only
Minecraft-specific presentation values, compatibility tags, public resource
paths, and machine-family assignments. The exporter reads scientific
quantities, compositions, phases, material fractions, reaction participants,
and operating ranges from the database.

Every rational value crossing into an integer-only datapack field must divide
exactly. Unspecified ore fractions are eligible for mineral/gangue identity
export but not material-composition export. Unsupported participant roles,
missing condition bounds, incomplete presentation metadata, and profile/data
coverage drift stop the export rather than selecting a fallback scientific
value.
