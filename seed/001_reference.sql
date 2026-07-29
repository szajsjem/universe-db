INSERT INTO database_metadata(key, value) VALUES
    ('title', 'Universe Database'),
    ('schema_version', '5'),
    ('data_policy', 'No invented values; missing data remains absent'),
    ('artifact', 'universe.db');

INSERT INTO license(
    license_id, name, spdx_id, url, redistribution_allowed, notes
) VALUES
    (
        'mit',
        'MIT License',
        'MIT',
        'https://opensource.org/license/mit',
        1,
        'Applies to original schema, scripts, and the Inorganic Engineering bootstrap data.'
    ),
    (
        'cc-by-4.0',
        'Creative Commons Attribution 4.0 International',
        'CC-BY-4.0',
        'https://creativecommons.org/licenses/by/4.0/',
        1,
        'Attribution is required.'
    ),
    (
        'cc-by-sa-4.0',
        'Creative Commons Attribution-ShareAlike 4.0 International',
        'CC-BY-SA-4.0',
        'https://creativecommons.org/licenses/by-sa/4.0/',
        1,
        'Attribution and ShareAlike are required. Wikipedia page snapshots retain permanent revision URLs for contributor attribution.'
    ),
    (
        'pubchem-no-restriction',
        'PubChem-generated information availability terms',
        NULL,
        'https://pubchem.ncbi.nlm.nih.gov/docs/data-submission-policy',
        1,
        'PubChem-generated information is made available without cost and without restriction; contributor-specific content can have separate terms.'
    ),
    (
        'nist-public-information',
        'NIST public information reuse terms',
        NULL,
        'https://www.nist.gov/copyrights-disclaimers',
        1,
        'Unmarked NIST website information may be distributed or copied; attribution is requested. Database disclaimers apply.'
    );

INSERT INTO source(
    source_id, title, citation, url, license_id, accessed_on
) VALUES
    (
        'inorganic-engineering-af5a553',
        'Inorganic Engineering generated chemistry catalog',
        'szajsjem, Inorganic Engineering, commit af5a553, generated element/species/mineral/material/reaction resources.',
        'https://github.com/szajsjem/icm/tree/af5a553',
        'mit',
        '2026-07-28'
    ),
    (
        'pdg-rpp-2024',
        '2024 Review of Particle Physics',
        'S. Navas et al. (Particle Data Group), Phys. Rev. D 110, 030001 (2024).',
        'https://pdg.lbl.gov/2024/',
        'cc-by-4.0',
        '2026-07-28'
    ),
    (
        'pubchem-periodic-table-2026-07-28',
        'PubChem Periodic Table',
        'National Library of Medicine, PubChem Periodic Table, PUG REST periodic-table JSON snapshot retrieved 2026-07-28.',
        'https://pubchem.ncbi.nlm.nih.gov/rest/pug/periodictable/JSON',
        'pubchem-no-restriction',
        '2026-07-28'
    ),
    (
        'nist-isotopic-compositions-2026-07-28',
        'NIST Atomic Weights and Isotopic Compositions',
        'J. S. Coursey, D. J. Schwab, and R. A. Dragoset, NIST Atomic Weights and Isotopic Compositions with Relative Atomic Masses, snapshot retrieved 2026-07-28.',
        'https://physics.nist.gov/PhysRefData/Compositions/index.html',
        'nist-public-information',
        '2026-07-28'
    ),
    (
        'wikipedia-chemistry-category-snapshot-2026-07-29',
        'English Wikipedia chemistry category snapshot',
        'English Wikipedia revision-pinned category snapshot, 1,239 pages retrieved 2026-07-29; archive SHA-256 c1b4db37964c497f901343c706019324eac204af2973b9aaff71c24f781cdf29.',
        'https://en.wikipedia.org/',
        'cc-by-sa-4.0',
        '2026-07-29'
    ),
    (
        'kiwix-wikipedia-en-chemistry-mini-2026-07',
        'Kiwix English Wikipedia chemistry mini release',
        'Official Kiwix English Wikipedia chemistry mini ZIM, July 2026; SHA-256 0a7f1e35b1f0deee19c68014421754ce42310bcf6cd8e8d3f01fad25a5ab6144.',
        'https://download.kiwix.org/zim/wikipedia/wikipedia_en_chemistry_mini_2026-07.zim',
        'cc-by-sa-4.0',
        '2026-07-29'
    );

