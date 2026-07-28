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
   `universe.db.sha256`, and `manifest.json`.

SQL files execute in lexical order. Use stable text IDs and explicit `ORDER BY`
clauses for inserts derived from temporary staging tables. Do not use current
timestamps, random IDs, locale-dependent sorting, or floating-point literals.

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
