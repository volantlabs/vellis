"""Connection policy and the fresh VEL2 SQLite schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from vellis.domain import PUBLIC_ITEM_LIMIT

APPLICATION_ID = 0x56454C32  # VEL2
PROTOTYPE_APPLICATION_ID = 0x56454C31  # VEL1
# VEL2 is unreleased during this rebaseline. Once released, any incompatible schema or canonical
# encoding change must select a new user_version rather than silently redefining this format.
USER_VERSION = 1
PROTOTYPE_SCHEMA_VERSION = 5


class DatabaseError(RuntimeError):
    """The selected file is not a supported VEL2 database."""


def connect_database(
    path: Path, *, read_only: bool = False, immutable: bool = False
) -> sqlite3.Connection:
    if immutable and not read_only:
        raise ValueError("immutable connections must be read-only")
    if read_only:
        immutable_query = "&immutable=1" if immutable else ""
        uri = f"{path.resolve().as_uri()}?mode=ro{immutable_query}"
        connection = sqlite3.connect(uri, uri=True, isolation_level=None)
    else:
        connection = sqlite3.connect(path, isolation_level=None)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA trusted_schema = OFF")
        if not read_only:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
        return connection
    except BaseException:
        connection.close()
        raise


def require_supported_database(connection: sqlite3.Connection) -> None:
    application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
    user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if application_id == PROTOTYPE_APPLICATION_ID and user_version in {
        0,
        PROTOTYPE_SCHEMA_VERSION,
    }:
        raise DatabaseError(
            "This is an unreleased prototype-v2 VEL1 database (schema 5). "
            "VEL2 intentionally does not migrate it; initialize a fresh database."
        )
    if application_id != APPLICATION_ID or user_version != USER_VERSION:
        raise DatabaseError(
            f"Unsupported database identity: application_id={application_id}, "
            f"user_version={user_version}; expected VEL2 schema 1"
        )
    row = connection.execute(
        "SELECT lineage_uuid, head_revision FROM metadata_setting WHERE singleton = 1"
    ).fetchone()
    if row is None:
        raise DatabaseError("VEL2 database metadata is absent")


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(_SCHEMA)
    connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
    connection.execute(f"PRAGMA user_version = {USER_VERSION}")


_SCHEMA = f"""
CREATE TABLE metadata_setting (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    lineage_uuid TEXT NOT NULL CHECK (
        length(lineage_uuid) = 36
        AND substr(lineage_uuid, 9, 1) = '-'
        AND substr(lineage_uuid, 14, 1) = '-'
        AND substr(lineage_uuid, 19, 1) = '-'
        AND substr(lineage_uuid, 24, 1) = '-'
    ),
    head_revision INTEGER NOT NULL REFERENCES canonical_record(revision)
        CHECK (head_revision >= 0),
    activity_mode TEXT NOT NULL DEFAULT 'semantic'
        CHECK (activity_mode IN ('semantic', 'verbose')),
    last_activity_sequence INTEGER NOT NULL DEFAULT 0 CHECK (last_activity_sequence >= 0),
    last_activity_time TEXT
) STRICT;

CREATE TABLE canonical_record (
    revision INTEGER PRIMARY KEY CHECK (revision >= 0),
    recorded_at TEXT NOT NULL,
    recorded_epoch_seconds INTEGER NOT NULL,
    recorded_nanosecond INTEGER NOT NULL CHECK (recorded_nanosecond BETWEEN 0 AND 999999999),
    initiator TEXT NOT NULL,
    source TEXT,
    transition_kind TEXT NOT NULL CHECK (
        transition_kind IN ('initialization', 'graphChange', 'draftActivation', 'restore')
    ),
    summary TEXT NOT NULL,
    affected_type_keys TEXT NOT NULL DEFAULT '[]',
    affected_uuids TEXT NOT NULL DEFAULT '[]',
    previous_hash BLOB NOT NULL CHECK (length(previous_hash) = 32),
    record_hash BLOB NOT NULL CHECK (length(record_hash) = 32),
    v1_report_digest BLOB CHECK (v1_report_digest IS NULL OR length(v1_report_digest) = 32)
) STRICT;
CREATE INDEX canonical_record_time_idx
    ON canonical_record(recorded_epoch_seconds, recorded_nanosecond, revision);

CREATE TABLE graph_object_identity (
    uuid TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('anchor', 'associatedData', 'link')),
    created_revision INTEGER NOT NULL REFERENCES canonical_record(revision),
    legacy_v1 TEXT
) STRICT;

