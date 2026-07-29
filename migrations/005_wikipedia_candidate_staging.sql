PRAGMA user_version = 5;

CREATE TABLE wikipedia_parse_run (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    model TEXT NOT NULL,
    archive_name TEXT NOT NULL,
    archive_format TEXT NOT NULL,
    archive_sha256 TEXT NOT NULL CHECK (length(archive_sha256) = 64),
    archive_page_count INTEGER NOT NULL CHECK (archive_page_count >= 0),
    license_spdx_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('running', 'completed', 'stopped', 'failed')
    ),
    notes TEXT
) STRICT;

CREATE TABLE wikipedia_page_parse (
    page_parse_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL
        REFERENCES wikipedia_parse_run(run_id) ON DELETE CASCADE,
    sequence_index INTEGER NOT NULL CHECK (sequence_index >= 0),
    source_entry_key TEXT NOT NULL,
    source_path TEXT NOT NULL,
    input_format TEXT NOT NULL CHECK (input_format IN ('wikitext', 'html')),
    page_id INTEGER CHECK (page_id IS NULL OR page_id > 0),
    revision_id INTEGER CHECK (revision_id IS NULL OR revision_id > 0),
    title TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_timestamp TEXT,
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    content_chars INTEGER NOT NULL CHECK (content_chars >= 0),
    submitted_chars INTEGER NOT NULL CHECK (
        submitted_chars >= 0 AND submitted_chars <= content_chars
    ),
    status TEXT NOT NULL CHECK (
        status IN (
            'pending', 'parsed', 'parsed_partial', 'no_data', 'error', 'skipped'
        )
    ),
    response_id TEXT,
    error_text TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (run_id, source_entry_key)
) STRICT;

CREATE TABLE unverified_entity_candidate (
    candidate_id TEXT PRIMARY KEY,
    page_parse_id TEXT NOT NULL
        REFERENCES wikipedia_page_parse(page_parse_id) ON DELETE CASCADE,
    candidate_index INTEGER NOT NULL CHECK (candidate_index >= 0),
    candidate_kind TEXT NOT NULL CHECK (
        candidate_kind IN (
            'particle', 'element', 'nuclide', 'atom', 'molecule', 'ion',
            'formula_unit', 'complex', 'polymer', 'material', 'mixture',
            'reaction'
        )
    ),
    name TEXT NOT NULL,
    proposed_id TEXT,
    existing_entity_id TEXT REFERENCES entity(entity_id),
    existing_reaction_id TEXT REFERENCES reaction(reaction_id),
    formula TEXT,
    electric_charge INTEGER,
    atomic_number INTEGER CHECK (
        atomic_number IS NULL OR atomic_number > 0
    ),
    proton_count INTEGER CHECK (
        proton_count IS NULL OR proton_count > 0
    ),
    neutron_count INTEGER CHECK (
        neutron_count IS NULL OR neutron_count >= 0
    ),
    isomer_index INTEGER CHECK (
        isomer_index IS NULL OR isomer_index >= 0
    ),
    observed INTEGER CHECK (observed IS NULL OR observed IN (0, 1)),
    confidence TEXT NOT NULL CHECK (
        confidence IN ('low', 'medium', 'high')
    ),
    evidence_text TEXT NOT NULL,
    UNIQUE (page_parse_id, candidate_index),
    CHECK (
        existing_entity_id IS NULL OR existing_reaction_id IS NULL
    )
) STRICT;

CREATE TABLE unverified_candidate_alias (
    candidate_id TEXT NOT NULL
        REFERENCES unverified_entity_candidate(candidate_id) ON DELETE CASCADE,
    alias_index INTEGER NOT NULL CHECK (alias_index >= 0),
    value TEXT NOT NULL,
    PRIMARY KEY (candidate_id, alias_index)
) STRICT, WITHOUT ROWID;

CREATE TABLE unverified_candidate_composition (
    candidate_id TEXT NOT NULL
        REFERENCES unverified_entity_candidate(candidate_id) ON DELETE CASCADE,
    component_index INTEGER NOT NULL CHECK (component_index >= 0),
    component_kind TEXT NOT NULL CHECK (
        component_kind IN ('element', 'nuclide', 'species', 'material', 'other')
    ),
    component_name TEXT NOT NULL,
    component_proposed_id TEXT,
    atom_count INTEGER CHECK (atom_count IS NULL OR atom_count > 0),
    evidence_text TEXT NOT NULL,
    PRIMARY KEY (candidate_id, component_index)
) STRICT, WITHOUT ROWID;

CREATE TABLE unverified_candidate_fact (
    candidate_fact_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL
        REFERENCES unverified_entity_candidate(candidate_id) ON DELETE CASCADE,
    fact_index INTEGER NOT NULL CHECK (fact_index >= 0),
    field_key TEXT NOT NULL,
    value_decimal_text TEXT,
    value_numerator INTEGER,
    value_denominator INTEGER CHECK (
        value_denominator IS NULL OR value_denominator > 0
    ),
    value_text TEXT,
    unit_text TEXT,
    uncertainty_decimal_text TEXT,
    uncertainty_numerator INTEGER,
    uncertainty_denominator INTEGER CHECK (
        uncertainty_denominator IS NULL OR uncertainty_denominator > 0
    ),
    evidence_text TEXT NOT NULL,
    UNIQUE (candidate_id, fact_index),
    CHECK (
        value_decimal_text IS NOT NULL OR value_text IS NOT NULL
    ),
    CHECK (
        (value_numerator IS NULL) = (value_denominator IS NULL)
    ),
    CHECK (
        (uncertainty_numerator IS NULL) =
        (uncertainty_denominator IS NULL)
    )
) STRICT;

CREATE TABLE unverified_candidate_fact_condition (
    candidate_fact_id TEXT NOT NULL
        REFERENCES unverified_candidate_fact(candidate_fact_id)
        ON DELETE CASCADE,
    condition_index INTEGER NOT NULL CHECK (condition_index >= 0),
    quantity_kind TEXT NOT NULL,
    value_decimal_text TEXT,
    value_numerator INTEGER,
    value_denominator INTEGER CHECK (
        value_denominator IS NULL OR value_denominator > 0
    ),
    value_text TEXT,
    unit_text TEXT,
    PRIMARY KEY (candidate_fact_id, condition_index),
    CHECK (
        value_decimal_text IS NOT NULL OR value_text IS NOT NULL
    ),
    CHECK (
        (value_numerator IS NULL) = (value_denominator IS NULL)
    )
) STRICT, WITHOUT ROWID;

CREATE TABLE unverified_candidate_relation (
    relation_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL
        REFERENCES unverified_entity_candidate(candidate_id) ON DELETE CASCADE,
    relation_index INTEGER NOT NULL CHECK (relation_index >= 0),
    relation_kind TEXT NOT NULL,
    object_name TEXT NOT NULL,
    object_proposed_id TEXT,
    role TEXT,
    coefficient_decimal_text TEXT,
    coefficient_numerator INTEGER,
    coefficient_denominator INTEGER CHECK (
        coefficient_denominator IS NULL OR coefficient_denominator > 0
    ),
    phase_text TEXT,
    details_text TEXT,
    evidence_text TEXT NOT NULL,
    UNIQUE (candidate_id, relation_index),
    CHECK (
        (coefficient_numerator IS NULL) =
        (coefficient_denominator IS NULL)
    )
) STRICT;
