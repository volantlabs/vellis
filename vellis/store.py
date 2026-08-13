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
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
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
    InitialStateRecord,
    Provenance,
    TransitionKind,
)
from vellis.changes import GraphChange
from vellis.definitions import GraphDefinitionSet
from vellis.graph import Anchor, AssociatedDataObject, Graph, GraphObject, Link, ObjectKind
from vellis.serialization import (
    DecodeError,
    decode_activity_record,
    decode_canonical_change,
    decode_canonical_state,
    decode_definition_delta,
    decode_definition_set,
    decode_graph,
    decode_text,
    encode_activity_record,
    encode_canonical_change,
    encode_canonical_state,
    encode_definition_delta,
    encode_definition_set,
    encode_graph,
    encode_text,
)

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

SCHEMA_VERSION = "3"

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
    " payload FROM canonical_record WHERE ordinal > 0 AND established_revision <= ?"
    " AND record_kind != 'graphMutation' ORDER BY established_revision"
)

# Whether canonical state exists. One statement, so a caller asking before it may create
# anything and the store asking during a commit are asking exactly the same question.
INITIALIZED_SQL = "SELECT 1 FROM current_state WHERE id = 0"

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
    payload              TEXT    NOT NULL
);
CREATE TABLE activity_record (
    ordinal     INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    payload     TEXT NOT NULL
);
CREATE TABLE ledger (
    id       INTEGER PRIMARY KEY CHECK (id = 0),
    identity TEXT    NOT NULL
);
CREATE INDEX activity_record_time ON activity_record (recorded_at);
CREATE INDEX canonical_record_time ON canonical_record (recorded_at);
CREATE INDEX canonical_record_kind ON canonical_record (record_kind, established_revision);
CREATE TABLE current_state (
    id             INTEGER PRIMARY KEY CHECK (id = 0),
    revision       INTEGER NOT NULL,
    established_by INTEGER NOT NULL REFERENCES canonical_record (established_revision),
    active_definitions TEXT NOT NULL,
    definition_delta TEXT
);
CREATE TABLE current_graph_object (
    uuid        TEXT PRIMARY KEY,
    object_kind TEXT NOT NULL,
    type_key    TEXT NOT NULL,
    source_uuid TEXT,
    target_uuid TEXT,
    payload     TEXT NOT NULL
);
CREATE TABLE current_data_anchor (
    data_uuid   TEXT NOT NULL REFERENCES current_graph_object (uuid),
    anchor_uuid TEXT NOT NULL REFERENCES current_graph_object (uuid),
    PRIMARY KEY (data_uuid, anchor_uuid)
);
CREATE INDEX current_graph_object_kind_type
    ON current_graph_object (object_kind, type_key);
CREATE INDEX current_graph_link_endpoints
    ON current_graph_object (object_kind, type_key, source_uuid, target_uuid);
CREATE INDEX current_data_anchor_anchor
    ON current_data_anchor (anchor_uuid, data_uuid);
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


def _encode_current_facets(state: CanonicalState) -> tuple[str, str | None]:
    return (
        encode_text(encode_definition_set(state.active_definitions)),
        (
            None
            if state.definition_delta is None
            else encode_text(encode_definition_delta(state.definition_delta))
        ),
    )


