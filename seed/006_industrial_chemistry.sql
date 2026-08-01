-- Hand-authored, balanced industrial chemistry identities and reactions.
-- This slice intentionally records no measured physical-property values.

INSERT INTO source(
    source_id, title, citation, url, license_id, accessed_on
) VALUES (
    'universe-db-industrial-chemistry-2026-08-01',
    'Universe DB industrial chemistry seed',
    'Universe DB contributors, seed/006_industrial_chemistry.sql, 2026-08-01.',
    'https://github.com/szajsjem/universe-db/blob/main/seed/006_industrial_chemistry.sql',
    'mit',
    '2026-08-01'
);

INSERT INTO dataset(
    dataset_id, title, version, source_id, provenance_class,
    schema_version, notes
) VALUES (
    'dataset:industrial-chemistry-2026-08-01',
    'Authored industrial chemistry foundations',
    '2026-08-01',
    'universe-db-industrial-chemistry-2026-08-01',
    'curated',
    1,
    'Balanced educational identities and net equations for combustion, ore reduction, copper refining and electrowinning, acids, bases, and common salts. No measured values are asserted.'
);

CREATE TEMP TABLE seed_industrial_species(
    entity_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    species_kind TEXT NOT NULL,
    formula TEXT NOT NULL,
    electric_charge INTEGER NOT NULL
) STRICT;

INSERT INTO seed_industrial_species VALUES
    ('chem:calcium_chloride', 'calcium chloride', 'formula_unit', 'CaCl2', 0),
    ('chem:calcium_hydroxide', 'calcium hydroxide', 'formula_unit', 'Ca(OH)2', 0),
    ('chem:calcium_ion', 'calcium ion', 'ion', 'Ca2+', 2),
    ('chem:calcium_oxide', 'calcium oxide', 'formula_unit', 'CaO', 0),
    ('chem:calcium_silicate', 'calcium silicate', 'formula_unit', 'CaSiO3', 0),
    ('chem:carbon', 'carbon', 'atom', 'C', 0),
    ('chem:carbon_dioxide', 'carbon dioxide', 'molecule', 'CO2', 0),
    ('chem:carbon_monoxide', 'carbon monoxide', 'molecule', 'CO', 0),
    ('chem:carbonate', 'carbonate', 'ion', 'CO3^2-', -2),
    ('chem:chloride', 'chloride', 'ion', 'Cl-', -1),
    ('chem:copper_ion_2', 'copper(II) ion', 'ion', 'Cu2+', 2),
    ('chem:hydrochloric_acid', 'hydrochloric acid', 'molecule', 'HCl', 0),
    ('chem:hydronium', 'hydronium', 'ion', 'H3O+', 1),
    ('chem:iron_ion_2', 'iron(II) ion', 'ion', 'Fe2+', 2),
    ('chem:iron_sulfate', 'iron(II) sulfate', 'formula_unit', 'FeSO4', 0),
    ('chem:nitrate', 'nitrate', 'ion', 'NO3-', -1),
    ('chem:nitric_acid', 'nitric acid', 'molecule', 'HNO3', 0),
    ('chem:sodium_carbonate', 'sodium carbonate', 'formula_unit', 'Na2CO3', 0),
    ('chem:sodium_hydroxide', 'sodium hydroxide', 'formula_unit', 'NaOH', 0),
    ('chem:sodium_ion', 'sodium ion', 'ion', 'Na+', 1),
    ('chem:sodium_nitrate', 'sodium nitrate', 'formula_unit', 'NaNO3', 0),
    ('chem:sodium_sulfate', 'sodium sulfate', 'formula_unit', 'Na2SO4', 0),
    ('chem:sulfate', 'sulfate', 'ion', 'SO4^2-', -2),
    ('chem:sulfur_trioxide', 'sulfur trioxide', 'molecule', 'SO3', 0);

INSERT INTO entity(
    entity_id, entity_type, name, dataset_id, lifecycle_state, schema_version
)
SELECT
    entity_id, 'chemical_species', name,
    'dataset:industrial-chemistry-2026-08-01', 'active', 1
FROM seed_industrial_species ORDER BY entity_id;

INSERT INTO chemical_species(entity_id, species_kind, formula, electric_charge)
SELECT entity_id, species_kind, formula, electric_charge
FROM seed_industrial_species ORDER BY entity_id;

