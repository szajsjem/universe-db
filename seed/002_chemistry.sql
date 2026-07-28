CREATE TEMP TABLE seed_element(
    entity_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    atomic_number INTEGER NOT NULL,
    atomic_mass_micrograms_per_mole INTEGER NOT NULL
) STRICT;

INSERT INTO seed_element VALUES
    ('element:hydrogen', 'hydrogen', 'H', 1, 1007940),
    ('element:carbon', 'carbon', 'C', 6, 12010700),
    ('element:oxygen', 'oxygen', 'O', 8, 15999400),
    ('element:fluorine', 'fluorine', 'F', 9, 18998403),
    ('element:sodium', 'sodium', 'Na', 11, 22989769),
    ('element:aluminum', 'aluminum', 'Al', 13, 26981538),
    ('element:silicon', 'silicon', 'Si', 14, 28085500),
    ('element:sulfur', 'sulfur', 'S', 16, 32065000),
    ('element:chlorine', 'chlorine', 'Cl', 17, 35453000),
    ('element:calcium', 'calcium', 'Ca', 20, 40078000),
    ('element:vanadium', 'vanadium', 'V', 23, 50941500),
    ('element:iron', 'iron', 'Fe', 26, 55845000),
    ('element:nickel', 'nickel', 'Ni', 28, 58693400),
    ('element:copper', 'copper', 'Cu', 29, 63546000),
    ('element:zinc', 'zinc', 'Zn', 30, 65380000),
    ('element:lead', 'lead', 'Pb', 82, 207200000);

INSERT INTO entity(
    entity_id, entity_type, name, dataset_id, lifecycle_state, schema_version
)
SELECT
    entity_id, 'element', name, 'dataset:inorganic-engineering-bootstrap',
    'active', 1
FROM seed_element ORDER BY atomic_number;

INSERT INTO element(entity_id, atomic_number, symbol)
SELECT entity_id, atomic_number, symbol
FROM seed_element ORDER BY atomic_number;

INSERT INTO observation(
    observation_id, subject_entity_id, property_id, value_numerator,
    value_denominator, unit_id, provenance_class, dataset_id, source_id,
    schema_version
)
SELECT
    'observation:atomic_mass:' || substr(entity_id, 9),
    entity_id,
    'property:atomic_mass',
    atomic_mass_micrograms_per_mole,
    1,
    'unit:microgram_per_mole',
    'curated',
    'dataset:inorganic-engineering-bootstrap',
    'inorganic-engineering-af5a553',
    1
FROM seed_element ORDER BY atomic_number;

DROP TABLE seed_element;

CREATE TEMP TABLE seed_species(
    entity_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    species_kind TEXT NOT NULL,
    formula TEXT NOT NULL,
    electric_charge INTEGER NOT NULL,
    molar_mass INTEGER NOT NULL,
    density INTEGER NOT NULL,
    heat_capacity INTEGER NOT NULL,
    melting_point INTEGER,
    boiling_point INTEGER
) STRICT;

INSERT INTO seed_species VALUES
    ('chem:calcite', 'calcite', 'formula_unit', 'CaCO3', 0, 100086900, 2710000, 820000, NULL, NULL),
    ('chem:chalcopyrite', 'chalcopyrite', 'formula_unit', 'CuFeS2', 0, 183521000, 4200000, 550000, NULL, NULL),
    ('chem:copper', 'copper', 'atom', 'Cu', 0, 63546000, 8960000, 385000, 1357770, 2835150),
    ('chem:copper_oxide', 'copper(II) oxide', 'formula_unit', 'CuO', 0, 79545400, 6310000, 535000, NULL, NULL),
    ('chem:copper_sulfate', 'copper(II) sulfate', 'formula_unit', 'CuSO4', 0, 159608600, 3600000, 1000000, NULL, NULL),
    ('chem:coulsonite', 'coulsonite', 'formula_unit', 'FeV2O4', 0, 221725600, 5150000, 650000, NULL, NULL),
    ('chem:fluorite', 'fluorite', 'formula_unit', 'CaF2', 0, 78074806, 3180000, 853000, NULL, NULL),
    ('chem:galena', 'galena', 'formula_unit', 'PbS', 0, 239265000, 7600000, 207000, NULL, NULL),
    ('chem:gibbsite', 'gibbsite', 'formula_unit', 'Al(OH)3', 0, 78003558, 2420000, 1100000, NULL, NULL),
    ('chem:halite', 'halite', 'formula_unit', 'NaCl', 0, 58442769, 2165000, 864000, NULL, NULL),
    ('chem:hematite', 'hematite', 'formula_unit', 'Fe2O3', 0, 159688200, 5260000, 650000, NULL, NULL),
    ('chem:hydrogen', 'hydrogen', 'molecule', 'H2', 0, 2015880, 90, 14304000, NULL, NULL),
    ('chem:hydrogen_ion', 'hydrogen ion', 'ion', 'H+', 1, 1007940, 0, 0, NULL, NULL),
    ('chem:hydroxide', 'hydroxide', 'ion', 'OH-', -1, 17007340, 0, 0, NULL, NULL),
    ('chem:iron', 'iron', 'atom', 'Fe', 0, 55845000, 7874000, 449000, 1811000, 3134000),
    ('chem:magnetite', 'magnetite', 'formula_unit', 'Fe3O4', 0, 231532600, 5170000, 650000, NULL, NULL),
    ('chem:oxygen', 'oxygen', 'molecule', 'O2', 0, 31998800, 1429, 918000, NULL, NULL),
    ('chem:pentlandite', 'pentlandite', 'formula_unit', 'Fe4Ni5S8', 0, 773367000, 4800000, 550000, NULL, NULL),
    ('chem:pyrite', 'pyrite', 'formula_unit', 'FeS2', 0, 119975000, 5010000, 710000, NULL, NULL),
    ('chem:quartz', 'quartz', 'formula_unit', 'SiO2', 0, 60084300, 2650000, 730000, 1986000, NULL),
    ('chem:sphalerite', 'sphalerite', 'formula_unit', 'ZnS', 0, 97445000, 4040000, 480000, NULL, NULL),
    ('chem:sulfur_dioxide', 'sulfur dioxide', 'molecule', 'SO2', 0, 64063800, 2628, 640000, NULL, 263050),
    ('chem:sulfuric_acid', 'sulfuric acid', 'molecule', 'H2SO4', 0, 98078480, 1830000, 1380000, NULL, NULL),
    ('chem:unresolved_trace', 'unresolved trace', 'unresolved', '?', 0, 0, 0, 0, NULL, NULL),
    ('chem:water', 'water', 'molecule', 'H2O', 0, 18015280, 1000000, 4184000, 273150, 373150);

