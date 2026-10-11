# Isotope evidence and approximation

The reviewed core contains 288 isotope masses and representative abundances.
`isotopes.db` extends research coverage with the full NIST archive and the
official AME2020/NUBASE2020 evaluations. New imported evidence remains pending
human review; evaluated values and upstream systematic estimates are distinct.
The NIST archive uses AME2012 masses, not the AME2020 evaluation. Both vintages
are preserved, and the fitter selects one evaluation rather than mixing them.

The reference contains 39,114 observations across 5,843 source state
assignments. NUBASE supplies 5,230 half-life entries, 5,546 spin/parity entries,
5,671 decay entries, 5,827 mass excesses and 2,269 excitation energies. Atomic
masses from different evaluation vintages coexist as separate observations.
Sixteen withdrawn assignments lack admitted mass evidence; 87 ground states
lack a reported half-life or stable designation and 185 lack spin/parity. These
remaining source gaps are explicit rather than filled by the mass model.

## Rebuild and fit

```powershell
python scripts/build_isotope_evidence.py
python scripts/fit_isotope_properties.py --output .build/isotope-core-model.json
python scripts/fit_isotope_properties.py --research-database isotopes.db --allow-unverified --output .build/isotope-ame-model.json
```

Builds and fitting use versioned local source archives, without network access.
The builder verifies source digests, retains citations and raw source records,
and emits `.build/isotope-evidence-audit.json`. Published uncertainties and
qualifiers are preserved. Stable nuclei have a textual stability observation;
their half-life is not stored as zero. Unreported abundance is not invented.
NUBASE state indices distinguish ground states, isomers, other levels and
historical assignments; they do not all represent observed long-lived isomers.
Withdrawn assignments remain explicit gaps and receive no observations.

Exact values and uncertainties use decimal-encoded integer ratios. Numerator
and denominator columns are TEXT because finite half-lives and tiny time units
can exceed SQLite's 64-bit integer range. Parse with Python `int`/`Fraction`;
do not cast to SQLite INTEGER or REAL for authoritative calculations.

## Algorithm

The approximation has two layers. First, a five-term liquid-drop model is
fitted by column-scaled, reorthogonalized QR least squares:

```text
B_proxy = av*A - as*A^(2/3) - ac*Z*(Z-1)/A^(1/3)
          - aa*(N-Z)^2/A + ap*pairing_sign/sqrt(A)

M_atom = Z*m(H-1) + N*m(neutron) - B_proxy/(u*c^2)
```

The pairing sign is +1 for even/even, -1 for odd/odd, and zero otherwise.
Atomic H-1 and neutron reference masses come from the selected evaluation when
available, with explicit archived NIST/CODATA fallbacks. CODATA2022 provides
the energy conversion constant. Training is unweighted: uncertainty-based
weights would overemphasize the most precisely measured masses without
accounting for the much larger model discrepancy.

Second, residuals from nearby known isotopes correct the smooth baseline.
The correction uses at most 12 neighbors within distance five in (Z,N),
weighted by `1/(1+distance_squared)^2`. It requires at least four neighbors;
otherwise the baseline is used. The queried coordinate is excluded from its
own correction. This approximates local shell/deformation trends without
claiming a microscopic nuclear-structure calculation. It is based on the
[semi-empirical model](https://doi.org/10.1007/s41365-019-0718-8) plus an authored,
explicitly documented interpolation policy.

Only nonestimated ground-state masses are fitted. Nuclei below A=16 are
excluded from fitting because the liquid-drop approximation is unsuitable;
available source masses for those nuclei can still be returned. Source values
marked `#`, excited states, modeled responses, and duplicate mass evaluations
are excluded or rejected. Research evidence requires `allow_unverified=True`.

## Validation

Validation happens before refitting on all eligible masses. A deterministic
coordinate hash holds out approximately 20% of isotopes. A second test holds
out both ends of isotope chains with at least five records. Each test fits
new coefficients and builds residual references from its training fold only.
Source/test records never contribute to that fold's local correction.

| Data | Final fit records | Coordinate holdout RMSE (u) | Chain-edge holdout RMSE (u) |
|---|---:|---:|---:|
| Reviewed core | 275 | 0.00122 | 0.00134 |
| Nonestimated AME2020, A>=16 | 2,484 | 0.000714 | 0.00164 |

AME validation uses 471 coordinate-holdout and 196 chain-edge records.
The baseline AME coordinate-holdout RMSE is 0.00359 u; the local correction
reduces it to 0.000714 u. These are empirical errors on known masses, not
calibrated confidence intervals for unknown nuclei or far extrapolation.
Training records, reference constants, validation split IDs, coefficients,
local residuals, and SHA-256 digests are stored in the model JSON. The model
itself remains unreviewed even when its training evidence is reviewed.

## Predict

```python
import json
from scripts.fit_isotope_properties import predict_isotope

model = json.load(open(".build/isotope-ame-model.json"))["model"]
result = predict_isotope(model, z=26, a=80, allow_extrapolation=True)
```

Or fit and predict with the CLI:

```powershell
python scripts/fit_isotope_properties.py --research-database isotopes.db --allow-unverified --predict 26 80 --allow-extrapolation
```

Known nonestimated masses return their source record before a model prediction.
Unknown ground states return modeled neutral atomic mass (u and kg), mass
excess, binding-energy proxy and approximate separation energies. The proxy
neglects total electronic binding corrections and must not be selected as an
exact nuclear binding measurement. Its units and method are explicit.

The model reports neighbor IDs and whether a local correction was available.
Predictions outside the observed Z/A/N:Z coordinate limits need explicit
extrapolation permission and have no empirical error estimate. Coordinates
beyond Z=118/A=400, unknown light nuclei, neutron clusters, and excited-state
predictions are unsupported. The coordinate envelope is not a convex-hull or
drip-line test. Even a positive binding estimate does not establish existence
or stability. Half-life, branching ratios, spin/parity, nuclear radius and
natural abundance are not inferred from this mass fit.

Research releases include `isotopes.db` and its checksum, plus the
`unverified_isotope_*` tables in the combined `universe.db`. Model JSON is
generated separately with the commands above.