DROP TABLE seed_industrial_species;

INSERT INTO species_element(species_id, element_id, atom_count) VALUES
    ('chem:calcium_chloride', 'element:calcium', 1),
    ('chem:calcium_chloride', 'element:chlorine', 2),
    ('chem:calcium_hydroxide', 'element:calcium', 1),
    ('chem:calcium_hydroxide', 'element:hydrogen', 2),
    ('chem:calcium_hydroxide', 'element:oxygen', 2),
    ('chem:calcium_ion', 'element:calcium', 1),
    ('chem:calcium_oxide', 'element:calcium', 1),
    ('chem:calcium_oxide', 'element:oxygen', 1),
    ('chem:calcium_silicate', 'element:calcium', 1),
    ('chem:calcium_silicate', 'element:oxygen', 3),
    ('chem:calcium_silicate', 'element:silicon', 1),
    ('chem:carbon', 'element:carbon', 1),
    ('chem:carbon_dioxide', 'element:carbon', 1),
    ('chem:carbon_dioxide', 'element:oxygen', 2),
    ('chem:carbon_monoxide', 'element:carbon', 1),
    ('chem:carbon_monoxide', 'element:oxygen', 1),
    ('chem:carbonate', 'element:carbon', 1),
    ('chem:carbonate', 'element:oxygen', 3),
    ('chem:chloride', 'element:chlorine', 1),
    ('chem:copper_ion_2', 'element:copper', 1),
    ('chem:hydrochloric_acid', 'element:chlorine', 1),
    ('chem:hydrochloric_acid', 'element:hydrogen', 1),
    ('chem:hydronium', 'element:hydrogen', 3),
    ('chem:hydronium', 'element:oxygen', 1),
    ('chem:iron_ion_2', 'element:iron', 1),
    ('chem:iron_sulfate', 'element:iron', 1),
    ('chem:iron_sulfate', 'element:oxygen', 4),
    ('chem:iron_sulfate', 'element:sulfur', 1),
    ('chem:nitrate', 'element:nitrogen', 1),
    ('chem:nitrate', 'element:oxygen', 3),
    ('chem:nitric_acid', 'element:hydrogen', 1),
    ('chem:nitric_acid', 'element:nitrogen', 1),
    ('chem:nitric_acid', 'element:oxygen', 3),
    ('chem:sodium_carbonate', 'element:carbon', 1),
    ('chem:sodium_carbonate', 'element:oxygen', 3),
    ('chem:sodium_carbonate', 'element:sodium', 2),
    ('chem:sodium_hydroxide', 'element:hydrogen', 1),
    ('chem:sodium_hydroxide', 'element:oxygen', 1),
    ('chem:sodium_hydroxide', 'element:sodium', 1),
    ('chem:sodium_ion', 'element:sodium', 1),
    ('chem:sodium_nitrate', 'element:nitrogen', 1),
    ('chem:sodium_nitrate', 'element:oxygen', 3),
    ('chem:sodium_nitrate', 'element:sodium', 1),
    ('chem:sodium_sulfate', 'element:oxygen', 4),
    ('chem:sodium_sulfate', 'element:sodium', 2),
    ('chem:sodium_sulfate', 'element:sulfur', 1),
    ('chem:sulfate', 'element:oxygen', 4),
    ('chem:sulfate', 'element:sulfur', 1),
    ('chem:sulfur_trioxide', 'element:oxygen', 3),
    ('chem:sulfur_trioxide', 'element:sulfur', 1);

INSERT INTO species_phase(
    species_id, phase_id, condition_set_id, dataset_id
) VALUES
    ('chem:calcium_chloride', 'phase:solid', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:calcium_chloride', 'phase:aqueous', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:calcium_hydroxide', 'phase:solid', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:calcium_hydroxide', 'phase:aqueous', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:calcium_ion', 'phase:aqueous', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:calcium_oxide', 'phase:solid', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:calcium_silicate', 'phase:solid', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:calcium_silicate', 'phase:molten', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:carbon', 'phase:solid', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:carbon_dioxide', 'phase:gas', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:carbon_monoxide', 'phase:gas', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:carbonate', 'phase:aqueous', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:chloride', 'phase:aqueous', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:copper_ion_2', 'phase:aqueous', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:hydrochloric_acid', 'phase:aqueous', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:hydronium', 'phase:aqueous', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:iron_ion_2', 'phase:aqueous', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:iron_sulfate', 'phase:solid', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:iron_sulfate', 'phase:aqueous', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:nitrate', 'phase:aqueous', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:nitric_acid', 'phase:liquid', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:nitric_acid', 'phase:aqueous', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:sodium_carbonate', 'phase:solid', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:sodium_carbonate', 'phase:aqueous', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:sodium_hydroxide', 'phase:solid', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:sodium_hydroxide', 'phase:aqueous', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:sodium_ion', 'phase:aqueous', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:sodium_nitrate', 'phase:solid', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:sodium_nitrate', 'phase:aqueous', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:sodium_sulfate', 'phase:solid', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:sodium_sulfate', 'phase:aqueous', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:sulfate', 'phase:aqueous', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01'),
    ('chem:sulfur_trioxide', 'phase:gas', 'condition:unspecified', 'dataset:industrial-chemistry-2026-08-01');

