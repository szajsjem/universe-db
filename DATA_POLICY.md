# Data policy

## Admission requirements

An import is accepted only when it records:

1. a stable source citation and URL or persistent identifier;
2. upstream version/release and retrieval date;
3. redistribution license or an explicit determination that only uncopyrightable
   factual identities are represented;
4. provenance class (`measured`, `modeled`, `curated`, or `fictional`);
5. units, conditions, uncertainty, and method when the source provides them;
6. a reproducible transformation represented in version control.

The repository does not accept values copied from an unattributed aggregation,
AI-generated scientific measurements, or data whose redistribution terms are
unknown.

## Meaning of provenance

- `measured`: an observation reported by an experimental source.
- `modeled`: a model output with model/version/input metadata.
- `curated`: an identity, reviewed selection, or authored engineering value
  that is not being claimed as a direct measurement.
- `fictional`: deliberately invented data in an explicit fictional namespace.

Modeled and fictional values may coexist with measured values but must never
be selected as measured by a view or export.

## Missing and conflicting data

Missing data is represented by no observation row. Zero is stored only when a
source actually reports zero. Conflicting observations are separate rows with
their original sources and conditions. Corrections add a reviewed replacement
or deprecation trail; published source observations are not silently edited.

## Numeric representation

Authoritative numbers are integer ratios. Units carry an exact rational SI
scale and an optional base-10 exponent, allowing very small units such as barns
without overflowing SQLite integers. Uncertainty is stored beside the value.

Floating point may be used by a downstream model, but model outputs must record
the algorithm version, inputs, and approximation policy before admission.

## Review boundary

Schema support does not imply data coverage. A table with zero rows is an
honest coverage result. Imports for nuclides, spectra, crystal structures,
dissociation equilibria, or nuclear channels require a source-specific review
before merging.
