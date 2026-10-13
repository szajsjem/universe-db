# Manually selected mod chemistry research — 2026-10-13

Three parallel research agents manually inspected primary sources and authored
three small, cited input slices. The parent reviewed the inputs, checked
formula/atom counts and existing candidate links, and imported them into
`universe-unverified.db`. This is **pending human review**, as required by
[DATA_POLICY.md](../DATA_POLICY.md); neither parallel agents nor database
integrity checks constitute scientific promotion.

The [second batch](manual-mod-chemistry-batch2.md) adds another 18 targets and
52 cited facts. Totals across both batches are 36 targets, 100 textual facts
and 36 structured identity records; the counts below describe batch 1 only.

## Coverage

| Slice | Compounds | Potential mod use |
| --- | --- | --- |
| [Propellants](manual-propellant-research.md) | Hydrazine, monomethylhydrazine, dinitrogen tetroxide, unsymmetrical dimethylhydrazine, hydrogen peroxide, nitrous oxide | Monopropellant attitude control, storable bipropellant families, alternative oxidizers/cold-gas research |
| [Process chemistry](manual-process-research.md) | Ammonium bifluoride, sodium aluminate, lithium chloride, ethanolamine, sodium metabisulfite, zinc chloride | Surface processing, coagulation, desiccants/adsorbent precursors, acid-gas solvents, reducing chemistry and electrochemistry |
| [Planet/life support](manual-planet-research.md) | Lithium hydroxide, calcium hydroxide, sodium carbonate, ethylene glycol, propylene glycol, lithium hexafluorophosphate | Consumable CO2 scrubbers, water treatment, coolant formulations and battery electrolytes |

The batch contains **18 compound targets**, **48 source-backed textual facts**,
and **18 structured identity records**: 66 tasks/facts/source links across three
research runs. The identity records preserve formulas, compositions, charge,
classification, aliases and existing candidate links. Calcium hydroxide and
sodium carbonate link reviewed identities; seven more targets enrich existing
candidate/name leads. Nine targets were not found in the agents' bounded
identity searches. That last count is discovery coverage, not proof of absence
under every possible synonym or a claim of nine newly discovered chemicals.
All 118 reviewed element identities were already present; none was duplicated.

No numerical measurements, operating temperatures, capacities, efficiencies,
planetary deposit abundances or gameplay recipe yields were invented. The
`usefulness` field is a proposed game-design role, stored in research-run notes
separately from sourced facts. A formulated product, blend, solvent grade,
hydrate or zeolite material is not silently identified with a neat compound.

The reviewed `universe.db`, schema, previous Wikipedia candidates and auxiliary
alloy/element/isotope databases are unchanged. The mod repositories and ICM's
pinned catalog are also unchanged: this batch adds database research, not
implemented fluids, tanks, engines or recipes. The ICM candidate exporter reads
`unverified_entity_candidate`; it does not automatically consume these new
`unverified_fact` records. A separately reviewed identity mapping and exporter
change would be needed before turning these leads into runtime catalog entries.

## Source ownership and provenance

The versioned inputs are under
[`sources/manual-chemistry/`](../sources/manual-chemistry/). Each fact records a
primary source URL, title, retrieval date, short original supporting paraphrase
and factual-only redistribution basis. Sources include NIST identities,
NASA propulsion/life-support pages and original reports, drinking-water
institutional guidance, DOE literature, manufacturer product references and
an original glass-treatment patent. The supporting prose is not a copied source
table or substantial quotation.

Source snapshots are not mislabeled as a Wikipedia parse. The loader uses the
existing `research_run`, `research_task`, `unverified_fact` and
`unverified_fact_source` tables. Every run identifies the browser-assisted
model research, checked-in input SHA-256, source date and reviewed-base hash.
Every fact retains per-source date/license metadata and pending-review status.
Timestamps normalize the retrieval date to midnight solely for schema
compatibility; the run notes explicitly retain day precision.

`research_task.target_kind` uses the existing coarse `molecule` compound-work
index. Actual scientific classification remains `molecule` or `formula_unit`
in `unverified_fact.target_kind` and the structured identity JSON. Ionic salts
are not claimed to consist of isolated neutral molecules. An existing N2O
candidate incorrectly classified as an element remains only a linked research
lead; this import does not reproduce that classification.

## Offline import and querying

```sh
python3 scripts/import_manual_chemistry.py
```

This imports the sorted dated slices into the checked-in companion database
and refreshes its checksum and `manifest.json`. It does not access the network,
change schemas, alter the reviewed base or promote a fact. All inputs are
validated before publication. Updates are staged beside the output and checked
for SQLite integrity/foreign-key consistency before replacement. Replaying an
identical input is a no-op at the row level; changing a previously imported
dated filename is rejected. Publish a newly named input for later corrections.

For regeneration starting from the previous companion artifact:

```sh
mkdir -p .build
git show e8ed409:universe-unverified.db > .build/manual-chemistry.db
python3 scripts/import_manual_chemistry.py --database .build/manual-chemistry.db
```

The loader checks that the input companion's reviewed-base SHA-256 matches the
current checked-in `universe.db`. Numeric formula counts use integers; simple
parenthesized groups are supported, while isotope/complex/hydrate notation is
outside this authoring format. Candidate links require matching composition
when a candidate has a formula, and matching charge when recorded. Any reused reviewed species ID must match its composition and charge; IDs
owned by another entity kind are rejected. No reviewed entity is linked solely
because a name looks similar.

Read the identity/engineering facts with their primary citations:

```sql
SELECT f.target_id, f.target_kind, f.field_key, f.value_text,
       s.url, s.title, s.supporting_text
FROM unverified_fact AS f
JOIN unverified_fact_source AS s USING (fact_id)
JOIN research_task AS t USING (task_id)
WHERE t.run_id LIKE 'manual-chemistry:%'
ORDER BY f.target_id, f.field_key, s.source_index;
```

Use `field_key = 'compound_identity'` for the structured identity JSON. Original
JSON inputs additionally retain the design rationale and retrieval/redistribution
metadata. Fact method notes and run notes retain that metadata in SQLite.

## Checks performed

The parent parsed all input JSON and importer Python as source. The import
validated formulas/composition, symbols, integer charge, HTTPS citations,
provenance fields, duplicate fact keys, candidate links and cross-slice identity
consistency. The importer also passed pinned Ruff 0.12.12 source lint/format checks.
The final SQLite integrity result is `ok`, foreign-key violations
are zero, and recorded database checksums match the artifacts. The reviewed-base
hash stayed unchanged.

No compilation, project test suites, scientific promotion or mod runtime tests
were run on this server. The importer is a new authoring tool and needs local
regression coverage for malformed formulas, conflicting/unknown candidate links,
changed-input rejection, replay, transaction rollback and byte-level
reproducibility. Human review of every primary source and identity mapping remains
the scientific admission gate before enabling these records as game chemistry.
