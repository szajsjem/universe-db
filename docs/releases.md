# Export a Universe database release

## Publish through GitHub Actions

The `release` workflow runs on tag pushes or manual dispatch. A manual run
requires an existing tag and checks out that tag's contents, even when the
workflow is launched from `main`. The historical `recent` tag predates the
companion and alloy databases; rerunning it publishes its original assets.
Use a new tag pointing to the desired current commit to publish newer data.

Tags that include `scripts/export_release.py` publish the combined release
bundle, individual databases, manifest, and checksums described below.
Older tags publish only their available database assets. A missing checksum
for a present companion database still fails validation.

## Export locally

```sh
python scripts/export_release.py
```

The command writes `dist/releases/<UTC timestamp>/` and a ZIP beside it.
It rebuilds the reviewed scientific core from current migrations and seeds,
rebuilds the alloy and elemental references from authored JSON, imports the
pinned isotope evaluations, and takes a consistent SQLite
backup of the current Wikipedia review database. The background reviewer can
continue working during export; the release contains one committed snapshot.

The default research input is the repository's `universe-unverified.db`, so
checked-in manual research is included and stale local review snapshots do not
override it. If absent, the exporter falls back to
`.build/wikipedia-codex-source-audit.db`, then `.build/wikipedia-glm-full-reviewed.db`.
Use `--wikipedia-db` to select a newer local snapshot explicitly. The legacy GLM filename may contain
reviews from subsequent models; their actual model names remain in the audit
tables. Override the input or choose a release label as follows:

```sh
python scripts/export_release.py --version 2026.10.11 --wikipedia-db .build/wikipedia-glm-full-reviewed.db
python scripts/export_release.py --version 2026.10.11-local --no-zip
```

Use `--output-dir PATH` to change the destination. Existing release labels are
never overwritten. Source databases and the repository's checked-in release
artifacts are preserved.

Each release contains:

| File | Contents |
|---|---|
| `universe.db` | Combined database: reviewed core, current Wikipedia/research tables, and alloy research tables |
| `universe-reviewed.db` | Reviewed scientific core only |
| `universe-wikipedia.db` | Snapshot of selected Wikipedia candidates and source audits, including their reference core |
| `universe-unverified.db` | All pending Wikipedia/alloy/element/isotope research with the reviewed reference core |
| `alloys.db` | Rebuilt alloy reference |
| `elements.db` | Rebuilt elemental physical-property evidence, pending review |
| `isotopes.db` | Full evaluated isotope evidence, pending review; source estimates flagged |
| `crystals.db` | Sourced crystal phases, lattice parameters and sites, pending review |
| `atomic.db` | Evaluated atomic/ionic electronic states and ionization energies, pending review |
| `spectra.db` | Sourced spectral-line lists, pending review; medium and native intensities preserved |
| `molecules.db` | Molecular graphs and source identity crosswalks, pending review |
| `manifest.json` | Version, export time, base identity, file sizes, row counts, review progress, and SHA-256 digests |
| `*.sha256` | Individual database checksums |
| `README.txt` | Artifact and review-status guide |
| `element-review-plan.json` | Source-pinned canonical admission proposals and mapping blockers |
| `crystal-cell-audit.json` | Source-explicit symmetry expansion and cell-content validation |
| `nuclear-normalized.json` | Conservative typed nuclear evidence and unsupported-syntax gaps |

The ZIP has its own `.zip.sha256` checksum. The full Wikipedia dump and API
credentials are not included.

Review reports are included in the ZIP and fingerprinted in the manifest.
They remain unverified review aids; generating a report does not approve
scientific observations or replace missing source context.

In the combined `universe.db`, reviewed core tables retain their existing
names. Wikipedia candidates remain in `unverified_*` staging tables, with
`wikipedia_*` provenance and audit tables. Alloy tables and views use the
`unverified_alloy_` prefix to avoid collisions with core tables.

Elemental research uses the `unverified_element_` prefix and retains complete
source-record JSON, composition basis, and supplied uncertainty metadata.
Isotope research uses `unverified_isotope_`, preserving evaluation vintages,
source-systematic estimates, nuclear states, and original uncertainty/qualifier
text. Fitted isotope model JSON is generated separately; see
[isotope approximation](isotope-approximation.md).
Crystallographic research uses `unverified_crystal_`; source cell settings,
isotope labels, incomplete metrics and asymmetric-unit sites remain explicit.
See [crystal evidence](crystal-evidence.md).

Additional references use `unverified_atomic_`, `unverified_spectral_` and
`unverified_molecular_` namespaces. The exporter rebuilds their pinned source
snapshots offline and includes them in both combined and unverified databases,
as well as standalone reference files. Ionization-energy source qualifiers,
line air/vacuum context and molecular isotope/stereo labels remain attached.

For example:

```sql
SELECT family, count(*) FROM unverified_alloy_alloy GROUP BY family;

SELECT a.name, c.element, c.min_wt_pct, c.max_wt_pct,
       c.nominal_wt_pct, s.url
FROM unverified_alloy_alloy a
JOIN unverified_alloy_composition_wt_percent c USING (alloy_id)
JOIN unverified_alloy_source s USING (source_id);

SELECT model, status, completed_count, error_count
FROM wikipedia_candidate_agent_run ORDER BY started_at DESC;
```

Model decisions and source-linked alloy research remain unverified until human
review. The exporter does not promote them into reviewed scientific identities
or observations. `database_metadata` records this mixed-content status.

Export fails if the research database's recorded base digest differs from the
rebuilt reviewed core, scientific validation fails, or SQLite integrity/foreign
key checks fail. Reconcile a mismatched research base before exporting it;
do not bypass the digest check.

Different SQLite versions may serialize identical reviewed data differently.
The exporter rebuilds and validates the core, then checks every schema object,
metadata row and data row against the checksummed canonical `universe.db`.
Only exact logical equivalence permits retaining canonical bytes for the
release/reference digest. Changed scientific data, schemas or metadata abort
export; research-base matching remains mandatory.
