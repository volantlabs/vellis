"""Normalized persistence and mechanical overlay for the sole metadata-free draft."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from typing import Any

from vellis.canonical_encoding import Record, ordered_values_hash
from vellis.definition_repository import _bounds
from vellis.domain import (
    Anchor,
    AnchorTypeDefinition,
    AnchorUpsert,
    AssociatedData,
    AssociatedDataTypeDefinition,
    AssociatedDataUpsert,
    Cardinality,
    GraphObject,
    Link,
    LinkTypeDefinition,
    LinkUpsert,
    ObjectKind,
    PropertyDefinition,
    TypeDefinition,
    ValueKind,
)
from vellis.sqlite_values import bound_columns, bound_from_row, property_columns, property_from_row


def draft_present(connection: sqlite3.Connection) -> bool:
    return (
        connection.execute("SELECT 1 FROM draft_metadata WHERE singleton = 1").fetchone()
        is not None
    )


def raw_entry_count(connection: sqlite3.Connection) -> int:
    return sum(
        int(connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0])
        for relation in ("draft_definition_entry", "draft_graph_object_patch")
    )


def ensure_draft(connection: sqlite3.Connection) -> None:
    connection.execute("INSERT OR IGNORE INTO draft_metadata(singleton) VALUES (1)")


def remove_draft_if_empty(connection: sqlite3.Connection) -> None:
    if raw_entry_count(connection) == 0:
        connection.execute("DELETE FROM validation_run WHERE scope = 'draft'")
        connection.execute("DELETE FROM draft_metadata WHERE singleton = 1")


def clear_draft(connection: sqlite3.Connection) -> None:
    connection.execute("DELETE FROM validation_run WHERE scope = 'draft'")
    for relation in (
        "draft_definition_permitted_type",
        "draft_property_definition_allowed_value",
        "draft_property_definition_entry",
        "draft_definition_entry",
        "draft_association_operation",
        "draft_property_operation",
        "draft_graph_object_patch",
        "draft_metadata",
    ):
        connection.execute(f"DELETE FROM {relation}")


def stage_definition(connection: sqlite3.Connection, definition: TypeDefinition) -> None:
    if definition.system is not None:
        raise ValueError("draft definition cannot supply system metadata")
    ensure_draft(connection)
    _delete_definition_children(connection, definition.type_key)
    bounds = _bounds(definition)
    connection.execute(
        """INSERT OR REPLACE INTO draft_definition_entry(
           type_key, operation, kind, description,
           anchors_per_object_minimum, anchors_per_object_maximum,
           objects_per_anchor_minimum, objects_per_anchor_maximum,
           links_per_source_minimum, links_per_source_maximum,
           links_per_target_minimum, links_per_target_maximum)
           VALUES (?, 'replace', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (definition.type_key, definition.kind.value, definition.description, *bounds),
    )
    for role, key in _permitted(definition):
        connection.execute(
            """INSERT INTO draft_definition_permitted_type(
               type_key, role, permitted_type_key) VALUES (?, ?, ?)""",
            (definition.type_key, role, key),
        )
    if isinstance(definition, AssociatedDataTypeDefinition):
        for prop in definition.properties:
            _stage_property_definition(connection, definition.type_key, prop)


def stage_definition_removal(connection: sqlite3.Connection, type_key: str) -> None:
    ensure_draft(connection)
    _delete_definition_children(connection, type_key)
    connection.execute(
        """INSERT OR REPLACE INTO draft_definition_entry(type_key, operation)
           VALUES (?, 'remove')""",
        (type_key,),
    )


def unstage_definition(connection: sqlite3.Connection, type_key: str) -> None:
    _delete_definition_children(connection, type_key)
    connection.execute("DELETE FROM draft_definition_entry WHERE type_key = ?", (type_key,))


