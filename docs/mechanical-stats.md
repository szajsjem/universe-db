# Calculated alloy mechanical statistics

`scripts/alloy_mechanical_properties.py` fits a portable explicit-state profile
of independent mechanical targets using the existing exact-rational Scheffe
mixture regression. Linear models use `sum(beta_i*x_i)` and quadratic models
add `beta_ij*x_i*x_j`, where `x` is elemental mass fraction. Each target gets its
own coefficients, composition domain, evidence, digest and diagnostics. No
fixed tensile-to-compressive ratio or strength-to-toughness conversion is used.

Targets and required units:

| Target | Unit | Meaning |
|---|---|---|
| tensile_strength | Pa | Ultimate tensile strength under stated conditions |
| compressive_strength | Pa | Source-defined compressive failure strength |
| yield_strength | Pa | Yield criterion must be specified in conditions |
| fracture_toughness | Pa*sqrt(m) | Source-defined fracture toughness, not impact energy |
| energy_toughness | J/m3 | Energy per volume from the source's stress-strain measurement |
| elongation_at_break | 1 | Engineering strain fraction, not percent |

All records use the training shape in [alloy-fitting.md](alloy-fitting.md), with
exact elemental mass fractions, point values, unique IDs, citations, provenance
and explicit temperature, phase and processing/measurement state. Extra
conditions such as specimen orientation, strain rate and yield criterion are
part of the state signature. Unit conversion must happen explicitly before
fitting. A nominal grade recipe is not a measured specimen composition. Ranges
must not be replaced by midpoints. Pure-element endpoints are not required for
this mechanical profile: microstructure-matched alloy specimens can span the
design, while pure carbon is not a steel endpoint. Rank-deficient fits still fail.
Profiles currently require the same state for every target. Use separate
profiles for different heat treatments, tensile/compressive test contexts, etc.

```sh
python scripts/alloy_mechanical_properties.py train --training specimen-records.json --degree 2 --output .build/mechanical-profile.json
python scripts/calculate_stats.py --model .build/mechanical-profile.json --input alloy-query.json --output .build/alloy-stats.json
```

Query shape:

```json
{"kind":"alloy", "composition_mass_fractions":{"Fe":"9/10","Ni":"1/10"},
 "conditions":{"temperature_k":"300","phase":"solid","state":"must match training"}}
```

This JSON demonstrates the interface only, not a scientifically supported alloy.
`fit_mechanical_properties` and `mechanical_properties` are also callable Python
APIs. Training requires reviewed evidence by default. `--allow-unverified` and
`--allow-synthetic` permit explicitly labeled research and fictional fixtures,
respectively; neither promotes observations. No fitted production mechanical
coefficients are published from the current pending grade-level evidence.

The result retains exact ratios, units, conditions, composition, provenance and
training/profile hashes. Unsupported targets, compositions and nonphysical
responses return independent `unavailable` reasons. A mismatched state is an
input error. There is no extrapolation switch in this profile API. No prediction
uncertainty is invented; training RMSE is not independent validation. Fits must
be independently validated on specimen/grade groups before production use.

If elongation is supported, an authored brittleness index is
`reference_strain / (reference_strain + elongation)`, with default reference
strain `1/20`. It is between zero and one and decreases with ductility. This is
an explicit gameplay-oriented proxy, not a measured brittleness property or a
fracture criterion. It carries the elongation fit's provenance; it is unavailable
when elongation cannot be calculated. Actual fracture and energy toughness
require their own evidence.

## Isotopes through the same interface

The existing independently fitted atomic mass and decay models can be accessed
through `scripts/calculate_stats.py`:

```sh
python scripts/atomic_isotope_properties.py train --database isotopes.db --allow-unverified-evidence --output .build/atomic-profile.json
python scripts/calculate_stats.py --model .build/atomic-profile.json --input isotope-query.json --output .build/isotope-stats.json
```

```json
{"kind":"isotope", "protons":26,"neutrons":54,"electrons":26,
 "state_index":0,"approximate_missing":true}
```

This returns source-first mass, lifetime and decay statistics, using the liquid-drop/residual mass model and the bounded local lifetime/decay-vector models.
It does not give an isotope a material strength, infer isotope existence, or
infer ion/isomer behavior. `approximate_missing` requires a boolean and only
permits separate modeled missing statistics; existing source bounds, estimates
and stable designations remain intact. See [atomic-isotope-stats.md](atomic-isotope-stats.md)
and [isotope-approximation.md](isotope-approximation.md) for validation errors and
limits. Approximately three decades of lifetime holdout error remain a material
limitation. The shared interface never fits on a query or writes observations.

ICM's `FittedAlloyStats` evaluates this mechanical profile schema with exact
rational arithmetic. Artifact hashes must be verified by the consuming import
pipeline; a digest field by itself is not an integrity check.
