# Universe Database

`universe.db` is a public, reproducible SQLite database for structured physics,
chemistry, materials, spectra, and nuclear data. `universe-unverified.db` is a
separate companion release containing the collected candidate data that has
not completed scientific review. The goal is one queryable source without
flattening scientific context into prose or pretending that missing values are
zero.

The checked-in artifact is built entirely from the versioned SQL in
[`migrations/`](migrations) and [`seed/`](seed). It is intentionally small
today. The schema is broad; the reviewed data will grow source by source.

## Current coverage

| Family | Seeded now | Schema ready |
|---|---:|:---:|
| Quarks and leptons | 12 identities | yes |
| Elements / atoms | 118 elements | yes |
| Nuclides and isomers | 288 naturally representative isotopes | yes |
| Chemical species | 49 | yes |
| Molecular atom/bond graphs | 0 | yes |
| Materials and ores | 15 | yes |
| Mixtures | 0 | yes |
| Crystal structures and lattice sites | 0 | yes |
| Chemical/process reactions | 38 | yes |
| Ion dissociation | 14 | yes |
| IR / visible / UV / X-ray spectra | 0 | yes |
| Nuclear decay and capture channels | 0 | yes |
| Energy-dependent cross sections | 0 | yes |

Zero means “not imported,” never “known to be absent.” Run
`python3 scripts/report.py universe.db` for the live counts.

The complete element identity table is generated from a vendored snapshot of
PubChem’s official PUG REST periodic-table endpoint. It includes names,
symbols, atomic numbers, relative atomic masses, chemical group/block,
electron configurations, and source-authored standard-state labels for
elements 1–118. PubChem values are retained as source-specific observations;
they are not relabeled as CIAAW standard atomic weights.

“Common isotopes” has a reproducible meaning here: the 288 nuclides across 84
elements for which NIST publishes a non-empty representative terrestrial
isotopic composition. Each stores proton/neutron counts, exact rational
relative atomic mass and uncertainty, exact rational abundance and uncertainty,
source notes, and a natural-composition designation. Their abundances sum
exactly to one per represented element. Trace-only, synthetic, and merely
well-known laboratory isotopes are not silently added to this set.

The particle identity bootstrap is attributed to the Particle Data Group’s
2024 *Review of Particle Physics* under CC BY 4.0. The chemistry bootstrap
comes from the authored Inorganic Engineering catalog
at commit `af5a553`: 16 elements, 25 species, 12 ore/mineral mappings, cathode
copper, and three balanced process definitions. Those values are labeled
`curated`; they are not silently upgraded to `measured`.

An additional hand-authored industrial chemistry slice adds 24 species, coal
and copper-anode material identities, and 35 balanced reactions. It covers
carbon combustion and producer-gas chemistry, iron-ore reduction and slag
formation, copper reduction, cementation, electrorefining and electrowinning,
plus acid ionization, neutralization, and common salt dissociation. It asserts
no measured property values or numeric operating envelopes.

## Use the artifact

```sh
sqlite3 universe.db
```

Use `universe-unverified.db` only when unreviewed Wikipedia/model-extracted
candidates and their parsing provenance are intentionally required:

```sh
sqlite3 universe-unverified.db
```

Example queries:

```sql
SELECT entity_id, name
FROM entity_summary
WHERE entity_type = 'chemical_species';

SELECT e.symbol, o.value_numerator, o.value_denominator
FROM element AS e
JOIN observation AS o ON o.subject_entity_id = e.entity_id
WHERE o.property_id = 'property:relative_atomic_mass'
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
sha256sum --check universe-unverified.db.sha256
```

`make check` performs the dependency-free
[publication validation gates](docs/validation.md), complete periodic-table
validation, a byte-for-byte same-runtime reproducibility test, and a logical
artifact freshness test that is stable across SQLite library versions. Release
checksums authenticate the exact published files. The datapack exporter runs
those same gates before reading its profile. It does not invoke Gradle or build
the Minecraft mod.