def stage_object_upsert(
    connection: sqlite3.Connection,
    upsert: AnchorUpsert | AssociatedDataUpsert | LinkUpsert,
) -> None:
    ensure_draft(connection)
    row = connection.execute(
        "SELECT * FROM draft_graph_object_patch WHERE uuid = ?", (upsert.uuid,)
    ).fetchone()
    restarting = row is None or bool(row["tombstone"])
    if row is not None and str(row["kind"]) != upsert.kind.value and not bool(row["tombstone"]):
        raise ValueError("a staged object kind cannot change")
    if restarting:
        _delete_object_children(connection, upsert.uuid)
        connection.execute("DELETE FROM draft_graph_object_patch WHERE uuid = ?", (upsert.uuid,))
        connection.execute(
            "INSERT INTO draft_graph_object_patch(uuid, kind) VALUES (?, ?)",
            (upsert.uuid, upsert.kind.value),
        )
    _merge_structural_patch(connection, upsert)
    if isinstance(upsert, AssociatedDataUpsert):
        _merge_data_patch(connection, upsert, restarting)


def stage_object_removal(connection: sqlite3.Connection, uuid: str, kind: ObjectKind) -> None:
    ensure_draft(connection)
    _delete_object_children(connection, uuid)
    connection.execute(
        """INSERT OR REPLACE INTO draft_graph_object_patch(uuid, kind, tombstone)
           VALUES (?, ?, 1)""",
        (uuid, kind.value),
    )


def unstage_object(connection: sqlite3.Connection, uuid: str) -> None:
    _delete_object_children(connection, uuid)
    connection.execute("DELETE FROM draft_graph_object_patch WHERE uuid = ?", (uuid,))


def load_draft_definitions(
    connection: sqlite3.Connection,
    current: tuple[TypeDefinition, ...],
    type_keys: tuple[str, ...] | None = None,
) -> tuple[TypeDefinition, ...]:
    values = {value.type_key: value for value in current}
    if type_keys is None:
        rows = connection.execute(
            "SELECT * FROM draft_definition_entry ORDER BY type_key"
        ).fetchall()
    elif not type_keys:
        rows = ()
    else:
        placeholders = ",".join("?" for _ in type_keys)
        rows = connection.execute(
            f"""SELECT * FROM draft_definition_entry
                WHERE type_key IN ({placeholders}) ORDER BY type_key""",
            type_keys,
        ).fetchall()
    for row in rows:
        key = str(row["type_key"])
        if str(row["operation"]) == "remove":
            values.pop(key, None)
            continue
        replacement = _definition_from_draft(connection, row)
        existing = values.get(key)
        if existing is not None:
            replacement = replace(replacement, system=existing.system)
        values[key] = replacement
    return tuple(values[key] for key in sorted(values))


def load_draft_graph(
    connection: sqlite3.Connection,
    current: tuple[GraphObject, ...],
    uuids: tuple[str, ...] | None = None,
) -> tuple[tuple[GraphObject, ...], tuple[str, ...]]:
    values = {value.uuid: value for value in current}
    unmaterializable: list[str] = []
    if uuids is None:
        rows = connection.execute("SELECT * FROM draft_graph_object_patch ORDER BY uuid").fetchall()
    elif not uuids:
        rows = ()
    else:
        placeholders = ",".join("?" for _ in uuids)
        rows = connection.execute(
            f"""SELECT * FROM draft_graph_object_patch
                WHERE uuid IN ({placeholders}) ORDER BY uuid""",
            uuids,
        ).fetchall()
    for row in rows:
        uuid = str(row["uuid"])
        if bool(row["tombstone"]):
            values.pop(uuid, None)
            continue
        try:
            values[uuid] = _overlay_object(connection, row, values.get(uuid))
        except ValueError:
            values.pop(uuid, None)
            unmaterializable.append(uuid)
    return tuple(values[key] for key in sorted(values)), tuple(unmaterializable)


def draft_fingerprint(connection: sqlite3.Connection) -> bytes:
    digest = computed_draft_fingerprint(connection)
    connection.execute("UPDATE draft_metadata SET fingerprint = ? WHERE singleton = 1", (digest,))
    return digest


def computed_draft_fingerprint(connection: sqlite3.Connection) -> bytes:
    """Compute the normalized draft digest without mutating metadata."""
    relations = (
        ("draft_definition_entry", "type_key"),
        ("draft_definition_permitted_type", "type_key, role, permitted_type_key"),
        ("draft_property_definition_entry", "type_key, property_name"),
        (
            "draft_property_definition_allowed_value",
            "type_key, property_name, ordinal",
        ),
        ("draft_graph_object_patch", "uuid"),
        ("draft_association_operation", "object_uuid, anchor_uuid"),
        ("draft_property_operation", "object_uuid, property_name"),
    )

    def rows():
        for relation, ordering in relations:
            cursor = connection.execute(f"SELECT * FROM {relation} ORDER BY {ordering}")
            names = tuple(value[0] for value in cursor.description)
            for row in cursor:
                fields: tuple[tuple[str, Any], ...] = (
                    ("relation", relation),
                    *((name, row[name]) for name in names),
                )
                yield Record(fields)

    return ordered_values_hash(rows)


