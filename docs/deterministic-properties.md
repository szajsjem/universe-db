# Deterministic atomic and composition properties

`scripts/calculate_properties.py` calculates the properties that are actually
identifiable from an atomic number, an isotope coordinate `(Z, N)`, or an
elemental composition. It has no training phase, random state, learned weights,
or network dependency. The same input and database artifact produce the same
JSON output.

The existing material descriptor is also deterministic: it is a fitted
composition k-nearest-neighbour classifier, not a neural network. This
calculator is different because it evaluates declared equations and does not
infer a material class from analogues.

## Examples

Calculate exact identity counts for iron and report the reviewed elemental
relative mass:

```sh
python3 scripts/calculate_properties.py --atomic-number 26 --charge 2
```

Add a neutron count to select an isotope and enable the nuclear liquid-drop
estimate:

```sh
python3 scripts/calculate_properties.py \
  --atomic-number 26 --neutrons 30 --charge 2
```

Calculate water composition invariants and source-derived mass values:

```sh
python3 scripts/calculate_properties.py --formula H2O
```

Formula input is neutral formula text. Ionic charge is a separate signed
integer, positive for cations:

```sh
python3 scripts/calculate_properties.py --formula SO4 --charge -2
```

Use an active reviewed species to take both composition and charge from the
database:

```sh
python3 scripts/calculate_properties.py --species chem:carbonate
```

An ideal-gas density is calculated only when both conditions are explicit:

```sh
python3 scripts/calculate_properties.py \
  --formula O2 --temperature-k 273.15 --pressure-pa 101325
```

## Method classes

Every numeric property carries a `method_class` so downstream code can keep
unlike claims separate:

- `exact_from_input` covers integer counts, charge, and rational composition;
- `source_observation` is a reviewed value read from `universe.db`;
- `derived_from_source_observations` aggregates those reviewed values;
- `derived_from_exact_constant` uses an exact SI defining constant;
- `conditional_ideal_model` is valid only under its stated physical model;
- `semi_empirical_model` is an approximate nuclear liquid-drop result.

The output records the calculator version, exact database SHA-256, constants,
formula references, numeric policy, and `random_seed: null`.

## Implemented relations

For a formula with element counts `n_i`, atomic numbers `Z_i`, and signed
charge `q`:

```text
atoms       = sum(n_i)
protons     = sum(n_i Z_i)
electrons   = sum(n_i Z_i) - q
atomic x_i  = n_i / sum(n_i)
M_r         = sum(n_i A_r,i)
mass w_i    = n_i A_r,i / M_r
M           = M_r M_u
charge      = q e
```

`A_r,i` comes from the pinned PubChem relative-atomic-mass observation already
reviewed into the database. It is not silently replaced by a different atomic
weight table. `M_u`, the atomic mass constant, particle masses, elementary
charge, Avogadro constant, and gas constant use the 2022 CODATA values. Molar
mass is evaluated as `M = M_r M_u`, rather than assuming the post-2019-SI molar
mass constant is exactly 1 g/mol.

The optional ideal-gas result is:

```text
rho = p M / (R T)
```

It is not a prediction of liquid or solid density.

For neutral, closed-shell organic formulas containing only C, H, N, O, S, and
halogens, the calculator also reports the formula-screening relation:

```text
DBE = C + 1 + (N - H - F - Cl - Br - I) / 2
```

It abstains for charged formulas, formulas without carbon, unsupported
elements, or a negative result. DBE constrains a structure; it does not identify
one.

When both `Z` and `N` are given, `A = Z + N` and the Benzaid et al. coefficient
set fitted to AME2016 is used:

```text
B = a_v A - a_s A^(2/3) - a_c Z^2/A^(1/3)
    - a_a (A - 2Z)^2/A + delta a_p/A^(1/2)

a_v = 14.9297 MeV   a_s = 15.0580 MeV
a_c = 0.6615 MeV    a_a = 21.6091 MeV
a_p = 10.1744 MeV
delta = +1 even-even, -1 odd-odd, 0 otherwise
R = 1.2257 fm A^(1/3)
```

Binding energy per nucleon, mass defect, estimated nuclear mass, and estimated
atomic/ion mass follow algebraically. This is a semi-empirical approximation,
not an observation. The source reports its strongest agreement for `A >= 50`;
light nuclei, shell closures, deformation, and electronic binding need better
models or measured data. A nonnegative model binding value is not a half-life
or stability claim.

## Why composition cannot calculate every property

There is no deterministic function from composition alone to all chemical
properties. Ethanol and dimethyl ether both have formula `C2H6O`, yet their
structures and physical properties differ. A substance can also have multiple
phases, polymorphs, charge states, spin states, and isotopic compositions.

Consequently, the JSON includes `not_identifiable_from_inputs` rather than
inventing values for:

- connectivity, geometry, stereochemistry, and isomer identity;
- condensed-phase density, melting point, and boiling point;
- heat capacity, thermodynamic functions, and reaction properties;
- spectra, dipole moment, polarizability, and electronic levels;
- solubility, toxicity, and mechanical properties;
- isotope half-life, decay channels, nuclear spin, and nuclear moments.

Those properties require additional structure and conditions, a numerical
quantum/statistical-mechanical model, or reviewed experimental observations.
More sophisticated deterministic quantum chemistry can improve estimates, but
it still needs geometry, charge, spin, method/basis choices, and convergence
criteria; composition alone is insufficient.

## References

- NIST, [2022 CODATA recommended values](https://physics.nist.gov/cuu/pdf/wall_2022.pdf).
- IUPAC, [relative molecular mass](https://goldbook.iupac.org/terms/view/R05271).
- D. Benzaid et al., [Bethe-Weizsaecker semi-empirical mass formula parameters
  2019 update based on AME2016](https://doi.org/10.1007/s41365-019-0718-8).
- D. A. Laws, [Molecular Formula and Degree of
  Unsaturation](https://doi.org/10.1038/2001202a0).

