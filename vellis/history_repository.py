"""Connection-local indexed canonical and activity history selection."""

from __future__ import annotations

import json
import sqlite3

from vellis.domain import TransitionKind, parse_timestamp
from vellis.history_domain import (
    ActivityHistoryEntry,
    ActivityOutcome,
    CanonicalHistoryEntry,
    HistoryKind,
    HistoryRequest,
    SequenceHistoryRange,
    TimeHistoryRange,
)


def history_head(connection: sqlite3.Connection, kind: HistoryKind) -> int:
    if kind is HistoryKind.CANONICAL:
        row = connection.execute(
            "SELECT head_revision FROM metadata_setting WHERE singleton = 1"
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT last_activity_sequence FROM metadata_setting WHERE singleton = 1"
        ).fetchone()
    if row is None:
        raise ValueError("database metadata is absent")
    return int(row[0])


def select_history(connection: sqlite3.Connection, request: HistoryRequest, head: int):
    if request.kind is HistoryKind.CANONICAL:
        return _canonical_entries(connection, request, head)
    return _activity_entries(connection, request, head)


def _canonical_entries(connection, request, head):
    statement, parameters = _canonical_statement(request, head)
    rows = connection.execute(
        statement,
        (*parameters, request.maximum_records + 1),
    ).fetchall()
    return tuple(
        CanonicalHistoryEntry(
            int(row["revision"]),
            parse_timestamp(str(row["recorded_at"])),
            str(row["initiator"]),
            None if row["source"] is None else str(row["source"]),
            TransitionKind(str(row["transition_kind"])),
            str(row["summary"]),
            _stored_array(row["affected_type_keys"], "affected type keys"),
            _stored_array(row["affected_uuids"], "affected UUIDs"),
        )
        for row in rows
    )


def _activity_entries(connection, request, head):
    statement, parameters = _activity_statement(request, head)
    rows = connection.execute(
        statement,
        (*parameters, request.maximum_records + 1),
    ).fetchall()
    return tuple(
        ActivityHistoryEntry(
            int(row["sequence"]),
            parse_timestamp(str(row["recorded_at"])),
            str(row["capability"]),
            ActivityOutcome(str(row["outcome"])),
            str(row["initiator"]),
            None if row["source"] is None else str(row["source"]),
            None if row["evaluated_revision"] is None else int(row["evaluated_revision"]),
            None if row["resulting_revision"] is None else int(row["resulting_revision"]),
            str(row["summary"]),
            json.loads(str(row["semantic_payload"])),
            (
                json.loads(str(row["verbose_payload"]))
                if request.include_verbose and row["verbose_payload"] is not None
                else None
            ),
        )
        for row in rows
    )


def _stored_array(encoded, label):
    if not isinstance(encoded, str):
        raise ValueError(f"stored {label} must be JSON text")
    try:
        decoded = json.loads(encoded)
    except json.JSONDecodeError as error:
        raise ValueError(f"stored {label} is malformed JSON") from error
    if not isinstance(decoded, list):
        raise ValueError(f"stored {label} must be a JSON array")
    return tuple(decoded)


def _canonical_statement(request, head):
    where, parameters = _range_sql(request, "revision", head)
    indexed = (
        " INDEXED BY canonical_record_time_idx"
        if isinstance(request.range, TimeHistoryRange)
        else ""
    )
    return (
        f"""SELECT revision, recorded_at, initiator, source, transition_kind, summary,
                   affected_type_keys, affected_uuids
            FROM canonical_record{indexed} WHERE {where}
            ORDER BY revision LIMIT ?""",
        parameters,
    )


def _activity_statement(request, head):
    where, parameters = _range_sql(request, "h.sequence", head)
    indexed = " INDEXED BY activity_time_idx" if isinstance(request.range, TimeHistoryRange) else ""
    return (
        f"""SELECT h.*, p.semantic_payload, p.verbose_payload
            FROM activity_header AS h{indexed}
            JOIN activity_payload AS p ON p.sequence = h.sequence
            WHERE {where} ORDER BY h.sequence LIMIT ?""",
        parameters,
    )


def _range_sql(request, sequence_column, head):
    value = request.range
    if value is None:
        return f"{sequence_column} <= ?", (head,)
    if isinstance(value, SequenceHistoryRange):
        if value.after is not None and value.after >= head:
            return "0", ()
        if value.after is not None and value.through is not None and value.after >= value.through:
            return "0", ()
        clauses = [f"{sequence_column} <= ?"]
        parameters: list[object] = [head]
        if value.after is not None:
            clauses.append(f"{sequence_column} > ?")
            parameters.append(value.after)
        if value.through is not None and value.through < head:
            clauses.append(f"{sequence_column} <= ?")
            parameters.append(value.through)
        return " AND ".join(clauses), tuple(parameters)
    assert isinstance(value, TimeHistoryRange)
    seconds = (
        "recorded_epoch_seconds"
        if request.kind is HistoryKind.CANONICAL
        else "h.recorded_epoch_seconds"
    )
    nanos = (
        "recorded_nanosecond" if request.kind is HistoryKind.CANONICAL else "h.recorded_nanosecond"
    )
    clauses = [f"{sequence_column} <= ?"]
    parameters = [head]
    if value.start is not None:
        clauses.append(f"({seconds}, {nanos}) >= (?, ?)")
        parameters.extend((value.start.epoch_seconds, value.start.nanosecond))
    if value.end is not None:
        clauses.append(f"({seconds}, {nanos}) <= (?, ?)")
        parameters.extend((value.end.epoch_seconds, value.end.nanosecond))
    return " AND ".join(clauses), tuple(parameters)
