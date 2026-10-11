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

The default research input is `.build/wikipedia-glm-full-reviewed.db` if it
exists, otherwise `universe-unverified.db`. The legacy GLM filename may contain
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
| `universe-unverified.db` | Snapshot of the selected research database, including its review audit |
| `alloys.db` | Rebuilt alloy reference |
| `elements.db` | Rebuilt elemental physical-property evidence, pending review |
| `isotopes.db` | Full evaluated isotope evidence, pending review; source estimates flagged |
| `manifest.json` | Version, export time, base identity, file sizes, row counts, review progress, and SHA-256 digests |
| `*.sha256` | Individual database checksums |
| `README.txt` | Artifact and review-status guide |

The ZIP has its own `.zip.sha256` checksum. The full Wikipedia dump and API
credentials are not included.

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
