# Neutral atomic isotope statistics fit

`scripts/fit_atomic_isotope_stats.py` learns a local empirical approximation from
NUBASE2020 ground-state records in `isotopes.db`. Its composition is integer
proton, neutron and electron counts. Only neutral atoms (electrons = protons) are
supported: this corpus does not identify an electron-count dependence. Isomers,
ions, isotope existence and nuclear stability predictions are unsupported.

For mass and decay statistics together, use
`fit_atomic_properties(database, allow_unverified=True)` and
`atomic_properties(profile, protons, neutrons, electrons, approximate_missing=True)`
from `scripts/atomic_isotope_properties.py`. This combines the existing AME
mass fit with the NUBASE lifetime/decay model, preserves each source and model
status, and returns validation context with the prediction. Electron count is
accepted explicitly but must equal proton count; no independent electron
coefficient can be fitted from neutral-only training.

```powershell
python scripts/atomic_isotope_properties.py train --database isotopes.db --allow-unverified-evidence --output .build/atomic-property-profile.json
python scripts/atomic_isotope_properties.py predict --model .build/atomic-property-profile.json --protons 26 --neutrons 54 --electrons 26
```

```powershell
python scripts/fit_atomic_isotope_stats.py train --database isotopes.db --allow-unverified-evidence --output .build/atomic-isotope-stats-model.json
python scripts/fit_atomic_isotope_stats.py predict --model .build/atomic-isotope-stats-model.json --protons 26 --neutrons 34 --electrons 26
```

Training requires explicit acceptance of unverified evidence; fitting never
promotes data. Model outputs remain `modeled`, `unverified`. A known isotope
returns its curated source reference with source locator and native uncertainty,
bounds or stability. Stable nuclei have a null lifetime, never a zero lifetime.
Missing complete branch vectors remain null.

For unknown compositions, a bounded local inverse squared distance kernel in
(Z,N) fits log10(seconds) from nonestimated positive point lifetimes. Stable
assignments, lifetime bounds and estimated values are excluded from training.
Defaults require at least four neighbors within radius five, taking at most
twelve. The coordinate bounding box and local-support gates prevent unrestricted
extrapolation. They do not establish nuclear existence or reliable interpolation.
Every modeled property exposes its neighbor identities, weights and references.

Decay vectors require every source token to parse as an explicit, nonestimated
simple-mode equality; the fractions must sum exactly to one. Incomplete,
uncertain, overlapping, delayed and IT expressions are excluded, never
renormalized. NUBASE B+ means combined positron emission and electron capture;
the output preserves `beta_plus_or_electron_capture`. EC remains a separate
source category; a vector containing both EC and aggregate B+ is rejected.
Alpha, beta-minus, neutron and proton modes remain distinct. No gamma branching
probability is available. IT, photon yields and gamma emission probabilities
are different quantities; the code does not reinterpret them.

The weighted average of complete admitted vectors conserves unit sum. A zero
weight for a mode absent from those complete vectors is an empirical model result,
not an experimental zero for the target. These predictions are not calibrated
probabilities. Strict parsing produces a selected training subset and can bias
coverage.

The current corpus supplies 3,558 ground-state references, 2,832 nonestimated
point lifetimes and 1,315 complete branch vectors. Deterministic coordinate
holdout predicts 562 lifetimes with log10 RMSE 2.968 and 257 branch vectors with
mean total variation 0.144. Element-group holdout (all Z divisible by five are
withheld together) predicts 554 lifetimes with log10 RMSE 2.858 and 245 branch
vectors with mean total variation 0.151. The roughly three decades of lifetime
error make this an exploratory approximation, unsuitable for replacing source
lifetimes. Residuals are not confidence intervals. Unpredicted held-out cases are
reported explicitly, along with complete held-out identities and training hashes.
Neither validation split permits a held-out record to serve as its own neighbor.

Model metadata records source file hash, source metadata, normalized-record hash,
algorithm version, kernel parameters, validation results and approximation
limitations. Known source uncertainties are retained; no predictive uncertainty
is invented. Ground-state composition alone omits shell/state and decay-Q-value
physics. A future validated model should add state-aware physical features and
compare parity-stratified kernels and independent evaluated releases.

NUBASE conventions are documented in the [NUBASE2020 evaluated nuclear properties
paper](https://www-nds.iaea.org/amdc/ame2020/NUBASE2020.pdf). Native text and exact
ratios remain authoritative; floating point occurs only in the downstream model.

With `predict(..., approximate_missing=True)` or CLI `--approximate-missing`,
missing statistics for a known source identity can be approximated separately
under `missing_stat_approximations`. Existing source points, bounds, estimates and
stable assignments are preserved. The separate result is explicitly modeled;
stable source assignments are never given a modeled finite lifetime or decay
vector. Without that option, a known identity returns source references only.