CREATE TEMP TABLE seed_industrial_material(
    entity_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    material_kind TEXT NOT NULL
) STRICT;

INSERT INTO seed_industrial_material VALUES
    ('material:coal', 'coal', 'other'),
    ('material:copper_anode', 'copper anode', 'alloy');

INSERT INTO entity(
    entity_id, entity_type, name, dataset_id, lifecycle_state, schema_version
)
SELECT
    entity_id, 'material', name, 'dataset:industrial-chemistry-2026-08-01',
    'active', 1
FROM seed_industrial_material ORDER BY entity_id;

INSERT INTO material(entity_id, material_kind)
SELECT entity_id, material_kind
FROM seed_industrial_material ORDER BY entity_id;

DROP TABLE seed_industrial_material;

INSERT INTO material_component(
    material_id, species_id, amount_numerator, amount_denominator, basis, role
) VALUES
    ('material:coal', 'chem:carbon', NULL, NULL, 'unspecified', 'combustible constituent'),
    ('material:coal', 'chem:unresolved_trace', NULL, NULL, 'unspecified', 'variable mineral matter and volatiles'),
    ('material:copper_anode', 'chem:copper', NULL, NULL, 'unspecified', 'major constituent'),
    ('material:copper_anode', 'chem:unresolved_trace', NULL, NULL, 'unspecified', 'anode impurities');

INSERT INTO condition_set(condition_set_id, description) VALUES
    (
        'condition:industrial_high_temperature',
        'Qualitative authored condition: elevated process temperature is required; no numeric operating range is asserted.'
    ),
    (
        'condition:direct_current_electrolysis',
        'Qualitative authored condition: an applied direct current and aqueous electrolyte are required; no voltage or current density is asserted.'
    );

CREATE TEMP TABLE seed_industrial_reaction(
    reaction_id TEXT PRIMARY KEY,
    reaction_kind TEXT NOT NULL,
    name TEXT NOT NULL,
    reversible INTEGER NOT NULL
) STRICT;

