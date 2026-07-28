PRAGMA user_version = 1;

CREATE TABLE schema_migration (
    version INTEGER PRIMARY KEY,
    filename TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64)
) STRICT;

CREATE TABLE database_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;

CREATE TABLE license (
    license_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    spdx_id TEXT,
    url TEXT,
    redistribution_allowed INTEGER NOT NULL
        CHECK (redistribution_allowed IN (0, 1)),
    notes TEXT
) STRICT;

CREATE TABLE source (
    source_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    citation TEXT NOT NULL,
    url TEXT,
    license_id TEXT NOT NULL REFERENCES license(license_id),
    accessed_on TEXT CHECK (
        accessed_on IS NULL OR
        accessed_on GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
    )
) STRICT;

CREATE TABLE dataset (
    dataset_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    version TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES source(source_id),
    provenance_class TEXT NOT NULL
        CHECK (provenance_class IN ('measured', 'modeled', 'curated', 'fictional')),
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    notes TEXT,
    UNIQUE (title, version)
) STRICT;

CREATE TABLE unit (
    unit_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    quantity_kind TEXT NOT NULL,
    si_scale_numerator INTEGER NOT NULL,
    si_scale_denominator INTEGER NOT NULL CHECK (si_scale_denominator > 0),
    si_scale_power10 INTEGER NOT NULL DEFAULT 0,
    si_offset_numerator INTEGER NOT NULL DEFAULT 0,
    si_offset_denominator INTEGER NOT NULL DEFAULT 1
        CHECK (si_offset_denominator > 0)
) STRICT;

CREATE TABLE condition_set (
    condition_set_id TEXT PRIMARY KEY,
    description TEXT NOT NULL
) STRICT;

CREATE TABLE condition_value (
    condition_set_id TEXT NOT NULL
        REFERENCES condition_set(condition_set_id) ON DELETE CASCADE,
    quantity_kind TEXT NOT NULL,
    value_numerator INTEGER NOT NULL,
    value_denominator INTEGER NOT NULL CHECK (value_denominator > 0),
    unit_id TEXT NOT NULL REFERENCES unit(unit_id),
    PRIMARY KEY (condition_set_id, quantity_kind)
) STRICT, WITHOUT ROWID;

CREATE TABLE entity (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (
        entity_type IN (
            'particle', 'element', 'nuclide', 'chemical_species', 'material',
            'crystal_structure', 'mixture'
        )
    ),
    name TEXT NOT NULL,
    dataset_id TEXT NOT NULL REFERENCES dataset(dataset_id),
    lifecycle_state TEXT NOT NULL DEFAULT 'active'
        CHECK (lifecycle_state IN ('active', 'deprecated', 'hypothetical', 'fictional')),
    replaced_by_entity_id TEXT REFERENCES entity(entity_id),
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    CHECK (replaced_by_entity_id IS NULL OR replaced_by_entity_id <> entity_id)
) STRICT;

CREATE TABLE alias (
    alias_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entity(entity_id) ON DELETE CASCADE,
    scheme TEXT NOT NULL,
    value TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES source(source_id),
    UNIQUE (scheme, value)
) STRICT;

CREATE TABLE particle (
    entity_id TEXT PRIMARY KEY REFERENCES entity(entity_id) ON DELETE CASCADE,
    family TEXT NOT NULL CHECK (
        family IN ('quark', 'lepton', 'gauge_boson', 'scalar_boson', 'composite', 'other')
    ),
    symbol TEXT NOT NULL,
    electric_charge_numerator INTEGER NOT NULL,
    electric_charge_denominator INTEGER NOT NULL
        CHECK (electric_charge_denominator > 0),
    baryon_number_numerator INTEGER NOT NULL DEFAULT 0,
    baryon_number_denominator INTEGER NOT NULL DEFAULT 1
        CHECK (baryon_number_denominator > 0),
    lepton_number INTEGER NOT NULL DEFAULT 0,
    antiparticle_id TEXT REFERENCES particle(entity_id)
) STRICT;

