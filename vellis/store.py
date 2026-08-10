"""Durable local canonical storage.

The model requires canonical history to be complete, ordered, locally durable across
ordinary process restarts, and append-only, and requires current work to reach the
current canonical-state projection without traversing history. It deliberately leaves
storage open.

This realization selects one embedded SQL database file. That choice supplies the
recoverable atomicity ``VellisRequirements::atomicCanonicalRevision`` requires — the
appended canonical record and the updated current projection commit as one effect —
and gives later slices ordered, indexed selection without a linear ledger scan. The
materialized current projection is the realization the model names as permitted: it is
a projection of replay through the final canonical record, never parallel authority,
and one row so no tuple can mix values established by different records.

The projection and the record it derives from are written as one effect and each read
checks the revision it carries against the row it came from, so an interrupted or
partial write cannot present a mixed tuple. Content divergence introduced by editing the
database file directly is not detected: comparing decoded content on every current read
would traverse a canonical record, which is exactly the work
``VellisRequirements::historyIndependentCurrentWork`` forbids. Direct external mutation
of the store file is outside this project's trust boundary, as recorded in AGENTS.md.

Every canonical-record access is counted so conformance evidence for
``VellisRequirements::historyIndependentCurrentWork`` can observe them directly rather
than through wall-clock timing.
"""

from __future__ import annotations

import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from vellis.activity import ActivityRecord
from vellis.canonical import (
    CanonicalChange,
    CanonicalState,
    CanonicalTransitionRecord,
    InitialStateRecord,
    Provenance,
    TransitionKind,
)
from vellis.serialization import (
    DecodeError,
    decode_activity_record,
    decode_canonical_change,
    decode_canonical_state,
    decode_text,
    encode_activity_record,
    encode_canonical_change,
    encode_canonical_state,
    encode_text,
)

__all__ = [
    "AlreadyInitializedError",
    "CanonicalStore",
    "ConcurrentRevisionError",
    "NotInitializedError",
    "StoreError",
]

SCHEMA_VERSION = "2"