INSERT INTO seed_industrial_reaction VALUES
    ('reaction:blast_furnace_slag_formation', 'process', 'blast-furnace calcium-silicate slag formation', 0),
    ('reaction:boudouard', 'chemical', 'Boudouard reaction', 1),
    ('reaction:calcium_carbonate_dissolution', 'dissociation', 'calcium carbonate dissolution', 1),
    ('reaction:calcium_chloride_dissociation', 'dissociation', 'calcium chloride dissociation', 1),
    ('reaction:calcium_hydroxide_dissociation', 'dissociation', 'calcium hydroxide dissociation', 1),
    ('reaction:carbon_complete_combustion', 'chemical', 'complete combustion of carbon', 0),
    ('reaction:carbon_incomplete_combustion', 'chemical', 'incomplete combustion of carbon', 0),
    ('reaction:carbon_monoxide_combustion', 'chemical', 'combustion of carbon monoxide', 0),
    ('reaction:carbonate_acidification', 'chemical', 'sodium carbonate acidification', 0),
    ('reaction:copper_cementation', 'redox', 'copper cementation with iron', 0),
    ('reaction:copper_electrorefining', 'process', 'net copper electrorefining transfer from anode to cathode', 0),
    ('reaction:copper_electrowinning', 'process', 'copper electrowinning from sulfate electrolyte', 0),
    ('reaction:copper_oxide_carbon_reduction', 'redox', 'carbon reduction of copper(II) oxide', 0),
    ('reaction:copper_sulfate_dissociation', 'dissociation', 'copper(II) sulfate dissociation', 1),
    ('reaction:hematite_carbon_monoxide_reduction', 'redox', 'hematite reduction by carbon monoxide', 0),
    ('reaction:hematite_direct_carbon_reduction', 'redox', 'direct carbon reduction of hematite', 0),
    ('reaction:hydrochloric_acid_dissociation', 'dissociation', 'hydrochloric acid ionization in water', 1),
    ('reaction:hydrochloric_acid_sodium_hydroxide', 'chemical', 'hydrochloric acid neutralization with sodium hydroxide', 0),
    ('reaction:hydronium_hydroxide_neutralization', 'chemical', 'hydronium and hydroxide neutralization', 0),
    ('reaction:iron_sulfate_dissociation', 'dissociation', 'iron(II) sulfate dissociation', 1),
    ('reaction:limestone_calcination', 'process', 'limestone calcination', 0),
    ('reaction:magnetite_carbon_monoxide_reduction', 'redox', 'magnetite reduction by carbon monoxide', 0),
    ('reaction:nitric_acid_dissociation', 'dissociation', 'nitric acid ionization in water', 1),
    ('reaction:nitric_acid_sodium_hydroxide', 'chemical', 'nitric acid neutralization with sodium hydroxide', 0),
    ('reaction:sodium_carbonate_dissociation', 'dissociation', 'sodium carbonate dissociation', 1),
    ('reaction:sodium_chloride_dissociation', 'dissociation', 'sodium chloride dissociation', 1),
    ('reaction:sodium_hydroxide_dissociation', 'dissociation', 'sodium hydroxide dissociation', 1),
    ('reaction:sodium_nitrate_dissociation', 'dissociation', 'sodium nitrate dissociation', 1),
    ('reaction:sodium_sulfate_dissociation', 'dissociation', 'sodium sulfate dissociation', 1),
    ('reaction:sulfur_dioxide_oxidation', 'chemical', 'oxidation of sulfur dioxide', 0),
    ('reaction:sulfur_trioxide_hydration', 'chemical', 'hydration of sulfur trioxide', 0),
    ('reaction:sulfuric_acid_dissociation', 'dissociation', 'overall sulfuric acid ionization in water', 1),
    ('reaction:sulfuric_acid_sodium_hydroxide', 'chemical', 'sulfuric acid neutralization with sodium hydroxide', 0),
    ('reaction:water_autoionization', 'dissociation', 'water autoionization', 1),
    ('reaction:water_gas', 'chemical', 'water-gas reaction', 0);

INSERT INTO reaction(
    reaction_id, reaction_kind, name, reversible, dataset_id, source_id,
    schema_version
)
SELECT
    reaction_id, reaction_kind, name, reversible,
    'dataset:industrial-chemistry-2026-08-01',
    'universe-db-industrial-chemistry-2026-08-01', 1
FROM seed_industrial_reaction ORDER BY reaction_id;

DROP TABLE seed_industrial_reaction;

