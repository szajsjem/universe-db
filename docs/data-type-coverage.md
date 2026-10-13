# Scientific data-type coverage

This inventory complements the [record/context investigation](missing-data-investigation.md). It examines reviewed `universe.db` and the independent alloy, element, isotope, crystal, atomic electronic, spectral and molecular research databases. Merged release databases and Wikipedia snapshots are excluded to avoid counting the same evidence twice. It does not rereview sources or assert completeness for every entity.

Run `python scripts/audit_data_types.py --output .build/data-type-coverage.json` for current counts. Mapping vocabulary version: `scientific-types-2`. Unknown property identifiers appear in `unmapped_properties`. Core `property:` identifiers are normalized to the same vocabulary as staging.

| Data family | Reviewed rows | Staged rows | Current coverage |
|---|---:|---:|---|
| atomic electronic | 0 | 5847 | staged only |
| crystallography | 0 | 284 | staged only |
| elastic mechanical | 0 | 91 | staged only |
| kinetics | 0 | 0 | missing |
| magnetic optical | 0 | 0 | missing |
| mass composition | 735 | 7198 | reviewed present |
| molecular graphs | 0 | 207 | staged only |
| nuclear cross sections | 0 | 0 | missing |
| nuclear decay | 0 | 5671 | staged only |
| nuclear lifetime spin | 0 | 11033 | staged only |
| nuclear mass energy | 0 | 15212 | staged only |
| nuclear radii | 0 | 0 | missing |
| phonons diffraction | 0 | 0 | missing |
| spectra | 0 | 1871 | staged only |
| thermodynamics | 58 | 213 | reviewed present |
| transport | 0 | 60 | staged only |

Counts are rows, not independent experiments: crystal parent records, lattice parameters and sites are separate rows. A family containing some values can still lack most entities, temperature/pressure coverage, uncertainties and source review.

## Missing data types and representational gaps

- **Spectroscopy:** reviewed spectra, sampled points and spectral features remain empty. Staged NIST strong-line lists now supply 1,871 lines for 16 elements, with air/vacuum and ion stages retained. These are line lists, not measured continuous spectral curves or gamma photon yields. Existing generic tables support axes, intensities, resolution, conditions and feature positions. Additional missing content includes resolved upper/lower transition assignments, rotational/vibrational spectra, IR/Raman/UV-visible/NMR/EPR, isotope shifts and hyperfine structure. Dedicated transition upper/lower states, line strengths, per-line widths, instrument calibration and response functions need explicit schema or typed property extensions.
- **Molecular structure/electronic information:** reviewed molecular graph/atom/bond rows remain empty. Staged PubChem evidence now supplies 19 graphs, 103 explicit atoms and 85 bonds; atomic electronic evidence supplies 5,847 evaluated or modeled ionization energies for 6,019 states. Experimental conformers and geometry, broad normalized stereochemistry coverage, orbitals, resolved electronic excitation energies, electron affinities and polarizabilities remain absent from the mapped observations. Source ground-state configuration/level labels are retained separately; they do not provide measured orbital populations. Formula-derived molar mass does not provide these quantities.
- **Nuclear reactions and structure:** core channel and energy/velocity cross-section tables are empty. Source-native decay text is staged; it is not equivalent to reviewed branch probabilities, complete daughter-state assignments or gamma transition intensities. Nuclear radii, magnetic dipole/electric quadrupole moments and evaluated reaction yields are absent from the mapped observations. Nuclear-normalization JSON sidecars retain typed subsets but are intentionally not double counted as DB evidence.
- **Crystal dynamics and experimental diffraction:** staged unit-cell/site evidence exists, while reviewed crystal tables are empty. No mapped phonon dispersions/frequencies, diffraction intensities or structure factors. Disorder, anisotropic displacement tensors, defects, texture/orientation and validated full-cell occupancy remain source/model-specific gaps.
- **Thermodynamics, transport and mechanics:** selected density, heat capacity, transition temperatures, conductivity/resistivity and mechanical scalars are staged. Enthalpy/entropy/free energy, phase diagrams, mixing activities, diffusivity, viscosity, fatigue/creep and fracture toughness remain absent from the vocabulary queried here. Alloy grade identities are not property measurements.
- **Magnetic and optical response:** no mapped magnetization/susceptibility, Curie temperature, refractive index, dielectric response, band gap or optical absorption observations.
- **Kinetics:** reaction identities/stoichiometry exist, but no mapped rate constants, activation energies or reaction orders. Equilibrium constants and reaction conditions require a separate evidence design.

## Evidence versus calculation

The existing calculator derives exact formula masses and explicitly modeled mixture estimates; alloy and nuclear mass fits interpolate selected training observations. Crystal cell tooling checks/expands supported source conventions. These capabilities do not fill missing experimental spectra, decay channels, phase diagrams or magnetic/optical evidence. New half-life and decay-mode fits are predictive models, not substitutes for observed nuclear branches.

Generic `observation` storage can be extended with new property definitions; `no_dedicated_schema` means this mapping found no dedicated table or defined property, not that SQLite cannot store the quantity. Raw CIF/JSON source details may be richer than normalized columns. Missing source context and admissibility are reported by the separate investigation.

The 2026-10-13 additions are described in [atomic electronic evidence](atomic-evidence.md), [spectral evidence](spectral-evidence.md) and [molecular graphs](molecular-evidence.md). All remain pending source review and canonical admission.