CREATE TABLE graph_object_version (
    uuid TEXT NOT NULL REFERENCES graph_object_identity(uuid),
    valid_from_revision INTEGER NOT NULL REFERENCES canonical_record(revision),
    valid_to_revision INTEGER REFERENCES canonical_record(revision),
    kind TEXT NOT NULL CHECK (kind IN ('anchor', 'associatedData', 'link')),
    type_key TEXT NOT NULL REFERENCES type_key_identity(type_key),
    display_name TEXT,
    source_uuid TEXT REFERENCES graph_object_identity(uuid),
    target_uuid TEXT REFERENCES graph_object_identity(uuid),
    last_changed_revision INTEGER NOT NULL REFERENCES canonical_record(revision),
    row_digest BLOB NOT NULL CHECK (length(row_digest) = 32),
    PRIMARY KEY (uuid, valid_from_revision),
    CHECK (valid_to_revision IS NULL OR valid_to_revision > valid_from_revision),
    CHECK (last_changed_revision = valid_from_revision),
    CHECK (
        (kind = 'anchor' AND display_name IS NOT NULL
            AND source_uuid IS NULL AND target_uuid IS NULL)
        OR (kind = 'associatedData' AND display_name IS NULL
            AND source_uuid IS NULL AND target_uuid IS NULL)
        OR (kind = 'link' AND display_name IS NULL
            AND source_uuid IS NOT NULL AND target_uuid IS NOT NULL)
    )
) STRICT;
CREATE UNIQUE INDEX graph_object_one_current_idx
    ON graph_object_version(uuid) WHERE valid_to_revision IS NULL;
CREATE INDEX graph_object_uuid_interval_idx
    ON graph_object_version(uuid, valid_from_revision, valid_to_revision);
CREATE INDEX graph_object_kind_type_interval_idx
    ON graph_object_version(kind, type_key, valid_from_revision, valid_to_revision);
CREATE INDEX graph_object_source_interval_idx
    ON graph_object_version(source_uuid, valid_from_revision, valid_to_revision);
CREATE INDEX graph_object_target_interval_idx
    ON graph_object_version(target_uuid, valid_from_revision, valid_to_revision);

CREATE TABLE direct_association_version (
    object_uuid TEXT NOT NULL REFERENCES graph_object_identity(uuid),
    anchor_uuid TEXT NOT NULL REFERENCES graph_object_identity(uuid),
    valid_from_revision INTEGER NOT NULL REFERENCES canonical_record(revision),
    valid_to_revision INTEGER REFERENCES canonical_record(revision),
    row_digest BLOB NOT NULL CHECK (length(row_digest) = 32),
    PRIMARY KEY (object_uuid, anchor_uuid, valid_from_revision),
    FOREIGN KEY (object_uuid, valid_from_revision)
        REFERENCES graph_object_version(uuid, valid_from_revision),
    CHECK (valid_to_revision IS NULL OR valid_to_revision > valid_from_revision)
) STRICT;
CREATE UNIQUE INDEX association_one_current_idx
    ON direct_association_version(object_uuid, anchor_uuid) WHERE valid_to_revision IS NULL;
CREATE INDEX association_object_interval_idx
    ON direct_association_version(object_uuid, valid_from_revision, valid_to_revision);
CREATE INDEX association_anchor_interval_idx
    ON direct_association_version(anchor_uuid, valid_from_revision, valid_to_revision);

CREATE TABLE property_version (
    object_uuid TEXT NOT NULL REFERENCES graph_object_identity(uuid),
    property_name TEXT NOT NULL,
    valid_from_revision INTEGER NOT NULL REFERENCES canonical_record(revision),
    valid_to_revision INTEGER REFERENCES canonical_record(revision),
    value_kind TEXT NOT NULL CHECK (
        value_kind IN ('boolean', 'integer', 'number', 'text', 'date', 'timestamp')
    ),
    is_null INTEGER NOT NULL CHECK (is_null IN (0, 1)),
    boolean_value INTEGER CHECK (boolean_value IN (0, 1)),
    integer_value INTEGER,
    number_value REAL,
    text_value TEXT,
    date_value TEXT,
    timestamp_epoch_seconds INTEGER,
    timestamp_nanosecond INTEGER CHECK (
        timestamp_nanosecond IS NULL OR timestamp_nanosecond BETWEEN 0 AND 999999999
    ),
    timestamp_text TEXT,
    row_digest BLOB NOT NULL CHECK (length(row_digest) = 32),
    PRIMARY KEY (object_uuid, property_name, valid_from_revision),
    FOREIGN KEY (object_uuid, valid_from_revision)
        REFERENCES graph_object_version(uuid, valid_from_revision),
    CHECK (valid_to_revision IS NULL OR valid_to_revision > valid_from_revision),
    CHECK (
        (is_null = 1 AND boolean_value IS NULL AND integer_value IS NULL
            AND number_value IS NULL AND text_value IS NULL AND date_value IS NULL
            AND timestamp_epoch_seconds IS NULL AND timestamp_nanosecond IS NULL
            AND timestamp_text IS NULL)
        OR
        (is_null = 0 AND
            (boolean_value IS NOT NULL) + (integer_value IS NOT NULL)
            + (number_value IS NOT NULL) + (text_value IS NOT NULL)
            + (date_value IS NOT NULL) + (timestamp_text IS NOT NULL) = 1)
    ),
    CHECK (
        is_null = 1
        OR (value_kind = 'boolean' AND boolean_value IS NOT NULL)
        OR (value_kind = 'integer' AND integer_value IS NOT NULL)
        OR (value_kind = 'number' AND number_value IS NOT NULL)
        OR (value_kind = 'text' AND text_value IS NOT NULL)
        OR (value_kind = 'date' AND date_value IS NOT NULL)
        OR (value_kind = 'timestamp' AND timestamp_text IS NOT NULL
            AND timestamp_epoch_seconds IS NOT NULL AND timestamp_nanosecond IS NOT NULL)
    ),
    CHECK (
        is_null = 1
        OR (value_kind = 'timestamp' AND timestamp_text IS NOT NULL
            AND timestamp_epoch_seconds IS NOT NULL AND timestamp_nanosecond IS NOT NULL)
        OR (value_kind <> 'timestamp' AND timestamp_text IS NULL
            AND timestamp_epoch_seconds IS NULL AND timestamp_nanosecond IS NULL)
    )
) STRICT;
CREATE UNIQUE INDEX property_one_current_idx
    ON property_version(object_uuid, property_name) WHERE valid_to_revision IS NULL;
