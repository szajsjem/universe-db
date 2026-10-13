# Atomic spectral evidence

`spectra.db` contains **1,871 atomic strong-line records from 16 NIST
Handbook elemental tables**: H, He, Li, C, N, O, Na, Mg, Al, Si, Fe, Ni,
Cu, Ag, Au, and Ti. These are unverified research records pending source
review, not additions to the reviewed core.

The source is [NIST Standard Reference Database 108, Handbook of Basic Atomic
Spectroscopic Data](https://www.nist.gov/pml/handbook-basic-atomic-spectroscopic-data),
J. E. Sansonetti and W. C. Martin, DOI
[10.18434/T4FW23](https://doi.org/10.18434/T4FW23). NIST identifies November
2013 as the last data-content update; retrieval timestamps distinguish our
current response snapshots from that upstream version. Each elemental source
records its official table URL and complete HTTP-response SHA-256. Every line
preserves the original reference code and a link to the elemental reference
table entry. Individual referenced papers have not been independently reviewed.

Only factual numerical entries, elemental identities, reference identifiers,
and marker codes are redistributed in
`sources/spectra/nist-handbook-strong-lines.json`. Publisher prose, page layouts,
and original complete HTML responses are excluded. The adjacent checksum pins
the factual snapshot. The response hashes permit comparison against a separately
retrieved original response; a factual snapshot alone cannot reconstruct the
original HTTP response.

## Semantics

Reported wavelengths retain their original decimal text in angstroms; stored
nanometers are the exact rational angstrom value divided by ten. **Air and
vacuum wavelengths remain separate**, without refractive-index conversion.
Spectrum stage I means neutral and II means singly ionized; their corresponding
ion charges are zero and one. No isotope assignment is inferred.

Intensities retain their source-native arbitrary relative values and suffixes.
They are **not transition probabilities, radioactive branching fractions,
calibrated absolute intensities, or values suitable for cross-species or
cross-spectrum comparison**. Persistent-line and other source marker strings
remain verbatim, including comma-separated codes. A doublet or repeated source
wavelength stays as separate rows; records are never merged by wavelength.

Missing uncertainty, plasma/excitation conditions, isotope identity, upper/lower
level assignments and transition probabilities are explicit coverage gaps.
This corpus is a selected line list, not sampled spectral curves. It does not
fill molecular IR/Raman/NMR/mass spectra, nuclear gamma spectra, band profiles,
oscillator strengths or spectral cross sections. Provenance is `curated`, since
these are evaluated Handbook entries rather than a direct experimental paper.

## Build and refresh

```powershell
python scripts/build_spectral_evidence.py
python scripts/build_spectral_evidence.py --output .build/spectra.db
# Explicit network retrieval and replacement of the pinned factual snapshot:
python scripts/build_spectral_evidence.py --refresh
```

`build(output)` is available for release integration. Default builds read only
the checksum-pinned local snapshot, enforce source metadata and identity checks,
validate SQLite integrity and foreign keys, and atomically replace the output.
Identical inputs produce identical database bytes. Refresh uses the accessible
`<element-name>table2_a.htm` pages, such as `hydrogentable2_a.htm`, parses
the single preformatted table and rejects
ambiguous numeric rows or missing reference links. It completes retrieval of
all 16 sources before writing the new factual snapshot.

Tables are `unverified_spectral_source`, `unverified_spectral_line`,
`unverified_spectral_gap`, and `unverified_spectral_metadata`. All line review
statuses remain `pending_human_review`. Tests cover exact conversion, separate
air/vacuum and ion-stage handling, source markers, malformed-row rejection,
snapshot tampering, byte determinism and atomic build failure.
