"""Bounded streaming evaluation of connected pattern bindings."""

from __future__ import annotations

import json
import sqlite3

from vellis.domain import ObjectKind, ResolvedState
from vellis.query_domain import (
    DirectAssociation,
    PatternLink,
    PatternMatch,
    PatternNodeKind,
    PatternSelection,
)
from vellis.query_repository import compile_predicate
from vellis.search_repository import register_query_functions
from vellis.state_repository import interval_parameters, interval_sql


def select_pattern_bindings(
    connection: sqlite3.Connection,
    state: ResolvedState,
    selection: PatternSelection,
) -> tuple[PatternMatch, ...] | None:
    register_query_functions(connection)
    node_indexes = {node.name: index for index, node in enumerate(selection.nodes)}
    node_order = _connected_node_order(selection, node_indexes)
    steps = _evaluation_steps(selection, node_indexes, node_order)
    node_bindings: list[str | None] = [None] * len(selection.nodes)
    link_bindings: list[str | None] = [None] * len(selection.links)
    binding_count = len(node_order) + len(selection.links)
    cursors: list[sqlite3.Cursor] = []
    rows: list[tuple[str, ...]] = []
    depth = 0
    try:
        while True:
            if depth == len(steps):
                complete = tuple(value for value in (*node_bindings, *link_bindings) if value)
                assert len(complete) == binding_count
                rows.append(complete)
                if len(rows) > selection.maximum_matches:
                    return None
                depth -= 1
                _clear_binding(steps[depth], node_bindings, link_bindings)
                continue
            if len(cursors) == depth:
                cursors.append(
                    _candidate_cursor(
                        connection,
                        state,
                        selection,
                        node_indexes,
                        steps,
                        node_bindings,
                        link_bindings,
                        depth,
                    )
                )
            row = cursors[depth].fetchone()
            if row is not None:
                _set_binding(steps[depth], str(row["uuid"]), node_bindings, link_bindings)
                depth += 1
                continue
            cursors.pop().close()
            if depth == 0:
                break
            depth -= 1
            _clear_binding(steps[depth], node_bindings, link_bindings)
    finally:
        for cursor in cursors:
            cursor.close()
    names = tuple(node.name for node in selection.nodes) + tuple(
        link.name for link in selection.links
    )
    matches = tuple(PatternMatch(tuple(zip(names, row, strict=True))) for row in rows)
    return tuple(sorted(matches, key=lambda match: tuple(uuid for _, uuid in match.bindings)))


def _candidate_cursor(
    connection: sqlite3.Connection,
    state: ResolvedState,
    selection: PatternSelection,
    node_indexes: dict[str, int],
    steps: tuple[tuple[str, int], ...],
    node_bindings: list[str | None],
    link_bindings: list[str | None],
    depth: int,
) -> sqlite3.Cursor:
    kind, index = steps[depth]
    if kind == "node":
        return _node_candidate_cursor(
            connection,
            state,
            selection,
            index,
            node_bindings,
        )
    if kind == "association":
        return _association_candidate_cursor(
            connection,
            state,
            selection.direct_associations[index],
            node_indexes,
            node_bindings,
        )
    return _link_candidate_cursor(
        connection,
        state,
        selection.links[index],
        node_indexes,
        node_bindings,
        link_bindings,
    )


def _node_candidate_cursor(
    connection: sqlite3.Connection,
    state: ResolvedState,
    selection: PatternSelection,
    node_index: int,
    node_bindings: list[str | None],
) -> sqlite3.Cursor:
    node = selection.nodes[node_index]
    conditions = [interval_sql("v"), "v.kind = ?"]
    parameters: list[object] = [
        *interval_parameters(state),
        ObjectKind.ANCHOR.value
        if node.kind is PatternNodeKind.ANCHOR
        else ObjectKind.ASSOCIATED_DATA.value,
    ]
    _json_filter(conditions, parameters, "v.type_key", node.type_keys)
    _json_filter(conditions, parameters, "v.uuid", node.uuids)
    for predicate in node.predicates:
        condition, values = compile_predicate(connection, state, "v", predicate)
        conditions.append(condition)
        parameters.extend(values)
    bound_nodes = tuple(value for value in node_bindings if value is not None)
    _exclude_bound_uuids(conditions, parameters, "v", bound_nodes)
    return connection.execute(
        f"SELECT v.uuid FROM graph_object_version AS v WHERE {' AND '.join(conditions)}",
        parameters,
    )


