# Nuclear evidence normalization

`scripts/normalize_nuclear_properties.py` reads NUBASE2020 observations from
`isotopes.db` and writes a separate deterministic JSON staging report. It does
not promote evidence or populate reviewed nuclear channels.

```powershell
python scripts/normalize_nuclear_properties.py --database isotopes.db --output .build/nuclear-normalized.json
```

The report includes the input SHA-256, original source metadata, all NUBASE state
identities and withdrawn assignment flags, observation IDs, source locators,
source-native records, review status, typed records, and unsupported syntax gaps.
Values are decimal-encoded integer numerator/denominator pairs. Half-life units
use the importer's exact conversion factors, including a tropical year of
31,556,926 seconds. Point values and strict bounds remain distinct. Symmetric
and explicit `+upper-lower` uncertainties are retained separately; unfamiliar
uncertainty qualifiers remain visible as gaps beside the source value.

The 2026-10-12 correction replaces the previous Julian-year transformation
for 149 year-denominated NUBASE half-life rows. It follows the publication's
31,556,926-second convention; its separately displayed 365.2422-day value is
rounded and is not asserted to be exactly equivalent. Raw source values and
source SHA-256 are unchanged. `isotopes.db` and its checksum are rebuilt from
the corrected transformation. Existing versioned release bundles remain
historical outputs; rebuild a new version to include the correction.

Only single unparenthesized spin/parity assignments are normalized. Alternatives,
parenthesized tentative assignments and unspecified parity remain text gaps.
The source `*` and `#` assignment flags remain explicit. A stable assignment
never becomes an infinite or zero numeric half-life.

The decay parser accepts explicit simple beta-minus, beta-plus, electron capture,
alpha, one/two neutron and one/two proton mode tokens with a supplied decimal
percentage and `=`, `<`, or `>` relation. Percentages become exact fractions;
branches are never renormalized. Daughter atomic and mass numbers are derived
from that mode's conservation bookkeeping, while daughter state remains unknown.
These records are incomplete channels: emitted-particle identities, energies,
selection rules and daughter excitation are not inferred. Combined/delayed
modes, spontaneous fission, isomeric transitions, branch uncertainty syntax and
natural abundance (`IS`) entries remain explicit gaps. State indices are retained
without claiming every nonzero index is an experimentally established isomer.

NUBASE `B+` is the combined positron-emission **or electron-capture** intensity,
not a separated positron probability. Beta intensities can include subsequent
delayed-particle emission; their primary daughters need not be final residual
nuclei. The normalizer records these semantics and never guarantees disjoint
branches. See [NUBASE2020 section 2.5](https://www-nds.iaea.org/amdc/ame2020/NUBASE2020.pdf#page=11).
An internal-transition fraction also cannot stand in for gamma-photon yield;
resolved radiation and conversion data require a separate source.

This transform retains the original curated provenance and pending human review
status. Passing parser tests establishes reproducibility and guards against
fabrication; it does not scientifically approve the upstream evaluation.
