# Elemental crystallography research

`sources/crystals/metals.json` contains eleven experimental structures from
revision-pinned Crystallography Open Database (COD) CIFs, with original paper
attribution. All records remain `pending_human_review`. The selected COD facts
are CC0; the original articles are cited, not redistributed.

| Element / phase | COD record | a (angstrom) | c (angstrom) | Temperature (K) |
| --- | --- | --- | --- | --- |
| Ag, fcc | 9013045 | 4.086 | 4.086 | 293 |
| Al, fcc | 9012002 | 4.04961 | 4.04961 | 298.15 |
| Au, fcc | 9013035 | 4.072 | 4.072 | 293 |
| C, diamond | 9011997 | 3.566986 | 3.566986 | 298.15 |
| Cu, fcc | 9013014 | 3.613 | 3.613 | 293 |
| Fe, alpha bcc | 9006587 | 2.8654 | 2.8654 | 298 |
| Fe, gamma fcc | 9012706 | 3.639 | 3.639 | 1189 |
| Mg, hcp | 9012001 | 3.2093 | 5.2103 | 298.15 |
| Ni, fcc | 9013024 | 3.524 | 3.524 | 293 |
| Si, diamond cubic | 9011998 | 5.430941 | 5.430941 | 298.15 |
| Ti, alpha hcp mineral specimen | 9017383 | 2.950 | 4.686 | Unreported |

Cu, Ag, Au and Ni use Suh, Ohta and Waseda (1988),
[DOI 10.1007/BF01174717](https://doi.org/10.1007/BF01174717).
Al and Mg use Straumanis (1949),
[DOI 10.1063/1.1698520](https://doi.org/10.1063/1.1698520).
Alpha-Fe uses Zhang and Guyot (1999),
[DOI 10.1007/s002690050178](https://doi.org/10.1007/s002690050178).
Gamma-Fe uses Basinski, Hume-Rothery and Sutton (1955),
[DOI 10.1098/rspa.1955.0102](https://doi.org/10.1098/rspa.1955.0102).
Full citations for diamond, silicon and the natural Ti specimen are retained
in their CIFs and source records.

Run `python sources/crystals/metals-transform.py` to reproduce the JSON from
the cached selected COD records and local CIFs. The transformation checks the
pinned revision and records each CIF SHA-256. It preserves source-native
decimal strings, including trailing zeros. No network access is needed.

Sites are asymmetric-unit coordinates. CIF symmetry operators are retained
in the raw files. The importer does not expand these into full-cell sites or
assign unreported occupancy, multiplicity or Wyckoff letters. Rounded hcp
coordinates `0.33333` and `0.66667` are preserved; a later symmetry expansion
must handle rounded special positions explicitly. Cell formula units are
the reported CIF values and do not imply that a row contains the full cell.

Most selected CIFs omit a method tag. Method stays null unless the publication
title explicitly identifies X-ray diffraction. Temperature and pressure are
not assumed to be room temperature or atmospheric pressure when absent. The
alpha-Fe paper's reported pressure of 0 GPa is stored as 0 Pa, with the native
source retained; it is not reinterpreted as a vacuum experiment.

Historical Ti record COD 9011600 is excluded: its CIF reports Z=4 and calculated
diffraction density 8.820 for a one-site hcp structure. This conflicts with
the expected hcp cell content. The raw pinned CIF remains available as a
flagged research gap, with no silent correction. The imported replacement is
a natural alpha-Ti mineral specimen, whose provenance and missing measurement
temperature are explicit; it is not labeled a certified pure-metal standard.
