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
- `element` records atomic number and symbol;
- `nuclide` records proton count, neutron count, and isomer index;
- `chemical_species` distinguishes atoms, molecules, ions, formula units,
  complexes, polymers, and unresolved placeholders;
- `material`, `mixture`, and `crystal_structure` describe larger-scale forms.

`alias` stores external identifiers and names without turning them into
canonical identities.

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
`nuclear_cross_section_point` stores energy-ordered cross-section curves with
units and uncertainty.

## Migrations

`PRAGMA user_version` is the machine-readable schema version.
`schema_migration` records every applied migration and its SHA-256 digest.
The build is atomic: a failed migration, seed, or integrity check never
replaces the last accepted artifact.
