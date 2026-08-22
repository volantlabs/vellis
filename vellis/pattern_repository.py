"""Bounded streaming evaluation of connected pattern bindings."""

from __future__ import annotations

import json
import sqlite3

from vellis.domain import ObjectKind, ResolvedState
from vellis.query_domain import (
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
    node_bindings: list[str | None] = [None] * len(selection.nodes)
    link_bindings: list[str | None] = [None] * len(selection.links)
    selector_count = len(node_order) + len(selection.links)
    cursors: list[sqlite3.Cursor] = []
    rows: list[tuple[str, ...]] = []
    depth = 0
    try:
        while True:
            if depth == selector_count:
                complete = tuple(value for value in (*node_bindings, *link_bindings) if value)
                assert len(complete) == selector_count
                rows.append(complete)
                if len(rows) > selection.maximum_matches:
                    return None
                depth -= 1
                _clear_binding(depth, node_order, node_bindings, link_bindings)
                continue
            if len(cursors) == depth:
                cursors.append(
                    _candidate_cursor(
                        connection,
                        state,
                        selection,
                        node_indexes,
                        node_order,
                        node_bindings,
                        link_bindings,
                        depth,
                    )
                )
            row = cursors[depth].fetchone()
            if row is not None:
                _set_binding(
                    depth,
                    str(row["uuid"]),
                    node_order,
                    node_bindings,
                    link_bindings,
                )
                depth += 1
                continue
            cursors.pop().close()
            if depth == 0:
                break
            depth -= 1
            _clear_binding(depth, node_order, node_bindings, link_bindings)
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
    node_order: tuple[int, ...],
    node_bindings: list[str | None],
    link_bindings: list[str | None],
    depth: int,
) -> sqlite3.Cursor:
    if depth < len(node_order):
        return _node_candidate_cursor(
            connection,
            state,
            selection,
            node_indexes,
            node_order[depth],
            node_bindings,
        )
    link_index = depth - len(node_order)
    return _link_candidate_cursor(
        connection,
        state,
        selection.links[link_index],
        node_indexes,
        node_bindings,
        link_bindings,
    )


def _node_candidate_cursor(
    connection: sqlite3.Connection,
    state: ResolvedState,
    selection: PatternSelection,
    node_indexes: dict[str, int],
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
    _node_relationship_conditions(
        state,
        selection,
        node_indexes,
        node_index,
        node_bindings,
        conditions,
        parameters,
    )
    return connection.execute(
        f"SELECT v.uuid FROM graph_object_version AS v WHERE {' AND '.join(conditions)}",
        parameters,
    )


def _node_relationship_conditions(
    state: ResolvedState,
    selection: PatternSelection,
    node_indexes: dict[str, int],
    node_index: int,
    node_bindings: list[str | None],
    conditions: list[str],
    parameters: list[object],
) -> None:
    for value in selection.direct_associations:
        anchor = node_indexes[value.anchor]
        data = node_indexes[value.associated_data]
        if node_index not in {anchor, data}:
            continue
        other = data if node_index == anchor else anchor
        if node_bindings[other] is None:
            continue
        object_sql = _current_or_bound(data, node_index, node_bindings, parameters)
        anchor_sql = _current_or_bound(anchor, node_index, node_bindings, parameters)
        conditions.append(
            "EXISTS (SELECT 1 FROM direct_association_version AS a "
            f"WHERE a.object_uuid = {object_sql} AND a.anchor_uuid = {anchor_sql} "
            f"AND {interval_sql('a')})"
        )
        parameters.extend(interval_parameters(state))
    for link in selection.links:
        source = node_indexes[link.source]
        target = node_indexes[link.target]
        if node_index not in {source, target}:
            continue
        other = target if node_index == source else source
        if node_bindings[other] is None:
            continue
        link_conditions = [interval_sql("l"), "l.kind = 'link'"]
        link_parameters: list[object] = [*interval_parameters(state)]
        _json_filter(link_conditions, link_parameters, "l.type_key", link.type_keys)
        _json_filter(link_conditions, link_parameters, "l.uuid", link.uuids)
        source_sql = _current_or_bound(source, node_index, node_bindings, link_parameters)
        target_sql = _current_or_bound(target, node_index, node_bindings, link_parameters)
        link_conditions.extend((f"l.source_uuid = {source_sql}", f"l.target_uuid = {target_sql}"))
        conditions.append(
            "EXISTS (SELECT 1 FROM graph_object_version AS l "
            f"WHERE {' AND '.join(link_conditions)})"
        )
        parameters.extend(link_parameters)


def _current_or_bound(
    index: int,
    current: int,
    node_bindings: list[str | None],
    parameters: list[object],
) -> str:
    if index == current:
        return "v.uuid"
    value = node_bindings[index]
    assert value is not None
    parameters.append(value)
    return "?"


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
    depth: int,
    uuid: str,
    node_order: tuple[int, ...],
    node_bindings: list[str | None],
    link_bindings: list[str | None],
) -> None:
    if depth < len(node_order):
        node_bindings[node_order[depth]] = uuid
    else:
        link_bindings[depth - len(node_order)] = uuid


def _clear_binding(
    depth: int,
    node_order: tuple[int, ...],
    node_bindings: list[str | None],
    link_bindings: list[str | None],
) -> None:
    if depth < len(node_order):
        node_bindings[node_order[depth]] = None
    else:
        link_bindings[depth - len(node_order)] = None


def _exclude_bound_uuids(
    conditions: list[str],
    parameters: list[object],
    alias: str,
    values: tuple[str, ...],
) -> None:
    if values:
        conditions.append(f"{alias}.uuid NOT IN ({', '.join('?' for _ in values)})")
        parameters.extend(values)


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


def _json_filter(
    conditions: list[str],
    parameters: list[object],
    column: str,
    values: tuple[str, ...],
) -> None:
    if values:
        conditions.append(f"{column} IN (SELECT value FROM json_each(?))")
        parameters.append(json.dumps(values, ensure_ascii=False, separators=(",", ":")))