CREATE INDEX property_owner_interval_idx
    ON property_version(object_uuid, property_name, valid_from_revision, valid_to_revision);
CREATE INDEX property_typed_value_interval_idx
    ON property_version(property_name, value_kind, boolean_value, integer_value, number_value,
        text_value, date_value, timestamp_epoch_seconds, timestamp_nanosecond,
        valid_from_revision, valid_to_revision);

CREATE TABLE type_key_identity (
    type_key TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('anchor', 'associatedData', 'link')),
    created_revision INTEGER NOT NULL REFERENCES canonical_record(revision),
    legacy_v1 TEXT
) STRICT;

CREATE TABLE definition_version (
    type_key TEXT NOT NULL REFERENCES type_key_identity(type_key),
    valid_from_revision INTEGER NOT NULL REFERENCES canonical_record(revision),
    valid_to_revision INTEGER REFERENCES canonical_record(revision),
    kind TEXT NOT NULL CHECK (kind IN ('anchor', 'associatedData', 'link')),
    description TEXT NOT NULL,
    anchors_per_object_minimum TEXT,
    anchors_per_object_maximum TEXT,
    objects_per_anchor_minimum TEXT,
    objects_per_anchor_maximum TEXT,
    links_per_source_minimum TEXT,
    links_per_source_maximum TEXT,
    links_per_target_minimum TEXT,
    links_per_target_maximum TEXT,
    last_changed_revision INTEGER NOT NULL REFERENCES canonical_record(revision),
    row_digest BLOB NOT NULL CHECK (length(row_digest) = 32),
    PRIMARY KEY (type_key, valid_from_revision),
    CHECK (valid_to_revision IS NULL OR valid_to_revision > valid_from_revision),
    CHECK (last_changed_revision = valid_from_revision),
    CHECK (
        (kind = 'anchor'
            AND anchors_per_object_minimum IS NULL
            AND anchors_per_object_maximum IS NULL
            AND objects_per_anchor_minimum IS NULL
            AND objects_per_anchor_maximum IS NULL
            AND links_per_source_minimum IS NULL
            AND links_per_source_maximum IS NULL
            AND links_per_target_minimum IS NULL
            AND links_per_target_maximum IS NULL)
        OR (kind = 'associatedData'
            AND anchors_per_object_minimum <> ''
            AND anchors_per_object_minimum NOT GLOB '*[^0-9]*'
            AND anchors_per_object_minimum NOT LIKE '0%'
            AND (anchors_per_object_maximum IS NULL
                OR ((anchors_per_object_maximum = '0'
                        OR (anchors_per_object_maximum <> ''
                            AND anchors_per_object_maximum NOT GLOB '*[^0-9]*'
                            AND anchors_per_object_maximum NOT LIKE '0%'))
                    AND (length(anchors_per_object_maximum)
                            > length(anchors_per_object_minimum)
                        OR (length(anchors_per_object_maximum)
                                = length(anchors_per_object_minimum)
                            AND anchors_per_object_maximum
                                >= anchors_per_object_minimum))))
            AND (objects_per_anchor_minimum = '0'
                OR (objects_per_anchor_minimum <> ''
                    AND objects_per_anchor_minimum NOT GLOB '*[^0-9]*'
                    AND objects_per_anchor_minimum NOT LIKE '0%'))
            AND (objects_per_anchor_maximum IS NULL
                OR ((objects_per_anchor_maximum = '0'
                        OR (objects_per_anchor_maximum <> ''
                            AND objects_per_anchor_maximum NOT GLOB '*[^0-9]*'
                            AND objects_per_anchor_maximum NOT LIKE '0%'))
                    AND (length(objects_per_anchor_maximum)
                            > length(objects_per_anchor_minimum)
                        OR (length(objects_per_anchor_maximum)
                                = length(objects_per_anchor_minimum)
                            AND objects_per_anchor_maximum >= objects_per_anchor_minimum))))
            AND links_per_source_minimum IS NULL
            AND links_per_source_maximum IS NULL
            AND links_per_target_minimum IS NULL
            AND links_per_target_maximum IS NULL)
        OR (kind = 'link'
            AND anchors_per_object_minimum IS NULL
            AND anchors_per_object_maximum IS NULL
            AND objects_per_anchor_minimum IS NULL
            AND objects_per_anchor_maximum IS NULL
            AND (links_per_source_minimum = '0'
                OR (links_per_source_minimum <> ''
                    AND links_per_source_minimum NOT GLOB '*[^0-9]*'
                    AND links_per_source_minimum NOT LIKE '0%'))
            AND (links_per_source_maximum IS NULL
                OR ((links_per_source_maximum = '0'
                        OR (links_per_source_maximum <> ''
                            AND links_per_source_maximum NOT GLOB '*[^0-9]*'
                            AND links_per_source_maximum NOT LIKE '0%'))
                    AND (length(links_per_source_maximum) > length(links_per_source_minimum)
                        OR (length(links_per_source_maximum)
                                = length(links_per_source_minimum)
                            AND links_per_source_maximum >= links_per_source_minimum))))
            AND (links_per_target_minimum = '0'
                OR (links_per_target_minimum <> ''
                    AND links_per_target_minimum NOT GLOB '*[^0-9]*'
                    AND links_per_target_minimum NOT LIKE '0%'))
            AND (links_per_target_maximum IS NULL
                OR ((links_per_target_maximum = '0'
                        OR (links_per_target_maximum <> ''
                            AND links_per_target_maximum NOT GLOB '*[^0-9]*'
                            AND links_per_target_maximum NOT LIKE '0%'))
                    AND (length(links_per_target_maximum) > length(links_per_target_minimum)
                        OR (length(links_per_target_maximum)
                                = length(links_per_target_minimum)
                            AND links_per_target_maximum >= links_per_target_minimum)))))
    )
) STRICT;
CREATE UNIQUE INDEX definition_one_current_idx
    ON definition_version(type_key) WHERE valid_to_revision IS NULL;
