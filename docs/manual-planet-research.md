# Manual planet and life-support chemistry leads, 2026-10-13

The source slice `sources/manual-chemistry/planet-life-support-2026-10-13.json`
records six manually researched identities with eighteen sourced facts. It is
model-assisted discovery for unverified staging, not reviewed scientific data.
All prose is an original factual paraphrase. Source identities, document titles,
URLs, retrieval date and factual-only redistribution determination accompany each
fact. No source tables, numerical measurements, efficiencies, reaction yields or
planetary abundance estimates were copied.

| Identity | Use supported by primary sources | Identity reconciliation |
| --- | --- | --- |
| Lithium hydroxide | NASA consumable CO2 removal canisters; carbonate/water products | No exact name, formula or alias found in either database |
| Calcium hydroxide | EPA pH/alkalinity control and lime softening | Reuse reviewed `chem:calcium_hydroxide`; enrich facts |
| Sodium carbonate | EPA pH/alkalinity adjustment and carbonate-assisted softening | Reuse reviewed `chem:sodium_carbonate`; enrich facts |
| Ethylene glycol | Dow heat-transfer and aircraft deicing fluid bases | Existing name-only candidate; evidence adds formula and application facts |
| Propylene glycol | Dow habitat-adjacent heat-transfer application; Sigma water miscibility | Existing candidates for propylene glycol; alias 1,2-propanediol, not 1,3-propanediol |
| Lithium hexafluorophosphate | DOE lithium-battery electrolyte salt and moisture hydrolysis | No exact name, formula or alias found in either database |

The molecular versus formula-unit classification and atom counts are structural
interpretations of the sourced formulas. Glycol products discussed by Dow are
formulated mixtures: their performance is not a measurement of neat glycol.
Useful game-design suggestions stay in `usefulness`, outside sourced scientific
facts. None of these entries asserts a resource deposit on any planet.

Research included read-only exact name, formula and alias queries against
`universe.db` and `universe-unverified.db`. The `existing_candidate_ids` list
records name-matched leads for parent importer reconciliation; it does not create
new identities or promote secondary-source evidence. Three sodium-carbonate
candidates include an unresolved formula and two matching formulas. Calcium
hydroxide has one matching formula candidate; propylene glycol has one name-only
and one matching formula candidate; ethylene glycol has a name-only candidate.

NASA's source contains an illustrative unbalanced reaction line. The added fact
states the identified products qualitatively and deliberately does not reproduce
that line or claim quantitative stoichiometry. NIST WebBook and PubChem pages were
blocked during this session; accessible official manufacturer identities were
used for glycol formulas instead.
