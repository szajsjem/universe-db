# Crystal cell validation

`scripts/crystal_cell.py` audits staged crystal structures without modifying or
promoting evidence. It expands explicitly reported symmetry operations into
periodically wrapped exact rational coordinates, deduplicating each independent
site orbit. It checks reported multiplicities, coincident independent orbits,
position occupancy sums, and composition against formula times cell formula
units Z. D and T in formulas denote H-2 and H-3; explicit isotope formulas require
matching isotope sites. Ordinary elemental formulas compare elemental totals.

```powershell
python scripts/crystal_cell.py --db crystals.db --output .build/crystal-cell-audit.json
```

The deterministic library entry points are `parse_operation(operation)`,
`apply_operation(parsed_operation, coordinates)`,
`audit_structure(structure, operations=None, masses=None)` and
`audit_database(path, root=ROOT)`. Structures use the builder's source JSON shape.
Database auditing reads in SQLite read-only mode and verifies source CIF SHA256
when the source record identifies a pinned file. Only explicit operations from
that CIF or the authored source transcription are used; a space-group number
alone never supplies operations. The CIF reader supports simple scalar symmetry
loops, not arbitrary CIF syntax. Unsupported input is reported as blocked.

The symmetry parser accepts signed rational constants and integer linear
combinations of x, y and z, with an integer unimodular linear part. It never
executes expressions. Coordinates remain exact fractions; no tolerance is used
for merging rounded near-special positions. A multiplicity mismatch can therefore
identify coordinate rounding rather than a false experimental claim. Inspect the
source refinement before interpreting a conflict or correcting coordinates.
Operations are treated as the source's complete supplied list; the auditor does
not determine a space group, prove group closure, or add omitted operations.

Unknown occupancy blocks cell composition and density. No missing occupancy,
pressure, temperature, cell angle, or multiplicity receives a default. Independent
coincident site orbits remain separate evidence and block density, including
possible disorder that needs an explicit treatment. Unknown Z, incomplete cell
metrics, formula mismatch, and known multiplicity conflict also block density.

For density, the caller must explicitly pass cited atomic masses in u, keyed by
natural element (`Cu`) or isotope (`H-2`), for example
`{"H-2": {"value": "2.01410177812", "source": "source citation"}}`.
Isotope mass numbers are never substituted for atomic masses. Density is labeled
`modeled` and `pending_human_review`, carries mass inputs and source conditions,
and records floating trigonometry and lack of uncertainty propagation. The
atomic mass constant matches the repository's CODATA 2022 calculator constant.
The CLI deliberately supplies no implicit mass selections.

The initial 36-structure audit expands 22 structures, obtains eight compositions
with reported occupancies, and confirms six formula/Z totals. Exact expansion
flags a quartz rounded-special-position multiplicity/composition discrepancy and
an ice-Ih composition/Z discrepancy. These are review leads, not source edits.
Fourteen structures remain blocked before expansion because explicit operations
or sites are unavailable in the normalized source inputs; further CIF
transcription can improve that coverage without guessing.