CREATE INDEX definition_kind_interval_idx
    ON definition_version(kind, type_key, valid_from_revision, valid_to_revision);

CREATE TABLE definition_permitted_type (
    type_key TEXT NOT NULL REFERENCES type_key_identity(type_key),
    role TEXT NOT NULL CHECK (role IN ('anchor', 'source', 'target')),
    permitted_type_key TEXT NOT NULL REFERENCES type_key_identity(type_key),
    valid_from_revision INTEGER NOT NULL REFERENCES canonical_record(revision),
    valid_to_revision INTEGER REFERENCES canonical_record(revision),
    row_digest BLOB NOT NULL CHECK (length(row_digest) = 32),
    PRIMARY KEY (type_key, role, permitted_type_key, valid_from_revision),
    FOREIGN KEY (type_key, valid_from_revision)
        REFERENCES definition_version(type_key, valid_from_revision),
    CHECK (valid_to_revision IS NULL OR valid_to_revision > valid_from_revision)
) STRICT;
CREATE UNIQUE INDEX permitted_type_one_current_idx
    ON definition_permitted_type(type_key, role, permitted_type_key)
    WHERE valid_to_revision IS NULL;
CREATE INDEX permitted_type_interval_idx
    ON definition_permitted_type(type_key, role, valid_from_revision, valid_to_revision);

