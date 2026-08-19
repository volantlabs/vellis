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

import os
import secrets
import sqlite3
import stat
from collections.abc import Iterable, Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from threading import Lock, RLock
from typing import TYPE_CHECKING
from urllib.parse import quote

from vellis.activity import ActivityRecord
from vellis.canonical import (
    CanonicalChange,
    CanonicalTransitionRecord,
    DefinitionDeltaDisposition,
    Provenance,
    TransitionKind,
    now,
)
from vellis.changes import (
    GraphChange,
    GraphChangeRequest,
    GraphChangeTarget,
    apply_change_to_objects,
    change_findings,
)
from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    DefinitionEntry,
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
    GraphObject,
    Link,
    ObjectKind,
)
from vellis.json_value import json_equal
from vellis.mutation_impact import (
    ImpactNeighborhood,
    MultiplicityImpactReason,
    count_multiplicity_for_subjects,
    derive_multiplicity_impact_reasons,
    index_multiplicity_facts,
)
from vellis.normalized import (
    adjust_semantic_summary,
    definition_content_stats,
    definition_entry_digest,
    definition_identity,
    definition_identity_from_stats,
    graph_entry_digest,
    insert_definition_entries,
    insert_definition_entry,
    insert_object_value,
    json_storage_value,
    load_definition_set,
    load_object_value,
    normalized_state_identity,
    object_identity,
    proposal_definition_stats_from_storage,
    recomputed_graph_summary,
    semantic_identity,
    semantic_row_summary,
    verify_proposal_summaries,
    verify_state_summaries,
)
from vellis.outcomes import (
    OperationStatus,
    RevisionedOutcome,
    ValidationFinding,
    ValidationReport,
    ValidationScope,
)
from vellis.patterns import PatternError, compile_pattern
from vellis.validation import (
    _prepare_property_constraint,
    _PreparedPropertyConstraint,
    _validate_prepared_property_value,
    assess_object_neighborhood,
)

_MAXIMUM_SQLITE_INTEGER = 2**63 - 1
_AGGREGATION_BATCH_SIZE = 256

if TYPE_CHECKING:
    from vellis.query import AggregateBinding, GraphQuery, GraphQueryResult

__all__ = [
    "AlreadyInitializedError",
    "ActivityAppendError",
    "CanonicalStore",
    "ConcurrentRevisionError",
    "ForeignDatabaseError",
    "InvalidInitialDefinitionsError",
    "NotADatabaseError",
    "NotInitializedError",
    "ProposalState",
    "StoreError",
    "UnreadableStoreError",
    "holds_established_memory",
]

