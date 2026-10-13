# Isotope composition fit: scientific review

The composition API uses proton, neutron and electron counts. Its current
lifetime and decay approximation is restricted to ground-state reference atoms
with electrons equal to protons. Electron count is therefore a constraint, not
an independently fitted variable. Isomer lifetimes require nuclear-state and
excitation information; ion lifetimes require charge-state-specific evidence.

The implementation fits local empirical trends in the nuclear chart. It does
not establish that a proposed isotope exists, is bound, or is stable. A positive
modeled lifetime is not evidence of radioactivity. Known reference values take
priority, including stability, censored limits and estimated-source flags.

## Source semantics checked

[NUBASE2020](https://www-nds.iaea.org/amdc/ame2020/NUBASE2020.pdf), sections
2.3 and 2.5, specifies a tropical-year conversion, represents beta-plus as the
combined electron-capture and positron category, and reports delayed-particle
intensities alongside inclusive beta intensities. These quantities cannot all
be treated as mutually exclusive probabilities. Its year expression prints
365.2422 days and rounded 31556926 seconds.

Internal transition is not a photon-emission probability: conversion electrons
and cascades require separate transition evidence. The composition fitter
therefore leaves gamma probability unavailable. Nuclear photon yields and
energy spectra need a transition-resolved source such as ENSDF and an explicit
yield basis (per parent decay or per transition).

## Admission and validation requirements

- Lifetime interpolation uses positive, nonestimated point values; bounds,
  stability and unsupported source qualifiers are preserved as reference
  information rather than transformed into regression targets.
- A decay vector requires all source tokens to be supported exact primary
  intensities, unique disjoint categories and a unit sum. Inclusive beta-plus
  cannot coexist with a separate electron-capture category in that vector.
  Delayed emission, unknown branches, limits and unsupported modes invalidate
  the vector; they are not silently removed or renormalized.
- Validation removes held-out identities before selecting neighbors. Both
  scattered coordinate holdouts and entire-element holdouts are needed.
  Prediction coverage must accompany error metrics because a local-support
  guard can abstain on difficult cases.
- Lifetime error is measured in log10 seconds, since lifetimes span many
  orders of magnitude. Decay-vector error uses total variation; prediction
  weights stay nonnegative and sum to one.
- Public fitting inputs must validate integer coordinates, consistent mass
  number, ground-state identity, positive finite lifetime values and branch
  conservation, independently of the database loader.

Local interpolation can fail near shell closures, pairing changes, different
decay mechanisms and energy thresholds. Validation errors describe tested
holdouts; they are not calibrated prediction intervals. Neighbor traces,
source locators and training hashes make every modeled result auditable.
Empirical vectors express model weights, not demonstrated decay probabilities
for an unobserved isotope. No modeled result is promoted to reviewed evidence.
