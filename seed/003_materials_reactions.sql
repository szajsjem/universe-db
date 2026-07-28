CREATE TEMP TABLE seed_material(
    entity_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    material_kind TEXT NOT NULL
) STRICT;

INSERT INTO seed_material VALUES
    ('material:bauxite', 'bauxite ore', 'ore'),
    ('material:calcite_ore', 'calcite ore', 'ore'),
    ('material:chalcopyrite_ore', 'chalcopyrite ore', 'ore'),
    ('material:fluorite_ore', 'fluorite ore', 'ore'),
    ('material:galena_ore', 'galena ore', 'ore'),
    ('material:halite_ore', 'halite ore', 'ore'),
    ('material:hematite_ore', 'hematite ore', 'ore'),
    ('material:magnetite_ore', 'magnetite ore', 'ore'),
    ('material:pentlandite_ore', 'pentlandite ore', 'ore'),
    ('material:pyrite_ore', 'pyrite ore', 'ore'),
    ('material:sphalerite_ore', 'sphalerite ore', 'ore'),
    ('material:vanadiferous_magnetite', 'vanadiferous magnetite ore', 'ore'),
    ('material:cathode_copper', 'cathode copper', 'pure_substance');

INSERT INTO entity(
    entity_id, entity_type, name, dataset_id, lifecycle_state, schema_version
)
SELECT
    entity_id, 'material', name, 'dataset:inorganic-engineering-bootstrap',
    'active', 1
FROM seed_material ORDER BY entity_id;

INSERT INTO material(entity_id, material_kind)
SELECT entity_id, material_kind FROM seed_material ORDER BY entity_id;

DROP TABLE seed_material;

INSERT INTO material_component(
    material_id, species_id, amount_numerator, amount_denominator, basis, role
) VALUES
    ('material:bauxite', 'chem:gibbsite', NULL, NULL, 'unspecified', 'mineral'),
    ('material:bauxite', 'chem:quartz', NULL, NULL, 'unspecified', 'gangue'),
    ('material:calcite_ore', 'chem:calcite', NULL, NULL, 'unspecified', 'mineral'),
    ('material:calcite_ore', 'chem:quartz', NULL, NULL, 'unspecified', 'gangue'),
    ('material:chalcopyrite_ore', 'chem:chalcopyrite', NULL, NULL, 'unspecified', 'mineral'),
    ('material:chalcopyrite_ore', 'chem:quartz', NULL, NULL, 'unspecified', 'gangue'),
    ('material:fluorite_ore', 'chem:fluorite', NULL, NULL, 'unspecified', 'mineral'),
    ('material:fluorite_ore', 'chem:quartz', NULL, NULL, 'unspecified', 'gangue'),
    ('material:galena_ore', 'chem:galena', NULL, NULL, 'unspecified', 'mineral'),
    ('material:galena_ore', 'chem:quartz', NULL, NULL, 'unspecified', 'gangue'),
    ('material:halite_ore', 'chem:halite', NULL, NULL, 'unspecified', 'mineral'),
    ('material:halite_ore', 'chem:quartz', NULL, NULL, 'unspecified', 'gangue'),
    ('material:hematite_ore', 'chem:hematite', NULL, NULL, 'unspecified', 'mineral'),
    ('material:hematite_ore', 'chem:quartz', NULL, NULL, 'unspecified', 'gangue'),
    ('material:magnetite_ore', 'chem:magnetite', NULL, NULL, 'unspecified', 'mineral'),
    ('material:magnetite_ore', 'chem:quartz', NULL, NULL, 'unspecified', 'gangue'),
    ('material:pentlandite_ore', 'chem:pentlandite', NULL, NULL, 'unspecified', 'mineral'),
    ('material:pentlandite_ore', 'chem:quartz', NULL, NULL, 'unspecified', 'gangue'),
    ('material:pyrite_ore', 'chem:pyrite', NULL, NULL, 'unspecified', 'mineral'),
    ('material:pyrite_ore', 'chem:quartz', NULL, NULL, 'unspecified', 'gangue'),
    ('material:sphalerite_ore', 'chem:sphalerite', NULL, NULL, 'unspecified', 'mineral'),
    ('material:sphalerite_ore', 'chem:quartz', NULL, NULL, 'unspecified', 'gangue'),
    ('material:vanadiferous_magnetite', 'chem:coulsonite', NULL, NULL, 'unspecified', 'mineral'),
    ('material:vanadiferous_magnetite', 'chem:quartz', NULL, NULL, 'unspecified', 'gangue'),
    ('material:cathode_copper', 'chem:copper', 1, 1, 'mass_fraction', 'constituent');

INSERT INTO condition_set(condition_set_id, description) VALUES
    (
        'condition:chalcopyrite_roasting_range',
        'Authored process envelope: 800–1500 K and 0–2 MPa.'
    ),
    (
        'condition:copper_oxide_leaching_range',
        'Authored process envelope: 273.15–373.15 K and 90–200 kPa.'
    ),
    (
        'condition:copper_leachate_filtration_range',
        'Authored process envelope: 0–1500 K and 0–2 MPa.'
    );

