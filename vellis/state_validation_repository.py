"""Bounded-memory validation of one indexed canonical state."""

from __future__ import annotations

import json
import sqlite3

from vellis.definition_repository import load_definitions
from vellis.domain import (
    AssociatedData,
    AssociatedDataTypeDefinition,
    Finding,
    FindingCode,
    Link,
    LinkTypeDefinition,
    ResolvedState,
    TypeDefinition,
)
from vellis.domain_validation import graph_object_findings, type_definition_findings
from vellis.graph_repository import load_graph_objects
from vellis.state_repository import interval_parameters, interval_sql


def first_state_finding(connection: sqlite3.Connection, state: ResolvedState) -> Finding | None:
    """Return the first conformance finding while retaining one object at a time."""
    finding = _first_definition_finding(connection, state)
    if finding is not None:
        return finding
    finding = _first_graph_finding(connection, state)
    if finding is not None:
        return finding
    return _first_cardinality_finding(connection, state)


def _first_definition_finding(connection, state):
    cursor = connection.execute(
        f"SELECT type_key FROM definition_version v WHERE {interval_sql('v')} ORDER BY type_key",
        interval_parameters(state),
    )
    for row in cursor:
        definitions = load_definitions(connection, state, (str(row[0]),))
        if not definitions:
            return Finding(FindingCode.MISSING, "definition version could not be decoded")
        definition = definitions[0]
        references = load_definitions(connection, state, _reference_keys(definition))
        findings = type_definition_findings(definition, references, require_system=True)
        if findings:
            return findings[0]
    return None


def _reference_keys(definition: TypeDefinition) -> tuple[str, ...]:
    if isinstance(definition, AssociatedDataTypeDefinition):
        return definition.permitted_anchor_type_keys
    if isinstance(definition, LinkTypeDefinition):
        return tuple(
            sorted(
                set(definition.permitted_source_type_keys)
                | set(definition.permitted_target_type_keys)
            )
        )
    return ()


def _first_graph_finding(connection, state):
    cursor = connection.execute(
        f"SELECT uuid FROM graph_object_version v WHERE {interval_sql('v')} ORDER BY uuid",
        interval_parameters(state),
    )
    for row in cursor:
        values = load_graph_objects(connection, state, (str(row[0]),))
        if not values:
            return Finding(FindingCode.MISSING, "graph object version could not be decoded")
        value = values[0]
        reference_keys = _object_reference_keys(value)
        referents = load_graph_objects(connection, state, reference_keys)
        type_keys = tuple(sorted({value.type_key, *(item.type_key for item in referents)}))
        definitions = load_definitions(connection, state, type_keys)
        findings = graph_object_findings(value, definitions, referents, require_system=True)
        if findings:
            return findings[0]
    return None


def _object_reference_keys(value) -> tuple[str, ...]:
    if isinstance(value, AssociatedData):
        return value.anchor_uuids
    if isinstance(value, Link):
        return tuple(sorted({value.source_uuid, value.target_uuid}))
    return ()


def _first_cardinality_finding(connection, state):
    cursor = connection.execute(
        f"""SELECT type_key FROM definition_version v
            WHERE {interval_sql("v")} AND kind IN ('associatedData', 'link')
            ORDER BY type_key""",
        interval_parameters(state),
    )
    for row in cursor:
        definitions = load_definitions(connection, state, (str(row[0]),))
        if not definitions:
            continue
        definition = definitions[0]
        if isinstance(definition, AssociatedDataTypeDefinition):
            label = _associated_cardinality_violation(connection, state, definition)
        else:
            assert isinstance(definition, LinkTypeDefinition)
            label = _link_cardinality_violation(connection, state, definition)
        if label is not None:
            return Finding(
                FindingCode.CARDINALITY_VIOLATION,
                f"{definition.type_key} violates {label}",
                type_keys=(definition.type_key,),
            )
    return None


def _associated_cardinality_violation(connection, state, definition):
    if _object_count_violation(
        connection,
        state,
        definition.type_key,
        definition.anchors_per_object.minimum,
        definition.anchors_per_object.maximum,
    ):
        return "anchorsPerObject"
    if _anchor_count_violation(connection, state, definition):
        return "objectsPerAnchor"
    return None


def _object_count_violation(connection, state, type_key, minimum, maximum):
    rows = connection.execute(
        f"""SELECT g.uuid, count(a.anchor_uuid) AS member_count
            FROM graph_object_version g
            LEFT JOIN direct_association_version a ON a.object_uuid = g.uuid
              AND {interval_sql("a")}
            WHERE {interval_sql("g")} AND g.type_key = ? GROUP BY g.uuid""",
        (*interval_parameters(state), *interval_parameters(state), type_key),
    )
    return any(_outside(int(row["member_count"]), minimum, maximum) for row in rows)


def _anchor_count_violation(connection, state, definition):
    permitted = json.dumps(definition.permitted_anchor_type_keys, separators=(",", ":"))
    rows = connection.execute(
        f"""SELECT anchor.uuid, count(d.uuid) AS member_count
            FROM graph_object_version anchor
            LEFT JOIN direct_association_version a ON a.anchor_uuid = anchor.uuid
              AND {interval_sql("a")}
            LEFT JOIN graph_object_version d ON d.uuid = a.object_uuid
              AND {interval_sql("d")} AND d.type_key = ?
            WHERE {interval_sql("anchor")} AND anchor.kind = 'anchor'
              AND anchor.type_key IN (SELECT value FROM json_each(?))
            GROUP BY anchor.uuid""",
        (
            *interval_parameters(state),
            *interval_parameters(state),
            definition.type_key,
            *interval_parameters(state),
            permitted,
        ),
    )
    bounds = definition.objects_per_anchor
    return any(_outside(int(row["member_count"]), bounds.minimum, bounds.maximum) for row in rows)


def _link_cardinality_violation(connection, state, definition):
    roles = (
        ("source_uuid", definition.permitted_source_type_keys, definition.links_per_source),
        ("target_uuid", definition.permitted_target_type_keys, definition.links_per_target),
    )
    for column, permitted_keys, bounds in roles:
        permitted = json.dumps(permitted_keys, separators=(",", ":"))
        rows = connection.execute(
            f"""SELECT subject.uuid, count(link.uuid) AS member_count
                FROM graph_object_version subject
                LEFT JOIN graph_object_version link ON link.{column} = subject.uuid
                  AND {interval_sql("link")} AND link.type_key = ?
                WHERE {interval_sql("subject")}
                  AND subject.type_key IN (SELECT value FROM json_each(?))
                GROUP BY subject.uuid""",
            (
                *interval_parameters(state),
                definition.type_key,
                *interval_parameters(state),
                permitted,
            ),
        )
        if any(_outside(int(row["member_count"]), bounds.minimum, bounds.maximum) for row in rows):
            return "linksPerSource" if column == "source_uuid" else "linksPerTarget"
    return None


def _outside(count: int, minimum: int, maximum: int | None) -> bool:
    return count < minimum or (maximum is not None and count > maximum)
