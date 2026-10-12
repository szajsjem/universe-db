# Local Wikipedia source review

The OpenRouter reviewer and its restart supervisor were stopped at the user's
request. The original reviewer database retains 677 successful candidate
decisions and all error/history records. Administrative stop events are stored
in `wikipedia_review_stop_event`; interrupted runs are closed with the existing
schema's `failed` status and a separate user-stop reason. No completed review
was fabricated. `.build/wikipedia-codex-review-base.db` is a frozen snapshot.

The replacement work uses local scripts and assistant subagents. It makes no
OpenRouter calls. Primary-source follow-up uses public journal/institutional
pages when a Wikipedia citation needs confirmation.

## Coverage

| Pass | Coverage | Meaning |
|---|---:|---|
| Filtered candidate queue | 5,270 candidates and all children/history | Exhaustive computational triage; selected source inspections |
| Pinned chemistry archive | 1,239 pages | Exhaustive parsing/representation inventory; selected recovered leads |
| Full English dump index | 25,859,744 entries | Streaming title discovery for selected science topics |
| Additional science matches | 7,053 after collision filtering | Candidate article titles, not validated identities or observations |
| Priority full-dump articles | 14 local bodies read | Source inspections; redirects remain distinct |

The archive has 421 unparsed pages, 96 error-only pages, one pending page,
277 no-data pages and 444 parsed pages. Six source pages remain represented
only through cleanup mentions. A failed/no-data parse does not prove that a
species is absent from the database; the recovered-lead report checks
cross-page name/formula coverage and preserves identity ambiguity.

Filtered findings include methods and bibliographic titles extracted as
substances, element/particle/compound kind errors, neutral salts classified
as ions, and unsupported isotope/spectroscopic assignments. Quotation
mismatches and name collisions are investigation signals, not automatic
rejections or duplicate merges. See [filtered review](wikipedia-filtered-review.md).

The remaining archive contains missed molecule/material leads and references
to newer isotope discoveries. See [archive coverage](wikipedia-archive-coverage.md)
and [primary follow-up](wikipedia-source-followup.md). Newly discovered alloy,
ceramic, structure and nuclear-data pages are documented in
[full-dump discovery](wikipedia-full-discovery.md).

## Reproduce the inventories

```powershell
python -m scripts.audit_wikipedia_filtered
python scripts/audit_wikipedia_archive_coverage.py
python scripts/discover_wikipedia_science_sources.py --read-priority
```

The full scan streams the compressed multistream title index. With a matching
saved inventory, `--reuse-inventory --read-priority` reuses offsets and avoids
repeating the index scan. Source inspections and primary confirmations are
separate authored report files, rather than automatically inferred from title
patterns. Inventory scripts can regenerate computational results; they do not
recreate scientific judgments from keywords.

## Collected artifact

```powershell
python scripts/collect_wikipedia_source_audits.py
```

This writes `.build/wikipedia-codex-source-audit.db` and its checksum and JSON
summary. It copies the stopped review snapshot and adds
`unverified_wikipedia_source_audit` and `unverified_wikipedia_source_audit_result`.
Each report has a file digest, scope and pending-review status. Each result
preserves its original JSON, source identity/URL, and review method:
deterministic triage, title discovery, local page read, source inspection or
primary-source check. Existing candidates and previous review decisions remain
intact; proposals form a recoverable follow-up queue.

The existing release exporter can snapshot this artifact explicitly:

```powershell
python scripts/export_release.py --wikipedia-db .build/wikipedia-codex-source-audit.db
```

Wikipedia excerpts retain their revision attribution and CC BY-SA 4.0 license;
their text is distinct from MIT project code. Neither a title match nor a
Wikipedia passage constitutes admission of a primary scientific measurement.
Reference disagreements and unresolved source details remain explicit in the
follow-up queue.
