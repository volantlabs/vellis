"""Streaming validation over current or connection-local draft-overlay SQL state."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from vellis.definition_repository import load_definitions
from vellis.domain import (
    AssociatedDataTypeDefinition,
    Finding,
    FindingCode,
    LinkTypeDefinition,
    ResolvedState,
)
from vellis.domain_validation import graph_object_findings, type_definition_findings
from vellis.draft_repository import load_draft_definitions
from vellis.draft_sql_overlay import install_draft_graph_overlay
from vellis.graph_repository import load_graph_objects
from vellis.json_pointer import append_pointer

_BATCH = 100


def effective_findings(
    connection: sqlite3.Connection,
    state: ResolvedState,
    *,
    draft: bool,
) -> Iterator[Finding]:
    """Yield deterministic findings while retaining at most one bounded object batch."""
    if draft:
        install_draft_graph_overlay(connection)
    yield from _definition_findings(connection, state, draft)
    yield from _object_findings(connection, state, draft)
    yield from _cardinality_findings(connection, state, draft)
    if draft:
        yield from _unmaterializable_findings(connection)


def _definition_findings(connection, state, draft):
    for key in _effective_definition_keys(connection, draft):
        selected = _effective_definitions(connection, state, (key,), draft)
        if not selected:
            continue
        definition = selected[0]
        references = _definition_references(definition)
        context = _effective_definitions(connection, state, references, draft)
        yield from type_definition_findings(
            definition,
            context,
            require_system=not draft,
        )


def _object_findings(connection, state, draft):
    cursor = connection.execute(
        "SELECT uuid FROM graph_object_version WHERE valid_to_revision IS NULL ORDER BY uuid"
    )
    while rows := cursor.fetchmany(_BATCH):
        for row in rows:
            uuid = str(row[0])
            loaded = load_graph_objects(connection, state, (uuid,))
            if not loaded:
                continue
            value = loaded[0]
            reference_uuids = _object_references(connection, uuid)
            referents = load_graph_objects(connection, state, reference_uuids)
            type_keys = tuple(sorted({value.type_key, *(item.type_key for item in referents)}))
            definitions = _effective_definitions(connection, state, type_keys, draft)
            yield from graph_object_findings(
                value, definitions, referents, require_system=not draft
            )


def _cardinality_findings(connection, state, draft):
    for key in _effective_definition_keys(connection, draft):
        values = _effective_definitions(connection, state, (key,), draft)
        if not values:
            continue
        definition = values[0]
        if isinstance(definition, AssociatedDataTypeDefinition):
            yield from _data_cardinality_findings(connection, definition)
        elif isinstance(definition, LinkTypeDefinition):
            yield from _link_cardinality_findings(connection, definition)


def _data_cardinality_findings(connection, definition):
    rows = connection.execute(
        """SELECT o.uuid, count(a.anchor_uuid)
           FROM graph_object_version AS o
           LEFT JOIN direct_association_version AS a
             ON a.object_uuid = o.uuid AND a.valid_to_revision IS NULL
           WHERE o.valid_to_revision IS NULL AND o.type_key = ?
           GROUP BY o.uuid ORDER BY o.uuid""",
        (definition.type_key,),
    )
    for uuid, count in rows:
        finding = _count_finding(
            int(count),
            definition.anchors_per_object,
            "anchors per object",
            definition.type_key,
            str(uuid),
        )
        if finding is not None:
            yield finding
    permitted = _json_values(definition.permitted_anchor_type_keys)
    rows = connection.execute(
        """SELECT anchor.uuid, count(data.uuid)
           FROM graph_object_version AS anchor
           LEFT JOIN direct_association_version AS a
             ON a.anchor_uuid = anchor.uuid AND a.valid_to_revision IS NULL
           LEFT JOIN graph_object_version AS data
             ON data.uuid = a.object_uuid AND data.valid_to_revision IS NULL AND data.type_key = ?
           WHERE anchor.valid_to_revision IS NULL
             AND anchor.type_key IN (SELECT value FROM json_each(?))
           GROUP BY anchor.uuid ORDER BY anchor.uuid""",
        (definition.type_key, permitted),
    )
    for uuid, count in rows:
        finding = _count_finding(
            int(count),
            definition.objects_per_anchor,
            "objects per anchor",
            definition.type_key,
            str(uuid),
        )
        if finding is not None:
            yield finding


def _link_cardinality_findings(connection, definition):
    yield from _link_role_findings(
        connection,
        definition.type_key,
        definition.permitted_source_type_keys,
        definition.links_per_source,
        "source_uuid",
        "links per source",
    )
    yield from _link_role_findings(
        connection,
        definition.type_key,
        definition.permitted_target_type_keys,
        definition.links_per_target,
        "target_uuid",
        "links per target",
    )


def _link_role_findings(connection, type_key, permitted, bound, column, label):
    rows = connection.execute(
        f"""SELECT endpoint.uuid, count(link.uuid)
            FROM graph_object_version AS endpoint
            LEFT JOIN graph_object_version AS link
              ON link.{column} = endpoint.uuid AND link.valid_to_revision IS NULL
             AND link.type_key = ?
            WHERE endpoint.valid_to_revision IS NULL
              AND endpoint.type_key IN (SELECT value FROM json_each(?))
            GROUP BY endpoint.uuid ORDER BY endpoint.uuid""",
        (type_key, _json_values(permitted)),
    )
    for uuid, count in rows:
        finding = _count_finding(int(count), bound, label, type_key, str(uuid))
        if finding is not None:
            yield finding


def _count_finding(count, bound, label, type_key, uuid):
    if count >= bound.minimum and (bound.maximum is None or count <= bound.maximum):
        return None
    return Finding(
        FindingCode.CARDINALITY_VIOLATION,
        f"{label} count {count} is outside {bound.minimum}..{bound.maximum}",
        append_pointer("/objects", uuid),
        type_keys=(type_key,),
        uuids=(uuid,),
    )


def _effective_definition_keys(connection, draft):
    if not draft:
        rows = connection.execute(
            """SELECT type_key FROM main.definition_version
               WHERE valid_to_revision IS NULL ORDER BY type_key"""
        )
    else:
        rows = connection.execute(
            """SELECT type_key FROM main.definition_version WHERE valid_to_revision IS NULL
               UNION SELECT type_key FROM main.draft_definition_entry ORDER BY type_key"""
        )
    return (str(row[0]) for row in rows)


def _effective_definitions(connection, state, keys, draft):
    if not keys:
        return ()
    current = load_definitions(connection, state, keys)
    return load_draft_definitions(connection, current, keys) if draft else current


def _definition_references(definition):
    if isinstance(definition, AssociatedDataTypeDefinition):
        return definition.permitted_anchor_type_keys
    if isinstance(definition, LinkTypeDefinition):
        return tuple(
            dict.fromkeys(
                (*definition.permitted_source_type_keys, *definition.permitted_target_type_keys)
            )
        )
    return ()


def _object_references(connection, uuid):
    row = connection.execute(
        """SELECT source_uuid, target_uuid FROM graph_object_version
           WHERE valid_to_revision IS NULL AND uuid = ?""",
        (uuid,),
    ).fetchone()
    values = set()
    if row is not None:
        values.update(str(value) for value in row if value is not None)
    values.update(
        str(item[0])
        for item in connection.execute(
            """SELECT anchor_uuid FROM direct_association_version
               WHERE valid_to_revision IS NULL AND object_uuid = ?""",
            (uuid,),
        )
    )
    return tuple(sorted(values))


def _unmaterializable_findings(connection):
    rows = connection.execute(
        """SELECT p.uuid FROM main.draft_graph_object_patch AS p
           WHERE p.tombstone = 0 AND NOT EXISTS (
               SELECT 1 FROM temp.graph_object_version AS v WHERE v.uuid = p.uuid
           ) ORDER BY p.uuid"""
    )
    for row in rows:
        uuid = str(row[0])
        yield Finding(
            FindingCode.MISSING,
            "staged partial object has no live base",
            append_pointer("/objects", uuid),
            uuids=(uuid,),
        )


def _json_values(values):
    import json

    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))