CREATE TABLE property_definition_version (
    type_key TEXT NOT NULL REFERENCES type_key_identity(type_key),
    property_name TEXT NOT NULL,
    valid_from_revision INTEGER NOT NULL REFERENCES canonical_record(revision),
    valid_to_revision INTEGER REFERENCES canonical_record(revision),
    description TEXT NOT NULL,
    value_kind TEXT NOT NULL CHECK (
        value_kind IN ('boolean', 'integer', 'number', 'text', 'date', 'timestamp')
    ),
    required INTEGER NOT NULL CHECK (required IN (0, 1)),
    nullable INTEGER NOT NULL CHECK (nullable IN (0, 1)),
    minimum_kind TEXT,
    minimum_integer INTEGER,
    minimum_number REAL,
    minimum_date TEXT,
    minimum_timestamp_epoch_seconds INTEGER,
    minimum_timestamp_nanosecond INTEGER,
    minimum_timestamp_text TEXT,
    maximum_kind TEXT,
    maximum_integer INTEGER,
    maximum_number REAL,
    maximum_date TEXT,
    maximum_timestamp_epoch_seconds INTEGER,
    maximum_timestamp_nanosecond INTEGER,
    maximum_timestamp_text TEXT,
    minimum_length TEXT CHECK (
        minimum_length IS NULL OR minimum_length = '0'
        OR (minimum_length <> '' AND minimum_length NOT GLOB '*[^0-9]*'
            AND minimum_length NOT LIKE '0%')
    ),
    maximum_length TEXT CHECK (
        maximum_length IS NULL OR maximum_length = '0'
        OR (maximum_length <> '' AND maximum_length NOT GLOB '*[^0-9]*'
            AND maximum_length NOT LIKE '0%')
    ),
    pattern TEXT,
    row_digest BLOB NOT NULL CHECK (length(row_digest) = 32),
    PRIMARY KEY (type_key, property_name, valid_from_revision),
    FOREIGN KEY (type_key, valid_from_revision)
        REFERENCES definition_version(type_key, valid_from_revision),
    CHECK (valid_to_revision IS NULL OR valid_to_revision > valid_from_revision),
    CHECK (
        (minimum_integer IS NOT NULL) + (minimum_number IS NOT NULL)
        + (minimum_date IS NOT NULL) + (minimum_timestamp_text IS NOT NULL)
        = (minimum_kind IS NOT NULL)
    ),
    CHECK (
        (maximum_integer IS NOT NULL) + (maximum_number IS NOT NULL)
        + (maximum_date IS NOT NULL) + (maximum_timestamp_text IS NOT NULL)
        = (maximum_kind IS NOT NULL)
    ),
    CHECK (
        (minimum_kind IS NULL AND minimum_integer IS NULL AND minimum_number IS NULL
            AND minimum_date IS NULL AND minimum_timestamp_text IS NULL)
        OR (minimum_kind = 'integer' AND minimum_integer IS NOT NULL)
        OR (minimum_kind = 'number' AND minimum_number IS NOT NULL)
        OR (minimum_kind = 'date' AND minimum_date IS NOT NULL)
        OR (minimum_kind = 'timestamp' AND minimum_timestamp_text IS NOT NULL
            AND minimum_timestamp_epoch_seconds IS NOT NULL
            AND minimum_timestamp_nanosecond IS NOT NULL)
    ),
    CHECK (
        (maximum_kind IS NULL AND maximum_integer IS NULL AND maximum_number IS NULL
            AND maximum_date IS NULL AND maximum_timestamp_text IS NULL)
        OR (maximum_kind = 'integer' AND maximum_integer IS NOT NULL)
        OR (maximum_kind = 'number' AND maximum_number IS NOT NULL)
        OR (maximum_kind = 'date' AND maximum_date IS NOT NULL)
        OR (maximum_kind = 'timestamp' AND maximum_timestamp_text IS NOT NULL
            AND maximum_timestamp_epoch_seconds IS NOT NULL
            AND maximum_timestamp_nanosecond IS NOT NULL)
    ),
    CHECK (
        (minimum_kind = 'timestamp' AND minimum_timestamp_text IS NOT NULL
            AND minimum_timestamp_epoch_seconds IS NOT NULL
            AND minimum_timestamp_nanosecond IS NOT NULL)
        OR (coalesce(minimum_kind, '') <> 'timestamp'
            AND minimum_timestamp_text IS NULL
            AND minimum_timestamp_epoch_seconds IS NULL
            AND minimum_timestamp_nanosecond IS NULL)
    ),
    CHECK (
        (maximum_kind = 'timestamp' AND maximum_timestamp_text IS NOT NULL
            AND maximum_timestamp_epoch_seconds IS NOT NULL
            AND maximum_timestamp_nanosecond IS NOT NULL)
        OR (coalesce(maximum_kind, '') <> 'timestamp'
            AND maximum_timestamp_text IS NULL
            AND maximum_timestamp_epoch_seconds IS NULL
            AND maximum_timestamp_nanosecond IS NULL)
    ),
    CHECK (
        minimum_length IS NULL OR maximum_length IS NULL
        OR length(maximum_length) > length(minimum_length)
        OR (length(maximum_length) = length(minimum_length)
            AND maximum_length >= minimum_length)
    )
) STRICT;
CREATE UNIQUE INDEX property_definition_one_current_idx
    ON property_definition_version(type_key, property_name) WHERE valid_to_revision IS NULL;
CREATE INDEX property_definition_interval_idx
    ON property_definition_version(type_key, property_name, valid_from_revision, valid_to_revision);

CREATE TABLE property_definition_allowed_value (
    type_key TEXT NOT NULL REFERENCES type_key_identity(type_key),
    property_name TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    valid_from_revision INTEGER NOT NULL REFERENCES canonical_record(revision),
    valid_to_revision INTEGER REFERENCES canonical_record(revision),
    value_kind TEXT NOT NULL CHECK (
        value_kind IN ('boolean', 'integer', 'number', 'text', 'date', 'timestamp')
    ),
    boolean_value INTEGER CHECK (boolean_value IN (0, 1)),
    integer_value INTEGER,
    number_value REAL,
    text_value TEXT,
    date_value TEXT,
    timestamp_epoch_seconds INTEGER,
    timestamp_nanosecond INTEGER CHECK (
        timestamp_nanosecond IS NULL OR timestamp_nanosecond BETWEEN 0 AND 999999999
    ),
    timestamp_text TEXT,
    row_digest BLOB NOT NULL CHECK (length(row_digest) = 32),
    PRIMARY KEY (type_key, property_name, ordinal, valid_from_revision),
    FOREIGN KEY (type_key, property_name, valid_from_revision)
        REFERENCES property_definition_version(type_key, property_name, valid_from_revision),
    CHECK (valid_to_revision IS NULL OR valid_to_revision > valid_from_revision),
    CHECK (
        (boolean_value IS NOT NULL) + (integer_value IS NOT NULL)
        + (number_value IS NOT NULL) + (text_value IS NOT NULL)
        + (date_value IS NOT NULL) + (timestamp_text IS NOT NULL) = 1
    ),
    CHECK (
        (value_kind = 'boolean' AND boolean_value IS NOT NULL)
        OR (value_kind = 'integer' AND integer_value IS NOT NULL)
        OR (value_kind = 'number' AND number_value IS NOT NULL)
        OR (value_kind = 'text' AND text_value IS NOT NULL)
        OR (value_kind = 'date' AND date_value IS NOT NULL)
        OR (value_kind = 'timestamp' AND timestamp_text IS NOT NULL
            AND timestamp_epoch_seconds IS NOT NULL AND timestamp_nanosecond IS NOT NULL)
    ),
    CHECK (
        (value_kind = 'timestamp' AND timestamp_text IS NOT NULL
            AND timestamp_epoch_seconds IS NOT NULL AND timestamp_nanosecond IS NOT NULL)
        OR (value_kind <> 'timestamp' AND timestamp_text IS NULL
            AND timestamp_epoch_seconds IS NULL AND timestamp_nanosecond IS NULL)
    )
) STRICT;
CREATE UNIQUE INDEX allowed_value_one_current_idx
    ON property_definition_allowed_value(type_key, property_name, ordinal)
    WHERE valid_to_revision IS NULL;

