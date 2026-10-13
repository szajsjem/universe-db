# Crystallographic evidence

`crystals.db` contains 36 source-specific crystal determinations/reference
records from 33 sources, with 182 lattice parameters and 66 asymmetric-unit
site records. Multiple records may describe the same phase at different
temperatures or in different source/settings conventions. All remain pending
human review in `unverified_crystal_*` tables.

## Coverage

- Metals: alpha/gamma iron; silver, aluminum, gold, copper, nickel; magnesium,
  alpha titanium, silicon, and diamond.
- Ceramics: MgO, corundum, SiC 3C/4H/6H, alpha/beta silicon nitride,
  rutile/anatase TiO2, and monoclinic zirconia.
- Molecular/mineral crystals: quartz, aragonite, high-temperature calcite,
  three deuterated-ice phases, two rhombic-sulfur determinations, black
  phosphorus, anhydrous calcium chloride, and molecular P4O10.

COD CIFs retain original publication attribution, source revisions and file
digests. NIST/evaluated lattice-only records preserve the directly reported
parameters. `sources/crystals/` contains authored source documents and native
archives; [metal notes](crystals-metals.md) and
[molecular notes](crystals-molecular.md) describe selection and transformation.

## Rebuild and query

```powershell
python scripts/build_crystal_evidence.py
```

The builder verifies archived source digests, exact numeric representations,
units, space-group/crystal-system consistency, cell geometry, site occupancies,
foreign keys, and SQLite integrity. Builds replace the artifact atomically
and write `crystals.db.sha256`.

```sql
SELECT c.name, c.formula, c.phase, c.crystal_system,
       c.space_group_number, c.site_convention, s.url
FROM unverified_crystal_structure c
JOIN unverified_crystal_source s USING (source_id);

SELECT c.name, p.parameter, p.value_numerator, p.value_denominator,
       p.unit, p.uncertainty_numerator, p.uncertainty_denominator
FROM unverified_crystal_structure c
JOIN unverified_crystal_lattice_parameter p USING (structure_id);
```

Lengths use angstroms; angles use degrees. Values, uncertainties, coordinates,
occupancies, temperature and pressure use exact integer ratios. The original
authored source and site records are retained in `input_json`, including
coordinate uncertainties, source formulas, isotope/symmetry metadata and
source-specific notes. Published negative fractional coordinates are retained,
not silently wrapped into a different representation.

## Interpretation and remaining gaps

Asymmetric-unit sites are **not** a complete unit-cell atom list. Symmetry
expansion, occupancies, multiplicities and cell formula units need agreement
before a density calculation. Missing occupancies/multiplicities remain null;
no default full occupancy is invented. The [mixture calculator](mixtures.md)
requires explicitly valid integer cell contents and compatible conditions;
these research records are not automatically converted into density inputs.

Deuterated ice is preserved as an isotope-specific specimen. Site element H
with isotope mass number 2 is distinct from ordinary hydrogen; its formula and
metadata must not be passed to a natural-isotope mass calculation implicitly.
Hydrates, allotropes and high-temperature phases also retain distinct identity.

NIST sources that publish only a or a/c have incomplete measured metrics.
Symmetry-implied geometry appears only in separately labeled derived metadata,
not as additional measured lattice parameters. Existing authored bcc/fcc/
rocksalt prototypes in `sources/crystal_prototypes.json` remain ideal geometry,
without invented experimental lattice constants.

The research pass recorded 11 explicit gap/quality notes. A historical Ti CIF
with inconsistent cell content was excluded. Beta-Si3N4 has conflicting CIF/card
cell-formula counts; its count remains null. NaCl and suitable pure
tetragonal/cubic zirconia records still need research. Unknown temperature,
pressure, measurement method and specimen details remain unknown.

Release exports rebuild `crystals.db` and include its tables in both combined
`universe.db` and `universe-unverified.db`; the reviewed core crystal tables
remain empty until a source-specific admission review. Publication workflow
assets include the standalone database and checksum.
