# Material descriptor

`scripts/describe_material.py` describes a proposed material by analogy with
reviewed material compositions. It is intended as a conservative baseline for
out-of-database identities. It does not add candidates to `universe.db`, call a
remote model, or turn an inference into a scientific observation.

## Input contract

Supply one or more `--component` values. A component can be a reviewed species
ID, reviewed name, reviewed formula, or a neutral formula composed of element
symbols in the database:

```sh
# Qualitative composition: components receive equal model weight.
python3 scripts/describe_material.py \
  --name "proposed calcium silicate feed" \
  --component CaCO3 \
  --component SiO2

# Quantitative composition: every component needs a positive exact amount.
python3 scripts/describe_material.py \
  --name "siliceous iron oxide concentrate" \
  --component Fe2O3=0.85 \
  --component SiO2=0.15 \
  --basis mass_fraction
```

Amounts accept decimal or rational text, such as `0.85` or `17/20`. They are
kept as exact rational values in the output and normalized only for model
features. Parentheses, brackets, and hydrate separators are supported in
formula-only input. Charged formula-only input is rejected because charge
notation is ambiguous; use a reviewed `chem:` species ID for a known ion.

## Fit and inference

The model is an instance-based k-nearest-neighbour algorithm:

1. Load active reviewed materials and their components from the selected
   database artifact.
2. Build a component vector and a normalized element vector for each material.
   Quantified components use their declared relative amounts. Fully
   unspecified compositions use equal component weights as an explicit
   fallback.
3. Fit inverse-document-frequency weights from the material corpus.
4. Score component overlap with weighted Jaccard similarity and element
   overlap with cosine similarity. The fixed combined weights are 0.65 and
   0.35 respectively.
5. Vote over the nearest reviewed material kinds. Abstain when the closest
   similarity is below a threshold fitted from leave-one-out nearest-neighbour
   scores.

The normalized element vector is a similarity embedding, not a mass or atomic
fraction claim. In particular, volume or mass fractions cannot be converted to
element fractions without additional density or molar-mass assumptions.

Every result declares the algorithm/version, database SHA-256, training row and
class counts, feature weights, deterministic/no-seed status, validity domain,
fallback policy, nearest-neighbour evidence, and limitations. This keeps model
outputs auditable and separate from the reference-data provenance model.

## Verification

Run:

```sh
python3 scripts/describe_material.py --evaluate
```

The benchmark has two parts:

- exact training-composition retrieval is a pipeline-integrity check and is
  labeled as such, not as generalization evidence;
- leave-one-material-out material-kind prediction excludes the query material
  before fitting IDF weights and searching neighbors, then reports accuracy,
  macro recall, per-kind recall, individual results, and a majority-class
  baseline.

The checked-in corpus is deliberately small: 12 of 15 materials are ores, and
the other material kinds have one example each. High aggregate accuracy can
therefore equal the majority baseline while macro recall remains poor. The
descriptor is useful for traceable analogies and abstention today, but the
singleton kinds are not validated for extrapolation. Adding independently
reviewed alloys, ceramics, glasses, composites, polymers, and measured
condition-dependent properties is required before those targets can be modeled
credibly.
