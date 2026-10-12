# Full Wikipedia science discovery

`scripts/discover_wikipedia_science_sources.py` discovers science-related titles
outside the current source index and chemistry archive in the checksum-verified
September 1, 2026 English Wikipedia multistream dump. It runs offline and makes
no OpenRouter or other model API calls. It does not write to any database.

The completed inventory in `.build/wiki-subagents/full-rest.json` scanned
25,859,744 index entries, including 19,093,031 colon-free titles. Its first pass
matched 7,604 entries, of which 7,561 were absent from both existing source sets.
A separate conservative collision pass removed 508 obvious unrelated titles,
leaving 7,096 candidates, including 7,053 new candidates. Original counts remain
unchanged; `postfilter_*` counters describe the retained candidate list. Topic
counts can overlap and remain counts from the first pass.

These are **computational title candidates**, not verified articles or numerical
observations. The exclusion patterns can reject relevant titles, and the retained
list can still contain unrelated titles. This is not exhaustive coverage of the
science in English Wikipedia.

## Reusing the inventory

```powershell
python scripts/discover_wikipedia_science_sources.py --reuse-inventory
```

Reuse validates the stored index SHA-256, title-filter fingerprint and source-page
sets against the download manifest and current inputs. The manifest was produced
by the previously completed download/checksum operation; reuse does not recompute
the large dump checksums. The collision pass is idempotent and fingerprints its
pattern separately. A changed collision pattern rejects reuse. No large index
rescan is needed for the current unchanged filters.

Adding `--read-priority` reads bounded bodies for matching priority pages using
existing multistream offsets and the standard identity-validating local reader.
It overwrites the priority-read output, so existing outputs should be preserved
when extending the review set. Each body is capped at 64 reader chunks (at most
512 KB); `read_chars` versus `document_chars` exposes incomplete reads.

## Inspected bodies and findings

The persisted `full-rest.reads.json` contains 14 priority bodies. All were inspected
in their lead, relevant scientific sections and reference contexts. Eleven contain
substantive articles and three are redirects. `full-rest.findings.json` records
14 findings with page identity, fixed revision URL, a short exact body excerpt,
reference leads, relevance and a proposed next action. This is source inspection,
not verification of every sentence, external citation or data table.

Useful leads include manufacturer sheets for Monel/Inconel, temper-specific
6061/7075 sources, Ioffe SiC polytype tables, Si3N4 polymorph/anisotropy references,
Ti-6Al-4V alpha/beta phases, thermal diffusivity derivation, and CALPHAD phase
equilibrium methodology. The iron isotope table names AME/NUBASE evaluations and
retains estimate/uncertainty markers. External documents remain unfetched and
unverified; template-only references need separate resolution.

Wurtzite crystal structure, Heusler alloy and Evaluated Nuclear Data File contain
only redirects. Their targets need local body reads before substantive findings
can be made. No lattice constants, physical properties or isotope statistics
were imported or promoted during discovery. Wikipedia excerpts retain
CC-BY-SA-4.0 attribution through the revision URLs, separately from MIT code.
