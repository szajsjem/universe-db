# Molecular graph evidence

`molecules.db` stages 19 PubChem factual molecular graphs: all ten existing core molecule identities, plus benzene, ethanol, methanol, acetone, acetic acid, methane, ammonia, heavy water and L-alanine. It contains 103 explicit atoms and 85 bonds. These records remain `pending_human_review`; core entity mappings are explicit candidate mappings rather than formula-based identity matches.

Sources are the [official PubChem PUG REST](https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest) compound JSON records, retrieved on 2026-10-13. Each response is pinned by SHA256 in `sources/molecules/manifest.json`; source URLs, available upstream property release labels, retrieval date and factual-data redistribution determination are stored with each graph. The snapshot extracts chemical identities and numerical structure facts, with no third-party prose. The source response is retained to reproduce the transformation.

```powershell
python scripts/build_molecular_evidence.py --output molecules.db
python -m unittest tests.test_molecular_evidence
```

The offline builder checks CID identity, explicit atom counts against both PubChem and authored reference formulas, formal-charge sums, unique atom IDs, bond endpoints and source hashes before replacing a database. Formula order differences such as `HCl`/`ClH` do not imply different identities. Hydrogen atoms are explicit in these source records.

Atom isotope labels, native radical codes and formal charges are retained. Stereo descriptors and the complete native graph (without coordinates) are retained as JSON; L-alanine provides a tetrahedral stereo example, heavy water preserves two isotope-2 hydrogen atoms, and carbon monoxide preserves its charge-separated representation. Bond orders retain PubChem integer codes: benzene's alternating bonds are not converted to an inferred aromatic representation. Absent radical annotations are NULL, rather than an invented radical state.

PubChem 2D depiction coordinates are deliberately omitted. They are not measured geometry, bond lengths or molecular spectra. Every graph has an explicit experimental-geometry gap. This corpus does not fill reaction kinetics, spectra, force-field parameters or experimental conformational ensembles.

All authoritative graph values are integers. The builder emits a deterministic SQLite file and its SHA256; rebuilding from identical snapshots produces identical database bytes. The tests cover invalid formulas/charges/endpoints, isotope/stereo preservation, checksum refusal and deterministic builds.