INSERT INTO entity(
    entity_id, entity_type, name, dataset_id, lifecycle_state, schema_version
)
SELECT
    entity_id, 'chemical_species', name,
    'dataset:inorganic-engineering-bootstrap', 'active', 1
FROM seed_species ORDER BY entity_id;

INSERT INTO chemical_species(entity_id, species_kind, formula, electric_charge)
SELECT entity_id, species_kind, formula, electric_charge
FROM seed_species ORDER BY entity_id;

INSERT INTO observation(
    observation_id, subject_entity_id, property_id, value_numerator,
    value_denominator, unit_id, provenance_class, dataset_id, source_id,
    schema_version
)
SELECT
    'observation:molar_mass:' || substr(entity_id, 6), entity_id,
    'property:molar_mass', molar_mass, 1, 'unit:microgram_per_mole',
    'curated', 'dataset:inorganic-engineering-bootstrap',
    'inorganic-engineering-af5a553', 1
FROM seed_species ORDER BY entity_id;

INSERT INTO observation(
    observation_id, subject_entity_id, property_id, value_numerator,
    value_denominator, unit_id, provenance_class, dataset_id, source_id,
    schema_version
)
SELECT
    'observation:density:' || substr(entity_id, 6), entity_id,
    'property:density', density, 1, 'unit:milligram_per_litre',
    'curated', 'dataset:inorganic-engineering-bootstrap',
    'inorganic-engineering-af5a553', 1
FROM seed_species ORDER BY entity_id;

INSERT INTO observation(
    observation_id, subject_entity_id, property_id, value_numerator,
    value_denominator, unit_id, provenance_class, dataset_id, source_id,
    schema_version
)
SELECT
    'observation:heat_capacity:' || substr(entity_id, 6), entity_id,
    'property:specific_heat_capacity', heat_capacity, 1,
    'unit:microjoule_per_gram_kelvin', 'curated',
    'dataset:inorganic-engineering-bootstrap',
    'inorganic-engineering-af5a553', 1
FROM seed_species ORDER BY entity_id;

INSERT INTO observation(
    observation_id, subject_entity_id, property_id, value_numerator,
    value_denominator, unit_id, provenance_class, dataset_id, source_id,
    schema_version
)
SELECT
    'observation:melting_point:' || substr(entity_id, 6), entity_id,
    'property:melting_point', melting_point, 1, 'unit:millikelvin',
    'curated', 'dataset:inorganic-engineering-bootstrap',
    'inorganic-engineering-af5a553', 1
FROM seed_species WHERE melting_point IS NOT NULL ORDER BY entity_id;

INSERT INTO observation(
    observation_id, subject_entity_id, property_id, value_numerator,
    value_denominator, unit_id, provenance_class, dataset_id, source_id,
    schema_version
)
SELECT
    'observation:boiling_point:' || substr(entity_id, 6), entity_id,
    'property:boiling_point', boiling_point, 1, 'unit:millikelvin',
    'curated', 'dataset:inorganic-engineering-bootstrap',
    'inorganic-engineering-af5a553', 1
FROM seed_species WHERE boiling_point IS NOT NULL ORDER BY entity_id;

DROP TABLE seed_species;