def _association_candidate_cursor(
    connection: sqlite3.Connection,
    state: ResolvedState,
    association: DirectAssociation,
    node_indexes: dict[str, int],
    node_bindings: list[str | None],
) -> sqlite3.Cursor:
    anchor = node_bindings[node_indexes[association.anchor]]
    associated_data = node_bindings[node_indexes[association.associated_data]]
    assert anchor is not None and associated_data is not None
    return connection.execute(
        "SELECT a.object_uuid AS uuid FROM direct_association_version AS a "
        f"WHERE a.object_uuid = ? AND a.anchor_uuid = ? AND {interval_sql('a')} LIMIT 1",
        (associated_data, anchor, *interval_parameters(state)),
    )


def _link_candidate_cursor(
    connection: sqlite3.Connection,
    state: ResolvedState,
    link: PatternLink,
    node_indexes: dict[str, int],
    node_bindings: list[str | None],
    link_bindings: list[str | None],
) -> sqlite3.Cursor:
    conditions = [interval_sql("v"), "v.kind = 'link'"]
    parameters: list[object] = [*interval_parameters(state)]
    _json_filter(conditions, parameters, "v.type_key", link.type_keys)
    _json_filter(conditions, parameters, "v.uuid", link.uuids)
    source = node_bindings[node_indexes[link.source]]
    target = node_bindings[node_indexes[link.target]]
    assert source is not None and target is not None
    conditions.extend(("v.source_uuid = ?", "v.target_uuid = ?"))
    parameters.extend((source, target))
    prior_links = tuple(value for value in link_bindings if value is not None)
    _exclude_bound_uuids(conditions, parameters, "v", prior_links)
    return connection.execute(
        f"SELECT v.uuid FROM graph_object_version AS v WHERE {' AND '.join(conditions)}",
        parameters,
    )


def _set_binding(
    step: tuple[str, int],
    uuid: str,
    node_bindings: list[str | None],
    link_bindings: list[str | None],
) -> None:
    kind, index = step
    if kind == "node":
        node_bindings[index] = uuid
    elif kind == "link":
        link_bindings[index] = uuid


def _clear_binding(
    step: tuple[str, int],
    node_bindings: list[str | None],
    link_bindings: list[str | None],
) -> None:
    kind, index = step
    if kind == "node":
        node_bindings[index] = None
    elif kind == "link":
        link_bindings[index] = None


def _exclude_bound_uuids(
    conditions: list[str],
    parameters: list[object],
    alias: str,
    values: tuple[str, ...],
) -> None:
    if values:
        conditions.append(f"{alias}.uuid NOT IN (SELECT value FROM json_each(?))")
        parameters.append(json.dumps(values, ensure_ascii=False, separators=(",", ":")))


def _connected_node_order(
    selection: PatternSelection, node_indexes: dict[str, int]
) -> tuple[int, ...]:
    neighbors = {index: set() for index in range(len(selection.nodes))}
    for value in selection.direct_associations:
        left, right = node_indexes[value.anchor], node_indexes[value.associated_data]
        neighbors[left].add(right)
        neighbors[right].add(left)
    for value in selection.links:
        left, right = node_indexes[value.source], node_indexes[value.target]
        neighbors[left].add(right)
        neighbors[right].add(left)
    order = [0]
    remaining = set(range(1, len(selection.nodes)))
    while remaining:
        candidate = min(index for index in remaining if neighbors[index].intersection(order))
        order.append(candidate)
        remaining.remove(candidate)
    return tuple(order)


def _evaluation_steps(
    selection: PatternSelection,
    node_indexes: dict[str, int],
    node_order: tuple[int, ...],
) -> tuple[tuple[str, int], ...]:
    node_positions = {node_index: position for position, node_index in enumerate(node_order)}
    steps: list[tuple[str, int]] = []
    for position, node_index in enumerate(node_order):
        steps.append(("node", node_index))
        for index, association in enumerate(selection.direct_associations):
            endpoints = (
                node_positions[node_indexes[association.anchor]],
                node_positions[node_indexes[association.associated_data]],
            )
            if max(endpoints) == position:
                steps.append(("association", index))
        for index, link in enumerate(selection.links):
            endpoints = (
                node_positions[node_indexes[link.source]],
                node_positions[node_indexes[link.target]],
            )
            if max(endpoints) == position:
                steps.append(("link", index))
    return tuple(steps)


def _json_filter(
    conditions: list[str],
    parameters: list[object],
    column: str,
    values: tuple[str, ...],
) -> None:
    if values:
        conditions.append(f"{column} IN (SELECT value FROM json_each(?))")
        parameters.append(json.dumps(values, ensure_ascii=False, separators=(",", ":")))