Normal builds are network-independent. To intentionally capture a new PubChem
snapshot and regenerate its SQL:

```sh
python3 scripts/import_pubchem_periodic_table.py --download
python3 scripts/import_nist_isotopes.py --download
make check
```

A new upstream snapshot should receive a new dated source filename and dataset
ID rather than overwriting a released source.

### Optional unverified web-research overlay

Bulk, licensed, reproducible source imports are preferred. For gap discovery,
the repository also includes an opt-in web-research staging script. It plans
one request per target and field, uses the Responses API web-search tool, and
never writes model output into reviewed observations:

```sh
# Inspect request counts and example prompts without spending API credits.
python3 scripts/research_missing_data.py --limit-targets 2

# Trial run into .build/unverified.db. OPENAI_API_KEY must be set.
python3 scripts/research_missing_data.py \
  --limit-targets 2 \
  --max-requests 5 \
  --execute \
  --accept-cost
```

The Responses API base URL and model are configurable. A loopback server does
not require an API key unless its own authentication is enabled:

```sh
python3 scripts/research_missing_data.py \
  --base-url http://127.0.0.1:8080/v1 \
  --model local-model \
  --limit-targets 2 \
  --max-requests 5 \
  --execute \
  --accept-cost
```

The server must implement the OpenAI-compatible `/responses` endpoint and the
web-search tool used by this research command. `--base-url` may point either to
the API root (such as `/v1`) or directly to `/v1/responses`.

The default model is `gpt-5.4-nano`. The script skips fields already covered by
reviewed data, resumes around previously found staged values, stores source
URLs and conditions, and can later include `molecules,reactions` with
`--scopes`. An unrestricted all-nuclide run can make thousands of paid web
searches; always review the dry-run count first. Staged facts remain
unverified and are excluded from normal builds and exports.

### Wikipedia chemistry releases and sequential parser

The repository vendors both a bounded, revision-pinned wikitext ZIP and the
official Kiwix chemistry mini ZIM. The parser processes pages independently and
stages candidate identities, facts, compositions, relationships, evidence, and
complete run provenance. Plan without contacting a model:

```sh
make wikipedia-plan
```

Then start with a small local trial:

```sh
python3 scripts/parse_wikipedia_archive.py \
  sources/wikipedia-chemistry-category-snapshot-2026-07-29.zip \
  --max-pages 5 --execute
```

Successful pages are committed individually and skipped on reruns; errors are
retried. Report pages still missing a successful parse with:

```sh
python3 scripts/list_missing_wikipedia_pages.py \
  sources/wikipedia-chemistry-category-snapshot-2026-07-29.zip \
  .build/wikipedia-unverified.db \
  .build/wikipedia-missing-pages.csv
```

Repeated page mentions can then be consolidated into a copied snapshot:

```sh
python3 scripts/clean_wikipedia_candidates.py \
  .build/wikipedia-unverified.db \
  --output .build/wikipedia-cleaned.db --execute
```

Plan bounded atom/molecule review without contacting a model:

```sh
python3 scripts/review_wikipedia_candidates.py .build/wikipedia-cleaned.db
```

The complete source-verification, extraction, resume, cleanup, review, and
recovery instructions are in the
[Wikipedia candidate workflow](docs/wikipedia-workflow.md). Wikipedia and
model output remain unverified even after cleanup or agent review; none of
these commands promotes candidates into reviewed scientific tables.

The release contains:

- `universe.db` — release-ready SQLite artifact;
- `universe.db.sha256` — SHA-256 checksum;
- `universe-unverified.db` — all currently collected, unreviewed candidate data;
- `universe-unverified.db.sha256` — companion artifact SHA-256 checksum;
- `manifest.json` — schema versions, hashes, table counts, data status, and
  Wikipedia parsing progress for both artifacts.

## Calculate deterministic atomic and composition properties

