"""Small connection-local activity append used by operation transactions."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from vellis.domain import TimestampValue, parse_timestamp


def append_activity(
    connection: sqlite3.Connection,
    *,
    capability: str,
    outcome: str,
    initiator: str,
    source: str | None,
    evaluated_revision: int | None,
    resulting_revision: int | None,
    summary: str,
    semantic_payload: object,
    verbose_payload: object | None = None,
) -> int:
    row = connection.execute(
        """SELECT last_activity_sequence, last_activity_time, activity_mode
           FROM metadata_setting WHERE singleton = 1"""
    ).fetchone()
    if row is None:
        raise ValueError("database metadata is absent")
    sequence = int(row["last_activity_sequence"]) + 1
    now = parse_timestamp(datetime.now(UTC).isoformat().replace("+00:00", "Z"))
    prior_text = row["last_activity_time"]
    timestamp = _nondecreasing(
        now, None if prior_text is None else parse_timestamp(str(prior_text))
    )
    semantic = json.dumps(
        semantic_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    connection.execute(
        """
        INSERT INTO activity_header(
            sequence, recorded_at, recorded_epoch_seconds, recorded_nanosecond,
            capability, outcome, initiator, source, evaluated_revision,
            resulting_revision, summary, semantic_payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sequence,
            timestamp.canonical,
            timestamp.epoch_seconds,
            timestamp.nanosecond,
            capability,
            outcome,
            initiator,
            source,
            evaluated_revision,
            resulting_revision,
            summary,
            semantic,
        ),
    )
    if str(row["activity_mode"]) == "verbose" and verbose_payload is not None:
        verbose = json.dumps(
            verbose_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        connection.execute(
            "INSERT INTO activity_payload(sequence, verbose_payload) VALUES (?, ?)",
            (sequence, verbose),
        )
    connection.execute(
        """UPDATE metadata_setting
           SET last_activity_sequence = ?, last_activity_time = ? WHERE singleton = 1""",
        (sequence, timestamp.canonical),
    )
    return sequence


def _nondecreasing(value: TimestampValue, prior: TimestampValue | None) -> TimestampValue:
    if prior is None or (value.epoch_seconds, value.nanosecond) >= (
        prior.epoch_seconds,
        prior.nanosecond,
    ):
        return value
    return prior
