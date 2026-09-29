# Wikipedia candidate workflow

This guide covers the repository's opt-in workflow for discovering and
reviewing scientific candidates from Wikipedia. Wikipedia text and model
output are secondary-source leads: every result stays in `unverified_*` tables
and is excluded from `universe.db` until it is independently reviewed under
the [data policy](../DATA_POLICY.md).

## Prerequisites and source snapshots

Python 3.11+ is sufficient for the revision-pinned ZIP. Reading the optional
Kiwix ZIM requires the official `libzim` binding:

```sh
python3 -m pip install -r requirements-wikipedia.txt
```

The repository vendors these sources:

- `sources/wikipedia-chemistry-category-snapshot-2026-07-29.zip`: 1,239
  wikitext pages with revision IDs, permanent URLs, discovery categories, and
  per-page hashes.
- `sources/wikipedia_en_chemistry_mini_2026-07.zim`: the official Kiwix
  chemistry mini release. It contains 9,255 canonical English Wikipedia HTML
  pages after redirects and non-page assets are excluded.

Verify the checked-in snapshots before parsing:

```sh
python3 scripts/check_wikipedia_snapshot.py
sha256sum --check sources/wikipedia_en_chemistry_mini_2026-07.zim.sha256
```

To intentionally capture a new bounded, revision-pinned ZIP, run:

```sh
python3 scripts/download_wikipedia_chemistry.py
```

This is a network operation. It defaults to seven scientific category roots,
depth 1, at most 180 pages per root and 1,260 pages overall. The output name is
dated; an existing destination is protected unless `--force` is supplied.
Commit a new dated source and dataset identity rather than replacing a released
snapshot. Use `--help` for category, delay, timeout, and retry controls.

## Plan and run extraction

Planning is cost-free and does not contact a model or write an overlay:

```sh
make wikipedia-plan

# Equivalent explicit plan, limited to five pages.
python3 scripts/parse_wikipedia_archive.py \
  sources/wikipedia-chemistry-category-snapshot-2026-07-29.zip \
  --max-pages 5
```

The parser defaults to reviewed `universe.db` as its identity base and writes
to `.build/wikipedia-unverified.db`. It uses LM Studio at
`http://localhost:12355/v1`, model `qwen/qwen3.5-9b`, streaming structured
output, a 180-second timeout, two call retries, two full-page retries, and 30
request starts per minute. `--parallel-requests 0` discovers LM Studio's loaded
model slots and falls back to one worker; SQLite writes remain serialized.

Start with a small local trial:

```sh
python3 scripts/parse_wikipedia_archive.py \
  sources/wikipedia-chemistry-category-snapshot-2026-07-29.zip \
  --max-pages 5 \
  --execute
```

No API key is needed for LM Studio's default authentication. If enabled, put
the token in `LM_STUDIO_API_KEY`. For another server, set `--base-url`,
`--model`, and a positive `--parallel-requests`; a non-loopback URL also
requires `--accept-cost`. `--no-stream` supports runtimes that cannot stream
grammar-constrained JSON.

For a complete two-pass extraction:

```sh
python3 scripts/parse_wikipedia_archive.py \
  sources/wikipedia-chemistry-category-snapshot-2026-07-29.zip \
  --verify \
  --requests-per-minute 0 \
  --timeout 900 \
  --execute
```

`--verify` sends the source and initial extraction through a second independent
call that can remove unsupported claims and correct transcription, units,
conditions, types, and evidence. Successful pages commit individually.
Rerunning skips pages already recorded as `parsed`, `parsed_partial`, or
`no_data` for the same archive digest, while error pages are retried. Use
`--refresh` only when successful pages should be processed again.

Selection always applies `--start-page` as the lowest original archive index,
then reverses when `--reverse` is present, then applies `--max-pages`. Thus a
backward five-page trial is:

```sh
python3 scripts/parse_wikipedia_archive.py \
  sources/wikipedia-chemistry-category-snapshot-2026-07-29.zip \
  --reverse --max-pages 5 --execute
```

## Report missing pages

Create a CSV of pages that have never reached a successful status for the
archive's exact SHA-256:

```sh
python3 scripts/list_missing_wikipedia_pages.py \
  sources/wikipedia-chemistry-category-snapshot-2026-07-29.zip \
  .build/wikipedia-unverified.db \
  .build/wikipedia-missing-pages.csv
```

The report includes original sequence index, current status, title, permanent
source URL, archive entry key, attempt count, latest error, and latest attempt
time. `untouched` means no attempt exists. Historical `error`, pending, and
interrupted attempts remain listed unless any attempt for that page succeeded.
The CSV is a diagnostic artifact; feed the original archive back to the parser
to resume rather than treating the CSV as parser input.

## Consolidate candidates deterministically

Parsing deliberately creates one candidate per page mention. First inspect the
cleanup plan against the live overlay:

```sh
python3 scripts/clean_wikipedia_candidates.py \
  .build/wikipedia-unverified.db
```

Then clean a consistent copied snapshot, safe even while parsing continues:

```sh
python3 scripts/clean_wikipedia_candidates.py \
  .build/wikipedia-unverified.db \
  --output .build/wikipedia-cleaned.db \
  --execute
```

The input is never edited. Cleanup preserves original wording, page identity,
and evidence in `wikipedia_candidate_mention`; applies conservative identity,
charge, and nuclide checks; and never merges molecules on formula alone.
Derived phase facts use 293.15 K and 101325 Pa by default, adjustable with
`--normal-temperature-k` and `--normal-pressure-pa`.

## Run bounded agent review

Plan the atom and molecule queue without loading a model or writing a database:

```sh
python3 scripts/review_wikipedia_candidates.py \
  .build/wikipedia-cleaned.db
```

Run a bounded trial (the default server is `http://127.0.0.1:8080/v1`):

```sh
python3 scripts/review_wikipedia_candidates.py \
  .build/wikipedia-cleaned.db \
  --max-candidates 5 \
  --execute
```

The default output is `.build/wikipedia-agent-reviewed.db`, copied from the
input on first execution. The agent has bounded read-only SQL and local archive
search tools plus one transactional staging write. It must inspect the database
and at least one attached source page. It can keep, rewrite, mark a duplicate,
or reject, but cannot write reviewed scientific tables. A remote endpoint
requires `--accept-cost`; in-place mutation requires both `--in-place` and
`--execute`.

Review is resumable: successful `keep`, `rewrite`, `duplicate`, and `reject`
records are skipped, while `error` records are retried. Use
`--start-after CANDIDATE_ID`, `--max-candidates`, and `--kinds atom,molecule`
to partition work. Decisions, before/after JSON, source keys, and tool traces
are audit records—not human review or scientific promotion.

## Artifacts and publication boundary

- `.build/wikipedia-unverified.db`: raw parse overlay.
- `.build/wikipedia-missing-pages.csv`: optional progress report.
- `.build/wikipedia-cleaned.db`: deterministic consolidated copy.
- `.build/wikipedia-agent-reviewed.db`: agent-reviewed staging copy.
- `universe-unverified.db`: published companion containing unreviewed
  candidates and provenance.
- `universe.db`: reviewed release; this workflow never changes it
  automatically.

Before publishing a companion snapshot, run `make check` and verify the release
checksums. Publication makes the candidates reproducible and auditable; it does
not promote them. Promotion requires independent source review and the normal
contribution, provenance, and validation process.
