"""Effective-change counts for the single normalized draft bucket."""

from dataclasses import replace

from vellis.change_domain import DraftCounts
from vellis.change_operations import _content
from vellis.definition_repository import load_definitions
from vellis.domain import CurrentState
from vellis.draft_repository import (
    draft_present,
    load_draft_definitions,
    load_draft_graph,
    raw_entry_count,
)
from vellis.graph_repository import load_graph_objects
from vellis.state_repository import resolve_state


def draft_counts(connection) -> DraftCounts:
    if not draft_present(connection):
        return DraftCounts(False, 0, 0)
    state = resolve_state(connection, CurrentState())
    definition_changes = sum(
        _definition_has_effect(connection, state, str(row[0]))
        for row in connection.execute(
            "SELECT type_key FROM draft_definition_entry ORDER BY type_key"
        )
    )
    graph_changes = sum(
        _object_has_effect(connection, state, str(row[0]))
        for row in connection.execute("SELECT uuid FROM draft_graph_object_patch ORDER BY uuid")
    )
    return DraftCounts(
        True,
        raw_entry_count(connection),
        definition_changes + graph_changes,
    )


def _definition_has_effect(connection, state, key):
    current = load_definitions(connection, state, (key,))
    proposed = load_draft_definitions(connection, current, (key,))
    before = None if not current else current[0]
    after = None if not proposed else proposed[0]
    return int(_definition_content(before) != _definition_content(after))


def _object_has_effect(connection, state, uuid):
    current = load_graph_objects(connection, state, (uuid,))
    proposed, _ = load_draft_graph(connection, current, (uuid,))
    before = None if not current else current[0]
    after = None if not proposed else proposed[0]
    if before is None and after is None:
        return 0
    return int(before is None or after is None or _content(before) != _content(after))


def _definition_content(value):
    return None if value is None else replace(value, system=None)