SCHEMA_VERSION = "5"

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
    prior_record_identity TEXT,
    content_identity     TEXT    NOT NULL,
    resulting_state_identity TEXT,
    event_identity TEXT
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
CREATE TABLE definition_set_overlay (
    definition_set_id TEXT PRIMARY KEY REFERENCES definition_set(identity),
    base_definition_set_id TEXT NOT NULL REFERENCES definition_set(identity)
);
CREATE TABLE definition_set_type_override (
    definition_set_id TEXT NOT NULL REFERENCES definition_set(identity),
    type_key TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('upsert', 'delete')),
    value_set_id TEXT REFERENCES definition_set(identity),
    PRIMARY KEY (definition_set_id, type_key)
);
CREATE TABLE definition_set_relationship_override (
    definition_set_id TEXT NOT NULL REFERENCES definition_set(identity),
    natural_key TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('upsert', 'delete')),
    value_set_id TEXT REFERENCES definition_set(identity),
    PRIMARY KEY (definition_set_id, natural_key)
);
CREATE TABLE current_definition_type_source (
    type_key TEXT PRIMARY KEY,
    value_set_id TEXT NOT NULL REFERENCES definition_set(identity)
);
CREATE TABLE current_definition_relationship_source (
    natural_key TEXT PRIMARY KEY,
    value_set_id TEXT NOT NULL REFERENCES definition_set(identity)
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
CREATE INDEX definition_type_natural_key
    ON definition_type(definition_set_id, type_key, occurrence);
CREATE TABLE definition_anchor_permission (
    definition_set_id TEXT NOT NULL,
    type_occurrence INTEGER NOT NULL,
    occurrence INTEGER NOT NULL,
    anchor_type_key TEXT NOT NULL,
    PRIMARY KEY (definition_set_id, type_occurrence, occurrence),
    FOREIGN KEY (definition_set_id, type_occurrence)
      REFERENCES definition_type(definition_set_id, occurrence)
);
CREATE INDEX definition_anchor_permission_reverse
    ON definition_anchor_permission(definition_set_id, anchor_type_key, type_occurrence);
CREATE INDEX definition_anchor_permission_by_type
    ON definition_anchor_permission(anchor_type_key, definition_set_id, type_occurrence);
CREATE INDEX definition_anchor_permission_forward
    ON definition_anchor_permission(
        definition_set_id, type_occurrence, occurrence, anchor_type_key
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
CREATE INDEX definition_endpoint_permission_reverse
    ON definition_endpoint_permission(definition_set_id, type_key, type_occurrence, role);
CREATE INDEX definition_endpoint_permission_by_type
    ON definition_endpoint_permission(type_key, definition_set_id, type_occurrence, role);
CREATE INDEX definition_endpoint_permission_forward
    ON definition_endpoint_permission(
        definition_set_id, type_occurrence, role, occurrence, type_key
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
CREATE UNIQUE INDEX definition_multiplicity_natural_key
    ON definition_multiplicity_rule(definition_set_id, natural_key, occurrence);
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
CREATE INDEX definition_multiplicity_participant_reverse
    ON definition_multiplicity_participant(definition_set_id, type_key, role, rule_occurrence);
CREATE INDEX definition_multiplicity_participant_by_type
    ON definition_multiplicity_participant(type_key, definition_set_id, role, rule_occurrence);
CREATE INDEX definition_multiplicity_participant_forward
    ON definition_multiplicity_participant(
        definition_set_id, rule_occurrence, role, occurrence, type_key
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
    proposed_definition_set_id TEXT,
    graph_entry_count INTEGER NOT NULL,
    graph_accumulator TEXT NOT NULL
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
CREATE INDEX graph_presence_uuid_revision
    ON graph_presence_interval(uuid, valid_from_revision, valid_to_revision);
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


@lru_cache(maxsize=256)
def _compiled_query_pattern(expression: str):
    return compile_pattern(expression)


def _stored_pattern_matches(value: object, expression: object) -> int:
    """Apply one already validated RE2 query pattern to one stored string value."""
    if not isinstance(value, str) or not isinstance(expression, str):
        return 0
    try:
        return int(_compiled_query_pattern(expression).matches(value))
    except PatternError:
        return 0


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


class ActivityAppendError(StoreError):
    """Raised when a required observational record cannot be durably appended."""


_CHECKPOINT_LOCK = Lock()


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


class InvalidInitialDefinitionsError(StoreError):
    """Raised when streamed initial definitions fail semantic validation."""

    def __init__(self, findings: tuple[ValidationFinding, ...]) -> None:
        super().__init__("the normalized initial definitions are not conforming")
        self.findings = findings


class NotInitializedError(StoreError):
    """Raised when an operation needs canonical state that was never established.

    Its sibling is ``AlreadyInitializedError``: both are determinate preconditions the
    caller can act on, not the damaged-store condition the bare ``StoreError`` reports.
    """


class ConcurrentRevisionError(StoreError):
    """Raised when the revision a change was prepared against is no longer current."""


def _private_path_error(path: Path, required_mode: int, reason: str) -> StoreError:
    mode = format(required_mode, "04o")
    return StoreError(
        f"refusing insecure plaintext Vellis storage at {path}: {reason}; "
        f"ensure it is owned by the current user and run `chmod {mode} -- {path}`"
    )


def _validate_private_posix_path(path: Path, *, directory: bool) -> None:
    """Fail closed on an existing POSIX path without changing its permissions."""
    if os.name != "posix":
        return
    required_mode = 0o700 if directory else 0o600
    try:
        metadata = path.lstat()
    except OSError as error:
        raise _private_path_error(path, required_mode, f"could not inspect it ({error})") from error
    expected_kind = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if not expected_kind:
        kind = "directory" if directory else "regular database file"
        raise _private_path_error(path, required_mode, f"it is not a {kind}")
    if metadata.st_uid != os.geteuid():
        raise _private_path_error(path, required_mode, "it is not owned by the current user")
    actual_mode = stat.S_IMODE(metadata.st_mode)
    if actual_mode != required_mode:
        raise _private_path_error(
            path,
            required_mode,
            f"its mode is {actual_mode:04o}, not the required {required_mode:04o}",
        )


def prepare_private_directory(path: Path) -> None:
    """Create one private Vellis directory, or validate an existing one on POSIX."""
    if os.name != "posix":
        path.mkdir(parents=True, exist_ok=True)
        return
    try:
        path.mkdir(parents=True, mode=0o700)
    except FileExistsError:
        _validate_private_posix_path(path, directory=True)
        return
    os.chmod(path, 0o700)
    _validate_private_posix_path(path, directory=True)


def _prepare_private_store_path(path: Path) -> None:
    """Validate the enclosing directory and atomically establish a private file."""
    if os.name != "posix":
        return
    _validate_private_posix_path(path.parent, directory=True)
    try:
        path.lstat()
    except FileNotFoundError:
        flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            _validate_private_posix_path(path, directory=False)
        else:
            try:
                os.fchmod(descriptor, 0o600)
            finally:
                os.close(descriptor)
    except OSError as error:
        raise _private_path_error(path, 0o600, f"could not inspect it ({error})") from error
    else:
        _validate_private_posix_path(path, directory=False)
    for suffix in ("-wal", "-shm"):
        companion = Path(f"{path}{suffix}")
        if companion.exists() or companion.is_symlink():
            _validate_private_posix_path(companion, directory=False)


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
        "graph_entry_count",
        "graph_accumulator",
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
    if not path.exists() and not path.is_symlink():
        return False
    if os.name == "posix":
        _validate_private_posix_path(path.parent, directory=True)
        _validate_private_posix_path(path, directory=False)
        for suffix in ("-wal", "-shm"):
            companion = Path(f"{path}{suffix}")
            if companion.exists() or companion.is_symlink():
                _validate_private_posix_path(companion, directory=False)
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


def _sqlite_chunks(
    connection: sqlite3.Connection,
    values: set[str],
    *,
    reserved: int = 0,
    repetitions: int = 1,
) -> Iterator[tuple[str, ...]]:
    """Yield deterministic batches within this connection's host-parameter limit."""
    available = connection.getlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER) - reserved
    size = max(1, min(400, available // repetitions))
    yield from _chunks(values, size)


def _query_type_keys(query: GraphQuery) -> set[str]:
    return {
        *(key for group in query.anchor_groups for key in group.anchor_types),
        *(condition.associated_data_type for condition in query.data_conditions),
        *(required.link_type for required in query.required_links),
    }


def _merge_objects(
    first: Iterable[GraphObject], second: Iterable[GraphObject]
) -> tuple[GraphObject, ...]:
    """Combine disjoint bounded identity selections from one SQLite snapshot."""
    by_uuid = {value.uuid: value for value in first}
    by_uuid.update((value.uuid, value) for value in second)
    return tuple(by_uuid.values())


def _merge_definition_sets(
    first: GraphDefinitionSet, second: GraphDefinitionSet
) -> GraphDefinitionSet:
    """Combine disjoint normalized definition selections without broadening either."""
    return GraphDefinitionSet(
        (*first.anchor_types, *second.anchor_types),
        (*first.associated_data_types, *second.associated_data_types),
        (*first.link_types, *second.link_types),
        (*first.relationship_constraints, *second.relationship_constraints),
    )


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
        )
    )


class CanonicalStore:
    """One local canonical store: its ledger, its current projection, and their durability."""

    def __init__(self, path: Path) -> None:
        self._path = path
        _prepare_private_store_path(path)
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
            self._connection.create_function(
                "vellis_re2_full_match", 2, _stored_pattern_matches, deterministic=True
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
            if os.name == "posix":
                _validate_private_posix_path(path, directory=False)
                for suffix in ("-wal", "-shm"):
                    companion = Path(f"{path}{suffix}")
                    if companion.exists():
                        _validate_private_posix_path(companion, directory=False)
        except sqlite3.Error as error:
            self._connection.close()
            raise StoreError(f"could not open a canonical store at {path}: {error}") from error
        except BaseException:
            self._connection.close()
            raise

    @classmethod
    def _borrowed_connection(cls, connection: sqlite3.Connection) -> CanonicalStore:
        """Use the SQL conformance engine inside an owning transaction without closing it."""
        store = cls.__new__(cls)
        store._path = Path("<borrowed-transaction>")
        store._connection = connection
        store._lock = RLock()
        store._record_reads = 0
        store._activity_reads = 0
        store._current_projection_decodes = 0
        store._current_graph_decodes = 0
        store._current_graph_object_decodes = 0
        store._current_definition_decodes = 0
        return store

    # --- Lifecycle ------------------------------------------------------------------

    @property
    def path(self) -> Path:
        return self._path

    def close(self) -> None:
        """Fold the write-ahead log back into the store file, then let go of it.

        Committed state otherwise lives partly in a sidecar until SQLite decides to move
        it, and an owner who copies their memory file — the obvious way to keep a copy of
        something that matters — gets a coherent state from some earlier moment with
        nothing to indicate it is not today's. Checkpointing on the way out means a memory
        this process closed cleanly is wholly in the file it is named after. It cannot help
        a copy taken while the memory is open, which is a thing to say in the guidance
        rather than a thing to solve here.
        """
        # Release this connection before checkpointing. Several Vellis connections may
        # be ending together (the initialization race is a deliberate example); holding
        # this reader while waiting for theirs would make each close prevent the others.
        self._connection.close()
        try:
            with (
                _CHECKPOINT_LOCK,
                closing(sqlite3.connect(self._path, isolation_level=None)) as checkpoint_connection,
            ):
                checkpoint_connection.execute("PRAGMA busy_timeout = 1000")
                checkpoint = checkpoint_connection.execute(
                    "PRAGMA wal_checkpoint(TRUNCATE)"
                ).fetchone()
                if checkpoint is None or int(checkpoint[0]) != 0:
                    raise StoreError(
                        f"could not finish closing the canonical store at {self._path}: "
                        "another database reader prevented the write-ahead log checkpoint; "
                        "close that reader and open then close Vellis again before copying the file"
                    )
        except StoreError:
            raise
        except sqlite3.Error as error:
            raise StoreError(
                f"could not finish closing the canonical store at {self._path}: {error}"
            ) from error

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
                    result = self._evaluate_compiled_query_unlocked(query, definitions, revision)
                    self._clear_query_temporaries_unlocked()
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
                    result = self._evaluate_compiled_query_unlocked(
                        query, definitions, revision, historical_revision=revision
                    )
                    self._clear_query_temporaries_unlocked()
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
        from vellis.query import GraphQueryResult

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
                    result = self._evaluate_compiled_query_unlocked(
                        query,
                        definitions,
                        revision,
                        prospective=True,
                    )
                    self._clear_query_temporaries_unlocked()
                    self._connection.execute("COMMIT")
                    return result
                except BaseException:
                    self._rollback_quietly()
                    raise
        except sqlite3.Error as error:
            raise StoreError(f"could not query the proposal at {self._path}: {error}") from error

    def _populate_query_selector_members_unlocked(self, query: GraphQuery) -> None:
        from vellis.sqlite_query import selector_members

        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS query_selector_member ("
            " member_kind TEXT NOT NULL, selector_name TEXT NOT NULL, value TEXT NOT NULL,"
            " PRIMARY KEY (member_kind, selector_name, value)) WITHOUT ROWID"
        )
        self._connection.execute("DELETE FROM query_selector_member")
        self._connection.executemany(
            "INSERT INTO query_selector_member VALUES (?, ?, ?)",
            (
                (member.member_kind, member.selector_name, member.value)
                for member in selector_members(query)
            ),
        )

    def _clear_query_temporaries_unlocked(self) -> None:
        self._connection.execute("DROP TABLE IF EXISTS query_answer")
        present = self._connection.execute(
            "SELECT 1 FROM sqlite_temp_master WHERE name = 'query_selector_member'"
        ).fetchone()
        if present is not None:
            self._connection.execute("DELETE FROM query_selector_member")

    def _evaluate_compiled_query_unlocked(
        self,
        query: GraphQuery,
        definitions: GraphDefinitionSet,
        revision: int,
        *,
        historical_revision: int | None = None,
        prospective: bool = False,
    ) -> GraphQueryResult:
        """Evaluate one analyzed conjunction and hydrate only its bounded identities."""
        from vellis.query import (
            AggregateQueryOutput,
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
            RowQueryOutput,
            _unreturnable_reason,
            analyze_graph_query,
        )
        from vellis.sqlite_query import QueryRelations, compile_query, selector_members

        analysis, findings = analyze_graph_query(query, definitions)
        if findings:
            return GraphQueryResult(
                status=OperationStatus.REJECTED,
                summary=f"the query was not evaluated ({len(findings)} findings)",
                findings=findings,
                query=query,
            )
        assert analysis is not None

        if historical_revision is None:
            relations = QueryRelations(
                graph="prospective_graph_object" if prospective else "current_graph_object",
                association=("prospective_data_anchor" if prospective else "current_data_anchor"),
            )
        else:
            relations = QueryRelations(
                graph="selected_graph_object",
                association="selected_data_anchor",
                prefix=(
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
                ),
                prefix_parameters=(historical_revision, historical_revision),
            )
        compiled = compile_query(analysis, relations)
        maximum_length = self._connection.getlimit(sqlite3.SQLITE_LIMIT_LENGTH)
        oversized = next(
            (
                member
                for member in selector_members(query)
                if sum(
                    len(value.encode("utf-8"))
                    for value in (member.member_kind, member.selector_name, member.value)
                )
                > maximum_length
            ),
            None,
        )
        if oversized is not None:
            return GraphQueryResult(
                status=OperationStatus.REJECTED,
                summary="the complete query exceeds this SQLite realization's capacity",
                findings=(
                    ValidationFinding(
                        summary=(
                            f"selector '{oversized.selector_name}' carries a member larger than"
                            f" SQLite's {maximum_length}-byte value capacity"
                        )
                    ),
                ),
                query=query,
            )
        capacity = self._compiled_query_capacity_finding_unlocked(compiled)
        if capacity is not None:
            return GraphQueryResult(
                status=OperationStatus.REJECTED,
                summary="the complete query exceeds this SQLite realization's capacity",
                findings=(capacity,),
                query=query,
            )

        try:
            self._populate_query_selector_members_unlocked(query)
        except sqlite3.Error as error:
            if error.sqlite_errorcode != sqlite3.SQLITE_TOOBIG:
                raise
            return GraphQueryResult(
                status=OperationStatus.REJECTED,
                summary="the complete query exceeds this SQLite realization's capacity",
                findings=(ValidationFinding(summary="a selector-member row is too large"),),
                query=query,
            )
        preparation = self._prepare_compiled_statements_unlocked(
            (compiled.reset_answer, compiled.create_answer)
        )
        if preparation is not None:
            return GraphQueryResult(
                status=OperationStatus.REJECTED,
                summary="the complete query exceeds this SQLite realization's capacity",
                findings=(preparation,),
                query=query,
            )
        self._connection.execute(compiled.reset_answer.sql)
        self._connection.execute(compiled.create_answer.sql)
        preparation = self._prepare_compiled_statements_unlocked(
            (
                *(validation.statement for validation in compiled.uuid_validations),
                compiled.populate_answer,
                compiled.read_answer,
            )
        )
        if preparation is not None:
            return GraphQueryResult(
                status=OperationStatus.REJECTED,
                summary="the complete query exceeds this SQLite realization's capacity",
                findings=(preparation,),
                query=query,
            )
        for validation in compiled.uuid_validations:
            invalid = self._connection.execute(
                validation.statement.sql, validation.statement.parameters
            ).fetchall()
            if invalid:
                uuid = str(invalid[0][0])
                return GraphQueryResult(
                    status=OperationStatus.REJECTED,
                    summary="the query was not evaluated (invalid UUID restriction)",
                    findings=(
                        ValidationFinding(
                            summary=(
                                f"{validation.label} restricts unknown "
                                f"{validation.object_kind} UUID '{uuid}'"
                            )
                        ),
                    ),
                    query=query,
                )

        try:
            self._connection.execute(
                compiled.populate_answer.sql, compiled.populate_answer.parameters
            )
        except sqlite3.Error as error:
            if error.sqlite_errorcode != sqlite3.SQLITE_TOOBIG:
                raise
            return GraphQueryResult(
                status=OperationStatus.REJECTED,
                summary="the complete query exceeds this SQLite realization's capacity",
                findings=(ValidationFinding(summary="an answer-identity row is too large"),),
                query=query,
            )
        matched = int(self._connection.execute("SELECT count(*) FROM query_answer").fetchone()[0])
        if matched > compiled.bound:
            noun = "rows" if compiled.bound_kind == "rows" else "matches"
            return GraphQueryResult(
                status=OperationStatus.REJECTED,
                summary=(
                    f"the result has more than {compiled.bound} {noun}; it is refused whole"
                    " rather than truncated"
                ),
                findings=(
                    ValidationFinding(
                        summary=f"the complete result exceeds the maximum of {compiled.bound}"
                    ),
                ),
                query=query,
            )

        if isinstance(query.output, AggregateQueryOutput):
            aggregates = self._aggregate_compiled_answer_unlocked(query, definitions, matched)
            if isinstance(aggregates, ValidationFinding):
                return GraphQueryResult(
                    status=OperationStatus.REJECTED,
                    summary="the complete aggregate could not be returned, so none of it was",
                    findings=(aggregates,),
                    query=query,
                )
            return GraphQueryResult(
                status=OperationStatus.ACCEPTED,
                summary=f"{len(aggregates)} aggregates at revision {revision}",
                query=query,
                evaluated_revision=revision,
                aggregates=aggregates,
            )

        assert isinstance(query.output, RowQueryOutput)
        rows: list[GraphQueryRow] = []
        for raw in self._connection.execute(
            compiled.read_answer.sql, compiled.read_answer.parameters
        ):
            anchors: list[AnchorBinding] = []
            links: list[LinkBinding] = []
            data: list[AssociatedDataBinding] = []
            properties: list[ReturnedProperty] = []
            for projection, stored_id in zip(query.output.projections, raw, strict=True):
                object_value_id = int(stored_id)
                if isinstance(projection, DataPropertyProjection):
                    source = self._connection.execute(
                        "SELECT uuid FROM object_value WHERE id = ?", (object_value_id,)
                    ).fetchone()
                    assert source is not None
                    stored = self._connection.execute(
                        "SELECT json_kind, boolean_value, number_value, text_value"
                        " FROM object_property WHERE object_value_id = ? AND name = ? LIMIT 1",
                        (object_value_id, projection.property_name),
                    ).fetchone()
                    properties.append(
                        ReturnedProperty(
                            projection=projection.name,
                            associated_data_uuid=str(source[0]),
                            present=stored is not None,
                            value=(None if stored is None else json_storage_value(*stored)),
                        )
                    )
                    continue
                value = self._load_object_value(object_value_id)
                self._current_graph_object_decodes += 1
                if isinstance(projection, AnchorProjection):
                    assert isinstance(value, Anchor)
                    anchors.append(AnchorBinding(projection.name, value))
                elif isinstance(projection, LinkProjection):
                    assert isinstance(value, Link)
                    links.append(LinkBinding(projection.name, value))
                else:
                    assert isinstance(projection, AssociatedDataProjection)
                    assert isinstance(value, AssociatedDataObject)
                    data.append(AssociatedDataBinding(projection.name, value))
            rows.append(GraphQueryRow(tuple(anchors), tuple(links), tuple(data), tuple(properties)))
        returned = tuple(rows)
        unreturnable = _unreturnable_reason(returned)
        if unreturnable is not None:
            return GraphQueryResult(
                status=OperationStatus.REJECTED,
                summary="the complete result could not be returned, so none of it was",
                findings=(ValidationFinding(summary=unreturnable),),
                query=query,
            )
        return GraphQueryResult(
            status=OperationStatus.ACCEPTED,
            summary=f"{len(returned)} rows at revision {revision}",
            query=query,
            evaluated_revision=revision,
            rows=returned,
        )

    def _compiled_query_capacity_finding_unlocked(self, compiled) -> ValidationFinding | None:
        """Compare exact compiled artifacts with directly inspectable SQLite limits."""
        limits = {
            "SQL bytes": self._connection.getlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH),
            "parameters": self._connection.getlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER),
            "columns": self._connection.getlimit(sqlite3.SQLITE_LIMIT_COLUMN),
            "expression depth": self._connection.getlimit(sqlite3.SQLITE_LIMIT_EXPR_DEPTH),
            "function arguments": self._connection.getlimit(sqlite3.SQLITE_LIMIT_FUNCTION_ARG),
        }
        for statement in compiled.statements:
            checks = (
                (statement.utf8_bytes, limits["SQL bytes"], "SQL bytes"),
                (statement.parameter_count, limits["parameters"], "parameters"),
                (statement.selected_columns, limits["columns"], "columns"),
                (statement.maximum_tables_in_select, 64, "tables in one SELECT"),
                (
                    statement.maximum_function_arguments,
                    limits["function arguments"],
                    "arguments to one SQL function",
                ),
            )
            if limits["expression depth"] > 0:
                checks = (
                    *checks,
                    (
                        statement.expression_depth,
                        limits["expression depth"],
                        "expression depth",
                    ),
                )
            for required, available, resource in checks:
                if required > available:
                    return ValidationFinding(
                        summary=(
                            f"the compiled query requires {required} {resource}, but this"
                            f" SQLite connection permits {available}"
                        )
                    )
            for parameter in statement.parameters:
                if isinstance(parameter, str) and len(parameter.encode("utf-8")) > (
                    self._connection.getlimit(sqlite3.SQLITE_LIMIT_LENGTH)
                ):
                    return ValidationFinding(
                        summary=(
                            "the compiled query contains a bound value larger than SQLite permits"
                        )
                    )
        if compiled.bound >= _MAXIMUM_SQLITE_INTEGER:
            return ValidationFinding(
                summary="the query bound plus its refusal sentinel exceeds SQLite's integer range"
            )
        return None

    def _prepare_compiled_statements_unlocked(self, statements) -> ValidationFinding | None:
        """Prepare generated statements without stepping an answer row."""
        for statement in statements:
            try:
                self._connection.execute("EXPLAIN " + statement.sql, statement.parameters)
            except sqlite3.Error as error:
                message = str(error).lower()
                if "recursion limit" in message:
                    try:
                        prior = self._connection.setlimit(12, 2_147_483_647)
                    except sqlite3.Error:
                        raise
                    try:
                        self._connection.execute("EXPLAIN " + statement.sql, statement.parameters)
                    except sqlite3.Error as retry_error:
                        raise StoreError(
                            "SQLite could not prepare the compiled query"
                        ) from retry_error
                    finally:
                        self._connection.setlimit(12, prior)
                    return ValidationFinding(
                        summary=(
                            "the compiled query exceeds this SQLite connection's parser-depth"
                            " capacity"
                        )
                    )
                capacity_markers = (
                    "too many sql variables",
                    "at most 64 tables",
                    "expression tree is too large",
                    "too many columns",
                    "statement too long",
                    "too many arguments",
                )
                if not any(marker in message for marker in capacity_markers):
                    raise
                return ValidationFinding(
                    summary=f"SQLite could not prepare the compiled query: {error}"
                )
            except MemoryError:
                # SQLite reports a deliberately lowered VDBE-operation limit as a bare
                # allocation failure. Retry only the preparation with the connection's
                # compiled maximum: success proves structural excess; another failure is
                # an actual allocation problem and remains a store failure.
                category = sqlite3.SQLITE_LIMIT_VDBE_OP
                prior = self._connection.setlimit(category, 2_147_483_647)
                try:
                    self._connection.execute("EXPLAIN " + statement.sql, statement.parameters)
                except (MemoryError, sqlite3.Error) as retry_error:
                    raise StoreError(
                        "SQLite could not allocate the compiled query plan"
                    ) from retry_error
                finally:
                    self._connection.setlimit(category, prior)
                return ValidationFinding(
                    summary=(
                        "the compiled query exceeds this SQLite connection's virtual-machine"
                        " operation capacity"
                    )
                )
        return None

    def definition_summary_rows(
        self, *, prospective: bool = False, revision: int | None = None
    ) -> tuple[int, tuple[tuple[str, str | None], ...], bool]:
        """Return the shallow anchor vocabulary without constructing a definition set."""
        try:
            with self.read_snapshot():
                evaluated, active_identity, delta_present = (
                    self._definition_selection_context_unlocked(
                        prospective=prospective, revision=revision
                    )
                )
                active_rows = (
                    "SELECT t.type_key, t.description"
                    " FROM current_definition_type_source AS s"
                    " JOIN definition_type AS t ON t.definition_set_id = s.value_set_id"
                    " AND t.type_key = s.type_key WHERE t.object_kind = 'anchor'"
                )
                if revision is not None:
                    sources = self._definition_source_map_unlocked(
                        active_identity, relationship=False
                    )
                    historical_rows: list[tuple[str, str | None]] = []
                    for key, source in sources.items():
                        row = self._connection.execute(
                            "SELECT description FROM definition_type"
                            " WHERE definition_set_id = ? AND type_key = ?"
                            " AND object_kind = 'anchor'",
                            (source, key),
                        ).fetchone()
                        if row is not None:
                            historical_rows.append((key, None if row[0] is None else str(row[0])))
                    return evaluated, tuple(sorted(historical_rows)), delta_present
                if not prospective:
                    rows = self._connection.execute(active_rows + " ORDER BY t.type_key")
                else:
                    rows = self._connection.execute(
                        "SELECT q.type_key, q.description FROM ("
                        + active_rows
                        + ") AS q WHERE NOT EXISTS"
                        " (SELECT 1 FROM proposal_definition_type AS p"
                        " WHERE p.type_key = q.type_key)"
                        " UNION ALL SELECT t.type_key, t.description"
                        " FROM proposal_definition_type AS p JOIN definition_type AS t"
                        " ON t.definition_set_id = p.value_set_id"
                        " WHERE p.operation = 'upsert' AND t.object_kind = 'anchor'"
                        " ORDER BY 1",
                        (),
                    )
                return (
                    evaluated,
                    tuple(
                        (str(key), None if description is None else str(description))
                        for key, description in rows
                    ),
                    delta_present,
                )
        except sqlite3.Error as error:
            raise StoreError(f"could not read from the store at {self._path}: {error}") from error

    def _definition_source_map_unlocked(
        self, identity: str, *, relationship: bool
    ) -> dict[str, str]:
        """Resolve keyed membership for complete-output and complete-scope operations."""
        chain: list[str] = []
        base = identity
        while True:
            row = self._connection.execute(
                "SELECT base_definition_set_id FROM definition_set_overlay"
                " WHERE definition_set_id = ?",
                (base,),
            ).fetchone()
            if row is None:
                break
            chain.append(base)
            base = str(row[0])
        if relationship:
            sources = {
                str(key): str(source)
                for key, source in self._connection.execute(
                    "SELECT natural_key, definition_set_id"
                    " FROM definition_multiplicity_rule WHERE definition_set_id = ?",
                    (base,),
                )
            }
            table, key_column = "definition_set_relationship_override", "natural_key"
        else:
            sources = {
                str(key): str(source)
                for key, source in self._connection.execute(
                    "SELECT type_key, definition_set_id FROM definition_type"
                    " WHERE definition_set_id = ?",
                    (base,),
                )
            }
            table, key_column = "definition_set_type_override", "type_key"
        for overlay in reversed(chain):
            for key, operation, value_set_id in self._connection.execute(
                f"SELECT {key_column}, operation, value_set_id FROM {table}"  # noqa: S608
                " WHERE definition_set_id = ?",
                (overlay,),
            ):
                text_key = str(key)
                if operation == "delete":
                    sources.pop(text_key, None)
                else:
                    sources[text_key] = str(value_set_id)
        return sources

    def _definition_entry_source_unlocked(
        self,
        base: str,
        chain: list[str],
        relationship: bool,
        key: str,
    ) -> str | None:
        """Resolve one natural key through a sparse newest-to-oldest overlay chain."""
        table, key_column = (
            ("definition_set_relationship_override", "natural_key")
            if relationship
            else ("definition_set_type_override", "type_key")
        )
        for overlay in chain:
            row = self._connection.execute(
                f"SELECT operation, value_set_id FROM {table}"  # noqa: S608
                f" WHERE definition_set_id = ? AND {key_column} = ?",  # noqa: S608
                (overlay, key),
            ).fetchone()
            if row is not None:
                return None if row[0] == "delete" else str(row[1])
        physical_table = "definition_multiplicity_rule" if relationship else "definition_type"
        physical_key = "natural_key" if relationship else "type_key"
        row = self._connection.execute(
            f"SELECT definition_set_id FROM {physical_table}"  # noqa: S608
            f" WHERE definition_set_id = ? AND {physical_key} = ? LIMIT 1",  # noqa: S608
            (base, key),
        ).fetchone()
        return None if row is None else str(row[0])

    def definition_neighborhood(
        self,
        type_keys: tuple[str, ...],
        *,
        prospective: bool = False,
        revision: int | None = None,
    ) -> tuple[int, GraphDefinitionSet, bool]:
        """Load the indexed transitive definition frontier for selected types."""
        try:
            with self.read_snapshot():
                evaluated, active_identity, delta_present = (
                    self._definition_selection_context_unlocked(
                        prospective=prospective, revision=revision
                    )
                )
                type_sources: dict[str, str] = {}
                relationship_sources: dict[str, str] = {}
                absent_types: set[str] = set()
                absent_relationships: set[str] = set()
                historical_chain: list[str] = []
                historical_base = active_identity
                if revision is not None:
                    while True:
                        row = self._connection.execute(
                            "SELECT base_definition_set_id FROM definition_set_overlay"
                            " WHERE definition_set_id = ?",
                            (historical_base,),
                        ).fetchone()
                        if row is None:
                            break
                        historical_chain.append(historical_base)
                        historical_base = str(row[0])

                def placeholders(values: set[str]) -> str:
                    return ", ".join("?" for _ in values)

                def parameter_chunks(
                    values: set[str], *, reserved: int = 0, repetitions: int = 1
                ) -> Iterator[tuple[str, ...]]:
                    yield from _sqlite_chunks(
                        self._connection,
                        values,
                        reserved=reserved,
                        repetitions=repetitions,
                    )

                def resolve_types(keys: set[str]) -> None:
                    unresolved = keys - type_sources.keys() - absent_types
                    if not unresolved:
                        return
                    edited: set[str] = set()
                    if prospective:
                        for chunk in parameter_chunks(unresolved):
                            sql = (
                                "SELECT type_key, operation, value_set_id"
                                " FROM proposal_definition_type WHERE type_key IN ("
                                + placeholders(set(chunk))
                                + ")"
                            )
                            for key, operation, value_set_id in self._connection.execute(
                                sql, chunk
                            ):
                                text_key = str(key)
                                edited.add(text_key)
                                if operation == "upsert":
                                    type_sources[text_key] = str(value_set_id)
                                else:
                                    absent_types.add(text_key)
                    active_keys = unresolved - edited
                    if active_keys:
                        if revision is None:
                            found_rows = tuple(
                                row
                                for chunk in parameter_chunks(active_keys)
                                for row in self._connection.execute(
                                    "SELECT type_key, value_set_id"
                                    " FROM current_definition_type_source WHERE type_key IN ("
                                    + placeholders(set(chunk))
                                    + ")",
                                    chunk,
                                )
                            )
                        else:
                            found_rows = tuple(
                                (key, source)
                                for key in active_keys
                                if (
                                    source := self._definition_entry_source_unlocked(
                                        historical_base, historical_chain, False, key
                                    )
                                )
                                is not None
                            )
                        found = {str(row[0]) for row in found_rows}
                        type_sources.update((str(key), str(source)) for key, source in found_rows)
                        absent_types.update(active_keys - found)

                def resolve_relationships(keys: set[str]) -> None:
                    unresolved = keys - relationship_sources.keys() - absent_relationships
                    if not unresolved:
                        return
                    edited: set[str] = set()
                    if prospective:
                        for chunk in parameter_chunks(unresolved):
                            sql = (
                                "SELECT natural_key, operation, value_set_id"
                                " FROM proposal_definition_relationship WHERE natural_key IN ("
                                + placeholders(set(chunk))
                                + ")"
                            )
                            for key, operation, value_set_id in self._connection.execute(
                                sql, chunk
                            ):
                                text_key = str(key)
                                edited.add(text_key)
                                if operation == "upsert":
                                    relationship_sources[text_key] = str(value_set_id)
                                else:
                                    absent_relationships.add(text_key)
                    active_keys = unresolved - edited
                    if active_keys:
                        if revision is None:
                            found_rows = tuple(
                                row
                                for chunk in parameter_chunks(active_keys)
                                for row in self._connection.execute(
                                    "SELECT natural_key, value_set_id"
                                    " FROM current_definition_relationship_source"
                                    " WHERE natural_key IN (" + placeholders(set(chunk)) + ")",
                                    chunk,
                                )
                            )
                        else:
                            found_rows = tuple(
                                (key, source)
                                for key in active_keys
                                if (
                                    source := self._definition_entry_source_unlocked(
                                        historical_base, historical_chain, True, key
                                    )
                                )
                                is not None
                            )
                        found = {str(row[0]) for row in found_rows}
                        relationship_sources.update(
                            (str(key), str(source)) for key, source in found_rows
                        )
                        absent_relationships.update(active_keys - found)

                wanted_types = set(type_keys)
                wanted_relationships: set[str] = set()
                pending_types = set(type_keys)
                pending_relationships: set[str] = set()

                def want_types(values: Iterable[str]) -> None:
                    for value in values:
                        if value not in wanted_types:
                            wanted_types.add(value)
                            pending_types.add(value)

                def want_relationships(values: Iterable[str]) -> None:
                    for value in values:
                        if value not in wanted_relationships:
                            wanted_relationships.add(value)
                            pending_relationships.add(value)

                def historical_reverse_types(selected: set[str]) -> set[str]:
                    candidates: set[tuple[str, str]] = set()
                    for source in (historical_base, *historical_chain):
                        for chunk in parameter_chunks(selected, reserved=1):
                            marks = placeholders(set(chunk))
                            for sql in (
                                "SELECT t.type_key, t.definition_set_id"
                                " FROM definition_anchor_permission AS p"
                                " INDEXED BY definition_anchor_permission_by_type"
                                " JOIN definition_type AS t"
                                " ON t.definition_set_id = p.definition_set_id"
                                " AND t.occurrence = p.type_occurrence"
                                " WHERE p.definition_set_id = ? AND p.anchor_type_key IN ("
                                + marks
                                + ")",
                                "SELECT t.type_key, t.definition_set_id"
                                " FROM definition_endpoint_permission AS p"
                                " INDEXED BY definition_endpoint_permission_by_type"
                                " JOIN definition_type AS t"
                                " ON t.definition_set_id = p.definition_set_id"
                                " AND t.occurrence = p.type_occurrence"
                                " WHERE p.definition_set_id = ? AND p.type_key IN (" + marks + ")",
                            ):
                                candidates.update(
                                    (str(key), str(value_source))
                                    for key, value_source in self._connection.execute(
                                        sql, (source, *chunk)
                                    )
                                )
                    return {
                        key
                        for key, source in candidates
                        if self._definition_entry_source_unlocked(
                            historical_base, historical_chain, False, key
                        )
                        == source
                    }

                def historical_reverse_relationships(selected: set[str]) -> set[str]:
                    candidates: set[tuple[str, str]] = set()
                    for source in (historical_base, *historical_chain):
                        for chunk in parameter_chunks(selected, reserved=1):
                            candidates.update(
                                (str(key), str(value_source))
                                for key, value_source in self._connection.execute(
                                    "SELECT r.natural_key, r.definition_set_id"
                                    " FROM definition_multiplicity_participant AS p"
                                    " INDEXED BY definition_multiplicity_participant_by_type"
                                    " JOIN definition_multiplicity_rule AS r"
                                    " ON r.definition_set_id = p.definition_set_id"
                                    " AND r.occurrence = p.rule_occurrence"
                                    " WHERE p.definition_set_id = ? AND p.type_key IN ("
                                    + placeholders(set(chunk))
                                    + ")",
                                    (source, *chunk),
                                )
                            )
                    return {
                        key
                        for key, source in candidates
                        if self._definition_entry_source_unlocked(
                            historical_base, historical_chain, True, key
                        )
                        == source
                    }

                resolve_types(wanted_types)
                while True:
                    resolve_types(pending_types)
                    resolve_relationships(pending_relationships)
                    selected = pending_types - absent_types
                    relationship_frontier = pending_relationships - absent_relationships
                    pending_types = set()
                    pending_relationships = set()
                    if not selected and not relationship_frontier:
                        break
                    if selected:
                        if revision is not None:
                            want_types(historical_reverse_types(selected))
                            want_relationships(historical_reverse_relationships(selected))
                        active_type_filter = (
                            ""
                            if not prospective
                            else " AND NOT EXISTS (SELECT 1"
                            " FROM proposal_definition_type AS e"
                            " WHERE e.type_key = t.type_key)"
                        )
                        active_relationship_filter = (
                            ""
                            if not prospective
                            else " AND NOT EXISTS (SELECT 1 FROM"
                            " proposal_definition_relationship AS e"
                            " WHERE e.natural_key = r.natural_key)"
                        )
                        if revision is None:
                            for chunk in parameter_chunks(selected):
                                selected_sql = placeholders(set(chunk))
                                current_reverse_queries = (
                                    "SELECT DISTINCT t.type_key"
                                    " FROM current_definition_type_source AS s"
                                    " JOIN definition_anchor_permission AS p"
                                    " INDEXED BY definition_anchor_permission_by_type"
                                    " ON p.definition_set_id = s.value_set_id"
                                    " JOIN definition_type AS t"
                                    " ON t.definition_set_id = p.definition_set_id"
                                    " AND t.occurrence = p.type_occurrence"
                                    " AND t.type_key = s.type_key"
                                    " WHERE p.anchor_type_key IN ("
                                    + selected_sql
                                    + ")"
                                    + active_type_filter,
                                    "SELECT DISTINCT t.type_key"
                                    " FROM current_definition_type_source AS s"
                                    " JOIN definition_endpoint_permission AS p"
                                    " INDEXED BY definition_endpoint_permission_by_type"
                                    " ON p.definition_set_id = s.value_set_id"
                                    " JOIN definition_type AS t"
                                    " ON t.definition_set_id = p.definition_set_id"
                                    " AND t.occurrence = p.type_occurrence"
                                    " AND t.type_key = s.type_key"
                                    " WHERE p.type_key IN ("
                                    + selected_sql
                                    + ")"
                                    + active_type_filter,
                                )
                                for sql in current_reverse_queries:
                                    want_types(
                                        str(row[0]) for row in self._connection.execute(sql, chunk)
                                    )
                        if revision is None:
                            for chunk in parameter_chunks(selected):
                                want_relationships(
                                    str(row[0])
                                    for row in self._connection.execute(
                                        "SELECT DISTINCT r.natural_key"
                                        " FROM current_definition_relationship_source AS s"
                                        " JOIN definition_multiplicity_participant AS p"
                                        " INDEXED BY definition_multiplicity_participant_by_type"
                                        " ON p.definition_set_id = s.value_set_id"
                                        " JOIN definition_multiplicity_rule AS r"
                                        " ON r.definition_set_id = p.definition_set_id"
                                        " AND r.occurrence = p.rule_occurrence"
                                        " AND r.natural_key = s.natural_key"
                                        " WHERE p.type_key IN ("
                                        + placeholders(set(chunk))
                                        + ")"
                                        + active_relationship_filter,
                                        chunk,
                                    )
                                )
                        if prospective:
                            for chunk in parameter_chunks(selected, repetitions=2):
                                selected_sql = placeholders(set(chunk))
                                for key, value_set_id in self._connection.execute(
                                    "SELECT e.type_key, e.value_set_id"
                                    " FROM proposal_definition_type AS e"
                                    " JOIN definition_type AS t"
                                    " ON t.definition_set_id = e.value_set_id"
                                    " JOIN definition_anchor_permission AS p"
                                    " ON p.definition_set_id = t.definition_set_id"
                                    " AND p.type_occurrence = t.occurrence"
                                    " WHERE e.operation = 'upsert'"
                                    " AND p.anchor_type_key IN ("
                                    + selected_sql
                                    + ") UNION SELECT e.type_key, e.value_set_id"
                                    " FROM proposal_definition_type AS e"
                                    " JOIN definition_type AS t"
                                    " ON t.definition_set_id = e.value_set_id"
                                    " JOIN definition_endpoint_permission AS p"
                                    " ON p.definition_set_id = t.definition_set_id"
                                    " AND p.type_occurrence = t.occurrence"
                                    " WHERE e.operation = 'upsert' AND p.type_key IN ("
                                    + selected_sql
                                    + ")",
                                    (*chunk, *chunk),
                                ):
                                    want_types((str(key),))
                                    type_sources[str(key)] = str(value_set_id)
                            for chunk in parameter_chunks(selected):
                                for key, value_set_id in self._connection.execute(
                                    "SELECT e.natural_key, e.value_set_id"
                                    " FROM proposal_definition_relationship AS e"
                                    " JOIN definition_multiplicity_rule AS r"
                                    " ON r.definition_set_id = e.value_set_id"
                                    " JOIN definition_multiplicity_participant AS p"
                                    " ON p.definition_set_id = r.definition_set_id"
                                    " AND p.rule_occurrence = r.occurrence"
                                    " WHERE e.operation = 'upsert' AND p.type_key IN ("
                                    + placeholders(set(chunk))
                                    + ")",
                                    chunk,
                                ):
                                    want_relationships((str(key),))
                                    relationship_sources[str(key)] = str(value_set_id)
                    resolve_relationships(wanted_relationships)
                    for key in selected:
                        source = type_sources.get(key)
                        if source is None:
                            continue
                        row = self._connection.execute(
                            "SELECT occurrence, object_kind FROM definition_type"
                            " WHERE definition_set_id = ? AND type_key = ? LIMIT 1",
                            (source, key),
                        ).fetchone()
                        if row is None or str(row[1]) != ObjectKind.LINK.value:
                            continue
                        want_types(
                            str(value[0])
                            for value in self._connection.execute(
                                "SELECT type_key FROM definition_endpoint_permission"
                                " WHERE definition_set_id = ? AND type_occurrence = ?",
                                (source, int(row[0])),
                            )
                        )
                    for key in relationship_frontier:
                        source = relationship_sources.get(key)
                        if source is None:
                            continue
                        row = self._connection.execute(
                            "SELECT occurrence, link_type_key FROM definition_multiplicity_rule"
                            " WHERE definition_set_id = ? AND natural_key = ? LIMIT 1",
                            (source, key),
                        ).fetchone()
                        if row is None:
                            continue
                        if row[1] is not None:
                            want_types((str(row[1]),))
                        want_types(
                            str(value[0])
                            for value in self._connection.execute(
                                "SELECT type_key FROM definition_multiplicity_participant"
                                " WHERE definition_set_id = ? AND rule_occurrence = ?",
                                (source, int(row[0])),
                            )
                        )

                definitions = GraphDefinitionSet()
                for source in sorted(set(type_sources.values())):
                    keys = {key for key, value in type_sources.items() if value == source}
                    for chunk in parameter_chunks(keys):
                        definitions = _merge_definition_sets(
                            definitions,
                            self._load_definition_set(
                                source, type_keys=set(chunk), relationship_keys=set()
                            ),
                        )
                for source in sorted(set(relationship_sources.values())):
                    keys = {key for key, value in relationship_sources.items() if value == source}
                    for chunk in parameter_chunks(keys):
                        definitions = _merge_definition_sets(
                            definitions,
                            self._load_definition_set(
                                source, type_keys=set(), relationship_keys=set(chunk)
                            ),
                        )
                return evaluated, definitions, delta_present
        except sqlite3.Error as error:
            raise StoreError(f"could not read from the store at {self._path}: {error}") from error

    def _definition_selection_context_unlocked(
        self, *, prospective: bool, revision: int | None
    ) -> tuple[int, str, bool]:
        if prospective and revision is not None:
            raise StoreError("prospective definition selection cannot be historical")
        if revision is None:
            row = self._connection.execute(
                "SELECT revision, established_by, active_definition_set_id,"
                " proposed_definition_set_id FROM state_head WHERE id = 0"
            ).fetchone()
            if not isinstance(row, tuple):
                raise NotInitializedError("no canonical state is established")
            evaluated = _projection_revision(row)
            delta_present = row[3] is not None
            if prospective and not delta_present:
                raise StoreError("no definition delta is present")
            return evaluated, str(row[2]), delta_present
        active = self._connection.execute(
            "SELECT active_definition_set_id FROM canonical_definition_event"
            " WHERE established_revision <= ? AND active_definition_set_id IS NOT NULL"
            " ORDER BY established_revision DESC LIMIT 1",
            (revision,),
        ).fetchone()
        delta = self._connection.execute(
            "SELECT delta_disposition FROM canonical_definition_event"
            " WHERE established_revision <= ? AND delta_disposition != 'unchanged'"
            " ORDER BY established_revision DESC LIMIT 1",
            (revision,),
        ).fetchone()
        if active is None:
            raise StoreError(f"revision {revision} has no active definition meaning")
        return revision, str(active[0]), delta is not None and delta[0] == "present"

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
        if type_keys is None:
            type_rows = self._connection.execute(
                "SELECT type_key, operation, value_set_id FROM proposal_definition_type"
            )
        else:
            type_rows = (
                row
                for chunk in _sqlite_chunks(self._connection, type_keys)
                for row in self._connection.execute(
                    "SELECT type_key, operation, value_set_id"
                    " FROM proposal_definition_type WHERE type_key IN ("
                    + ", ".join("?" for _ in chunk)
                    + ")",
                    chunk,
                )
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
            relationship_rows: Iterable[tuple[object, ...]] = (
                row
                for chunk in _sqlite_chunks(self._connection, relationship_keys)
                for row in self._connection.execute(
                    relationship_sql
                    + " WHERE natural_key IN ("
                    + ", ".join("?" for _ in chunk)
                    + ")",
                    chunk,
                )
            )
        elif constrained_type_keys is not None:
            if not constrained_type_keys:
                relationship_rows = ()
            else:
                relationship_rows = (
                    row
                    for chunk in _sqlite_chunks(
                        self._connection,
                        constrained_type_keys,
                        reserved=1,
                        repetitions=2,
                    )
                    for row in self._connection.execute(
                        relationship_sql + " AS e WHERE (e.operation = 'upsert' AND EXISTS ("
                        " SELECT 1 FROM definition_multiplicity_rule AS r"
                        " JOIN definition_multiplicity_participant AS p"
                        " ON p.definition_set_id = r.definition_set_id"
                        " AND p.rule_occurrence = r.occurrence AND p.role = 'first'"
                        " WHERE r.definition_set_id = e.value_set_id AND p.type_key IN ("
                        + ", ".join("?" for _ in chunk)
                        + "))) OR (e.operation = 'delete' AND EXISTS ("
                        " SELECT 1 FROM definition_multiplicity_rule AS r"
                        " JOIN definition_multiplicity_participant AS p"
                        " ON p.definition_set_id = r.definition_set_id"
                        " AND p.rule_occurrence = r.occurrence AND p.role = 'first'"
                        " WHERE r.definition_set_id = ? AND r.natural_key = e.natural_key"
                        " AND p.type_key IN (" + ", ".join("?" for _ in chunk) + ")))",
                        (*chunk, active_identity, *chunk),
                    )
                )
        else:
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
                        value_set_id = insert_definition_entry(self._connection, single)
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
                        value_set_id = insert_definition_entry(self._connection, single)
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

    def proposal_state(self) -> ProposalState:
        """Return bounded identities, counts, and exact current assessment for the delta."""
        try:
            with self.read_snapshot():
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
            " prior_record_identity, content_identity) VALUES (?, ("
            + NEXT_ORDINAL_SQL
            + "), ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                content,
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
        self._seal_record_identity_unlocked(resulting_revision)

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
        remaining_findings = max(0, count - start_ordinal + 1)
        sql_limit = min(maximum_findings, remaining_findings)
        finding_rows = self._connection.execute(
            "SELECT ordinal, summary FROM validation_finding"
            " WHERE assessment_id = ? AND ordinal >= ? ORDER BY ordinal LIMIT ?",
            (assessment_id, start_ordinal, sql_limit),
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
        self,
        scope: ValidationScope,
        *,
        maximum_findings: int,
        provenance: Provenance,
        observation_scope: str,
    ) -> ValidationReport:
        """Atomically publish a complete assessment and its required observation."""
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
                self._append_activity_unlocked(
                    ActivityRecord(
                        capability="check",
                        outcome_category=report.status,
                        semantic_scope=observation_scope,
                        summary=report.summary,
                        provenance=provenance,
                        recorded_at=now(),
                        evaluated_revision=report.evaluated_revision,
                    )
                )
                self._connection.execute("COMMIT")
                return report
            except ActivityAppendError:
                self._rollback_quietly()
                raise
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
        yield from self._iter_local_object_findings_unlocked(
            relation, object_relation, active_identity
        )
        yield from self._iter_multiplicity_findings_unlocked(relation, active_identity)

    def _iter_local_object_findings_unlocked(
        self, relation: str, object_relation: str, active_identity: str
    ) -> Iterator[ValidationFinding]:
        """Validate each object from normalized rows without assembling its neighborhood."""
        rows = self._connection.execute(
            f"SELECT uuid, object_value_id, object_kind, type_key, source_uuid, target_uuid"
            f" FROM {object_relation}"  # noqa: S608
            + (
                " WHERE uuid IN (SELECT uuid FROM assessment_validation_uuid)"
                if relation == "prospective_graph_object"
                else ""
            )
            + " ORDER BY type_key, uuid"
        )
        cached_type_key: str | None = None
        cached_definitions = GraphDefinitionSet()
        cached_property_constraints: dict[str, _PreparedPropertyConstraint] = {}
        for uuid_value, value_id, kind_value, type_key_value, source, target in rows:
            uuid = str(uuid_value)
            kind = ObjectKind(str(kind_value))
            type_key = str(type_key_value)
            if type_key != cached_type_key:
                cached_definitions = self._definitions_for_relation_unlocked(
                    relation,
                    active_identity,
                    type_keys={type_key},
                    constrained_type_keys=set(),
                    relationship_keys=set(),
                )
                cached_type_key = type_key
                data_definition = cached_definitions.associated_data_type(type_key)
                cached_property_constraints = (
                    {}
                    if data_definition is None
                    else {
                        constraint.property_name: _prepare_property_constraint(constraint)
                        for constraint in data_definition.property_constraints
                    }
                )
            definitions = cached_definitions
            resolved = {
                ObjectKind.ANCHOR: definitions.anchor_type(type_key) is not None,
                ObjectKind.ASSOCIATED_DATA: definitions.associated_data_type(type_key) is not None,
                ObjectKind.LINK: definitions.link_type(type_key) is not None,
            }
            if not resolved[kind]:
                other = next((each for each, present in resolved.items() if present), None)
                detail = (
                    f", which is active as a {other.value} type; a type key never changes an "
                    "object's kind"
                    if other is not None
                    else f", which resolves to no active {kind.value} type definition"
                )
                yield ValidationFinding(
                    summary=f"{kind.value} {uuid!r} uses type key {type_key!r}{detail}",
                    implicated_objects=(uuid,),
                )
                continue
            if kind is ObjectKind.ANCHOR:
                display_name = self._connection.execute(
                    "SELECT display_name FROM object_value WHERE id = ?", (value_id,)
                ).fetchone()[0]
                if not display_name:
                    yield ValidationFinding(
                        summary=f"anchor {uuid!r} has an empty display name",
                        implicated_objects=(uuid,),
                    )
                continue
            if kind is ObjectKind.LINK:
                definition = definitions.link_type(type_key)
                assert definition is not None
                endpoints = definition.endpoint_constraint
                for role, endpoint_uuid, permitted in (
                    ("source", str(source), endpoints.permitted_source_type_keys),
                    ("target", str(target), endpoints.permitted_target_type_keys),
                ):
                    endpoint = self._connection.execute(
                        f"SELECT object_kind, type_key FROM {object_relation} WHERE uuid = ?",  # noqa: S608
                        (endpoint_uuid,),
                    ).fetchone()
                    if endpoint is None or str(endpoint[0]) not in {
                        ObjectKind.ANCHOR.value,
                        ObjectKind.ASSOCIATED_DATA.value,
                    }:
                        detail = (
                            "a link, which is never an endpoint"
                            if endpoint is not None
                            else "no anchor or associated data owned by this graph"
                        )
                        yield ValidationFinding(
                            summary=(
                                f"link {uuid!r} {role} {endpoint_uuid!r} resolves to {detail}"
                            ),
                            implicated_objects=(uuid, endpoint_uuid),
                        )
                    elif str(endpoint[1]) not in permitted:
                        yield ValidationFinding(
                            summary=(
                                f"link {uuid!r} of type {type_key!r} has {role} type "
                                f"{endpoint[1]!r}, which its endpoint constraint does not permit"
                            ),
                            implicated_definitions=(f"endpointConstraint:{type_key}",),
                            implicated_objects=(uuid, endpoint_uuid),
                        )
                continue

            definition = definitions.associated_data_type(type_key)
            assert definition is not None
            association_count = int(
                self._connection.execute(
                    "SELECT count(*) FROM object_anchor WHERE object_value_id = ?", (value_id,)
                ).fetchone()[0]
            )
            if association_count == 0:
                yield ValidationFinding(
                    summary=(
                        f"associated data {uuid!r} is grounded by no anchor; "
                        "at least one is required"
                    ),
                    implicated_objects=(uuid,),
                )
            for anchor_uuid, occurrence_count in self._connection.execute(
                "SELECT anchor_uuid, count(*) FROM object_anchor WHERE object_value_id = ?"
                " GROUP BY anchor_uuid ORDER BY anchor_uuid",
                (value_id,),
            ):
                anchor_id = str(anchor_uuid)
                if int(occurrence_count) > 1:
                    yield ValidationFinding(
                        summary=(
                            f"associated data {uuid!r} references anchor {anchor_id!r} "
                            "more than once"
                        ),
                        implicated_objects=(uuid, anchor_id),
                    )
                anchor = self._connection.execute(
                    f"SELECT object_kind, type_key FROM {object_relation} WHERE uuid = ?",  # noqa: S608
                    (anchor_id,),
                ).fetchone()
                if anchor is None or str(anchor[0]) != ObjectKind.ANCHOR.value:
                    yield ValidationFinding(
                        summary=(
                            f"associated data {uuid!r} references {anchor_id!r}, which is no "
                            "anchor owned by this graph"
                        ),
                        implicated_objects=(uuid, anchor_id),
                    )
                elif str(anchor[1]) not in definition.permitted_anchor_type_keys:
                    yield ValidationFinding(
                        summary=(
                            f"associated data {uuid!r} of type {type_key!r} is grounded by "
                            f"anchor type {anchor[1]!r}, which that type does not permit"
                        ),
                        implicated_definitions=(f"associatedDataType:{type_key}",),
                        implicated_objects=(uuid, anchor_id),
                    )
            declared = cached_property_constraints
            present: set[str] = set()
            for name, json_kind_value, boolean, number, text_value in self._connection.execute(
                "SELECT name, json_kind, boolean_value, number_value, text_value"
                " FROM object_property WHERE object_value_id = ? ORDER BY ordinal",
                (value_id,),
            ):
                property_name = str(name)
                present.add(property_name)
                prepared = declared.get(property_name)
                if prepared is None:
                    yield ValidationFinding(
                        summary=(
                            f"associated data {uuid!r} carries property {property_name!r}, which "
                            f"its type {type_key!r} does not declare"
                        ),
                        implicated_definitions=(f"associatedDataType:{type_key}",),
                        implicated_objects=(uuid,),
                    )
                    continue
                value = json_storage_value(json_kind_value, boolean, number, text_value)
                for reason in _validate_prepared_property_value(prepared, value):
                    yield ValidationFinding(
                        summary=f"associated data {uuid!r} property {property_name!r} {reason}",
                        implicated_definitions=(f"property:{type_key}.{property_name}",),
                        implicated_objects=(uuid,),
                    )
            for name, prepared in declared.items():
                if prepared.constraint.required and name not in present:
                    yield ValidationFinding(
                        summary=f"associated data {uuid!r} omits required property {name!r}",
                        implicated_definitions=(f"property:{type_key}.{name}",),
                        implicated_objects=(uuid,),
                    )

    def _aggregate_compiled_answer_unlocked(
        self,
        query: GraphQuery,
        definitions: GraphDefinitionSet,
        matched_count: int,
    ) -> tuple[AggregateBinding, ...] | ValidationFinding:
        """Stream exact reducers over the one already bounded target population."""
        from vellis.json_value import JsonValue, json_kind, unencodable_reason
        from vellis.query import (
            AggregateBinding,
            AggregateQueryOutput,
            AggregationOperator,
            _decimal_term,
            _exact_decimal_streamed_result,
            _integer_from_text,
            _integer_text,
        )

        assert isinstance(query.output, AggregateQueryOutput)
        output = query.output
        conditions = {condition.name: condition for condition in query.data_conditions}
        condition = conditions[output.data_condition]
        data_type = definitions.associated_data_type(condition.associated_data_type)
        declared = {
            rule.property_name: rule.json_kind
            for rule in (data_type.property_constraints if data_type else ())
        }
        bindings: dict[str, AggregateBinding] = {}
        for aggregation in output.aggregations:
            if aggregation.operator is AggregationOperator.COUNT:
                bindings[aggregation.name] = AggregateBinding(
                    aggregation=aggregation.name,
                    present=True,
                    value=Decimal(matched_count),
                )

        property_aggregations = tuple(
            aggregation
            for aggregation in output.aggregations
            if aggregation.operator is not AggregationOperator.COUNT
        )
        if not property_aggregations:
            return tuple(bindings[aggregation.name] for aggregation in output.aggregations)

        operations: dict[str, set[AggregationOperator]] = {}
        for aggregation in property_aggregations:
            operations.setdefault(str(aggregation.property_name), set()).add(aggregation.operator)
        sum_counts = {
            name: 0
            for name, operators in operations.items()
            if AggregationOperator.SUM in operators
        }
        sum_input_digits = dict.fromkeys(sum_counts, 0)
        extrema: dict[tuple[str, AggregationOperator], JsonValue] = {}
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS query_aggregate_sum_term"
            " (name TEXT, exponent INTEGER, coefficient TEXT NOT NULL,"
            " PRIMARY KEY (name, exponent)) WITHOUT ROWID"
        )
        self._connection.execute("DELETE FROM query_aggregate_sum_term")
        try:
            cursor = self._connection.execute(
                "SELECT p.name, p.json_kind, p.boolean_value, p.number_value, p.text_value"
                " FROM query_answer AS m"
                " JOIN object_property AS p ON p.object_value_id = m.c0"
                " JOIN query_selector_member AS r ON r.member_kind = 'aggregateProperty'"
                " AND r.selector_name = ? AND r.value = p.name",
                (output.data_condition,),
            )
            while batch := cursor.fetchmany(_AGGREGATION_BATCH_SIZE):
                for name_value, kind, boolean, number, text_value in batch:
                    name = str(name_value)
                    value = json_storage_value(kind, boolean, number, text_value)
                    if json_kind(value) is not declared.get(name):
                        continue
                    for operator in operations[name]:
                        if operator is AggregationOperator.SUM:
                            assert isinstance(value, Decimal)
                            exponent, coefficient, digits = _decimal_term(value)
                            sum_counts[name] += 1
                            sum_input_digits[name] += digits
                            while coefficient:
                                while coefficient % 10 == 0:
                                    coefficient //= 10
                                    exponent += 1
                                row = self._connection.execute(
                                    "SELECT coefficient FROM query_aggregate_sum_term"
                                    " WHERE name = ? AND exponent = ?",
                                    (name, exponent),
                                ).fetchone()
                                if row is None:
                                    break
                                self._connection.execute(
                                    "DELETE FROM query_aggregate_sum_term"
                                    " WHERE name = ? AND exponent = ?",
                                    (name, exponent),
                                )
                                coefficient += _integer_from_text(str(row[0]))
                            if coefficient:
                                self._connection.execute(
                                    "INSERT INTO query_aggregate_sum_term VALUES (?, ?, ?)",
                                    (name, exponent, _integer_text(coefficient)),
                                )
                            continue
                        key = (name, operator)
                        if key not in extrema:
                            extrema[key] = value
                        elif operator is AggregationOperator.MINIMUM:
                            if value < extrema[key]:  # pyright: ignore[reportOperatorIssue]
                                extrema[key] = value
                        elif value > extrema[key]:  # pyright: ignore[reportOperatorIssue]
                            extrema[key] = value

            for aggregation in property_aggregations:
                name = str(aggregation.property_name)
                if aggregation.operator is AggregationOperator.SUM:
                    if not sum_counts[name]:
                        bindings[aggregation.name] = AggregateBinding(
                            aggregation=aggregation.name, present=False
                        )
                        continue
                    try:
                        reduced: JsonValue = _exact_decimal_streamed_result(
                            lambda name=name: (
                                (int(exponent), _integer_from_text(str(coefficient)))
                                for exponent, coefficient in self._connection.execute(
                                    "SELECT exponent, coefficient"
                                    " FROM query_aggregate_sum_term WHERE name = ?"
                                    " ORDER BY exponent",
                                    (name,),
                                )
                            ),
                            sum_input_digits[name],
                            sum_counts[name],
                        )
                    except ArithmeticError as error:
                        return ValidationFinding(summary=str(error))
                else:
                    key = (name, aggregation.operator)
                    if key not in extrema:
                        bindings[aggregation.name] = AggregateBinding(
                            aggregation=aggregation.name, present=False
                        )
                        continue
                    reduced = extrema[key]
                if isinstance(reduced, str) and (reason := unencodable_reason(reduced)) is not None:
                    return ValidationFinding(summary=reason)
                bindings[aggregation.name] = AggregateBinding(
                    aggregation=aggregation.name, present=True, value=reduced
                )
        finally:
            self._connection.execute("DELETE FROM query_aggregate_sum_term")
        return tuple(bindings[aggregation.name] for aggregation in output.aggregations)

    def _prepare_prospective_assessment_scope_unlocked(self, active_identity: str) -> None:
        """Derive the changed-definition and staged-graph invariant closure in SQL."""
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS assessment_structural_type"
            " (type_key TEXT PRIMARY KEY) WITHOUT ROWID"
        )
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS assessment_definition_type"
            " (type_key TEXT PRIMARY KEY) WITHOUT ROWID"
        )
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS assessment_materialized_uuid"
            " (uuid TEXT PRIMARY KEY) WITHOUT ROWID"
        )
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS assessment_definition_relationship"
            " (natural_key TEXT PRIMARY KEY) WITHOUT ROWID"
        )
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS assessment_changed_multiplicity_rule"
            " (natural_key TEXT PRIMARY KEY) WITHOUT ROWID"
        )
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS assessment_structural_relationship"
            " (uuid TEXT PRIMARY KEY) WITHOUT ROWID"
        )
        self._connection.execute("DELETE FROM assessment_structural_type")
        self._connection.execute("DELETE FROM assessment_definition_type")
        self._connection.execute("DELETE FROM assessment_materialized_uuid")
        self._connection.execute("DELETE FROM assessment_definition_relationship")
        self._connection.execute("DELETE FROM assessment_changed_multiplicity_rule")
        self._connection.execute("DELETE FROM assessment_structural_relationship")
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
                    "INSERT OR IGNORE INTO assessment_structural_type VALUES (?)",
                    (str(type_key),),
                )
        # Include every effective type definition that refers to an edited type. A
        # removed anchor type, for example, must revalidate untouched data/link types
        # that still permit it.
        #
        # Reached through the resolved current source rather than by definition-set
        # identity. Once a proposal has been activated the active vocabulary is an overlay
        # over a base set, so a type nobody has edited since still lives in the base and no
        # row of it carries the active identity. Selecting by that identity finds nothing,
        # and the removal that orphans it is reported as conforming — on every system past
        # its first vocabulary change, which is every system that has been used.
        self._connection.execute(
            "INSERT OR IGNORE INTO assessment_definition_type"
            " SELECT DISTINCT t.type_key FROM current_definition_type_source AS s"
            " JOIN definition_type AS t ON t.definition_set_id = s.value_set_id"
            " AND t.type_key = s.type_key"
            " JOIN definition_anchor_permission AS p"
            " ON p.definition_set_id = t.definition_set_id"
            " AND p.type_occurrence = t.occurrence"
            " WHERE p.anchor_type_key IN (SELECT type_key FROM proposal_definition_type)"
            " AND NOT EXISTS (SELECT 1 FROM proposal_definition_type AS e"
            " WHERE e.type_key = t.type_key)"
            " UNION SELECT DISTINCT t.type_key FROM current_definition_type_source AS s"
            " JOIN definition_type AS t ON t.definition_set_id = s.value_set_id"
            " AND t.type_key = s.type_key"
            " JOIN definition_endpoint_permission AS p"
            " ON p.definition_set_id = t.definition_set_id"
            " AND p.type_occurrence = t.occurrence"
            " WHERE p.type_key IN (SELECT type_key FROM proposal_definition_type)"
            " AND NOT EXISTS (SELECT 1 FROM proposal_definition_type AS e"
            " WHERE e.type_key = t.type_key)"
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
        # Multiplicity rules are reached the same way, and for the same reason: a rule
        # nobody has edited since an activation lives in the base set.
        if self._connection.execute("SELECT 1 FROM proposal_definition_type LIMIT 1").fetchone():
            self._connection.execute(
                "INSERT OR IGNORE INTO assessment_definition_relationship"
                " SELECT DISTINCT r.natural_key"
                " FROM current_definition_relationship_source AS s"
                " JOIN definition_multiplicity_rule AS r"
                " ON r.definition_set_id = s.value_set_id AND r.natural_key = s.natural_key"
                " JOIN definition_multiplicity_participant AS p"
                " ON p.definition_set_id = r.definition_set_id"
                " AND p.rule_occurrence = r.occurrence"
                " WHERE p.type_key IN (SELECT type_key FROM proposal_definition_type)"
                " AND NOT EXISTS (SELECT 1 FROM proposal_definition_relationship AS e"
                " WHERE e.natural_key = r.natural_key)"
                " UNION SELECT DISTINCT r.natural_key"
                " FROM current_definition_relationship_source AS s"
                " JOIN definition_multiplicity_rule AS r"
                " ON r.definition_set_id = s.value_set_id AND r.natural_key = s.natural_key"
                " WHERE r.link_type_key IN (SELECT type_key FROM proposal_definition_type)"
                " AND NOT EXISTS (SELECT 1 FROM proposal_definition_relationship AS e"
                " WHERE e.natural_key = r.natural_key)"
            )
        self._connection.execute(
            "INSERT OR IGNORE INTO assessment_definition_relationship"
            " SELECT natural_key FROM proposal_definition_relationship"
            " WHERE operation = 'upsert'"
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
            self._connection.execute(
                "INSERT OR IGNORE INTO assessment_changed_multiplicity_rule VALUES (?)",
                (str(natural_key),),
            )
        self._connection.execute(
            "INSERT OR IGNORE INTO assessment_materialized_uuid"
            " SELECT g.uuid FROM assessment_structural_type AS t"
            " CROSS JOIN graph_presence_interval AS g INDEXED BY graph_presence_current_type"
            " ON g.object_kind IN ('anchor', 'associatedData', 'link')"
            " AND g.type_key = t.type_key AND g.valid_to_revision IS NULL"
            " WHERE NOT EXISTS (SELECT 1 FROM proposal_entry AS p WHERE p.uuid = g.uuid)"
            " UNION SELECT v.uuid FROM proposal_entry AS p JOIN object_value AS v"
            " ON v.id = p.object_value_id WHERE p.operation = 'upsert'"
            " AND v.type_key IN (SELECT type_key FROM assessment_structural_type)"
        )
        self._connection.execute(
            "INSERT OR IGNORE INTO assessment_materialized_uuid SELECT uuid FROM proposal_entry"
        )
        self._connection.execute(
            "INSERT OR IGNORE INTO assessment_materialized_uuid"
            " SELECT source_uuid FROM object_value AS v JOIN proposal_entry AS p"
            " ON v.id = p.object_value_id"
            " WHERE v.object_kind = 'link'"
            " UNION SELECT target_uuid FROM object_value AS v JOIN proposal_entry AS p"
            " ON v.id = p.object_value_id"
            " WHERE v.object_kind = 'link'"
            " UNION SELECT a.anchor_uuid FROM object_anchor AS a JOIN proposal_entry AS p"
            " ON a.object_value_id = p.object_value_id"
            " UNION SELECT v.source_uuid FROM proposal_entry AS p"
            " CROSS JOIN graph_presence_interval AS g INDEXED BY graph_presence_current_uuid"
            " ON g.uuid = p.uuid AND g.valid_to_revision IS NULL"
            " JOIN object_value AS v ON v.id = g.object_value_id"
            " WHERE v.object_kind = 'link'"
            " UNION SELECT v.target_uuid FROM proposal_entry AS p"
            " CROSS JOIN graph_presence_interval AS g INDEXED BY graph_presence_current_uuid"
            " ON g.uuid = p.uuid AND g.valid_to_revision IS NULL"
            " JOIN object_value AS v ON v.id = g.object_value_id"
            " WHERE v.object_kind = 'link'"
            " UNION SELECT a.anchor_uuid FROM proposal_entry AS p"
            " CROSS JOIN graph_presence_interval AS g INDEXED BY graph_presence_current_uuid"
            " ON g.uuid = p.uuid AND g.valid_to_revision IS NULL"
            " JOIN object_anchor AS a ON a.object_value_id = g.object_value_id"
        )
        for table in (
            "assessment_validation_uuid",
            "assessment_endpoint_membership_change",
        ):
            self._connection.execute(
                f"CREATE TEMP TABLE IF NOT EXISTS {table}"  # noqa: S608
                " (uuid TEXT PRIMARY KEY) WITHOUT ROWID"
            )
            self._connection.execute(f"DELETE FROM {table}")  # noqa: S608
        self._connection.execute(
            "INSERT INTO assessment_validation_uuid SELECT uuid FROM proposal_entry"
            " UNION SELECT g.uuid FROM assessment_structural_type AS t"
            " CROSS JOIN graph_presence_interval AS g INDEXED BY graph_presence_current_type"
            " ON g.object_kind IN ('anchor', 'associatedData', 'link')"
            " AND g.type_key = t.type_key AND g.valid_to_revision IS NULL"
            " WHERE NOT EXISTS (SELECT 1 FROM proposal_entry AS p WHERE p.uuid = g.uuid)"
        )
        self._connection.execute(
            "INSERT OR IGNORE INTO assessment_endpoint_membership_change"
            " SELECT p.uuid FROM proposal_entry AS p"
            " LEFT JOIN graph_presence_interval AS g INDEXED BY graph_presence_current_uuid"
            " ON g.uuid = p.uuid AND g.valid_to_revision IS NULL"
            " LEFT JOIN object_value AS c ON c.id = g.object_value_id"
            " LEFT JOIN object_value AS n ON n.id = p.object_value_id"
            " WHERE p.object_kind IN ('anchor', 'associatedData')"
            " AND ((c.id IS NULL) != (n.id IS NULL)"
            " OR c.object_kind IS NOT n.object_kind OR c.type_key IS NOT n.type_key)"
        )

        def include_incident_relations(subject_table: str, relation_table: str) -> None:
            self._connection.execute(
                f"INSERT OR IGNORE INTO {relation_table}"  # noqa: S608
                f" SELECT g.uuid FROM {subject_table} AS s"  # noqa: S608
                " CROSS JOIN graph_presence_interval AS g"
                " INDEXED BY graph_presence_current_link_source"
                " ON g.source_uuid = s.uuid AND g.valid_to_revision IS NULL"
                " WHERE g.object_kind = 'link'"
                " AND NOT EXISTS (SELECT 1 FROM proposal_entry AS p WHERE p.uuid = g.uuid)"
                f" UNION SELECT g.uuid FROM {subject_table} AS s"  # noqa: S608
                " CROSS JOIN graph_presence_interval AS g"
                " INDEXED BY graph_presence_current_link_target"
                " ON g.target_uuid = s.uuid AND g.valid_to_revision IS NULL"
                " WHERE g.object_kind = 'link'"
                " AND NOT EXISTS (SELECT 1 FROM proposal_entry AS p WHERE p.uuid = g.uuid)"
                " UNION SELECT v.uuid FROM proposal_entry AS p JOIN object_value AS v"
                " ON v.id = p.object_value_id WHERE p.operation = 'upsert'"
                f" AND v.object_kind = 'link' AND v.source_uuid IN"  # noqa: S608
                f" (SELECT uuid FROM {subject_table})"  # noqa: S608
                " UNION SELECT v.uuid FROM proposal_entry AS p JOIN object_value AS v"
                " ON v.id = p.object_value_id WHERE p.operation = 'upsert'"
                f" AND v.object_kind = 'link' AND v.target_uuid IN"  # noqa: S608
                f" (SELECT uuid FROM {subject_table})"  # noqa: S608
                f" UNION SELECT v.uuid FROM {subject_table} AS s"  # noqa: S608
                " CROSS JOIN object_anchor AS a INDEXED BY object_anchor_reverse"
                " ON a.anchor_uuid = s.uuid JOIN object_value AS v ON v.id = a.object_value_id"
                " JOIN graph_presence_interval AS g"
                " ON g.object_value_id = v.id AND g.valid_to_revision IS NULL"
                " WHERE v.object_kind = 'associatedData'"
                " AND NOT EXISTS (SELECT 1 FROM proposal_entry AS p WHERE p.uuid = v.uuid)"
                " UNION SELECT v.uuid FROM proposal_entry AS p JOIN object_value AS v"
                " ON v.id = p.object_value_id JOIN object_anchor AS a ON a.object_value_id = v.id"
                " WHERE p.operation = 'upsert' AND v.object_kind = 'associatedData'"
                f" AND a.anchor_uuid IN (SELECT uuid FROM {subject_table})"  # noqa: S608
                f" UNION SELECT v.uuid FROM {subject_table} AS i"  # noqa: S608
                " CROSS JOIN graph_presence_interval AS g INDEXED BY graph_presence_current_uuid"
                " ON g.uuid = i.uuid AND g.valid_to_revision IS NULL"
                " JOIN object_value AS v ON v.id = g.object_value_id"
                " WHERE v.object_kind IN ('link', 'associatedData')"
                " UNION SELECT p.uuid FROM proposal_entry AS p"
                f" WHERE p.uuid IN (SELECT uuid FROM {subject_table})"  # noqa: S608
                " AND p.object_kind IN ('link', 'associatedData')"
            )

        # A participant type/membership change can change the validity of its incident
        # relationship objects. Promote those relationships into local validation;
        # rule-specific multiplicity subjects are derived later without a second hop.
        include_incident_relations(
            "assessment_endpoint_membership_change", "assessment_structural_relationship"
        )
        self._connection.execute(
            "INSERT OR IGNORE INTO assessment_materialized_uuid"
            " SELECT uuid FROM assessment_structural_relationship"
            " UNION SELECT g.source_uuid FROM assessment_structural_relationship AS r"
            " CROSS JOIN graph_presence_interval AS g INDEXED BY graph_presence_current_uuid"
            " ON g.uuid = r.uuid"
            " AND g.valid_to_revision IS NULL WHERE g.object_kind = 'link'"
            " UNION SELECT g.target_uuid FROM assessment_structural_relationship AS r"
            " CROSS JOIN graph_presence_interval AS g INDEXED BY graph_presence_current_uuid"
            " ON g.uuid = r.uuid"
            " AND g.valid_to_revision IS NULL WHERE g.object_kind = 'link'"
            " UNION SELECT v.source_uuid FROM proposal_entry AS p JOIN object_value AS v"
            " ON v.id = p.object_value_id WHERE p.operation = 'upsert'"
            " AND v.object_kind = 'link'"
            " AND v.uuid IN (SELECT uuid FROM assessment_structural_relationship)"
            " UNION SELECT v.target_uuid FROM proposal_entry AS p JOIN object_value AS v"
            " ON v.id = p.object_value_id WHERE p.operation = 'upsert'"
            " AND v.object_kind = 'link'"
            " AND v.uuid IN (SELECT uuid FROM assessment_structural_relationship)"
            " UNION SELECT a.anchor_uuid FROM assessment_structural_relationship AS r"
            " CROSS JOIN graph_presence_interval AS g INDEXED BY graph_presence_current_uuid"
            " ON g.uuid = r.uuid"
            " AND g.valid_to_revision IS NULL JOIN object_anchor AS a"
            " ON a.object_value_id = g.object_value_id"
            " UNION SELECT a.anchor_uuid FROM assessment_structural_relationship AS r"
            " JOIN proposal_entry AS p ON p.uuid = r.uuid JOIN object_anchor AS a"
            " ON a.object_value_id = p.object_value_id WHERE p.operation = 'upsert'"
        )
        self._connection.execute(
            "INSERT OR IGNORE INTO assessment_validation_uuid"
            " SELECT uuid FROM assessment_structural_relationship"
        )
        # Local relationship validation needs its unchanged endpoints for lookup, but
        # lookup-only participants do not themselves become validation work.
        self._connection.execute(
            "INSERT OR IGNORE INTO assessment_materialized_uuid"
            " SELECT v.source_uuid FROM assessment_validation_uuid AS i"
            " CROSS JOIN graph_presence_interval AS g INDEXED BY graph_presence_current_uuid"
            " ON g.uuid = i.uuid AND g.valid_to_revision IS NULL"
            " JOIN object_value AS v ON v.id = g.object_value_id"
            " WHERE v.object_kind = 'link'"
            " UNION SELECT v.target_uuid FROM assessment_validation_uuid AS i"
            " CROSS JOIN graph_presence_interval AS g INDEXED BY graph_presence_current_uuid"
            " ON g.uuid = i.uuid AND g.valid_to_revision IS NULL"
            " JOIN object_value AS v ON v.id = g.object_value_id"
            " WHERE v.object_kind = 'link'"
            " UNION SELECT v.source_uuid FROM assessment_validation_uuid AS i"
            " JOIN proposal_entry AS p ON p.uuid = i.uuid"
            " JOIN object_value AS v ON v.id = p.object_value_id"
            " WHERE p.operation = 'upsert' AND v.object_kind = 'link'"
            " UNION SELECT v.target_uuid FROM assessment_validation_uuid AS i"
            " JOIN proposal_entry AS p ON p.uuid = i.uuid"
            " JOIN object_value AS v ON v.id = p.object_value_id"
            " WHERE p.operation = 'upsert' AND v.object_kind = 'link'"
            " UNION SELECT a.anchor_uuid FROM assessment_validation_uuid AS i"
            " JOIN graph_presence_interval AS g INDEXED BY graph_presence_current_uuid"
            " ON g.uuid = i.uuid AND g.valid_to_revision IS NULL"
            " JOIN object_anchor AS a ON a.object_value_id = g.object_value_id"
            " UNION SELECT a.anchor_uuid FROM assessment_validation_uuid AS i"
            " JOIN proposal_entry AS p ON p.uuid = i.uuid"
            " JOIN object_anchor AS a ON a.object_value_id = p.object_value_id"
            " WHERE p.operation = 'upsert'"
        )
        self._prepare_prospective_multiplicity_impact_unlocked(active_identity)
        self._prepare_effective_assessment_relations_unlocked()

    def _prepare_effective_assessment_relations_unlocked(self) -> None:
        """Materialize affected validation objects and lookup-only participants."""
        self._connection.execute("DROP TABLE IF EXISTS temp.assessment_effective_object")
        self._connection.execute(
            "CREATE TEMP TABLE assessment_effective_object AS"
            " SELECT g.uuid, v.object_kind, v.type_key, v.source_uuid, v.target_uuid,"
            " v.id AS object_value_id FROM assessment_materialized_uuid AS i"
            " CROSS JOIN graph_presence_interval AS g INDEXED BY graph_presence_current_uuid"
            " ON g.uuid = i.uuid AND g.valid_to_revision IS NULL"
            " JOIN object_value AS v ON v.id = g.object_value_id WHERE 1 = 1"
            " AND NOT EXISTS (SELECT 1 FROM proposal_entry AS p WHERE p.uuid = g.uuid)"
            " UNION ALL SELECT v.uuid, v.object_kind, v.type_key, v.source_uuid,"
            " v.target_uuid, v.id FROM proposal_entry AS p"
            " JOIN object_value AS v ON v.id = p.object_value_id"
            " WHERE p.operation = 'upsert' AND p.uuid IN"
            " (SELECT uuid FROM assessment_materialized_uuid)"
        )
        self._connection.execute(
            "CREATE UNIQUE INDEX assessment_effective_object_uuid"
            " ON assessment_effective_object(uuid)"
        )
        self._connection.execute(
            "CREATE INDEX assessment_effective_object_type"
            " ON assessment_effective_object(object_kind, type_key, uuid)"
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
            overlay = self._connection.execute(
                "SELECT base_definition_set_id FROM definition_set_overlay"
                " WHERE definition_set_id = ?",
                (active_identity,),
            ).fetchone()
            if overlay is None:
                rows = self._connection.execute(
                    "SELECT type_key FROM definition_type WHERE definition_set_id = ?"
                    " ORDER BY type_key",
                    (active_identity,),
                )
            else:
                rows = self._connection.execute(
                    "SELECT type_key FROM definition_type AS t WHERE definition_set_id = ?"
                    " AND NOT EXISTS (SELECT 1 FROM definition_set_type_override AS o"
                    " WHERE o.definition_set_id = ? AND o.type_key = t.type_key)"
                    " UNION ALL SELECT type_key FROM definition_set_type_override"
                    " WHERE definition_set_id = ? AND operation = 'upsert' ORDER BY type_key",
                    (str(overlay[0]), active_identity, active_identity),
                )
        else:
            rows = self._connection.execute(
                "SELECT type_key FROM assessment_definition_type ORDER BY type_key"
            )
        for (type_key,) in rows:
            yield str(type_key)

    def _effective_relationship_keys_unlocked(self, active_identity: str) -> Iterator[str]:
        overlay = self._connection.execute(
            "SELECT base_definition_set_id FROM definition_set_overlay WHERE definition_set_id = ?",
            (active_identity,),
        ).fetchone()
        if overlay is None:
            rows = self._connection.execute(
                "SELECT natural_key FROM definition_multiplicity_rule"
                " WHERE definition_set_id = ? ORDER BY natural_key",
                (active_identity,),
            )
        else:
            rows = self._connection.execute(
                "SELECT natural_key FROM definition_multiplicity_rule AS r"
                " WHERE definition_set_id = ? AND NOT EXISTS"
                " (SELECT 1 FROM definition_set_relationship_override AS o"
                " WHERE o.definition_set_id = ? AND o.natural_key = r.natural_key)"
                " UNION ALL SELECT natural_key FROM definition_set_relationship_override"
                " WHERE definition_set_id = ? AND operation = 'upsert' ORDER BY natural_key",
                (str(overlay[0]), active_identity, active_identity),
            )
        for (natural_key,) in rows:
            yield str(natural_key)

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
            keys = ((key,) for key in self._effective_relationship_keys_unlocked(active_identity))
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
            keys = ((key,) for key in self._effective_relationship_keys_unlocked(active_identity))
        else:
            keys = self._connection.execute(
                "SELECT DISTINCT rule_key FROM multiplicity_work ORDER BY rule_key"
            )
        for (natural_key,) in keys:
            definitions = self._definitions_for_relation_unlocked(
                relation,
                active_identity,
                type_keys=set(),
                relationship_keys={str(natural_key)},
            )
            yield from self._multiplicity_findings_unlocked(
                relation, definitions, natural_key=str(natural_key)
            )

    def _clear_multiplicity_impact_unlocked(self) -> None:
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS multiplicity_impact_reason"
            " (rule_key TEXT NOT NULL, subject_uuid TEXT NOT NULL,"
            " constrained_end TEXT NOT NULL, reason_kind TEXT NOT NULL,"
            " PRIMARY KEY(rule_key, subject_uuid, constrained_end, reason_kind)) WITHOUT ROWID"
        )
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS multiplicity_work"
            " (rule_key TEXT NOT NULL, subject_uuid TEXT NOT NULL,"
            " constrained_end TEXT NOT NULL,"
            " PRIMARY KEY(rule_key, subject_uuid, constrained_end)) WITHOUT ROWID"
        )
        self._connection.execute("DELETE FROM multiplicity_impact_reason")
        self._connection.execute("DELETE FROM multiplicity_work")

    def _record_multiplicity_reasons_unlocked(
        self, reasons: Iterable[MultiplicityImpactReason]
    ) -> None:
        self._connection.executemany(
            "INSERT OR IGNORE INTO multiplicity_impact_reason VALUES (?, ?, ?, ?)",
            (
                (
                    reason.rule_key,
                    reason.subject_uuid,
                    reason.constrained_end,
                    reason.reason_kind,
                )
                for reason in reasons
            ),
        )

    def _insert_rule_meaning_reasons_unlocked(
        self,
        rule: LinkMultiplicityConstraint | DirectAssociationMultiplicityConstraint,
        relation: str,
    ) -> None:
        if relation not in {"current_graph_object", "prospective_graph_object"}:
            raise ValueError("unknown rule-meaning state relation")
        natural_key = semantic_identity(relationship_identity(rule))
        if isinstance(rule, LinkMultiplicityConstraint):
            kind_sql = "object_kind IN ('anchor', 'associatedData')"
            constrained_types = rule.constrained_endpoint_type_keys
        elif rule.constrained_end is DirectAssociationEnd.ANCHOR:
            kind_sql = "object_kind = 'anchor'"
            constrained_types = rule.anchor_type_keys
        else:
            kind_sql = "object_kind = 'associatedData'"
            constrained_types = rule.associated_data_type_keys
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS multiplicity_rule_subject_type"
            " (type_key TEXT PRIMARY KEY) WITHOUT ROWID"
        )
        self._connection.execute("DELETE FROM multiplicity_rule_subject_type")
        self._connection.executemany(
            "INSERT INTO multiplicity_rule_subject_type VALUES (?)",
            ((type_key,) for type_key in constrained_types),
        )
        self._connection.execute(
            "INSERT OR IGNORE INTO multiplicity_impact_reason"
            " (rule_key, subject_uuid, constrained_end, reason_kind)"
            f" SELECT ?, uuid, ?, 'ruleMeaningChanged' FROM {relation}"  # noqa: S608
            f" WHERE {kind_sql} AND type_key IN"  # noqa: S608
            " (SELECT type_key FROM multiplicity_rule_subject_type)",
            (natural_key, rule.constrained_end.value),
        )

    def _prepare_prospective_multiplicity_impact_unlocked(self, active_identity: str) -> None:
        """Use the shared old/proposed kernel to derive exact prospective work."""
        self._clear_multiplicity_impact_unlocked()
        changed_uuids = {
            str(row[0])
            for row in self._connection.execute(
                "SELECT p.uuid FROM proposal_entry AS p"
                " LEFT JOIN graph_presence_interval AS g INDEXED BY graph_presence_current_uuid"
                " ON g.uuid = p.uuid AND g.valid_to_revision IS NULL"
                " LEFT JOIN object_value AS c ON c.id = g.object_value_id"
                " LEFT JOIN object_value AS n ON n.id = p.object_value_id"
                " WHERE (c.id IS NULL) != (n.id IS NULL)"
                " OR c.object_kind IS NOT n.object_kind OR c.type_key IS NOT n.type_key"
                " OR c.source_uuid IS NOT n.source_uuid OR c.target_uuid IS NOT n.target_uuid"
                " OR EXISTS (SELECT anchor_uuid FROM object_anchor"
                " WHERE object_value_id = c.id EXCEPT SELECT anchor_uuid"
                " FROM object_anchor WHERE object_value_id = n.id)"
                " OR EXISTS (SELECT anchor_uuid FROM object_anchor"
                " WHERE object_value_id = n.id EXCEPT SELECT anchor_uuid"
                " FROM object_anchor WHERE object_value_id = c.id)"
            )
        }
        # A proposal entry's stored base is conflict-detection evidence. Active work may
        # subsequently change that identity, so prospective meaning must compare the
        # evaluated current object with the proposal overlay rather than the stale base.
        old_changed = {
            value.uuid: value for value in self._objects_for_uuids_unlocked(changed_uuids)
        }
        proposed_changed = {
            value.uuid: value
            for value in self._objects_from_relation_for_uuids_unlocked(
                "prospective_graph_object", changed_uuids
            )
        }
        neighborhood = self._multiplicity_impact_neighborhood_unlocked(
            old_changed,
            proposed_changed,
            proposed_relation="prospective_graph_object",
        )
        changed_rule_keys = {
            str(row[0])
            for row in self._connection.execute(
                "SELECT natural_key FROM assessment_changed_multiplicity_rule"
            )
        }
        candidate_keys = self._candidate_multiplicity_rule_keys_unlocked(neighborhood)
        candidate_keys.difference_update(changed_rule_keys)
        if candidate_keys:
            definitions = self._definitions_for_relation_unlocked(
                "prospective_graph_object",
                active_identity,
                type_keys=set(),
                relationship_keys=candidate_keys,
            )
            self._record_multiplicity_reasons_unlocked(
                derive_multiplicity_impact_reasons(
                    neighborhood, definitions.relationship_constraints
                )
            )
        for natural_key in changed_rule_keys:
            old_definitions = self._load_definition_set(
                active_identity, type_keys=set(), relationship_keys={natural_key}
            )
            proposed_definitions = self._definitions_for_relation_unlocked(
                "prospective_graph_object",
                active_identity,
                type_keys=set(),
                relationship_keys={natural_key},
            )
            for rule in old_definitions.relationship_constraints:
                self._insert_rule_meaning_reasons_unlocked(rule, "current_graph_object")
            for rule in proposed_definitions.relationship_constraints:
                self._insert_rule_meaning_reasons_unlocked(rule, "prospective_graph_object")
        self._connection.execute(
            "INSERT INTO multiplicity_work"
            " SELECT DISTINCT rule_key, subject_uuid, constrained_end"
            " FROM multiplicity_impact_reason"
        )

    def _prepare_multiplicity_relations_unlocked(
        self,
        natural_key: str,
        constraint: LinkMultiplicityConstraint | DirectAssociationMultiplicityConstraint,
    ) -> None:
        """Materialize one rule's incident degree and lookup-only participants."""
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS multiplicity_lookup_uuid"
            " (uuid TEXT PRIMARY KEY) WITHOUT ROWID"
        )
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS multiplicity_effective_object"
            " (uuid TEXT PRIMARY KEY, object_kind TEXT, type_key TEXT) WITHOUT ROWID"
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS multiplicity_effective_object_type"
            " ON multiplicity_effective_object(object_kind, type_key, uuid)"
        )
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS multiplicity_incident_link"
            " (uuid TEXT PRIMARY KEY, type_key TEXT, source_uuid TEXT, target_uuid TEXT)"
            " WITHOUT ROWID"
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS multiplicity_incident_link_source"
            " ON multiplicity_incident_link(source_uuid, type_key, target_uuid)"
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS multiplicity_incident_link_target"
            " ON multiplicity_incident_link(target_uuid, type_key, source_uuid)"
        )
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS multiplicity_effective_data_anchor"
            " (data_uuid TEXT, anchor_uuid TEXT, PRIMARY KEY (data_uuid, anchor_uuid))"
            " WITHOUT ROWID"
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS multiplicity_effective_data_anchor_anchor"
            " ON multiplicity_effective_data_anchor(anchor_uuid, data_uuid)"
        )
        self._connection.execute("DELETE FROM multiplicity_lookup_uuid")
        self._connection.execute("DELETE FROM multiplicity_effective_object")
        self._connection.execute("DELETE FROM multiplicity_incident_link")
        self._connection.execute("DELETE FROM multiplicity_effective_data_anchor")
        self._connection.execute(
            "INSERT INTO multiplicity_lookup_uuid SELECT subject_uuid"
            " FROM multiplicity_work WHERE rule_key = ?",
            (natural_key,),
        )
        if not self._connection.execute(
            "SELECT 1 FROM multiplicity_lookup_uuid LIMIT 1"
        ).fetchone():
            return
        if isinstance(constraint, LinkMultiplicityConstraint):
            near = "source_uuid" if constraint.constrained_end is LinkEnd.SOURCE else "target_uuid"
            far = "target_uuid" if constraint.constrained_end is LinkEnd.SOURCE else "source_uuid"
            self._connection.execute(
                "INSERT OR IGNORE INTO multiplicity_incident_link"
                f" SELECT g.uuid, g.type_key, g.source_uuid, g.target_uuid"  # noqa: S608
                " FROM multiplicity_work AS w"
                " CROSS JOIN graph_presence_interval AS g"
                f" INDEXED BY graph_presence_current_link_{near.removesuffix('_uuid')}"  # noqa: S608
                f" ON g.{near} = w.subject_uuid AND g.valid_to_revision IS NULL"  # noqa: S608
                " WHERE w.rule_key = ? AND g.object_kind = 'link' AND g.type_key = ?"
                " AND NOT EXISTS (SELECT 1 FROM proposal_entry AS p WHERE p.uuid = g.uuid)"
                " UNION SELECT v.uuid, v.type_key, v.source_uuid, v.target_uuid"
                " FROM multiplicity_work AS w"
                " JOIN proposal_entry AS p JOIN object_value AS v ON v.id = p.object_value_id"
                f" AND v.{near} = w.subject_uuid WHERE w.rule_key = ?"  # noqa: S608
                " AND p.operation = 'upsert' AND v.object_kind = 'link' AND v.type_key = ?",
                (
                    natural_key,
                    constraint.link_type_key,
                    natural_key,
                    constraint.link_type_key,
                ),
            )
            self._connection.execute(
                "INSERT OR IGNORE INTO multiplicity_lookup_uuid"
                f" SELECT {far} FROM multiplicity_incident_link"  # noqa: S608
            )
        else:
            if constraint.constrained_end is DirectAssociationEnd.ANCHOR:
                self._connection.execute(
                    "INSERT OR IGNORE INTO multiplicity_effective_data_anchor"
                    " SELECT a.data_uuid, a.anchor_uuid"
                    " FROM multiplicity_work AS w"
                    " JOIN current_data_anchor AS a ON a.anchor_uuid = w.subject_uuid"
                    " WHERE w.rule_key = ? AND NOT EXISTS"
                    " (SELECT 1 FROM proposal_entry AS p WHERE p.uuid = a.data_uuid)"
                    " UNION SELECT v.uuid, a.anchor_uuid"
                    " FROM multiplicity_work AS w"
                    " JOIN proposal_entry AS p JOIN object_value AS v ON v.id = p.object_value_id"
                    " JOIN object_anchor AS a ON a.object_value_id = v.id"
                    " AND a.anchor_uuid = w.subject_uuid WHERE w.rule_key = ?"
                    " AND p.operation = 'upsert' AND v.object_kind = 'associatedData'",
                    (natural_key, natural_key),
                )
                self._connection.execute(
                    "INSERT OR IGNORE INTO multiplicity_lookup_uuid"
                    " SELECT data_uuid FROM multiplicity_effective_data_anchor"
                )
            else:
                self._connection.execute(
                    "INSERT OR IGNORE INTO multiplicity_effective_data_anchor"
                    " SELECT a.data_uuid, a.anchor_uuid"
                    " FROM multiplicity_work AS w"
                    " JOIN current_data_anchor AS a ON a.data_uuid = w.subject_uuid"
                    " WHERE w.rule_key = ? AND NOT EXISTS"
                    " (SELECT 1 FROM proposal_entry AS p WHERE p.uuid = a.data_uuid)"
                    " UNION SELECT v.uuid, a.anchor_uuid"
                    " FROM multiplicity_work AS w"
                    " JOIN proposal_entry AS p ON p.uuid = w.subject_uuid"
                    " JOIN object_value AS v ON v.id = p.object_value_id"
                    " JOIN object_anchor AS a ON a.object_value_id = v.id"
                    " WHERE w.rule_key = ? AND p.operation = 'upsert'"
                    " AND v.object_kind = 'associatedData'",
                    (natural_key, natural_key),
                )
                self._connection.execute(
                    "INSERT OR IGNORE INTO multiplicity_lookup_uuid"
                    " SELECT anchor_uuid FROM multiplicity_effective_data_anchor"
                )
        self._connection.execute(
            "INSERT OR IGNORE INTO multiplicity_effective_object"
            " SELECT g.uuid, g.object_kind, g.type_key FROM multiplicity_lookup_uuid AS i"
            " CROSS JOIN graph_presence_interval AS g INDEXED BY graph_presence_current_uuid"
            " ON g.uuid = i.uuid AND g.valid_to_revision IS NULL"
            " WHERE NOT EXISTS (SELECT 1 FROM proposal_entry AS p WHERE p.uuid = g.uuid)"
            " UNION SELECT v.uuid, v.object_kind, v.type_key"
            " FROM multiplicity_lookup_uuid AS i JOIN proposal_entry AS p ON p.uuid = i.uuid"
            " JOIN object_value AS v ON v.id = p.object_value_id WHERE p.operation = 'upsert'"
        )

    def _multiplicity_findings_unlocked(
        self, relation: str, definitions: GraphDefinitionSet, *, natural_key: str = ""
    ) -> Iterator[ValidationFinding]:
        prospective = relation == "prospective_graph_object"
        object_relation = "multiplicity_effective_object" if prospective else relation
        link_relation = "multiplicity_incident_link" if prospective else relation
        association_relation = (
            "multiplicity_effective_data_anchor" if prospective else "current_data_anchor"
        )
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS multiplicity_type_filter"
            " (role TEXT, type_key TEXT, PRIMARY KEY (role, type_key)) WITHOUT ROWID"
        )
        for constraint in definitions.relationship_constraints:
            self._connection.execute("DELETE FROM multiplicity_type_filter")
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
                self._connection.executemany(
                    "INSERT INTO multiplicity_type_filter VALUES ('constrained', ?)",
                    ((value,) for value in constrained),
                )
                self._connection.executemany(
                    "INSERT INTO multiplicity_type_filter VALUES ('opposite', ?)",
                    ((value,) for value in opposite),
                )
                if prospective:
                    self._prepare_multiplicity_relations_unlocked(natural_key, constraint)
                sql = (
                    f"SELECT e.uuid, e.type_key, count(f.uuid) FROM {object_relation} AS e"
                    f" LEFT JOIN {link_relation} AS l ON "
                    + ("1 = 1" if prospective else "l.object_kind = 'link'")
                    + f" AND l.type_key = ? AND l.{near} = e.uuid"
                    + f" LEFT JOIN {object_relation} AS f ON f.uuid = l.{far}"
                    + " AND EXISTS (SELECT 1 FROM multiplicity_type_filter AS mtf"
                    + " WHERE mtf.role = 'opposite' AND mtf.type_key = f.type_key)"
                    + " WHERE e.object_kind IN ('anchor', 'associatedData')"
                    + " AND EXISTS (SELECT 1 FROM multiplicity_type_filter AS mtf"
                    + " WHERE mtf.role = 'constrained' AND mtf.type_key = e.type_key)"
                    + (
                        " AND e.uuid IN (SELECT subject_uuid FROM multiplicity_work"
                        " WHERE rule_key = ?)"
                        if prospective
                        else ""
                    )
                    + " GROUP BY e.uuid, e.type_key ORDER BY e.uuid"
                )
                parameters = (
                    (constraint.link_type_key, natural_key)
                    if prospective
                    else (constraint.link_type_key,)
                )
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
            self._connection.executemany(
                "INSERT INTO multiplicity_type_filter VALUES ('anchor', ?)",
                ((value,) for value in anchors),
            )
            self._connection.executemany(
                "INSERT INTO multiplicity_type_filter VALUES ('data', ?)",
                ((value,) for value in data_types),
            )
            if prospective:
                self._prepare_multiplicity_relations_unlocked(natural_key, constraint)
            if constraint.constrained_end is DirectAssociationEnd.ANCHOR:
                sql = (
                    f"SELECT a.uuid, count(DISTINCT d.uuid) FROM {object_relation} AS a"
                    f" LEFT JOIN {association_relation} AS da ON da.anchor_uuid = a.uuid"
                    f" LEFT JOIN {object_relation} AS d ON d.uuid = da.data_uuid"
                    " AND EXISTS (SELECT 1 FROM multiplicity_type_filter AS mtf"
                    " WHERE mtf.role = 'data' AND mtf.type_key = d.type_key)"
                    " WHERE a.object_kind = 'anchor'"
                    " AND EXISTS (SELECT 1 FROM multiplicity_type_filter AS mtf"
                    " WHERE mtf.role = 'anchor' AND mtf.type_key = a.type_key)"
                    " GROUP BY a.uuid ORDER BY a.uuid"
                )
                if prospective:
                    sql = sql.replace(
                        " GROUP BY",
                        " AND a.uuid IN (SELECT subject_uuid FROM multiplicity_work"
                        " WHERE rule_key = ?)"
                        " GROUP BY",
                    )
                rows = self._connection.execute(sql, (natural_key,) if prospective else ())
            else:
                sql = (
                    f"SELECT d.uuid, count(DISTINCT a.uuid) FROM {object_relation} AS d"
                    f" LEFT JOIN {association_relation} AS da ON da.data_uuid = d.uuid"
                    f" LEFT JOIN {object_relation} AS a ON a.uuid = da.anchor_uuid"
                    " AND EXISTS (SELECT 1 FROM multiplicity_type_filter AS mtf"
                    " WHERE mtf.role = 'anchor' AND mtf.type_key = a.type_key)"
                    " WHERE d.object_kind = 'associatedData'"
                    " AND EXISTS (SELECT 1 FROM multiplicity_type_filter AS mtf"
                    " WHERE mtf.role = 'data' AND mtf.type_key = d.type_key)"
                    " GROUP BY d.uuid ORDER BY d.uuid"
                )
                if prospective:
                    sql = sql.replace(
                        " GROUP BY",
                        " AND d.uuid IN (SELECT subject_uuid FROM multiplicity_work"
                        " WHERE rule_key = ?)"
                        " GROUP BY",
                    )
                rows = self._connection.execute(sql, (natural_key,) if prospective else ())
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
        """Create one immutable structurally shared definition-set membership."""
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
        self._connection.execute(
            "INSERT INTO definition_set_overlay VALUES (?, ?)",
            (proposed_identity, active_identity),
        )
        self._connection.execute(
            "INSERT OR REPLACE INTO definition_set_type_override"
            " SELECT ?, type_key, operation, value_set_id FROM proposal_definition_type",
            (proposed_identity,),
        )
        self._connection.execute(
            "INSERT OR REPLACE INTO definition_set_relationship_override"
            " SELECT ?, natural_key, operation, value_set_id"
            " FROM proposal_definition_relationship",
            (proposed_identity,),
        )
        return proposed_identity

    def _replace_current_definition_sources_unlocked(self, identity: str) -> None:
        """Rebuild keyed current membership with SQL-sized work and chain-sized memory."""
        chain: list[str] = []
        base = identity
        while True:
            row = self._connection.execute(
                "SELECT base_definition_set_id FROM definition_set_overlay"
                " WHERE definition_set_id = ?",
                (base,),
            ).fetchone()
            if row is None:
                break
            chain.append(base)
            base = str(row[0])
        self._connection.execute("DELETE FROM current_definition_type_source")
        self._connection.execute("DELETE FROM current_definition_relationship_source")
        self._connection.execute(
            "INSERT INTO current_definition_type_source"
            " SELECT type_key, definition_set_id FROM definition_type"
            " WHERE definition_set_id = ?",
            (base,),
        )
        self._connection.execute(
            "INSERT INTO current_definition_relationship_source"
            " SELECT natural_key, definition_set_id FROM definition_multiplicity_rule"
            " WHERE definition_set_id = ?",
            (base,),
        )
        for overlay in reversed(chain):
            self._connection.execute(
                "DELETE FROM current_definition_type_source WHERE type_key IN"
                " (SELECT type_key FROM definition_set_type_override"
                " WHERE definition_set_id = ?)",
                (overlay,),
            )
            self._connection.execute(
                "INSERT INTO current_definition_type_source"
                " SELECT type_key, value_set_id FROM definition_set_type_override"
                " WHERE definition_set_id = ? AND operation = 'upsert'",
                (overlay,),
            )
            self._connection.execute(
                "DELETE FROM current_definition_relationship_source WHERE natural_key IN"
                " (SELECT natural_key FROM definition_set_relationship_override"
                " WHERE definition_set_id = ?)",
                (overlay,),
            )
            self._connection.execute(
                "INSERT INTO current_definition_relationship_source"
                " SELECT natural_key, value_set_id"
                " FROM definition_set_relationship_override"
                " WHERE definition_set_id = ? AND operation = 'upsert'",
                (overlay,),
            )

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
                # Which of these it is decides what the caller does next: assess again,
                # or repair the proposal first. One message covering all of them leaves
                # them re-running an assessment to find out what they were already told.
                reason: str | None = None
                if assessed is None:
                    reason = "no assessment with that identity was ever recorded"
                elif not bool(assessed[3]):
                    reason = (
                        "that assessment found the proposal nonconforming; repair the "
                        "proposal and assess it again"
                    )
                elif str(assessed[1]) != proposed:
                    reason = (
                        "the proposed definitions changed after that assessment; assess "
                        "the current proposal again"
                    )
                elif str(assessed[2]) != overlay:
                    reason = (
                        "the staged graph work changed after that assessment; assess the "
                        "current proposal again"
                    )
                elif int(assessed[0]) != revision:
                    reason = (
                        f"that assessment evaluated revision {int(assessed[0])} and the "
                        f"current revision is {revision}; assess the current proposal again"
                    )
                if reason is not None:
                    self._connection.execute("ROLLBACK")
                    return RevisionedOutcome(
                        OperationStatus.REJECTED,
                        "activation requires the exact current conforming proposal assessment",
                        (ValidationFinding(summary=reason),),
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
                self._connection.execute(
                    "DELETE FROM current_definition_type_source"
                    " WHERE type_key IN (SELECT type_key FROM proposal_definition_type)"
                )
                self._connection.execute(
                    "INSERT INTO current_definition_type_source"
                    " SELECT p.type_key, p.value_set_id FROM proposal_definition_type AS p"
                    " WHERE p.operation = 'upsert'"
                )
                self._connection.execute(
                    "DELETE FROM current_definition_relationship_source"
                    " WHERE natural_key IN"
                    " (SELECT natural_key FROM proposal_definition_relationship)"
                )
                self._connection.execute(
                    "INSERT INTO current_definition_relationship_source"
                    " SELECT p.natural_key, p.value_set_id"
                    " FROM proposal_definition_relationship AS p"
                    " WHERE p.operation = 'upsert'"
                )
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
                content_identity = semantic_identity((proposed, overlay, assessment_id))
                record_identity = self._record_identity(
                    str(ledger[0]),
                    str(previous[0]),
                    resulting,
                    TransitionKind.DEFINITION_ACTIVATION.value,
                    recorded_at,
                    provenance.initiator,
                    provenance.source,
                    str(revision),
                    content_identity,
                )
                self._connection.execute(
                    "INSERT INTO canonical_record (established_revision, ordinal, record_kind,"
                    " recorded_at, initiator, source, summary, prior_revision, record_identity,"
                    " prior_record_identity, content_identity) VALUES (?, ("
                    + NEXT_ORDINAL_SQL
                    + "), ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                        content_identity,
                    ),
                )
                graph_summary = self._connection.execute(
                    "SELECT graph_accumulator, graph_entry_count FROM state_head WHERE id = 0"
                ).fetchone()
                assert graph_summary is not None
                graph_accumulator, graph_count = str(graph_summary[0]), int(graph_summary[1])
                entries = self._connection.execute(
                    "SELECT p.uuid, p.object_kind, p.operation, p.object_value_id,"
                    " base.content_identity, next.content_identity FROM proposal_entry AS p"
                    " LEFT JOIN object_value AS base ON base.id = p.base_object_value_id"
                    " LEFT JOIN object_value AS next ON next.id = p.object_value_id ORDER BY p.uuid"
                )
                for occurrence, (
                    uuid,
                    kind,
                    operation,
                    value_id,
                    base_identity,
                    next_identity,
                ) in enumerate(entries):
                    graph_accumulator, graph_count = adjust_semantic_summary(
                        graph_accumulator,
                        graph_count,
                        removed=(
                            ()
                            if base_identity is None
                            else (graph_entry_digest(str(uuid), str(base_identity)),)
                        ),
                        added=(
                            ()
                            if next_identity is None
                            else (graph_entry_digest(str(uuid), str(next_identity)),)
                        ),
                    )
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
                    " active_definition_set_id = ?, proposed_definition_set_id = NULL,"
                    " graph_accumulator = ?, graph_entry_count = ? WHERE id = 0",
                    (resulting, resulting, proposed, graph_accumulator, graph_count),
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
                self._seal_record_identity_unlocked(resulting)
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
                self._connection.execute("DROP TABLE IF EXISTS temp.restore_candidate")
                self._connection.execute("DROP TABLE IF EXISTS temp.restore_current")
                self._connection.execute("DROP TABLE IF EXISTS temp.restore_target")
                self._connection.execute(
                    "CREATE TEMP TABLE restore_candidate (uuid TEXT PRIMARY KEY)"
                )
                self._connection.execute(
                    "INSERT OR IGNORE INTO restore_candidate"
                    " SELECT uuid FROM canonical_graph_event"
                    " WHERE established_revision > ? AND established_revision <= ?",
                    (selected_revision, int(head[0])),
                )
                self._connection.execute(
                    "CREATE TEMP TABLE restore_current AS"
                    " SELECT c.uuid, v.object_kind, g.object_value_id"
                    " FROM restore_candidate AS c"
                    " CROSS JOIN graph_presence_interval AS g"
                    " INDEXED BY graph_presence_current_uuid"
                    " ON g.uuid = c.uuid AND g.valid_to_revision IS NULL"
                    " JOIN object_value AS v ON v.id = g.object_value_id"
                )
                self._connection.execute(
                    "CREATE UNIQUE INDEX restore_current_uuid ON restore_current(uuid)"
                )
                self._connection.execute(
                    "CREATE TEMP TABLE restore_target AS"
                    " SELECT c.uuid, v.object_kind, p.object_value_id"
                    " FROM restore_candidate AS c"
                    " CROSS JOIN graph_presence_interval AS p"
                    " INDEXED BY graph_presence_uuid_revision ON p.uuid = c.uuid"
                    " JOIN object_value AS v"
                    " ON v.id = p.object_value_id WHERE p.valid_from_revision <= ?"
                    " AND (p.valid_to_revision IS NULL OR p.valid_to_revision > ?)",
                    (selected_revision, selected_revision),
                )
                self._connection.execute(
                    "CREATE UNIQUE INDEX restore_target_uuid ON restore_target(uuid)"
                )
                difference = self._connection.execute(
                    "SELECT uuid, object_value_id FROM (SELECT uuid, object_value_id"
                    " FROM restore_target EXCEPT SELECT uuid, object_value_id"
                    " FROM restore_current) UNION ALL SELECT uuid, object_value_id"
                    " FROM (SELECT uuid, object_value_id FROM restore_current"
                    " EXCEPT SELECT uuid, object_value_id FROM restore_target) LIMIT 1"
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
                content_identity = semantic_identity(
                    ("restore", selected_revision, str(target_definition[0]))
                )
                record_identity = self._record_identity(
                    str(ledger[0]),
                    str(previous[0]),
                    resulting,
                    TransitionKind.HISTORICAL_RESTORATION.value,
                    recorded_at,
                    provenance.initiator,
                    provenance.source,
                    str(revision),
                    content_identity,
                )
                self._connection.execute(
                    "INSERT INTO canonical_record (established_revision, ordinal, record_kind,"
                    " recorded_at, initiator, source, summary, prior_revision, record_identity,"
                    " prior_record_identity, content_identity) VALUES (?, ("
                    + NEXT_ORDINAL_SQL
                    + "), ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                        content_identity,
                    ),
                )
                events = self._connection.execute(
                    "SELECT c.uuid, c.object_kind, 'delete', NULL"
                    " FROM restore_current AS c LEFT JOIN restore_target AS t"
                    " ON t.uuid = c.uuid WHERE t.uuid IS NULL"
                    " UNION ALL SELECT t.uuid, t.object_kind, 'upsert', t.object_value_id"
                    " FROM restore_target AS t LEFT JOIN restore_current AS c"
                    " ON c.uuid = t.uuid WHERE c.object_value_id IS NULL"
                    " OR c.object_value_id != t.object_value_id ORDER BY 1"
                )
                graph_summary = self._connection.execute(
                    "SELECT graph_accumulator, graph_entry_count FROM state_head WHERE id = 0"
                ).fetchone()
                assert graph_summary is not None
                graph_accumulator, graph_count = str(graph_summary[0]), int(graph_summary[1])
                for occurrence, (uuid, kind, operation, value_id) in enumerate(events):
                    prior_identity = self._connection.execute(
                        "SELECT v.content_identity FROM current_graph_object AS c"
                        " JOIN object_value AS v ON v.id = c.object_value_id WHERE c.uuid = ?",
                        (uuid,),
                    ).fetchone()
                    next_identity = (
                        None
                        if value_id is None
                        else self._connection.execute(
                            "SELECT content_identity FROM object_value WHERE id = ?", (value_id,)
                        ).fetchone()
                    )
                    graph_accumulator, graph_count = adjust_semantic_summary(
                        graph_accumulator,
                        graph_count,
                        removed=(
                            ()
                            if prior_identity is None
                            else (graph_entry_digest(str(uuid), str(prior_identity[0])),)
                        ),
                        added=(
                            ()
                            if next_identity is None
                            else (graph_entry_digest(str(uuid), str(next_identity[0])),)
                        ),
                    )
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
                if str(head[1]) != str(target_definition[0]):
                    self._replace_current_definition_sources_unlocked(str(target_definition[0]))
                self._connection.execute(
                    "UPDATE state_head SET revision = ?, established_by = ?,"
                    " active_definition_set_id = ?, graph_accumulator = ?,"
                    " graph_entry_count = ? WHERE id = 0",
                    (
                        resulting,
                        resulting,
                        target_definition[0],
                        graph_accumulator,
                        graph_count,
                    ),
                )
                self._connection.execute(
                    "INSERT INTO canonical_definition_event VALUES (?, ?, 'absent', NULL)",
                    (resulting, target_definition[0]),
                )
                self._seal_record_identity_unlocked(resulting)
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

    def current_revision(self) -> int:
        """Read the established current revision without materializing any state facet."""
        row = self._fetchone("SELECT revision, established_by FROM state_head WHERE id = 0")
        if not isinstance(row, tuple):
            raise NotInitializedError("no canonical state is established")
        revision = _projection_revision(row)
        return revision

    @staticmethod
    def _multiplicity_relationship_shape(value: GraphObject | None) -> object | None:
        """Return only graph meaning that can change a multiplicity contribution."""
        if isinstance(value, Link):
            return ("link", value.type_key, value.source_uuid, value.target_uuid)
        if isinstance(value, AssociatedDataObject):
            # Its type is participant membership, not direct-association identity.
            # Insertion, removal, and anchor-set changes alter the relationship itself.
            return ("association", frozenset(value.anchor_uuids))
        return None

    @staticmethod
    def _multiplicity_participant_shape(value: GraphObject | None) -> object | None:
        if isinstance(value, Anchor):
            return (ObjectKind.ANCHOR.value, value.type_key)
        if isinstance(value, AssociatedDataObject):
            return (ObjectKind.ASSOCIATED_DATA.value, value.type_key)
        return None

    def _objects_from_relation_for_uuids_unlocked(
        self, relation: str, uuids: set[str]
    ) -> tuple[GraphObject, ...]:
        if relation == "current_graph_object":
            return self._objects_for_uuids_unlocked(uuids)
        if relation != "prospective_graph_object":
            raise ValueError("unknown impact object relation")
        objects: list[GraphObject] = []
        for chunk in _sqlite_chunks(self._connection, uuids):
            placeholders = ", ".join("?" for _ in chunk)
            for (value_id,) in self._connection.execute(
                "SELECT object_value_id FROM prospective_graph_object"
                f" WHERE uuid IN ({placeholders})",
                tuple(chunk),
            ):
                objects.append(load_object_value(self._connection, int(value_id)))
        return tuple(objects)

    @staticmethod
    def _referenced_impact_uuids(objects: Iterable[GraphObject]) -> set[str]:
        referenced: set[str] = set()
        for value in objects:
            if isinstance(value, Link):
                referenced.update((value.source_uuid, value.target_uuid))
            elif isinstance(value, AssociatedDataObject):
                referenced.update(value.anchor_uuids)
        return referenced

    def _multiplicity_impact_neighborhood_unlocked(
        self,
        old_changed: dict[str, GraphObject],
        proposed_changed: dict[str, GraphObject],
        *,
        proposed_relation: str | None,
    ) -> ImpactNeighborhood:
        """Load exactly changed/incident relationships and their lookup identities."""
        changed_uuids = set(old_changed) | set(proposed_changed)
        changed_participants = {
            uuid
            for uuid in changed_uuids
            if self._multiplicity_participant_shape(old_changed.get(uuid))
            != self._multiplicity_participant_shape(proposed_changed.get(uuid))
        }
        changed_relationships = {
            uuid
            for uuid in changed_uuids
            if self._multiplicity_relationship_shape(old_changed.get(uuid))
            != self._multiplicity_relationship_shape(proposed_changed.get(uuid))
        }
        relationship_uuids = self._relationship_uuids_for_subjects_unlocked(changed_participants)
        relationship_uuids.update(changed_relationships)

        old_relationships = self._objects_for_uuids_unlocked(relationship_uuids)
        if proposed_relation is None:
            proposed_relationship_map = {value.uuid: value for value in old_relationships}
            for uuid in relationship_uuids:
                if uuid in proposed_changed:
                    proposed_relationship_map[uuid] = proposed_changed[uuid]
                elif uuid in old_changed:
                    proposed_relationship_map.pop(uuid, None)
            proposed_relationships = tuple(proposed_relationship_map.values())
        else:
            proposed_relationships = self._objects_from_relation_for_uuids_unlocked(
                proposed_relation, relationship_uuids
            )

        old_lookup = self._referenced_impact_uuids(old_relationships) | changed_participants
        proposed_lookup = (
            self._referenced_impact_uuids(proposed_relationships) | changed_participants
        )
        old_objects = {
            value.uuid: value
            for value in self._objects_for_uuids_unlocked(old_lookup | relationship_uuids)
        }
        if proposed_relation is None:
            proposed_objects = {
                value.uuid: value
                for value in self._objects_for_uuids_unlocked(proposed_lookup | relationship_uuids)
            }
            for uuid in old_changed:
                proposed_objects.pop(uuid, None)
            proposed_objects.update(proposed_changed)
            proposed_objects.update({value.uuid: value for value in proposed_relationships})
        else:
            proposed_objects = {
                value.uuid: value
                for value in self._objects_from_relation_for_uuids_unlocked(
                    proposed_relation, proposed_lookup | relationship_uuids
                )
            }
        old_objects.update(old_changed)
        proposed_objects.update(proposed_changed)
        return ImpactNeighborhood(
            old_objects,
            proposed_objects,
            frozenset(relationship_uuids),
            frozenset(changed_relationships),
            frozenset(changed_participants),
        )

    def _candidate_multiplicity_rule_keys_unlocked(
        self, neighborhood: ImpactNeighborhood
    ) -> set[str]:
        """Select current rules that have an old/new contribution or subject-membership delta."""
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS multiplicity_link_seed"
            " (link_type_key TEXT, source_type_key TEXT, target_type_key TEXT,"
            " PRIMARY KEY(link_type_key, source_type_key, target_type_key)) WITHOUT ROWID"
        )
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS multiplicity_association_seed"
            " (anchor_type_key TEXT, data_type_key TEXT,"
            " PRIMARY KEY(anchor_type_key, data_type_key)) WITHOUT ROWID"
        )
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS multiplicity_subject_seed"
            " (uuid TEXT PRIMARY KEY, object_kind TEXT, old_type_key TEXT, new_type_key TEXT)"
            " WITHOUT ROWID"
        )
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS multiplicity_subject_type_seed"
            " (uuid TEXT, object_kind TEXT, side TEXT, type_key TEXT,"
            " PRIMARY KEY(uuid, side)) WITHOUT ROWID"
        )
        self._connection.execute("DELETE FROM multiplicity_link_seed")
        self._connection.execute("DELETE FROM multiplicity_association_seed")
        self._connection.execute("DELETE FROM multiplicity_subject_seed")
        self._connection.execute("DELETE FROM multiplicity_subject_type_seed")

        link_seeds: set[tuple[str, str, str]] = set()
        association_seeds: set[tuple[str, str]] = set()
        for objects in (neighborhood.old_objects, neighborhood.proposed_objects):
            for uuid in neighborhood.examined_relationship_uuids:
                relationship = objects.get(uuid)
                if isinstance(relationship, Link):
                    source = objects.get(relationship.source_uuid)
                    target = objects.get(relationship.target_uuid)
                    if isinstance(source, (Anchor, AssociatedDataObject)) and isinstance(
                        target, (Anchor, AssociatedDataObject)
                    ):
                        link_seeds.add((relationship.type_key, source.type_key, target.type_key))
                elif isinstance(relationship, AssociatedDataObject):
                    for anchor_uuid in relationship.anchor_uuids:
                        anchor = objects.get(anchor_uuid)
                        if isinstance(anchor, Anchor):
                            association_seeds.add((anchor.type_key, relationship.type_key))
        self._connection.executemany(
            "INSERT OR IGNORE INTO multiplicity_link_seed VALUES (?, ?, ?)", link_seeds
        )
        self._connection.executemany(
            "INSERT OR IGNORE INTO multiplicity_association_seed VALUES (?, ?)",
            association_seeds,
        )
        subject_seeds = []
        for uuid in neighborhood.changed_participant_uuids:
            old = neighborhood.old_objects.get(uuid)
            proposed = neighborhood.proposed_objects.get(uuid)
            value = proposed if isinstance(proposed, (Anchor, AssociatedDataObject)) else old
            assert isinstance(value, (Anchor, AssociatedDataObject))
            subject_seeds.append(
                (
                    uuid,
                    (
                        ObjectKind.ANCHOR.value
                        if isinstance(value, Anchor)
                        else ObjectKind.ASSOCIATED_DATA.value
                    ),
                    old.type_key if isinstance(old, (Anchor, AssociatedDataObject)) else None,
                    (
                        proposed.type_key
                        if isinstance(proposed, (Anchor, AssociatedDataObject))
                        else None
                    ),
                )
            )
        self._connection.executemany(
            "INSERT INTO multiplicity_subject_seed VALUES (?, ?, ?, ?)", subject_seeds
        )
        self._connection.executemany(
            "INSERT INTO multiplicity_subject_type_seed VALUES (?, ?, ?, ?)",
            (
                (uuid, kind, side, type_key)
                for uuid, kind, old_type, new_type in subject_seeds
                for side, type_key in (("old", old_type), ("new", new_type))
                if type_key is not None
            ),
        )

        if not link_seeds and not association_seeds and not subject_seeds:
            return set()

        keys: set[str] = set()
        if link_seeds:
            keys.update(
                str(row[0])
                for row in self._connection.execute(
                    "SELECT DISTINCT r.natural_key FROM multiplicity_link_seed AS l"
                    " CROSS JOIN definition_multiplicity_participant AS first"
                    " INDEXED BY definition_multiplicity_participant_by_type"
                    " ON first.type_key IN (l.source_type_key, l.target_type_key)"
                    " AND first.role = 'first'"
                    " JOIN definition_multiplicity_rule AS r"
                    " ON r.definition_set_id = first.definition_set_id"
                    " AND r.occurrence = first.rule_occurrence"
                    " JOIN current_definition_relationship_source AS s"
                    " ON s.natural_key = r.natural_key"
                    " AND s.value_set_id = r.definition_set_id"
                    " WHERE r.rule_kind = 'linkMultiplicity'"
                    " AND r.link_type_key = l.link_type_key"
                    " AND ((r.constrained_end = 'source'"
                    " AND first.type_key = l.source_type_key"
                    " AND EXISTS (SELECT 1 FROM definition_multiplicity_participant AS p"
                    " WHERE p.definition_set_id = r.definition_set_id"
                    " AND p.rule_occurrence = r.occurrence AND p.role = 'second'"
                    " AND p.type_key = l.target_type_key))"
                    " OR (r.constrained_end = 'target'"
                    " AND first.type_key = l.target_type_key"
                    " AND EXISTS (SELECT 1 FROM definition_multiplicity_participant AS p"
                    " WHERE p.definition_set_id = r.definition_set_id"
                    " AND p.rule_occurrence = r.occurrence AND p.role = 'second'"
                    " AND p.type_key = l.source_type_key)))"
                )
            )
        if association_seeds:
            keys.update(
                str(row[0])
                for row in self._connection.execute(
                    "SELECT DISTINCT r.natural_key FROM multiplicity_association_seed AS a"
                    " CROSS JOIN definition_multiplicity_participant AS first"
                    " INDEXED BY definition_multiplicity_participant_by_type"
                    " ON first.type_key = a.anchor_type_key AND first.role = 'first'"
                    " JOIN definition_multiplicity_rule AS r"
                    " ON r.definition_set_id = first.definition_set_id"
                    " AND r.occurrence = first.rule_occurrence"
                    " JOIN current_definition_relationship_source AS s"
                    " ON s.natural_key = r.natural_key"
                    " AND s.value_set_id = r.definition_set_id"
                    " WHERE r.rule_kind = 'directAssociationMultiplicity'"
                    " AND EXISTS (SELECT 1 FROM definition_multiplicity_participant AS p"
                    " WHERE p.definition_set_id = r.definition_set_id"
                    " AND p.rule_occurrence = r.occurrence AND p.role = 'second'"
                    " AND p.type_key = a.data_type_key)"
                )
            )
        if subject_seeds:
            keys.update(
                str(row[0])
                for row in self._connection.execute(
                    "SELECT DISTINCT r.natural_key"
                    " FROM multiplicity_subject_type_seed AS t"
                    " CROSS JOIN definition_multiplicity_participant AS p"
                    " INDEXED BY definition_multiplicity_participant_by_type"
                    " ON p.type_key = t.type_key"
                    " JOIN definition_multiplicity_rule AS r"
                    " ON r.definition_set_id = p.definition_set_id"
                    " AND r.occurrence = p.rule_occurrence"
                    " JOIN current_definition_relationship_source AS s"
                    " ON s.natural_key = r.natural_key"
                    " AND s.value_set_id = r.definition_set_id"
                    " JOIN multiplicity_subject_seed AS c ON c.uuid = t.uuid"
                    " WHERE p.role = CASE WHEN r.rule_kind = 'linkMultiplicity'"
                    " OR r.constrained_end = 'anchor' THEN 'first' ELSE 'second' END"
                    " AND (r.rule_kind = 'linkMultiplicity'"
                    " OR (r.rule_kind = 'directAssociationMultiplicity'"
                    " AND ((r.constrained_end = 'anchor' AND c.object_kind = 'anchor')"
                    " OR (r.constrained_end = 'associatedData'"
                    " AND c.object_kind = 'associatedData'))))"
                    " AND (EXISTS (SELECT 1 FROM definition_multiplicity_participant AS x"
                    " WHERE x.definition_set_id = r.definition_set_id"
                    " AND x.rule_occurrence = r.occurrence AND x.role = p.role"
                    " AND x.type_key = c.old_type_key)"
                    " != EXISTS (SELECT 1 FROM definition_multiplicity_participant AS x"
                    " WHERE x.definition_set_id = r.definition_set_id"
                    " AND x.rule_occurrence = r.occurrence AND x.role = p.role"
                    " AND x.type_key = c.new_type_key))"
                )
            )
        return keys

    def _prepare_active_multiplicity_impact_unlocked(
        self,
        active_identity: str,
        old_changed: dict[str, GraphObject],
        proposed_changed: dict[str, GraphObject],
    ) -> tuple[ImpactNeighborhood, GraphDefinitionSet]:
        self._clear_multiplicity_impact_unlocked()
        neighborhood = self._multiplicity_impact_neighborhood_unlocked(
            old_changed, proposed_changed, proposed_relation=None
        )
        candidate_keys = self._candidate_multiplicity_rule_keys_unlocked(neighborhood)
        definitions = self._load_definition_set(
            active_identity,
            type_keys=set(),
            relationship_keys=candidate_keys,
        )
        self._record_multiplicity_reasons_unlocked(
            derive_multiplicity_impact_reasons(neighborhood, definitions.relationship_constraints)
        )
        self._connection.execute(
            "INSERT INTO multiplicity_work"
            " SELECT DISTINCT rule_key, subject_uuid, constrained_end"
            " FROM multiplicity_impact_reason"
        )
        return neighborhood, definitions

    def _active_multiplicity_evaluation_objects_unlocked(
        self,
        old_changed: dict[str, GraphObject],
        proposed_changed: dict[str, GraphObject],
        changed_relationships: frozenset[str],
    ) -> tuple[dict[str, GraphObject], frozenset[str]]:
        subject_uuids = {
            str(row[0])
            for row in self._connection.execute(
                "SELECT DISTINCT subject_uuid FROM multiplicity_work"
            )
        }
        relationship_uuids = self._relationship_uuids_for_subjects_unlocked(subject_uuids)
        relationship_uuids.update(changed_relationships)
        current_relationships = self._objects_for_uuids_unlocked(relationship_uuids)
        proposed_relationships = {value.uuid: value for value in current_relationships}
        for uuid in relationship_uuids:
            if uuid in proposed_changed:
                proposed_relationships[uuid] = proposed_changed[uuid]
            elif uuid in old_changed:
                proposed_relationships.pop(uuid, None)
        referenced = self._referenced_impact_uuids(proposed_relationships.values())
        objects = {
            value.uuid: value
            for value in self._objects_for_uuids_unlocked(
                subject_uuids | relationship_uuids | referenced
            )
        }
        for uuid in old_changed:
            objects.pop(uuid, None)
        objects.update(proposed_changed)
        objects.update(proposed_relationships)
        return objects, frozenset(relationship_uuids)

    def _active_multiplicity_findings_unlocked(
        self,
        definitions: GraphDefinitionSet,
        objects: dict[str, GraphObject],
        relationship_uuids: frozenset[str],
    ) -> tuple[ValidationFinding, ...]:
        findings: list[ValidationFinding] = []
        facts = index_multiplicity_facts(objects)
        for constraint in definitions.relationship_constraints:
            natural_key = semantic_identity(relationship_identity(constraint))
            subjects = frozenset(
                str(row[0])
                for row in self._connection.execute(
                    "SELECT subject_uuid FROM multiplicity_work WHERE rule_key = ?",
                    (natural_key,),
                )
            )
            counts = count_multiplicity_for_subjects(
                constraint, facts, subjects, relationship_uuids
            )
            for uuid, count in sorted(counts.items()):
                if count >= constraint.lower_bound and (
                    constraint.upper_bound is None or count <= constraint.upper_bound
                ):
                    continue
                bound = (
                    f"{constraint.lower_bound}.."
                    f"{'*' if constraint.upper_bound is None else constraint.upper_bound}"
                )
                if isinstance(constraint, LinkMultiplicityConstraint):
                    value = objects[uuid]
                    summary = (
                        f"{value.type_key} {uuid!r} participates in {count}"
                        f" {constraint.link_type_key!r} links at its"
                        f" {constraint.constrained_end.value} end, outside {bound}"
                    )
                else:
                    subject = (
                        "anchor"
                        if constraint.constrained_end is DirectAssociationEnd.ANCHOR
                        else "associated data"
                    )
                    summary = (
                        f"{subject} {uuid!r} has {count} matching direct associations,"
                        f" outside {bound}"
                    )
                findings.append(
                    ValidationFinding(
                        summary=summary,
                        implicated_definitions=(relationship_label(constraint),),
                        implicated_objects=(uuid,),
                    )
                )
        return tuple(findings)

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
                    result = self._prepare_active_graph_change_unlocked(change)
                    self._connection.execute("COMMIT")
                    return result
                except BaseException:
                    self._rollback_quietly()
                    raise
        except sqlite3.Error as error:
            raise StoreError(
                f"could not validate a graph change at {self._path}: {error}"
            ) from error

    def _prepare_active_graph_change_unlocked(
        self, change: GraphChange
    ) -> tuple[
        int,
        tuple[ValidationFinding, ...],
        tuple[ValidationFinding, ...],
        bool,
    ]:
        """Validate one active change inside the caller's existing transaction."""
        head = self._connection.execute(
            "SELECT revision, established_by, active_definition_set_id FROM state_head WHERE id = 0"
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
        structural_objects = self._objects_for_uuids_unlocked(structural_ids)
        structural = change_findings(change, structural_objects)
        if structural:
            return revision, structural, (), False

        existing_touched = {
            value.uuid: value for value in structural_objects if value.uuid in touched
        }
        proposed_changed = {value.uuid: value for _, value in change.upserts()}
        impact, multiplicity_definitions = self._prepare_active_multiplicity_impact_unlocked(
            str(head[2]), existing_touched, proposed_changed
        )
        unchanged_proposed_lookups = (
            value for uuid, value in impact.proposed_objects.items() if uuid not in proposed_changed
        )
        current_neighborhood = _merge_objects(
            _merge_objects(structural_objects, impact.old_objects.values()),
            unchanged_proposed_lookups,
        )
        structural_references = self._referenced_impact_uuids(
            (*current_neighborhood, *proposed_changed.values())
        )
        known = {value.uuid for value in current_neighborhood}
        current_neighborhood = _merge_objects(
            current_neighborhood,
            self._objects_for_uuids_unlocked(structural_references - known),
        )
        resulting = apply_change_to_objects(current_neighborhood, change)
        structural_subjects = set(touched) | set(impact.examined_relationship_uuids)
        type_keys = {value.type_key for value in resulting}
        definitions = self._load_definition_set(
            str(head[2]),
            type_keys=type_keys,
            constrained_type_keys=set(),
            relationship_keys=set(),
        )
        structural_conformance = tuple(
            finding
            for finding in assess_object_neighborhood(
                resulting, definitions, include_multiplicity=False
            )
            if set(finding.implicated_objects) & structural_subjects
        )
        multiplicity_objects, multiplicity_relationships = (
            self._active_multiplicity_evaluation_objects_unlocked(
                existing_touched,
                proposed_changed,
                impact.changed_relationship_uuids,
            )
        )
        multiplicity_conformance = self._active_multiplicity_findings_unlocked(
            multiplicity_definitions,
            multiplicity_objects,
            multiplicity_relationships,
        )
        no_op = {value.uuid: object_identity(value) for value in resulting} == {
            value.uuid: object_identity(value) for value in current_neighborhood
        }
        return revision, (), (*structural_conformance, *multiplicity_conformance), no_op

    def _objects_for_uuids_unlocked(self, uuids: set[str]) -> tuple[GraphObject, ...]:
        objects: list[GraphObject] = []
        for chunk in _sqlite_chunks(self._connection, uuids):
            placeholders = ", ".join("?" for _ in chunk)
            rows = self._connection.execute(
                "SELECT uuid, object_kind, type_key, source_uuid, target_uuid,"
                " object_value_id FROM current_graph_object"
                f" WHERE uuid IN ({placeholders})",
                tuple(chunk),
            )
            objects.extend(self._decode_current_graph_object(*row) for row in rows)
        return tuple(objects)

    def _referencing_uuids_unlocked(self, uuids: set[str]) -> set[str]:
        references: set[str] = set()
        for chunk in _sqlite_chunks(self._connection, uuids, repetitions=2):
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

    def _relationship_uuids_for_subjects_unlocked(self, subjects: set[str]) -> set[str]:
        """Return direct relationship objects only; their other ends remain lookups."""
        relationships = self._referencing_uuids_unlocked(subjects)
        for chunk in _sqlite_chunks(self._connection, subjects):
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

    # --- Owned history base ---------------------------------------------------------

    def initialize_empty(
        self,
        definition_entries: Iterable[DefinitionEntry],
        *,
        provenance: Provenance,
        initialization_summary: str,
        recorded_at: datetime,
    ) -> None:
        """Establish an empty revision-zero history base as one atomic effect.

        Nothing is established when the store already holds canonical state, and a
        failure part-way through leaves no partial canonical or activity state.
        """
        self._initialize_base(
            False,
            definition_entries,
            revision=0,
            provenance=provenance,
            initialization_summary=initialization_summary,
            recorded_at=recorded_at,
        )

    def initialize_staged_recovery_identity(
        self,
        active_definition_identity: str,
        *,
        provenance: Provenance,
        initialization_summary: str,
        recorded_at: datetime,
    ) -> None:
        """Establish staged graph rows with an already-normalized definition set."""
        self._initialize_base(
            True,
            None,
            active_definition_identity=active_definition_identity,
            revision=0,
            provenance=provenance,
            initialization_summary=initialization_summary,
            recorded_at=recorded_at,
        )

    def _initialize_base(
        self,
        use_staged_graph: bool,
        definition_entries: Iterable[DefinitionEntry] | None,
        *,
        active_definition_identity: str | None = None,
        revision: int,
        provenance: Provenance,
        initialization_summary: str,
        recorded_at: datetime,
    ) -> None:
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
                if definition_entries is not None:
                    try:
                        active_identity = insert_definition_entries(
                            self._connection, definition_entries
                        )
                    except (OverflowError, UnicodeError, ValueError) as error:
                        reason = (
                            "contains a numeric bound too large to be stored"
                            if isinstance(error, OverflowError)
                            else f"cannot be stored: {error}"
                        )
                        raise InvalidInitialDefinitionsError(
                            (ValidationFinding(summary=f"an initial definition {reason}"),)
                        ) from error
                elif (
                    active_definition_identity is not None
                    and self._connection.execute(
                        "SELECT 1 FROM definition_set WHERE identity = ?",
                        (active_definition_identity,),
                    ).fetchone()
                ):
                    active_identity = active_definition_identity
                else:
                    raise StoreError("the normalized initial definition set is absent")
                self._connection.execute(
                    "INSERT INTO current_definition_type_source"
                    " SELECT type_key, definition_set_id FROM definition_type"
                    " WHERE definition_set_id = ?",
                    (active_identity,),
                )
                self._connection.execute(
                    "INSERT INTO current_definition_relationship_source"
                    " SELECT natural_key, definition_set_id FROM definition_multiplicity_rule"
                    " WHERE definition_set_id = ?",
                    (active_identity,),
                )
                content_identity = semantic_identity(("pendingInitialState", secrets.token_hex(16)))
                record_identity = self._record_identity(
                    ledger_identity,
                    None,
                    revision,
                    "initial",
                    recorded_at,
                    provenance.initiator,
                    provenance.source,
                    initialization_summary,
                    content_identity,
                )
                self._connection.execute(
                    "INSERT INTO canonical_record (established_revision, ordinal, record_kind,"
                    " recorded_at, initiator, source, summary, prior_revision, record_identity,"
                    " prior_record_identity, content_identity)"
                    " VALUES (?, 0, 'initial', ?, ?, ?, ?, NULL, ?, NULL, ?)",
                    (
                        revision,
                        _stored_time(recorded_at),
                        provenance.initiator,
                        provenance.source,
                        initialization_summary,
                        record_identity,
                        content_identity,
                    ),
                )
                self._connection.execute(
                    "INSERT INTO state_head"
                    " (id, revision, established_by, active_definition_set_id,"
                    " proposed_definition_set_id, graph_entry_count, graph_accumulator)"
                    " VALUES (0, ?, ?, ?, ?, 0, ?)",
                    (
                        revision,
                        revision,
                        active_identity,
                        None,
                        "0" * 64,
                    ),
                )
                if use_staged_graph:
                    self._connection.execute(
                        "INSERT INTO graph_presence_interval"
                        " (uuid, object_value_id, object_kind, type_key, source_uuid, target_uuid,"
                        " valid_from_revision, valid_to_revision)"
                        " SELECT r.uuid, r.object_value_id, v.object_kind, v.type_key,"
                        " v.source_uuid, v.target_uuid, ?, NULL FROM recovery_object AS r"
                        " JOIN object_value AS v ON v.id = r.object_value_id",
                        (revision,),
                    )
                    graph_count, graph_accumulator = recomputed_graph_summary(self._connection)
                    self._connection.execute(
                        "UPDATE state_head SET graph_entry_count = ?, graph_accumulator = ?"
                        " WHERE id = 0",
                        (graph_count, graph_accumulator),
                    )
                self._connection.execute(
                    "INSERT INTO canonical_definition_event"
                    " (established_revision, active_definition_set_id, delta_disposition,"
                    " proposed_definition_set_id)"
                    " VALUES (?, ?, ?, ?)",
                    (
                        revision,
                        active_identity,
                        "absent",
                        None,
                    ),
                )
                definition_findings = tuple(
                    self._iter_definition_findings_unlocked("current_graph_object", active_identity)
                )
                if definition_findings:
                    raise InvalidInitialDefinitionsError(definition_findings)
                self._seal_record_identity_unlocked(revision)
                # A read attempted before the system existed may already have observed itself
                # here, and success promises an empty ledger.
                self._connection.execute("DELETE FROM activity_record")
                self._connection.execute("COMMIT")
            except AlreadyInitializedError:
                raise
            except InvalidInitialDefinitionsError:
                self._rollback_quietly()
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

    def _record_event_identity_unlocked(self, revision: int, kind: str) -> str:
        """Derive one bounded commitment from normalized events, never an assertion."""
        graph_events = semantic_row_summary(
            (
                int(occurrence),
                str(operation),
                str(object_kind),
                str(uuid),
                None if identity is None else str(identity),
            )
            for occurrence, operation, object_kind, uuid, identity in self._connection.execute(
                "SELECT g.occurrence, g.operation, g.object_kind, g.uuid, v.content_identity"
                " FROM canonical_graph_event AS g LEFT JOIN object_value AS v"
                " ON v.id = g.object_value_id WHERE g.established_revision = ?"
                " ORDER BY g.occurrence",
                (revision,),
            )
        )
        proposal_events = semantic_row_summary(
            (
                int(occurrence),
                str(operation),
                str(object_kind),
                str(uuid),
                None if identity is None else str(identity),
            )
            for occurrence, operation, object_kind, uuid, identity in self._connection.execute(
                "SELECT p.occurrence, p.operation, p.object_kind, p.uuid, v.content_identity"
                " FROM canonical_proposal_event AS p LEFT JOIN object_value AS v"
                " ON v.id = p.object_value_id WHERE p.established_revision = ?"
                " ORDER BY p.occurrence",
                (revision,),
            )
        )
        definition_proposal_events = semantic_row_summary(
            (
                int(occurrence),
                str(entity_kind),
                str(natural_key),
                str(operation),
                None if value_set_id is None else str(value_set_id),
            )
            for (
                occurrence,
                entity_kind,
                natural_key,
                operation,
                value_set_id,
            ) in self._connection.execute(
                "SELECT occurrence, entity_kind, natural_key, operation, value_set_id"
                " FROM canonical_definition_proposal_event WHERE established_revision = ?"
                " ORDER BY occurrence",
                (revision,),
            )
        )
        definition_event = self._connection.execute(
            "SELECT active_definition_set_id, delta_disposition, proposed_definition_set_id"
            " FROM canonical_definition_event WHERE established_revision = ?",
            (revision,),
        ).fetchone()
        base_graph: tuple[int, str] = (0, "0" * 64)
        if kind == "initial":
            base_graph = semantic_row_summary(
                (str(uuid), str(identity))
                for uuid, identity in self._connection.execute(
                    "SELECT p.uuid, v.content_identity FROM graph_presence_interval AS p"
                    " JOIN object_value AS v ON v.id = p.object_value_id"
                    " WHERE p.valid_from_revision = ? ORDER BY p.uuid",
                    (revision,),
                )
            )
        return semantic_identity(
            (
                "canonicalEvents",
                kind,
                base_graph,
                graph_events,
                proposal_events,
                definition_proposal_events,
                None if definition_event is None else tuple(definition_event),
            )
        )

    def _seal_record_identity_unlocked(self, revision: int) -> None:
        row = self._connection.execute(
            "SELECT r.record_kind, r.recorded_at, r.initiator, r.source, r.summary,"
            " r.prior_record_identity, l.identity FROM canonical_record AS r CROSS JOIN ledger AS l"
            " WHERE r.established_revision = ? AND l.id = 0",
            (revision,),
        ).fetchone()
        if row is None:
            raise StoreError(f"revision {revision} has no record to seal")
        kind, recorded_at, initiator, source, summary, prior_identity, ledger_identity = row
        resulting_state_identity = normalized_state_identity(self._connection)
        event_identity = self._record_event_identity_unlocked(revision, str(kind))
        content_identity = semantic_identity(
            ("canonicalRecordContent", event_identity, resulting_state_identity)
        )
        record_identity = self._record_identity(
            str(ledger_identity),
            None if prior_identity is None else str(prior_identity),
            revision,
            str(kind),
            self._recorded_at(str(recorded_at)),
            str(initiator),
            None if source is None else str(source),
            str(summary),
            content_identity,
        )
        self._connection.execute(
            "UPDATE canonical_record SET content_identity = ?, record_identity = ?,"
            " resulting_state_identity = ?, event_identity = ?"
            " WHERE established_revision = ?",
            (
                content_identity,
                record_identity,
                resulting_state_identity,
                event_identity,
                revision,
            ),
        )

    def _apply_current_graph_change_unlocked(self, change: GraphChange, revision: int) -> None:
        removals = tuple(uuid for _, uuid in change.removals())
        replaced = (*removals, *(value.uuid for _, value in change.upserts()))
        summary = self._connection.execute(
            "SELECT graph_accumulator, graph_entry_count FROM state_head WHERE id = 0"
        ).fetchone()
        if summary is None:
            raise StoreError("the current graph has no maintained semantic summary")
        accumulator, entry_count = str(summary[0]), int(summary[1])
        if replaced:
            removed: list[str] = []
            for chunk in _sqlite_chunks(self._connection, set(replaced)):
                placeholders = ", ".join("?" for _ in chunk)
                removed.extend(
                    graph_entry_digest(str(uuid), str(identity))
                    for uuid, identity in self._connection.execute(
                        "SELECT c.uuid, v.content_identity FROM current_graph_object AS c"
                        " JOIN object_value AS v ON v.id = c.object_value_id"
                        f" WHERE c.uuid IN ({placeholders})",
                        chunk,
                    )
                )
            accumulator, entry_count = adjust_semantic_summary(
                accumulator, entry_count, removed=removed
            )
            for chunk in _sqlite_chunks(self._connection, set(replaced), reserved=1):
                placeholders = ", ".join("?" for _ in chunk)
                self._connection.execute(
                    f"UPDATE graph_presence_interval SET valid_to_revision = ?"
                    f" WHERE valid_to_revision IS NULL AND uuid IN ({placeholders})",
                    (revision, *chunk),
                )
        for _, graph_object in change.upserts():
            self._upsert_current_graph_object_unlocked(graph_object, revision)
            accumulator, entry_count = adjust_semantic_summary(
                accumulator,
                entry_count,
                added=(graph_entry_digest(graph_object.uuid, object_identity(graph_object)),),
            )
        self._connection.execute(
            "UPDATE state_head SET graph_accumulator = ?, graph_entry_count = ? WHERE id = 0",
            (accumulator, entry_count),
        )

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

    def _append_transition(self, record: CanonicalTransitionRecord) -> None:
        """Append one transition and update the projection as one recoverable effect.

        The appended record and the updated projection commit together, so no reader can
        observe a revision established by one without the state established by the other.
        The prior revision is re-checked inside the transaction, so two writers cannot
        both believe they are advancing from it.
        """
        projection_assignments = ["revision = ?", "established_by = ?"]
        projection_values: list[object] = [record.resulting_revision, record.resulting_revision]
        if record.change.delta_disposition is DefinitionDeltaDisposition.ABSENT:
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
                if record.change.delta_disposition is DefinitionDeltaDisposition.ABSENT:
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
                content_identity = _change_identity(record.change)
                record_identity = self._record_identity(
                    str(ledger_row[0]),
                    prior_identity,
                    record.resulting_revision,
                    record.kind.value,
                    record.recorded_at,
                    record.provenance.initiator,
                    record.provenance.source,
                    str(record.prior_revision),
                    content_identity,
                )
                self._connection.execute(
                    "INSERT INTO canonical_record (established_revision, ordinal, record_kind,"
                    " recorded_at, initiator, source, summary, prior_revision, record_identity,"
                    " prior_record_identity, content_identity)"
                    f" VALUES (?, ({NEXT_ORDINAL_SQL}), ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                        content_identity,
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
                self._connection.execute(
                    "INSERT INTO canonical_definition_event"
                    " (established_revision, active_definition_set_id, delta_disposition,"
                    " proposed_definition_set_id)"
                    " VALUES (?, ?, ?, ?)",
                    (
                        record.resulting_revision,
                        None,
                        record.change.delta_disposition.value,
                        None,
                    ),
                )
                self._seal_record_identity_unlocked(record.resulting_revision)
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

    def verify_projection_from_ledger(self) -> tuple[ValidationFinding, ...]:
        """Rebuild expected projection in temporary SQL and compare in both directions."""
        with self._lock:
            try:
                self._connection.execute("BEGIN")
                findings: list[ValidationFinding] = []
                ledger = self._connection.execute(
                    "SELECT identity FROM ledger WHERE id = 0"
                ).fetchone()
                previous_revision: int | None = None
                previous_identity: str | None = None
                record_count = 0
                allowed_kinds = {kind.value for kind in TransitionKind}
                for row in self._connection.execute(
                    "SELECT ordinal, established_revision, record_kind, recorded_at, initiator,"
                    " source, summary, prior_revision, record_identity, prior_record_identity,"
                    " content_identity, resulting_state_identity, event_identity"
                    " FROM canonical_record ORDER BY ordinal"
                ):
                    (
                        ordinal,
                        revision,
                        kind,
                        recorded_at,
                        initiator,
                        source,
                        summary,
                        prior_revision,
                        record_identity,
                        prior_record_identity,
                        content_identity,
                        resulting_state_identity,
                        event_identity,
                    ) = row
                    ordinal, revision = int(ordinal), int(revision)
                    structural_error: str | None = None
                    if ordinal != record_count:
                        structural_error = "canonical record ordinals are not contiguous"
                    elif ordinal == 0 and (
                        kind != "initial"
                        or prior_revision is not None
                        or prior_record_identity is not None
                    ):
                        structural_error = (
                            "canonical history does not begin with one initial record"
                        )
                    elif ordinal > 0 and (
                        kind not in allowed_kinds
                        or previous_revision is None
                        or revision != previous_revision + 1
                        or prior_revision != previous_revision
                        or prior_record_identity != previous_identity
                    ):
                        structural_error = "canonical transition lineage is not contiguous"
                    if ledger is None:
                        structural_error = "canonical history has no ledger identity"
                    else:
                        actual_event = self._record_event_identity_unlocked(revision, str(kind))
                        actual_content = semantic_identity(
                            (
                                "canonicalRecordContent",
                                actual_event,
                                str(resulting_state_identity),
                            )
                        )
                        if actual_event != str(event_identity) or actual_content != str(
                            content_identity
                        ):
                            structural_error = (
                                "canonical record content does not match its normalized events"
                            )
                        expected_identity = self._record_identity(
                            str(ledger[0]),
                            None if prior_record_identity is None else str(prior_record_identity),
                            revision,
                            str(kind),
                            self._recorded_at(str(recorded_at)),
                            str(initiator),
                            None if source is None else str(source),
                            str(summary),
                            str(content_identity),
                        )
                        if expected_identity != str(record_identity):
                            structural_error = (
                                "canonical record identity does not bind its content and lineage"
                            )
                    event_counts: dict[str, int] = {}
                    for table in (
                        "canonical_graph_event",
                        "canonical_proposal_event",
                        "canonical_definition_proposal_event",
                    ):
                        event_row = self._connection.execute(
                            f"SELECT count(*), min(occurrence), max(occurrence) FROM {table}"
                            " WHERE established_revision = ?",
                            (revision,),
                        ).fetchone()
                        assert event_row is not None
                        event_count = int(event_row[0])
                        event_counts[table] = event_count
                        if event_count and (
                            int(event_row[1]) != 0 or int(event_row[2]) != event_count - 1
                        ):
                            structural_error = (
                                "canonical event occurrences are not complete and contiguous"
                            )
                    definition_event = self._connection.execute(
                        "SELECT active_definition_set_id, delta_disposition,"
                        " proposed_definition_set_id FROM canonical_definition_event"
                        " WHERE established_revision = ?",
                        (revision,),
                    ).fetchone()
                    if definition_event is None:
                        structural_error = "canonical record has no definition disposition event"
                    elif kind == "initial":
                        if definition_event[0] is None or definition_event[1] not in {
                            "absent",
                            "present",
                        }:
                            structural_error = "initial record has incompatible definition events"
                    elif kind == TransitionKind.GRAPH_MUTATION.value:
                        if (
                            event_counts["canonical_proposal_event"]
                            or event_counts["canonical_definition_proposal_event"]
                            or tuple(definition_event) != (None, "unchanged", None)
                        ):
                            structural_error = "graph mutation has incompatible event families"
                    elif kind == TransitionKind.DEFINITION_DELTA_CHANGE.value:
                        if event_counts["canonical_graph_event"] or definition_event[0] is not None:
                            structural_error = (
                                "definition-delta change has incompatible event families"
                            )
                    elif kind in {
                        TransitionKind.DEFINITION_ACTIVATION.value,
                        TransitionKind.HISTORICAL_RESTORATION.value,
                    }:
                        if (
                            event_counts["canonical_proposal_event"]
                            or event_counts["canonical_definition_proposal_event"]
                            or definition_event[0] is None
                            or tuple(definition_event[1:]) != ("absent", None)
                        ):
                            structural_error = (
                                "activation or restoration has incompatible event families"
                            )
                    if structural_error is not None:
                        findings.append(ValidationFinding(summary=structural_error))
                        break
                    previous_revision = revision
                    previous_identity = str(record_identity)
                    record_count += 1
                head_record = self._connection.execute(
                    "SELECT h.revision, r.record_identity, r.resulting_state_identity"
                    " FROM state_head AS h"
                    " JOIN canonical_record AS r ON r.established_revision = h.established_by"
                    " WHERE h.id = 0"
                ).fetchone()
                summary_error = verify_state_summaries(
                    self._connection
                ) or verify_proposal_summaries(self._connection)
                if not findings and summary_error is not None:
                    findings.append(ValidationFinding(summary=summary_error))
                proposal_summary = self._connection.execute(
                    "SELECT effective_accumulator, effective_entry_count, identity"
                    " FROM proposal_definition_state WHERE id = 0"
                ).fetchone()
                head_proposal = self._connection.execute(
                    "SELECT proposed_definition_set_id FROM state_head WHERE id = 0"
                ).fetchone()
                if not findings and proposal_summary is not None:
                    if proposal_summary[2] is None:
                        if proposal_summary[0] is not None or proposal_summary[1] is not None:
                            findings.append(
                                ValidationFinding(
                                    summary="absent proposal retains effective definition summary"
                                )
                            )
                    else:
                        actual_proposal = proposal_definition_stats_from_storage(self._connection)
                        if (
                            (
                                str(proposal_summary[0]),
                                int(proposal_summary[1]),
                            )
                            != actual_proposal
                            or head_proposal is None
                            or str(head_proposal[0]) != str(proposal_summary[2])
                        ):
                            findings.append(
                                ValidationFinding(
                                    summary=(
                                        "proposal effective definition summary does not match"
                                        " normalized state"
                                    )
                                )
                            )
                if not findings and (
                    record_count == 0
                    or head_record is None
                    or int(head_record[0]) != previous_revision
                    or str(head_record[1]) != previous_identity
                    or str(head_record[2]) != normalized_state_identity(self._connection)
                ):
                    findings.append(
                        ValidationFinding(
                            summary=(
                                "the state head is not established by the final canonical record"
                            )
                        )
                    )
                invalid_event = self._connection.execute(
                    "SELECT g.uuid FROM canonical_graph_event AS g"
                    " LEFT JOIN object_value AS v ON v.id = g.object_value_id"
                    " WHERE g.operation NOT IN ('upsert', 'delete')"
                    " OR (g.operation = 'upsert' AND (v.id IS NULL OR v.uuid != g.uuid"
                    " OR v.object_kind != g.object_kind))"
                    " OR (g.operation = 'delete' AND g.object_value_id IS NOT NULL) LIMIT 1"
                ).fetchone()
                if not findings and invalid_event is not None:
                    findings.append(
                        ValidationFinding(
                            summary="a canonical graph event is invalid or kind-incompatible",
                            implicated_objects=(str(invalid_event[0]),),
                        )
                    )
                invalid_proposal_event = self._connection.execute(
                    "SELECT e.uuid FROM canonical_proposal_event AS e"
                    " LEFT JOIN object_value AS v ON v.id = e.object_value_id WHERE"
                    " e.operation NOT IN ('upsert', 'delete', 'unstage')"
                    " OR e.object_kind NOT IN ('anchor', 'associatedData', 'link')"
                    " OR (e.operation = 'upsert' AND (v.id IS NULL OR v.uuid != e.uuid"
                    " OR v.object_kind != e.object_kind))"
                    " OR (e.operation IN ('delete', 'unstage')"
                    " AND e.object_value_id IS NOT NULL) LIMIT 1"
                ).fetchone()
                if not findings and invalid_proposal_event is not None:
                    findings.append(
                        ValidationFinding(
                            summary="a canonical proposal event is invalid or kind-incompatible",
                            implicated_objects=(str(invalid_proposal_event[0]),),
                        )
                    )
                if not findings:
                    for (
                        entity_kind,
                        natural_key,
                        operation,
                        value_set_id,
                    ) in self._connection.execute(
                        "SELECT entity_kind, natural_key, operation, value_set_id"
                        " FROM canonical_definition_proposal_event"
                    ):
                        definition_error = False
                        if entity_kind not in {"type", "relationship"} or operation not in {
                            "upsert",
                            "delete",
                            "unstage",
                        }:
                            definition_error = True
                        elif operation != "upsert":
                            definition_error = value_set_id is not None
                        elif value_set_id is None:
                            definition_error = True
                        else:
                            value = self._load_definition_set(str(value_set_id), one_entry=True)
                            if definition_content_stats(value)[1] != 1:
                                definition_error = True
                            elif entity_kind == "type":
                                types = (
                                    *value.anchor_types,
                                    *value.associated_data_types,
                                    *value.link_types,
                                )
                                definition_error = len(types) != 1 or types[0].type_key != str(
                                    natural_key
                                )
                            else:
                                relationships = value.relationship_constraints
                                definition_error = len(relationships) != 1 or semantic_identity(
                                    relationship_identity(relationships[0])
                                ) != str(natural_key)
                        if definition_error:
                            findings.append(
                                ValidationFinding(
                                    summary=(
                                        "a canonical definition-proposal event is invalid or"
                                        " key-incompatible"
                                    )
                                )
                            )
                            break
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
                    "SELECT uuid, object_value_id FROM (SELECT uuid, object_value_id"
                    " FROM replay_expected EXCEPT SELECT uuid, object_value_id"
                    " FROM current_graph_object) UNION ALL SELECT uuid, object_value_id"
                    " FROM (SELECT uuid, object_value_id FROM current_graph_object"
                    " EXCEPT SELECT uuid, object_value_id FROM replay_expected) LIMIT 1"
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
        with self._lock:
            self._append_activity_unlocked(record)

    def _append_activity_unlocked(self, record: ActivityRecord) -> None:
        """Append an observation while the caller owns any required transaction."""
        try:
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
            raise ActivityAppendError(f"could not append the activity record: {error}") from error

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
        one_entry: bool = False,
    ) -> GraphDefinitionSet:
        self._current_definition_decodes += 1
        try:
            head = self._connection.execute(
                "SELECT active_definition_set_id FROM state_head WHERE id = 0"
            ).fetchone()
            if (
                head is not None
                and str(head[0]) == identity
                and not one_entry
                and (
                    type_keys is not None
                    or constrained_type_keys is not None
                    or relationship_keys is not None
                )
            ):
                definitions = GraphDefinitionSet()
                type_sources: dict[str, set[str]] = {}
                if type_keys is None:
                    type_rows = self._connection.execute(
                        "SELECT type_key, value_set_id FROM current_definition_type_source"
                    )
                else:
                    type_rows = (
                        row
                        for chunk in _sqlite_chunks(self._connection, type_keys)
                        for row in self._connection.execute(
                            "SELECT type_key, value_set_id"
                            " FROM current_definition_type_source WHERE type_key IN ("
                            + ", ".join("?" for _ in chunk)
                            + ")",
                            chunk,
                        )
                    )
                for key, source in type_rows:
                    type_sources.setdefault(str(source), set()).add(str(key))
                for source, keys in type_sources.items():
                    for chunk in _sqlite_chunks(self._connection, keys):
                        definitions = _merge_definition_sets(
                            definitions,
                            load_definition_set(
                                self._connection,
                                source,
                                type_keys=set(chunk),
                                relationship_keys=set(),
                            ),
                        )
                relationship_sources: dict[str, set[str]] = {}
                if relationship_keys is not None:
                    relationship_rows = (
                        row
                        for chunk in _sqlite_chunks(self._connection, relationship_keys)
                        for row in self._connection.execute(
                            "SELECT natural_key, value_set_id"
                            " FROM current_definition_relationship_source"
                            " WHERE natural_key IN (" + ", ".join("?" for _ in chunk) + ")",
                            chunk,
                        )
                    )
                elif constrained_type_keys is not None:
                    relationship_rows = (
                        row
                        for chunk in _sqlite_chunks(self._connection, constrained_type_keys)
                        for row in self._connection.execute(
                            "SELECT DISTINCT s.natural_key, s.value_set_id"
                            " FROM current_definition_relationship_source AS s"
                            " JOIN definition_multiplicity_rule AS r"
                            " ON r.definition_set_id = s.value_set_id"
                            " AND r.natural_key = s.natural_key"
                            " JOIN definition_multiplicity_participant AS p"
                            " ON p.definition_set_id = r.definition_set_id"
                            " AND p.rule_occurrence = r.occurrence"
                            " WHERE p.role = 'first' AND p.type_key IN ("
                            + ", ".join("?" for _ in chunk)
                            + ")",
                            chunk,
                        )
                    )
                else:
                    relationship_rows = self._connection.execute(
                        "SELECT natural_key, value_set_id"
                        " FROM current_definition_relationship_source"
                    )
                for key, source in relationship_rows:
                    relationship_sources.setdefault(str(source), set()).add(str(key))
                for source, keys in relationship_sources.items():
                    for chunk in _sqlite_chunks(self._connection, keys):
                        definitions = _merge_definition_sets(
                            definitions,
                            load_definition_set(
                                self._connection,
                                source,
                                type_keys=set(),
                                relationship_keys=set(chunk),
                            ),
                        )
                return definitions
            overlay = self._connection.execute(
                "SELECT base_definition_set_id FROM definition_set_overlay"
                " WHERE definition_set_id = ?",
                (identity,),
            ).fetchone()
            if overlay is None:
                return load_definition_set(
                    self._connection,
                    identity,
                    type_keys=type_keys,
                    constrained_type_keys=constrained_type_keys,
                    relationship_keys=relationship_keys,
                    one_entry=one_entry,
                )
            if one_entry:
                raise ValueError("an aggregate definition overlay is not one definition entry")
            base_identity = str(overlay[0])
            type_sql = (
                "SELECT type_key, operation, value_set_id"
                " FROM definition_set_type_override WHERE definition_set_id = ?"
            )
            if type_keys is None:
                type_rows = self._connection.execute(type_sql, (identity,))
            else:
                type_rows = (
                    row
                    for chunk in _sqlite_chunks(self._connection, type_keys, reserved=1)
                    for row in self._connection.execute(
                        type_sql + " AND type_key IN (" + ", ".join("?" for _ in chunk) + ")",
                        (identity, *chunk),
                    )
                )
            edited_types = {str(row[0]): row for row in type_rows}
            base = self._load_definition_set(
                base_identity,
                type_keys=type_keys,
                constrained_type_keys=constrained_type_keys,
                relationship_keys=relationship_keys,
            )
            anchors = [v for v in base.anchor_types if v.type_key not in edited_types]
            data = [v for v in base.associated_data_types if v.type_key not in edited_types]
            links = [v for v in base.link_types if v.type_key not in edited_types]
            for _, operation, value_set_id in edited_types.values():
                if operation == "delete":
                    continue
                value = load_definition_set(
                    self._connection, str(value_set_id), constrained_type_keys=set()
                )
                anchors.extend(value.anchor_types)
                data.extend(value.associated_data_types)
                links.extend(value.link_types)

            relationship_sql = (
                "SELECT natural_key, operation, value_set_id"
                " FROM definition_set_relationship_override WHERE definition_set_id = ?"
            )
            if relationship_keys is not None:
                relationship_rows = (
                    row
                    for chunk in _sqlite_chunks(self._connection, relationship_keys, reserved=1)
                    for row in self._connection.execute(
                        relationship_sql
                        + " AND natural_key IN ("
                        + ", ".join("?" for _ in chunk)
                        + ")",
                        (identity, *chunk),
                    )
                )
            elif constrained_type_keys is not None:
                if not constrained_type_keys:
                    relationship_rows = ()
                else:
                    relationship_rows = (
                        row
                        for chunk in _sqlite_chunks(
                            self._connection,
                            constrained_type_keys,
                            reserved=2,
                            repetitions=2,
                        )
                        for row in self._connection.execute(
                            relationship_sql + " AND ((operation = 'upsert' AND EXISTS (SELECT 1"
                            " FROM definition_multiplicity_rule AS r"
                            " JOIN definition_multiplicity_participant AS p"
                            " ON p.definition_set_id = r.definition_set_id"
                            " AND p.rule_occurrence = r.occurrence AND p.role = 'first'"
                            " WHERE r.definition_set_id = value_set_id AND p.type_key IN ("
                            + ", ".join("?" for _ in chunk)
                            + ")) OR (operation = 'delete' AND EXISTS (SELECT 1"
                            " FROM definition_multiplicity_rule AS r"
                            " JOIN definition_multiplicity_participant AS p"
                            " ON p.definition_set_id = r.definition_set_id"
                            " AND p.rule_occurrence = r.occurrence AND p.role = 'first'"
                            " WHERE r.definition_set_id = ? AND r.natural_key ="
                            " definition_set_relationship_override.natural_key"
                            " AND p.type_key IN (" + ", ".join("?" for _ in chunk) + ")))",
                            (identity, *chunk, base_identity, *chunk),
                        )
                    )
            else:
                relationship_rows = self._connection.execute(relationship_sql, (identity,))
            edited_relationships = {str(row[0]): row for row in relationship_rows}
            relationships = [
                v
                for v in base.relationship_constraints
                if semantic_identity(relationship_identity(v)) not in edited_relationships
            ]
            for _, operation, value_set_id in edited_relationships.values():
                if operation == "delete":
                    continue
                value = load_definition_set(
                    self._connection,
                    str(value_set_id),
                    type_keys=set(),
                    constrained_type_keys=None,
                )
                relationships.extend(value.relationship_constraints)
            return GraphDefinitionSet(
                tuple(anchors), tuple(data), tuple(links), tuple(relationships)
            )
        except (ValueError, ArithmeticError) as error:
            raise StoreError(f"stored definitions do not decode: {error}") from error
