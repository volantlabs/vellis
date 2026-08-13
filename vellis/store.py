"""Durable local canonical storage.

The model requires canonical history to be complete, ordered, locally durable across
ordinary process restarts, and append-only, and requires current work to reach the
current canonical-state projection without traversing history. It deliberately leaves
storage open.

This realization selects one embedded SQL database file. That choice supplies the
recoverable atomicity ``VellisRequirements::atomicCanonicalRevision`` requires — the
appended canonical record and the updated current projection commit as one effect —
and gives later slices ordered, indexed selection without a linear ledger scan. The
current projection stores graph objects as addressable rows and definitions as a
separate facet. It remains a projection of replay through the final canonical record,
never parallel authority, but routine reads need not deserialize unrelated graph data.

The projection and the record it derives from are written as one effect and each read
checks its revision markers, so an interrupted or partial write cannot present a mixed
tuple. Content divergence introduced by editing the database file directly is not
detected: comparing decoded content on every current read would traverse a canonical
record, which is exactly the work
``VellisRequirements::historyIndependentCurrentWork`` forbids. A store file edited from
outside is therefore screened, not trusted: what this module can tell about such a file —
that it is not a database, that it belongs to something else, that it is a store this
build cannot read — it says, and content divergence below that is out of reach.

Every canonical-record access is counted so conformance evidence for
``VellisRequirements::historyIndependentCurrentWork`` can observe them directly rather
than through wall-clock timing.
"""

from __future__ import annotations

import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING
from urllib.parse import quote

from vellis.activity import ActivityRecord
from vellis.canonical import (
    CanonicalChange,
    CanonicalState,
    CanonicalTransitionRecord,
    DefinitionDelta,
    DefinitionDeltaDisposition,
    InitialStateRecord,
    Provenance,
    TransitionKind,
    now,
)
from vellis.changes import (
    GraphChange,
    GraphChangeRequest,
    GraphChangeTarget,
    apply_change,
    change_findings,
)
from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    DirectAssociationEnd,
    DirectAssociationMultiplicityConstraint,
    EndpointConstraint,
    GraphDefinitionSet,
    LinkEnd,
    LinkMultiplicityConstraint,
    LinkTypeDefinition,
    relationship_identity,
    relationship_label,
    validate_definition_set,
)
from vellis.governance import DefinitionChange, definition_change_findings
from vellis.graph import (
    Anchor,
    AssociatedDataObject,
    Graph,
    GraphObject,
    Link,
    ObjectKind,
    graph_equal,
)
from vellis.json_value import JsonKind, json_equal
from vellis.normalized import (
    definition_content_stats,
    definition_entry_digest,
    definition_identity,
    definition_identity_from_stats,
    insert_definition_set,
    insert_object_value,
    json_storage_fields,
    json_storage_value,
    load_definition_set,
    load_object_value,
    object_identity,
    semantic_identity,
)
from vellis.outcomes import (
    OperationStatus,
    RevisionedOutcome,
    ValidationFinding,
    ValidationReport,
    ValidationScope,
)
from vellis.validation import assess_graph_conformance

if TYPE_CHECKING:
    from vellis.query import AnchorGroup, GraphQuery, GraphQueryResult, RequiredLink

__all__ = [
    "AlreadyInitializedError",
    "CanonicalStore",
    "ConcurrentRevisionError",
    "ForeignDatabaseError",
    "NotADatabaseError",
    "NotInitializedError",
    "ProposalState",
    "StoreError",
    "UnreadableStoreError",
    "holds_established_memory",
]

SCHEMA_VERSION = "4"

# The next ledger position. Counting rows would traverse the whole prefix on every
# commit, which is exactly the work history-independent current operations may not do;
# ordinal is UNIQUE, so taking its maximum is an index seek instead.
NEXT_ORDINAL_SQL = "SELECT ifnull(max(ordinal), -1) + 1 FROM canonical_record"

# A partial index over only definition-affecting transitions. The predicate is repeated
# literally in the historical-definition query so SQLite can prove the index applies;
# a returned-row counter cannot detect an ordinal-index walk that filters graph records.
DEFINITION_TRANSITION_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS canonical_definition_transition
ON canonical_record (established_revision)
WHERE ordinal > 0 AND record_kind != 'graphMutation'
"""

DEFINITION_TRANSITIONS_SQL = (
    "SELECT established_revision, record_kind, recorded_at, initiator, source, summary,"
    " prior_revision FROM canonical_record WHERE ordinal > 0 AND established_revision <= ?"
    " AND record_kind != 'graphMutation' ORDER BY established_revision"
)

# Whether canonical state exists. One statement, so a caller asking before it may create
# anything and the store asking during a commit are asking exactly the same question.
INITIALIZED_SQL = "SELECT 1 FROM state_head WHERE id = 0"

# What every SQLite database begins with, so a file that is not one can be told apart
# from a database this attempt merely could not open.
SQLITE_MAGIC = b"SQLite format 3\x00"

# A stable marker so an unrelated database at the store path is refused, not adopted.
APPLICATION_ID = 0x56454C31  # "VEL1"

_SCHEMA = """
CREATE TABLE schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE canonical_record (
    established_revision INTEGER PRIMARY KEY,
    ordinal              INTEGER NOT NULL UNIQUE,
    record_kind          TEXT    NOT NULL,
    recorded_at          TEXT    NOT NULL,
    initiator            TEXT    NOT NULL,
    source               TEXT,
    summary              TEXT    NOT NULL,
    prior_revision       INTEGER,
    record_identity      TEXT    NOT NULL UNIQUE,
    prior_record_identity TEXT
);
CREATE TABLE activity_record (
    ordinal     INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    capability TEXT NOT NULL,
    outcome_category TEXT NOT NULL,
    semantic_scope TEXT NOT NULL,
    summary TEXT NOT NULL,
    initiator TEXT NOT NULL,
    source TEXT,
    evaluated_revision INTEGER
);
CREATE TABLE ledger (
    id       INTEGER PRIMARY KEY CHECK (id = 0),
    identity TEXT    NOT NULL
);
CREATE INDEX activity_record_time ON activity_record (recorded_at);
CREATE INDEX canonical_record_time ON canonical_record (recorded_at);
CREATE INDEX canonical_record_kind ON canonical_record (record_kind, established_revision);
CREATE TABLE definition_set (
    identity TEXT PRIMARY KEY,
    content_accumulator TEXT NOT NULL,
    entry_count INTEGER NOT NULL
);
CREATE TABLE definition_type (
    definition_set_id TEXT NOT NULL REFERENCES definition_set(identity),
    occurrence INTEGER NOT NULL,
    object_kind TEXT NOT NULL,
    type_key TEXT NOT NULL,
    description TEXT,
    PRIMARY KEY (definition_set_id, occurrence)
);
CREATE INDEX definition_type_lookup ON definition_type(definition_set_id, object_kind, type_key);
CREATE TABLE definition_anchor_permission (
    definition_set_id TEXT NOT NULL,
    type_occurrence INTEGER NOT NULL,
    occurrence INTEGER NOT NULL,
    anchor_type_key TEXT NOT NULL,
    PRIMARY KEY (definition_set_id, type_occurrence, occurrence),
    FOREIGN KEY (definition_set_id, type_occurrence)
      REFERENCES definition_type(definition_set_id, occurrence)
);
CREATE TABLE definition_property_rule (
    definition_set_id TEXT NOT NULL,
    type_occurrence INTEGER NOT NULL,
    occurrence INTEGER NOT NULL,
    property_name TEXT NOT NULL,
    required INTEGER NOT NULL,
    json_kind TEXT NOT NULL,
    description TEXT,
    minimum_size INTEGER,
    maximum_size INTEGER,
    lower_kind TEXT,
    lower_value TEXT,
    upper_kind TEXT,
    upper_value TEXT,
    pattern TEXT,
    PRIMARY KEY (definition_set_id, type_occurrence, occurrence),
    FOREIGN KEY (definition_set_id, type_occurrence)
      REFERENCES definition_type(definition_set_id, occurrence)
);
CREATE TABLE definition_permitted_value (
    definition_set_id TEXT NOT NULL,
    type_occurrence INTEGER NOT NULL,
    property_occurrence INTEGER NOT NULL,
    occurrence INTEGER NOT NULL,
    json_kind TEXT NOT NULL,
    json_value TEXT NOT NULL,
    PRIMARY KEY (definition_set_id, type_occurrence, property_occurrence, occurrence),
    FOREIGN KEY (definition_set_id, type_occurrence, property_occurrence)
      REFERENCES definition_property_rule(definition_set_id, type_occurrence, occurrence)
);
CREATE TABLE definition_endpoint_rule (
    definition_set_id TEXT NOT NULL,
    type_occurrence INTEGER NOT NULL,
    description TEXT,
    PRIMARY KEY (definition_set_id, type_occurrence),
    FOREIGN KEY (definition_set_id, type_occurrence)
      REFERENCES definition_type(definition_set_id, occurrence)
);
CREATE TABLE definition_endpoint_permission (
    definition_set_id TEXT NOT NULL,
    type_occurrence INTEGER NOT NULL,
    role TEXT NOT NULL,
    occurrence INTEGER NOT NULL,
    type_key TEXT NOT NULL,
    PRIMARY KEY (definition_set_id, type_occurrence, role, occurrence),
    FOREIGN KEY (definition_set_id, type_occurrence)
      REFERENCES definition_type(definition_set_id, occurrence)
);
CREATE TABLE definition_multiplicity_rule (
    definition_set_id TEXT NOT NULL REFERENCES definition_set(identity),
    occurrence INTEGER NOT NULL,
    natural_key TEXT NOT NULL,
    rule_kind TEXT NOT NULL,
    link_type_key TEXT,
    constrained_end TEXT NOT NULL,
    lower_bound INTEGER NOT NULL,
    upper_bound INTEGER,
    description TEXT,
    PRIMARY KEY (definition_set_id, occurrence)
);
CREATE TABLE definition_multiplicity_participant (
    definition_set_id TEXT NOT NULL,
    rule_occurrence INTEGER NOT NULL,
    role TEXT NOT NULL,
    occurrence INTEGER NOT NULL,
    type_key TEXT NOT NULL,
    PRIMARY KEY (definition_set_id, rule_occurrence, role, occurrence),
    FOREIGN KEY (definition_set_id, rule_occurrence)
      REFERENCES definition_multiplicity_rule(definition_set_id, occurrence)
);
CREATE TABLE object_value (
    id INTEGER PRIMARY KEY,
    content_identity TEXT NOT NULL UNIQUE,
    uuid TEXT NOT NULL,
    object_kind TEXT NOT NULL,
    type_key TEXT NOT NULL,
    display_name TEXT,
    source_uuid TEXT,
    target_uuid TEXT
);
CREATE INDEX object_value_selector
    ON object_value(object_kind, type_key, uuid, source_uuid, target_uuid);
CREATE INDEX object_value_uuid ON object_value(uuid, id);
CREATE INDEX object_value_type_key ON object_value(type_key, object_kind, id);
CREATE INDEX object_value_link_source
    ON object_value(source_uuid, type_key, id) WHERE object_kind = 'link';
CREATE INDEX object_value_link_target
    ON object_value(target_uuid, type_key, id) WHERE object_kind = 'link';
CREATE TABLE object_metadata (
    object_value_id INTEGER NOT NULL REFERENCES object_value(id),
    ordinal INTEGER NOT NULL,
    name TEXT NOT NULL,
    json_kind TEXT NOT NULL,
    boolean_value INTEGER,
    number_value TEXT,
    text_value TEXT,
    PRIMARY KEY (object_value_id, ordinal)
);
CREATE TABLE object_property (
    object_value_id INTEGER NOT NULL REFERENCES object_value(id),
    ordinal INTEGER NOT NULL,
    name TEXT NOT NULL,
    json_kind TEXT NOT NULL,
    boolean_value INTEGER,
    number_value TEXT,
    text_value TEXT,
    PRIMARY KEY (object_value_id, ordinal)
);
CREATE INDEX object_property_lookup
    ON object_property(name, json_kind, text_value, number_value, boolean_value, object_value_id);
CREATE INDEX object_property_by_value ON object_property(object_value_id, name);
CREATE TABLE object_anchor (
    object_value_id INTEGER NOT NULL REFERENCES object_value(id),
    ordinal INTEGER NOT NULL,
    anchor_uuid TEXT NOT NULL,
    PRIMARY KEY (object_value_id, ordinal)
);
CREATE INDEX object_anchor_reverse ON object_anchor(anchor_uuid, object_value_id);
CREATE TABLE state_head (
    id             INTEGER PRIMARY KEY CHECK (id = 0),
    revision       INTEGER NOT NULL,
    established_by INTEGER NOT NULL REFERENCES canonical_record (established_revision),
    active_definition_set_id TEXT NOT NULL REFERENCES definition_set(identity),
    proposed_definition_set_id TEXT
);
CREATE TABLE graph_presence_interval (
    uuid TEXT NOT NULL,
    object_value_id INTEGER NOT NULL REFERENCES object_value(id),
    object_kind TEXT NOT NULL,
    type_key TEXT NOT NULL,
    source_uuid TEXT,
    target_uuid TEXT,
    valid_from_revision INTEGER NOT NULL,
    valid_to_revision INTEGER,
    PRIMARY KEY (uuid, valid_from_revision)
);
CREATE UNIQUE INDEX graph_presence_current_uuid
    ON graph_presence_interval(uuid) WHERE valid_to_revision IS NULL;
CREATE INDEX graph_presence_current_value
    ON graph_presence_interval(object_value_id, uuid) WHERE valid_to_revision IS NULL;
CREATE INDEX graph_presence_current_type
    ON graph_presence_interval(object_kind, type_key, uuid)
    WHERE valid_to_revision IS NULL;
CREATE INDEX graph_presence_current_link_source
    ON graph_presence_interval(source_uuid, type_key, uuid)
    WHERE valid_to_revision IS NULL AND object_kind = 'link';
CREATE INDEX graph_presence_current_link_target
    ON graph_presence_interval(target_uuid, type_key, uuid)
    WHERE valid_to_revision IS NULL AND object_kind = 'link';
CREATE INDEX graph_presence_revision
    ON graph_presence_interval(valid_from_revision, valid_to_revision, uuid);
CREATE VIEW current_graph_object AS
SELECT p.uuid, p.object_kind, p.type_key, p.source_uuid, p.target_uuid, p.object_value_id
FROM graph_presence_interval p
WHERE p.valid_to_revision IS NULL;
CREATE VIEW current_data_anchor AS
SELECT v.uuid AS data_uuid, a.anchor_uuid
FROM current_graph_object c
JOIN object_value v ON v.id = c.object_value_id
JOIN object_anchor a ON a.object_value_id = v.id
WHERE v.object_kind = 'associatedData';
CREATE TABLE proposal_entry (
    uuid TEXT PRIMARY KEY,
    object_kind TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('upsert', 'delete')),
    object_value_id INTEGER REFERENCES object_value(id),
    base_object_value_id INTEGER REFERENCES object_value(id),
    CHECK ((operation = 'upsert') = (object_value_id IS NOT NULL))
);
CREATE INDEX proposal_entry_kind ON proposal_entry(object_kind, operation, uuid);
CREATE TABLE proposal_overlay_state (
    id INTEGER PRIMARY KEY CHECK (id = 0),
    accumulator TEXT NOT NULL,
    entry_count INTEGER NOT NULL
);
CREATE TABLE proposal_overlay_count (
    object_kind TEXT NOT NULL,
    operation TEXT NOT NULL,
    entry_count INTEGER NOT NULL,
    PRIMARY KEY (object_kind, operation)
);
CREATE TRIGGER proposal_entry_count_insert AFTER INSERT ON proposal_entry BEGIN
    UPDATE proposal_overlay_count SET entry_count = entry_count + 1
    WHERE object_kind = NEW.object_kind AND operation = NEW.operation;
END;
CREATE TRIGGER proposal_entry_count_delete AFTER DELETE ON proposal_entry BEGIN
    UPDATE proposal_overlay_count SET entry_count = entry_count - 1
    WHERE object_kind = OLD.object_kind AND operation = OLD.operation;
END;
CREATE TRIGGER proposal_entry_count_update AFTER UPDATE ON proposal_entry
WHEN OLD.object_kind != NEW.object_kind OR OLD.operation != NEW.operation BEGIN
    UPDATE proposal_overlay_count SET entry_count = entry_count - 1
    WHERE object_kind = OLD.object_kind AND operation = OLD.operation;
    UPDATE proposal_overlay_count SET entry_count = entry_count + 1
    WHERE object_kind = NEW.object_kind AND operation = NEW.operation;
END;
CREATE TABLE proposal_definition_state (
    id INTEGER PRIMARY KEY CHECK (id = 0),
    base_definition_set_id TEXT REFERENCES definition_set(identity),
    accumulator TEXT NOT NULL,
    entry_count INTEGER NOT NULL,
    effective_accumulator TEXT,
    effective_entry_count INTEGER,
    identity TEXT
);
CREATE TABLE proposal_definition_type (
    type_key TEXT PRIMARY KEY,
    operation TEXT NOT NULL CHECK (operation IN ('upsert', 'delete')),
    value_set_id TEXT REFERENCES definition_set(identity),
    CHECK ((operation = 'upsert') = (value_set_id IS NOT NULL))
);
CREATE TABLE proposal_definition_relationship (
    natural_key TEXT PRIMARY KEY,
    operation TEXT NOT NULL CHECK (operation IN ('upsert', 'delete')),
    value_set_id TEXT REFERENCES definition_set(identity),
    CHECK ((operation = 'upsert') = (value_set_id IS NOT NULL))
);
CREATE VIEW prospective_graph_object AS
SELECT c.uuid, c.object_kind, c.type_key, c.source_uuid, c.target_uuid, c.object_value_id
FROM current_graph_object AS c
WHERE NOT EXISTS (SELECT 1 FROM proposal_entry AS p WHERE p.uuid = c.uuid)
UNION ALL
SELECT v.uuid, v.object_kind, v.type_key, v.source_uuid, v.target_uuid, v.id
FROM proposal_entry AS p JOIN object_value AS v ON v.id = p.object_value_id
WHERE p.operation = 'upsert';
CREATE VIEW prospective_data_anchor AS
SELECT v.uuid AS data_uuid, a.anchor_uuid
FROM prospective_graph_object AS c
JOIN object_value AS v ON v.id = c.object_value_id
JOIN object_anchor AS a ON a.object_value_id = v.id
WHERE v.object_kind = 'associatedData';
CREATE TABLE validation_assessment (
    identity TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    evaluated_revision INTEGER NOT NULL,
    proposed_definition_set_id TEXT,
    graph_overlay_identity TEXT,
    conforms INTEGER NOT NULL,
    finding_count INTEGER NOT NULL,
    completed_at TEXT NOT NULL
);
CREATE TABLE current_assessment (
    scope TEXT PRIMARY KEY,
    assessment_id TEXT NOT NULL REFERENCES validation_assessment(identity)
);
CREATE TABLE validation_finding (
    assessment_id TEXT NOT NULL REFERENCES validation_assessment(identity),
    ordinal INTEGER NOT NULL,
    summary TEXT NOT NULL,
    PRIMARY KEY (assessment_id, ordinal)
);
CREATE TABLE validation_finding_definition (
    assessment_id TEXT NOT NULL,
    finding_ordinal INTEGER NOT NULL,
    ordinal INTEGER NOT NULL,
    definition_ref TEXT NOT NULL,
    PRIMARY KEY (assessment_id, finding_ordinal, ordinal),
    FOREIGN KEY (assessment_id, finding_ordinal)
      REFERENCES validation_finding(assessment_id, ordinal)
);
CREATE TABLE validation_finding_object (
    assessment_id TEXT NOT NULL,
    finding_ordinal INTEGER NOT NULL,
    ordinal INTEGER NOT NULL,
    object_uuid TEXT NOT NULL,
    PRIMARY KEY (assessment_id, finding_ordinal, ordinal),
    FOREIGN KEY (assessment_id, finding_ordinal)
      REFERENCES validation_finding(assessment_id, ordinal)
);
CREATE TABLE canonical_graph_event (
    established_revision INTEGER NOT NULL REFERENCES canonical_record(established_revision),
    occurrence INTEGER NOT NULL,
    operation TEXT NOT NULL,
    object_kind TEXT NOT NULL,
    uuid TEXT NOT NULL,
    object_value_id INTEGER REFERENCES object_value(id),
    PRIMARY KEY (established_revision, occurrence)
);
CREATE TABLE canonical_proposal_event (
    established_revision INTEGER NOT NULL REFERENCES canonical_record(established_revision),
    occurrence INTEGER NOT NULL,
    operation TEXT NOT NULL,
    object_kind TEXT NOT NULL,
    uuid TEXT NOT NULL,
    object_value_id INTEGER REFERENCES object_value(id),
    PRIMARY KEY (established_revision, occurrence)
);
CREATE TABLE canonical_definition_proposal_event (
    established_revision INTEGER NOT NULL REFERENCES canonical_record(established_revision),
    occurrence INTEGER NOT NULL,
    entity_kind TEXT NOT NULL,
    natural_key TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('upsert', 'delete', 'unstage')),
    value_set_id TEXT REFERENCES definition_set(identity),
    PRIMARY KEY (established_revision, occurrence)
);
CREATE TABLE canonical_definition_event (
    established_revision INTEGER PRIMARY KEY REFERENCES canonical_record(established_revision),
    active_definition_set_id TEXT REFERENCES definition_set(identity),
    delta_disposition TEXT NOT NULL,
    proposed_definition_set_id TEXT
);
"""


def _stored_time(moment: datetime) -> str:
    """Render one instant so that text order is instant order.

    The activity ledger is selected and pruned by comparing this column, and ISO-8601
    text only sorts by instant when every value carries the same offset. A caller's
    bound in another zone would otherwise silently select — or delete — the wrong
    interval, which on the retention path means losing history the owner meant to keep.
    """
    if moment.tzinfo is None:
        raise StoreError(f"a time bound must say which zone it is in: {moment.isoformat()}")
    return moment.astimezone(UTC).isoformat()


def _decimal_compare(left: object, right: object) -> int | None:
    """Compare canonical decimal strings without converting them to binary floats."""
    try:
        first, second = Decimal(str(left)), Decimal(str(right))
    except InvalidOperation, ValueError:
        return None
    return (first > second) - (first < second)


def _stored_json_equal(
    left_kind: object,
    left_boolean: object,
    left_number: object,
    left_text: object,
    right_kind: object,
    right_boolean: object,
    right_number: object,
    right_text: object,
) -> int:
    try:
        left = json_storage_value(left_kind, left_boolean, left_number, left_text)
        right = json_storage_value(right_kind, right_boolean, right_number, right_text)
    except ValueError, ArithmeticError:
        return 0
    return int(json_equal(left, right))


def _property_comparison_sql(
    alias: str,
    operation: str,
    kind: str,
    boolean: int | None,
    number: str | None,
    text: str | None,
    parameters: list[object],
) -> str:
    """Compile one typed property comparison and append its SQL parameters."""
    if operation in {"equal", "notEqual"}:
        parameters.extend((kind, boolean, number, text))
        predicate = (
            f"vellis_json_equal({alias}.json_kind, {alias}.boolean_value,"
            f" {alias}.number_value, {alias}.text_value, ?, ?, ?, ?)"
        )
        return f"{predicate} = {1 if operation == 'equal' else 0}"
    operators = {
        "lessThan": "<",
        "lessThanOrEqual": "<=",
        "greaterThan": ">",
        "greaterThanOrEqual": ">=",
    }
    parameters.append(number)
    return (
        f"({alias}.json_kind = '{JsonKind.NUMBER.value}' AND "
        f"vellis_decimal_cmp({alias}.number_value, ?) {operators[operation]} 0)"
    )


def _projection_revision(row: tuple[object, ...]) -> int:
    if not isinstance(row[0], int) or not isinstance(row[1], int):
        raise StoreError("the current projection revision markers are not integers")
    revision = row[0]
    established_by = row[1]
    if revision != established_by:
        raise StoreError(
            f"the current projection claims revision {revision} established by record "
            f"{established_by}"
        )
    return revision


class StoreError(RuntimeError):
    """Raised when durable state cannot be read or written safely."""


class NotADatabaseError(StoreError):
    """Raised when the file at a store path is not a database at all.

    Whose file it is stays unknown — a store whose header was destroyed looks the same as
    something that was never ours — so the way out says nothing about ownership: put that
    file somewhere else, or use a different destination.
    """


class ForeignDatabaseError(StoreError):
    """Raised when a database at a store path belongs to something other than Vellis.

    Nothing of the owner's is at stake, so the way out is a different destination — which
    is exactly the advice that would be wrong for a store that is theirs.
    """


class UnreadableStoreError(StoreError):
    """Raised when a file is a canonical store that this build cannot read.

    Distinct from a bare :class:`StoreError` about a database that belongs to something
    else: this one is somebody's memory. What to do about it — a build that reads it, a
    restore, a migration — is not what to do about a destination that was never ours, and
    telling an owner to go and use a different directory would leave their memory behind.
    """


class AlreadyInitializedError(StoreError):
    """Raised when initialization is attempted against established canonical state."""


class NotInitializedError(StoreError):
    """Raised when an operation needs canonical state that was never established.

    Its sibling is ``AlreadyInitializedError``: both are determinate preconditions the
    caller can act on, not the damaged-store condition the bare ``StoreError`` reports.
    """


class ConcurrentRevisionError(StoreError):
    """Raised when the revision a change was prepared against is no longer current."""


@dataclass(frozen=True, slots=True)
class ProposalState:
    revision: int
    proposed_definition_identity: str | None
    graph_overlay_identity: str | None
    staged_anchor_count: int = 0
    staged_associated_data_count: int = 0
    staged_link_count: int = 0
    staged_removal_count: int = 0
    assessment: ValidationReport | None = None


@dataclass(slots=True)
class _RecordRow:
    established_revision: int
    record_kind: str
    recorded_at: str
    initiator: str
    source: str | None
    summary: str
    prior_revision: int | None


def _schema_present(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_meta'"
    ).fetchone()
    return row is not None


def _refuse_foreign_database(connection: sqlite3.Connection, path: Path) -> None:
    """Refuse a database that already holds something other than a Vellis store.

    Without this the schema would be created inside an unrelated database and its
    own application marker overwritten.
    """
    marker = connection.execute("PRAGMA application_id").fetchone()
    if marker is not None and int(marker[0]) not in {0, APPLICATION_ID}:
        raise ForeignDatabaseError(f"the database at {path} belongs to another application")
    existing = connection.execute(
        "SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
    ).fetchall()
    if not existing:
        return
    names = ", ".join(sorted(str(row[0]) for row in existing))
    if marker is not None and int(marker[0]) == APPLICATION_ID:
        # Our own marker over our own tables: this is somebody's store with a piece
        # missing, not a stranger's database, and its owner may not be sent elsewhere.
        raise UnreadableStoreError(
            f"canonical store at {path} is missing its schema_meta table, "
            f"though it still holds {names}"
        )
    raise ForeignDatabaseError(
        f"the database at {path} already holds other objects ({names}); "
        "choose a different destination"
    )


def _screen_database(connection: sqlite3.Connection, path: Path) -> bool:
    """Decide whether this file may be used, and report whether it is already a store.

    Refuses anything that belongs to something else, before the file is changed at all.
    A database can carry a table named ``schema_meta`` without being a Vellis store, so
    the marker check belongs here rather than after the pragmas have already rewritten
    the header.

    One rule, used by the store when it opens a file and by anyone asking what is already
    at a path. Two rules would eventually disagree, and then a destination would be
    refused by one and adopted by the other. They still look at the file differently — one
    opens it to write, the other only to read — so they can differ about what is there,
    but not about what would be allowed.
    """
    if _schema_present(connection):
        _screen_marker(connection, path)
        return True
    _refuse_foreign_database(connection, path)
    return False


def _screen_marker(connection: sqlite3.Connection, path: Path) -> None:
    """Refuse a database that is not a canonical store this build reads."""
    # Whose database this is comes first. A version mismatch is a statement about a
    # Vellis store, and reporting one about a file that is not ours would send the
    # owner looking for a migration that does not apply.
    marker = connection.execute("PRAGMA application_id").fetchone()
    if marker is None or int(marker[0]) != APPLICATION_ID:
        raise ForeignDatabaseError(f"the database at {path} is not a Vellis canonical store")
    row = connection.execute(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'"
    ).fetchone()
    if row is None or row[0] != SCHEMA_VERSION:
        found = "none" if row is None else str(row[0])
        raise UnreadableStoreError(
            f"canonical store at {path} has schema version {found}, "
            f"but this build reads version {SCHEMA_VERSION}"
        )
    for table in (
        "canonical_record",
        "activity_record",
        "state_head",
        "object_value",
        "graph_presence_interval",
        "definition_set",
        "ledger",
    ):
        present = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        if present is None:
            raise UnreadableStoreError(f"canonical store at {path} is missing its {table} table")
    columns = {str(info[1]) for info in connection.execute("PRAGMA table_info(state_head)")}
    required = {
        "id",
        "revision",
        "established_by",
        "active_definition_set_id",
        "proposed_definition_set_id",
    }
    if not required.issubset(columns):
        missing = ", ".join(sorted(required - columns))
        raise UnreadableStoreError(
            f"canonical store at {path} schema version {SCHEMA_VERSION} is missing state-head "
            f"columns {missing}"
        )


def holds_established_memory(path: Path) -> bool:
    """Report whether a store at ``path`` already holds canonical state, changing nothing.

    A caller can ask this before it has permission to change anything at all — a preview
    that promises no effect has to be able to keep that promise — so the file is opened
    immutably. That reads the database and nothing beside it: no index file is made, no
    write-ahead log is finished, and a path with no file at it is never opened.

    Reading a database immutably means reading it as it stands. A store another process is
    writing may therefore be unreadable, which is reported as such rather than as an
    answer. It may also be short of commits still sitting in its write-ahead log, and
    those this cannot see: such a store can answer that it holds nothing. Finishing the
    log would mean writing to it, which is the one thing a caller asking this may not do,
    so the cost is left where it is cheapest — the operation that follows opens the file
    properly, refuses, and says so, and nothing is established either way.
    """
    if not path.exists():
        return False
    if _is_not_a_database(path):
        raise NotADatabaseError(f"the file at {path} is not a database")
    try:
        # The path is escaped because a URI reads '?' and '#' in it as its own
        # punctuation, and would otherwise open some truncated path nobody named.
        with closing(
            sqlite3.connect(f"file:{quote(str(path))}?mode=ro&immutable=1", uri=True)
        ) as connection:
            if not _screen_database(connection, path):
                return False
            return connection.execute(INITIALIZED_SQL).fetchone() is not None
    except sqlite3.Error as error:
        raise StoreError(f"could not read the store at {path}: {error}") from error


def _is_not_a_database(path: Path) -> bool:
    """Say whether a non-empty file is something other than a SQLite database.

    Read from the file rather than from a failed open, because opening it says only that
    this attempt did not work — which is also what a busy or unreadable store says, and
    those two deserve different answers.
    """
    try:
        with path.open("rb") as handle:
            header = handle.read(len(SQLITE_MAGIC))
    except OSError:
        return False
    return bool(header) and not header.startswith(SQLITE_MAGIC)


def _chunks(values: set[str], size: int = 400) -> Iterator[tuple[str, ...]]:
    """Yield deterministic parameter batches below SQLite's conservative host limit."""
    ordered = sorted(values)
    for start in range(0, len(ordered), size):
        yield tuple(ordered[start : start + size])


