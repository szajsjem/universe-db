# Contributing

Contributions should add a small, reviewable source slice rather than a large
unsourced dump.

## Workflow

1. Open an issue describing the source, upstream release, license, data
   families, expected row counts, and transformation.
2. Add or update `license`, `source`, and `dataset` rows before scientific data.
3. Put schema changes in a new numbered migration. Never rewrite a migration
   that has appeared in a release.
4. Put deterministic data/import output in a numbered file under `seed/`.
5. Add validation for new dimensional, conservation, ordering, or probability
   invariants.
6. Run `make check` and include the regenerated `universe.db`,
   `universe.db.sha256`, `universe-unverified.db.sha256`, and `manifest.json`.
   If the reviewed database hash changes, rebase or regenerate the companion
   `universe-unverified.db` as well; its manifest records the exact reviewed
   artifact from which it was created.

SQL files execute in lexical order. Use stable text IDs and explicit `ORDER BY`
clauses for inserts derived from temporary staging tables. Do not use current
timestamps, random IDs, locale-dependent sorting, or floating-point literals.

The periodic table is a generated exception to hand-authored seed SQL. Its
vendored, dated PubChem response lives in `sources/`, and
`scripts/import_pubchem_periodic_table.py` deterministically produces
`seed/004_periodic_table.sql`. Refreshes must create a new dated snapshot and
dataset identity; do not silently replace the released 2026-07-28 source.

The same rule applies to the NIST isotope snapshot and
`scripts/import_nist_isotopes.py`. The “common” set is selected only by a
non-empty NIST representative isotopic-composition field. Do not add isotopes
to that designation based on familiarity, medical use, or an arbitrary
abundance threshold; create a separately sourced designation instead.

The Wikipedia chemistry ZIP is a bounded discovery snapshot, not a reviewed
scientific dataset. Refresh it with
`scripts/download_wikipedia_chemistry.py`, retain its permanent revision URLs
and CC BY-SA attribution, and update the dated source identity and digest.
Results from `scripts/parse_wikipedia_archive.py` may enter only the
`unverified_*` candidate tables until independently reviewed.
Release snapshots retain all parsing attempts for provenance, but publishing
`universe-unverified.db` does not constitute review or promotion.

## Stable IDs

IDs use a lowercase namespace prefix:

```text
particle:electron
element:copper
nuclide:copper-63
chem:water
material:cathode_copper
reaction:chalcopyrite_roasting
```

An alias is not a second entity. A polymorph, ion, isotopologue, mixture, or
material form may be a separate entity when it has a distinct scientific
identity.

## Corrections

Do not edit a released observation in place merely to make it agree with
another source. Add the new observation, retain the disagreement, and document
any reviewed preference. Identity corrections use lifecycle state and
replacement links.
