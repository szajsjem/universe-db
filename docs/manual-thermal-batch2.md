# Manual thermal and ceramic chemistry research — second batch, 2026-10-13

This slice adds **six compound targets and 18 textual facts** to
[`thermal-batch2-2026-10-13.json`](../sources/manual-chemistry/thermal-batch2-2026-10-13.json).
It is **pending human review**, under [DATA_POLICY.md](../DATA_POLICY.md).
Research input authoring does not promote a compound or implement a mod material.

| Compound | Formula | Source-backed application lead | Proposed mod use, separate from evidence |
| --- | --- | --- | --- |
| Aluminum oxide | Al2O3 | Electrical insulation and electronic substrates in alumina ceramics | Ceramic insulators, electronic substrates and wear components |
| Boron nitride | BN | Hexagonal-BN thermal management and molten-metal processing | A separately identified hBN heat-spreading/insulating material |
| Silicon carbide | SiC | Loose abrasive powders; reaction-bonded ceramic composition boundary | Grinding/lapping consumables and distinct ceramic component grades |
| Zirconium dioxide | ZrO2 | Stabilized ceramic grades and oxygen-transport membrane leads | Feedstock for separately modeled stabilized ceramics |
| Magnesium oxide | MgO | Refractories, heaters and mineral-insulated sensor/conductor tubes | Furnace, heater and sensor components |
| Lithium fluoride | LiF | UV optics, X-ray spectrometry crystals and molten-salt component use | Optical feedstock and separately specified coolant mixtures |

## Primary sources inspected

- [CoorsTek alumina](https://www2.coorstek.com/en/materials/alumina/),
  [magnesia](https://www2.coorstek.com/en/materials/magnesia/),
  [silicon carbide](https://www2.coorstek.com/en/materials/silicon-carbide/) and
  [zirconia](https://www2.coorstek.com/en/materials/zirconia/): current undated
  manufacturer material-family pages, retrieved 2026-10-13. The public pages
  were read directly; their grade property tables are not imported.
- [Saint-Gobain boron nitride](https://www.bn.saint-gobain.com/): current
  undated manufacturer page, retrieved 2026-10-13. Its opening identifies the
  material as hexagonal BN; application facts retain that phase scope.
- [NIST-JANAF boron index](https://janaf.nist.gov/tables/B-index.html):
  Fourth Edition (1998) online index, used only for BN identity, not its
  copyrighted thermochemical compilation.
- [NIST Chemistry WebBook zirconium dioxide](https://webbook.nist.gov/cgi/cbook.cgi?ID=1314-23-4&Units=SI):
  current SRD 69 identity page, retrieved 2026-10-13; O2Zr is rewritten as
  ZrO2 without changing composition. The similarly named monoxide is excluded.
- [PACE abrasive belts, rolls and powders](https://www.metallographic.com/metallographic-consumables/grinding/belts-rolls-powders):
  current undated manufacturer page, retrieved 2026-10-13; the SiC loose-powder
  application section supports lapping, grinding and polishing.
- [Thermo Scientific optical-grade lithium fluoride, product 14056](https://www.fishersci.com/shop/products/lithium-fluoride-optical-grade-99-5-thermo-scientific/AA1405606):
  current undated supplier/manufacturer product page, retrieved 2026-10-13.
  FLi and ionic SMILES support the LiF formula-unit identity; only the named
  application leads are retained.

Each fact stores its own URL, original supporting paraphrase, retrieval date
and factual-only redistribution determination. No manufacturer prose table or
scientific numerical measurement is copied. The qualitative application claims
are curated manufacturer/institutional evidence awaiting reviewer inspection,
not model-created measurements.

## Identity reconciliation and limits

Read-only searches inspected reviewed entity names, chemical-species formulas
and aliases, candidate formulas/names/aliases, and prior manual JSON entries.
No matching reviewed compound identity or earlier manual entry was found for
these six targets in that bounded search. All six already have candidate leads;
this batch enriches their research and does not claim discovery of new compounds.

The JSON links **30 exact existing candidate IDs** with matching formula
composition: 12 Al2O3, two BN, five SiC, four ZrO2, six MgO and one LiF. Generic
name-only alumina/zirconia/SiC leads remain unlinked because their identity is
less constrained. The formula-matching `corundum` candidate
`b5fff529-cdc7-4d0f-8218-be8b483a6e3d` remains unlinked because it denotes a
specific crystal material. One linked MgO lead uses the old coarse `molecule`
classification; its evidence is an MgO carbonation equation. The new record
uses `formula_unit` and does not copy the old classification.

All six identities specify neutral formula units. Stoichiometry alone does
not choose a crystal phase, ceramic grade or microstructure. Hexagonal and
cubic BN are not aliases. Stabilized zirconia, zirconia-alumina abrasives,
silicon-infiltrated or graphite-containing SiC, ceramic grades, filled polymers,
LiF-containing molten salts, doped dosimeters and enriched lithium-isotope
materials remain separate materials or mixtures. Engineering facts about such
derivatives explicitly retain the derivative scope instead of assigning their
performance to a pure formula identity.

There are no temperature limits, densities, efficiencies, planet deposits,
crafting yields, blend fractions, nuclear recipes or universal thermal-protection
ratings in this slice. A mod recipe or modeled material property would require
its own authored-data/provenance decision.

Only the two owned research files were authored here. The parent handles any
subsequent offline import and commit. No database, schema, shared script,
compilation or project test was changed or run by this researcher.