INSERT INTO condition_value(
    condition_set_id, quantity_kind, value_numerator, value_denominator, unit_id
) VALUES
    ('condition:chalcopyrite_roasting_range', 'temperature_min', 800000, 1, 'unit:millikelvin'),
    ('condition:chalcopyrite_roasting_range', 'temperature_max', 1500000, 1, 'unit:millikelvin'),
    ('condition:chalcopyrite_roasting_range', 'pressure_min', 0, 1, 'unit:pascal'),
    ('condition:chalcopyrite_roasting_range', 'pressure_max', 2000000, 1, 'unit:pascal'),
    ('condition:copper_oxide_leaching_range', 'temperature_min', 273150, 1, 'unit:millikelvin'),
    ('condition:copper_oxide_leaching_range', 'temperature_max', 373150, 1, 'unit:millikelvin'),
    ('condition:copper_oxide_leaching_range', 'pressure_min', 90000, 1, 'unit:pascal'),
    ('condition:copper_oxide_leaching_range', 'pressure_max', 200000, 1, 'unit:pascal'),
    ('condition:copper_leachate_filtration_range', 'temperature_min', 0, 1, 'unit:millikelvin'),
    ('condition:copper_leachate_filtration_range', 'temperature_max', 1500000, 1, 'unit:millikelvin'),
    ('condition:copper_leachate_filtration_range', 'pressure_min', 0, 1, 'unit:pascal'),
    ('condition:copper_leachate_filtration_range', 'pressure_max', 2000000, 1, 'unit:pascal');

INSERT INTO reaction(
    reaction_id, reaction_kind, name, reversible, energy_change_numerator,
    energy_change_denominator, energy_unit_id, dataset_id, source_id,
    schema_version
) VALUES
    (
        'reaction:chalcopyrite_roasting', 'process', 'chalcopyrite roasting',
        0, 0, 1, 'unit:joule', 'dataset:inorganic-engineering-bootstrap',
        'inorganic-engineering-af5a553', 1
    ),
    (
        'reaction:copper_oxide_leaching', 'process', 'copper oxide leaching',
        0, 0, 1, 'unit:joule', 'dataset:inorganic-engineering-bootstrap',
        'inorganic-engineering-af5a553', 1
    ),
    (
        'reaction:copper_leachate_filtration', 'process', 'copper leachate filtration',
        0, 0, 1, 'unit:joule', 'dataset:inorganic-engineering-bootstrap',
        'inorganic-engineering-af5a553', 1
    );

INSERT INTO reaction_participant(
    reaction_id, role, species_id, phase_id,
    coefficient_numerator, coefficient_denominator
) VALUES
    ('reaction:chalcopyrite_roasting', 'reactant', 'chem:chalcopyrite', 'phase:solid', 4, 1),
    ('reaction:chalcopyrite_roasting', 'reactant', 'chem:oxygen', 'phase:gas', 13, 1),
    ('reaction:chalcopyrite_roasting', 'product', 'chem:copper_oxide', 'phase:solid', 4, 1),
    ('reaction:chalcopyrite_roasting', 'product', 'chem:hematite', 'phase:solid', 2, 1),
    ('reaction:chalcopyrite_roasting', 'product', 'chem:sulfur_dioxide', 'phase:gas', 8, 1),
    ('reaction:copper_oxide_leaching', 'reactant', 'chem:copper_oxide', 'phase:solid', 1, 1),
    ('reaction:copper_oxide_leaching', 'reactant', 'chem:sulfuric_acid', 'phase:aqueous', 1, 1),
    ('reaction:copper_oxide_leaching', 'product', 'chem:copper_sulfate', 'phase:aqueous', 1, 1),
    ('reaction:copper_oxide_leaching', 'product', 'chem:water', 'phase:aqueous', 1, 1),
    ('reaction:copper_leachate_filtration', 'reactant', 'chem:copper_sulfate', 'phase:aqueous', 2, 1),
    ('reaction:copper_leachate_filtration', 'reactant', 'chem:water', 'phase:aqueous', 2, 1),
    ('reaction:copper_leachate_filtration', 'reactant', 'chem:hematite', 'phase:solid', 1, 1),
    ('reaction:copper_leachate_filtration', 'product', 'chem:copper_sulfate', 'phase:aqueous', 2, 1),
    ('reaction:copper_leachate_filtration', 'product', 'chem:water', 'phase:aqueous', 2, 1),
    ('reaction:copper_leachate_filtration', 'product', 'chem:hematite', 'phase:solid', 1, 1);

INSERT INTO reaction_condition(reaction_id, condition_set_id, relationship) VALUES
    (
        'reaction:chalcopyrite_roasting',
        'condition:chalcopyrite_roasting_range',
        'valid_range'
    ),
    (
        'reaction:copper_oxide_leaching',
        'condition:copper_oxide_leaching_range',
        'valid_range'
    ),
    (
        'reaction:copper_leachate_filtration',
        'condition:copper_leachate_filtration_range',
        'valid_range'
    );