INSERT INTO dataset(
    dataset_id, title, version, source_id, provenance_class,
    schema_version, notes
) VALUES
    (
        'dataset:inorganic-engineering-bootstrap',
        'Inorganic Engineering bootstrap catalog',
        'af5a553',
        'inorganic-engineering-af5a553',
        'curated',
        1,
        'Small authored gameplay catalog. Values are retained as curated source observations, not relabeled as laboratory measurements.'
    ),
    (
        'dataset:standard-model-identities',
        'Standard Model matter-particle identities',
        'RPP 2024',
        'pdg-rpp-2024',
        'curated',
        1,
        'Identity, family, symbol, and exact charge only; no masses or lifetimes.'
    ),
    (
        'dataset:pubchem-periodic-table-2026-07-28',
        'PubChem Periodic Table',
        '2026-07-28 snapshot',
        'pubchem-periodic-table-2026-07-28',
        'curated',
        2,
        'All 118 element identities plus PubChem AtomicMass, group classification, electron configuration, and standard-state fields.'
    ),
    (
        'dataset:nist-natural-isotopes-2026-07-28',
        'NIST representative natural isotopic compositions',
        '2026-07-28 snapshot',
        'nist-isotopic-compositions-2026-07-28',
        'curated',
        3,
        'Nuclides with a non-empty representative isotopic-composition field. Trace-only and synthetic nuclides are not selected as common.'
    );

INSERT INTO unit(
    unit_id, symbol, quantity_kind, si_scale_numerator, si_scale_denominator,
    si_scale_power10, si_offset_numerator, si_offset_denominator
) VALUES
    ('unit:one', '1', 'dimensionless', 1, 1, 0, 0, 1),
    ('unit:microgram_per_mole', 'µg/mol', 'molar_mass', 1, 1000000000, 0, 0, 1),
    ('unit:milligram_per_litre', 'mg/L', 'density', 1, 1000, 0, 0, 1),
    ('unit:microjoule_per_gram_kelvin', 'µJ/(g·K)', 'specific_heat_capacity', 1, 1000, 0, 0, 1),
    ('unit:millikelvin', 'mK', 'temperature', 1, 1000, 0, 0, 1),
    ('unit:kelvin', 'K', 'temperature', 1, 1, 0, 0, 1),
    ('unit:pascal', 'Pa', 'pressure', 1, 1, 0, 0, 1),
    ('unit:metre_per_second', 'm/s', 'speed', 1, 1, 0, 0, 1),
    ('unit:second', 's', 'time', 1, 1, 0, 0, 1),
    ('unit:joule', 'J', 'energy', 1, 1, 0, 0, 1),
    ('unit:electronvolt', 'eV', 'energy', 1602176634, 1, -28, 0, 1),
    ('unit:nanometre', 'nm', 'length', 1, 1000000000, 0, 0, 1),
    ('unit:reciprocal_centimetre', 'cm⁻¹', 'wavenumber', 100, 1, 0, 0, 1),
    ('unit:arbitrary', 'a.u.', 'relative_intensity', 1, 1, 0, 0, 1),
    ('unit:barn', 'b', 'cross_section', 1, 1, -28, 0, 1);

INSERT INTO phase(phase_id, name) VALUES
    ('phase:solid', 'solid'),
    ('phase:liquid', 'liquid'),
    ('phase:aqueous', 'aqueous solution'),
    ('phase:gas', 'gas'),
    ('phase:molten', 'molten'),
    ('phase:slurry', 'slurry');

INSERT INTO crystal_system(crystal_system_id, name) VALUES
    ('crystal:triclinic', 'triclinic'),
    ('crystal:monoclinic', 'monoclinic'),
    ('crystal:orthorhombic', 'orthorhombic'),
    ('crystal:tetragonal', 'tetragonal'),
    ('crystal:trigonal', 'trigonal'),
    ('crystal:hexagonal', 'hexagonal'),
    ('crystal:cubic', 'cubic');

INSERT INTO condition_set(condition_set_id, description) VALUES
    (
        'condition:unspecified',
        'The source did not author the applicable conditions; this is not a standard-state claim.'
    ),
    (
        'condition:nist_representative_terrestrial_composition',
        'Representative terrestrial isotopic composition as defined by the NIST source; geological, commercial, or modified samples can differ.'
    );