INSERT INTO reaction_participant(
    reaction_id, role, species_id, phase_id,
    coefficient_numerator, coefficient_denominator
) VALUES
    ('reaction:blast_furnace_slag_formation', 'reactant', 'chem:calcium_oxide', 'phase:solid', 1, 1),
    ('reaction:blast_furnace_slag_formation', 'reactant', 'chem:quartz', 'phase:solid', 1, 1),
    ('reaction:blast_furnace_slag_formation', 'product', 'chem:calcium_silicate', 'phase:molten', 1, 1),
    ('reaction:boudouard', 'reactant', 'chem:carbon', 'phase:solid', 1, 1),
    ('reaction:boudouard', 'reactant', 'chem:carbon_dioxide', 'phase:gas', 1, 1),
    ('reaction:boudouard', 'product', 'chem:carbon_monoxide', 'phase:gas', 2, 1),
    ('reaction:calcium_carbonate_dissolution', 'reactant', 'chem:calcite', 'phase:solid', 1, 1),
    ('reaction:calcium_carbonate_dissolution', 'product', 'chem:calcium_ion', 'phase:aqueous', 1, 1),
    ('reaction:calcium_carbonate_dissolution', 'product', 'chem:carbonate', 'phase:aqueous', 1, 1),
    ('reaction:calcium_chloride_dissociation', 'reactant', 'chem:calcium_chloride', 'phase:aqueous', 1, 1),
    ('reaction:calcium_chloride_dissociation', 'product', 'chem:calcium_ion', 'phase:aqueous', 1, 1),
    ('reaction:calcium_chloride_dissociation', 'product', 'chem:chloride', 'phase:aqueous', 2, 1),
    ('reaction:calcium_hydroxide_dissociation', 'reactant', 'chem:calcium_hydroxide', 'phase:aqueous', 1, 1),
    ('reaction:calcium_hydroxide_dissociation', 'product', 'chem:calcium_ion', 'phase:aqueous', 1, 1),
    ('reaction:calcium_hydroxide_dissociation', 'product', 'chem:hydroxide', 'phase:aqueous', 2, 1),
    ('reaction:carbon_complete_combustion', 'reactant', 'chem:carbon', 'phase:solid', 1, 1),
    ('reaction:carbon_complete_combustion', 'reactant', 'chem:oxygen', 'phase:gas', 1, 1),
    ('reaction:carbon_complete_combustion', 'product', 'chem:carbon_dioxide', 'phase:gas', 1, 1),
    ('reaction:carbon_incomplete_combustion', 'reactant', 'chem:carbon', 'phase:solid', 2, 1),
    ('reaction:carbon_incomplete_combustion', 'reactant', 'chem:oxygen', 'phase:gas', 1, 1),
    ('reaction:carbon_incomplete_combustion', 'product', 'chem:carbon_monoxide', 'phase:gas', 2, 1),
    ('reaction:carbon_monoxide_combustion', 'reactant', 'chem:carbon_monoxide', 'phase:gas', 2, 1),
    ('reaction:carbon_monoxide_combustion', 'reactant', 'chem:oxygen', 'phase:gas', 1, 1),
    ('reaction:carbon_monoxide_combustion', 'product', 'chem:carbon_dioxide', 'phase:gas', 2, 1),
    ('reaction:carbonate_acidification', 'reactant', 'chem:sodium_carbonate', 'phase:aqueous', 1, 1),
    ('reaction:carbonate_acidification', 'reactant', 'chem:hydrochloric_acid', 'phase:aqueous', 2, 1),
    ('reaction:carbonate_acidification', 'product', 'chem:halite', 'phase:aqueous', 2, 1),
    ('reaction:carbonate_acidification', 'product', 'chem:water', 'phase:aqueous', 1, 1),
    ('reaction:carbonate_acidification', 'product', 'chem:carbon_dioxide', 'phase:gas', 1, 1),
    ('reaction:copper_cementation', 'reactant', 'chem:copper_sulfate', 'phase:aqueous', 1, 1),
    ('reaction:copper_cementation', 'reactant', 'chem:iron', 'phase:solid', 1, 1),
    ('reaction:copper_cementation', 'product', 'chem:copper', 'phase:solid', 1, 1),
    ('reaction:copper_cementation', 'product', 'chem:iron_sulfate', 'phase:aqueous', 1, 1),
    ('reaction:copper_electrorefining', 'reactant', 'chem:copper', 'phase:solid', 1, 1),
    ('reaction:copper_electrorefining', 'product', 'chem:copper', 'phase:solid', 1, 1),
    ('reaction:copper_electrowinning', 'reactant', 'chem:copper_sulfate', 'phase:aqueous', 2, 1),
    ('reaction:copper_electrowinning', 'reactant', 'chem:water', 'phase:aqueous', 2, 1),
    ('reaction:copper_electrowinning', 'product', 'chem:copper', 'phase:solid', 2, 1),
    ('reaction:copper_electrowinning', 'product', 'chem:oxygen', 'phase:gas', 1, 1),
    ('reaction:copper_electrowinning', 'product', 'chem:sulfuric_acid', 'phase:aqueous', 2, 1),
    ('reaction:copper_oxide_carbon_reduction', 'reactant', 'chem:copper_oxide', 'phase:solid', 2, 1),
    ('reaction:copper_oxide_carbon_reduction', 'reactant', 'chem:carbon', 'phase:solid', 1, 1),
    ('reaction:copper_oxide_carbon_reduction', 'product', 'chem:copper', 'phase:solid', 2, 1),
    ('reaction:copper_oxide_carbon_reduction', 'product', 'chem:carbon_dioxide', 'phase:gas', 1, 1),
    ('reaction:copper_sulfate_dissociation', 'reactant', 'chem:copper_sulfate', 'phase:aqueous', 1, 1),
    ('reaction:copper_sulfate_dissociation', 'product', 'chem:copper_ion_2', 'phase:aqueous', 1, 1),
    ('reaction:copper_sulfate_dissociation', 'product', 'chem:sulfate', 'phase:aqueous', 1, 1),
    ('reaction:hematite_carbon_monoxide_reduction', 'reactant', 'chem:hematite', 'phase:solid', 1, 1),
    ('reaction:hematite_carbon_monoxide_reduction', 'reactant', 'chem:carbon_monoxide', 'phase:gas', 3, 1),
    ('reaction:hematite_carbon_monoxide_reduction', 'product', 'chem:iron', 'phase:solid', 2, 1),
    ('reaction:hematite_carbon_monoxide_reduction', 'product', 'chem:carbon_dioxide', 'phase:gas', 3, 1),
    ('reaction:hematite_direct_carbon_reduction', 'reactant', 'chem:hematite', 'phase:solid', 1, 1),
    ('reaction:hematite_direct_carbon_reduction', 'reactant', 'chem:carbon', 'phase:solid', 3, 1),
    ('reaction:hematite_direct_carbon_reduction', 'product', 'chem:iron', 'phase:solid', 2, 1),
    ('reaction:hematite_direct_carbon_reduction', 'product', 'chem:carbon_monoxide', 'phase:gas', 3, 1),
    ('reaction:hydrochloric_acid_dissociation', 'reactant', 'chem:hydrochloric_acid', 'phase:aqueous', 1, 1),
    ('reaction:hydrochloric_acid_dissociation', 'reactant', 'chem:water', 'phase:aqueous', 1, 1),
    ('reaction:hydrochloric_acid_dissociation', 'product', 'chem:hydronium', 'phase:aqueous', 1, 1),
    ('reaction:hydrochloric_acid_dissociation', 'product', 'chem:chloride', 'phase:aqueous', 1, 1),
    ('reaction:hydrochloric_acid_sodium_hydroxide', 'reactant', 'chem:hydrochloric_acid', 'phase:aqueous', 1, 1),
    ('reaction:hydrochloric_acid_sodium_hydroxide', 'reactant', 'chem:sodium_hydroxide', 'phase:aqueous', 1, 1),
    ('reaction:hydrochloric_acid_sodium_hydroxide', 'product', 'chem:halite', 'phase:aqueous', 1, 1),
    ('reaction:hydrochloric_acid_sodium_hydroxide', 'product', 'chem:water', 'phase:aqueous', 1, 1),
    ('reaction:hydronium_hydroxide_neutralization', 'reactant', 'chem:hydronium', 'phase:aqueous', 1, 1),
    ('reaction:hydronium_hydroxide_neutralization', 'reactant', 'chem:hydroxide', 'phase:aqueous', 1, 1),
    ('reaction:hydronium_hydroxide_neutralization', 'product', 'chem:water', 'phase:aqueous', 2, 1),
    ('reaction:iron_sulfate_dissociation', 'reactant', 'chem:iron_sulfate', 'phase:aqueous', 1, 1),
    ('reaction:iron_sulfate_dissociation', 'product', 'chem:iron_ion_2', 'phase:aqueous', 1, 1),
    ('reaction:iron_sulfate_dissociation', 'product', 'chem:sulfate', 'phase:aqueous', 1, 1),
    ('reaction:limestone_calcination', 'reactant', 'chem:calcite', 'phase:solid', 1, 1),
    ('reaction:limestone_calcination', 'product', 'chem:calcium_oxide', 'phase:solid', 1, 1),
    ('reaction:limestone_calcination', 'product', 'chem:carbon_dioxide', 'phase:gas', 1, 1),
    ('reaction:magnetite_carbon_monoxide_reduction', 'reactant', 'chem:magnetite', 'phase:solid', 1, 1),
    ('reaction:magnetite_carbon_monoxide_reduction', 'reactant', 'chem:carbon_monoxide', 'phase:gas', 4, 1),
    ('reaction:magnetite_carbon_monoxide_reduction', 'product', 'chem:iron', 'phase:solid', 3, 1),
    ('reaction:magnetite_carbon_monoxide_reduction', 'product', 'chem:carbon_dioxide', 'phase:gas', 4, 1),
    ('reaction:nitric_acid_dissociation', 'reactant', 'chem:nitric_acid', 'phase:aqueous', 1, 1),
    ('reaction:nitric_acid_dissociation', 'reactant', 'chem:water', 'phase:aqueous', 1, 1),
    ('reaction:nitric_acid_dissociation', 'product', 'chem:hydronium', 'phase:aqueous', 1, 1),
    ('reaction:nitric_acid_dissociation', 'product', 'chem:nitrate', 'phase:aqueous', 1, 1),
    ('reaction:nitric_acid_sodium_hydroxide', 'reactant', 'chem:nitric_acid', 'phase:aqueous', 1, 1),
    ('reaction:nitric_acid_sodium_hydroxide', 'reactant', 'chem:sodium_hydroxide', 'phase:aqueous', 1, 1),
    ('reaction:nitric_acid_sodium_hydroxide', 'product', 'chem:sodium_nitrate', 'phase:aqueous', 1, 1),
    ('reaction:nitric_acid_sodium_hydroxide', 'product', 'chem:water', 'phase:aqueous', 1, 1),
    ('reaction:sodium_carbonate_dissociation', 'reactant', 'chem:sodium_carbonate', 'phase:aqueous', 1, 1),
    ('reaction:sodium_carbonate_dissociation', 'product', 'chem:sodium_ion', 'phase:aqueous', 2, 1),
    ('reaction:sodium_carbonate_dissociation', 'product', 'chem:carbonate', 'phase:aqueous', 1, 1),
    ('reaction:sodium_chloride_dissociation', 'reactant', 'chem:halite', 'phase:aqueous', 1, 1),
    ('reaction:sodium_chloride_dissociation', 'product', 'chem:sodium_ion', 'phase:aqueous', 1, 1),
    ('reaction:sodium_chloride_dissociation', 'product', 'chem:chloride', 'phase:aqueous', 1, 1),
    ('reaction:sodium_hydroxide_dissociation', 'reactant', 'chem:sodium_hydroxide', 'phase:aqueous', 1, 1),
    ('reaction:sodium_hydroxide_dissociation', 'product', 'chem:sodium_ion', 'phase:aqueous', 1, 1),
    ('reaction:sodium_hydroxide_dissociation', 'product', 'chem:hydroxide', 'phase:aqueous', 1, 1),
    ('reaction:sodium_nitrate_dissociation', 'reactant', 'chem:sodium_nitrate', 'phase:aqueous', 1, 1),
    ('reaction:sodium_nitrate_dissociation', 'product', 'chem:sodium_ion', 'phase:aqueous', 1, 1),
    ('reaction:sodium_nitrate_dissociation', 'product', 'chem:nitrate', 'phase:aqueous', 1, 1),
    ('reaction:sodium_sulfate_dissociation', 'reactant', 'chem:sodium_sulfate', 'phase:aqueous', 1, 1),
    ('reaction:sodium_sulfate_dissociation', 'product', 'chem:sodium_ion', 'phase:aqueous', 2, 1),
    ('reaction:sodium_sulfate_dissociation', 'product', 'chem:sulfate', 'phase:aqueous', 1, 1),
    ('reaction:sulfur_dioxide_oxidation', 'reactant', 'chem:sulfur_dioxide', 'phase:gas', 2, 1),
    ('reaction:sulfur_dioxide_oxidation', 'reactant', 'chem:oxygen', 'phase:gas', 1, 1),
    ('reaction:sulfur_dioxide_oxidation', 'product', 'chem:sulfur_trioxide', 'phase:gas', 2, 1),
    ('reaction:sulfur_trioxide_hydration', 'reactant', 'chem:sulfur_trioxide', 'phase:gas', 1, 1),
    ('reaction:sulfur_trioxide_hydration', 'reactant', 'chem:water', 'phase:aqueous', 1, 1),
    ('reaction:sulfur_trioxide_hydration', 'product', 'chem:sulfuric_acid', 'phase:aqueous', 1, 1),
    ('reaction:sulfuric_acid_dissociation', 'reactant', 'chem:sulfuric_acid', 'phase:aqueous', 1, 1),
    ('reaction:sulfuric_acid_dissociation', 'reactant', 'chem:water', 'phase:aqueous', 2, 1),
    ('reaction:sulfuric_acid_dissociation', 'product', 'chem:hydronium', 'phase:aqueous', 2, 1),
    ('reaction:sulfuric_acid_dissociation', 'product', 'chem:sulfate', 'phase:aqueous', 1, 1),
    ('reaction:sulfuric_acid_sodium_hydroxide', 'reactant', 'chem:sulfuric_acid', 'phase:aqueous', 1, 1),
    ('reaction:sulfuric_acid_sodium_hydroxide', 'reactant', 'chem:sodium_hydroxide', 'phase:aqueous', 2, 1),
    ('reaction:sulfuric_acid_sodium_hydroxide', 'product', 'chem:sodium_sulfate', 'phase:aqueous', 1, 1),
    ('reaction:sulfuric_acid_sodium_hydroxide', 'product', 'chem:water', 'phase:aqueous', 2, 1),
    ('reaction:water_autoionization', 'reactant', 'chem:water', 'phase:aqueous', 2, 1),
    ('reaction:water_autoionization', 'product', 'chem:hydronium', 'phase:aqueous', 1, 1),
    ('reaction:water_autoionization', 'product', 'chem:hydroxide', 'phase:aqueous', 1, 1),
    ('reaction:water_gas', 'reactant', 'chem:carbon', 'phase:solid', 1, 1),
    ('reaction:water_gas', 'reactant', 'chem:water', 'phase:gas', 1, 1),
    ('reaction:water_gas', 'product', 'chem:carbon_monoxide', 'phase:gas', 1, 1),
    ('reaction:water_gas', 'product', 'chem:hydrogen', 'phase:gas', 1, 1);