def _encoded_graph_object(
    graph_object: GraphObject,
) -> tuple[str, str, str, str | None, str | None, str]:
    """Encode one addressable projection row without inventing another wire format."""
    if isinstance(graph_object, Anchor):
        graph = Graph(anchors=(graph_object,))
        kind = ObjectKind.ANCHOR.value
        source = target = None
    elif isinstance(graph_object, AssociatedDataObject):
        graph = Graph(associated_data=(graph_object,))
        kind = ObjectKind.ASSOCIATED_DATA.value
        source = target = None
    else:
        graph = Graph(links=(graph_object,))
        kind = ObjectKind.LINK.value
        source, target = graph_object.source_uuid, graph_object.target_uuid
    return (
        graph_object.uuid,
        kind,
        graph_object.type_key,
        source,
        target,
        encode_text(encode_graph(graph)),
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
    payload: str


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
        "current_state",
        "current_graph_object",
        "current_data_anchor",
        "ledger",
    ):
        present = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        if present is None:
            raise UnreadableStoreError(f"canonical store at {path} is missing its {table} table")
    columns = {
        str(info[1]) for info in connection.execute("PRAGMA table_info(current_state)").fetchall()
    }
    required = {
        "id",
        "revision",
        "established_by",
        "active_definitions",
        "definition_delta",
    }
    if not required.issubset(columns):
        missing = ", ".join(sorted(required - columns))
        raise UnreadableStoreError(
            f"canonical store at {path} schema version {SCHEMA_VERSION} is missing current-state "
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

    def current_state(self) -> CanonicalState:
        """Return the current canonical-state projection.

        SQLite owns the live projection. Every call materializes a new domain value, so
        mutable nested JSON handed to a library caller has no shared resident object to
        corrupt and needs no defensive whole-state copy. This explicit complete-state
        operation is one of the few paths that assembles every graph row.
        """
        try:
            with self._lock:
                row = self._connection.execute(
                    "SELECT revision, established_by, active_definitions, definition_delta"
                    " FROM current_state WHERE id = 0"
                ).fetchone()
                if not isinstance(row, tuple):
                    raise NotInitializedError("no canonical state is established")
                revision = _projection_revision(row)
                state = CanonicalState(
                    graph=self._current_graph_unlocked(),
                    active_definitions=self._decode_current_definitions(row[2]),
                    definition_delta=self._decode_current_delta(row[3]),
                    revision=revision,
                )
                self._current_projection_decodes += 1
                return state
        except sqlite3.Error as error:
            raise StoreError(f"could not read from the store at {self._path}: {error}") from error

    def current_graph(self) -> Graph:
        """Assemble the complete current graph without reading canonical history."""
        try:
            with self._lock:
                if self._connection.execute(INITIALIZED_SQL).fetchone() is None:
                    raise NotInitializedError("no canonical state is established")
                return self._current_graph_unlocked()
        except sqlite3.Error as error:
            raise StoreError(f"could not read from the store at {self._path}: {error}") from error

    def evaluate_current_query(self, query: GraphQuery) -> GraphQueryResult:
        """Evaluate against indexed SQLite candidates in one revision snapshot."""
        from vellis.query import evaluate_indexed_query

        try:
            with self._lock:
                self._connection.execute("BEGIN")
                try:
                    row = self._connection.execute(
                        "SELECT revision, established_by, active_definitions"
                        " FROM current_state WHERE id = 0"
                    ).fetchone()
                    if not isinstance(row, tuple):
                        raise NotInitializedError("no canonical state is established")
                    revision = _projection_revision(row)
                    definitions = self._decode_current_definitions(row[2])
                    result = evaluate_indexed_query(
                        query, definitions, _SQLiteQueryIndex(self), revision
                    )
                    self._connection.execute("COMMIT")
                    return result
                except BaseException:
                    self._rollback_quietly()
                    raise
        except sqlite3.Error as error:
            raise StoreError(f"could not read from the store at {self._path}: {error}") from error

    def current_definitions(self) -> tuple[int, GraphDefinitionSet, DefinitionDelta | None]:
        """Read current definition facets without materializing the graph facet."""
        row = self._fetchone(
            "SELECT revision, established_by, active_definitions, definition_delta"
            " FROM current_state WHERE id = 0"
        )
        if not isinstance(row, tuple):
            raise NotInitializedError("no canonical state is established")
        return (
            _projection_revision(row),
            self._decode_current_definitions(row[2]),
            self._decode_current_delta(row[3]),
        )

    def current_revision(self) -> int:
        """Read the established current revision without materializing any state facet."""
        row = self._fetchone("SELECT revision, established_by FROM current_state WHERE id = 0")
        if not isinstance(row, tuple):
            raise NotInitializedError("no canonical state is established")
        return _projection_revision(row)

    # --- Owned history base ---------------------------------------------------------

    def initialize(self, record: InitialStateRecord) -> None:
        """Establish the owned history base and its projection as one atomic effect.

        Nothing is established when the store already holds canonical state, and a
        failure part-way through leaves no partial canonical or activity state.
        """
        state = record.canonical_state
        payload = encode_text(encode_canonical_state(state))
        definitions, delta = _encode_current_facets(state)
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                if self._connection.execute(INITIALIZED_SQL).fetchone():
                    self._connection.execute("ROLLBACK")
                    raise AlreadyInitializedError(
                        f"canonical state is already established at {self._path}"
                    )
                self._connection.execute(
                    "INSERT INTO canonical_record (established_revision, ordinal, record_kind,"
                    " recorded_at, initiator, source, summary, payload)"
                    " VALUES (?, 0, 'initial', ?, ?, ?, ?, ?)",
                    (
                        record.established_revision,
                        _stored_time(record.recorded_at),
                        record.provenance.initiator,
                        record.provenance.source,
                        record.initialization_summary,
                        payload,
                    ),
                )
                self._connection.execute(
                    "INSERT INTO current_state"
                    " (id, revision, established_by, active_definitions, definition_delta)"
                    " VALUES (0, ?, ?, ?, ?)",
                    (
                        state.revision,
                        record.established_revision,
                        definitions,
                        delta,
                    ),
                )
                self._replace_current_graph_unlocked(state.graph)
                # A read attempted before the system existed may already have observed itself
                # here, and success promises an empty ledger.
                self._connection.execute("DELETE FROM activity_record")
                # One value that no other ledger can hold, so a record's identity says which
                # history it belongs to and not merely what it contains. Two systems seeded
                # from the same snapshot are otherwise indistinguishable by content alone.
                self._connection.execute(
                    "INSERT INTO ledger (id, identity) VALUES (0, ?)", (secrets.token_hex(16),)
                )
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

    def _replace_current_graph_unlocked(self, graph: Graph) -> None:
        self._connection.execute("DELETE FROM current_data_anchor")
        self._connection.execute("DELETE FROM current_graph_object")
        for graph_object in graph.objects():
            self._upsert_current_graph_object_unlocked(graph_object)

    def _apply_current_graph_change_unlocked(self, change: GraphChange) -> None:
        data_to_replace = {
            *(data.uuid for data in change.associated_data_upserts),
            *change.associated_data_removals,
        }
        if data_to_replace:
            placeholders = ", ".join("?" for _ in data_to_replace)
            self._connection.execute(
                f"DELETE FROM current_data_anchor WHERE data_uuid IN ({placeholders})",
                tuple(data_to_replace),
            )
        removals = tuple(uuid for _, uuid in change.removals())
        if removals:
            placeholders = ", ".join("?" for _ in removals)
            self._connection.execute(
                f"DELETE FROM current_graph_object WHERE uuid IN ({placeholders})", removals
            )
        for _, graph_object in change.upserts():
            self._upsert_current_graph_object_unlocked(graph_object)

    def _upsert_current_graph_object_unlocked(self, graph_object: GraphObject) -> None:
        self._connection.execute(
            "INSERT INTO current_graph_object"
            " (uuid, object_kind, type_key, source_uuid, target_uuid, payload)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(uuid) DO UPDATE SET"
            " object_kind=excluded.object_kind, type_key=excluded.type_key,"
            " source_uuid=excluded.source_uuid, target_uuid=excluded.target_uuid,"
            " payload=excluded.payload",
            _encoded_graph_object(graph_object),
        )
        if isinstance(graph_object, AssociatedDataObject):
            self._connection.executemany(
                "INSERT INTO current_data_anchor (data_uuid, anchor_uuid) VALUES (?, ?)",
                ((graph_object.uuid, uuid) for uuid in graph_object.anchor_uuids),
            )

    def append_transition(
        self, record: CanonicalTransitionRecord, resulting_state: CanonicalState
    ) -> None:
        """Append one transition and update the projection as one recoverable effect.

        The appended record and the updated projection commit together, so no reader can
        observe a revision established by one without the state established by the other.
        The prior revision is re-checked inside the transaction, so two writers cannot
        both believe they are advancing from it.
        """
        definitions, delta = _encode_current_facets(resulting_state)
        change = encode_text(encode_canonical_change(record.change))
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                row = self._connection.execute(
                    "SELECT revision FROM current_state WHERE id = 0"
                ).fetchone()
                if row is None:
                    self._connection.execute("ROLLBACK")
                    raise NotInitializedError("no canonical state is established")
                if row[0] != record.prior_revision:
                    self._connection.execute("ROLLBACK")
                    raise ConcurrentRevisionError(
                        f"the current revision is {row[0]}, not {record.prior_revision}"
                    )
                self._connection.execute(
                    "INSERT INTO canonical_record (established_revision, ordinal, record_kind,"
                    " recorded_at, initiator, source, summary, payload)"
                    f" VALUES (?, ({NEXT_ORDINAL_SQL}), ?, ?, ?, ?, ?, ?)",
                    (
                        record.resulting_revision,
                        record.kind.value,
                        _stored_time(record.recorded_at),
                        record.provenance.initiator,
                        record.provenance.source,
                        str(record.prior_revision),
                        change,
                    ),
                )
                self._connection.execute(
                    "UPDATE current_state SET revision = ?, established_by = ?,"
                    " active_definitions = ?, definition_delta = ? WHERE id = 0",
                    (
                        resulting_state.revision,
                        record.resulting_revision,
                        definitions,
                        delta,
                    ),
                )
                if record.change.graph_change is not None:
                    self._apply_current_graph_change_unlocked(record.change.graph_change)
                elif record.change.replacement_graph is not None:
                    self._replace_current_graph_unlocked(record.change.replacement_graph)
                self._connection.execute("COMMIT")
            except StoreError:
                self._rollback_quietly()
                raise
            except Exception as error:
                self._rollback_quietly()
                raise StoreError(f"could not append the transition: {error}") from error

    def transitions(self) -> tuple[CanonicalTransitionRecord, ...]:
        """Read every transition in ledger order. Each is a semantic record access."""
        rows = self._fetchall(
            "SELECT established_revision, record_kind, recorded_at, initiator, source, summary,"
            " payload FROM canonical_record WHERE ordinal > 0 ORDER BY ordinal"
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
            prior = int(record.summary)
        except ValueError as error:
            raise StoreError(
                f"a canonical record at {self._path} is not a readable transition: {error}"
            ) from error
        return CanonicalTransitionRecord(
            prior_revision=prior,
            resulting_revision=record.established_revision,
            kind=kind,
            change=self._decode_change(record.payload),
            provenance=Provenance(initiator=record.initiator, source=record.source),
            recorded_at=self._recorded_at(record.recorded_at),
        )

    def _decode_change(self, payload: object) -> CanonicalChange:
        if not isinstance(payload, str):
            raise StoreError("a stored canonical change is not text")
        try:
            return decode_canonical_change(decode_text(payload))
        except (DecodeError, ValueError, ArithmeticError, RecursionError) as error:
            raise StoreError(
                f"a stored canonical change does not decode to canonical meaning: {error}"
            ) from error

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
            " r.initiator, r.source, r.summary, r.payload"
            " FROM current_state s JOIN canonical_record r"
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
            " payload FROM canonical_record WHERE ordinal > 0 AND established_revision <= ?"
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
            " payload FROM canonical_record WHERE ordinal = 0"
        )
        if row is None:
            raise StoreError("no initial canonical record is established")
        assert isinstance(row, tuple)
        record = _RecordRow(*row)
        if record.record_kind != "initial":
            raise StoreError(f"ledger base is a {record.record_kind} record, not an initial record")
        state = self._decode_state(record.payload, "initial record")
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
        payload = encode_text(encode_activity_record(record))
        try:
            with self._lock:
                self._connection.execute(
                    "INSERT INTO activity_record (recorded_at, payload) VALUES (?, ?)",
                    (_stored_time(record.recorded_at), payload),
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
            sql = f"SELECT payload FROM activity_record{where} ORDER BY ordinal"
        else:
            parameters.append(limit)
            sql = (
                "WITH bounded AS MATERIALIZED (SELECT ordinal, payload FROM activity_record"
                f"{where} LIMIT ?) SELECT payload FROM bounded ORDER BY ordinal"
            )
        rows = self._fetchall(sql, tuple(parameters))
        self._activity_reads += len(rows)
        records: list[ActivityRecord] = []
        for row in rows:
            assert isinstance(row, tuple)
            payload = row[0]
            if not isinstance(payload, str):
                raise StoreError("a stored activity record is not text")
            try:
                records.append(decode_activity_record(decode_text(payload)))
            except (DecodeError, ValueError, ArithmeticError, RecursionError) as error:
                raise StoreError(
                    f"a stored activity record does not decode to an observation: {error}"
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

    def _decode_state(self, payload: object, where: str) -> CanonicalState:
        if not isinstance(payload, str):
            raise StoreError(f"stored {where} is not text")
        try:
            return decode_canonical_state(decode_text(payload))
        except (DecodeError, ValueError, ArithmeticError, RecursionError) as error:
            raise StoreError(f"stored {where} does not decode to canonical meaning: {error}") from (
                error
            )

    def _current_graph_unlocked(self) -> Graph:
        rows = self._connection.execute(
            "SELECT uuid, object_kind, type_key, source_uuid, target_uuid, payload"
            " FROM current_graph_object ORDER BY rowid"
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
        payload: object,
    ) -> GraphObject:
        if (
            not isinstance(uuid, str)
            or not isinstance(kind, str)
            or not isinstance(type_key, str)
            or not isinstance(payload, str)
        ):
            raise StoreError("a stored current graph-object row has non-text identity or content")
        try:
            graph = decode_graph(decode_text(payload))
        except (DecodeError, ValueError, ArithmeticError, RecursionError) as error:
            raise StoreError(
                f"stored current graph object {uuid!r} does not decode: {error}"
            ) from error
        objects = graph.objects()
        if len(objects) != 1 or objects[0].uuid != uuid:
            raise StoreError(f"stored current graph-object row {uuid!r} carries different content")
        graph_object = objects[0]
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
                " its payload"
            )
        self._current_graph_object_decodes += 1
        return graph_object

    def _decode_current_definitions(self, payload: object) -> GraphDefinitionSet:
        if not isinstance(payload, str):
            raise StoreError("stored current definitions are not text")
        try:
            definitions = decode_definition_set(decode_text(payload))
        except (DecodeError, ValueError, ArithmeticError, RecursionError) as error:
            raise StoreError(
                f"stored current definitions do not decode to definition meaning: {error}"
            ) from error
        self._current_definition_decodes += 1
        return definitions

    def _decode_current_delta(self, payload: object) -> DefinitionDelta | None:
        if payload is None:
            return None
        if not isinstance(payload, str):
            raise StoreError("stored current definition delta is not text")
        try:
            return decode_definition_delta(decode_text(payload))
        except (DecodeError, ValueError, ArithmeticError, RecursionError) as error:
            raise StoreError(
                f"stored current definition delta does not decode to proposal meaning: {error}"
            ) from error


class _SQLiteQueryIndex:
    """Query-local access through the durable projection's identity indexes."""

    def __init__(self, store: CanonicalStore) -> None:
        self._store = store
        self._anchors: dict[object, tuple[Anchor, ...]] = {}
        self._data: dict[tuple[str, str], tuple[AssociatedDataObject, ...]] = {}
        self._links: dict[tuple[object, str, str], tuple[Link, ...]] = {}
        self._link_pairs: dict[object, frozenset[tuple[str, str]]] = {}

    def known_anchor_uuids(self, uuids: tuple[str, ...]) -> set[str]:
        return self._known_uuids(ObjectKind.ANCHOR, uuids)

    def known_link_uuids(self, uuids: tuple[str, ...]) -> set[str]:
        return self._known_uuids(ObjectKind.LINK, uuids)

    def _known_uuids(self, kind: ObjectKind, uuids: tuple[str, ...]) -> set[str]:
        if not uuids:
            return set()
        placeholders = ", ".join("?" for _ in uuids)
        return {
            str(row[0])
            for row in self._store._connection.execute(  # noqa: SLF001
                "SELECT uuid FROM current_graph_object"
                f" WHERE object_kind = ? AND uuid IN ({placeholders})",
                (kind.value, *uuids),
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
            "SELECT uuid, object_kind, type_key, source_uuid, target_uuid, payload"
            " FROM current_graph_object WHERE " + " AND ".join(clauses),
            tuple(parameters),
        ).fetchall()
        result = tuple(self._anchors_from(rows))
        self._anchors[key] = result
        return result

    def associated_data_candidates(
        self, associated_data_type: str, anchor_uuid: str
    ) -> tuple[AssociatedDataObject, ...]:
        key = (associated_data_type, anchor_uuid)
        cached = self._data.get(key)
        if cached is not None:
            return cached
        rows = self._store._connection.execute(  # noqa: SLF001
            "SELECT o.uuid, o.object_kind, o.type_key, o.source_uuid, o.target_uuid, o.payload"
            " FROM current_data_anchor AS da"
            " JOIN current_graph_object AS o ON o.uuid = da.data_uuid"
            " WHERE da.anchor_uuid = ? AND o.object_kind = ? AND o.type_key = ?",
            (anchor_uuid, ObjectKind.ASSOCIATED_DATA.value, associated_data_type),
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
            "SELECT uuid, object_kind, type_key, source_uuid, target_uuid, payload"
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