INSERT INTO species_element(species_id, element_id, atom_count) VALUES
    ('chem:calcite', 'element:calcium', 1),
    ('chem:calcite', 'element:carbon', 1),
    ('chem:calcite', 'element:oxygen', 3),
    ('chem:chalcopyrite', 'element:copper', 1),
    ('chem:chalcopyrite', 'element:iron', 1),
    ('chem:chalcopyrite', 'element:sulfur', 2),
    ('chem:copper', 'element:copper', 1),
    ('chem:copper_oxide', 'element:copper', 1),
    ('chem:copper_oxide', 'element:oxygen', 1),
    ('chem:copper_sulfate', 'element:copper', 1),
    ('chem:copper_sulfate', 'element:oxygen', 4),
    ('chem:copper_sulfate', 'element:sulfur', 1),
    ('chem:coulsonite', 'element:iron', 1),
    ('chem:coulsonite', 'element:oxygen', 4),
    ('chem:coulsonite', 'element:vanadium', 2),
    ('chem:fluorite', 'element:calcium', 1),
    ('chem:fluorite', 'element:fluorine', 2),
    ('chem:galena', 'element:lead', 1),
    ('chem:galena', 'element:sulfur', 1),
    ('chem:gibbsite', 'element:aluminum', 1),
    ('chem:gibbsite', 'element:hydrogen', 3),
    ('chem:gibbsite', 'element:oxygen', 3),
    ('chem:halite', 'element:chlorine', 1),
    ('chem:halite', 'element:sodium', 1),
    ('chem:hematite', 'element:iron', 2),
    ('chem:hematite', 'element:oxygen', 3),
    ('chem:hydrogen', 'element:hydrogen', 2),
    ('chem:hydrogen_ion', 'element:hydrogen', 1),
    ('chem:hydroxide', 'element:hydrogen', 1),
    ('chem:hydroxide', 'element:oxygen', 1),
    ('chem:iron', 'element:iron', 1),
    ('chem:magnetite', 'element:iron', 3),
    ('chem:magnetite', 'element:oxygen', 4),
    ('chem:oxygen', 'element:oxygen', 2),
    ('chem:pentlandite', 'element:iron', 4),
    ('chem:pentlandite', 'element:nickel', 5),
    ('chem:pentlandite', 'element:sulfur', 8),
    ('chem:pyrite', 'element:iron', 1),
    ('chem:pyrite', 'element:sulfur', 2),
    ('chem:quartz', 'element:oxygen', 2),
    ('chem:quartz', 'element:silicon', 1),
    ('chem:sphalerite', 'element:sulfur', 1),
    ('chem:sphalerite', 'element:zinc', 1),
    ('chem:sulfur_dioxide', 'element:oxygen', 2),
    ('chem:sulfur_dioxide', 'element:sulfur', 1),
    ('chem:sulfuric_acid', 'element:hydrogen', 2),
    ('chem:sulfuric_acid', 'element:oxygen', 4),
    ('chem:sulfuric_acid', 'element:sulfur', 1),
    ('chem:water', 'element:hydrogen', 2),
    ('chem:water', 'element:oxygen', 1);

INSERT INTO species_phase(species_id, phase_id, condition_set_id, dataset_id) VALUES
    ('chem:calcite', 'phase:solid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:chalcopyrite', 'phase:solid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:copper', 'phase:solid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:copper', 'phase:molten', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:copper', 'phase:gas', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:copper_oxide', 'phase:solid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:copper_sulfate', 'phase:solid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:copper_sulfate', 'phase:aqueous', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:coulsonite', 'phase:solid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:fluorite', 'phase:solid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:galena', 'phase:solid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:gibbsite', 'phase:solid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:halite', 'phase:solid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:halite', 'phase:aqueous', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:hematite', 'phase:solid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:hydrogen', 'phase:gas', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:hydrogen_ion', 'phase:aqueous', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:hydroxide', 'phase:aqueous', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:iron', 'phase:solid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:iron', 'phase:molten', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:iron', 'phase:gas', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:magnetite', 'phase:solid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:oxygen', 'phase:gas', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:pentlandite', 'phase:solid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:pyrite', 'phase:solid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:quartz', 'phase:solid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:quartz', 'phase:molten', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:sphalerite', 'phase:solid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:sulfur_dioxide', 'phase:liquid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:sulfur_dioxide', 'phase:aqueous', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:sulfur_dioxide', 'phase:gas', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:sulfuric_acid', 'phase:liquid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:sulfuric_acid', 'phase:aqueous', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:unresolved_trace', 'phase:solid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:unresolved_trace', 'phase:liquid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:unresolved_trace', 'phase:aqueous', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:unresolved_trace', 'phase:gas', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:unresolved_trace', 'phase:molten', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:unresolved_trace', 'phase:slurry', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:water', 'phase:solid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:water', 'phase:liquid', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:water', 'phase:aqueous', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap'),
    ('chem:water', 'phase:gas', 'condition:unspecified', 'dataset:inorganic-engineering-bootstrap');