INSERT INTO property_definition(
    property_id, name, quantity_kind, canonical_unit_id
) VALUES
    ('property:atomic_mass', 'atomic mass per mole', 'molar_mass', 'unit:microgram_per_mole'),
    (
        'property:relative_atomic_mass',
        'relative atomic mass',
        'dimensionless',
        'unit:one'
    ),
    (
        'property:isotopic_composition',
        'representative isotopic composition',
        'dimensionless',
        'unit:one'
    ),
    ('property:molar_mass', 'molar mass', 'molar_mass', 'unit:microgram_per_mole'),
    ('property:density', 'density', 'density', 'unit:milligram_per_litre'),
    (
        'property:specific_heat_capacity',
        'specific heat capacity',
        'specific_heat_capacity',
        'unit:microjoule_per_gram_kelvin'
    ),
    ('property:melting_point', 'melting point', 'temperature', 'unit:millikelvin'),
    ('property:boiling_point', 'boiling point', 'temperature', 'unit:millikelvin'),
    (
        'property:electronegativity',
        'electronegativity',
        'dimensionless',
        'unit:one'
    ),
    ('property:nuclear_spin', 'nuclear spin', 'dimensionless', 'unit:one'),
    ('property:half_life', 'half-life', 'time', 'unit:second'),
    (
        'property:mass_excess_energy',
        'mass excess energy',
        'energy',
        'unit:electronvolt'
    ),
    (
        'property:nuclear_binding_energy',
        'nuclear binding energy',
        'energy',
        'unit:electronvolt'
    ),
    (
        'property:nuclear_binding_energy_per_nucleon',
        'nuclear binding energy per nucleon',
        'energy',
        'unit:electronvolt'
    );

CREATE TEMP TABLE seed_particle(
    entity_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    family TEXT NOT NULL,
    symbol TEXT NOT NULL,
    charge_numerator INTEGER NOT NULL,
    charge_denominator INTEGER NOT NULL,
    baryon_numerator INTEGER NOT NULL,
    baryon_denominator INTEGER NOT NULL,
    lepton_number INTEGER NOT NULL
) STRICT;

INSERT INTO seed_particle VALUES
    ('particle:up', 'up quark', 'quark', 'u', 2, 3, 1, 3, 0),
    ('particle:down', 'down quark', 'quark', 'd', -1, 3, 1, 3, 0),
    ('particle:charm', 'charm quark', 'quark', 'c', 2, 3, 1, 3, 0),
    ('particle:strange', 'strange quark', 'quark', 's', -1, 3, 1, 3, 0),
    ('particle:top', 'top quark', 'quark', 't', 2, 3, 1, 3, 0),
    ('particle:bottom', 'bottom quark', 'quark', 'b', -1, 3, 1, 3, 0),
    ('particle:electron', 'electron', 'lepton', 'e⁻', -1, 1, 0, 1, 1),
    ('particle:electron_neutrino', 'electron neutrino', 'lepton', 'νe', 0, 1, 0, 1, 1),
    ('particle:muon', 'muon', 'lepton', 'μ⁻', -1, 1, 0, 1, 1),
    ('particle:muon_neutrino', 'muon neutrino', 'lepton', 'νμ', 0, 1, 0, 1, 1),
    ('particle:tau', 'tau', 'lepton', 'τ⁻', -1, 1, 0, 1, 1),
    ('particle:tau_neutrino', 'tau neutrino', 'lepton', 'ντ', 0, 1, 0, 1, 1);

INSERT INTO entity(
    entity_id, entity_type, name, dataset_id, lifecycle_state, schema_version
)
SELECT
    entity_id, 'particle', name, 'dataset:standard-model-identities', 'active', 1
FROM seed_particle ORDER BY entity_id;

INSERT INTO particle(
    entity_id, family, symbol, electric_charge_numerator,
    electric_charge_denominator, baryon_number_numerator,
    baryon_number_denominator, lepton_number
)
SELECT
    entity_id, family, symbol, charge_numerator, charge_denominator,
    baryon_numerator, baryon_denominator, lepton_number
FROM seed_particle ORDER BY entity_id;

DROP TABLE seed_particle;
