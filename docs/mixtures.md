# Integer mixtures, alloys and ceramic cells

The function accepts atoms, molecules or formula units with integer counts.
For example `[99, 1]` for Fe/C means 99 iron atoms per carbon atom. It does
not mean 99 wt% iron. Molecule counts count whole molecules, not their atoms.
The output preserves exact component number fractions, mass fractions,
elemental atom counts and fractions, charge, electrons, and molar masses.

```python
from scripts.mixture_properties import calculate_mixture, structure_from_prototype

result = calculate_mixture([{"formula": "Fe"}, {"formula": "C"}], [99, 1])
print(result["component_fractions"])
```

`DeterministicPropertyCalculator.load().calculate_mixture(...)` exposes the
same function while reusing the already loaded element database. Reviewed
chemical species can use `{"species_id": "chem:carbonate"}`. Formula inputs
may specify an integer `charge`; species IDs use their recorded charge.
Counts can include zero, but cannot be negative, fractional, Boolean, or all
zero. Zero-count components contribute nothing and need no property inputs.

## Property models

Models are opt-in. A temperature and consistent source-backed constituent
statistics are required. All constituent observations must have conditions
equal to the requested target. The calculator does not interpolate
temperature or infer missing conditions.

```python
conditions = {"temperature_k": "293.15"}
components = [
    {"formula": "Fe", "stats": {
        "density": {"value": "7870", "unit": "kg/m3", "phase": "solid",
                    "conditions": conditions, "source": "illustrative input"}}},
    {"formula": "C", "stats": {
        "density": {"value": "2200", "unit": "kg/m3", "phase": "solid",
                    "conditions": conditions, "source": "illustrative input"}}},
]
estimate = calculate_mixture(components, [99, 1],
    models=["additive_volume"], conditions=conditions)
```

Those example densities are illustrative caller inputs. The result is an
ideal constituent-mixture estimate, not a validated steel density. Default
molar masses come from the existing source-backed element/species calculator;
`molar_mass_g_mol` overrides that value when explicitly supplied. Fraction
arithmetic is exact over the supplied or source-derived rounded input values.
Uncertainties are not propagated. Each result records inputs, database digest,
algorithm version, model assumptions and method classes.

| Model | Required statistics | Output |
|---|---|---|
| `additive_volume` | density (`kg/m3`) | Density from total mass / additive constituent volumes |
| `ideal_heat_capacity` | specific_heat_capacity (`J/(kg*K)`) | Mass-weighted constant-pressure heat capacity |
| `thermal_bounds` | density; thermal_conductivity (`W/(m*K)`) | Series and parallel ideal laminate values |
| `electrical_bounds` | density; electrical_conductivity (`S/m`) | Series and parallel ideal laminate values |
| `elastic_bounds` | density; bulk_modulus and shear_modulus (`Pa`) | Voigt/Reuss bulk, shear, and derived isotropic Young's-modulus bounds |

Every statistic uses `{value, unit, phase, conditions, source}`. Numbers may
be decimal strings, integers, Decimal, or Fraction; binary floating-point
inputs are rejected. Temperature is in kelvin and pressure, if specified,
in pascals. Statistics must be positive, finite and in the listed units.
Missing required values, units, sources, phases or matching conditions fail
the requested model instead of producing an arbitrary fallback.

Density and volume fractions assume zero excess volume and no porosity.
Heat capacity assumes no excess heat capacity, reaction or phase transition.
Transport models assume isotropic conductivities and perfect interfaces;
their series/parallel geometry is not a prediction of alloy microstructure.
Elastic bounds assume linear elasticity, isotropic constituent properties,
an isotropic effective response, and perfect bonding. They do not predict
yield strength or hardness.

## Crystal and ceramic structures

The existing database schema already supports materials of kind `ceramic`,
crystal structures, space groups, lattice parameters and sites. This calculator
adds cell-based modeling without creating unsupported measured structure rows.

```python
cell = structure_from_prototype("rocksalt", "5")  # illustrative a = 5 angstrom
ceramic = calculate_mixture([{"formula": "Mg"}, {"formula": "O"}],
                           [1, 1], structure=cell)
print(ceramic["models"]["crystal_density"])
```

The authored [prototype catalog](../sources/crystal_prototypes.json) includes
BCC, FCC and rocksalt conventional cubic cells, full-occupancy fractional
sites, component-role counts, space-group identities and primary citations.
The selected prototype does not establish that the mixture actually forms
that phase. Lattice constants must be supplied; none are guessed from atomic
radii or mixed from elemental lattice constants.

For an arbitrary cell, pass `structure` with `lattice_angstrom` containing
`a,b,c,alpha,beta,gamma`, `cell_counts` aligned with the input component list,
and `conditions` matching the target. Angles are degrees. Cell contents must
be proportional to the requested integer composition. A molecular/formula-unit
component's count is the number of whole units in the cell. Impossible or
degenerate cell metrics are rejected. Density is calculated from cell mass,
Avogadro's constant and the full triclinic cell volume. It represents a fully
occupied, zero-porosity cell. Optional `porosity_fraction` adds a separate
bulk-density estimate `(1-porosity)*cell_density`, assuming negligible pore
mass. When fractional `sites` are supplied, their counts must match the cell
contents and sites cannot overlap. The model does not determine bonding, defects, phase
stability or mechanical properties.

The supplied component quantities may describe unreacted ingredients.
The function does not assume they react into a named compound, substitute
into a lattice, dissolve in a matrix, or reach thermodynamic equilibrium.
Reaction products and phase fractions require separate evidence or models.

## JSON command line

```sh
python scripts/mixture_properties.py examples/iron-carbon-mixture.json
python scripts/mixture_properties.py examples/ceramic-cell.json --output .build/ceramic-result.json
```

Outputs are model results, not automatic database promotions. Unknown alloy
strength, melting behavior, microstructure and spectra are listed explicitly.

The cell-volume/density implementation follows the
[IUCr cell-volume definition](https://it.iucr.org/Cb/ch1o1v0001/) and
[IUCr density consistency check](https://journals.iucr.org/services/cif/checking/DENSD01.html).
Series/parallel transport follows the
[effective-conductivity formulation](https://doc.comsol.com/6.3/doc/com.comsol.help.acdc/acdc_ug_theory.05.39.html).
