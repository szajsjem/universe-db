# Alloy and element property approximation

Run the database evidence audit before selecting training data:

```powershell
python scripts/fit_alloy_properties.py
```

The report is written to `.build/alloy-evidence-audit.json`. It checks all
118 elements against eight physical properties and identifies the 33 elements
used by the alloy reference. Every constituent lacks at least one checked
property; 29 lack density evidence in the reviewed core. Atomic mass evidence
exists for all 118 elements. Presence of a property observation does not mean
its temperature, allotrope, or material state is suitable for a fit.

The new [elemental evidence database](element-evidence.md) adds 187 pending
observations. All constituent density coverage gaps have a research source;
the reviewed-core counts above remain unchanged. The audit reports both.

The current 177 alloy property records have no eligible reviewed training
rows. They remain pending human review; many have ranged compositions or
unspecified measurement temperatures. Commercially pure grades are reported
as possible research leads, never substituted for exact elemental endpoints.
An explicit nominal recipe can be extracted with `exact_alloy_composition`,
but nominal composition is not a measured specimen composition.

## API

`load_element_training_records(property_name, elements={...})` extracts
explicit-state elemental endpoints from `elements.db` with their citations
and review status. It excludes finite-purity specimens and missing context,
and preserves source-native data when converting molar heat capacities.

`scripts.fit_alloy_properties.fit_alloy_approximation(records, degree=1)`
fits exact-rational weighted least squares to elemental **mass fractions**.
The linear model is `sum(beta_i * x_i)`; `degree=2` adds pairwise
`beta_ij * x_i * x_j` interactions. These are
[Scheffe mixture models](https://www.itl.nist.gov/div898/handbook/pri/section5/pri542.htm).
There is no separate intercept because fractions sum to one. Use
`transform="reciprocal"` to fit specific volume instead of density.

Each training record has this shape (the placeholders are not measurements):

```python
{
    "id": "stable-observation-id",
    "property": "density",
    "unit": "kg/m3",
    "value": "source-reported-point-value",
    "composition_mass_fractions": {"Fe": "exact-fraction", "C": "exact-fraction"},
    "conditions": {"temperature_k": "source-temperature", "phase": "solid",
                   "state": "source-reported-processing-and-structure"},
    "source": "persistent source citation or URL",
    "review_status": "reviewed",
    "provenance_class": "measured",
    "weight": "1",
}
```

Numbers are decimal strings, integers, or rational strings such as `1/2`;
binary floats are rejected. Compositions must sum exactly to one. All records
must match property, unit, temperature, phase, and state. By default each
element needs a pure-element training endpoint, and all records must be
reviewed. A quadratic binary model also needs an independent mixed-composition
point. More records are needed for residual error assessment. Rank-deficient
designs fail rather than receive invented coefficients.

Use `predict_alloy(model, mass_fractions, conditions=...)` for composition
predictions. `predict_integer_mixture(model, components, counts, conditions=...)`
accepts the atom/molecule input from the mixture calculator, expands formulas,
and derives elemental mass fractions using the database's PubChem atomic
masses. Equal atom counts do not imply equal mass fractions. Isotope/mass
overrides are rejected by this regression adapter.

To fit an explicitly prepared source-backed training file after the audit:

```powershell
python scripts/fit_alloy_properties.py --training training.json --degree 2 --output .build/alloy-fit.json
```

`--allow-unverified` explicitly permits research fitting without promoting
evidence. `--allow-synthetic` permits fictional demonstration inputs and marks
the resulting model fictional. Neither option writes observations into the
reviewed database.

Models preserve complete training records, a SHA-256 digest, coefficients,
conditions, composition limits, and transformed training RMSE. Predictions
are labeled approximations and have no inferred uncertainty. Training RMSE
is not independent validation; a saturated fit can have zero residual with
no evidence of predictive accuracy. Coordinate limits are not a convex-hull
check. Polynomial fits do not predict phase diagrams, crystal structures,
precipitation, or heat-treatment effects. Separate fits are needed for
different structures and states; measured lattice parameters belong in the
[mixture/crystal calculator](mixtures.md).
