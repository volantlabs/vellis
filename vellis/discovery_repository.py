"""Targeted definition discovery through the single VEL2 definition resolver."""

from __future__ import annotations

import json
import sqlite3

from vellis.definition_repository import load_definitions
from vellis.domain import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    LinkTypeDefinition,
    ResolvedState,
)
from vellis.query_domain import DefinitionNeighborhood
from vellis.state_repository import interval_parameters, interval_sql


def load_anchor_summary(
    connection: sqlite3.Connection, state: ResolvedState, maximum: int | None = None
) -> tuple[AnchorTypeDefinition, ...]:
    rows = connection.execute(
        f"""
        SELECT type_key
        FROM definition_version AS v
        WHERE {interval_sql("v")} AND v.kind = 'anchor'
        ORDER BY type_key LIMIT ?
        """,
        (*interval_parameters(state), -1 if maximum is None else maximum),
    )
    keys = tuple(str(row["type_key"]) for row in rows)
    definitions = load_definitions(connection, state, keys)
    if any(not isinstance(value, AnchorTypeDefinition) for value in definitions):
        raise ValueError("anchor summary resolved an incompatible definition")
    return tuple(value for value in definitions if isinstance(value, AnchorTypeDefinition))


def load_neighborhoods(
    connection: sqlite3.Connection,
    state: ResolvedState,
    anchor_type_keys: tuple[str, ...],
) -> tuple[DefinitionNeighborhood, ...]:
    data_keys = _associated_data_keys(connection, state, anchor_type_keys)
    endpoint_keys = tuple(sorted({*anchor_type_keys, *data_keys}))
    link_keys = _link_keys(connection, state, endpoint_keys)
    definitions = load_definitions(
        connection,
        state,
        tuple(sorted({*anchor_type_keys, *data_keys, *link_keys})),
    )
    by_key = {definition.type_key: definition for definition in definitions}
    neighborhoods = []
    for key in anchor_type_keys:
        anchor = by_key[key]
        if not isinstance(anchor, AnchorTypeDefinition):
            raise ValueError(f"definition {key} is not an anchor type")
        data = tuple(
            value
            for value in definitions
            if isinstance(value, AssociatedDataTypeDefinition)
            and key in value.permitted_anchor_type_keys
        )
        participating = {key, *(value.type_key for value in data)}
        links = tuple(
            value
            for value in definitions
            if isinstance(value, LinkTypeDefinition)
            and participating.intersection(
                {*value.permitted_source_type_keys, *value.permitted_target_type_keys}
            )
        )
        neighborhoods.append(DefinitionNeighborhood(anchor, data, links))
    return tuple(neighborhoods)


def _associated_data_keys(
    connection: sqlite3.Connection,
    state: ResolvedState,
    anchor_type_keys: tuple[str, ...],
) -> tuple[str, ...]:
    if not anchor_type_keys:
        return ()
    encoded = json.dumps(anchor_type_keys, ensure_ascii=False, separators=(",", ":"))
    rows = connection.execute(
        f"""
        SELECT DISTINCT p.type_key
        FROM definition_permitted_type AS p
        JOIN definition_version AS v
          ON v.type_key = p.type_key AND v.valid_from_revision = p.valid_from_revision
        WHERE {interval_sql("p")} AND p.role = 'anchor'
          AND p.permitted_type_key IN (SELECT value FROM json_each(?))
        ORDER BY p.type_key
        """,
        (*interval_parameters(state), encoded),
    ).fetchall()
    return tuple(str(row["type_key"]) for row in rows)


def _link_keys(
    connection: sqlite3.Connection,
    state: ResolvedState,
    endpoint_type_keys: tuple[str, ...],
) -> tuple[str, ...]:
    if not endpoint_type_keys:
        return ()
    encoded = json.dumps(endpoint_type_keys, ensure_ascii=False, separators=(",", ":"))
    rows = connection.execute(
        f"""
        SELECT DISTINCT p.type_key
        FROM definition_permitted_type AS p
        JOIN definition_version AS v
          ON v.type_key = p.type_key AND v.valid_from_revision = p.valid_from_revision
        WHERE {interval_sql("p")} AND p.role IN ('source', 'target')
          AND p.permitted_type_key IN (SELECT value FROM json_each(?))
        ORDER BY p.type_key
        """,
        (*interval_parameters(state), encoded),
    ).fetchall()
    return tuple(str(row["type_key"]) for row in rows)
