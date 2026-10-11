# Elemental property evidence

`elements.db` contains 187 source-backed research observations for all 33
constituent elements used by the alloy reference, from 48 cited sources.
Rebuild without network access:

```powershell
python scripts/build_element_evidence.py
python scripts/fit_alloy_properties.py
```

Sources and transformations are versioned in `sources/elements/`. Three
parallel research passes cover ferrous/refractory, light, and precious metals;
a fourth document covers H, N, O, P, and S. The observations include 49
densities, 59 molar heat capacities, 17 mass heat capacities, 31 melting
points, 19 thermal conductivities, 8 electrical resistivities, and 4 elastic
properties. Multiple observations can describe one element at different
temperatures, phases, or source versions.

The reviewed core's 29 missing constituent-density evidence entries now have
source-backed research candidates. This closes the density **source coverage**
gap, not the scientific review or fitting-context gaps. All observations
remain `pending_human_review` in `unverified_element_*` tables. Many density
references lack a temperature or phase, and some sources describe liquids
at their boiling points. Those values are not room-temperature solid densities.

`unverified_element_source` records citation, URL, upstream version, retrieval
date, and a license/factual-data determination. `unverified_element_observation`
stores exact rational numbers, temperature, phase, state, method, source
location, and provenance. `input_json` preserves the complete authored source
record, including any pressure, uncertainty, and composition-basis metadata.
`unverified_element_gap` retains 192 outstanding property/context research
notes. Missing values are never replaced with zero.

Evaluated elemental references differ from finite-purity experimental
specimens. `composition_basis` identifies `elemental_reference`,
`finite_purity_specimen`, or `unspecified`. Finite specimens retain their
actual assay/state description and cannot silently become exact pure-element
training endpoints. In particular, a nominally pure nickel or reference-metal
specimen is not declared 100% pure just to satisfy a fit.

## Training endpoints

```python
from scripts.fit_alloy_properties import load_element_training_records

result = load_element_training_records("specific_heat_capacity", elements={"Al", "Mg", "Ti"})
records = result["records"]
excluded = result["excluded"]
```

The loader requires a point value, explicit temperature, phase, state, and
elemental-reference composition basis. It excludes modeled source responses
from observed endpoint training. Returned records remain pending review and
are not automatically matched across different conditions. The
[fitter](alloy-fitting.md) still rejects differing states and temperatures.

Source-native molar heat capacities are preserved in J/(mol*K). When mass
heat capacity is requested, the loader converts exactly using the repository's
PubChem atomic mass snapshot, preserving the source value and transformation
metadata. This conversion adds no new measurement precision; uncertainty is
not inferred or propagated when unavailable.

The audit report retains reviewed-core coverage separately from pending
elemental candidates, lists remaining per-element property gaps, and records
database digests. Elastic properties, transport properties for many elements,
allotrope-specific evidence, and matching alloy specimen compositions remain
priority gaps. Historical evaluated transition temperatures coexist with
newer references; they are not silently overwritten.

Versioned release exports include `elements.db`, its checksum, and the
`unverified_element_*` tables in the combined `universe.db`.