def _merge_structural_patch(connection, upsert) -> None:
    updates: list[str] = []
    values: list[object] = []
    for field_name, column in (
        ("type_key", "type_key"),
        ("display_name", "display_name"),
        ("source_uuid", "source_uuid"),
        ("target_uuid", "target_uuid"),
    ):
        if not hasattr(upsert, field_name):
            continue
        value = getattr(upsert, field_name)
        if value is not None:
            updates.extend((f"has_{column} = 1", f"{column} = ?"))
            values.append(value)
    if updates:
        connection.execute(
            f"UPDATE draft_graph_object_patch SET {', '.join(updates)} WHERE uuid = ?",
            (*values, upsert.uuid),
        )


def _merge_data_patch(connection, upsert: AssociatedDataUpsert, restarting: bool) -> None:
    if upsert.anchor_uuids is not None:
        connection.execute(
            "UPDATE draft_graph_object_patch SET has_complete_anchor_set = 1 WHERE uuid = ?",
            (upsert.uuid,),
        )
        connection.execute(
            "DELETE FROM draft_association_operation WHERE object_uuid = ?", (upsert.uuid,)
        )
        for uuid in upsert.anchor_uuids:
            connection.execute(
                "INSERT INTO draft_association_operation VALUES (?, ?, 'base')",
                (upsert.uuid, uuid),
            )
    elif restarting and (upsert.add_anchor_uuids or upsert.remove_anchor_uuids):
        pass
    for uuid in upsert.add_anchor_uuids:
        connection.execute(
            "INSERT OR REPLACE INTO draft_association_operation VALUES (?, ?, 'add')",
            (upsert.uuid, uuid),
        )
    for uuid in upsert.remove_anchor_uuids:
        connection.execute(
            "INSERT OR REPLACE INTO draft_association_operation VALUES (?, ?, 'remove')",
            (upsert.uuid, uuid),
        )
    for name, value in upsert.set_properties:
        columns = (
            {
                "value_kind": None,
                "is_null": 1,
                "boolean_value": None,
                "integer_value": None,
                "number_value": None,
                "text_value": None,
                "date_value": None,
                "timestamp_epoch_seconds": None,
                "timestamp_nanosecond": None,
                "timestamp_text": None,
            }
            if value is None
            else property_columns(value, value.kind)
        )
        connection.execute(
            """INSERT OR REPLACE INTO draft_property_operation(
               object_uuid, property_name, operation, value_kind, is_null,
               boolean_value, integer_value, number_value, text_value, date_value,
               timestamp_epoch_seconds, timestamp_nanosecond, timestamp_text)
               VALUES (:object_uuid, :property_name, 'set', :value_kind, :is_null,
               :boolean_value, :integer_value, :number_value, :text_value, :date_value,
               :timestamp_epoch_seconds, :timestamp_nanosecond, :timestamp_text)""",
            {**columns, "object_uuid": upsert.uuid, "property_name": name},
        )
    for name in upsert.remove_properties:
        connection.execute(
            """INSERT OR REPLACE INTO draft_property_operation(
               object_uuid, property_name, operation) VALUES (?, ?, 'remove')""",
            (upsert.uuid, name),
        )


def _overlay_object(connection, row, existing) -> GraphObject:
    kind = ObjectKind(str(row["kind"]))
    if existing is not None and existing.kind is not kind:
        raise ValueError("draft kind conflicts with live kind")
    type_key = (
        str(row["type_key"])
        if bool(row["has_type_key"])
        else (None if existing is None else existing.type_key)
    )
    if kind is ObjectKind.ANCHOR:
        return _overlay_anchor(row, existing, type_key)
    if kind is ObjectKind.LINK:
        return _overlay_link(row, existing, type_key)
    return _overlay_data(connection, row, existing, type_key)