CREATE TABLE draft_metadata (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    fingerprint BLOB,
    inspect_cursor_hash BLOB,
    inspect_cursor_state TEXT
) STRICT;
CREATE TABLE draft_definition_entry (
    type_key TEXT PRIMARY KEY,
    operation TEXT NOT NULL CHECK (operation IN ('replace', 'remove')),
    kind TEXT CHECK (kind IN ('anchor', 'associatedData', 'link')),
    description TEXT,
    anchors_per_object_minimum TEXT,
    anchors_per_object_maximum TEXT,
    objects_per_anchor_minimum TEXT,
    objects_per_anchor_maximum TEXT,
    links_per_source_minimum TEXT,
    links_per_source_maximum TEXT,
    links_per_target_minimum TEXT,
    links_per_target_maximum TEXT,
    CHECK (
        (operation = 'remove' AND kind IS NULL AND description IS NULL)
        OR (operation = 'replace' AND kind IS NOT NULL AND description IS NOT NULL)
    )
) STRICT;
CREATE TABLE draft_definition_permitted_type (
    type_key TEXT NOT NULL,
    role TEXT NOT NULL,
    permitted_type_key TEXT NOT NULL,
    PRIMARY KEY (type_key, role, permitted_type_key)
) STRICT;
CREATE TABLE draft_property_definition_entry (
    type_key TEXT NOT NULL,
    property_name TEXT NOT NULL,
    description TEXT NOT NULL,
    value_kind TEXT NOT NULL CHECK (
        value_kind IN ('boolean', 'integer', 'number', 'text', 'date', 'timestamp')
    ),
    required INTEGER NOT NULL CHECK (required IN (0, 1)),
    nullable INTEGER NOT NULL CHECK (nullable IN (0, 1)),
    allowed_values_present INTEGER NOT NULL CHECK (allowed_values_present IN (0, 1)),
    minimum_kind TEXT,
    minimum_boolean INTEGER CHECK (minimum_boolean IN (0, 1)),
    minimum_integer INTEGER,
    minimum_number REAL,
    minimum_text TEXT,
    minimum_date TEXT,
    minimum_timestamp_epoch_seconds INTEGER,
    minimum_timestamp_nanosecond INTEGER,
    minimum_timestamp_text TEXT,
    maximum_kind TEXT,
    maximum_boolean INTEGER CHECK (maximum_boolean IN (0, 1)),
    maximum_integer INTEGER,
    maximum_number REAL,
    maximum_text TEXT,
    maximum_date TEXT,
    maximum_timestamp_epoch_seconds INTEGER,
    maximum_timestamp_nanosecond INTEGER,
    maximum_timestamp_text TEXT,
    minimum_length TEXT,
    maximum_length TEXT,
    pattern TEXT,
    PRIMARY KEY (type_key, property_name),
    CHECK (
        (minimum_boolean IS NOT NULL) + (minimum_integer IS NOT NULL)
        + (minimum_number IS NOT NULL) + (minimum_text IS NOT NULL)
        + (minimum_date IS NOT NULL) + (minimum_timestamp_text IS NOT NULL)
        = (minimum_kind IS NOT NULL)
    ),
    CHECK (
        (maximum_boolean IS NOT NULL) + (maximum_integer IS NOT NULL)
        + (maximum_number IS NOT NULL) + (maximum_text IS NOT NULL)
        + (maximum_date IS NOT NULL) + (maximum_timestamp_text IS NOT NULL)
        = (maximum_kind IS NOT NULL)
    ),
    CHECK (
        (minimum_kind IS NULL AND minimum_boolean IS NULL AND minimum_integer IS NULL
            AND minimum_number IS NULL AND minimum_text IS NULL AND minimum_date IS NULL
            AND minimum_timestamp_text IS NULL)
        OR (minimum_kind = 'boolean' AND minimum_boolean IS NOT NULL)
        OR (minimum_kind = 'integer' AND minimum_integer IS NOT NULL)
        OR (minimum_kind = 'number' AND minimum_number IS NOT NULL)
        OR (minimum_kind = 'text' AND minimum_text IS NOT NULL)
        OR (minimum_kind = 'date' AND minimum_date IS NOT NULL)
        OR (minimum_kind = 'timestamp' AND minimum_timestamp_text IS NOT NULL
            AND minimum_timestamp_epoch_seconds IS NOT NULL
            AND minimum_timestamp_nanosecond IS NOT NULL)
    ),
    CHECK (
        (maximum_kind IS NULL AND maximum_boolean IS NULL AND maximum_integer IS NULL
            AND maximum_number IS NULL AND maximum_text IS NULL AND maximum_date IS NULL
            AND maximum_timestamp_text IS NULL)
        OR (maximum_kind = 'boolean' AND maximum_boolean IS NOT NULL)
        OR (maximum_kind = 'integer' AND maximum_integer IS NOT NULL)
        OR (maximum_kind = 'number' AND maximum_number IS NOT NULL)
        OR (maximum_kind = 'text' AND maximum_text IS NOT NULL)
        OR (maximum_kind = 'date' AND maximum_date IS NOT NULL)
        OR (maximum_kind = 'timestamp' AND maximum_timestamp_text IS NOT NULL
            AND maximum_timestamp_epoch_seconds IS NOT NULL
            AND maximum_timestamp_nanosecond IS NOT NULL)
    ),
    CHECK (
        (minimum_kind = 'timestamp' AND minimum_timestamp_text IS NOT NULL
            AND minimum_timestamp_epoch_seconds IS NOT NULL
            AND minimum_timestamp_nanosecond IS NOT NULL)
        OR (coalesce(minimum_kind, '') <> 'timestamp'
            AND minimum_timestamp_text IS NULL
            AND minimum_timestamp_epoch_seconds IS NULL
            AND minimum_timestamp_nanosecond IS NULL)
    ),
    CHECK (
        (maximum_kind = 'timestamp' AND maximum_timestamp_text IS NOT NULL
            AND maximum_timestamp_epoch_seconds IS NOT NULL
            AND maximum_timestamp_nanosecond IS NOT NULL)
        OR (coalesce(maximum_kind, '') <> 'timestamp'
            AND maximum_timestamp_text IS NULL
            AND maximum_timestamp_epoch_seconds IS NULL
            AND maximum_timestamp_nanosecond IS NULL)
    )
) STRICT;
CREATE TABLE draft_property_definition_allowed_value (
    type_key TEXT NOT NULL,
    property_name TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    value_kind TEXT NOT NULL,
    boolean_value INTEGER CHECK (boolean_value IN (0, 1)),
    integer_value INTEGER,
    number_value REAL,
    text_value TEXT,
    date_value TEXT,
    timestamp_epoch_seconds INTEGER,
    timestamp_nanosecond INTEGER,
    timestamp_text TEXT,
    PRIMARY KEY (type_key, property_name, ordinal),
    CHECK (
        (boolean_value IS NOT NULL) + (integer_value IS NOT NULL)
        + (number_value IS NOT NULL) + (text_value IS NOT NULL)
        + (date_value IS NOT NULL) + (timestamp_text IS NOT NULL) = 1
    ),
    CHECK (
        (value_kind = 'boolean' AND boolean_value IS NOT NULL)
        OR (value_kind = 'integer' AND integer_value IS NOT NULL)
        OR (value_kind = 'number' AND number_value IS NOT NULL)
        OR (value_kind = 'text' AND text_value IS NOT NULL)
        OR (value_kind = 'date' AND date_value IS NOT NULL)
        OR (value_kind = 'timestamp' AND timestamp_text IS NOT NULL
            AND timestamp_epoch_seconds IS NOT NULL AND timestamp_nanosecond IS NOT NULL)
    ),
    CHECK (
        (value_kind = 'timestamp' AND timestamp_text IS NOT NULL
            AND timestamp_epoch_seconds IS NOT NULL AND timestamp_nanosecond IS NOT NULL)
        OR (value_kind <> 'timestamp' AND timestamp_text IS NULL
            AND timestamp_epoch_seconds IS NULL AND timestamp_nanosecond IS NULL)
    )
) STRICT;
CREATE TABLE draft_graph_object_patch (
    uuid TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('anchor', 'associatedData', 'link')),
    tombstone INTEGER NOT NULL DEFAULT 0 CHECK (tombstone IN (0, 1)),
    has_type_key INTEGER NOT NULL DEFAULT 0 CHECK (has_type_key IN (0, 1)),
    type_key TEXT,
    has_display_name INTEGER NOT NULL DEFAULT 0 CHECK (has_display_name IN (0, 1)),
    display_name TEXT,
    has_source_uuid INTEGER NOT NULL DEFAULT 0 CHECK (has_source_uuid IN (0, 1)),
    source_uuid TEXT,
    has_target_uuid INTEGER NOT NULL DEFAULT 0 CHECK (has_target_uuid IN (0, 1)),
    target_uuid TEXT,
    has_complete_anchor_set INTEGER NOT NULL DEFAULT 0
        CHECK (has_complete_anchor_set IN (0, 1)),
    CHECK (has_type_key = (type_key IS NOT NULL)),
    CHECK (has_display_name = (display_name IS NOT NULL)),
    CHECK (has_source_uuid = (source_uuid IS NOT NULL)),
    CHECK (has_target_uuid = (target_uuid IS NOT NULL)),
    CHECK (
        tombstone = 0 OR (
            has_type_key = 0 AND has_display_name = 0 AND has_source_uuid = 0
            AND has_target_uuid = 0 AND has_complete_anchor_set = 0
        )
    )
) STRICT;
CREATE TABLE draft_association_operation (
    object_uuid TEXT NOT NULL,
    anchor_uuid TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('base', 'add', 'remove')),
    PRIMARY KEY (object_uuid, anchor_uuid)
) STRICT;
CREATE TABLE draft_property_operation (
    object_uuid TEXT NOT NULL,
    property_name TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('set', 'remove')),
    value_kind TEXT,
    is_null INTEGER CHECK (is_null IN (0, 1)),
    boolean_value INTEGER CHECK (boolean_value IN (0, 1)),
    integer_value INTEGER,
    number_value REAL,
    text_value TEXT,
    date_value TEXT,
    timestamp_epoch_seconds INTEGER,
    timestamp_nanosecond INTEGER,
    timestamp_text TEXT,
    CHECK (
        operation = 'remove'
        OR (operation = 'set' AND is_null = 1 AND value_kind IS NULL)
        OR (operation = 'set' AND is_null = 0 AND value_kind IS NOT NULL)
    ),
    CHECK (
        operation = 'remove' OR is_null = 1 OR (
            (boolean_value IS NOT NULL) + (integer_value IS NOT NULL)
            + (number_value IS NOT NULL) + (text_value IS NOT NULL)
            + (date_value IS NOT NULL) + (timestamp_text IS NOT NULL) = 1
        )
    ),
    CHECK (
        operation = 'remove' OR is_null = 1
        OR (value_kind = 'boolean' AND boolean_value IS NOT NULL)
        OR (value_kind = 'integer' AND integer_value IS NOT NULL)
        OR (value_kind = 'number' AND number_value IS NOT NULL)
        OR (value_kind = 'text' AND text_value IS NOT NULL)
        OR (value_kind = 'date' AND date_value IS NOT NULL)
        OR (value_kind = 'timestamp' AND timestamp_text IS NOT NULL
            AND timestamp_epoch_seconds IS NOT NULL AND timestamp_nanosecond IS NOT NULL)
    ),
    CHECK (
        operation = 'remove' OR is_null = 1
        OR (value_kind = 'timestamp' AND timestamp_text IS NOT NULL
            AND timestamp_epoch_seconds IS NOT NULL AND timestamp_nanosecond IS NOT NULL)
        OR (value_kind <> 'timestamp' AND timestamp_text IS NULL
            AND timestamp_epoch_seconds IS NULL AND timestamp_nanosecond IS NULL)
    ),
    PRIMARY KEY (object_uuid, property_name)
) STRICT;