CREATE TABLE element (
    entity_id TEXT PRIMARY KEY REFERENCES entity(entity_id) ON DELETE CASCADE,
    atomic_number INTEGER NOT NULL UNIQUE CHECK (atomic_number > 0),
    symbol TEXT NOT NULL UNIQUE
) STRICT;

CREATE TABLE nuclide (
    entity_id TEXT PRIMARY KEY REFERENCES entity(entity_id) ON DELETE CASCADE,
    element_id TEXT NOT NULL REFERENCES element(entity_id),
    proton_count INTEGER NOT NULL CHECK (proton_count > 0),
    neutron_count INTEGER NOT NULL CHECK (neutron_count >= 0),
    isomer_index INTEGER NOT NULL DEFAULT 0 CHECK (isomer_index >= 0),
    excitation_energy_numerator INTEGER,
    excitation_energy_denominator INTEGER
        CHECK (excitation_energy_denominator IS NULL OR excitation_energy_denominator > 0),
    excitation_energy_unit_id TEXT REFERENCES unit(unit_id),
    observed INTEGER NOT NULL CHECK (observed IN (0, 1)),
    UNIQUE (proton_count, neutron_count, isomer_index),
    CHECK (
        (excitation_energy_numerator IS NULL) =
        (excitation_energy_denominator IS NULL)
    ),
    CHECK (
        (excitation_energy_numerator IS NULL) =
        (excitation_energy_unit_id IS NULL)
    )
) STRICT;

CREATE TABLE chemical_species (
    entity_id TEXT PRIMARY KEY REFERENCES entity(entity_id) ON DELETE CASCADE,
    species_kind TEXT NOT NULL CHECK (
        species_kind IN (
            'atom', 'molecule', 'ion', 'formula_unit', 'complex',
            'polymer', 'unresolved'
        )
    ),
    formula TEXT NOT NULL,
    electric_charge INTEGER NOT NULL
) STRICT;

