# Atomic electronic evidence

`atomic.db` adds isolated-atom/ion electronic ground states and single-electron
ionization energies from the [NIST Atomic Spectra Database](https://physics.nist.gov/asd)
(version 5.12, 2024; DOI [10.18434/T4W30F](https://doi.org/10.18434/T4W30F)).
The response was retrieved on 2026-10-13. Source metadata contains the exact query,
retrieval time, response SHA-256, citation and redistribution determination.
Only factual values, scientific labels, reference identifiers and the short NIST
output legend are retained; upstream journal papers are not redistributed.

## Coverage and meaning

The pinned H-Ds query supplies 6,019 electronic states and 5,847 ionization
energies. It has 108 neutral-state energies, including every constituent in the
current alloy corpus and H, He, C, N, O and S. Some intermediate charge stages
are absent, and the query does not cover elements after Ds. Ten missing neutral
rows through Z=118 are explicit query-coverage gaps, rather than claims that the
energy is physically unknown. The 172 present states whose energy is blank have
source-reported unknown-energy gaps. Missing values never become zero.

Rows retain atomic number, element, integer positive ion charge, electron count,
configuration, ground-shell and ground-level labels. Isotope mass number is NULL:
these entries must not be assigned to a particular isotope. They describe
isolated electronic states, not solid-state work functions, chemical bonding
energies, ambient-temperature material measurements or molecular ionization.
Configurations and levels remain source-native labels; the import does not
convert them into experimentally established orbital populations.

The [NIST legend](https://physics.nist.gov/PhysRefData/ASD/Html/iehelp.html)
distinguishes 311 unbracketed evaluated-experimental entries (stored as `curated`
source evaluations), 919 square-bracketed semiempirical entries and 4,617
parenthesized theoretical entries (both stored as `modeled`). The original
prefix/suffix and bibliography reference IDs remain in each observation's
`input_json`. All records are `pending_human_review`; no reviewed core rows are
promoted.

## Numeric representation and reproducibility

The authoritative output is the displayed eV value and displayed uncertainty,
represented as arbitrary-precision integer ratios in TEXT columns. Consumers
must use integer/Fraction parsing, not SQLite REAL. Unknown uncertainties remain
NULL. NIST stores its native energies in reciprocal centimetres; this import
preserves the requested eV conversion and its displayed uncertainty, including
upstream rounding. It does not claim native-wavenumber precision or perform a
new conversion.

```powershell
python scripts/build_atomic_evidence.py
python scripts/build_atomic_evidence.py --output .build/atomic.db
python -m unittest tests.test_atomic_evidence
```

`build(output, metadata_path)` performs an offline checksum-verified rebuild.
The source parser recognizes ASD's CSV text wrappers and never evaluates
spreadsheet formulas. Unexpected units, qualifiers, identities, duplicates,
negative uncertainties and nonpositive energies fail the build. Output
replacement is atomic and happens only after integrity and foreign-key checks.
Two builds from the pinned input produce identical bytes.

Updating the source is an explicit source-maintenance operation: request the
URL in `sources/atomic/nist-asd-metadata.json`, confirm the current ASD version
against its HTML citation, replace the response, update its SHA-256 and retrieval
metadata, then rerun the tests. Do not silently overwrite a pinned source during
a release build. The old response/version should remain recoverable in Git.

Tables are `unverified_atomic_source`, `unverified_atomic_state`,
`unverified_atomic_observation`, `unverified_atomic_gap` and
`unverified_atomic_metadata`. These fit the research export namespace; no new
core property or atomic-state admission is implied.