CREATE TABLE validation_run (
    scope TEXT PRIMARY KEY CHECK (scope IN ('current', 'draft')),
    evaluated_revision INTEGER NOT NULL,
    draft_fingerprint BLOB,
    total_findings INTEGER NOT NULL,
    raw_draft_entry_count INTEGER,
    effective_draft_change_count INTEGER,
    cursor_hash BLOB,
    next_offset INTEGER,
    page_limit INTEGER CHECK (page_limit IS NULL OR page_limit BETWEEN 1 AND {PUBLIC_ITEM_LIMIT})
) STRICT;
CREATE TABLE validation_finding (
    scope TEXT NOT NULL REFERENCES validation_run(scope) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    finding TEXT NOT NULL,
    PRIMARY KEY (scope, ordinal)
) STRICT;

CREATE TABLE activity_header (
    sequence INTEGER PRIMARY KEY CHECK (sequence > 0),
    recorded_at TEXT NOT NULL,
    recorded_epoch_seconds INTEGER NOT NULL,
    recorded_nanosecond INTEGER NOT NULL,
    capability TEXT NOT NULL,
    outcome TEXT NOT NULL,
    initiator TEXT NOT NULL,
    source TEXT,
    evaluated_revision INTEGER,
    resulting_revision INTEGER,
    summary TEXT NOT NULL
) STRICT;
CREATE INDEX activity_time_idx
    ON activity_header(recorded_epoch_seconds, recorded_nanosecond, sequence);