def _overlay_anchor(row, existing, type_key):
    display = (
        str(row["display_name"])
        if bool(row["has_display_name"])
        else (None if existing is None else existing.display_name)
    )
    if type_key is None or display is None:
        raise ValueError("partial anchor has no live base")
    return Anchor(
        str(row["uuid"]), type_key, display, None if existing is None else existing.system
    )


def _overlay_link(row, existing, type_key):
    source = (
        str(row["source_uuid"])
        if bool(row["has_source_uuid"])
        else (None if existing is None else existing.source_uuid)
    )
    target = (
        str(row["target_uuid"])
        if bool(row["has_target_uuid"])
        else (None if existing is None else existing.target_uuid)
    )
    if type_key is None or source is None or target is None:
        raise ValueError("partial link has no live base")
    return Link(
        str(row["uuid"]), type_key, source, target, None if existing is None else existing.system
    )


def _overlay_data(connection, row, existing, type_key):
    if type_key is None:
        raise ValueError("partial associated data has no live base")
    if existing is None and not bool(row["has_complete_anchor_set"]):
        raise ValueError("partial associated data has no complete anchor base")
    anchors: set[str] = set(() if existing is None else existing.anchor_uuids)
    if bool(row["has_complete_anchor_set"]):
        anchors.clear()
    operations = connection.execute(
        "SELECT anchor_uuid, operation FROM draft_association_operation WHERE object_uuid = ?",
        (row["uuid"],),
    ).fetchall()
    for operation in operations:
        if str(operation["operation"]) in {"base", "add"}:
            anchors.add(str(operation["anchor_uuid"]))
        else:
            anchors.discard(str(operation["anchor_uuid"]))
    if not anchors:
        raise ValueError("associated data has no anchors")
    properties = dict(() if existing is None else existing.properties)
    for operation in connection.execute(
        "SELECT * FROM draft_property_operation WHERE object_uuid = ? ORDER BY property_name",
        (row["uuid"],),
    ):
        name = str(operation["property_name"])
        if str(operation["operation"]) == "remove":
            properties.pop(name, None)
        else:
            properties[name] = property_from_row(operation)
    return AssociatedData(
        str(row["uuid"]),
        type_key,
        tuple(anchors),
        tuple(properties.items()),
        None if existing is None else existing.system,
    )


def _stage_property_definition(connection, type_key: str, prop: PropertyDefinition) -> None:
    columns = {**bound_columns(prop.minimum, "minimum"), **bound_columns(prop.maximum, "maximum")}
    connection.execute(
        """INSERT INTO draft_property_definition_entry(
           type_key, property_name, description, value_kind, required, nullable,
           minimum_kind, minimum_integer, minimum_number, minimum_date,
           minimum_timestamp_epoch_seconds, minimum_timestamp_nanosecond, minimum_timestamp_text,
           maximum_kind, maximum_integer, maximum_number, maximum_date,
           maximum_timestamp_epoch_seconds, maximum_timestamp_nanosecond, maximum_timestamp_text,
           minimum_length, maximum_length, pattern)
           VALUES (:type_key, :property_name, :description, :value_kind, :required, :nullable,
           :minimum_kind, :minimum_integer, :minimum_number, :minimum_date,
           :minimum_timestamp_epoch_seconds, :minimum_timestamp_nanosecond, :minimum_timestamp_text,
           :maximum_kind, :maximum_integer, :maximum_number, :maximum_date,
           :maximum_timestamp_epoch_seconds, :maximum_timestamp_nanosecond, :maximum_timestamp_text,
           :minimum_length, :maximum_length, :pattern)""",
        {
            **columns,
            "type_key": type_key,
            "property_name": prop.name,
            "description": prop.description,
            "value_kind": prop.value_kind.value,
            "required": int(prop.required),
            "nullable": int(prop.nullable),
            "minimum_length": None if prop.minimum_length is None else str(prop.minimum_length),
            "maximum_length": None if prop.maximum_length is None else str(prop.maximum_length),
            "pattern": prop.pattern,
        },
    )
    for ordinal, value in enumerate(prop.allowed_values):
        columns = property_columns(value, value.kind)
        connection.execute(
            """INSERT INTO draft_property_definition_allowed_value(
               type_key, property_name, ordinal, value_kind, boolean_value, integer_value,
               number_value, text_value, date_value, timestamp_epoch_seconds,
               timestamp_nanosecond, timestamp_text)
               VALUES (:type_key, :property_name, :ordinal, :value_kind, :boolean_value,
               :integer_value, :number_value, :text_value, :date_value,
               :timestamp_epoch_seconds, :timestamp_nanosecond, :timestamp_text)""",
            {**columns, "type_key": type_key, "property_name": prop.name, "ordinal": ordinal},
        )