def _query_type_keys(query: GraphQuery) -> set[str]:
    return {
        *(group.anchor_type for group in query.anchor_groups),
        *(condition.associated_data_type for condition in query.data_conditions),
        *(required.link_type for required in query.required_links),
    }


def _query_component_names(query: GraphQuery) -> tuple[frozenset[str], ...]:
    names = [
        *(group.name for group in query.anchor_groups),
        *(condition.name for condition in query.data_conditions),
    ]
    adjacent = {name: set[str]() for name in names}
    for condition in query.data_conditions:
        adjacent[condition.name].add(condition.anchor_group)
        adjacent[condition.anchor_group].add(condition.name)
    for required in query.required_links:
        adjacent[required.source_group].add(required.target_group)
        adjacent[required.target_group].add(required.source_group)
    components: list[frozenset[str]] = []
    visited: set[str] = set()
    for name in names:
        if name in visited:
            continue
        pending = [name]
        members: set[str] = set()
        while pending:
            current = pending.pop()
            if current in members:
                continue
            members.add(current)
            pending.extend(adjacent[current] - members)
        visited.update(members)
        components.append(frozenset(members))
    return tuple(components)


def _projected_selector_names(query: GraphQuery) -> set[str]:
    from vellis.query import (
        AnchorProjection,
        AssociatedDataProjection,
        DataPropertyProjection,
        LinkProjection,
    )

    required = {link.name: link for link in query.required_links}
    names: set[str] = set()
    for projection in query.return_shape.projections:
        if isinstance(projection, AnchorProjection):
            names.add(projection.anchor_group)
        elif isinstance(projection, (AssociatedDataProjection, DataPropertyProjection)):
            names.add(projection.data_condition)
        elif isinstance(projection, LinkProjection):
            link = required[projection.required_link]
            names.update((link.source_group, link.target_group))
    return names


def _component_query(query: GraphQuery, names: set[str], *, projections: bool) -> GraphQuery:
    from vellis.query import (
        AnchorProjection,
        AssociatedDataProjection,
        DataPropertyProjection,
        GraphQuery,
        LinkProjection,
        ReturnShape,
    )

    links = tuple(
        link
        for link in query.required_links
        if link.source_group in names and link.target_group in names
    )
    link_names = {link.name for link in links}
    selected = (
        tuple(
            projection
            for projection in query.return_shape.projections
            if (
                isinstance(projection, AnchorProjection)
                and projection.anchor_group in names
                or isinstance(projection, (AssociatedDataProjection, DataPropertyProjection))
                and projection.data_condition in names
                or isinstance(projection, LinkProjection)
                and projection.required_link in link_names
            )
        )
        if projections
        else ()
    )
    return GraphQuery(
        anchor_groups=tuple(group for group in query.anchor_groups if group.name in names),
        data_conditions=tuple(
            condition for condition in query.data_conditions if condition.name in names
        ),
        required_links=links,
        return_shape=ReturnShape(selected),
        maximum_rows=query.maximum_rows,
        historical_selection=query.historical_selection,
    )


def _graph_from_objects(values: Iterator[GraphObject] | list[GraphObject]) -> Graph:
    anchors: list[Anchor] = []
    data: list[AssociatedDataObject] = []
    links: list[Link] = []
    for value in values:
        if isinstance(value, Anchor):
            anchors.append(value)
        elif isinstance(value, AssociatedDataObject):
            data.append(value)
        else:
            links.append(value)
    return Graph(tuple(anchors), tuple(data), tuple(links))


def _merge_graphs(first: Graph, second: Graph) -> Graph:
    """Combine disjoint identity selections from one SQLite snapshot."""
    by_uuid = {value.uuid: value for value in first.objects()}
    by_uuid.update((value.uuid, value) for value in second.objects())
    return _graph_from_objects(list(by_uuid.values()))


def _graph_identity(graph: Graph) -> str:
    return semantic_identity(tuple(sorted(object_identity(value) for value in graph.objects())))


def _change_identity(change: CanonicalChange) -> str:
    graph_change: object = None
    if change.graph_change is not None:
        graph_change = (
            tuple(
                sorted(
                    (kind.value, object_identity(value))
                    for kind, value in change.graph_change.upserts()
                )
            ),
            tuple(sorted((kind.value, uuid) for kind, uuid in change.graph_change.removals())),
        )
    return semantic_identity(
        (
            change.delta_disposition.value,
            graph_change,
            None if change.replacement_graph is None else _graph_identity(change.replacement_graph),
            None
            if change.active_definitions is None
            else definition_identity(change.active_definitions),
            None
            if change.definition_delta is None
            else (
                definition_identity(change.definition_delta.proposed_definitions),
                (
                    tuple(
                        sorted(
                            (kind.value, object_identity(value))
                            for kind, value in change.definition_delta.graph_overlay.upserts()
                        )
                    ),
                    tuple(
                        sorted(
                            (kind.value, uuid)
                            for kind, uuid in change.definition_delta.graph_overlay.removals()
                        )
                    ),
                ),
            ),
        )
    )