The dependency-free property calculator evaluates exact composition invariants,
reviewed-source mass aggregates, optional ideal-gas density, and an explicitly
labeled semi-empirical nuclear model. It has no fitting step, learned weights,
randomness, or network access:

```sh
python3 scripts/calculate_properties.py --formula H2O
python3 scripts/calculate_properties.py --species chem:carbonate
python3 scripts/calculate_properties.py \
  --atomic-number 26 --neutrons 30 --charge 2
```

It reports why structure-, phase-, state-, and evidence-dependent properties
cannot be identified from an atomic number or elemental composition. See
[`docs/deterministic-properties.md`](docs/deterministic-properties.md) for the
equations, method classes, validity limits, and references.

## Describe an unreviewed material

The dependency-free material descriptor fits a deterministic, composition-based
k-nearest-neighbour model directly from the reviewed `material`,
`material_component`, `chemical_species`, and `species_element` rows. It can
describe a material identity that is not in the database without inserting it
or inventing physical properties:

```sh
python3 scripts/describe_material.py \
  --name "siliceous iron oxide concentrate" \
  --component Fe2O3=0.85 \
  --component SiO2=0.15 \
  --basis mass_fraction
```

The JSON result reports resolved and formula-only components, a normalized
element embedding, nearest reviewed analogues, material-kind inference,
applicability/abstention, model version, and the exact database SHA-256 used for
training. It is explicitly a model output, not a reviewed observation.

Run its leakage-controlled leave-one-material-out benchmark with:

```sh
make material-benchmark
```

The current corpus contains only 15 materials and is dominated by ores. The
benchmark therefore exposes both accuracy and macro recall plus a majority
baseline; it does not claim that singleton kinds are validated. See
[`docs/material-descriptor.md`](docs/material-descriptor.md) for the input
contract, algorithm, validation method, and limitations.

## Export the Inorganic Engineering datapack

The checked-in `inorganicengineering-0.1` export profile combines scientific
rows from `universe.db` with target-specific presentation metadata and machine
IDs. Keeping those target details in the profile prevents Minecraft fields
from being mistaken for scientific observations.

```sh
make export
```

This writes `dist/inorganicengineering-0.1.zip`, a directly installable
Minecraft 1.21.1 datapack. It contains the reviewed bootstrap's 16 referenced
elements, 25 species, 12 mineral definitions, cathode-copper material, and
three conserved process recipes.

The ZIP uses sorted paths, fixed timestamps, stable permissions, and stored
entries so repeated exports from the same database and profile are
byte-for-byte identical. `universe-db-export.json` records the database and
profile SHA-256 digests plus a digest for every payload file. The exporter
fails instead of rounding rational values or filling absent scientific fields.

Custom paths are available without third-party dependencies:

```sh
python3 scripts/export_inorganicengineering.py \
  --database universe.db \
  --profile profiles/inorganicengineering-0.1.json \
  --output /path/to/inorganicengineering.zip
```

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
  measurements, and Wikipedia-derived candidates are never promoted
  automatically.

See [the schema guide](docs/schema.md), [data policy](DATA_POLICY.md), and
[contribution workflow](CONTRIBUTING.md). Planned data-source expansion is
tracked in the [roadmap](ROADMAP.md).

## Relationship to Inorganic Engineering

This is a standalone repository and release artifact. The Minecraft mod build
statically imports a pinned `universe.db` release or its deterministic datapack
export and packages the generated resources. Game runtime must not query
SQLite, call a model, or access the network. Database releases and mod releases
can therefore evolve independently.

## Licensing

The schema, scripts, documentation, and original chemistry bootstrap data are
MIT licensed. Particle identity data is attributed to the Particle Data Group
under CC BY 4.0. Periodic-table data is attributed to PubChem/NLM, natural
isotope data to NIST, and the revision-pinned Wikipedia source archive is CC
BY-SA 4.0. Each external source has its own row in `license` and `source`.
Future imports must be redistributable before their data can enter the checked-
in artifact. Citation does not override an upstream license.
