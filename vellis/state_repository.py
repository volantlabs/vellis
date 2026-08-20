"""Single selected-state resolution path for all VEL2 repositories."""

from __future__ import annotations

import sqlite3

from vellis.domain import (
    CurrentState,
    DraftState,
    ResolvedState,
    RevisionState,
    StateSelection,
    TimeState,
)


class StateNotFoundError(ValueError):
    pass


def resolve_state(
    connection: sqlite3.Connection, selection: StateSelection | None = None
) -> ResolvedState:
    selected = CurrentState() if selection is None else selection
    if isinstance(selected, DraftState):
        present = connection.execute("SELECT 1 FROM draft_metadata WHERE singleton = 1").fetchone()
        if present is None:
            raise StateNotFoundError("draft state does not exist")
        return ResolvedState(_head_revision(connection), includes_draft=True)
    if isinstance(selected, CurrentState):
        return ResolvedState(_head_revision(connection))
    if isinstance(selected, RevisionState):
        head = _head_revision(connection)
        if selected.revision > head or not _revision_exists(connection, selected.revision):
            raise StateNotFoundError(f"canonical revision {selected.revision} does not exist")
        return ResolvedState(selected.revision)
    assert isinstance(selected, TimeState)
    row = connection.execute(
        """
        SELECT revision
        FROM canonical_record
        WHERE (recorded_epoch_seconds < ?)
           OR (recorded_epoch_seconds = ? AND recorded_nanosecond <= ?)
        ORDER BY recorded_epoch_seconds DESC, recorded_nanosecond DESC, revision DESC
        LIMIT 1
        """,
        (
            selected.timestamp.epoch_seconds,
            selected.timestamp.epoch_seconds,
            selected.timestamp.nanosecond,
        ),
    ).fetchone()
    if row is None:
        raise StateNotFoundError("no canonical revision exists at or before the selected time")
    return ResolvedState(int(row["revision"]))


def interval_sql(alias: str) -> str:
    return (
        f"{alias}.valid_from_revision <= ? AND "
        f"({alias}.valid_to_revision IS NULL OR {alias}.valid_to_revision > ?)"
    )


def interval_parameters(state: ResolvedState) -> tuple[int, int]:
    return state.evaluated_revision, state.evaluated_revision


def _head_revision(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT head_revision FROM metadata_setting WHERE singleton = 1"
    ).fetchone()
    if row is None:
        raise StateNotFoundError("database head is absent")
    return int(row["head_revision"])


def _revision_exists(connection: sqlite3.Connection, revision: int) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM canonical_record WHERE revision = ?", (revision,)
        ).fetchone()
        is not None
    )
