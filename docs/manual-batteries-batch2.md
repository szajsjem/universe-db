# Battery precursor and electrolyte research — batch 2, 2026-10-13

This slice adds six manually selected chemical targets with **18 sourced textual
facts**, plus structured identities, in
[`batteries-batch2-2026-10-13.json`](../sources/manual-chemistry/batteries-batch2-2026-10-13.json).
They are model-assisted **unverified research**, subject to human review under
[DATA_POLICY.md](../DATA_POLICY.md). No measurements, capacities, efficiencies,
recipe yields or game balance are inferred.

| Compound | Identity | Sourced relevance | Proposed mod role |
| --- | --- | --- | --- |
| Lithium sulfate | Li2SO4, neutral formula unit | Lithium iron phosphate precursor; lead-acid additive | Lithium-processing intermediate |
| Lithium carbonate | Li2CO3, neutral formula unit | Lithium iron phosphate precursor; sulfate-to-carbonate processing | Battery-material precursor |
| Lithium nitrate | LiNO3, neutral formula unit | Lithium-sulfur/metal electrolyte additive; lithium-surface passivation | Advanced battery additive |
| Lithium tetrafluoroborate | LiBF4, neutral formula unit | Liquid electrolyte ingredient; solid composite electrolyte research | Alternative electrolyte salt |
| Ethylene carbonate | C3H4O3, neutral molecule | Battery solvent; blending with carbonates for liquid, lower-viscosity formulations | Cyclic carbonate solvent |
| Dimethyl carbonate | C3H6O3, neutral molecule | EC/DMC lithium-battery electrolyte solvent component; transesterification product | Linear carbonate co-solvent |

The proposed roles are design suggestions kept in `usefulness`, separately from
source facts. A formulated EC/DMC/LiPF6 electrolyte is not identified with either
neat solvent, and its product specifications are not properties of those solvents.
Lithium salts are formula units; no isolated neutral-molecule structure is asserted.

## Primary source inspection

All cited references are the manufacturer's own product documentation, retrieved
2026-10-13, identified by stable product numbers. Only independently worded
qualitative facts and chemical identities are represented; source prose, tables,
images and numerical product specifications are not redistributed. Every fact's
citation retains retrieval date and factual-only redistribution determination.

- [MilliporeSigma lithium sulfate 920339](https://www.sigmaaldrich.com/US/en/product/aldrich/920339): formula and cathode/additive applications. The vague general-description statement about lithium ions in batteries is deliberately not used as evidence of a conventional Li-ion electrolyte formulation.
- [Lithium carbonate 931942](https://www.sigmaaldrich.com/US/en/product/aldrich/931942): formula, lithium iron phosphate preparation and sulfate concentrate conversion.
- [Lithium nitrate 930938](https://www.sigmaaldrich.com/US/en/product/aldrich/930938): formula and electrolyte additive/passivation applications; numerical performance anecdotes are omitted.
- [Lithium tetrafluoroborate 451622](https://www.sigmaaldrich.com/US/en/product/aldrich/451622): formula and liquid/solid-composite electrolyte applications.
- [Ethylene carbonate 809950](https://www.sigmaaldrich.com/US/en/product/aldrich/809950): identity, condensed formula, solvent application and carbonate blending. Expanded C3H4O3 agrees with the source's InChI formula.
- [Dimethyl carbonate 517127](https://www.sigmaaldrich.com/US/en/product/sial/517127): identity and condensed formula. Expanded C3H6O3 agrees with the source's InChI formula.
- [EC/DMC lithium hexafluorophosphate solution 746711](https://www.sigmaaldrich.com/US/en/product/aldrich/746711): evidence for DMC as a component of a salt-containing battery electrolyte, without assigning blend properties to DMC.
- [Ethylene carbonate E26258](https://www.sigmaaldrich.com/US/en/product/aldrich/e26258): dimethyl carbonate preparation by transesterification.

## Identity search and limitations

Read-only SQLite searches inspected reviewed `entity`, `alias` and
`chemical_species` tables and staging `unverified_entity_candidate`,
`unverified_candidate_alias` and earlier manual facts, using compound names,
selected manufacturer synonyms and exact formulas. Earlier checked-in manual
inputs were also inspected. No compatible reviewed or candidate identities were
found in these bounded searches; all six targets therefore use new proposed
`chem:` IDs and empty candidate-link arrays. This is not proof of absence under
every possible synonym or molecular representation.

Candidate `62f127f5-cf7c-4f4b-a5da-b4617a8f32fe` is an unspecified
**tetrafluoroborate anion**, charge -1, not neutral LiBF4, so it is not linked.
Formula-only candidates named pyruvate (C3H4O3) and lactic acid (C3H6O3) are not
carbonate identities and are not linked. Equal atom counts do not establish
molecular identity. Lithium hexafluorophosphate was researched in the first batch
and is not duplicated here.

These files do not change the reviewed database, mod catalog, ICM pin or
recipes. The parent owns any staging import and integrity checks. No compilation
or project test suite was run by this research agent.