# The next ledger position. Counting rows would traverse the whole prefix on every
# commit, which is exactly the work history-independent current operations may not do;
# ordinal is UNIQUE, so taking its maximum is an index seek instead.
NEXT_ORDINAL_SQL = "SELECT ifnull(max(ordinal), -1) + 1 FROM canonical_record"

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
CREATE TABLE current_state (
    id             INTEGER PRIMARY KEY CHECK (id = 0),
    revision       INTEGER NOT NULL,
    established_by INTEGER NOT NULL REFERENCES canonical_record (established_revision),
    state          TEXT    NOT NULL
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


class StoreError(RuntimeError):
    """Raised when durable state cannot be read or written safely."""


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


class CanonicalStore:
    """One local canonical store: its ledger, its current projection, and their durability."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._record_reads = 0
        try:
            self._connection = sqlite3.connect(path, isolation_level=None)
        except sqlite3.Error as error:
            raise StoreError(f"could not open a canonical store at {path}: {error}") from error
        try:
            # Screening happens before the pragmas because setting the journal mode
            # rewrites the file header: refusing a database must leave it untouched.
            self._screen_database()
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

    def _screen_database(self) -> None:
        """Decide whether this file is ours, before anything about it is changed.

        A database can carry a table named ``schema_meta`` without being a Vellis store,
        so the marker check belongs here too rather than after the pragmas have already
        rewritten the header.
        """
        if self._schema_present():
            self._check_marker()
            return
        self._refuse_foreign_database()

    def _ensure_schema(self) -> None:
        if self._schema_present():
            return
        version_row = (
            f"INSERT INTO schema_meta (key, value) VALUES ('schema_version', '{SCHEMA_VERSION}');"
        )
        try:
            self._connection.executescript(
                f"BEGIN IMMEDIATE;PRAGMA application_id = {APPLICATION_ID};"
                f"{_SCHEMA}{version_row}COMMIT;"
            )
        except sqlite3.OperationalError:
            # Another process created the schema between the check and this statement.
            self._rollback_quietly()
            if not self._schema_present():
                raise
        self._check_marker()

    def _refuse_foreign_database(self) -> None:
        """Refuse a database that already holds something other than a Vellis store.

        Without this the schema would be created inside an unrelated database and its
        own application marker overwritten.
        """
        marker = self._connection.execute("PRAGMA application_id").fetchone()
        if marker is not None and int(marker[0]) not in {0, APPLICATION_ID}:
            raise StoreError(f"the database at {self._path} belongs to another application")
        existing = self._connection.execute(
            "SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        ).fetchall()
        if existing:
            names = ", ".join(sorted(str(row[0]) for row in existing))
            raise StoreError(
                f"the database at {self._path} already holds other objects ({names}); "
                "choose a different destination"
            )

    def _schema_present(self) -> bool:
        row = self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_meta'"
        ).fetchone()
        return row is not None

    def _check_marker(self) -> None:
        # Whose database this is comes first. A version mismatch is a statement about a
        # Vellis store, and reporting one about a file that is not ours would send the
        # owner looking for a migration that does not apply.
        marker = self._connection.execute("PRAGMA application_id").fetchone()
        if marker is None or int(marker[0]) != APPLICATION_ID:
            raise StoreError(f"the database at {self._path} is not a Vellis canonical store")
        row = self._connection.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None or row[0] != SCHEMA_VERSION:
            found = "none" if row is None else str(row[0])
            raise StoreError(
                f"canonical store at {self._path} has schema version {found}, "
                f"but this build reads version {SCHEMA_VERSION}"
            )
        for table in ("canonical_record", "activity_record", "current_state", "ledger"):
            present = self._connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
            ).fetchone()
            if present is None:
                raise StoreError(f"canonical store at {self._path} is missing its {table} table")

    # --- Instrumentation ------------------------------------------------------------

    @property
    def record_reads(self) -> int:
        """Semantic canonical-record accesses since the last reset."""
        return self._record_reads

    def reset_instrumentation(self) -> None:
        self._record_reads = 0

    # --- Current projection ---------------------------------------------------------

    def is_initialized(self) -> bool:
        """Return whether canonical state exists, without reading any canonical record."""
        return self._fetchone("SELECT 1 FROM current_state WHERE id = 0") is not None

    def _fetchone(self, sql: str, parameters: tuple[object, ...] = ()) -> object:
        """Run one read, reporting a database failure as a store error.

        Callers of this store handle :class:`StoreError`; letting a driver exception out
        would turn an operation that should report a failure into a traceback.
        """
        try:
            return self._connection.execute(sql, parameters).fetchone()
        except sqlite3.Error as error:
            raise StoreError(f"could not read from the store at {self._path}: {error}") from error

    def _fetchall(self, sql: str, parameters: tuple[object, ...] = ()) -> list[object]:
        try:
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

        This reads the one projection row and no canonical record, so its work does not
        grow with history length.
        """
        row = self._fetchone(
            "SELECT revision, established_by, state FROM current_state WHERE id = 0"
        )
        if not isinstance(row, tuple):
            raise NotInitializedError("no canonical state is established")
        state = self._decode_state(row[2], "current state")
        if state.revision != row[0] or state.revision != row[1]:
            raise StoreError(
                f"the current projection at {self._path} claims revision {row[0]} established by "
                f"record {row[1]}, but carries revision {state.revision}"
            )
        return state

    # --- Owned history base ---------------------------------------------------------

    def initialize(self, record: InitialStateRecord) -> None:
        """Establish the owned history base and its projection as one atomic effect.

        Nothing is established when the store already holds canonical state, and a
        failure part-way through leaves no partial canonical or activity state.
        """
        state = record.canonical_state
        payload = encode_text(encode_canonical_state(state))
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            if self._connection.execute("SELECT 1 FROM current_state WHERE id = 0").fetchone():
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
                "INSERT INTO current_state (id, revision, established_by, state)"
                " VALUES (0, ?, ?, ?)",
                (state.revision, record.established_revision, payload),
            )
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

    def append_transition(
        self, record: CanonicalTransitionRecord, resulting_state: CanonicalState
    ) -> None:
        """Append one transition and update the projection as one recoverable effect.

        The appended record and the updated projection commit together, so no reader can
        observe a revision established by one without the state established by the other.
        The prior revision is re-checked inside the transaction, so two writers cannot
        both believe they are advancing from it.
        """
        payload = encode_text(encode_canonical_state(resulting_state))
        change = encode_text(encode_canonical_change(record.change))
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
                "UPDATE current_state SET revision = ?, established_by = ?, state = ? WHERE id = 0",
                (resulting_state.revision, record.resulting_revision, payload),
            )
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

    def canonical_summaries(
        self, *, start: datetime | None = None, end: datetime | None = None
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
        rows = self._fetchall(
            "SELECT established_revision, ordinal, record_kind, summary, initiator, source,"
            f" recorded_at FROM canonical_record{where} ORDER BY ordinal",
            tuple(parameters),
        )
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
            self._connection.execute(
                "INSERT INTO activity_record (recorded_at, payload) VALUES (?, ?)",
                (_stored_time(record.recorded_at), payload),
            )
        except sqlite3.Error as error:
            raise StoreError(f"could not append the activity record: {error}") from error

    def activity_records(
        self, *, start: datetime | None = None, end: datetime | None = None
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
        rows = self._fetchall(
            f"SELECT payload FROM activity_record{where} ORDER BY ordinal", tuple(parameters)
        )
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
