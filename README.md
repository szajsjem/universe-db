# Universe Database

`universe.db` is a public, reproducible SQLite database for structured physics,
chemistry, materials, spectra, and nuclear data. The goal is one queryable
source without flattening scientific context into prose or pretending that
missing values are zero.

The checked-in artifact is built entirely from the versioned SQL in
[`migrations/`](migrations) and [`seed/`](seed). It is intentionally small
today. The schema is broad; the reviewed data will grow source by source.

## Current coverage

| Family | Seeded now | Schema ready |
|---|---:|:---:|
| Quarks and leptons | 12 identities | yes |
| Elements / atoms | 16 elements | yes |
| Nuclides and isomers | 0 | yes |
| Chemical species | 25 | yes |
| Molecular atom/bond graphs | 0 | yes |
| Materials and ores | 13 | yes |
| Mixtures | 0 | yes |
| Crystal structures and lattice sites | 0 | yes |
| Chemical/process reactions | 3 | yes |
| Ion dissociation | 0 | yes |
| IR / visible / UV / X-ray spectra | 0 | yes |
| Nuclear decay and capture channels | 0 | yes |
| Energy-dependent cross sections | 0 | yes |

Zero means “not imported,” never “known to be absent.” Run
`python3 scripts/report.py universe.db` for the live counts.

The particle identity bootstrap is attributed to the Particle Data Group’s
2024 *Review of Particle Physics* under CC BY 4.0. The chemistry bootstrap
comes from the authored Inorganic Engineering catalog
at commit `af5a553`: 16 elements, 25 species, 12 ore/mineral mappings, cathode
copper, and three balanced process definitions. Those values are labeled
`curated`; they are not silently upgraded to `measured`.

## Use the artifact

```sh
sqlite3 universe.db
```

Example queries:

```sql
SELECT entity_id, name
FROM entity_summary
WHERE entity_type = 'chemical_species';

SELECT e.symbol, o.value_numerator, u.symbol AS unit
FROM element AS e
JOIN observation AS o ON o.subject_entity_id = e.entity_id
JOIN unit AS u ON u.unit_id = o.unit_id
WHERE o.property_id = 'property:atomic_mass'
ORDER BY e.atomic_number;

SELECT r.name, rp.role, cs.formula, rp.coefficient_numerator
FROM reaction AS r
JOIN reaction_participant AS rp USING (reaction_id)
JOIN chemical_species AS cs ON cs.entity_id = rp.species_id
ORDER BY r.reaction_id, rp.role DESC, cs.formula;
```

## Rebuild and verify

Requirements are Python 3.11+ and its standard-library SQLite module. There are
no third-party runtime or build dependencies.

```sh
make build
make check
sha256sum --check universe.db.sha256
```

`make check` performs SQLite integrity and foreign-key checks, exact reaction
balance validation, a byte-for-byte reproducibility test, and an artifact
freshness test. It does not invoke Gradle or build the Minecraft mod.

The build writes:

- `universe.db` — release-ready SQLite artifact;
- `universe.db.sha256` — SHA-256 checksum;
- `manifest.json` — schema version, SQLite version, hash, and all table counts.

## Design rules

- Every imported dataset identifies its source, version, provenance class, and
  redistribution status.
- Scientific values use integer rationals plus explicit units; decimal text and
  binary floating point are not authoritative storage formats.
- Conditions and uncertainty remain attached to observations.
- Conflicting observations can coexist. A preference is review metadata, not a
  destructive overwrite.
- Measured, modeled, curated, hypothetical, and fictional records cannot be
  silently conflated.
- Spectra and cross sections store ordered points with axis units, conditions,
  uncertainty, and source metadata.
- Nuclear channels use typed parents, daughters, incident/emitted particles,
  branch probabilities, and energy-dependent cross sections.
- Missing source data stays missing. There are no generated “reasonable”
  measurements or Wikipedia prose scrapes.

See [the schema guide](docs/schema.md), [data policy](DATA_POLICY.md), and
[contribution workflow](CONTRIBUTING.md). Planned data-source expansion is
tracked in the [roadmap](ROADMAP.md).

## Relationship to Inorganic Engineering

This is a standalone repository and release artifact. The Minecraft mod may
later consume deterministic exports, but game servers should not query SQLite
on the tick thread. Database releases and mod releases can therefore evolve
independently.

## Licensing

The schema, scripts, documentation, and original chemistry bootstrap data are
MIT licensed. Particle identity data is attributed to the Particle Data Group
under CC BY 4.0. Each external source has its own row in `license` and `source`.
Future imports must be redistributable before their data can enter the checked-
in artifact. Citation does not override an upstream license.
