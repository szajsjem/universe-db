# Additional mod chemistry research — batch 2, 2026-10-13

Three research agents continued the manually selected source review with
**18 other compound targets and 52 cited textual facts**. The parent reviewed
formula/composition, identity reconciliation and evidence boundaries, then
imported them into the existing unverified research tables. All entries remain
pending human review under [DATA_POLICY.md](../DATA_POLICY.md).

| Slice | Compounds | Possible mod roles |
| --- | --- | --- |
| [Refining](manual-refining-batch2.md) | Methyl isobutyl carbinol (MIBC), potassium ethyl xanthate, sodium sulfide, sodium cyanide, oxalic acid, sodium metasilicate | Flotation frothers/collectors, ore-processing reagents, metal precipitation, modeled rare-earth separation research, alkaline cleaning |
| [Batteries](manual-batteries-batch2.md) | Lithium sulfate, lithium carbonate, lithium nitrate, lithium tetrafluoroborate, ethylene carbonate, dimethyl carbonate | Battery precursors, electrolyte additives/salts and carbonate solvents |
| [Thermal materials](manual-thermal-batch2.md) | Aluminum oxide, boron nitride, silicon carbide, zirconium dioxide, magnesium oxide, lithium fluoride | Electrical/thermal ceramics, abrasives, separately formulated stabilized ceramics, refractory components, optical components and molten-salt ingredients |

These possible game roles are proposals, stored separately from source facts.
No engines, recipes, resource deposits, electrolyte formulations or thermal
performance values are implemented or implied by this research import.

## Identity and evidence boundaries

The three new slices are under
[`sources/manual-chemistry/`](../sources/manual-chemistry/), with `batch2` in
their filenames. Their IDs are distinct from the first 18 manual targets.
Bounded searches checked reviewed species, aliases, Wikipedia candidates and
previous manual facts. Existing compatible candidate leads are linked instead
of creating duplicate candidate entities. None of this batch's targets matched
an exact reviewed species identity; its 34 candidate links are unverified leads,
not scientific promotion. Equal formulas alone are not accepted as proof of a
common molecular identity: pyruvic acid and ethylene carbonate, for example,
must not be merged. The source-specific notes explain each reconciliation.

Anhydrous salts are distinguished from hydrates. Generic waterglass mixtures,
other xanthates and cyanide component ions are not aliases of the selected
compounds. Hexagonal-BN application facts are explicitly phase-scoped. Stabilized
zirconia, reaction-bonded silicon carbide and filled polymer products remain
separate derivatives/composites; their performance is not assigned to a pure
compound. Oxalic-acid separation facts describe an original **modeled**
solution-equilibrium study and do not assert measured capacities or universal
reagent requirements.

Primary manufacturer/institution sources were inspected directly. Facts retain
source URL/title, retrieval date, independently worded supporting text and
factual-only redistribution basis. No numerical measurements, recipes, yields,
purity specifications or product performance tables were copied. Product
identifiers and dated original studies give source context without inventing
release versions for live pages.

## Database and tooling result

The new batch contributes 18 identity records in addition to its 52 factual
assertions: **70 new research tasks/facts/source links**. Together with
[batch 1](manual-mod-chemistry.md), there are now:

- 6 immutable dated research slices/runs;
- 36 distinct compound targets;
- 100 source-backed textual facts plus 36 structured identity records;
- 136 research tasks, unverified facts and source links.

The importer now additionally verifies that any reused reviewed species ID has
matching composition and charge, and rejects compound IDs owned by another
entity kind. No reviewed identity is linked merely because its text ID exists.
Existing exact reviewed links in batch 1 remain valid; its facts were not
rewritten. Replaying a previously imported source file is still a row-level no-op.

`universe-unverified.db`, its checksum and `manifest.json` were refreshed.
The reviewed base and previous Wikipedia candidate counts are unchanged. The
Minecraft/ICM repositories and runtime catalog pins were not altered; these
research facts require a separate reviewed admission/export step to become
usable gameplay chemistry.

## Checks performed

The import checked all six source files for formulas, elemental symbols/counts,
integer charge, fact keys, source metadata, HTTPS citations, exact compatible
candidate links and cross-slice identity consistency. All 36 manual target IDs
are distinct. SQLite integrity returned `ok`; foreign-key violations were zero;
both recorded database checksums matched their artifacts. The new importer
identity guards passed pinned Ruff 0.12.12 source lint/format checks.

No compilation, project test suites or mod runtime tests ran on this server.
Local importer regression checks and independent human source/identity review
remain required, as documented in the first-batch workflow. The unverified label
must be preserved until that scientific review is completed.