CREATE TABLE activity_payload (
    sequence INTEGER PRIMARY KEY REFERENCES activity_header(sequence) ON DELETE CASCADE,
    semantic_payload TEXT NOT NULL,
    verbose_payload TEXT
) STRICT;

CREATE TABLE search_document (
    document_id INTEGER PRIMARY KEY,
    object_uuid TEXT NOT NULL REFERENCES graph_object_identity(uuid),
    kind TEXT NOT NULL CHECK (kind IN ('anchor', 'associatedData')),
    type_key TEXT NOT NULL REFERENCES type_key_identity(type_key),
    field_name TEXT NOT NULL,
    content TEXT NOT NULL,
    valid_from_revision INTEGER NOT NULL REFERENCES canonical_record(revision),
    valid_to_revision INTEGER REFERENCES canonical_record(revision),
    FOREIGN KEY (object_uuid, valid_from_revision)
        REFERENCES graph_object_version(uuid, valid_from_revision),
    CHECK (valid_to_revision IS NULL OR valid_to_revision > valid_from_revision)
) STRICT;
CREATE INDEX search_document_scope_interval_idx
    ON search_document(kind, type_key, field_name, valid_from_revision, valid_to_revision);
CREATE INDEX search_document_object_interval_idx
    ON search_document(object_uuid, field_name, valid_from_revision, valid_to_revision);
CREATE VIRTUAL TABLE search_fts USING fts5(
    content,
    content='search_document',
    content_rowid='document_id',
    tokenize='unicode61 remove_diacritics 2'
);
"""