CREATE TABLE species_element (
    species_id TEXT NOT NULL
        REFERENCES chemical_species(entity_id) ON DELETE CASCADE,
    element_id TEXT NOT NULL REFERENCES element(entity_id),
    atom_count INTEGER NOT NULL CHECK (atom_count > 0),
    PRIMARY KEY (species_id, element_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE species_nuclide (
    species_id TEXT NOT NULL
        REFERENCES chemical_species(entity_id) ON DELETE CASCADE,
    nuclide_id TEXT NOT NULL REFERENCES nuclide(entity_id),
    atom_count INTEGER NOT NULL CHECK (atom_count > 0),
    PRIMARY KEY (species_id, nuclide_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE phase (
    phase_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
) STRICT;

CREATE TABLE species_phase (
    species_id TEXT NOT NULL
        REFERENCES chemical_species(entity_id) ON DELETE CASCADE,
    phase_id TEXT NOT NULL REFERENCES phase(phase_id),
    condition_set_id TEXT NOT NULL REFERENCES condition_set(condition_set_id),
    dataset_id TEXT NOT NULL REFERENCES dataset(dataset_id),
    PRIMARY KEY (species_id, phase_id, condition_set_id)
) STRICT;

CREATE TABLE molecule (
    species_id TEXT PRIMARY KEY
        REFERENCES chemical_species(entity_id) ON DELETE CASCADE,
    graph_model TEXT NOT NULL,
    total_formal_charge INTEGER NOT NULL,
    stereochemistry_status TEXT NOT NULL CHECK (
        stereochemistry_status IN ('specified', 'unspecified', 'not_applicable')
    )
) STRICT;

CREATE TABLE molecular_atom (
    species_id TEXT NOT NULL REFERENCES molecule(species_id) ON DELETE CASCADE,
    atom_index INTEGER NOT NULL CHECK (atom_index >= 0),
    element_id TEXT NOT NULL REFERENCES element(entity_id),
    nuclide_id TEXT REFERENCES nuclide(entity_id),
    formal_charge INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (species_id, atom_index)
) STRICT, WITHOUT ROWID;

CREATE TABLE molecular_bond (
    species_id TEXT NOT NULL REFERENCES molecule(species_id) ON DELETE CASCADE,
    atom_index_a INTEGER NOT NULL,
    atom_index_b INTEGER NOT NULL,
    bond_order_numerator INTEGER NOT NULL CHECK (bond_order_numerator > 0),
    bond_order_denominator INTEGER NOT NULL CHECK (bond_order_denominator > 0),
    bond_type TEXT NOT NULL CHECK (
        bond_type IN ('covalent', 'ionic', 'metallic', 'coordination', 'aromatic', 'other')
    ),
    PRIMARY KEY (species_id, atom_index_a, atom_index_b),
    FOREIGN KEY (species_id, atom_index_a)
        REFERENCES molecular_atom(species_id, atom_index),
    FOREIGN KEY (species_id, atom_index_b)
        REFERENCES molecular_atom(species_id, atom_index),
    CHECK (atom_index_a < atom_index_b)
) STRICT, WITHOUT ROWID;

CREATE TABLE material (
    entity_id TEXT PRIMARY KEY REFERENCES entity(entity_id) ON DELETE CASCADE,
    material_kind TEXT NOT NULL CHECK (
        material_kind IN (
            'pure_substance', 'mineral', 'ore', 'alloy', 'ceramic',
            'glass', 'composite', 'polymer', 'other'
        )
    )
) STRICT;

CREATE TABLE material_component (
    material_id TEXT NOT NULL REFERENCES material(entity_id) ON DELETE CASCADE,
    species_id TEXT NOT NULL REFERENCES chemical_species(entity_id),
    amount_numerator INTEGER,
    amount_denominator INTEGER CHECK (
        amount_denominator IS NULL OR amount_denominator > 0
    ),
    basis TEXT NOT NULL CHECK (
        basis IN ('mole_fraction', 'mass_fraction', 'volume_fraction', 'unspecified')
    ),
    role TEXT,
    PRIMARY KEY (material_id, species_id),
    CHECK (
        (amount_numerator IS NULL) = (amount_denominator IS NULL)
    ),
    CHECK (
        (basis = 'unspecified') = (amount_numerator IS NULL)
    )
) STRICT, WITHOUT ROWID;

CREATE TABLE mixture (
    entity_id TEXT PRIMARY KEY REFERENCES entity(entity_id) ON DELETE CASCADE,
    homogeneous INTEGER NOT NULL CHECK (homogeneous IN (0, 1)),
    basis TEXT NOT NULL CHECK (
        basis IN ('mole_fraction', 'mass_fraction', 'volume_fraction', 'amount')
    ),
    condition_set_id TEXT REFERENCES condition_set(condition_set_id)
) STRICT;

CREATE TABLE mixture_component (
    mixture_id TEXT NOT NULL REFERENCES mixture(entity_id) ON DELETE CASCADE,
    component_entity_id TEXT NOT NULL REFERENCES entity(entity_id),
    amount_numerator INTEGER NOT NULL,
    amount_denominator INTEGER NOT NULL CHECK (amount_denominator > 0),
    unit_id TEXT REFERENCES unit(unit_id),
    role TEXT,
    PRIMARY KEY (mixture_id, component_entity_id),
    CHECK (mixture_id <> component_entity_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE crystal_system (
    crystal_system_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
) STRICT;

CREATE TABLE space_group (
    international_number INTEGER PRIMARY KEY CHECK (
        international_number BETWEEN 1 AND 230
    ),
    hermann_mauguin_symbol TEXT NOT NULL,
    crystal_system_id TEXT NOT NULL REFERENCES crystal_system(crystal_system_id)
) STRICT;

CREATE TABLE crystal_structure (
    entity_id TEXT PRIMARY KEY REFERENCES entity(entity_id) ON DELETE CASCADE,
    species_id TEXT REFERENCES chemical_species(entity_id),
    material_id TEXT REFERENCES material(entity_id),
    space_group_number INTEGER REFERENCES space_group(international_number),
    condition_set_id TEXT REFERENCES condition_set(condition_set_id),
    structure_status TEXT NOT NULL CHECK (
        structure_status IN ('measured', 'modeled', 'hypothetical', 'fictional')
    ),
    CHECK ((species_id IS NULL) <> (material_id IS NULL))
) STRICT;

CREATE TABLE crystal_lattice_parameter (
    crystal_structure_id TEXT NOT NULL
        REFERENCES crystal_structure(entity_id) ON DELETE CASCADE,
    parameter TEXT NOT NULL CHECK (parameter IN ('a', 'b', 'c', 'alpha', 'beta', 'gamma')),
    value_numerator INTEGER NOT NULL,
    value_denominator INTEGER NOT NULL CHECK (value_denominator > 0),
    unit_id TEXT NOT NULL REFERENCES unit(unit_id),
    uncertainty_numerator INTEGER,
    uncertainty_denominator INTEGER CHECK (
        uncertainty_denominator IS NULL OR uncertainty_denominator > 0
    ),
    PRIMARY KEY (crystal_structure_id, parameter),
    CHECK (
        (uncertainty_numerator IS NULL) =
        (uncertainty_denominator IS NULL)
    )
) STRICT, WITHOUT ROWID;

CREATE TABLE crystal_lattice_site (
    crystal_structure_id TEXT NOT NULL
        REFERENCES crystal_structure(entity_id) ON DELETE CASCADE,
    site_id TEXT NOT NULL,
    component_entity_id TEXT NOT NULL REFERENCES entity(entity_id),
    x_numerator INTEGER NOT NULL,
    x_denominator INTEGER NOT NULL CHECK (x_denominator > 0),
    y_numerator INTEGER NOT NULL,
    y_denominator INTEGER NOT NULL CHECK (y_denominator > 0),
    z_numerator INTEGER NOT NULL,
    z_denominator INTEGER NOT NULL CHECK (z_denominator > 0),
    occupancy_numerator INTEGER NOT NULL CHECK (occupancy_numerator >= 0),
    occupancy_denominator INTEGER NOT NULL CHECK (
        occupancy_denominator > 0 AND occupancy_numerator <= occupancy_denominator
    ),
    PRIMARY KEY (crystal_structure_id, site_id, component_entity_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE property_definition (
    property_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    quantity_kind TEXT NOT NULL,
    canonical_unit_id TEXT NOT NULL REFERENCES unit(unit_id)
) STRICT;

CREATE TABLE observation (
    observation_id TEXT PRIMARY KEY,
    subject_entity_id TEXT NOT NULL REFERENCES entity(entity_id),
    property_id TEXT NOT NULL REFERENCES property_definition(property_id),
    value_numerator INTEGER NOT NULL,
    value_denominator INTEGER NOT NULL CHECK (value_denominator > 0),
    unit_id TEXT NOT NULL REFERENCES unit(unit_id),
    uncertainty_numerator INTEGER,
    uncertainty_denominator INTEGER CHECK (
        uncertainty_denominator IS NULL OR uncertainty_denominator > 0
    ),
    provenance_class TEXT NOT NULL CHECK (
        provenance_class IN ('measured', 'modeled', 'curated', 'fictional')
    ),
    dataset_id TEXT NOT NULL REFERENCES dataset(dataset_id),
    source_id TEXT NOT NULL REFERENCES source(source_id),
    condition_set_id TEXT REFERENCES condition_set(condition_set_id),
    method TEXT,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    CHECK (
        (uncertainty_numerator IS NULL) =
        (uncertainty_denominator IS NULL)
    )
) STRICT;

CREATE TABLE reaction (
    reaction_id TEXT PRIMARY KEY,
    reaction_kind TEXT NOT NULL CHECK (
        reaction_kind IN (
            'chemical', 'dissociation', 'ionization', 'redox',
            'phase_transition', 'process'
        )
    ),
    name TEXT NOT NULL,
    reversible INTEGER NOT NULL CHECK (reversible IN (0, 1)),
    energy_change_numerator INTEGER,
    energy_change_denominator INTEGER CHECK (
        energy_change_denominator IS NULL OR energy_change_denominator > 0
    ),
    energy_unit_id TEXT REFERENCES unit(unit_id),
    dataset_id TEXT NOT NULL REFERENCES dataset(dataset_id),
    source_id TEXT NOT NULL REFERENCES source(source_id),
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    CHECK (
        (energy_change_numerator IS NULL) =
        (energy_change_denominator IS NULL)
    ),
    CHECK (
        (energy_change_numerator IS NULL) =
        (energy_unit_id IS NULL)
    )
) STRICT;

CREATE TABLE reaction_participant (
    reaction_id TEXT NOT NULL REFERENCES reaction(reaction_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('reactant', 'product', 'catalyst', 'solvent')),
    species_id TEXT NOT NULL REFERENCES chemical_species(entity_id),
    phase_id TEXT NOT NULL REFERENCES phase(phase_id),
    coefficient_numerator INTEGER NOT NULL CHECK (coefficient_numerator > 0),
    coefficient_denominator INTEGER NOT NULL CHECK (coefficient_denominator > 0),
    PRIMARY KEY (reaction_id, role, species_id, phase_id)
) STRICT;

CREATE TABLE reaction_condition (
    reaction_id TEXT NOT NULL REFERENCES reaction(reaction_id) ON DELETE CASCADE,
    condition_set_id TEXT NOT NULL REFERENCES condition_set(condition_set_id),
    relationship TEXT NOT NULL CHECK (
        relationship IN ('required', 'measured_at', 'valid_range')
    ),
    PRIMARY KEY (reaction_id, condition_set_id, relationship)
) STRICT, WITHOUT ROWID;

CREATE TABLE dissociation (
    reaction_id TEXT PRIMARY KEY REFERENCES reaction(reaction_id) ON DELETE CASCADE,
    parent_species_id TEXT NOT NULL REFERENCES chemical_species(entity_id),
    solvent_species_id TEXT REFERENCES chemical_species(entity_id),
    dissociation_type TEXT NOT NULL CHECK (
        dissociation_type IN ('acid_base', 'salt', 'complex', 'thermal', 'photolytic', 'other')
    ),
    equilibrium_constant_observation_id TEXT REFERENCES observation(observation_id)
) STRICT;

CREATE TABLE spectrum (
    spectrum_id TEXT PRIMARY KEY,
    subject_entity_id TEXT NOT NULL REFERENCES entity(entity_id),
    region TEXT NOT NULL CHECK (
        region IN ('radio', 'microwave', 'infrared', 'visible', 'ultraviolet', 'xray', 'gamma')
    ),
    spectrum_kind TEXT NOT NULL CHECK (
        spectrum_kind IN ('absorption', 'emission', 'transmission', 'reflectance', 'scattering')
    ),
    axis_unit_id TEXT NOT NULL REFERENCES unit(unit_id),
    intensity_unit_id TEXT NOT NULL REFERENCES unit(unit_id),
    condition_set_id TEXT REFERENCES condition_set(condition_set_id),
    resolution_numerator INTEGER,
    resolution_denominator INTEGER CHECK (
        resolution_denominator IS NULL OR resolution_denominator > 0
    ),
    dataset_id TEXT NOT NULL REFERENCES dataset(dataset_id),
    source_id TEXT NOT NULL REFERENCES source(source_id),
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    CHECK (
        (resolution_numerator IS NULL) =
        (resolution_denominator IS NULL)
    )
) STRICT;

CREATE TABLE spectrum_point (
    spectrum_id TEXT NOT NULL REFERENCES spectrum(spectrum_id) ON DELETE CASCADE,
    point_index INTEGER NOT NULL CHECK (point_index >= 0),
    axis_numerator INTEGER NOT NULL,
    axis_denominator INTEGER NOT NULL CHECK (axis_denominator > 0),
    intensity_numerator INTEGER NOT NULL,
    intensity_denominator INTEGER NOT NULL CHECK (intensity_denominator > 0),
    uncertainty_numerator INTEGER,
    uncertainty_denominator INTEGER CHECK (
        uncertainty_denominator IS NULL OR uncertainty_denominator > 0
    ),
    PRIMARY KEY (spectrum_id, point_index),
    CHECK (
        (uncertainty_numerator IS NULL) =
        (uncertainty_denominator IS NULL)
    )
) STRICT, WITHOUT ROWID;

CREATE TABLE spectral_feature (
    feature_id TEXT PRIMARY KEY,
    spectrum_id TEXT NOT NULL REFERENCES spectrum(spectrum_id) ON DELETE CASCADE,
    feature_kind TEXT NOT NULL CHECK (
        feature_kind IN ('peak', 'edge', 'band', 'line', 'multiplet', 'other')
    ),
    position_numerator INTEGER NOT NULL,
    position_denominator INTEGER NOT NULL CHECK (position_denominator > 0),
    assignment TEXT
) STRICT;

CREATE TABLE nuclear_channel (
    channel_id TEXT PRIMARY KEY,
    channel_type TEXT NOT NULL CHECK (
        channel_type IN (
            'alpha', 'beta_minus', 'beta_plus', 'electron_capture',
            'gamma', 'neutron_emission', 'proton_emission',
            'spontaneous_fission', 'induced_fission', 'neutron_capture',
            'proton_capture', 'other'
        )
    ),
    parent_nuclide_id TEXT NOT NULL REFERENCES nuclide(entity_id),
    daughter_nuclide_id TEXT REFERENCES nuclide(entity_id),
    probability_numerator INTEGER,
    probability_denominator INTEGER CHECK (
        probability_denominator IS NULL OR probability_denominator > 0
    ),
    condition_set_id TEXT REFERENCES condition_set(condition_set_id),
    dataset_id TEXT NOT NULL REFERENCES dataset(dataset_id),
    source_id TEXT NOT NULL REFERENCES source(source_id),
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    CHECK (
        (probability_numerator IS NULL) =
        (probability_denominator IS NULL)
    ),
    CHECK (
        probability_numerator IS NULL OR
        probability_numerator BETWEEN 0 AND probability_denominator
    )
) STRICT;

CREATE TABLE nuclear_channel_particle (
    channel_id TEXT NOT NULL
        REFERENCES nuclear_channel(channel_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('incident', 'emitted')),
    particle_id TEXT NOT NULL REFERENCES particle(entity_id),
    count INTEGER NOT NULL CHECK (count > 0),
    PRIMARY KEY (channel_id, role, particle_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE nuclear_cross_section_point (
    channel_id TEXT NOT NULL
        REFERENCES nuclear_channel(channel_id) ON DELETE CASCADE,
    point_index INTEGER NOT NULL CHECK (point_index >= 0),
    energy_numerator INTEGER NOT NULL CHECK (energy_numerator >= 0),
    energy_denominator INTEGER NOT NULL CHECK (energy_denominator > 0),
    energy_unit_id TEXT NOT NULL REFERENCES unit(unit_id),
    cross_section_numerator INTEGER NOT NULL CHECK (cross_section_numerator >= 0),
    cross_section_denominator INTEGER NOT NULL CHECK (cross_section_denominator > 0),
    cross_section_unit_id TEXT NOT NULL REFERENCES unit(unit_id),
    uncertainty_numerator INTEGER,
    uncertainty_denominator INTEGER CHECK (
        uncertainty_denominator IS NULL OR uncertainty_denominator > 0
    ),
    PRIMARY KEY (channel_id, point_index),
    CHECK (
        (uncertainty_numerator IS NULL) =
        (uncertainty_denominator IS NULL)
    )
) STRICT, WITHOUT ROWID;

CREATE VIEW entity_summary AS
SELECT entity_id, entity_type, name, lifecycle_state, dataset_id
FROM entity
ORDER BY entity_type, entity_id;
