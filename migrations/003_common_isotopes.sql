PRAGMA user_version = 3;

CREATE TABLE nuclide_designation (
    nuclide_id TEXT NOT NULL REFERENCES nuclide(entity_id) ON DELETE CASCADE,
    designation TEXT NOT NULL CHECK (
        designation IN (
            'natural_isotopic_composition',
            'representative_radioisotope'
        )
    ),
    dataset_id TEXT NOT NULL REFERENCES dataset(dataset_id),
    source_id TEXT NOT NULL REFERENCES source(source_id),
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    PRIMARY KEY (nuclide_id, designation, dataset_id)
) STRICT, WITHOUT ROWID;
