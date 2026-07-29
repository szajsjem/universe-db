PRAGMA user_version = 4;

ALTER TABLE nuclear_channel
ADD COLUMN partial_half_life_observation_id TEXT
    REFERENCES observation(observation_id);

CREATE TABLE nuclear_channel_nuclide (
    channel_id TEXT NOT NULL
        REFERENCES nuclear_channel(channel_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('incident', 'emitted')),
    nuclide_id TEXT NOT NULL REFERENCES nuclide(entity_id),
    count INTEGER NOT NULL CHECK (count > 0),
    PRIMARY KEY (channel_id, role, nuclide_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE nuclear_cross_section_velocity_point (
    channel_id TEXT NOT NULL
        REFERENCES nuclear_channel(channel_id) ON DELETE CASCADE,
    point_index INTEGER NOT NULL CHECK (point_index >= 0),
    speed_numerator INTEGER NOT NULL CHECK (speed_numerator >= 0),
    speed_denominator INTEGER NOT NULL CHECK (speed_denominator > 0),
    speed_unit_id TEXT NOT NULL REFERENCES unit(unit_id),
    cross_section_numerator INTEGER NOT NULL CHECK (
        cross_section_numerator >= 0
    ),
    cross_section_denominator INTEGER NOT NULL CHECK (
        cross_section_denominator > 0
    ),
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

CREATE TABLE research_run (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    model TEXT NOT NULL,
    base_database_sha256 TEXT NOT NULL
        CHECK (length(base_database_sha256) = 64),
    requested_scopes TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('running', 'completed', 'stopped', 'failed')
    ),
    notes TEXT
) STRICT;

CREATE TABLE research_task (
    task_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES research_run(run_id) ON DELETE CASCADE,
    target_kind TEXT NOT NULL CHECK (
        target_kind IN ('element', 'nuclide', 'molecule', 'reaction')
    ),
    target_id TEXT NOT NULL,
    target_label TEXT NOT NULL,
    field_key TEXT NOT NULL,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'pending', 'found', 'not_found', 'ambiguous', 'error', 'skipped'
        )
    ),
    response_id TEXT,
    error_text TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (run_id, target_kind, target_id, field_key)
) STRICT;

CREATE TABLE unverified_fact (
    fact_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES research_task(task_id) ON DELETE CASCADE,
    target_entity_id TEXT REFERENCES entity(entity_id),
    target_kind TEXT NOT NULL,
    target_id TEXT NOT NULL,
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
    relation_kind TEXT,
    related_entity_text TEXT,
    method_notes TEXT,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
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

CREATE TABLE unverified_fact_condition (
    fact_id TEXT NOT NULL
        REFERENCES unverified_fact(fact_id) ON DELETE CASCADE,
    condition_index INTEGER NOT NULL CHECK (condition_index >= 0),
    quantity_kind TEXT NOT NULL,
    value_decimal_text TEXT,
    value_numerator INTEGER,
    value_denominator INTEGER CHECK (
        value_denominator IS NULL OR value_denominator > 0
    ),
    value_text TEXT,
    unit_text TEXT,
    PRIMARY KEY (fact_id, condition_index),
    CHECK (
        value_decimal_text IS NOT NULL OR value_text IS NOT NULL
    ),
    CHECK (
        (value_numerator IS NULL) = (value_denominator IS NULL)
    )
) STRICT, WITHOUT ROWID;

CREATE TABLE unverified_fact_source (
    fact_id TEXT NOT NULL
        REFERENCES unverified_fact(fact_id) ON DELETE CASCADE,
    source_index INTEGER NOT NULL CHECK (source_index >= 0),
    url TEXT NOT NULL,
    title TEXT,
    supporting_text TEXT,
    PRIMARY KEY (fact_id, source_index)
) STRICT, WITHOUT ROWID;