INSERT INTO dissociation(
    reaction_id, parent_species_id, solvent_species_id, dissociation_type
) VALUES
    ('reaction:calcium_carbonate_dissolution', 'chem:calcite', 'chem:water', 'salt'),
    ('reaction:calcium_chloride_dissociation', 'chem:calcium_chloride', 'chem:water', 'salt'),
    ('reaction:calcium_hydroxide_dissociation', 'chem:calcium_hydroxide', 'chem:water', 'acid_base'),
    ('reaction:copper_sulfate_dissociation', 'chem:copper_sulfate', 'chem:water', 'salt'),
    ('reaction:hydrochloric_acid_dissociation', 'chem:hydrochloric_acid', 'chem:water', 'acid_base'),
    ('reaction:iron_sulfate_dissociation', 'chem:iron_sulfate', 'chem:water', 'salt'),
    ('reaction:nitric_acid_dissociation', 'chem:nitric_acid', 'chem:water', 'acid_base'),
    ('reaction:sodium_carbonate_dissociation', 'chem:sodium_carbonate', 'chem:water', 'salt'),
    ('reaction:sodium_chloride_dissociation', 'chem:halite', 'chem:water', 'salt'),
    ('reaction:sodium_hydroxide_dissociation', 'chem:sodium_hydroxide', 'chem:water', 'acid_base'),
    ('reaction:sodium_nitrate_dissociation', 'chem:sodium_nitrate', 'chem:water', 'salt'),
    ('reaction:sodium_sulfate_dissociation', 'chem:sodium_sulfate', 'chem:water', 'salt'),
    ('reaction:sulfuric_acid_dissociation', 'chem:sulfuric_acid', 'chem:water', 'acid_base'),
    ('reaction:water_autoionization', 'chem:water', 'chem:water', 'acid_base');

INSERT INTO reaction_condition(
    reaction_id, condition_set_id, relationship
) VALUES
    ('reaction:blast_furnace_slag_formation', 'condition:industrial_high_temperature', 'required'),
    ('reaction:boudouard', 'condition:industrial_high_temperature', 'required'),
    ('reaction:copper_electrorefining', 'condition:direct_current_electrolysis', 'required'),
    ('reaction:copper_electrowinning', 'condition:direct_current_electrolysis', 'required'),
    ('reaction:hematite_carbon_monoxide_reduction', 'condition:industrial_high_temperature', 'required'),
    ('reaction:hematite_direct_carbon_reduction', 'condition:industrial_high_temperature', 'required'),
    ('reaction:limestone_calcination', 'condition:industrial_high_temperature', 'required'),
    ('reaction:magnetite_carbon_monoxide_reduction', 'condition:industrial_high_temperature', 'required'),
    ('reaction:water_gas', 'condition:industrial_high_temperature', 'required');
