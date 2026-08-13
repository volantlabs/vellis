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
)
from vellis.changes import GraphChange, apply_change, change_findings
from vellis.definitions import GraphDefinitionSet
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
    definition_identity,
    insert_definition_set,
    insert_object_value,
    json_storage_fields,
    json_storage_value,
    load_definition_set,
    load_object_value,
    object_identity,
    semantic_identity,
)
from vellis.outcomes import OperationStatus, ValidationFinding
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
    identity TEXT PRIMARY KEY
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
    proposed_definition_set_id TEXT REFERENCES definition_set(identity)
);
CREATE TABLE graph_presence_interval (
    uuid TEXT NOT NULL,
    object_value_id INTEGER NOT NULL REFERENCES object_value(id),
    valid_from_revision INTEGER NOT NULL,
    valid_to_revision INTEGER,
    PRIMARY KEY (uuid, valid_from_revision)
);
CREATE UNIQUE INDEX graph_presence_current_uuid
    ON graph_presence_interval(uuid) WHERE valid_to_revision IS NULL;
CREATE INDEX graph_presence_current_value
    ON graph_presence_interval(object_value_id, uuid) WHERE valid_to_revision IS NULL;
CREATE INDEX graph_presence_revision
    ON graph_presence_interval(valid_from_revision, valid_to_revision, uuid);
CREATE VIEW current_graph_object AS
SELECT p.uuid, v.object_kind, v.type_key, v.source_uuid, v.target_uuid, v.id AS object_value_id
FROM graph_presence_interval p JOIN object_value v ON v.id = p.object_value_id
WHERE p.valid_to_revision IS NULL;
CREATE VIEW current_data_anchor AS
SELECT v.uuid AS data_uuid, a.anchor_uuid
FROM current_graph_object c
JOIN object_value v ON v.id = c.object_value_id
JOIN object_anchor a ON a.object_value_id = v.id
WHERE v.object_kind = 'associatedData';
CREATE TABLE canonical_graph_event (
    established_revision INTEGER NOT NULL REFERENCES canonical_record(established_revision),
    occurrence INTEGER NOT NULL,
    operation TEXT NOT NULL,
    object_kind TEXT NOT NULL,
    uuid TEXT NOT NULL,
    object_value_id INTEGER REFERENCES object_value(id),
    PRIMARY KEY (established_revision, occurrence)
);
CREATE TABLE canonical_definition_event (
    established_revision INTEGER PRIMARY KEY REFERENCES canonical_record(established_revision),
    active_definition_set_id TEXT REFERENCES definition_set(identity),
    delta_disposition TEXT NOT NULL,
    proposed_definition_set_id TEXT REFERENCES definition_set(identity)
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
            else definition_identity(change.definition_delta.proposed_definitions),
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
                else DefinitionDelta(proposed_definitions=self._load_definition_set(str(row[3])))
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
                        str(row[2]), type_keys=_query_type_keys(query), constrained_type_keys=set()
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

    def _evaluate_sql_query_unlocked(
        self,
        query: GraphQuery,
        definitions: GraphDefinitionSet,
        revision: int,
        *,
        historical_revision: int | None = None,
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
                query, definitions, _SQLiteQueryIndex(self, historical_revision)
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
        row = self._fetchone(
            "SELECT revision, established_by, active_definition_set_id, proposed_definition_set_id"
            " FROM state_head WHERE id = 0"
        )
        if not isinstance(row, tuple):
            raise NotInitializedError("no canonical state is established")
        return (
            _projection_revision(row),
            self._load_definition_set(str(row[2])),
            None
            if row[3] is None
            else DefinitionDelta(proposed_definitions=self._load_definition_set(str(row[3]))),
        )

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
        self._connection.execute(
            "INSERT INTO graph_presence_interval"
            " (uuid, object_value_id, valid_from_revision, valid_to_revision)"
            " VALUES (?, ?, ?, NULL)",
            (graph_object.uuid, value_id, revision),
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
            else DefinitionDelta(proposed_definitions=self._load_definition_set(str(proposed_id)))
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
    ) -> GraphDefinitionSet:
        self._current_definition_decodes += 1
        try:
            return load_definition_set(
                self._connection,
                identity,
                type_keys=type_keys,
                constrained_type_keys=constrained_type_keys,
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

    def __init__(self, store: CanonicalStore, revision: int | None = None) -> None:
        self._store = store
        self._revision = revision
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
        return {
            str(row[0])
            for row in self._store._connection.execute(  # noqa: SLF001
                "SELECT uuid FROM current_graph_object"
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