def _definition_from_draft(connection, row) -> TypeDefinition:
    key = str(row["type_key"])
    kind = str(row["kind"])
    if kind == "anchor":
        return AnchorTypeDefinition(key, str(row["description"]))
    members = connection.execute(
        """SELECT role, permitted_type_key FROM draft_definition_permitted_type
           WHERE type_key = ? ORDER BY role, permitted_type_key""",
        (key,),
    ).fetchall()
    grouped = {
        role: tuple(str(v["permitted_type_key"]) for v in members if str(v["role"]) == role)
        for role in ("anchor", "source", "target")
    }
    if kind == "associatedData":
        props = _draft_properties(connection, key)
        return AssociatedDataTypeDefinition(
            key,
            str(row["description"]),
            grouped["anchor"],
            props,
            Cardinality(
                int(row["anchors_per_object_minimum"]),
                _optional_int(row["anchors_per_object_maximum"]),
            ),
            Cardinality(
                int(row["objects_per_anchor_minimum"]),
                _optional_int(row["objects_per_anchor_maximum"]),
            ),
        )
    return LinkTypeDefinition(
        key,
        str(row["description"]),
        grouped["source"],
        grouped["target"],
        Cardinality(
            int(row["links_per_source_minimum"]), _optional_int(row["links_per_source_maximum"])
        ),
        Cardinality(
            int(row["links_per_target_minimum"]), _optional_int(row["links_per_target_maximum"])
        ),
    )


def _draft_properties(connection, key: str) -> tuple[PropertyDefinition, ...]:
    rows = connection.execute(
        "SELECT * FROM draft_property_definition_entry WHERE type_key = ? ORDER BY property_name",
        (key,),
    ).fetchall()
    result = []
    for row in rows:
        allowed_rows = connection.execute(
            """SELECT * FROM draft_property_definition_allowed_value
               WHERE type_key = ? AND property_name = ? ORDER BY ordinal""",
            (key, row["property_name"]),
        ).fetchall()
        allowed_values = tuple(
            property_from_row({**dict(value), "is_null": 0}) for value in allowed_rows
        )
        if any(value is None for value in allowed_values):
            raise ValueError("draft allowed value decoded as null")
        allowed = tuple(value for value in allowed_values if value is not None)
        result.append(
            PropertyDefinition(
                str(row["property_name"]),
                str(row["description"]),
                ValueKind(str(row["value_kind"])),
                bool(row["required"]),
                bool(row["nullable"]),
                allowed,
                bound_from_row(row, "minimum"),
                bound_from_row(row, "maximum"),
                _optional_int(row["minimum_length"]),
                _optional_int(row["maximum_length"]),
                None if row["pattern"] is None else str(row["pattern"]),
            )
        )
    return tuple(result)


def _delete_definition_children(connection, key):
    for relation in (
        "draft_definition_permitted_type",
        "draft_property_definition_allowed_value",
        "draft_property_definition_entry",
    ):
        connection.execute(f"DELETE FROM {relation} WHERE type_key = ?", (key,))


def _delete_object_children(connection, uuid):
    connection.execute("DELETE FROM draft_association_operation WHERE object_uuid = ?", (uuid,))
    connection.execute("DELETE FROM draft_property_operation WHERE object_uuid = ?", (uuid,))


def _permitted(definition):
    if isinstance(definition, AssociatedDataTypeDefinition):
        return tuple(("anchor", key) for key in definition.permitted_anchor_type_keys)
    if isinstance(definition, LinkTypeDefinition):
        return tuple(("source", key) for key in definition.permitted_source_type_keys) + tuple(
            ("target", key) for key in definition.permitted_target_type_keys
        )
    return ()


def _optional_int(value):
    return None if value is None else int(value)