class CanonicalStore:
    """One local canonical store: its ledger, its current projection, and their durability."""

    def __init__(self, path: Path) -> None:
        self._path = path
        if _is_not_a_database(path):
            # Told apart here rather than from a failed open, so this refusal reads the
            # same whether a caller asked what was at the path or went to use it.
            raise NotADatabaseError(f"the file at {path} is not a database")
        self._record_reads = 0
        self._activity_reads = 0
        self._current_projection_decodes = 0
        self._current_graph_decodes = 0
        self._current_graph_object_decodes = 0
        self._current_definition_decodes = 0
        try:
            # One owner, one process, one connection — but not necessarily one thread:
            # a tool boundary answers on whichever worker it is called from. The
            # connection is shared across them and every operation takes the lock, so
            # access stays serialized without a pool or a connection per caller.
            self._connection = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
            self._connection.create_function(
                "vellis_decimal_cmp", 2, _decimal_compare, deterministic=True
            )
            self._connection.create_function(
                "vellis_json_equal", 8, _stored_json_equal, deterministic=True
            )
            self._lock = RLock()
        except sqlite3.Error as error:
            raise StoreError(f"could not open a canonical store at {path}: {error}") from error
        try:
            # Screening happens before the pragmas because setting the journal mode
            # rewrites the file header: refusing a database must leave it untouched.
            _screen_database(self._connection, path)
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("PRAGMA synchronous = FULL")
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._ensure_schema()
        except sqlite3.Error as error:
            self._connection.close()
            raise StoreError(f"could not open a canonical store at {path}: {error}") from error
        except BaseException:
            self._connection.close()
            raise

    # --- Lifecycle ------------------------------------------------------------------

    @property
    def path(self) -> Path:
        return self._path

    def close(self) -> None:
        self._connection.close()

    def _ensure_schema(self) -> None:
        if not _schema_present(self._connection):
            version_row = (
                "INSERT INTO schema_meta (key, value) VALUES "
                f"('schema_version', '{SCHEMA_VERSION}');"
            )
            try:
                self._connection.executescript(
                    f"BEGIN IMMEDIATE;PRAGMA application_id = {APPLICATION_ID};"
                    f"{_SCHEMA}{version_row}COMMIT;"
                )
            except sqlite3.OperationalError:
                # Another process created the schema between the check and this statement.
                self._rollback_quietly()
                if not _schema_present(self._connection):
                    raise
        _screen_marker(self._connection, self._path)
        self._connection.execute(DEFINITION_TRANSITION_INDEX_SQL)

    # --- Instrumentation ------------------------------------------------------------

    @property
    def record_reads(self) -> int:
        """Semantic canonical-record accesses since the last reset."""
        return self._record_reads

    @property
    def activity_reads(self) -> int:
        """Semantic activity-record accesses since the last reset.

        Counted separately from canonical accesses because the two ledgers answer
        different questions and the bound on selecting an interval is claimed of each of
        them. One counter over both would let a linear walk of one hide behind a narrow
        read of the other.
        """
        return self._activity_reads

    @property
    def current_projection_decodes(self) -> int:
        """Complete current-state materializations since the last instrumentation reset."""
        return self._current_projection_decodes

    @property
    def current_graph_decodes(self) -> int:
        """Current graph-facet decodes since the last instrumentation reset."""
        return self._current_graph_decodes

    @property
    def current_definition_decodes(self) -> int:
        """Current definition-facet decodes since the last instrumentation reset."""
        return self._current_definition_decodes

    @property
    def current_graph_object_decodes(self) -> int:
        """Addressable graph-object decodes since the last instrumentation reset."""
        return self._current_graph_object_decodes

    def reset_instrumentation(self) -> None:
        self._record_reads = 0
        self._activity_reads = 0
        self._current_projection_decodes = 0
        self._current_graph_decodes = 0
        self._current_graph_object_decodes = 0
        self._current_definition_decodes = 0

    # --- Current projection ---------------------------------------------------------

    def is_initialized(self) -> bool:
        """Return whether canonical state exists, without reading any canonical record."""
        return self._fetchone(INITIALIZED_SQL) is not None

    def _fetchone(self, sql: str, parameters: tuple[object, ...] = ()) -> object:
        """Run one read, reporting a database failure as a store error.

        Callers of this store handle :class:`StoreError`; letting a driver exception out
        would turn an operation that should report a failure into a traceback.
        """
        try:
            with self._lock:
                return self._connection.execute(sql, parameters).fetchone()
        except sqlite3.Error as error:
            raise StoreError(f"could not read from the store at {self._path}: {error}") from error

    def _fetchall(self, sql: str, parameters: tuple[object, ...] = ()) -> list[object]:
        try:
            with self._lock:
                return list(self._connection.execute(sql, parameters).fetchall())
        except sqlite3.Error as error:
            raise StoreError(f"could not read from the store at {self._path}: {error}") from error

    def _read_record(self, sql: str, parameters: tuple[object, ...] = ()) -> object:
        """Run one canonical-record query and count it as a semantic record access.

        Every read of the ledger goes through here, so the instrumentation measures
        access to the records themselves rather than calls to one convenience method.
        """
        self._record_reads += 1
        return self._fetchone(sql, parameters)

    @contextmanager
    def read_snapshot(self) -> Iterator[None]:
        """Keep several semantic reads on one committed SQLite snapshot."""
        try:
            with self._lock:
                self._connection.execute("BEGIN")
                try:
                    yield
                    self._connection.execute("COMMIT")
                except BaseException:
                    self._rollback_quietly()
                    raise
        except sqlite3.Error as error:
            raise StoreError(f"could not read from the store at {self._path}: {error}") from error

    def current_state(self) -> CanonicalState:
        """Return the current canonical-state projection.

        SQLite owns the live projection. Every call materializes a new domain value, so
        mutable nested JSON handed to a library caller has no shared resident object to
        corrupt and needs no defensive whole-state copy. This explicit complete-state
        operation is one of the few paths that assembles every graph row.
        """
        try:
            with self._lock:
                self._connection.execute("BEGIN")
                try:
                    state = self._current_state_unlocked()
                    self._connection.execute("COMMIT")
                    return state
                except BaseException:
                    self._rollback_quietly()
                    raise
        except sqlite3.Error as error:
            raise StoreError(f"could not read from the store at {self._path}: {error}") from error

    def _current_state_unlocked(self) -> CanonicalState:
        row = self._connection.execute(
            "SELECT revision, established_by, active_definition_set_id,"
            " proposed_definition_set_id FROM state_head WHERE id = 0"
        ).fetchone()
        if not isinstance(row, tuple):
            raise NotInitializedError("no canonical state is established")
        revision = _projection_revision(row)
        state = CanonicalState(
            graph=self._current_graph_unlocked(),
            active_definitions=self._load_definition_set(str(row[2])),
            definition_delta=(
                None
                if row[3] is None
                else DefinitionDelta(
                    proposed_definitions=self._effective_proposed_definitions_unlocked(str(row[2])),
                    graph_overlay=self._proposal_graph_change_unlocked(),
                )
            ),
            revision=revision,
        )
        self._current_projection_decodes += 1
        return state

    def current_graph(self) -> Graph:
        """Assemble the complete current graph without reading canonical history."""
        try:
            with self._lock:
                self._connection.execute("BEGIN")
                try:
                    if self._connection.execute(INITIALIZED_SQL).fetchone() is None:
                        raise NotInitializedError("no canonical state is established")
                    row = self._connection.execute(
                        "SELECT revision, established_by FROM state_head WHERE id = 0"
                    ).fetchone()
                    assert isinstance(row, tuple)
                    _projection_revision(row)
                    graph = self._current_graph_unlocked()
                    self._connection.execute("COMMIT")
                    return graph
                except BaseException:
                    self._rollback_quietly()
                    raise
        except sqlite3.Error as error:
            raise StoreError(f"could not read from the store at {self._path}: {error}") from error

    def evaluate_current_query(self, query: GraphQuery) -> GraphQueryResult:
        """Compile and evaluate a bounded current-state query inside SQLite."""

        try:
            with self._lock:
                self._connection.execute("BEGIN")
                try:
                    row = self._connection.execute(
                        "SELECT revision, established_by, active_definition_set_id"
                        " FROM state_head WHERE id = 0"
                    ).fetchone()
                    if not isinstance(row, tuple):
                        raise NotInitializedError("no canonical state is established")
                    revision = _projection_revision(row)
                    definitions = self._load_definition_set(
                        str(row[2]),
                        type_keys=_query_type_keys(query),
                        constrained_type_keys=set(),
                    )
                    result = self._evaluate_sql_query_unlocked(query, definitions, revision)
                    self._connection.execute("COMMIT")
                    return result
                except BaseException:
                    self._rollback_quietly()
                    raise
        except sqlite3.Error as error:
            raise StoreError(f"could not read from the store at {self._path}: {error}") from error

    def evaluate_query_at_revision(self, query: GraphQuery, revision: int) -> GraphQueryResult:
        """Evaluate directly over the normalized graph intervals at ``revision``."""
        try:
            with self._lock:
                self._connection.execute("BEGIN")
                try:
                    definition_row = self._connection.execute(
                        "SELECT active_definition_set_id FROM canonical_definition_event"
                        " WHERE established_revision <= ?"
                        " AND active_definition_set_id IS NOT NULL"
                        " ORDER BY established_revision DESC LIMIT 1",
                        (revision,),
                    ).fetchone()
                    if definition_row is None:
                        raise StoreError(
                            f"revision {revision} has no normalized active definition set"
                        )
                    definitions = self._load_definition_set(
                        str(definition_row[0]),
                        type_keys=_query_type_keys(query),
                        constrained_type_keys=set(),
                    )
                    result = self._evaluate_sql_query_unlocked(
                        query, definitions, revision, historical_revision=revision
                    )
                    self._connection.execute("COMMIT")
                    return result
                except BaseException:
                    self._rollback_quietly()
                    raise
        except sqlite3.Error as error:
            raise StoreError(
                f"could not query revision {revision} at {self._path}: {error}"
            ) from error

    def evaluate_prospective_query(self, query: GraphQuery) -> GraphQueryResult:
        """Evaluate over the sole definition-and-graph proposal without copying it."""
        try:
            with self._lock:
                self._connection.execute("BEGIN")
                try:
                    row = self._connection.execute(
                        "SELECT revision, established_by, proposed_definition_set_id"
                        " FROM state_head WHERE id = 0"
                    ).fetchone()
                    if not isinstance(row, tuple):
                        raise NotInitializedError("no canonical state is established")
                    revision = _projection_revision(row)
                    if row[2] is None:
                        self._connection.execute("ROLLBACK")
                        return GraphQueryResult(
                            status=OperationStatus.REJECTED,
                            summary="there is no prospective definition delta to query",
                            query=query,
                            findings=(ValidationFinding(summary="no definition delta is present"),),
                        )
                    active = self._connection.execute(
                        "SELECT active_definition_set_id FROM state_head WHERE id = 0"
                    ).fetchone()
                    assert active is not None
                    definitions = self._effective_proposed_definitions_unlocked(
                        str(active[0]),
                        type_keys=_query_type_keys(query),
                        constrained_type_keys=set(),
                    )
                    result = self._evaluate_sql_query_unlocked(
                        query,
                        definitions,
                        revision,
                        prospective=True,
                    )
                    self._connection.execute("COMMIT")
                    return result
                except BaseException:
                    self._rollback_quietly()
                    raise
        except sqlite3.Error as error:
            raise StoreError(f"could not query the proposal at {self._path}: {error}") from error

    def _evaluate_sql_query_unlocked(
        self,
        query: GraphQuery,
        definitions: GraphDefinitionSet,
        revision: int,
        *,
        historical_revision: int | None = None,
        prospective: bool = False,
        validate: bool = True,
        existence_only: bool = False,
    ) -> GraphQueryResult:
        from vellis.query import (
            AnchorBinding,
            AnchorProjection,
            AssociatedDataBinding,
            AssociatedDataProjection,
            DataPropertyProjection,
            GraphQueryResult,
            GraphQueryRow,
            LinkBinding,
            LinkProjection,
            ReturnedProperty,
            ReturnProjection,
            indexed_query_findings,
        )

        response_query = query
        if validate:
            findings = indexed_query_findings(
                query, definitions, _SQLiteQueryIndex(self, historical_revision, prospective)
            )
            if findings:
                return GraphQueryResult(
                    status=OperationStatus.REJECTED,
                    summary=f"the query was not evaluated ({len(findings)} findings)",
                    findings=findings,
                    query=response_query,
                )
            projected = _projected_selector_names(query)
            projected_components: list[frozenset[str]] = []
            for component in _query_component_names(query):
                if component & projected:
                    projected_components.append(component)
                    continue
                existence = self._evaluate_sql_query_unlocked(
                    _component_query(query, set(component), projections=False),
                    definitions,
                    revision,
                    historical_revision=historical_revision,
                    prospective=prospective,
                    validate=False,
                    existence_only=True,
                )
                if not existence.rows:
                    return GraphQueryResult(
                        status=OperationStatus.ACCEPTED,
                        summary=f"0 rows at revision {revision}",
                        query=response_query,
                        evaluated_revision=revision,
                    )
            kept = set().union(*projected_components)
            query = _component_query(query, kept, projections=True)

        prefix = ""
        prefix_parameters: list[object] = []
        graph_relation = "current_graph_object"
        association_relation = "current_data_anchor"
        if prospective:
            graph_relation = "prospective_graph_object"
            association_relation = "prospective_data_anchor"
        if historical_revision is not None:
            graph_relation = "selected_graph_object"
            association_relation = "selected_data_anchor"
            prefix = (
                "WITH selected_graph_object AS NOT MATERIALIZED ("
                "SELECT p.uuid, v.object_kind, v.type_key, v.source_uuid, v.target_uuid,"
                " v.id AS object_value_id FROM graph_presence_interval AS p"
                " JOIN object_value AS v ON v.id = p.object_value_id"
                " WHERE p.valid_from_revision <= ? AND"
                " (p.valid_to_revision IS NULL OR p.valid_to_revision > ?)),"
                " selected_data_anchor AS NOT MATERIALIZED ("
                "SELECT c.uuid AS data_uuid, a.anchor_uuid"
                " FROM selected_graph_object AS c"
                " JOIN object_anchor AS a ON a.object_value_id = c.object_value_id"
                " WHERE c.object_kind = 'associatedData') "
            )
            prefix_parameters.extend((historical_revision, historical_revision))

        tables: list[str] = []
        predicates: list[str] = []
        where_parameters: list[object] = []
        select_parameters: list[object] = []
        selector_alias: dict[str, str] = {}
        for index, group in enumerate(query.anchor_groups):
            alias = f"a{index}"
            selector_alias[group.name] = alias
            tables.append(f"{graph_relation} AS {alias}")
            predicates.extend((f"{alias}.object_kind = ?", f"{alias}.type_key = ?"))
            where_parameters.extend((ObjectKind.ANCHOR.value, group.anchor_type))
            if group.uuid_filter is not None:
                placeholders = ", ".join("?" for _ in group.uuid_filter.uuids)
                predicates.append(f"{alias}.uuid IN ({placeholders})")
                where_parameters.extend(group.uuid_filter.uuids)

        for index, condition in enumerate(query.data_conditions):
            alias, association = f"d{index}", f"da{index}"
            selector_alias[condition.name] = alias
            tables.extend(
                (f"{graph_relation} AS {alias}", f"{association_relation} AS {association}")
            )
            predicates.extend(
                (
                    f"{alias}.object_kind = ?",
                    f"{alias}.type_key = ?",
                    f"{association}.data_uuid = {alias}.uuid",
                    f"{association}.anchor_uuid = {selector_alias[condition.anchor_group]}.uuid",
                )
            )
            where_parameters.extend(
                (ObjectKind.ASSOCIATED_DATA.value, condition.associated_data_type)
            )
            for rule_index, comparison in enumerate(condition.property_conditions):
                property_alias = f"pc{index}_{rule_index}"
                tables.append(f"object_property AS {property_alias}")
                predicates.extend(
                    (
                        f"{property_alias}.object_value_id = {alias}.object_value_id",
                        f"{property_alias}.name = ?",
                    )
                )
                where_parameters.append(comparison.property_name)
                kind, boolean, number, text = json_storage_fields(comparison.expected_value)
                predicates.append(
                    _property_comparison_sql(
                        property_alias,
                        comparison.comparison.value,
                        kind,
                        boolean,
                        number,
                        text,
                        where_parameters,
                    )
                )

        link_alias: dict[str, str] = {}
        for index, required in enumerate(query.required_links):
            alias = f"l{index}"
            link_alias[required.name] = alias
            tables.append(f"{graph_relation} AS {alias}")
            predicates.extend(
                (
                    f"{alias}.object_kind = ?",
                    f"{alias}.type_key = ?",
                    f"{alias}.source_uuid = {selector_alias[required.source_group]}.uuid",
                    f"{alias}.target_uuid = {selector_alias[required.target_group]}.uuid",
                )
            )
            where_parameters.extend((ObjectKind.LINK.value, required.link_type))
            if required.uuid_filter is not None:
                placeholders = ", ".join("?" for _ in required.uuid_filter.uuids)
                predicates.append(f"{alias}.uuid IN ({placeholders})")
                where_parameters.extend(required.uuid_filter.uuids)

        selected: list[str] = ["1"] if existence_only else []
        column_shapes: list[tuple[str, ReturnProjection]] = []
        for projection_index, projection in enumerate(query.return_shape.projections):
            if isinstance(projection, AnchorProjection):
                selected.append(f"{selector_alias[projection.anchor_group]}.object_value_id")
                column_shapes.append(("anchor", projection))
            elif isinstance(projection, LinkProjection):
                selected.append(f"{link_alias[projection.required_link]}.object_value_id")
                column_shapes.append(("link", projection))
            elif isinstance(projection, AssociatedDataProjection):
                selected.append(f"{selector_alias[projection.data_condition]}.object_value_id")
                column_shapes.append(("data", projection))
            else:
                assert isinstance(projection, DataPropertyProjection)
                alias = selector_alias[projection.data_condition]
                for column in ("json_kind", "boolean_value", "number_value", "text_value"):
                    selected.append(
                        "(SELECT "
                        f"pp{projection_index}.{column} FROM object_property"
                        f" AS pp{projection_index}"
                        f" WHERE pp{projection_index}.object_value_id = {alias}.object_value_id"
                        f" AND pp{projection_index}.name = ? LIMIT 1)"
                    )
                    select_parameters.append(projection.property_name)
                column_shapes.append(("property", projection))

        sql = (
            prefix
            + "SELECT DISTINCT "
            + ", ".join(selected)
            + " FROM "
            + ", ".join(tables)
            + " WHERE "
            + " AND ".join(predicates)
            + " LIMIT ?"
        )
        parameters = [
            *prefix_parameters,
            *select_parameters,
            *where_parameters,
            1 if existence_only else query.maximum_rows + 1,
        ]
        cursor = self._connection.execute(sql, tuple(parameters))
        raw_rows = cursor.fetchmany(1 if existence_only else query.maximum_rows + 1)
        if not existence_only and len(raw_rows) > query.maximum_rows:
            return GraphQueryResult(
                status=OperationStatus.REJECTED,
                summary=(
                    f"the result has more than {query.maximum_rows} rows; it is refused whole "
                    "rather than truncated"
                ),
                findings=(
                    ValidationFinding(
                        summary=f"the complete result exceeds the maximum of {query.maximum_rows}"
                    ),
                ),
                query=response_query,
            )

        if existence_only:
            return GraphQueryResult(
                status=OperationStatus.ACCEPTED,
                summary=f"{int(bool(raw_rows))} existence rows at revision {revision}",
                query=response_query,
                evaluated_revision=revision,
                rows=(GraphQueryRow(),) if raw_rows else (),
            )

        rows: list[GraphQueryRow] = []
        for raw in raw_rows:
            offset = 0
            anchors: list[AnchorBinding] = []
            links: list[LinkBinding] = []
            data: list[AssociatedDataBinding] = []
            properties: list[ReturnedProperty] = []
            for shape, projection in column_shapes:
                if shape == "property":
                    assert isinstance(projection, DataPropertyProjection)
                    stored = raw[offset : offset + 4]
                    offset += 4
                    properties.append(
                        ReturnedProperty(
                            projection=projection.name,
                            present=stored[0] is not None,
                            value=(None if stored[0] is None else json_storage_value(*stored)),
                        )
                    )
                    continue
                value = self._load_object_value(int(raw[offset]))
                self._current_graph_object_decodes += 1
                offset += 1
                if shape == "anchor":
                    assert isinstance(projection, AnchorProjection)
                    assert isinstance(value, Anchor)
                    anchors.append(AnchorBinding(projection.name, value))
                elif shape == "link":
                    assert isinstance(projection, LinkProjection)
                    assert isinstance(value, Link)
                    links.append(LinkBinding(projection.name, value))
                else:
                    assert isinstance(projection, AssociatedDataProjection)
                    assert isinstance(value, AssociatedDataObject)
                    data.append(AssociatedDataBinding(projection.name, value))
            rows.append(GraphQueryRow(tuple(anchors), tuple(links), tuple(data), tuple(properties)))
        return GraphQueryResult(
            status=OperationStatus.ACCEPTED,
            summary=f"{len(rows)} rows at revision {revision}",
            query=response_query,
            evaluated_revision=revision,
            rows=tuple(rows),
        )

    def current_definitions(self) -> tuple[int, GraphDefinitionSet, DefinitionDelta | None]:
        """Read current definition facets without materializing the graph facet."""
        with self._lock:
            row = self._connection.execute(
                "SELECT revision, established_by, active_definition_set_id,"
                " proposed_definition_set_id FROM state_head WHERE id = 0"
            ).fetchone()
            if not isinstance(row, tuple):
                raise NotInitializedError("no canonical state is established")
            return (
                _projection_revision(row),
                self._load_definition_set(str(row[2])),
                None
                if row[3] is None
                else DefinitionDelta(
                    proposed_definitions=self._effective_proposed_definitions_unlocked(str(row[2])),
                    graph_overlay=self._proposal_graph_change_unlocked(),
                ),
            )

    def definition_view(self, *, prospective: bool = False) -> tuple[int, GraphDefinitionSet, bool]:
        """Read evaluated definition meaning without reading staged graph objects."""
        with self._lock:
            row = self._connection.execute(
                "SELECT revision, established_by, active_definition_set_id,"
                " proposed_definition_set_id FROM state_head WHERE id = 0"
            ).fetchone()
            if not isinstance(row, tuple):
                raise NotInitializedError("no canonical state is established")
            revision = _projection_revision(row)
            if prospective:
                if row[3] is None:
                    raise StoreError("no definition delta is present")
                definitions = self._effective_proposed_definitions_unlocked(str(row[2]))
            else:
                definitions = self._load_definition_set(str(row[2]))
            return revision, definitions, row[3] is not None

    def _effective_proposed_definitions_unlocked(
        self,
        active_identity: str,
        *,
        type_keys: set[str] | None = None,
        constrained_type_keys: set[str] | None = None,
        relationship_keys: set[str] | None = None,
    ) -> GraphDefinitionSet:
        """Load only requested effective proposal definitions from sparse keyed edits."""
        active = self._load_definition_set(
            active_identity,
            type_keys=type_keys,
            constrained_type_keys=constrained_type_keys,
            relationship_keys=relationship_keys,
        )
        type_rows = self._connection.execute(
            "SELECT type_key, operation, value_set_id FROM proposal_definition_type"
            + (
                ""
                if type_keys is None
                else (
                    " WHERE 0"
                    if not type_keys
                    else " WHERE type_key IN (" + ", ".join("?" for _ in type_keys) + ")"
                )
            ),
            () if type_keys is None else tuple(sorted(type_keys)),
        )
        edited_types = {str(row[0]): row for row in type_rows}
        anchors = [each for each in active.anchor_types if each.type_key not in edited_types]
        data = [each for each in active.associated_data_types if each.type_key not in edited_types]
        links = [each for each in active.link_types if each.type_key not in edited_types]
        for _, operation, value_set_id in edited_types.values():
            if operation == "delete":
                continue
            value = self._load_definition_set(str(value_set_id), constrained_type_keys=set())
            anchors.extend(value.anchor_types)
            data.extend(value.associated_data_types)
            links.extend(value.link_types)

        relationship_sql = (
            "SELECT natural_key, operation, value_set_id FROM proposal_definition_relationship"
        )
        parameters: tuple[object, ...] = ()
        if relationship_keys is not None:
            if not relationship_keys:
                relationship_sql += " WHERE 0"
            else:
                relationship_sql += (
                    " WHERE natural_key IN (" + ", ".join("?" for _ in relationship_keys) + ")"
                )
                parameters = tuple(sorted(relationship_keys))
        elif constrained_type_keys is not None:
            if not constrained_type_keys:
                relationship_sql += " WHERE 0"
            else:
                placeholders = ", ".join("?" for _ in constrained_type_keys)
                relationship_sql += (
                    " AS e WHERE (e.operation = 'upsert' AND EXISTS ("
                    " SELECT 1 FROM definition_multiplicity_rule AS r"
                    " JOIN definition_multiplicity_participant AS p"
                    " ON p.definition_set_id = r.definition_set_id"
                    " AND p.rule_occurrence = r.occurrence AND p.role = 'first'"
                    " WHERE r.definition_set_id = e.value_set_id"
                    f" AND p.type_key IN ({placeholders})))"
                    " OR (e.operation = 'delete' AND EXISTS ("
                    " SELECT 1 FROM definition_multiplicity_rule AS r"
                    " JOIN definition_multiplicity_participant AS p"
                    " ON p.definition_set_id = r.definition_set_id"
                    " AND p.rule_occurrence = r.occurrence AND p.role = 'first'"
                    " WHERE r.definition_set_id = ? AND r.natural_key = e.natural_key"
                    f" AND p.type_key IN ({placeholders})))"
                )
                selected = tuple(sorted(constrained_type_keys))
                parameters = (*selected, active_identity, *selected)
        relationship_rows = self._connection.execute(relationship_sql, parameters)
        edited_relationships = {str(row[0]): row for row in relationship_rows}
        relationships = [
            each
            for each in active.relationship_constraints
            if semantic_identity(relationship_identity(each)) not in edited_relationships
        ]
        for _, operation, value_set_id in edited_relationships.values():
            if operation == "delete":
                continue
            value = self._load_definition_set(
                str(value_set_id), type_keys=set(), constrained_type_keys=None
            )
            relationships.extend(value.relationship_constraints)
        return GraphDefinitionSet(tuple(anchors), tuple(data), tuple(links), tuple(relationships))

    def _definition_entry_digest(self, key: str, operation: str, value: str | None) -> str:
        return semantic_identity((key, operation, value))

    def _definition_accumulator_update_unlocked(
        self,
        before: str | None,
        after: str | None,
        before_content: str | None,
        after_content: str | None,
    ) -> None:
        row = self._connection.execute(
            "SELECT accumulator, entry_count, effective_accumulator, effective_entry_count"
            " FROM proposal_definition_state WHERE id = 0"
        ).fetchone()
        assert row is not None
        accumulator, count = int(str(row[0]), 16), int(row[1])
        if row[2] is None or row[3] is None:
            raise StoreError("the proposal definition accumulator has no active base")
        effective, effective_count = int(str(row[2]), 16), int(row[3])
        if before is not None:
            accumulator ^= int(before, 16)
            count -= 1
        if after is not None:
            accumulator ^= int(after, 16)
            count += 1
        if before_content is not None:
            effective = (effective - int(before_content, 16)) % (1 << 256)
            effective_count -= 1
        if after_content is not None:
            effective = (effective + int(after_content, 16)) % (1 << 256)
            effective_count += 1
        self._connection.execute(
            "UPDATE proposal_definition_state SET accumulator = ?, entry_count = ?,"
            " effective_accumulator = ?, effective_entry_count = ? WHERE id = 0",
            (f"{accumulator:064x}", count, f"{effective:064x}", effective_count),
        )

    def _proposal_definition_identity_unlocked(self, active_identity: str) -> str:
        row = self._connection.execute(
            "SELECT entry_count, effective_accumulator, effective_entry_count"
            " FROM proposal_definition_state WHERE id = 0"
        ).fetchone()
        assert row is not None
        if int(row[0]) == 0:
            return active_identity
        if row[1] is None or row[2] is None:
            raise StoreError("the proposal definition identity has no content summary")
        return definition_identity_from_stats(str(row[1]), int(row[2]))

    def _definition_value_digest_unlocked(self, value_set_id: str) -> str:
        row = self._connection.execute(
            "SELECT content_accumulator, entry_count FROM definition_set WHERE identity = ?",
            (value_set_id,),
        ).fetchone()
        if row is None or int(row[1]) != 1:
            raise StoreError("a sparse definition entry does not reference exactly one value")
        return str(row[0])

    def stage_definition_change(
        self, change: DefinitionChange, *, provenance: Provenance
    ) -> RevisionedOutcome:
        """Stage one bounded natural-keyed definition edit without copying the set."""
        findings = definition_change_findings(change)
        if findings:
            return RevisionedOutcome(
                OperationStatus.REJECTED,
                f"the definition edit was rejected ({len(findings)} findings)",
                findings,
            )
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                head = self._connection.execute(
                    "SELECT revision, active_definition_set_id, proposed_definition_set_id"
                    " FROM state_head WHERE id = 0"
                ).fetchone()
                if head is None:
                    raise NotInitializedError("no canonical state is established")
                revision, active_identity = int(head[0]), str(head[1])
                before_proposed = None if head[2] is None else str(head[2])
                effective = self._connection.execute(
                    "SELECT effective_accumulator FROM proposal_definition_state WHERE id = 0"
                ).fetchone()
                if effective is None:
                    raise StoreError("the proposal definition state is absent")
                if effective[0] is None:
                    active_stats = self._connection.execute(
                        "SELECT content_accumulator, entry_count FROM definition_set"
                        " WHERE identity = ?",
                        (active_identity,),
                    ).fetchone()
                    if active_stats is None:
                        raise StoreError("the active definition content summary is absent")
                    self._connection.execute(
                        "UPDATE proposal_definition_state SET effective_accumulator = ?,"
                        " effective_entry_count = ? WHERE id = 0",
                        (str(active_stats[0]), int(active_stats[1])),
                    )
                changed = False
                definition_events: list[tuple[str, str, str, str | None]] = []

                type_upserts = (
                    *change.anchor_type_upserts,
                    *change.associated_data_type_upserts,
                    *change.link_type_upserts,
                )
                for type_key, value in (
                    *((key, None) for key in change.type_removals),
                    *((value.type_key, value) for value in type_upserts),
                ):
                    prior = self._connection.execute(
                        "SELECT operation, value_set_id FROM proposal_definition_type"
                        " WHERE type_key = ?",
                        (type_key,),
                    ).fetchone()
                    prior_digest = (
                        None
                        if prior is None
                        else self._definition_entry_digest(
                            type_key,
                            str(prior[0]),
                            None if prior[1] is None else str(prior[1]),
                        )
                    )
                    active = self._load_definition_set(
                        active_identity,
                        type_keys={type_key},
                        constrained_type_keys=set(),
                    )
                    active_count = definition_content_stats(active)[1]
                    active_content = None if active_count == 0 else definition_entry_digest(active)
                    prior_content = (
                        active_content
                        if prior is None
                        else None
                        if str(prior[0]) == "delete"
                        else self._definition_value_digest_unlocked(str(prior[1]))
                    )
                    if value is None:
                        value_set_id = None
                        operation = (
                            "delete"
                            if (
                                active.anchor_types
                                or active.associated_data_types
                                or active.link_types
                            )
                            else None
                        )
                    else:
                        if isinstance(value, AnchorTypeDefinition):
                            single = GraphDefinitionSet(anchor_types=(value,))
                        elif isinstance(value, AssociatedDataTypeDefinition):
                            single = GraphDefinitionSet(associated_data_types=(value,))
                        else:
                            assert isinstance(value, LinkTypeDefinition)
                            single = GraphDefinitionSet(link_types=(value,))
                        value_set_id = insert_definition_set(self._connection, single)
                        active_single = (
                            GraphDefinitionSet(anchor_types=active.anchor_types)
                            if active.anchor_types
                            else GraphDefinitionSet(
                                associated_data_types=active.associated_data_types
                            )
                            if active.associated_data_types
                            else GraphDefinitionSet(link_types=active.link_types)
                        )
                        operation = (
                            None if definition_identity(active_single) == value_set_id else "upsert"
                        )
                    if operation is None:
                        self._connection.execute(
                            "DELETE FROM proposal_definition_type WHERE type_key = ?",
                            (type_key,),
                        )
                        after_digest = None
                    else:
                        self._connection.execute(
                            "INSERT INTO proposal_definition_type VALUES (?, ?, ?)"
                            " ON CONFLICT(type_key) DO UPDATE SET"
                            " operation=excluded.operation, value_set_id=excluded.value_set_id",
                            (type_key, operation, value_set_id),
                        )
                        after_digest = self._definition_entry_digest(
                            type_key, operation, value_set_id
                        )
                    if prior_digest != after_digest:
                        after_content = (
                            active_content
                            if operation is None
                            else None
                            if operation == "delete"
                            else self._definition_value_digest_unlocked(str(value_set_id))
                        )
                        self._definition_accumulator_update_unlocked(
                            prior_digest, after_digest, prior_content, after_content
                        )
                        changed = True
                        definition_events.append(
                            (
                                "type",
                                type_key,
                                "unstage" if operation is None else operation,
                                value_set_id if operation == "upsert" else None,
                            )
                        )

                relationship_commands = (
                    *(
                        (selection.identity(), None)
                        for selection in change.link_multiplicity_removals
                    ),
                    *(
                        (selection.identity(), None)
                        for selection in change.direct_association_multiplicity_removals
                    ),
                    *(
                        (relationship_identity(value), value)
                        for value in change.relationship_constraint_upserts
                    ),
                )
                for natural_identity, value in relationship_commands:
                    natural_key = semantic_identity(natural_identity)
                    prior = self._connection.execute(
                        "SELECT operation, value_set_id"
                        " FROM proposal_definition_relationship WHERE natural_key = ?",
                        (natural_key,),
                    ).fetchone()
                    prior_digest = (
                        None
                        if prior is None
                        else self._definition_entry_digest(
                            natural_key,
                            str(prior[0]),
                            None if prior[1] is None else str(prior[1]),
                        )
                    )
                    active = self._load_definition_set(
                        active_identity,
                        type_keys=set(),
                        relationship_keys={natural_key},
                    )
                    active_count = definition_content_stats(active)[1]
                    active_content = None if active_count == 0 else definition_entry_digest(active)
                    prior_content = (
                        active_content
                        if prior is None
                        else None
                        if str(prior[0]) == "delete"
                        else self._definition_value_digest_unlocked(str(prior[1]))
                    )
                    if value is None:
                        value_set_id = None
                        operation = "delete" if active.relationship_constraints else None
                    else:
                        single = GraphDefinitionSet(relationship_constraints=(value,))
                        value_set_id = insert_definition_set(self._connection, single)
                        operation = (
                            None
                            if definition_identity(
                                GraphDefinitionSet(
                                    relationship_constraints=active.relationship_constraints
                                )
                            )
                            == value_set_id
                            else "upsert"
                        )
                    if operation is None:
                        self._connection.execute(
                            "DELETE FROM proposal_definition_relationship WHERE natural_key = ?",
                            (natural_key,),
                        )
                        after_digest = None
                    else:
                        self._connection.execute(
                            "INSERT INTO proposal_definition_relationship VALUES (?, ?, ?)"
                            " ON CONFLICT(natural_key) DO UPDATE SET"
                            " operation=excluded.operation, value_set_id=excluded.value_set_id",
                            (natural_key, operation, value_set_id),
                        )
                        after_digest = self._definition_entry_digest(
                            natural_key, operation, value_set_id
                        )
                    if prior_digest != after_digest:
                        after_content = (
                            active_content
                            if operation is None
                            else None
                            if operation == "delete"
                            else self._definition_value_digest_unlocked(str(value_set_id))
                        )
                        self._definition_accumulator_update_unlocked(
                            prior_digest, after_digest, prior_content, after_content
                        )
                        changed = True
                        definition_events.append(
                            (
                                "relationship",
                                natural_key,
                                "unstage" if operation is None else operation,
                                value_set_id if operation == "upsert" else None,
                            )
                        )

                definition_count = int(
                    self._connection.execute(
                        "SELECT entry_count FROM proposal_definition_state WHERE id = 0"
                    ).fetchone()[0]
                )
                graph_count = int(
                    self._connection.execute(
                        "SELECT entry_count FROM proposal_overlay_state WHERE id = 0"
                    ).fetchone()[0]
                )
                if not changed:
                    self._connection.execute("ROLLBACK")
                    return RevisionedOutcome(
                        OperationStatus.ACCEPTED,
                        "the proposed definition edit changes no proposal meaning",
                    )
                if definition_count == 0 and graph_count == 0:
                    self._connection.execute("ROLLBACK")
                    if before_proposed is None:
                        return RevisionedOutcome(
                            OperationStatus.ACCEPTED,
                            "the definition edit matches active meaning; nothing was staged",
                        )
                    return RevisionedOutcome(
                        OperationStatus.REJECTED,
                        "the edit would remove the proposal's final semantic difference;"
                        " use discard",
                        (ValidationFinding(summary="a proposal cannot be discarded implicitly"),),
                    )
                proposed_identity = self._proposal_definition_identity_unlocked(active_identity)
                self._connection.execute(
                    "UPDATE proposal_definition_state SET base_definition_set_id = ?,"
                    " identity = ? WHERE id = 0",
                    (active_identity, proposed_identity),
                )
                resulting = revision + 1
                self._append_proposal_transition_unlocked(
                    revision,
                    resulting,
                    proposed_identity,
                    [],
                    provenance,
                    definition_events=definition_events,
                )
                self._connection.execute("COMMIT")
                return RevisionedOutcome(
                    OperationStatus.ACCEPTED,
                    f"staged definition work at revision {resulting}",
                    resulting_revision=resulting,
                )
            except Exception as error:
                self._rollback_quietly()
                if isinstance(error, StoreError):
                    raise
                raise StoreError(f"could not stage definition work: {error}") from error

    def _proposal_graph_change_unlocked(self) -> GraphChange:
        anchors: list[Anchor] = []
        data: list[AssociatedDataObject] = []
        links: list[Link] = []
        removals: dict[ObjectKind, list[str]] = {kind: [] for kind in ObjectKind}
        for uuid, kind_name, operation, value_id in self._connection.execute(
            "SELECT uuid, object_kind, operation, object_value_id FROM proposal_entry ORDER BY uuid"
        ):
            kind = ObjectKind(str(kind_name))
            if operation == "delete":
                removals[kind].append(str(uuid))
                continue
            value = self._load_object_value(int(value_id))
            if isinstance(value, Anchor):
                anchors.append(value)
            elif isinstance(value, AssociatedDataObject):
                data.append(value)
            else:
                links.append(value)
        return GraphChange(
            tuple(anchors),
            tuple(data),
            tuple(links),
            tuple(removals[ObjectKind.ANCHOR]),
            tuple(removals[ObjectKind.ASSOCIATED_DATA]),
            tuple(removals[ObjectKind.LINK]),
        )

    def proposal_state(self) -> ProposalState:
        """Return bounded identities, counts, and exact current assessment for the delta."""
        try:
            with self._lock:
                row = self._connection.execute(
                    "SELECT revision, established_by, proposed_definition_set_id"
                    " FROM state_head WHERE id = 0"
                ).fetchone()
                if not isinstance(row, tuple):
                    raise NotInitializedError("no canonical state is established")
                revision = _projection_revision(row)
                if row[2] is None:
                    return ProposalState(revision, None, None)
                proposed = str(row[2])
                overlay = self._overlay_identity_unlocked()
                counts = {
                    (str(kind), str(operation)): int(count)
                    for kind, operation, count in self._connection.execute(
                        "SELECT object_kind, operation, entry_count FROM proposal_overlay_count"
                    )
                }
                assessment = self._current_assessment_unlocked(
                    ValidationScope.DEFINITION_DELTA,
                    revision=revision,
                    proposed_identity=proposed,
                    overlay_identity=overlay,
                )
                return ProposalState(
                    revision,
                    proposed,
                    overlay,
                    sum(
                        counts.get((ObjectKind.ANCHOR.value, operation), 0)
                        for operation in ("upsert", "delete")
                    ),
                    sum(
                        counts.get((ObjectKind.ASSOCIATED_DATA.value, operation), 0)
                        for operation in ("upsert", "delete")
                    ),
                    sum(
                        counts.get((ObjectKind.LINK.value, operation), 0)
                        for operation in ("upsert", "delete")
                    ),
                    sum(counts.get((kind.value, "delete"), 0) for kind in ObjectKind),
                    assessment,
                )
        except sqlite3.Error as error:
            raise StoreError(f"could not read proposal state: {error}") from error

    def _overlay_identity_unlocked(self) -> str:
        row = self._connection.execute(
            "SELECT accumulator, entry_count FROM proposal_overlay_state WHERE id = 0"
        ).fetchone()
        if row is None:
            raise StoreError("the proposal overlay has no identity state")
        return semantic_identity(("graphOverlay", str(row[0]), int(row[1])))

    def _proposal_entry_digest_unlocked(self, uuid: str) -> str | None:
        row = self._connection.execute(
            "SELECT p.object_kind, p.operation, v.content_identity"
            " FROM proposal_entry AS p LEFT JOIN object_value AS v"
            " ON v.id = p.object_value_id WHERE p.uuid = ?",
            (uuid,),
        ).fetchone()
        if row is None:
            return None
        return semantic_identity((uuid, *(None if each is None else str(each) for each in row)))

    def _update_overlay_accumulator_unlocked(self, before: str | None, after: str | None) -> None:
        row = self._connection.execute(
            "SELECT accumulator, entry_count FROM proposal_overlay_state WHERE id = 0"
        ).fetchone()
        if row is None:
            raise StoreError("the proposal overlay has no identity state")
        accumulator = int(str(row[0]), 16)
        count = int(row[1])
        if before is not None:
            accumulator ^= int(before, 16)
            count -= 1
        if after is not None:
            accumulator ^= int(after, 16)
            count += 1
        self._connection.execute(
            "UPDATE proposal_overlay_state SET accumulator = ?, entry_count = ? WHERE id = 0",
            (f"{accumulator:064x}", count),
        )

    def stage_proposal_graph(
        self, request: GraphChangeRequest, *, provenance: Provenance
    ) -> RevisionedOutcome:
        """Apply one bounded graph-overlay edit and record it atomically."""
        if request.target is not GraphChangeTarget.DEFINITION_DELTA:
            raise ValueError("stage_proposal_graph requires a definition-delta target")
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                head = self._connection.execute(
                    "SELECT revision, active_definition_set_id, proposed_definition_set_id"
                    " FROM state_head WHERE id = 0"
                ).fetchone()
                if head is None:
                    self._connection.execute("ROLLBACK")
                    raise NotInitializedError("no canonical state is established")
                revision = int(head[0])
                findings = self._proposal_command_findings_unlocked(request)
                if findings:
                    self._connection.execute("ROLLBACK")
                    return RevisionedOutcome(
                        OperationStatus.REJECTED,
                        f"the prospective graph change was rejected ({len(findings)} findings)",
                        findings,
                    )
                before_definition = None if head[2] is None else str(head[2])
                proposed_identity = before_definition or str(head[1])
                before_overlay = self._overlay_identity_unlocked()
                changed_events: list[tuple[str, ObjectKind, str, int | None]] = []
                for kind, uuid in request.unstaging():
                    prior_digest = self._proposal_entry_digest_unlocked(uuid)
                    self._connection.execute("DELETE FROM proposal_entry WHERE uuid = ?", (uuid,))
                    self._update_overlay_accumulator_unlocked(prior_digest, None)
                    changed_events.append(("unstage", kind, uuid, None))
                for kind, uuid in request.change.removals():
                    prior_digest = self._proposal_entry_digest_unlocked(uuid)
                    base = self._active_value_unlocked(uuid)
                    if base is None:
                        self._connection.execute(
                            "DELETE FROM proposal_entry WHERE uuid = ?", (uuid,)
                        )
                        self._update_overlay_accumulator_unlocked(prior_digest, None)
                        if prior_digest is not None:
                            changed_events.append(("unstage", kind, uuid, None))
                        continue
                    self._connection.execute(
                        "INSERT INTO proposal_entry"
                        " (uuid, object_kind, operation, object_value_id, base_object_value_id)"
                        " VALUES (?, ?, 'delete', NULL, ?)"
                        " ON CONFLICT(uuid) DO UPDATE SET object_kind=excluded.object_kind,"
                        " operation='delete', object_value_id=NULL,"
                        " base_object_value_id=excluded.base_object_value_id",
                        (uuid, kind.value, base),
                    )
                    after_digest = self._proposal_entry_digest_unlocked(uuid)
                    if prior_digest != after_digest:
                        self._update_overlay_accumulator_unlocked(prior_digest, after_digest)
                        changed_events.append(("delete", kind, uuid, None))
                for kind, value in request.change.upserts():
                    prior_digest = self._proposal_entry_digest_unlocked(value.uuid)
                    value_id = insert_object_value(self._connection, value)
                    base = self._active_value_unlocked(value.uuid)
                    if base == value_id:
                        prior = self._connection.execute(
                            "SELECT 1 FROM proposal_entry WHERE uuid = ?", (value.uuid,)
                        ).fetchone()
                        if prior is not None:
                            self._connection.execute(
                                "DELETE FROM proposal_entry WHERE uuid = ?", (value.uuid,)
                            )
                            self._update_overlay_accumulator_unlocked(prior_digest, None)
                            changed_events.append(("unstage", kind, value.uuid, None))
                        continue
                    self._connection.execute(
                        "INSERT INTO proposal_entry"
                        " (uuid, object_kind, operation, object_value_id, base_object_value_id)"
                        " VALUES (?, ?, 'upsert', ?, ?)"
                        " ON CONFLICT(uuid) DO UPDATE SET object_kind=excluded.object_kind,"
                        " operation='upsert', object_value_id=excluded.object_value_id,"
                        " base_object_value_id=excluded.base_object_value_id",
                        (value.uuid, kind.value, value_id, base),
                    )
                    after_digest = self._proposal_entry_digest_unlocked(value.uuid)
                    if prior_digest != after_digest:
                        self._update_overlay_accumulator_unlocked(prior_digest, after_digest)
                        changed_events.append(("upsert", kind, value.uuid, value_id))
                after_overlay = self._overlay_identity_unlocked()
                if before_definition == proposed_identity and before_overlay == after_overlay:
                    # Refreshing the conflict-detection base is realization metadata, not
                    # modeled overlay meaning. Preserve it without creating a canonical
                    # revision when the requested keyed overlay is otherwise identical.
                    self._connection.execute("COMMIT")
                    return RevisionedOutcome(
                        OperationStatus.ACCEPTED,
                        "the prospective graph edit changes no proposal meaning",
                    )
                proposal_count = int(
                    self._connection.execute(
                        "SELECT entry_count FROM proposal_overlay_state WHERE id = 0"
                    ).fetchone()[0]
                )
                if (
                    before_definition is not None
                    and proposal_count == 0
                    and proposed_identity == str(head[1])
                ):
                    self._connection.execute("ROLLBACK")
                    return RevisionedOutcome(
                        OperationStatus.REJECTED,
                        "the edit would remove the proposal's final semantic difference; "
                        "use discard",
                        (
                            ValidationFinding(
                                summary=(
                                    "the final proposal difference cannot be unstaged implicitly"
                                )
                            ),
                        ),
                    )
                if (
                    before_definition is None
                    and proposal_count == 0
                    and proposed_identity == str(head[1])
                ):
                    self._connection.execute("ROLLBACK")
                    return RevisionedOutcome(
                        OperationStatus.ACCEPTED,
                        "the prospective graph edit changes no proposal meaning",
                    )
                resulting = revision + 1
                self._append_proposal_transition_unlocked(
                    revision,
                    resulting,
                    proposed_identity,
                    changed_events,
                    provenance,
                )
                self._connection.execute("COMMIT")
                return RevisionedOutcome(
                    OperationStatus.ACCEPTED,
                    f"staged prospective graph work at revision {resulting}",
                    resulting_revision=resulting,
                )
            except StoreError:
                self._rollback_quietly()
                raise
            except Exception as error:
                self._rollback_quietly()
                raise StoreError(f"could not stage prospective graph work: {error}") from error

    def _base_value_for_proposal_unlocked(self, uuid: str) -> int | None:
        existing = self._connection.execute(
            "SELECT base_object_value_id FROM proposal_entry WHERE uuid = ?", (uuid,)
        ).fetchone()
        if existing is not None:
            return None if existing[0] is None else int(existing[0])
        active = self._connection.execute(
            "SELECT object_value_id FROM current_graph_object WHERE uuid = ?", (uuid,)
        ).fetchone()
        return None if active is None else int(active[0])

    def _active_value_unlocked(self, uuid: str) -> int | None:
        active = self._connection.execute(
            "SELECT object_value_id FROM current_graph_object WHERE uuid = ?", (uuid,)
        ).fetchone()
        return None if active is None else int(active[0])

    def _proposal_command_findings_unlocked(
        self, request: GraphChangeRequest
    ) -> tuple[ValidationFinding, ...]:
        findings: list[ValidationFinding] = []
        commands = [
            *((value.uuid, kind, "upsert") for kind, value in request.change.upserts()),
            *((uuid, kind, "delete") for kind, uuid in request.change.removals()),
            *((uuid, kind, "unstage") for kind, uuid in request.unstaging()),
        ]
        seen: set[str] = set()
        for uuid, kind, operation in commands:
            if uuid in seen:
                findings.append(
                    ValidationFinding(
                        summary=f"{uuid!r} has more than one command in the proposal edit",
                        implicated_objects=(uuid,),
                    )
                )
                continue
            seen.add(uuid)
            effective = self._connection.execute(
                "SELECT object_kind FROM prospective_graph_object WHERE uuid = ?", (uuid,)
            ).fetchone()
            current = self._connection.execute(
                "SELECT object_kind FROM current_graph_object WHERE uuid = ?", (uuid,)
            ).fetchone()
            if operation != "unstage" and current is not None and str(current[0]) != kind.value:
                findings.append(
                    ValidationFinding(
                        summary=(
                            f"{uuid!r} is currently {current[0]} and cannot be staged as"
                            f" {kind.value}"
                        ),
                        implicated_objects=(uuid,),
                    )
                )
                continue
            if operation == "unstage":
                staged = self._connection.execute(
                    "SELECT object_kind FROM proposal_entry WHERE uuid = ?", (uuid,)
                ).fetchone()
                if staged is None or str(staged[0]) != kind.value:
                    findings.append(
                        ValidationFinding(
                            summary=f"{uuid!r} is not staged as {kind.value}",
                            implicated_objects=(uuid,),
                        )
                    )
            elif operation == "delete":
                if effective is None:
                    findings.append(
                        ValidationFinding(
                            summary=(
                                f"{uuid!r} is removed but no effective prospective object exists"
                            ),
                            implicated_objects=(uuid,),
                        )
                    )
                elif str(effective[0]) != kind.value:
                    findings.append(
                        ValidationFinding(
                            summary=f"{uuid!r} is removed as {kind.value} but is {effective[0]}",
                            implicated_objects=(uuid,),
                        )
                    )
            elif effective is not None and str(effective[0]) != kind.value:
                findings.append(
                    ValidationFinding(
                        summary=f"{uuid!r} cannot change object kind in prospective state",
                        implicated_objects=(uuid,),
                    )
                )
        return tuple(findings)

    def _append_proposal_transition_unlocked(
        self,
        prior_revision: int,
        resulting_revision: int,
        proposed_identity: str,
        events: list[tuple[str, ObjectKind, str, int | None]],
        provenance: Provenance,
        *,
        definition_events: list[tuple[str, str, str, str | None]] | None = None,
    ) -> None:
        previous = self._connection.execute(
            "SELECT r.record_identity FROM canonical_record AS r"
            " JOIN state_head AS h ON h.established_by = r.established_revision WHERE h.id = 0"
        ).fetchone()
        ledger = self._connection.execute("SELECT identity FROM ledger WHERE id = 0").fetchone()
        if previous is None or ledger is None:
            raise StoreError("the canonical ledger has no identity-bearing base")
        recorded_at = now()
        content = semantic_identity(
            (
                proposed_identity,
                self._overlay_identity_unlocked(),
                tuple(
                    (operation, kind.value, uuid, value_id)
                    for operation, kind, uuid, value_id in events
                ),
                tuple(definition_events or ()),
            )
        )
        record_identity = self._record_identity(
            str(ledger[0]),
            str(previous[0]),
            resulting_revision,
            TransitionKind.DEFINITION_DELTA_CHANGE.value,
            recorded_at,
            provenance.initiator,
            provenance.source,
            str(prior_revision),
            content,
        )
        self._connection.execute(
            "INSERT INTO canonical_record (established_revision, ordinal, record_kind,"
            " recorded_at, initiator, source, summary, prior_revision, record_identity,"
            " prior_record_identity) VALUES (?, ("
            + NEXT_ORDINAL_SQL
            + "), ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                resulting_revision,
                TransitionKind.DEFINITION_DELTA_CHANGE.value,
                _stored_time(recorded_at),
                provenance.initiator,
                provenance.source,
                str(prior_revision),
                prior_revision,
                record_identity,
                str(previous[0]),
            ),
        )
        self._connection.execute(
            "UPDATE state_head SET revision = ?, established_by = ?,"
            " proposed_definition_set_id = ? WHERE id = 0",
            (resulting_revision, resulting_revision, proposed_identity),
        )
        for occurrence, (operation, kind, uuid, value_id) in enumerate(events):
            self._connection.execute(
                "INSERT INTO canonical_proposal_event VALUES (?, ?, ?, ?, ?, ?)",
                (resulting_revision, occurrence, operation, kind.value, uuid, value_id),
            )
        for occurrence, (entity_kind, natural_key, operation, value_set_id) in enumerate(
            definition_events or ()
        ):
            self._connection.execute(
                "INSERT INTO canonical_definition_proposal_event VALUES (?, ?, ?, ?, ?, ?)",
                (
                    resulting_revision,
                    occurrence,
                    entity_kind,
                    natural_key,
                    operation,
                    value_set_id,
                ),
            )
        self._connection.execute(
            "INSERT INTO canonical_definition_event"
            " (established_revision, active_definition_set_id, delta_disposition,"
            " proposed_definition_set_id) VALUES (?, NULL, 'present', ?)",
            (resulting_revision, proposed_identity),
        )

    def _current_assessment_unlocked(
        self,
        scope: ValidationScope,
        *,
        revision: int,
        proposed_identity: str | None,
        overlay_identity: str | None,
    ) -> ValidationReport | None:
        row = self._connection.execute(
            "SELECT a.identity, a.evaluated_revision, a.proposed_definition_set_id,"
            " a.graph_overlay_identity FROM current_assessment AS c"
            " JOIN validation_assessment AS a ON a.identity = c.assessment_id"
            " WHERE c.scope = ?",
            (scope.value,),
        ).fetchone()
        if row is None:
            return None
        if (
            int(row[1]) != revision
            or (None if row[2] is None else str(row[2])) != proposed_identity
            or (None if row[3] is None else str(row[3])) != overlay_identity
        ):
            return None
        return self._assessment_report_unlocked(str(row[0]), 1, 1)

    def assessment_page(
        self, assessment_id: str, start_ordinal: int, maximum_findings: int
    ) -> ValidationReport | None:
        """Read one stable positive ordered interval without reassessment."""
        if start_ordinal < 1 or maximum_findings < 1:
            return None
        with self._lock:
            return self._assessment_report_unlocked(assessment_id, start_ordinal, maximum_findings)

    def _assessment_report_unlocked(
        self, assessment_id: str, start_ordinal: int, maximum_findings: int
    ) -> ValidationReport | None:
        row = self._connection.execute(
            "SELECT scope, evaluated_revision, proposed_definition_set_id,"
            " graph_overlay_identity, conforms, finding_count"
            " FROM validation_assessment WHERE identity = ?",
            (assessment_id,),
        ).fetchone()
        if row is None:
            return None
        count = int(row[5])
        if start_ordinal > max(1, count):
            return None
        finding_rows = self._connection.execute(
            "SELECT ordinal, summary FROM validation_finding"
            " WHERE assessment_id = ? AND ordinal >= ? ORDER BY ordinal LIMIT ?",
            (assessment_id, start_ordinal, maximum_findings),
        ).fetchall()
        findings: list[ValidationFinding] = []
        for ordinal, summary in finding_rows:
            definitions = tuple(
                str(each[0])
                for each in self._connection.execute(
                    "SELECT definition_ref FROM validation_finding_definition"
                    " WHERE assessment_id = ? AND finding_ordinal = ? ORDER BY ordinal",
                    (assessment_id, ordinal),
                )
            )
            objects = tuple(
                str(each[0])
                for each in self._connection.execute(
                    "SELECT object_uuid FROM validation_finding_object"
                    " WHERE assessment_id = ? AND finding_ordinal = ? ORDER BY ordinal",
                    (assessment_id, ordinal),
                )
            )
            findings.append(ValidationFinding(str(summary), definitions, objects))
        returned_start = None if not finding_rows else int(finding_rows[0][0])
        last = 0 if not finding_rows else int(finding_rows[-1][0])
        scope = ValidationScope(str(row[0]))
        return ValidationReport(
            scope=scope,
            conforms=bool(row[4]),
            evaluated_revision=int(row[1]),
            summary=(
                "the assessed state conforms"
                if bool(row[4])
                else "the assessed state does not conform"
            ),
            assessment_id=assessment_id,
            proposed_definition_identity=None if row[2] is None else str(row[2]),
            graph_overlay_identity=None if row[3] is None else str(row[3]),
            finding_count=count,
            returned_start_ordinal=returned_start,
            more_findings=last < count,
            returned_findings=tuple(findings),
        )

    def publish_assessment(
        self,
        scope: ValidationScope,
        evaluated_revision: int,
        findings: Iterator[ValidationFinding],
        *,
        maximum_findings: int,
        proposed_identity: str | None = None,
        overlay_identity: str | None = None,
    ) -> ValidationReport:
        """Persist every streamed finding, then atomically publish the completed slot."""
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                report = self._publish_assessment_unlocked(
                    scope,
                    evaluated_revision,
                    findings,
                    maximum_findings=maximum_findings,
                    proposed_identity=proposed_identity,
                    overlay_identity=overlay_identity,
                )
                self._connection.execute("COMMIT")
                return report
            except Exception as error:
                self._rollback_quietly()
                raise StoreError(f"could not publish validation assessment: {error}") from error

    def assess_and_publish(
        self, scope: ValidationScope, *, maximum_findings: int
    ) -> ValidationReport:
        """Bind, scan, and publish one complete assessment in one SQLite transaction."""
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                revision, relation, definition_identity_value, overlay_identity = (
                    self.conformance_context(scope)
                )
                assert definition_identity_value is not None
                report = self._publish_assessment_unlocked(
                    scope,
                    revision,
                    self.iter_conformance_findings(relation, definition_identity_value),
                    maximum_findings=maximum_findings,
                    proposed_identity=(
                        definition_identity_value
                        if scope is ValidationScope.DEFINITION_DELTA
                        else None
                    ),
                    overlay_identity=overlay_identity,
                )
                self._connection.execute("COMMIT")
                return report
            except Exception as error:
                self._rollback_quietly()
                raise StoreError(f"could not publish validation assessment: {error}") from error

    def _publish_assessment_unlocked(
        self,
        scope: ValidationScope,
        evaluated_revision: int,
        findings: Iterator[ValidationFinding],
        *,
        maximum_findings: int,
        proposed_identity: str | None,
        overlay_identity: str | None,
    ) -> ValidationReport:
        material = (
            scope.value,
            evaluated_revision,
            proposed_identity,
            overlay_identity,
            secrets.token_hex(16),
        )
        assessment_id = semantic_identity(material)
        self._connection.execute(
            "INSERT INTO validation_assessment VALUES (?, ?, ?, ?, ?, 0, 0, ?)",
            (
                assessment_id,
                scope.value,
                evaluated_revision,
                proposed_identity,
                overlay_identity,
                _stored_time(now()),
            ),
        )
        count = 0
        for count, finding in enumerate(findings, start=1):
            self._connection.execute(
                "INSERT INTO validation_finding VALUES (?, ?, ?)",
                (assessment_id, count, finding.summary),
            )
            for ordinal, reference in enumerate(finding.implicated_definitions):
                self._connection.execute(
                    "INSERT INTO validation_finding_definition VALUES (?, ?, ?, ?)",
                    (assessment_id, count, ordinal, reference),
                )
            for ordinal, uuid in enumerate(finding.implicated_objects):
                self._connection.execute(
                    "INSERT INTO validation_finding_object VALUES (?, ?, ?, ?)",
                    (assessment_id, count, ordinal, uuid),
                )
        self._connection.execute(
            "UPDATE validation_assessment SET conforms = ?, finding_count = ? WHERE identity = ?",
            (int(count == 0), count, assessment_id),
        )
        prior = self._connection.execute(
            "SELECT assessment_id FROM current_assessment WHERE scope = ?",
            (scope.value,),
        ).fetchone()
        self._connection.execute(
            "INSERT INTO current_assessment VALUES (?, ?)"
            " ON CONFLICT(scope) DO UPDATE SET assessment_id=excluded.assessment_id",
            (scope.value, assessment_id),
        )
        if prior is not None:
            self._delete_assessment_unlocked(str(prior[0]))
        report = self.assessment_page(assessment_id, 1, maximum_findings)
        assert report is not None
        return report

    def conformance_context(
        self, scope: ValidationScope
    ) -> tuple[int, str, str | None, str | None]:
        """Return exact assessment binding and the SQL relation to scan."""
        with self._lock:
            row = self._connection.execute(
                "SELECT revision, established_by, active_definition_set_id,"
                " proposed_definition_set_id FROM state_head WHERE id = 0"
            ).fetchone()
            if not isinstance(row, tuple):
                raise NotInitializedError("no canonical state is established")
            revision = _projection_revision(row)
            if scope is ValidationScope.DEFINITION_DELTA:
                if row[3] is None:
                    raise StoreError("no definition delta is present")
                proposed = str(row[3])
                return (
                    revision,
                    "prospective_graph_object",
                    proposed,
                    self._overlay_identity_unlocked(),
                )
            return revision, "current_graph_object", str(row[2]), None

    def iter_conformance_findings(
        self, relation: str, definition_identity_value: str
    ) -> Iterator[ValidationFinding]:
        """Yield complete findings while retaining only one local object neighborhood."""
        if relation not in {"current_graph_object", "prospective_graph_object"}:
            raise ValueError("unknown conformance relation")
        if relation == "prospective_graph_object":
            for (uuid,) in self._connection.execute(
                "SELECT p.uuid FROM proposal_entry AS p"
                " LEFT JOIN graph_presence_interval AS c ON c.uuid = p.uuid"
                " AND c.valid_to_revision IS NULL"
                " WHERE (p.base_object_value_id IS NULL AND c.object_value_id IS NOT NULL)"
                " OR (p.base_object_value_id IS NOT NULL"
                " AND (c.object_value_id IS NULL"
                " OR c.object_value_id != p.base_object_value_id)) ORDER BY p.uuid"
            ):
                yield ValidationFinding(
                    summary="staged work has a stale active base; restage this identity",
                    implicated_objects=(str(uuid),),
                )
        # Definition populations are much smaller than graph populations in normal use;
        # W006 replaces this remaining aggregate validator with normalized row checks.
        active_identity = str(
            self._connection.execute(
                "SELECT active_definition_set_id FROM state_head WHERE id = 0"
            ).fetchone()[0]
        )
        if relation == "prospective_graph_object":
            self._prepare_prospective_assessment_scope_unlocked(active_identity)
        yield from self._iter_definition_findings_unlocked(relation, active_identity)
        object_relation = (
            "assessment_effective_object" if relation == "prospective_graph_object" else relation
        )
        object_sql = f"SELECT uuid, object_value_id FROM {object_relation}"
        for uuid, value_id in self._connection.execute(object_sql + " ORDER BY uuid"):
            root = self._load_object_value(int(value_id))
            neighborhood = self._effective_neighborhood_unlocked(object_relation, root)
            type_keys = {value.type_key for value in neighborhood.objects()}
            object_definitions = self._definitions_for_relation_unlocked(
                relation,
                active_identity,
                type_keys=type_keys,
                constrained_type_keys=set(),
                relationship_keys=set(),
            )
            for finding in assess_graph_conformance(neighborhood, object_definitions):
                if finding.implicated_objects and finding.implicated_objects[0] == str(uuid):
                    yield finding
        yield from self._iter_multiplicity_findings_unlocked(relation, active_identity)

    def _prepare_prospective_assessment_scope_unlocked(self, active_identity: str) -> None:
        """Derive the changed-definition and staged-graph invariant closure in SQL."""
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS assessment_impacted_type"
            " (type_key TEXT PRIMARY KEY) WITHOUT ROWID"
        )
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS assessment_definition_type"
            " (type_key TEXT PRIMARY KEY) WITHOUT ROWID"
        )
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS assessment_impacted_uuid"
            " (uuid TEXT PRIMARY KEY) WITHOUT ROWID"
        )
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS assessment_definition_relationship"
            " (natural_key TEXT PRIMARY KEY) WITHOUT ROWID"
        )
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS assessment_impacted_relation"
            " (uuid TEXT PRIMARY KEY) WITHOUT ROWID"
        )
        self._connection.execute("DELETE FROM assessment_impacted_type")
        self._connection.execute("DELETE FROM assessment_definition_type")
        self._connection.execute("DELETE FROM assessment_impacted_uuid")
        self._connection.execute("DELETE FROM assessment_definition_relationship")
        self._connection.execute("DELETE FROM assessment_impacted_relation")
        self._connection.execute(
            "INSERT OR IGNORE INTO assessment_definition_type"
            " SELECT type_key FROM proposal_definition_type"
        )
        for type_key, operation, value_set_id in self._connection.execute(
            "SELECT type_key, operation, value_set_id FROM proposal_definition_type"
        ):
            active = self._load_definition_set(
                active_identity, type_keys={str(type_key)}, constrained_type_keys=set()
            )
            proposed = (
                GraphDefinitionSet()
                if str(operation) == "delete"
                else self._load_definition_set(
                    str(value_set_id), type_keys={str(type_key)}, constrained_type_keys=set()
                )
            )
            if self._graph_validation_signature(active) != self._graph_validation_signature(
                proposed
            ):
                self._connection.execute(
                    "INSERT OR IGNORE INTO assessment_impacted_type VALUES (?)",
                    (str(type_key),),
                )
        # Include every effective type definition that refers to an edited type. A
        # removed anchor type, for example, must revalidate untouched data/link types
        # that still permit it.
        self._connection.execute(
            "INSERT OR IGNORE INTO assessment_definition_type"
            " SELECT DISTINCT t.type_key FROM definition_type AS t"
            " JOIN definition_anchor_permission AS p"
            " ON p.definition_set_id = t.definition_set_id"
            " AND p.type_occurrence = t.occurrence"
            " WHERE t.definition_set_id = ?"
            " AND p.anchor_type_key IN (SELECT type_key FROM proposal_definition_type)"
            " AND NOT EXISTS (SELECT 1 FROM proposal_definition_type AS e"
            " WHERE e.type_key = t.type_key)"
            " UNION SELECT DISTINCT t.type_key FROM definition_type AS t"
            " JOIN definition_endpoint_permission AS p"
            " ON p.definition_set_id = t.definition_set_id"
            " AND p.type_occurrence = t.occurrence"
            " WHERE t.definition_set_id = ?"
            " AND p.type_key IN (SELECT type_key FROM proposal_definition_type)"
            " AND NOT EXISTS (SELECT 1 FROM proposal_definition_type AS e"
            " WHERE e.type_key = t.type_key)",
            (active_identity, active_identity),
        )
        self._connection.execute(
            "INSERT OR IGNORE INTO assessment_definition_type"
            " SELECT DISTINCT t.type_key FROM proposal_definition_type AS e"
            " JOIN definition_type AS t ON t.definition_set_id = e.value_set_id"
            " JOIN definition_anchor_permission AS p"
            " ON p.definition_set_id = t.definition_set_id"
            " AND p.type_occurrence = t.occurrence"
            " WHERE e.operation = 'upsert'"
            " AND p.anchor_type_key IN (SELECT type_key FROM proposal_definition_type)"
            " UNION SELECT DISTINCT t.type_key FROM proposal_definition_type AS e"
            " JOIN definition_type AS t ON t.definition_set_id = e.value_set_id"
            " JOIN definition_endpoint_permission AS p"
            " ON p.definition_set_id = t.definition_set_id"
            " AND p.type_occurrence = t.occurrence"
            " WHERE e.operation = 'upsert'"
            " AND p.type_key IN (SELECT type_key FROM proposal_definition_type)"
        )
        self._connection.execute(
            "INSERT OR IGNORE INTO assessment_definition_relationship"
            " SELECT DISTINCT r.natural_key FROM definition_multiplicity_rule AS r"
            " JOIN definition_multiplicity_participant AS p"
            " ON p.definition_set_id = r.definition_set_id"
            " AND p.rule_occurrence = r.occurrence"
            " WHERE r.definition_set_id = ?"
            " AND p.type_key IN (SELECT type_key FROM proposal_definition_type)"
            " AND NOT EXISTS (SELECT 1 FROM proposal_definition_relationship AS e"
            " WHERE e.natural_key = r.natural_key)"
            " UNION SELECT DISTINCT r.natural_key"
            " FROM definition_multiplicity_rule AS r"
            " WHERE r.definition_set_id = ? AND r.link_type_key IN"
            " (SELECT type_key FROM proposal_definition_type)"
            " AND NOT EXISTS (SELECT 1 FROM proposal_definition_relationship AS e"
            " WHERE e.natural_key = r.natural_key)"
            " UNION SELECT natural_key FROM proposal_definition_relationship"
            " WHERE operation = 'upsert'",
            (active_identity, active_identity),
        )
        self._connection.execute(
            "INSERT OR IGNORE INTO assessment_definition_type"
            " SELECT p.type_key FROM proposal_definition_relationship AS e"
            " JOIN definition_multiplicity_participant AS p"
            " ON p.definition_set_id = e.value_set_id WHERE e.operation = 'upsert'"
        )
        for natural_key, operation, value_set_id in self._connection.execute(
            "SELECT natural_key, operation, value_set_id FROM proposal_definition_relationship"
        ):
            active_rule = self._load_definition_set(
                active_identity, type_keys=set(), relationship_keys={str(natural_key)}
            )
            proposed_rule = (
                GraphDefinitionSet()
                if str(operation) == "delete"
                else self._load_definition_set(
                    str(value_set_id), type_keys=set(), relationship_keys={str(natural_key)}
                )
            )
            if self._multiplicity_validation_signature(
                active_rule
            ) == self._multiplicity_validation_signature(proposed_rule):
                continue
            impacted_types: set[str] = set()
            for rule in (
                *active_rule.relationship_constraints,
                *proposed_rule.relationship_constraints,
            ):
                if isinstance(rule, LinkMultiplicityConstraint):
                    impacted_types.add(rule.link_type_key)
                    impacted_types.update(rule.constrained_endpoint_type_keys)
                    impacted_types.update(rule.opposite_endpoint_type_keys)
                else:
                    impacted_types.update(rule.anchor_type_keys)
                    impacted_types.update(rule.associated_data_type_keys)
            self._connection.executemany(
                "INSERT OR IGNORE INTO assessment_impacted_type VALUES (?)",
                ((type_key,) for type_key in impacted_types),
            )
        self._connection.execute(
            "INSERT OR IGNORE INTO assessment_impacted_uuid"
            " SELECT g.uuid FROM assessment_impacted_type AS t"
            " CROSS JOIN graph_presence_interval AS g INDEXED BY graph_presence_current_type"
            " ON g.object_kind IN ('anchor', 'associatedData', 'link')"
            " AND g.type_key = t.type_key AND g.valid_to_revision IS NULL"
            " WHERE NOT EXISTS (SELECT 1 FROM proposal_entry AS p WHERE p.uuid = g.uuid)"
            " UNION SELECT v.uuid FROM proposal_entry AS p JOIN object_value AS v"
            " ON v.id = p.object_value_id WHERE p.operation = 'upsert'"
            " AND v.type_key IN (SELECT type_key FROM assessment_impacted_type)"
        )
        self._connection.execute(
            "INSERT OR IGNORE INTO assessment_impacted_uuid SELECT uuid FROM proposal_entry"
        )
        self._connection.execute(
            "INSERT OR IGNORE INTO assessment_impacted_uuid"
            " SELECT source_uuid FROM object_value AS v JOIN proposal_entry AS p"
            " ON v.id IN (p.object_value_id, p.base_object_value_id)"
            " WHERE v.object_kind = 'link'"
            " UNION SELECT target_uuid FROM object_value AS v JOIN proposal_entry AS p"
            " ON v.id IN (p.object_value_id, p.base_object_value_id)"
            " WHERE v.object_kind = 'link'"
            " UNION SELECT a.anchor_uuid FROM object_anchor AS a JOIN proposal_entry AS p"
            " ON a.object_value_id IN (p.object_value_id, p.base_object_value_id)"
        )
        # Expand seeds to the relationships whose invariants can change, then to those
        # relationships' participants. This is deliberately not arbitrary graph
        # reachability: unrelated links of an unchanged opposite endpoint are outside the
        # affected invariant closure. Current and prospective edges are both required so
        # removals and upserts receive identical treatment.
        self._connection.execute(
            "INSERT OR IGNORE INTO assessment_impacted_relation"
            " SELECT g.uuid FROM assessment_impacted_uuid AS s"
            " CROSS JOIN graph_presence_interval AS g"
            " INDEXED BY graph_presence_current_link_source"
            " ON g.source_uuid = s.uuid AND g.valid_to_revision IS NULL"
            " WHERE g.object_kind = 'link'"
            " AND NOT EXISTS (SELECT 1 FROM proposal_entry AS p WHERE p.uuid = g.uuid)"
            " UNION SELECT g.uuid FROM assessment_impacted_uuid AS s"
            " CROSS JOIN graph_presence_interval AS g"
            " INDEXED BY graph_presence_current_link_target"
            " ON g.target_uuid = s.uuid AND g.valid_to_revision IS NULL"
            " WHERE g.object_kind = 'link'"
            " AND NOT EXISTS (SELECT 1 FROM proposal_entry AS p WHERE p.uuid = g.uuid)"
            " UNION SELECT v.uuid FROM proposal_entry AS p JOIN object_value AS v"
            " ON v.id = p.object_value_id WHERE p.operation = 'upsert'"
            " AND v.object_kind = 'link' AND v.source_uuid IN"
            " (SELECT uuid FROM assessment_impacted_uuid)"
            " UNION SELECT v.uuid FROM proposal_entry AS p JOIN object_value AS v"
            " ON v.id = p.object_value_id WHERE p.operation = 'upsert'"
            " AND v.object_kind = 'link' AND v.target_uuid IN"
            " (SELECT uuid FROM assessment_impacted_uuid)"
            " UNION SELECT v.uuid FROM assessment_impacted_uuid AS s"
            " CROSS JOIN object_anchor AS a INDEXED BY object_anchor_reverse"
            " ON a.anchor_uuid = s.uuid JOIN object_value AS v ON v.id = a.object_value_id"
            " JOIN graph_presence_interval AS g"
            " ON g.object_value_id = v.id AND g.valid_to_revision IS NULL"
            " WHERE v.object_kind = 'associatedData'"
            " AND NOT EXISTS (SELECT 1 FROM proposal_entry AS p WHERE p.uuid = v.uuid)"
            " UNION SELECT v.uuid FROM proposal_entry AS p JOIN object_value AS v"
            " ON v.id = p.object_value_id JOIN object_anchor AS a ON a.object_value_id = v.id"
            " WHERE p.operation = 'upsert' AND v.object_kind = 'associatedData'"
            " AND a.anchor_uuid IN (SELECT uuid FROM assessment_impacted_uuid)"
            " UNION SELECT v.uuid FROM assessment_impacted_uuid AS i"
            " CROSS JOIN graph_presence_interval AS g INDEXED BY graph_presence_current_uuid"
            " ON g.uuid = i.uuid AND g.valid_to_revision IS NULL"
            " JOIN object_value AS v ON v.id = g.object_value_id"
            " WHERE v.object_kind IN ('link', 'associatedData')"
            " UNION SELECT uuid FROM proposal_entry WHERE object_kind IN ('link', 'associatedData')"
        )
        self._connection.execute(
            "INSERT OR IGNORE INTO assessment_impacted_uuid"
            " SELECT uuid FROM assessment_impacted_relation"
            " UNION SELECT g.source_uuid FROM assessment_impacted_relation AS r"
            " CROSS JOIN graph_presence_interval AS g"
            " INDEXED BY graph_presence_current_uuid ON g.uuid = r.uuid"
            " AND g.valid_to_revision IS NULL WHERE g.object_kind = 'link'"
            " UNION SELECT g.target_uuid FROM assessment_impacted_relation AS r"
            " CROSS JOIN graph_presence_interval AS g"
            " INDEXED BY graph_presence_current_uuid ON g.uuid = r.uuid"
            " AND g.valid_to_revision IS NULL WHERE g.object_kind = 'link'"
            " UNION SELECT v.source_uuid FROM proposal_entry AS p JOIN object_value AS v"
            " ON v.id = p.object_value_id WHERE p.operation = 'upsert'"
            " AND v.object_kind = 'link' AND v.uuid IN"
            " (SELECT uuid FROM assessment_impacted_relation)"
            " UNION SELECT v.target_uuid FROM proposal_entry AS p JOIN object_value AS v"
            " ON v.id = p.object_value_id WHERE p.operation = 'upsert'"
            " AND v.object_kind = 'link' AND v.uuid IN"
            " (SELECT uuid FROM assessment_impacted_relation)"
            " UNION SELECT a.anchor_uuid FROM assessment_impacted_relation AS r"
            " CROSS JOIN graph_presence_interval AS g"
            " INDEXED BY graph_presence_current_uuid ON g.uuid = r.uuid"
            " AND g.valid_to_revision IS NULL JOIN object_anchor AS a"
            " ON a.object_value_id = g.object_value_id"
            " UNION SELECT a.anchor_uuid FROM assessment_impacted_relation AS r"
            " CROSS JOIN proposal_entry AS p ON p.uuid = r.uuid"
            " JOIN object_anchor AS a ON a.object_value_id = p.object_value_id"
            " WHERE p.operation = 'upsert'"
        )
        self._connection.execute(
            "INSERT OR IGNORE INTO assessment_impacted_type"
            " SELECT v.type_key FROM graph_presence_interval AS g JOIN object_value AS v"
            " ON v.id = g.object_value_id WHERE g.valid_to_revision IS NULL"
            " AND g.uuid IN (SELECT uuid FROM assessment_impacted_uuid)"
            " UNION SELECT v.type_key FROM proposal_entry AS p JOIN object_value AS v"
            " ON v.id = p.object_value_id WHERE p.operation = 'upsert'"
            " AND p.uuid IN (SELECT uuid FROM assessment_impacted_uuid)"
        )
        self._prepare_effective_assessment_relations_unlocked()

    def _prepare_effective_assessment_relations_unlocked(self) -> None:
        """Materialize only the affected effective objects and their incident relations."""
        self._connection.execute("DROP TABLE IF EXISTS temp.assessment_effective_object")
        self._connection.execute("DROP TABLE IF EXISTS temp.assessment_incident_link")
        self._connection.execute("DROP TABLE IF EXISTS temp.assessment_effective_data_anchor")
        self._connection.execute(
            "CREATE TEMP TABLE assessment_effective_object AS"
            " SELECT g.uuid, v.object_kind, v.type_key, v.source_uuid, v.target_uuid,"
            " v.id AS object_value_id FROM assessment_impacted_uuid AS i"
            " CROSS JOIN graph_presence_interval AS g INDEXED BY graph_presence_current_uuid"
            " ON g.uuid = i.uuid AND g.valid_to_revision IS NULL"
            " JOIN object_value AS v ON v.id = g.object_value_id WHERE 1 = 1"
            " AND NOT EXISTS (SELECT 1 FROM proposal_entry AS p WHERE p.uuid = g.uuid)"
            " UNION ALL SELECT v.uuid, v.object_kind, v.type_key, v.source_uuid,"
            " v.target_uuid, v.id FROM proposal_entry AS p"
            " JOIN object_value AS v ON v.id = p.object_value_id"
            " WHERE p.operation = 'upsert' AND p.uuid IN"
            " (SELECT uuid FROM assessment_impacted_uuid)"
        )
        self._connection.execute(
            "CREATE UNIQUE INDEX assessment_effective_object_uuid"
            " ON assessment_effective_object(uuid)"
        )
        self._connection.execute(
            "CREATE INDEX assessment_effective_object_type"
            " ON assessment_effective_object(object_kind, type_key, uuid)"
        )
        self._connection.execute(
            "CREATE TEMP TABLE assessment_incident_link AS"
            " SELECT v.uuid, v.type_key, v.source_uuid, v.target_uuid"
            " FROM assessment_impacted_relation AS r"
            " CROSS JOIN graph_presence_interval AS g INDEXED BY graph_presence_current_uuid"
            " ON g.uuid = r.uuid AND g.valid_to_revision IS NULL"
            " JOIN object_value AS v ON v.id = g.object_value_id"
            " WHERE v.object_kind = 'link'"
            " AND NOT EXISTS (SELECT 1 FROM proposal_entry AS p WHERE p.uuid = v.uuid)"
            " UNION ALL SELECT v.uuid, v.type_key, v.source_uuid, v.target_uuid"
            " FROM assessment_impacted_relation AS r CROSS JOIN proposal_entry AS p"
            " ON p.uuid = r.uuid JOIN object_value AS v ON v.id = p.object_value_id"
            " WHERE p.operation = 'upsert' AND v.object_kind = 'link'"
        )
        self._connection.execute(
            "CREATE UNIQUE INDEX assessment_incident_link_uuid ON assessment_incident_link(uuid)"
        )
        self._connection.execute(
            "CREATE INDEX assessment_incident_link_source"
            " ON assessment_incident_link(source_uuid, type_key, target_uuid)"
        )
        self._connection.execute(
            "CREATE INDEX assessment_incident_link_target"
            " ON assessment_incident_link(target_uuid, type_key, source_uuid)"
        )
        self._connection.execute(
            "CREATE TEMP TABLE assessment_effective_data_anchor AS"
            " SELECT a.data_uuid, a.anchor_uuid FROM current_data_anchor AS a"
            " WHERE NOT EXISTS (SELECT 1 FROM proposal_entry AS p WHERE p.uuid = a.data_uuid)"
            " AND a.data_uuid IN (SELECT uuid FROM assessment_impacted_relation)"
            " UNION ALL SELECT v.uuid, a.anchor_uuid FROM proposal_entry AS p"
            " JOIN object_value AS v ON v.id = p.object_value_id"
            " JOIN object_anchor AS a ON a.object_value_id = v.id"
            " WHERE p.operation = 'upsert' AND v.object_kind = 'associatedData'"
            " AND v.uuid IN (SELECT uuid FROM assessment_impacted_relation)"
        )
        self._connection.execute(
            "CREATE INDEX assessment_data_anchor_anchor"
            " ON assessment_effective_data_anchor(anchor_uuid, data_uuid)"
        )
        self._connection.execute(
            "CREATE INDEX assessment_data_anchor_data"
            " ON assessment_effective_data_anchor(data_uuid, anchor_uuid)"
        )

    @staticmethod
    def _graph_validation_signature(definitions: GraphDefinitionSet) -> str:
        """Return only definition meaning that can change graph conformance."""
        members: list[object] = []
        members.extend(("anchor", value.type_key) for value in definitions.anchor_types)
        for value in definitions.associated_data_types:
            rules: list[object] = []
            for rule in value.property_constraints:
                rules.append(
                    (
                        rule.property_name,
                        rule.required,
                        rule.json_kind.value,
                        None
                        if rule.value_shape is None
                        else (rule.value_shape.minimum_size, rule.value_shape.maximum_size),
                        None
                        if rule.value_range is None
                        else (
                            rule.value_range.lower_bound,
                            rule.value_range.upper_bound,
                            tuple(sorted(rule.value_range.permitted_values, key=semantic_identity)),
                        ),
                        None if rule.pattern is None else rule.pattern.expression,
                    )
                )
            members.append(
                (
                    "associatedData",
                    value.type_key,
                    tuple(sorted(value.permitted_anchor_type_keys)),
                    tuple(sorted(rules, key=semantic_identity)),
                )
            )
        members.extend(
            (
                "link",
                value.type_key,
                tuple(sorted(value.endpoint_constraint.permitted_source_type_keys)),
                tuple(sorted(value.endpoint_constraint.permitted_target_type_keys)),
            )
            for value in definitions.link_types
        )
        return semantic_identity(tuple(sorted(members, key=semantic_identity)))

    @staticmethod
    def _multiplicity_validation_signature(definitions: GraphDefinitionSet) -> str:
        """Return rule meaning that can change graph conformance, excluding prose."""
        members: list[object] = []
        for rule in definitions.relationship_constraints:
            if isinstance(rule, LinkMultiplicityConstraint):
                members.append(
                    (
                        "link",
                        rule.link_type_key,
                        rule.constrained_end.value,
                        tuple(sorted(rule.constrained_endpoint_type_keys)),
                        tuple(sorted(rule.opposite_endpoint_type_keys)),
                        rule.lower_bound,
                        rule.upper_bound,
                    )
                )
            else:
                members.append(
                    (
                        "directAssociation",
                        rule.constrained_end.value,
                        tuple(sorted(rule.anchor_type_keys)),
                        tuple(sorted(rule.associated_data_type_keys)),
                        rule.lower_bound,
                        rule.upper_bound,
                    )
                )
        return semantic_identity(tuple(sorted(members, key=semantic_identity)))

    def _definitions_for_relation_unlocked(
        self,
        relation: str,
        active_identity: str,
        *,
        type_keys: set[str] | None = None,
        constrained_type_keys: set[str] | None = None,
        relationship_keys: set[str] | None = None,
    ) -> GraphDefinitionSet:
        if relation == "prospective_graph_object":
            return self._effective_proposed_definitions_unlocked(
                active_identity,
                type_keys=type_keys,
                constrained_type_keys=constrained_type_keys,
                relationship_keys=relationship_keys,
            )
        return self._load_definition_set(
            active_identity,
            type_keys=type_keys,
            constrained_type_keys=constrained_type_keys,
            relationship_keys=relationship_keys,
        )

    def _effective_type_keys_unlocked(self, relation: str, active_identity: str) -> Iterator[str]:
        if relation == "current_graph_object":
            rows = self._connection.execute(
                "SELECT type_key FROM definition_type WHERE definition_set_id = ?"
                " ORDER BY type_key",
                (active_identity,),
            )
        else:
            rows = self._connection.execute(
                "SELECT type_key FROM assessment_definition_type ORDER BY type_key"
            )
        for (type_key,) in rows:
            yield str(type_key)

    def _definition_context_unlocked(
        self, relation: str, active_identity: str, root: GraphDefinitionSet
    ) -> GraphDefinitionSet:
        referenced: set[str] = set()
        for value in root.associated_data_types:
            referenced.update(value.permitted_anchor_type_keys)
        for value in root.link_types:
            referenced.update(value.endpoint_constraint.permitted_source_type_keys)
            referenced.update(value.endpoint_constraint.permitted_target_type_keys)
        for rule in root.relationship_constraints:
            if isinstance(rule, LinkMultiplicityConstraint):
                referenced.add(rule.link_type_key)
                referenced.update(rule.constrained_endpoint_type_keys)
                referenced.update(rule.opposite_endpoint_type_keys)
            else:
                referenced.update(rule.anchor_type_keys)
                referenced.update(rule.associated_data_type_keys)
        resolved = self._definitions_for_relation_unlocked(
            relation,
            active_identity,
            type_keys=referenced,
            constrained_type_keys=set(),
        )
        root_keys = {
            *(value.type_key for value in root.anchor_types),
            *(value.type_key for value in root.associated_data_types),
            *(value.type_key for value in root.link_types),
        }
        anchors = [
            AnchorTypeDefinition(value.type_key, "reference")
            for value in resolved.anchor_types
            if value.type_key not in root_keys
        ]
        reference_anchor = "__vellis_validation_reference_anchor__"
        needs_reference_anchor = any(
            value.type_key not in root_keys for value in resolved.associated_data_types
        ) or any(value.type_key not in root_keys for value in resolved.link_types)
        if needs_reference_anchor and all(
            value.type_key != reference_anchor for value in (*root.anchor_types, *anchors)
        ):
            anchors.append(AnchorTypeDefinition(reference_anchor, "reference"))
        data = [
            AssociatedDataTypeDefinition(
                value.type_key,
                permitted_anchor_type_keys=(reference_anchor,),
                description="reference",
            )
            for value in resolved.associated_data_types
            if value.type_key not in root_keys
        ]
        links = [
            LinkTypeDefinition(
                value.type_key,
                EndpointConstraint((reference_anchor,), (reference_anchor,), "reference"),
                "reference",
            )
            for value in resolved.link_types
            if value.type_key not in root_keys
        ]
        return GraphDefinitionSet(
            (*root.anchor_types, *anchors),
            (*root.associated_data_types, *data),
            (*root.link_types, *links),
            root.relationship_constraints,
        )

    def _iter_definition_findings_unlocked(
        self, relation: str, active_identity: str
    ) -> Iterator[ValidationFinding]:
        for type_key in self._effective_type_keys_unlocked(relation, active_identity):
            root = self._definitions_for_relation_unlocked(
                relation,
                active_identity,
                type_keys={type_key},
                constrained_type_keys=set(),
            )
            yield from validate_definition_set(
                self._definition_context_unlocked(relation, active_identity, root),
                require_descriptions=True,
            )
        if relation == "current_graph_object":
            keys = self._connection.execute(
                "SELECT natural_key FROM definition_multiplicity_rule"
                " WHERE definition_set_id = ? ORDER BY natural_key",
                (active_identity,),
            )
        else:
            keys = self._connection.execute(
                "SELECT natural_key FROM assessment_definition_relationship ORDER BY natural_key"
            )
        for (natural_key,) in keys:
            root = self._definitions_for_relation_unlocked(
                relation,
                active_identity,
                type_keys=set(),
                relationship_keys={str(natural_key)},
            )
            yield from validate_definition_set(
                self._definition_context_unlocked(relation, active_identity, root),
                require_descriptions=True,
            )

    def _iter_multiplicity_findings_unlocked(
        self, relation: str, active_identity: str
    ) -> Iterator[ValidationFinding]:
        if relation == "current_graph_object":
            keys = self._connection.execute(
                "SELECT natural_key FROM definition_multiplicity_rule"
                " WHERE definition_set_id = ? ORDER BY natural_key",
                (active_identity,),
            )
        else:
            keys = self._connection.execute(
                "SELECT r.natural_key FROM definition_multiplicity_rule AS r"
                " WHERE r.definition_set_id = ? AND NOT EXISTS"
                " (SELECT 1 FROM proposal_definition_relationship AS p"
                " WHERE p.natural_key = r.natural_key)"
                " AND EXISTS (SELECT 1 FROM definition_multiplicity_participant AS p"
                " WHERE p.definition_set_id = r.definition_set_id"
                " AND p.rule_occurrence = r.occurrence"
                " AND p.type_key IN (SELECT type_key FROM assessment_impacted_type))"
                " UNION ALL SELECT natural_key FROM proposal_definition_relationship"
                " WHERE operation = 'upsert' ORDER BY 1",
                (active_identity,),
            )
        for (natural_key,) in keys:
            definitions = self._definitions_for_relation_unlocked(
                relation,
                active_identity,
                type_keys=set(),
                relationship_keys={str(natural_key)},
            )
            yield from self._multiplicity_findings_unlocked(relation, definitions)

    def _effective_neighborhood_unlocked(self, relation: str, root: GraphObject) -> Graph:
        wanted = {root.uuid}
        if isinstance(root, AssociatedDataObject):
            wanted.update(root.anchor_uuids)
        elif isinstance(root, Link):
            wanted.update((root.source_uuid, root.target_uuid))
        values: list[GraphObject] = [root]
        pending = wanted - {root.uuid}
        if pending:
            placeholders = ", ".join("?" for _ in pending)
            for (value_id,) in self._connection.execute(
                f"SELECT object_value_id FROM {relation} WHERE uuid IN ({placeholders})",
                tuple(pending),
            ):
                values.append(self._load_object_value(int(value_id)))
        anchors = [each for each in values if isinstance(each, Anchor)]
        data = [each for each in values if isinstance(each, AssociatedDataObject)]
        links = [each for each in values if isinstance(each, Link)]
        # Data used as a link endpoint brings its grounding anchors into the local
        # neighborhood so its own reference checks do not create false findings.
        extra_anchor_ids = {
            anchor_uuid
            for each in data
            for anchor_uuid in each.anchor_uuids
            if all(anchor.uuid != anchor_uuid for anchor in anchors)
        }
        if extra_anchor_ids:
            placeholders = ", ".join("?" for _ in extra_anchor_ids)
            for (value_id,) in self._connection.execute(
                f"SELECT object_value_id FROM {relation}"
                f" WHERE object_kind = 'anchor' AND uuid IN ({placeholders})",
                tuple(extra_anchor_ids),
            ):
                value = self._load_object_value(int(value_id))
                assert isinstance(value, Anchor)
                anchors.append(value)
        return Graph(tuple(anchors), tuple(data), tuple(links))

    def _multiplicity_findings_unlocked(
        self, relation: str, definitions: GraphDefinitionSet
    ) -> Iterator[ValidationFinding]:
        prospective = relation == "prospective_graph_object"
        object_relation = "assessment_effective_object" if prospective else relation
        link_relation = "assessment_incident_link" if prospective else relation
        association_relation = (
            "assessment_effective_data_anchor" if prospective else "current_data_anchor"
        )
        for constraint in definitions.relationship_constraints:
            label = relationship_label(constraint)
            lower, upper = constraint.lower_bound, constraint.upper_bound
            if isinstance(constraint, LinkMultiplicityConstraint):
                near = (
                    "source_uuid" if constraint.constrained_end is LinkEnd.SOURCE else "target_uuid"
                )
                far = (
                    "target_uuid" if constraint.constrained_end is LinkEnd.SOURCE else "source_uuid"
                )
                constrained = tuple(constraint.constrained_endpoint_type_keys)
                opposite = tuple(constraint.opposite_endpoint_type_keys)
                if not constrained or not opposite:
                    continue
                constrained_marks = ", ".join("?" for _ in constrained)
                opposite_marks = ", ".join("?" for _ in opposite)
                sql = (
                    f"SELECT e.uuid, e.type_key, count(f.uuid) FROM {object_relation} AS e"
                    f" LEFT JOIN {link_relation} AS l ON "
                    + ("1 = 1" if prospective else "l.object_kind = 'link'")
                    + f" AND l.type_key = ? AND l.{near} = e.uuid"
                    + f" LEFT JOIN {object_relation} AS f ON f.uuid = l.{far}"
                    + f" AND f.type_key IN ({opposite_marks})"
                    + " WHERE e.object_kind IN ('anchor', 'associatedData')"
                    + f" AND e.type_key IN ({constrained_marks})"
                    + (
                        " AND e.uuid IN (SELECT uuid FROM assessment_impacted_uuid)"
                        if prospective
                        else ""
                    )
                    + " GROUP BY e.uuid, e.type_key ORDER BY e.uuid"
                )
                parameters = (constraint.link_type_key, *opposite, *constrained)
                rows = self._connection.execute(sql, parameters)
                for uuid, type_key, count_value in rows:
                    count = int(count_value)
                    if count < lower or (upper is not None and count > upper):
                        bound = f"{lower}..{'*' if upper is None else upper}"
                        yield ValidationFinding(
                            summary=(
                                f"{type_key} {uuid!r} participates in {count}"
                                f" {constraint.link_type_key!r} links at its"
                                f" {constraint.constrained_end.value} end, outside {bound}"
                            ),
                            implicated_definitions=(label,),
                            implicated_objects=(str(uuid),),
                        )
                continue
            assert isinstance(constraint, DirectAssociationMultiplicityConstraint)
            anchors = tuple(constraint.anchor_type_keys)
            data_types = tuple(constraint.associated_data_type_keys)
            if not anchors or not data_types:
                continue
            anchor_marks = ", ".join("?" for _ in anchors)
            data_marks = ", ".join("?" for _ in data_types)
            if constraint.constrained_end is DirectAssociationEnd.ANCHOR:
                sql = (
                    f"SELECT a.uuid, count(d.uuid) FROM {object_relation} AS a"
                    f" LEFT JOIN {association_relation} AS da ON da.anchor_uuid = a.uuid"
                    f" LEFT JOIN {object_relation} AS d ON d.uuid = da.data_uuid"
                    f" AND d.type_key IN ({data_marks})"
                    " WHERE a.object_kind = 'anchor'"
                    f" AND a.type_key IN ({anchor_marks}) GROUP BY a.uuid ORDER BY a.uuid"
                )
                if prospective:
                    sql = sql.replace(
                        " GROUP BY",
                        " AND a.uuid IN (SELECT uuid FROM assessment_impacted_uuid) GROUP BY",
                    )
                rows = self._connection.execute(sql, (*data_types, *anchors))
            else:
                sql = (
                    f"SELECT d.uuid, count(DISTINCT a.uuid) FROM {object_relation} AS d"
                    f" LEFT JOIN {association_relation} AS da ON da.data_uuid = d.uuid"
                    f" LEFT JOIN {object_relation} AS a ON a.uuid = da.anchor_uuid"
                    f" AND a.type_key IN ({anchor_marks})"
                    " WHERE d.object_kind = 'associatedData'"
                    f" AND d.type_key IN ({data_marks}) GROUP BY d.uuid ORDER BY d.uuid"
                )
                if prospective:
                    sql = sql.replace(
                        " GROUP BY",
                        " AND d.uuid IN (SELECT uuid FROM assessment_impacted_uuid) GROUP BY",
                    )
                rows = self._connection.execute(sql, (*anchors, *data_types))
            for uuid, count_value in rows:
                count = int(count_value)
                if count < lower or (upper is not None and count > upper):
                    bound = f"{lower}..{'*' if upper is None else upper}"
                    subject = (
                        "anchor"
                        if constraint.constrained_end is DirectAssociationEnd.ANCHOR
                        else "associated data"
                    )
                    yield ValidationFinding(
                        summary=(
                            f"{subject} {uuid!r} has {count} matching direct associations, "
                            f"outside {bound}"
                        ),
                        implicated_definitions=(label,),
                        implicated_objects=(str(uuid),),
                    )

    def _delete_assessment_unlocked(self, assessment_id: str) -> None:
        self._connection.execute(
            "DELETE FROM validation_finding_definition WHERE assessment_id = ?",
            (assessment_id,),
        )
        self._connection.execute(
            "DELETE FROM validation_finding_object WHERE assessment_id = ?",
            (assessment_id,),
        )
        self._connection.execute(
            "DELETE FROM validation_finding WHERE assessment_id = ?", (assessment_id,)
        )
        self._connection.execute(
            "DELETE FROM validation_assessment WHERE identity = ?", (assessment_id,)
        )

    def _materialize_proposed_definitions_unlocked(
        self, active_identity: str, proposed_identity: str
    ) -> str:
        """Build the activated immutable set with fixed-size SQL row work."""
        if self._connection.execute(
            "SELECT 1 FROM definition_set WHERE identity = ?", (proposed_identity,)
        ).fetchone():
            return proposed_identity
        content = self._connection.execute(
            "SELECT effective_accumulator, effective_entry_count"
            " FROM proposal_definition_state WHERE id = 0"
        ).fetchone()
        if content is None or content[0] is None or content[1] is None:
            raise StoreError("the proposed definition content summary is absent")
        canonical_identity = definition_identity_from_stats(str(content[0]), int(content[1]))
        if canonical_identity != proposed_identity:
            raise StoreError("the proposed definition identity does not match its content")
        self._connection.execute(
            "INSERT INTO definition_set(identity, content_accumulator, entry_count)"
            " VALUES (?, ?, ?)",
            (proposed_identity, str(content[0]), int(content[1])),
        )
        sources = self._connection.execute(
            "SELECT t.definition_set_id, t.occurrence, t.type_key, t.object_kind"
            " FROM definition_type AS t WHERE t.definition_set_id = ?"
            " AND NOT EXISTS (SELECT 1 FROM proposal_definition_type AS p"
            " WHERE p.type_key = t.type_key)"
            " UNION ALL SELECT t.definition_set_id, t.occurrence, t.type_key, t.object_kind"
            " FROM proposal_definition_type AS p JOIN definition_type AS t"
            " ON t.definition_set_id = p.value_set_id WHERE p.operation = 'upsert'"
            " ORDER BY 3, 4",
            (active_identity,),
        )
        type_occurrence = 0
        while batch := sources.fetchmany(128):
            for source_set, source_occurrence, _, _ in batch:
                self._connection.execute(
                    "INSERT INTO definition_type SELECT ?, ?, object_kind, type_key, description"
                    " FROM definition_type WHERE definition_set_id = ? AND occurrence = ?",
                    (proposed_identity, type_occurrence, source_set, source_occurrence),
                )
                for table, columns in (
                    (
                        "definition_anchor_permission",
                        "occurrence, anchor_type_key",
                    ),
                    (
                        "definition_property_rule",
                        "occurrence, property_name, required, json_kind, description,"
                        " minimum_size, maximum_size, lower_kind, lower_value, upper_kind,"
                        " upper_value, pattern",
                    ),
                    (
                        "definition_endpoint_rule",
                        "description",
                    ),
                    (
                        "definition_endpoint_permission",
                        "role, occurrence, type_key",
                    ),
                ):
                    self._connection.execute(
                        f"INSERT INTO {table} SELECT ?, ?, {columns} FROM {table}"
                        " WHERE definition_set_id = ? AND type_occurrence = ?",
                        (proposed_identity, type_occurrence, source_set, source_occurrence),
                    )
                self._connection.execute(
                    "INSERT INTO definition_permitted_value"
                    " SELECT ?, ?, v.property_occurrence, v.occurrence, v.json_kind, v.json_value"
                    " FROM definition_permitted_value AS v WHERE v.definition_set_id = ?"
                    " AND v.type_occurrence = ?",
                    (proposed_identity, type_occurrence, source_set, source_occurrence),
                )
                type_occurrence += 1

        rule_sources = self._connection.execute(
            "SELECT r.definition_set_id, r.occurrence, r.natural_key"
            " FROM definition_multiplicity_rule AS r WHERE r.definition_set_id = ?"
            " AND NOT EXISTS (SELECT 1 FROM proposal_definition_relationship AS p"
            " WHERE p.natural_key = r.natural_key)"
            " UNION ALL SELECT r.definition_set_id, r.occurrence, r.natural_key"
            " FROM proposal_definition_relationship AS p"
            " JOIN definition_multiplicity_rule AS r"
            " ON r.definition_set_id = p.value_set_id WHERE p.operation = 'upsert'"
            " ORDER BY 3",
            (active_identity,),
        )
        rule_occurrence = 0
        while batch := rule_sources.fetchmany(128):
            for source_set, source_occurrence, _ in batch:
                self._connection.execute(
                    "INSERT INTO definition_multiplicity_rule"
                    " SELECT ?, ?, natural_key, rule_kind, link_type_key, constrained_end,"
                    " lower_bound, upper_bound, description"
                    " FROM definition_multiplicity_rule"
                    " WHERE definition_set_id = ? AND occurrence = ?",
                    (proposed_identity, rule_occurrence, source_set, source_occurrence),
                )
                self._connection.execute(
                    "INSERT INTO definition_multiplicity_participant"
                    " SELECT ?, ?, role, occurrence, type_key"
                    " FROM definition_multiplicity_participant"
                    " WHERE definition_set_id = ? AND rule_occurrence = ?",
                    (proposed_identity, rule_occurrence, source_set, source_occurrence),
                )
                rule_occurrence += 1
        return proposed_identity

    def activate_proposal(self, assessment_id: str, *, provenance: Provenance) -> RevisionedOutcome:
        """Atomically activate the exact assessed definition-and-graph proposal."""
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                head = self._connection.execute(
                    "SELECT revision, proposed_definition_set_id, active_definition_set_id"
                    " FROM state_head WHERE id = 0"
                ).fetchone()
                if head is None:
                    raise NotInitializedError("no canonical state is established")
                revision = int(head[0])
                if head[1] is None:
                    self._connection.execute("ROLLBACK")
                    return RevisionedOutcome(
                        OperationStatus.REJECTED, "there is no proposal to activate"
                    )
                proposed = str(head[1])
                overlay = self._overlay_identity_unlocked()
                assessed = self._connection.execute(
                    "SELECT evaluated_revision, proposed_definition_set_id,"
                    " graph_overlay_identity, conforms FROM validation_assessment"
                    " WHERE identity = ?",
                    (assessment_id,),
                ).fetchone()
                if assessed is None or (
                    int(assessed[0]) != revision
                    or str(assessed[1]) != proposed
                    or str(assessed[2]) != overlay
                    or not bool(assessed[3])
                ):
                    self._connection.execute("ROLLBACK")
                    return RevisionedOutcome(
                        OperationStatus.REJECTED,
                        "activation requires the exact current conforming proposal assessment",
                        (
                            ValidationFinding(
                                summary=(
                                    "the selected assessment is missing, stale, or nonconforming"
                                )
                            ),
                        ),
                    )
                conflict = self._connection.execute(
                    "SELECT p.uuid FROM proposal_entry AS p"
                    " LEFT JOIN current_graph_object AS c ON c.uuid = p.uuid"
                    " WHERE (p.base_object_value_id IS NULL AND c.object_value_id IS NOT NULL)"
                    " OR (p.base_object_value_id IS NOT NULL"
                    " AND (c.object_value_id IS NULL"
                    " OR c.object_value_id != p.base_object_value_id))"
                    " LIMIT 1"
                ).fetchone()
                if conflict is not None:
                    self._connection.execute("ROLLBACK")
                    return RevisionedOutcome(
                        OperationStatus.REJECTED,
                        "the active base of staged work changed; reassess after restaging",
                        (
                            ValidationFinding(
                                summary="staged work has a stale active base",
                                implicated_objects=(str(conflict[0]),),
                            ),
                        ),
                    )
                self._materialize_proposed_definitions_unlocked(str(head[2]), proposed)
                resulting = revision + 1
                previous = self._connection.execute(
                    "SELECT r.record_identity FROM canonical_record AS r"
                    " JOIN state_head AS h ON h.established_by = r.established_revision"
                    " WHERE h.id = 0"
                ).fetchone()
                ledger = self._connection.execute(
                    "SELECT identity FROM ledger WHERE id = 0"
                ).fetchone()
                assert previous is not None and ledger is not None
                recorded_at = now()
                record_identity = self._record_identity(
                    str(ledger[0]),
                    str(previous[0]),
                    resulting,
                    TransitionKind.DEFINITION_ACTIVATION.value,
                    recorded_at,
                    provenance.initiator,
                    provenance.source,
                    str(revision),
                    semantic_identity((proposed, overlay, assessment_id)),
                )
                self._connection.execute(
                    "INSERT INTO canonical_record (established_revision, ordinal, record_kind,"
                    " recorded_at, initiator, source, summary, prior_revision, record_identity,"
                    " prior_record_identity) VALUES (?, ("
                    + NEXT_ORDINAL_SQL
                    + "), ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        resulting,
                        TransitionKind.DEFINITION_ACTIVATION.value,
                        _stored_time(recorded_at),
                        provenance.initiator,
                        provenance.source,
                        str(revision),
                        revision,
                        record_identity,
                        str(previous[0]),
                    ),
                )
                entries = self._connection.execute(
                    "SELECT uuid, object_kind, operation, object_value_id"
                    " FROM proposal_entry ORDER BY uuid"
                )
                for occurrence, (uuid, kind, operation, value_id) in enumerate(entries):
                    self._connection.execute(
                        "UPDATE graph_presence_interval SET valid_to_revision = ?"
                        " WHERE uuid = ? AND valid_to_revision IS NULL",
                        (resulting, uuid),
                    )
                    if operation == "upsert":
                        self._connection.execute(
                            "INSERT INTO graph_presence_interval"
                            " SELECT ?, id, object_kind, type_key, source_uuid, target_uuid,"
                            " ?, NULL FROM object_value WHERE id = ?",
                            (uuid, resulting, value_id),
                        )
                    self._connection.execute(
                        "INSERT INTO canonical_graph_event VALUES (?, ?, ?, ?, ?, ?)",
                        (resulting, occurrence, operation, kind, uuid, value_id),
                    )
                self._connection.execute(
                    "UPDATE state_head SET revision = ?, established_by = ?,"
                    " active_definition_set_id = ?, proposed_definition_set_id = NULL WHERE id = 0",
                    (resulting, resulting, proposed),
                )
                self._connection.execute(
                    "INSERT INTO canonical_definition_event VALUES (?, ?, 'absent', NULL)",
                    (resulting, proposed),
                )
                self._connection.execute("DELETE FROM proposal_entry")
                self._connection.execute(
                    "UPDATE proposal_overlay_state SET accumulator = ?, entry_count = 0"
                    " WHERE id = 0",
                    ("0" * 64,),
                )
                self._connection.execute("DELETE FROM proposal_definition_type")
                self._connection.execute("DELETE FROM proposal_definition_relationship")
                self._connection.execute(
                    "UPDATE proposal_definition_state SET base_definition_set_id = NULL,"
                    " accumulator = ?, entry_count = 0, effective_accumulator = NULL,"
                    " effective_entry_count = NULL, identity = NULL WHERE id = 0",
                    ("0" * 64,),
                )
                self._connection.execute("COMMIT")
                return RevisionedOutcome(
                    OperationStatus.ACCEPTED,
                    f"activated the assessed proposal at revision {resulting}",
                    resulting_revision=resulting,
                )
            except StoreError:
                self._rollback_quietly()
                raise
            except Exception as error:
                self._rollback_quietly()
                raise StoreError(f"could not activate the proposal: {error}") from error

    def restore_revision(
        self, selected_revision: int, *, provenance: Provenance
    ) -> RevisionedOutcome:
        """Restore historical graph/definitions through SQL set differences."""
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                head = self._connection.execute(
                    "SELECT revision, active_definition_set_id, proposed_definition_set_id"
                    " FROM state_head WHERE id = 0"
                ).fetchone()
                if head is None:
                    raise NotInitializedError("no canonical state is established")
                if head[2] is not None:
                    self._connection.execute("ROLLBACK")
                    return RevisionedOutcome(
                        OperationStatus.REJECTED,
                        "a proposal is in flight; activate or discard it before restoring",
                    )
                target_definition = self._connection.execute(
                    "SELECT active_definition_set_id FROM canonical_definition_event"
                    " WHERE established_revision <= ? AND active_definition_set_id IS NOT NULL"
                    " ORDER BY established_revision DESC LIMIT 1",
                    (selected_revision,),
                ).fetchone()
                if target_definition is None:
                    self._connection.execute("ROLLBACK")
                    return RevisionedOutcome(
                        OperationStatus.REJECTED,
                        f"revision {selected_revision} is not established by this ledger",
                    )
                self._connection.execute("DROP TABLE IF EXISTS temp.restore_target")
                self._connection.execute(
                    "CREATE TEMP TABLE restore_target AS"
                    " SELECT p.uuid, v.object_kind, p.object_value_id"
                    " FROM graph_presence_interval AS p JOIN object_value AS v"
                    " ON v.id = p.object_value_id WHERE p.valid_from_revision <= ?"
                    " AND (p.valid_to_revision IS NULL OR p.valid_to_revision > ?)",
                    (selected_revision, selected_revision),
                )
                difference = self._connection.execute(
                    "SELECT uuid, object_value_id FROM restore_target"
                    " EXCEPT SELECT uuid, object_value_id FROM current_graph_object"
                    " UNION ALL SELECT uuid, object_value_id FROM current_graph_object"
                    " EXCEPT SELECT uuid, object_value_id FROM restore_target LIMIT 1"
                ).fetchone()
                if difference is None and str(head[1]) == str(target_definition[0]):
                    self._connection.execute("ROLLBACK")
                    return RevisionedOutcome(
                        OperationStatus.ACCEPTED,
                        f"revision {selected_revision} is already current; nothing was restored",
                    )
                revision, resulting = int(head[0]), int(head[0]) + 1
                previous = self._connection.execute(
                    "SELECT r.record_identity FROM canonical_record AS r"
                    " JOIN state_head AS h ON h.established_by = r.established_revision"
                    " WHERE h.id = 0"
                ).fetchone()
                ledger = self._connection.execute(
                    "SELECT identity FROM ledger WHERE id = 0"
                ).fetchone()
                assert previous is not None and ledger is not None
                recorded_at = now()
                record_identity = self._record_identity(
                    str(ledger[0]),
                    str(previous[0]),
                    resulting,
                    TransitionKind.HISTORICAL_RESTORATION.value,
                    recorded_at,
                    provenance.initiator,
                    provenance.source,
                    str(revision),
                    semantic_identity(("restore", selected_revision, str(target_definition[0]))),
                )
                self._connection.execute(
                    "INSERT INTO canonical_record (established_revision, ordinal, record_kind,"
                    " recorded_at, initiator, source, summary, prior_revision, record_identity,"
                    " prior_record_identity) VALUES (?, ("
                    + NEXT_ORDINAL_SQL
                    + "), ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        resulting,
                        TransitionKind.HISTORICAL_RESTORATION.value,
                        _stored_time(recorded_at),
                        provenance.initiator,
                        provenance.source,
                        str(revision),
                        revision,
                        record_identity,
                        str(previous[0]),
                    ),
                )
                events = self._connection.execute(
                    "SELECT c.uuid, c.object_kind, 'delete', NULL"
                    " FROM current_graph_object AS c LEFT JOIN restore_target AS t"
                    " ON t.uuid = c.uuid WHERE t.uuid IS NULL"
                    " UNION ALL SELECT t.uuid, t.object_kind, 'upsert', t.object_value_id"
                    " FROM restore_target AS t LEFT JOIN current_graph_object AS c"
                    " ON c.uuid = t.uuid WHERE c.object_value_id IS NULL"
                    " OR c.object_value_id != t.object_value_id ORDER BY 1"
                )
                for occurrence, (uuid, kind, operation, value_id) in enumerate(events):
                    self._connection.execute(
                        "UPDATE graph_presence_interval SET valid_to_revision = ?"
                        " WHERE uuid = ? AND valid_to_revision IS NULL",
                        (resulting, uuid),
                    )
                    if operation == "upsert":
                        self._connection.execute(
                            "INSERT INTO graph_presence_interval"
                            " SELECT ?, id, object_kind, type_key, source_uuid, target_uuid,"
                            " ?, NULL FROM object_value WHERE id = ?",
                            (uuid, resulting, value_id),
                        )
                    self._connection.execute(
                        "INSERT INTO canonical_graph_event VALUES (?, ?, ?, ?, ?, ?)",
                        (resulting, occurrence, operation, kind, uuid, value_id),
                    )
                self._connection.execute(
                    "UPDATE state_head SET revision = ?, established_by = ?,"
                    " active_definition_set_id = ? WHERE id = 0",
                    (resulting, resulting, target_definition[0]),
                )
                self._connection.execute(
                    "INSERT INTO canonical_definition_event VALUES (?, ?, 'absent', NULL)",
                    (resulting, target_definition[0]),
                )
                self._connection.execute("COMMIT")
                return RevisionedOutcome(
                    OperationStatus.ACCEPTED,
                    f"restored revision {selected_revision} as revision {resulting}",
                    resulting_revision=resulting,
                )
            except StoreError:
                self._rollback_quietly()
                raise
            except Exception as error:
                self._rollback_quietly()
                raise StoreError(
                    f"could not restore revision {selected_revision}: {error}"
                ) from error

    def definitions_at_revision(self, revision: int) -> tuple[GraphDefinitionSet, bool]:
        """Read definition meaning in force at a revision without graph or record replay."""
        active_row = self._fetchone(
            "SELECT active_definition_set_id FROM canonical_definition_event"
            " WHERE established_revision <= ? AND active_definition_set_id IS NOT NULL"
            " ORDER BY established_revision DESC LIMIT 1",
            (revision,),
        )
        delta_row = self._fetchone(
            "SELECT delta_disposition FROM canonical_definition_event"
            " WHERE established_revision <= ? AND delta_disposition != 'unchanged'"
            " ORDER BY established_revision DESC LIMIT 1",
            (revision,),
        )
        if not isinstance(active_row, tuple) or active_row[0] is None:
            raise StoreError(f"revision {revision} has no active definition meaning")
        return (
            self._load_definition_set(str(active_row[0])),
            isinstance(delta_row, tuple) and delta_row[0] == "present",
        )

    def current_revision(self) -> int:
        """Read the established current revision without materializing any state facet."""
        row = self._fetchone("SELECT revision, established_by FROM state_head WHERE id = 0")
        if not isinstance(row, tuple):
            raise NotInitializedError("no canonical state is established")
        revision = _projection_revision(row)
        return revision

    def prepare_active_graph_change(
        self, change: GraphChange
    ) -> tuple[
        int,
        tuple[ValidationFinding, ...],
        tuple[ValidationFinding, ...],
        bool,
    ]:
        """Validate one active change from its affected SQLite neighborhood.

        The established graph is already conforming, so ordinary mutation re-evaluates
        only touched identities, their references, and multiplicity participants whose
        relationship counts can change. The selected closure may grow with local degree;
        unrelated graph population is never selected or decoded.
        """
        try:
            with self._lock:
                self._connection.execute("BEGIN")
                try:
                    head = self._connection.execute(
                        "SELECT revision, established_by, active_definition_set_id"
                        " FROM state_head WHERE id = 0"
                    ).fetchone()
                    if not isinstance(head, tuple):
                        raise NotInitializedError("no canonical state is established")
                    revision = _projection_revision(head)
                    touched = {
                        *(value.uuid for _, value in change.upserts()),
                        *(uuid for _, uuid in change.removals()),
                    }
                    removed = {uuid for _, uuid in change.removals()}
                    structural_ids = set(touched)
                    structural_ids.update(self._referencing_uuids_unlocked(removed))
                    structural_graph = self._graph_for_uuids_unlocked(structural_ids)
                    structural = change_findings(change, structural_graph)
                    if structural:
                        self._connection.execute("COMMIT")
                        return revision, structural, (), False

                    existing_touched = {
                        value.uuid: value
                        for value in structural_graph.objects()
                        if value.uuid in touched
                    }
                    affected = self._affected_participants_unlocked(change, existing_touched)
                    closure_ids = set(touched) | affected
                    closure_ids.update(self._incident_relationship_uuids_unlocked(affected))
                    already_loaded = {value.uuid for value in structural_graph.objects()}
                    current_neighborhood = _merge_graphs(
                        structural_graph,
                        self._graph_for_uuids_unlocked(closure_ids - already_loaded),
                    )

                    referenced: set[str] = set()
                    values = (*current_neighborhood.objects(), *(v for _, v in change.upserts()))
                    for value in values:
                        if isinstance(value, AssociatedDataObject):
                            referenced.update(value.anchor_uuids)
                        elif isinstance(value, Link):
                            referenced.update((value.source_uuid, value.target_uuid))
                    known = {value.uuid for value in current_neighborhood.objects()}
                    missing_references = referenced - known
                    if missing_references:
                        current_neighborhood = _merge_graphs(
                            current_neighborhood,
                            self._graph_for_uuids_unlocked(missing_references),
                        )

                    resulting = apply_change(current_neighborhood, change)
                    relevant = closure_ids
                    type_keys = {value.type_key for value in resulting.objects()}
                    constrained_type_keys = {
                        value.type_key
                        for value in resulting.objects()
                        if value.uuid in relevant and not isinstance(value, Link)
                    }
                    definitions = self._load_definition_set(
                        str(head[2]),
                        type_keys=type_keys,
                        constrained_type_keys=constrained_type_keys,
                    )
                    conformance = tuple(
                        finding
                        for finding in assess_graph_conformance(resulting, definitions)
                        if set(finding.implicated_objects) & relevant
                    )
                    no_op = graph_equal(resulting, current_neighborhood)
                    self._connection.execute("COMMIT")
                    return revision, (), conformance, no_op
                except BaseException:
                    self._rollback_quietly()
                    raise
        except sqlite3.Error as error:
            raise StoreError(
                f"could not validate a graph change at {self._path}: {error}"
            ) from error

    def _graph_for_uuids_unlocked(self, uuids: set[str]) -> Graph:
        objects: list[GraphObject] = []
        for chunk in _chunks(uuids):
            placeholders = ", ".join("?" for _ in chunk)
            rows = self._connection.execute(
                "SELECT uuid, object_kind, type_key, source_uuid, target_uuid,"
                " object_value_id FROM current_graph_object"
                f" WHERE uuid IN ({placeholders})",
                tuple(chunk),
            )
            objects.extend(self._decode_current_graph_object(*row) for row in rows)
        return _graph_from_objects(objects)

    def _referencing_uuids_unlocked(self, uuids: set[str]) -> set[str]:
        references: set[str] = set()
        for chunk in _chunks(uuids):
            placeholders = ", ".join("?" for _ in chunk)
            references.update(
                str(row[0])
                for row in self._connection.execute(
                    "SELECT DISTINCT data_uuid FROM current_data_anchor"
                    f" WHERE anchor_uuid IN ({placeholders})",
                    tuple(chunk),
                )
            )
            references.update(
                str(row[0])
                for row in self._connection.execute(
                    "SELECT uuid FROM current_graph_object WHERE object_kind = 'link'"
                    f" AND (source_uuid IN ({placeholders})"
                    f" OR target_uuid IN ({placeholders}))",
                    (*chunk, *chunk),
                )
            )
        return references

    def _incident_relationship_uuids_unlocked(self, participants: set[str]) -> set[str]:
        relationships = self._referencing_uuids_unlocked(participants)
        for chunk in _chunks(participants):
            placeholders = ", ".join("?" for _ in chunk)
            relationships.update(
                str(row[0])
                for row in self._connection.execute(
                    "SELECT uuid FROM current_graph_object"
                    " WHERE object_kind = 'associatedData'"
                    f" AND uuid IN ({placeholders})",
                    tuple(chunk),
                )
            )
        return relationships

    def _affected_participants_unlocked(
        self, change: GraphChange, existing: dict[str, GraphObject]
    ) -> set[str]:
        """Return identities whose relationship counts may differ after ``change``."""
        affected: set[str] = set()
        changed_endpoint_types: set[str] = set()
        for _, new in change.upserts():
            old = existing.get(new.uuid)
            if isinstance(old, AssociatedDataObject):
                affected.update((old.uuid, *old.anchor_uuids))
            elif isinstance(old, Link):
                affected.update((old.source_uuid, old.target_uuid))
            if isinstance(new, AssociatedDataObject):
                affected.update((new.uuid, *new.anchor_uuids))
            elif isinstance(new, Link):
                affected.update((new.source_uuid, new.target_uuid))
            else:
                affected.add(new.uuid)
            if old is not None and old.type_key != new.type_key and not isinstance(new, Link):
                changed_endpoint_types.add(new.uuid)
        for _, uuid in change.removals():
            old = existing.get(uuid)
            if isinstance(old, AssociatedDataObject):
                affected.update((old.uuid, *old.anchor_uuids))
                changed_endpoint_types.add(old.uuid)
            elif isinstance(old, Link):
                affected.update((old.source_uuid, old.target_uuid))
            elif isinstance(old, Anchor):
                affected.add(old.uuid)
                changed_endpoint_types.add(old.uuid)

        incident = self._incident_relationship_uuids_unlocked(changed_endpoint_types)
        incident_graph = self._graph_for_uuids_unlocked(incident)
        for relationship in incident_graph.objects():
            if isinstance(relationship, Link):
                affected.update((relationship.source_uuid, relationship.target_uuid))
            elif isinstance(relationship, AssociatedDataObject):
                affected.update((relationship.uuid, *relationship.anchor_uuids))
        return affected

    # --- Owned history base ---------------------------------------------------------

    def initialize(self, record: InitialStateRecord) -> None:
        """Establish the owned history base and its projection as one atomic effect.

        Nothing is established when the store already holds canonical state, and a
        failure part-way through leaves no partial canonical or activity state.
        """
        state = record.canonical_state
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                if self._connection.execute(INITIALIZED_SQL).fetchone():
                    self._connection.execute("ROLLBACK")
                    raise AlreadyInitializedError(
                        f"canonical state is already established at {self._path}"
                    )
                ledger_identity = secrets.token_hex(16)
                self._connection.execute(
                    "INSERT INTO ledger (id, identity) VALUES (0, ?)", (ledger_identity,)
                )
                self._connection.execute(
                    "INSERT INTO proposal_overlay_state VALUES (0, ?, 0)", ("0" * 64,)
                )
                self._connection.executemany(
                    "INSERT INTO proposal_overlay_count VALUES (?, ?, 0)",
                    tuple(
                        (kind.value, operation)
                        for kind in ObjectKind
                        for operation in ("upsert", "delete")
                    ),
                )
                self._connection.execute(
                    "INSERT INTO proposal_definition_state"
                    " (id, base_definition_set_id, accumulator, entry_count,"
                    " effective_accumulator, effective_entry_count, identity)"
                    " VALUES (0, NULL, ?, 0, NULL, NULL, NULL)",
                    ("0" * 64,),
                )
                active_identity = insert_definition_set(self._connection, state.active_definitions)
                proposed_identity = (
                    None
                    if state.definition_delta is None
                    else insert_definition_set(
                        self._connection, state.definition_delta.proposed_definitions
                    )
                )
                record_identity = self._record_identity(
                    ledger_identity,
                    None,
                    record.established_revision,
                    "initial",
                    record.recorded_at,
                    record.provenance.initiator,
                    record.provenance.source,
                    record.initialization_summary,
                    semantic_identity(
                        (_graph_identity(state.graph), active_identity, proposed_identity)
                    ),
                )
                self._connection.execute(
                    "INSERT INTO canonical_record (established_revision, ordinal, record_kind,"
                    " recorded_at, initiator, source, summary, prior_revision, record_identity,"
                    " prior_record_identity) VALUES (?, 0, 'initial', ?, ?, ?, ?, NULL, ?, NULL)",
                    (
                        record.established_revision,
                        _stored_time(record.recorded_at),
                        record.provenance.initiator,
                        record.provenance.source,
                        record.initialization_summary,
                        record_identity,
                    ),
                )
                self._connection.execute(
                    "INSERT INTO state_head"
                    " (id, revision, established_by, active_definition_set_id,"
                    " proposed_definition_set_id)"
                    " VALUES (0, ?, ?, ?, ?)",
                    (
                        state.revision,
                        record.established_revision,
                        active_identity,
                        proposed_identity,
                    ),
                )
                self._replace_current_graph_unlocked(state.graph, state.revision)
                self._connection.execute(
                    "INSERT INTO canonical_definition_event"
                    " (established_revision, active_definition_set_id, delta_disposition,"
                    " proposed_definition_set_id)"
                    " VALUES (?, ?, ?, ?)",
                    (
                        state.revision,
                        active_identity,
                        "absent" if proposed_identity is None else "present",
                        proposed_identity,
                    ),
                )
                # A read attempted before the system existed may already have observed itself
                # here, and success promises an empty ledger.
                self._connection.execute("DELETE FROM activity_record")
                self._connection.execute("COMMIT")
            except AlreadyInitializedError:
                raise
            except Exception as error:
                # Any failure between BEGIN and COMMIT must roll back. Letting one escape
                # would leave the transaction open and poison every later use of this store.
                self._rollback_quietly()
                raise StoreError(f"could not establish canonical state: {error}") from error

    def _rollback_quietly(self) -> None:
        try:
            self._connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass

    @staticmethod
    def _record_identity(
        ledger_identity: str,
        prior_identity: str | None,
        revision: int,
        kind: str,
        recorded_at: datetime,
        initiator: str,
        source: str | None,
        summary: str,
        content_identity: str,
    ) -> str:
        return semantic_identity(
            (
                ledger_identity,
                prior_identity,
                revision,
                kind,
                _stored_time(recorded_at),
                initiator,
                source,
                summary,
                content_identity,
            )
        )

    def _replace_current_graph_unlocked(self, graph: Graph, revision: int) -> None:
        self._connection.execute(
            "UPDATE graph_presence_interval SET valid_to_revision = ?"
            " WHERE valid_to_revision IS NULL",
            (revision,),
        )
        for graph_object in graph.objects():
            self._upsert_current_graph_object_unlocked(graph_object, revision)

    def _apply_current_graph_change_unlocked(self, change: GraphChange, revision: int) -> None:
        removals = tuple(uuid for _, uuid in change.removals())
        replaced = (*removals, *(value.uuid for _, value in change.upserts()))
        if replaced:
            placeholders = ", ".join("?" for _ in replaced)
            self._connection.execute(
                f"UPDATE graph_presence_interval SET valid_to_revision = ?"
                f" WHERE valid_to_revision IS NULL AND uuid IN ({placeholders})",
                (revision, *replaced),
            )
        for _, graph_object in change.upserts():
            self._upsert_current_graph_object_unlocked(graph_object, revision)

    def _upsert_current_graph_object_unlocked(
        self, graph_object: GraphObject, revision: int
    ) -> int:
        value_id = insert_object_value(self._connection, graph_object)
        kind = (
            ObjectKind.ANCHOR
            if isinstance(graph_object, Anchor)
            else ObjectKind.ASSOCIATED_DATA
            if isinstance(graph_object, AssociatedDataObject)
            else ObjectKind.LINK
        )
        self._connection.execute(
            "INSERT INTO graph_presence_interval"
            " (uuid, object_value_id, object_kind, type_key, source_uuid, target_uuid,"
            " valid_from_revision, valid_to_revision) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            (
                graph_object.uuid,
                value_id,
                kind.value,
                graph_object.type_key,
                graph_object.source_uuid if isinstance(graph_object, Link) else None,
                graph_object.target_uuid if isinstance(graph_object, Link) else None,
                revision,
            ),
        )
        return value_id

    def append_transition(self, record: CanonicalTransitionRecord) -> None:
        """Append one transition and update the projection as one recoverable effect.

        The appended record and the updated projection commit together, so no reader can
        observe a revision established by one without the state established by the other.
        The prior revision is re-checked inside the transaction, so two writers cannot
        both believe they are advancing from it.
        """
        projection_assignments = ["revision = ?", "established_by = ?"]
        projection_values: list[object] = [record.resulting_revision, record.resulting_revision]
        active_identity: str | None = None
        proposed_identity: str | None = None
        if record.change.active_definitions is not None:
            projection_assignments.append("active_definition_set_id = ?")
        if record.change.delta_disposition is DefinitionDeltaDisposition.PRESENT:
            assert record.change.definition_delta is not None
            projection_assignments.append("proposed_definition_set_id = ?")
        elif record.change.delta_disposition is DefinitionDeltaDisposition.ABSENT:
            projection_assignments.append("proposed_definition_set_id = ?")
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                row = self._connection.execute(
                    "SELECT revision FROM state_head WHERE id = 0"
                ).fetchone()
                if row is None:
                    self._connection.execute("ROLLBACK")
                    raise NotInitializedError("no canonical state is established")
                if row[0] != record.prior_revision:
                    self._connection.execute("ROLLBACK")
                    raise ConcurrentRevisionError(
                        f"the current revision is {row[0]}, not {record.prior_revision}"
                    )
                if record.change.active_definitions is not None:
                    active_identity = insert_definition_set(
                        self._connection, record.change.active_definitions
                    )
                    projection_values.append(active_identity)
                if record.change.delta_disposition is DefinitionDeltaDisposition.PRESENT:
                    assert record.change.definition_delta is not None
                    proposed_identity = insert_definition_set(
                        self._connection, record.change.definition_delta.proposed_definitions
                    )
                    projection_values.append(proposed_identity)
                elif record.change.delta_disposition is DefinitionDeltaDisposition.ABSENT:
                    projection_values.append(None)
                previous = self._connection.execute(
                    "SELECT r.record_identity FROM canonical_record AS r"
                    " JOIN state_head AS h ON h.established_by = r.established_revision"
                    " WHERE h.id = 0"
                ).fetchone()
                ledger_row = self._connection.execute(
                    "SELECT identity FROM ledger WHERE id = 0"
                ).fetchone()
                if previous is None or ledger_row is None:
                    raise StoreError("the canonical ledger has no identity-bearing base")
                prior_identity = str(previous[0])
                record_identity = self._record_identity(
                    str(ledger_row[0]),
                    prior_identity,
                    record.resulting_revision,
                    record.kind.value,
                    record.recorded_at,
                    record.provenance.initiator,
                    record.provenance.source,
                    str(record.prior_revision),
                    _change_identity(record.change),
                )
                self._connection.execute(
                    "INSERT INTO canonical_record (established_revision, ordinal, record_kind,"
                    " recorded_at, initiator, source, summary, prior_revision, record_identity,"
                    " prior_record_identity)"
                    f" VALUES (?, ({NEXT_ORDINAL_SQL}), ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record.resulting_revision,
                        record.kind.value,
                        _stored_time(record.recorded_at),
                        record.provenance.initiator,
                        record.provenance.source,
                        str(record.prior_revision),
                        record.prior_revision,
                        record_identity,
                        prior_identity,
                    ),
                )
                self._connection.execute(
                    "UPDATE state_head SET " + ", ".join(projection_assignments) + " WHERE id = 0",
                    tuple(projection_values),
                )
                if record.change.delta_disposition is DefinitionDeltaDisposition.ABSENT:
                    self._connection.execute("DELETE FROM proposal_entry")
                    self._connection.execute(
                        "UPDATE proposal_overlay_state SET accumulator = ?, entry_count = 0"
                        " WHERE id = 0",
                        ("0" * 64,),
                    )
                    self._connection.execute("DELETE FROM proposal_definition_type")
                    self._connection.execute("DELETE FROM proposal_definition_relationship")
                    self._connection.execute(
                        "UPDATE proposal_definition_state SET base_definition_set_id = NULL,"
                        " accumulator = ?, entry_count = 0, effective_accumulator = NULL,"
                        " effective_entry_count = NULL, identity = NULL WHERE id = 0",
                        ("0" * 64,),
                    )
                if record.change.graph_change is not None:
                    self._apply_current_graph_change_unlocked(
                        record.change.graph_change, record.resulting_revision
                    )
                    self._insert_graph_events(record.resulting_revision, record.change.graph_change)
                elif record.change.replacement_graph is not None:
                    self._insert_replacement_events(
                        record.resulting_revision, record.change.replacement_graph
                    )
                    self._replace_current_graph_unlocked(
                        record.change.replacement_graph, record.resulting_revision
                    )
                self._connection.execute(
                    "INSERT INTO canonical_definition_event"
                    " (established_revision, active_definition_set_id, delta_disposition,"
                    " proposed_definition_set_id)"
                    " VALUES (?, ?, ?, ?)",
                    (
                        record.resulting_revision,
                        active_identity,
                        record.change.delta_disposition.value,
                        proposed_identity,
                    ),
                )
                self._connection.execute("COMMIT")
            except StoreError:
                self._rollback_quietly()
                raise
            except Exception as error:
                self._rollback_quietly()
                raise StoreError(f"could not append the transition: {error}") from error

    def _insert_graph_events(self, revision: int, change: GraphChange) -> None:
        occurrence = 0
        for kind, uuid in change.removals():
            self._connection.execute(
                "INSERT INTO canonical_graph_event VALUES (?, ?, 'delete', ?, ?, NULL)",
                (revision, occurrence, kind.value, uuid),
            )
            occurrence += 1
        for kind, value in change.upserts():
            value_id = insert_object_value(self._connection, value)
            self._connection.execute(
                "INSERT INTO canonical_graph_event VALUES (?, ?, 'upsert', ?, ?, ?)",
                (revision, occurrence, kind.value, value.uuid, value_id),
            )
            occurrence += 1

    def _insert_replacement_events(self, revision: int, graph: Graph) -> None:
        # Historical replacement is retained only until W005 converts restore to an
        # SQL-computed explicit difference.  Even here the ledger stores normalized
        # per-object events rather than one replacement document.
        current = {
            str(row[0]): str(row[1])
            for row in self._connection.execute(
                "SELECT uuid, object_kind FROM current_graph_object"
            )
        }
        wanted = {value.uuid: value for value in graph.objects()}
        change = GraphChange(
            anchor_upserts=tuple(value for value in wanted.values() if isinstance(value, Anchor)),
            associated_data_upserts=tuple(
                value for value in wanted.values() if isinstance(value, AssociatedDataObject)
            ),
            link_upserts=tuple(value for value in wanted.values() if isinstance(value, Link)),
            anchor_removals=tuple(
                uuid
                for uuid, kind in current.items()
                if uuid not in wanted and kind == ObjectKind.ANCHOR.value
            ),
            associated_data_removals=tuple(
                uuid
                for uuid, kind in current.items()
                if uuid not in wanted and kind == ObjectKind.ASSOCIATED_DATA.value
            ),
            link_removals=tuple(
                uuid
                for uuid, kind in current.items()
                if uuid not in wanted and kind == ObjectKind.LINK.value
            ),
        )
        self._insert_graph_events(revision, change)

    def transitions(self) -> tuple[CanonicalTransitionRecord, ...]:
        """Read every transition in ledger order. Each is a semantic record access."""
        rows = self._fetchall(
            "SELECT established_revision, record_kind, recorded_at, initiator, source, summary,"
            " prior_revision FROM canonical_record WHERE ordinal > 0 ORDER BY ordinal"
        )
        self._record_reads += len(rows)
        records: list[CanonicalTransitionRecord] = []
        for row in rows:
            assert isinstance(row, tuple)
            records.append(self._transition_from(_RecordRow(*row)))
        return tuple(records)

    def _transition_from(self, record: _RecordRow) -> CanonicalTransitionRecord:
        try:
            kind = TransitionKind(record.record_kind)
            if record.prior_revision is None:
                raise ValueError("a transition has no prior revision")
            prior = int(record.prior_revision)
        except ValueError as error:
            raise StoreError(
                f"a canonical record at {self._path} is not a readable transition: {error}"
            ) from error
        return CanonicalTransitionRecord(
            prior_revision=prior,
            resulting_revision=record.established_revision,
            kind=kind,
            change=self._change_at(record.established_revision, kind),
            provenance=Provenance(initiator=record.initiator, source=record.source),
            recorded_at=self._recorded_at(record.recorded_at),
        )

    def _change_at(self, revision: int, kind: TransitionKind) -> CanonicalChange:
        upserts: dict[ObjectKind, list[GraphObject]] = {each: [] for each in ObjectKind}
        removals: dict[ObjectKind, list[str]] = {each: [] for each in ObjectKind}
        for operation, kind_text, uuid, value_id in self._connection.execute(
            "SELECT operation, object_kind, uuid, object_value_id FROM canonical_graph_event"
            " WHERE established_revision = ? ORDER BY occurrence",
            (revision,),
        ):
            object_kind = ObjectKind(str(kind_text))
            if operation == "delete":
                removals[object_kind].append(str(uuid))
            else:
                if value_id is None:
                    raise StoreError(f"upsert event {revision}:{uuid} has no object value")
                upserts[object_kind].append(self._load_object_value(int(value_id)))
        graph_change = GraphChange(
            anchor_upserts=tuple(
                each for each in upserts[ObjectKind.ANCHOR] if isinstance(each, Anchor)
            ),
            associated_data_upserts=tuple(
                each
                for each in upserts[ObjectKind.ASSOCIATED_DATA]
                if isinstance(each, AssociatedDataObject)
            ),
            link_upserts=tuple(each for each in upserts[ObjectKind.LINK] if isinstance(each, Link)),
            anchor_removals=tuple(removals[ObjectKind.ANCHOR]),
            associated_data_removals=tuple(removals[ObjectKind.ASSOCIATED_DATA]),
            link_removals=tuple(removals[ObjectKind.LINK]),
        )
        definition_row = self._connection.execute(
            "SELECT active_definition_set_id, delta_disposition, proposed_definition_set_id"
            " FROM canonical_definition_event WHERE established_revision = ?",
            (revision,),
        ).fetchone()
        if definition_row is None:
            raise StoreError(f"canonical record {revision} has no normalized definition event")
        active_id, disposition_text, proposed_id = definition_row
        disposition = DefinitionDeltaDisposition(str(disposition_text))
        definition_delta = (
            None
            if proposed_id is None
            else DefinitionDelta(
                proposed_definitions=self._proposal_definitions_at_unlocked(revision),
                graph_overlay=self._proposal_graph_change_at_unlocked(revision),
            )
        )
        replacement = (
            self._graph_at_unlocked(revision)
            if kind is TransitionKind.HISTORICAL_RESTORATION
            else None
        )
        return CanonicalChange(
            graph_change=(
                graph_change
                if kind in {TransitionKind.GRAPH_MUTATION, TransitionKind.DEFINITION_ACTIVATION}
                and (graph_change.upserts() or graph_change.removals())
                else None
            ),
            replacement_graph=replacement,
            active_definitions=(
                None if active_id is None else self._load_definition_set(str(active_id))
            ),
            delta_disposition=disposition,
            definition_delta=definition_delta,
        )

    def _proposal_definitions_at_unlocked(self, revision: int) -> GraphDefinitionSet:
        """Rebuild sparse proposed-definition meaning from append-only keyed events."""
        active_row = self._connection.execute(
            "SELECT active_definition_set_id FROM canonical_definition_event"
            " WHERE established_revision <= ? AND active_definition_set_id IS NOT NULL"
            " ORDER BY established_revision DESC LIMIT 1",
            (revision,),
        ).fetchone()
        if active_row is None:
            raise StoreError(f"revision {revision} has no active definition base")
        active = self._load_definition_set(str(active_row[0]))
        last_absent = self._connection.execute(
            "SELECT coalesce(max(established_revision), -1) FROM canonical_definition_event"
            " WHERE established_revision <= ? AND delta_disposition = 'absent'",
            (revision,),
        ).fetchone()
        start = -1 if last_absent is None else int(last_absent[0])
        active_types: dict[str, object] = {
            **{value.type_key: value for value in active.anchor_types},
            **{value.type_key: value for value in active.associated_data_types},
            **{value.type_key: value for value in active.link_types},
        }
        active_relationships = {
            semantic_identity(relationship_identity(value)): value
            for value in active.relationship_constraints
        }
        types = dict(active_types)
        relationships = dict(active_relationships)
        for entity_kind, natural_key, operation, value_set_id in self._connection.execute(
            "SELECT entity_kind, natural_key, operation, value_set_id"
            " FROM canonical_definition_proposal_event WHERE established_revision > ?"
            " AND established_revision <= ? ORDER BY established_revision, occurrence",
            (start, revision),
        ):
            key = str(natural_key)
            if str(entity_kind) == "type":
                if operation == "unstage":
                    if key in active_types:
                        types[key] = active_types[key]
                    else:
                        types.pop(key, None)
                    continue
                if operation == "delete":
                    types.pop(key, None)
                    continue
                value = self._load_definition_set(str(value_set_id))
                members = (*value.anchor_types, *value.associated_data_types, *value.link_types)
                if len(members) != 1:
                    raise StoreError("a definition proposal type event is not one value")
                types[key] = members[0]
            else:
                if operation == "unstage":
                    if key in active_relationships:
                        relationships[key] = active_relationships[key]
                    else:
                        relationships.pop(key, None)
                    continue
                if operation == "delete":
                    relationships.pop(key, None)
                    continue
                value = self._load_definition_set(str(value_set_id))
                if len(value.relationship_constraints) != 1:
                    raise StoreError("a definition proposal rule event is not one value")
                relationships[key] = value.relationship_constraints[0]
        return GraphDefinitionSet(
            tuple(value for value in types.values() if isinstance(value, AnchorTypeDefinition)),
            tuple(
                value for value in types.values() if isinstance(value, AssociatedDataTypeDefinition)
            ),
            tuple(value for value in types.values() if isinstance(value, LinkTypeDefinition)),
            tuple(relationships.values()),
        )

    def _proposal_graph_change_at_unlocked(self, revision: int) -> GraphChange:
        last_absent = self._connection.execute(
            "SELECT coalesce(max(established_revision), -1) FROM canonical_definition_event"
            " WHERE established_revision <= ? AND delta_disposition = 'absent'",
            (revision,),
        ).fetchone()
        start = -1 if last_absent is None else int(last_absent[0])
        entries: dict[str, tuple[ObjectKind, str, int | None]] = {}
        for operation, kind_name, uuid, value_id in self._connection.execute(
            "SELECT operation, object_kind, uuid, object_value_id"
            " FROM canonical_proposal_event WHERE established_revision > ?"
            " AND established_revision <= ? ORDER BY established_revision, occurrence",
            (start, revision),
        ):
            if operation == "unstage":
                entries.pop(str(uuid), None)
            else:
                entries[str(uuid)] = (ObjectKind(str(kind_name)), str(operation), value_id)
        upserts: dict[ObjectKind, list[GraphObject]] = {kind: [] for kind in ObjectKind}
        removals: dict[ObjectKind, list[str]] = {kind: [] for kind in ObjectKind}
        for uuid, (kind, operation, value_id) in sorted(entries.items()):
            if operation == "delete":
                removals[kind].append(uuid)
            else:
                assert value_id is not None
                upserts[kind].append(self._load_object_value(int(value_id)))
        return GraphChange(
            tuple(each for each in upserts[ObjectKind.ANCHOR] if isinstance(each, Anchor)),
            tuple(
                each
                for each in upserts[ObjectKind.ASSOCIATED_DATA]
                if isinstance(each, AssociatedDataObject)
            ),
            tuple(each for each in upserts[ObjectKind.LINK] if isinstance(each, Link)),
            tuple(removals[ObjectKind.ANCHOR]),
            tuple(removals[ObjectKind.ASSOCIATED_DATA]),
            tuple(removals[ObjectKind.LINK]),
        )

    def _recorded_at(self, text: str) -> datetime:
        try:
            return datetime.fromisoformat(text)
        except ValueError as error:
            raise StoreError(
                f"a canonical record at {self._path} has an unreadable time: {error}"
            ) from error

    def ledger_identity(self) -> str:
        """Return this ledger's own identity, established with its history base."""
        row = self._fetchone("SELECT identity FROM ledger WHERE id = 0")
        if row is None:
            raise NotInitializedError("no canonical state is established")
        assert isinstance(row, tuple)
        return str(row[0])

    def establishing_record(self) -> tuple[int, CanonicalTransitionRecord | None]:
        """Return the current revision and the transition that established it.

        Read from the projection row in one statement, so the pair cannot disagree the
        way two separate reads can when another writer commits between them.
        """
        row = self._read_record(
            "SELECT s.revision, r.ordinal, r.established_revision, r.record_kind, r.recorded_at,"
            " r.initiator, r.source, r.summary, r.prior_revision"
            " FROM state_head s JOIN canonical_record r"
            " ON r.established_revision = s.established_by WHERE s.id = 0"
        )
        if row is None:
            raise NotInitializedError("no canonical state is established")
        assert isinstance(row, tuple)
        revision, ordinal = int(row[0]), int(row[1])
        if not ordinal:
            return revision, None
        record = _RecordRow(*row[2:])
        return revision, self._transition_from(record)

    def snapshot_basis(
        self,
    ) -> tuple[
        CanonicalState,
        InitialStateRecord,
        tuple[CanonicalTransitionRecord, ...],
        str,
    ]:
        """Capture state and every value needed for its lineage in one read snapshot."""
        try:
            with self._lock:
                self._connection.execute("BEGIN")
                try:
                    state = self._current_state_unlocked()
                    initial = self.initial_record()
                    transitions = self.transitions()
                    identity = self.ledger_identity()
                    if transitions and transitions[-1].resulting_revision != state.revision:
                        raise StoreError(
                            "the current projection and canonical ledger end at different revisions"
                        )
                    if not transitions and state.revision != initial.established_revision:
                        raise StoreError(
                            "the current projection and canonical history base disagree"
                        )
                    self._connection.execute("COMMIT")
                    return state, initial, transitions, identity
                except BaseException:
                    self._rollback_quietly()
                    raise
        except sqlite3.Error as error:
            raise StoreError(
                f"could not capture a snapshot basis at {self._path}: {error}"
            ) from error

    def revision_at(self, moment: datetime) -> int | None:
        """Return the greatest committed revision recorded at or before ``moment``.

        Written to seek the time index rather than aggregate over it. An ``max()`` with a
        time predicate looks equivalent and is not: it walks the revision key downward
        until the predicate passes, so the cost is everything committed *after* the
        answer — worst exactly where this capability is used, reading an old state.

        The tie-break is on revision, because the requirement asks for the greatest
        committed revision at or before an instant, and two records can share one.
        """
        row = self._read_record(
            "SELECT established_revision FROM canonical_record WHERE recorded_at <= ?"
            " ORDER BY recorded_at DESC, established_revision DESC LIMIT 1",
            (_stored_time(moment),),
        )
        return None if row is None else int(row[0])  # pyright: ignore[reportIndexIssue]

    def has_revision(self, revision: int) -> bool:
        """Whether some record in this ledger established ``revision``."""
        row = self._read_record(
            "SELECT 1 FROM canonical_record WHERE established_revision = ?", (revision,)
        )
        return row is not None

    def transitions_through(self, revision: int) -> tuple[CanonicalTransitionRecord, ...]:
        """Read the transitions establishing revisions up to and including ``revision``."""
        rows = self._fetchall(
            "SELECT established_revision, record_kind, recorded_at, initiator, source, summary,"
            " prior_revision FROM canonical_record WHERE ordinal > 0 AND established_revision <= ?"
            " ORDER BY ordinal",
            (revision,),
        )
        self._record_reads += len(rows)
        records: list[CanonicalTransitionRecord] = []
        for row in rows:
            assert isinstance(row, tuple)
            records.append(self._transition_from(_RecordRow(*row)))
        return tuple(records)

    def definition_transitions_through(
        self, revision: int
    ) -> tuple[CanonicalTransitionRecord, ...]:
        """Read only the transitions up to ``revision`` that changed definitions.

        Graph mutations are excluded in the query rather than skipped afterwards, so
        answering "what was the vocabulary then" does not cost the graph work that
        happened in between — which is the difference the requirement asks for.

        Stated as what to leave out rather than what to include: a kind added later is
        then read by default and answers for itself, instead of being silently dropped
        from every historical vocabulary until someone remembers this list.
        """
        rows = self._fetchall(
            DEFINITION_TRANSITIONS_SQL,
            (revision,),
        )
        self._record_reads += len(rows)
        records: list[CanonicalTransitionRecord] = []
        for row in rows:
            assert isinstance(row, tuple)
            records.append(self._transition_from(_RecordRow(*row)))
        return tuple(records)

    def canonical_summaries(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> tuple[tuple[int, int | None, str | None, str, str | None, str, datetime], ...]:
        """Read canonical records for review over an inclusive interval.

        Selects on the indexed time column and reads only the columns an owner-facing
        entry needs, so a narrow window costs the window rather than the ledger. The
        replay payload is not read at all: review is not authority, and decoding every
        change to project a summary would make a bounded read cost the whole history.
        """
        clauses: list[str] = []
        parameters: list[object] = []
        if start is not None:
            clauses.append("recorded_at >= ?")
            parameters.append(_stored_time(start))
        if end is not None:
            clauses.append("recorded_at <= ?")
            parameters.append(_stored_time(end))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        columns = (
            "established_revision, ordinal, record_kind, summary, initiator, source, recorded_at"
        )
        if limit is None:
            sql = f"SELECT {columns} FROM canonical_record{where} ORDER BY ordinal"
        else:
            parameters.append(limit)
            sql = (
                f"WITH bounded AS MATERIALIZED (SELECT {columns} FROM canonical_record{where}"
                f" LIMIT ?) SELECT {columns} FROM bounded ORDER BY ordinal"
            )
        rows = self._fetchall(sql, tuple(parameters))
        self._record_reads += len(rows)
        summaries: list[tuple[int, int | None, str | None, str, str | None, str, datetime]] = []
        for row in rows:
            assert isinstance(row, tuple)
            revision, ordinal, kind, summary, initiator, source, recorded_at = row
            prior = int(summary) if ordinal else None
            summaries.append(
                (
                    int(revision),
                    prior,
                    None if not ordinal else str(kind),
                    str(initiator),
                    None if source is None else str(source),
                    "" if ordinal else str(summary),
                    self._recorded_at(str(recorded_at)),
                )
            )
        return tuple(summaries)

    def initial_record(self) -> InitialStateRecord:
        """Read the owned initial record. This is a semantic canonical-record access."""
        row = self._read_record(
            "SELECT established_revision, record_kind, recorded_at, initiator, source, summary,"
            " prior_revision FROM canonical_record WHERE ordinal = 0"
        )
        if row is None:
            raise StoreError("no initial canonical record is established")
        assert isinstance(row, tuple)
        record = _RecordRow(*row)
        if record.record_kind != "initial":
            raise StoreError(f"ledger base is a {record.record_kind} record, not an initial record")
        definition_row = self._fetchone(
            "SELECT active_definition_set_id, proposed_definition_set_id"
            " FROM canonical_definition_event"
            " WHERE established_revision = ?",
            (record.established_revision,),
        )
        if not isinstance(definition_row, tuple):
            raise StoreError("the initial record has no normalized definition event")
        state = CanonicalState(
            graph=self._graph_at_unlocked(record.established_revision),
            active_definitions=self._load_definition_set(str(definition_row[0])),
            definition_delta=(
                None
                if definition_row[1] is None
                else DefinitionDelta(
                    proposed_definitions=self._load_definition_set(str(definition_row[1]))
                )
            ),
            revision=record.established_revision,
        )
        if state.revision != record.established_revision:
            raise StoreError(
                f"the initial record at {self._path} establishes revision "
                f"{record.established_revision} but carries revision {state.revision}"
            )
        recorded_at = self._recorded_at(record.recorded_at)
        return InitialStateRecord(
            canonical_state=state,
            initialization_summary=record.summary,
            provenance=Provenance(initiator=record.initiator, source=record.source),
            recorded_at=recorded_at,
        )

    def replay(self) -> CanonicalState:
        """Reconstruct canonical state by replaying through the final canonical record."""
        from vellis.canonical import replay as replay_records

        return replay_records(self.initial_record(), self.transitions())

    def verify_projection_from_ledger(self) -> tuple[ValidationFinding, ...]:
        """Rebuild expected projection in temporary SQL and compare in both directions."""
        with self._lock:
            try:
                self._connection.execute("BEGIN")
                base = self._connection.execute(
                    "SELECT established_revision FROM canonical_record WHERE ordinal = 0"
                ).fetchone()
                if base is None:
                    raise NotInitializedError("no canonical state is established")
                self._connection.execute("DROP TABLE IF EXISTS temp.replay_expected")
                self._connection.execute(
                    "CREATE TEMP TABLE replay_expected AS WITH candidates AS ("
                    " SELECT p.uuid, p.object_value_id, p.valid_from_revision AS revision,"
                    " -1 AS occurrence, 'upsert' AS operation"
                    " FROM graph_presence_interval AS p WHERE p.valid_from_revision = ?"
                    " UNION ALL SELECT uuid, object_value_id, established_revision, occurrence,"
                    " operation FROM canonical_graph_event), ranked AS ("
                    " SELECT *, row_number() OVER (PARTITION BY uuid"
                    " ORDER BY revision DESC, occurrence DESC) AS rank FROM candidates)"
                    " SELECT uuid, object_value_id FROM ranked"
                    " WHERE rank = 1 AND operation = 'upsert'",
                    (int(base[0]),),
                )
                differences = self._connection.execute(
                    "SELECT uuid, object_value_id FROM replay_expected"
                    " EXCEPT SELECT uuid, object_value_id FROM current_graph_object"
                    " UNION ALL SELECT uuid, object_value_id FROM current_graph_object"
                    " EXCEPT SELECT uuid, object_value_id FROM replay_expected LIMIT 1"
                ).fetchone()
                definition = self._connection.execute(
                    "SELECT active_definition_set_id, proposed_definition_set_id"
                    " FROM state_head WHERE id = 0"
                ).fetchone()
                expected_active = self._connection.execute(
                    "SELECT active_definition_set_id FROM canonical_definition_event"
                    " WHERE active_definition_set_id IS NOT NULL"
                    " ORDER BY established_revision DESC LIMIT 1"
                ).fetchone()
                expected_delta = self._connection.execute(
                    "SELECT delta_disposition, proposed_definition_set_id"
                    " FROM canonical_definition_event WHERE delta_disposition != 'unchanged'"
                    " ORDER BY established_revision DESC LIMIT 1"
                ).fetchone()
                findings: list[ValidationFinding] = []
                if differences is not None:
                    findings.append(
                        ValidationFinding(
                            summary="replayed graph rows differ from the current projection",
                            implicated_objects=(str(differences[0]),),
                        )
                    )
                expected_proposed = (
                    None
                    if expected_delta is None or expected_delta[0] == "absent"
                    else expected_delta[1]
                )
                if (
                    definition is None
                    or expected_active is None
                    or definition[0] != expected_active[0]
                    or definition[1] != expected_proposed
                ):
                    findings.append(
                        ValidationFinding(
                            summary="replayed definition facets differ from the current projection"
                        )
                    )
                self._connection.execute("ROLLBACK")
                return tuple(findings)
            except BaseException:
                self._rollback_quietly()
                raise

    def canonical_record_count(self) -> int:
        """Return how many canonical records the ledger holds.

        This reaches the ledger, so it counts as a semantic record access.
        """
        row = self._read_record("SELECT count(*) FROM canonical_record")
        assert isinstance(row, tuple)
        return int(row[0])

    # --- The observational ledger ------------------------------------------------------
    #
    # Kept apart from the canonical ledger in every direction: its own table, its own
    # reader, and no path from it into replay. Retention deletes here and nowhere else.

    def append_activity(self, record: ActivityRecord) -> None:
        """Append one observation. Never part of a canonical transaction."""
        try:
            with self._lock:
                self._connection.execute(
                    "INSERT INTO activity_record"
                    " (recorded_at, capability, outcome_category, semantic_scope, summary,"
                    " initiator, source, evaluated_revision) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        _stored_time(record.recorded_at),
                        record.capability,
                        record.outcome_category.value,
                        record.semantic_scope,
                        record.summary,
                        record.provenance.initiator,
                        record.provenance.source,
                        record.evaluated_revision,
                    ),
                )
        except sqlite3.Error as error:
            raise StoreError(f"could not append the activity record: {error}") from error

    def activity_records(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> tuple[ActivityRecord, ...]:
        """Read observations in ledger order over an inclusive interval."""
        clauses: list[str] = []
        parameters: list[object] = []
        if start is not None:
            clauses.append("recorded_at >= ?")
            parameters.append(_stored_time(start))
        if end is not None:
            clauses.append("recorded_at <= ?")
            parameters.append(_stored_time(end))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        if limit is None:
            sql = (
                "SELECT recorded_at, capability, outcome_category, semantic_scope, summary,"
                " initiator, source, evaluated_revision"
                f" FROM activity_record{where} ORDER BY ordinal"
            )
        else:
            parameters.append(limit)
            sql = (
                "WITH bounded AS MATERIALIZED (SELECT ordinal, recorded_at, capability,"
                " outcome_category, semantic_scope, summary, initiator, source, evaluated_revision"
                f" FROM activity_record{where} LIMIT ?) SELECT recorded_at, capability,"
                " outcome_category, semantic_scope, summary, initiator, source, evaluated_revision"
                " FROM bounded ORDER BY ordinal"
            )
        rows = self._fetchall(sql, tuple(parameters))
        self._activity_reads += len(rows)
        records: list[ActivityRecord] = []
        for row in rows:
            assert isinstance(row, tuple)
            try:
                recorded_at, capability, outcome, scope, summary, initiator, source, revision = row
                records.append(
                    ActivityRecord(
                        capability=str(capability),
                        outcome_category=OperationStatus(str(outcome)),
                        semantic_scope=str(scope),
                        summary=str(summary),
                        provenance=Provenance(
                            str(initiator), None if source is None else str(source)
                        ),
                        recorded_at=self._recorded_at(str(recorded_at)),
                        evaluated_revision=None if revision is None else int(revision),
                    )
                )
            except (ValueError, TypeError) as error:
                raise StoreError(
                    f"a stored activity record is not a normalized observation: {error}"
                ) from error
        return tuple(records)

    def remove_activity_before(self, boundary: datetime) -> int:
        """Remove observations recorded before ``boundary``, returning how many went."""
        try:
            with self._lock:
                cursor = self._connection.execute(
                    "DELETE FROM activity_record WHERE recorded_at < ?", (_stored_time(boundary),)
                )
        except sqlite3.Error as error:
            raise StoreError(f"could not apply the retention decision: {error}") from error
        return cursor.rowcount

    def activity_record_count(self) -> int:
        """Return how many activity records the observational ledger holds."""
        row = self._fetchone("SELECT count(*) FROM activity_record")
        assert isinstance(row, tuple)
        return int(row[0])

    def _current_graph_unlocked(self) -> Graph:
        rows = self._connection.execute(
            "SELECT uuid, object_kind, type_key, source_uuid, target_uuid, object_value_id"
            " FROM current_graph_object ORDER BY uuid"
        ).fetchall()
        anchors: list[Anchor] = []
        associated: list[AssociatedDataObject] = []
        links: list[Link] = []
        for row in rows:
            graph_object = self._decode_current_graph_object(*row)
            if isinstance(graph_object, Anchor):
                anchors.append(graph_object)
            elif isinstance(graph_object, AssociatedDataObject):
                associated.append(graph_object)
            else:
                links.append(graph_object)
        self._current_graph_decodes += 1
        return Graph(anchors=tuple(anchors), associated_data=tuple(associated), links=tuple(links))

    def _decode_current_graph_object(
        self,
        uuid: object,
        kind: object,
        type_key: object,
        source_uuid: object,
        target_uuid: object,
        value_id: object,
    ) -> GraphObject:
        if (
            not isinstance(uuid, str)
            or not isinstance(kind, str)
            or not isinstance(type_key, str)
            or not isinstance(value_id, int)
        ):
            raise StoreError("a stored current graph-object row has invalid identity or value")
        try:
            graph_object = self._load_object_value(value_id)
        except (ValueError, ArithmeticError) as error:
            raise StoreError(
                f"stored current graph object {uuid!r} does not decode from normalized rows:"
                f" {error}"
            ) from error
        if graph_object.uuid != uuid:
            raise StoreError(f"stored current graph-object row {uuid!r} carries different content")
        if kind != (
            ObjectKind.ANCHOR.value
            if isinstance(graph_object, Anchor)
            else ObjectKind.ASSOCIATED_DATA.value
            if isinstance(graph_object, AssociatedDataObject)
            else ObjectKind.LINK.value
        ):
            raise StoreError(f"stored current graph-object row {uuid!r} carries a different kind")
        expected_source = graph_object.source_uuid if isinstance(graph_object, Link) else None
        expected_target = graph_object.target_uuid if isinstance(graph_object, Link) else None
        if (
            type_key != graph_object.type_key
            or source_uuid != expected_source
            or target_uuid != expected_target
        ):
            raise StoreError(
                f"stored current graph-object row {uuid!r} has selectors that disagree with"
                " its normalized value"
            )
        if isinstance(graph_object, AssociatedDataObject):
            indexed_anchors = {
                str(row[0])
                for row in self._connection.execute(
                    "SELECT anchor_uuid FROM current_data_anchor WHERE data_uuid = ?",
                    (uuid,),
                ).fetchall()
            }
            if indexed_anchors != set(graph_object.anchor_uuids):
                raise StoreError(
                    f"stored current associated-data row {uuid!r} has association selectors"
                    " that disagree with its normalized value"
                )
        self._current_graph_object_decodes += 1
        return graph_object

    def _load_object_value(self, value_id: int) -> GraphObject:
        return load_object_value(self._connection, value_id)

    def _load_definition_set(
        self,
        identity: str,
        *,
        type_keys: set[str] | None = None,
        constrained_type_keys: set[str] | None = None,
        relationship_keys: set[str] | None = None,
    ) -> GraphDefinitionSet:
        self._current_definition_decodes += 1
        try:
            return load_definition_set(
                self._connection,
                identity,
                type_keys=type_keys,
                constrained_type_keys=constrained_type_keys,
                relationship_keys=relationship_keys,
            )
        except (ValueError, ArithmeticError) as error:
            raise StoreError(f"stored definitions do not decode: {error}") from error

    def _graph_at_unlocked(self, revision: int) -> Graph:
        rows = self._connection.execute(
            "SELECT v.id FROM graph_presence_interval p JOIN object_value v"
            " ON v.id = p.object_value_id WHERE p.valid_from_revision <= ?"
            " AND (p.valid_to_revision IS NULL OR p.valid_to_revision > ?) ORDER BY p.uuid",
            (revision, revision),
        )
        anchors: list[Anchor] = []
        associated: list[AssociatedDataObject] = []
        links: list[Link] = []
        for (value_id,) in rows:
            value = self._load_object_value(int(value_id))
            if isinstance(value, Anchor):
                anchors.append(value)
            elif isinstance(value, AssociatedDataObject):
                associated.append(value)
            else:
                links.append(value)
        return Graph(tuple(anchors), tuple(associated), tuple(links))


class _SQLiteQueryIndex:
    """Query-local access through the durable projection's identity indexes."""

    def __init__(
        self, store: CanonicalStore, revision: int | None = None, prospective: bool = False
    ) -> None:
        self._store = store
        self._revision = revision
        self._prospective = prospective
        self._anchors: dict[object, tuple[Anchor, ...]] = {}
        self._data: dict[
            tuple[str, str, frozenset[str] | None], tuple[AssociatedDataObject, ...]
        ] = {}
        self._links: dict[tuple[object, str, str], tuple[Link, ...]] = {}
        self._link_pairs: dict[object, frozenset[tuple[str, str]]] = {}

    def known_anchor_uuids(self, anchor_type: str, uuids: tuple[str, ...]) -> set[str]:
        return self._known_uuids(ObjectKind.ANCHOR, anchor_type, uuids)

    def known_link_uuids(self, link_type: str, uuids: tuple[str, ...]) -> set[str]:
        return self._known_uuids(ObjectKind.LINK, link_type, uuids)

    def _known_uuids(self, kind: ObjectKind, type_key: str, uuids: tuple[str, ...]) -> set[str]:
        if not uuids:
            return set()
        placeholders = ", ".join("?" for _ in uuids)
        if self._revision is not None:
            return {
                str(row[0])
                for row in self._store._connection.execute(  # noqa: SLF001
                    "SELECT p.uuid FROM graph_presence_interval AS p"
                    " JOIN object_value AS v ON v.id = p.object_value_id"
                    " WHERE p.valid_from_revision <= ?"
                    " AND (p.valid_to_revision IS NULL OR p.valid_to_revision > ?)"
                    " AND v.object_kind = ? AND v.type_key = ?"
                    f" AND p.uuid IN ({placeholders})",
                    (self._revision, self._revision, kind.value, type_key, *uuids),
                )
            }
        relation = "prospective_graph_object" if self._prospective else "current_graph_object"
        return {
            str(row[0])
            for row in self._store._connection.execute(  # noqa: SLF001
                f"SELECT uuid FROM {relation}"
                f" WHERE object_kind = ? AND type_key = ? AND uuid IN ({placeholders})",
                (kind.value, type_key, *uuids),
            ).fetchall()
        }

    def anchor_candidates(
        self, group: AnchorGroup, allowed_uuids: frozenset[str] | None = None
    ) -> tuple[Anchor, ...]:
        key = (group.anchor_type, group.uuid_filter, allowed_uuids)
        cached = self._anchors.get(key)
        if cached is not None:
            return cached
        clauses = ["object_kind = ?", "type_key = ?"]
        parameters: list[object] = [ObjectKind.ANCHOR.value, group.anchor_type]
        permitted = None if group.uuid_filter is None else frozenset(group.uuid_filter.uuids)
        if allowed_uuids is not None:
            permitted = allowed_uuids if permitted is None else permitted & allowed_uuids
        if permitted is not None:
            if not permitted:
                return ()
            placeholders = ", ".join("?" for _ in permitted)
            clauses.append(f"uuid IN ({placeholders})")
            parameters.extend(permitted)
        rows = self._store._connection.execute(  # noqa: SLF001
            "SELECT uuid, object_kind, type_key, source_uuid, target_uuid, object_value_id"
            " FROM current_graph_object WHERE " + " AND ".join(clauses),
            tuple(parameters),
        ).fetchall()
        result = tuple(self._anchors_from(rows))
        self._anchors[key] = result
        return result

    def associated_data_candidates(
        self,
        associated_data_type: str,
        anchor_uuid: str,
        allowed_uuids: frozenset[str] | None = None,
    ) -> tuple[AssociatedDataObject, ...]:
        key = (associated_data_type, anchor_uuid, allowed_uuids)
        cached = self._data.get(key)
        if cached is not None:
            return cached
        clauses = ["da.anchor_uuid = ?", "o.object_kind = ?", "o.type_key = ?"]
        parameters: list[object] = [
            anchor_uuid,
            ObjectKind.ASSOCIATED_DATA.value,
            associated_data_type,
        ]
        if allowed_uuids is not None:
            if not allowed_uuids:
                return ()
            placeholders = ", ".join("?" for _ in allowed_uuids)
            clauses.append(f"o.uuid IN ({placeholders})")
            parameters.extend(allowed_uuids)
        rows = self._store._connection.execute(  # noqa: SLF001
            "SELECT o.uuid, o.object_kind, o.type_key, o.source_uuid, o.target_uuid,"
            " o.object_value_id"
            " FROM current_data_anchor AS da"
            " JOIN current_graph_object AS o ON o.uuid = da.data_uuid"
            " WHERE " + " AND ".join(clauses),
            tuple(parameters),
        ).fetchall()
        result = tuple(self._data_from(rows))
        self._data[key] = result
        return result

    def link_candidates(
        self, required: RequiredLink, source_uuid: str, target_uuid: str
    ) -> tuple[Link, ...]:
        key = (required, source_uuid, target_uuid)
        cached = self._links.get(key)
        if cached is not None:
            return cached
        clauses = [
            "object_kind = ?",
            "type_key = ?",
            "source_uuid = ?",
            "target_uuid = ?",
        ]
        parameters: list[object] = [
            ObjectKind.LINK.value,
            required.link_type,
            source_uuid,
            target_uuid,
        ]
        if required.uuid_filter is not None:
            if not required.uuid_filter.uuids:
                return ()
            placeholders = ", ".join("?" for _ in required.uuid_filter.uuids)
            clauses.append(f"uuid IN ({placeholders})")
            parameters.extend(required.uuid_filter.uuids)
        rows = self._store._connection.execute(  # noqa: SLF001
            "SELECT uuid, object_kind, type_key, source_uuid, target_uuid, object_value_id"
            " FROM current_graph_object WHERE " + " AND ".join(clauses),
            tuple(parameters),
        ).fetchall()
        result = tuple(self._links_from(rows))
        self._links[key] = result
        return result

    def link_endpoint_pairs(self, required: RequiredLink) -> frozenset[tuple[str, str]]:
        cached = self._link_pairs.get(required)
        if cached is not None:
            return cached
        clauses = ["object_kind = ?", "type_key = ?"]
        parameters: list[object] = [ObjectKind.LINK.value, required.link_type]
        if required.uuid_filter is not None:
            if not required.uuid_filter.uuids:
                return frozenset()
            placeholders = ", ".join("?" for _ in required.uuid_filter.uuids)
            clauses.append(f"uuid IN ({placeholders})")
            parameters.extend(required.uuid_filter.uuids)
        rows = self._store._connection.execute(  # noqa: SLF001
            "SELECT source_uuid, target_uuid FROM current_graph_object WHERE "
            + " AND ".join(clauses),
            tuple(parameters),
        ).fetchall()
        result = frozenset(
            (str(source_uuid), str(target_uuid)) for source_uuid, target_uuid in rows
        )
        self._link_pairs[required] = result
        return result

    def _anchors_from(self, rows: list[tuple[object, ...]]):
        for row in rows:
            graph_object = self._store._decode_current_graph_object(*row)  # noqa: SLF001
            if not isinstance(graph_object, Anchor):
                raise StoreError("an indexed anchor candidate carries another object kind")
            yield graph_object

    def _data_from(self, rows: list[tuple[object, ...]]):
        for row in rows:
            graph_object = self._store._decode_current_graph_object(*row)  # noqa: SLF001
            if not isinstance(graph_object, AssociatedDataObject):
                raise StoreError("an indexed data candidate carries another object kind")
            yield graph_object

    def _links_from(self, rows: list[tuple[object, ...]]):
        for row in rows:
            graph_object = self._store._decode_current_graph_object(*row)  # noqa: SLF001
            if not isinstance(graph_object, Link):
                raise StoreError("an indexed link candidate carries another object kind")
            yield graph_object
