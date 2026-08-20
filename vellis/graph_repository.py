"""Connection-local VEL2 graph version persistence and resolution."""

from __future__ import annotations

import sqlite3
from collections import defaultdict

from vellis.canonical_encoding import RowDescriptor
from vellis.domain import (
    Anchor,
    AssociatedData,
    AssociatedDataTypeDefinition,
    GraphObject,
    Link,
    ObjectKind,
    ResolvedState,
    ScalarValue,
    SystemEnvelope,
    TypeDefinition,
)
from vellis.sqlite_values import property_columns, property_from_row
from vellis.state_repository import interval_parameters, interval_sql
from vellis.version_encoding import (
    association_version_encoding,
    graph_object_version_encoding,
    property_version_encoding,
)


def insert_graph_versions(
    connection: sqlite3.Connection,
    objects: tuple[GraphObject, ...],
    definitions: tuple[TypeDefinition, ...],
    revision: int,
) -> tuple[RowDescriptor, ...]:
    for value in objects:
        if _required_system(value).last_changed_revision != revision:
            raise ValueError("object lastChangedRevision must equal its introducing revision")
    for value in sorted(objects, key=lambda item: item.uuid):
        _reserve_identity(connection, value, revision)
    descriptors: list[RowDescriptor] = []
    definition_map = {definition.type_key: definition for definition in definitions}
    for value in sorted(objects, key=lambda item: item.uuid):
        descriptors.extend(_insert_object(connection, value, definition_map, revision))
    return tuple(descriptors)


def graph_descriptors(
    objects: tuple[GraphObject, ...],
    definitions: tuple[TypeDefinition, ...],
    revision: int,
) -> tuple[RowDescriptor, ...]:
    rules_by_type = {
        definition.type_key: {rule.name: rule for rule in definition.properties}
        for definition in definitions
        if isinstance(definition, AssociatedDataTypeDefinition)
    }
    descriptors: list[RowDescriptor] = []
    for value in sorted(objects, key=lambda item: item.uuid):
        system = _required_system(value)
        identity, digest = graph_object_version_encoding(value, revision, system)
        descriptors.append(RowDescriptor("graph_object_version", identity, digest))
        if isinstance(value, AssociatedData):
            for anchor_uuid in sorted(value.anchor_uuids):
                identity, digest = association_version_encoding(value.uuid, anchor_uuid, revision)
                descriptors.append(RowDescriptor("direct_association_version", identity, digest))
            for name, content in sorted(value.properties):
                rule = rules_by_type[value.type_key][name]
                identity, digest = property_version_encoding(
                    value.uuid, name, content, rule.value_kind.value, revision
                )
                descriptors.append(RowDescriptor("property_version", identity, digest))
    return tuple(descriptors)


def load_graph(connection: sqlite3.Connection, state: ResolvedState) -> tuple[GraphObject, ...]:
    parameters = interval_parameters(state)
    rows = connection.execute(
        f"""
        SELECT v.*, i.created_revision, i.legacy_v1
        FROM graph_object_version AS v
        JOIN graph_object_identity AS i USING (uuid)
        WHERE {interval_sql("v")}
        ORDER BY v.uuid
        """,
        parameters,
    ).fetchall()
    associations = _load_associations(connection, state)
    properties = _load_properties(connection, state)
    return tuple(_object_from_row(row, associations, properties) for row in rows)


def _reserve_identity(connection: sqlite3.Connection, value: GraphObject, revision: int) -> None:
    system = _required_system(value)
    row = connection.execute(
        """
        SELECT kind, created_revision, legacy_v1
        FROM graph_object_identity WHERE uuid = ?
        """,
        (value.uuid,),
    ).fetchone()
    if row is not None:
        if str(row["kind"]) != value.kind.value:
            raise ValueError(f"UUID {value.uuid} is reserved to another object kind")
        stored_legacy = None if row["legacy_v1"] is None else str(row["legacy_v1"])
        if (
            int(row["created_revision"]) != system.created_revision
            or stored_legacy != system.legacy_v1
        ):
            raise ValueError(f"UUID {value.uuid} changed reserved system metadata")
        return
    connection.execute(
        """
        INSERT INTO graph_object_identity(uuid, kind, created_revision, legacy_v1)
        VALUES (?, ?, ?, ?)
        """,
        (value.uuid, value.kind.value, system.created_revision, system.legacy_v1),
    )
    if system.created_revision != revision:
        raise ValueError("a newly reserved UUID must be created in the introducing revision")


def _insert_object(
    connection: sqlite3.Connection,
    value: GraphObject,
    definitions: dict[str, TypeDefinition],
    revision: int,
) -> list[RowDescriptor]:
    system = _required_system(value)
    identity, digest = graph_object_version_encoding(value, revision, system)
    display_name = value.display_name if isinstance(value, Anchor) else None
    source_uuid = value.source_uuid if isinstance(value, Link) else None
    target_uuid = value.target_uuid if isinstance(value, Link) else None
    connection.execute(
        """
        INSERT INTO graph_object_version(
            uuid, valid_from_revision, kind, type_key, display_name,
            source_uuid, target_uuid, last_changed_revision, row_digest
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            value.uuid,
            revision,
            value.kind.value,
            value.type_key,
            display_name,
            source_uuid,
            target_uuid,
            system.last_changed_revision,
            digest,
        ),
    )
    descriptors = [RowDescriptor("graph_object_version", identity, digest)]
    if isinstance(value, AssociatedData):
        descriptors.extend(_insert_associations(connection, value, revision))
        descriptors.extend(_insert_properties(connection, value, definitions, revision))
    return descriptors


def _insert_associations(
    connection: sqlite3.Connection, value: AssociatedData, revision: int
) -> list[RowDescriptor]:
    descriptors: list[RowDescriptor] = []
    for anchor_uuid in sorted(value.anchor_uuids):
        identity, digest = association_version_encoding(value.uuid, anchor_uuid, revision)
        connection.execute(
            """
            INSERT INTO direct_association_version(
                object_uuid, anchor_uuid, valid_from_revision, row_digest
            ) VALUES (?, ?, ?, ?)
            """,
            (value.uuid, anchor_uuid, revision, digest),
        )
        descriptors.append(RowDescriptor("direct_association_version", identity, digest))
    return descriptors


def _insert_properties(
    connection: sqlite3.Connection,
    value: AssociatedData,
    definitions: dict[str, TypeDefinition],
    revision: int,
) -> list[RowDescriptor]:
    definition = definitions.get(value.type_key)
    if not isinstance(definition, AssociatedDataTypeDefinition):
        raise ValueError(f"associated-data type {value.type_key} is absent")
    rules = {rule.name: rule for rule in definition.properties}
    descriptors: list[RowDescriptor] = []
    for name, content in sorted(value.properties):
        rule = rules.get(name)
        if rule is None:
            raise ValueError(f"property {name} is not declared by {value.type_key}")
        identity, digest = property_version_encoding(
            value.uuid, name, content, rule.value_kind.value, revision
        )
        columns = property_columns(content, rule.value_kind)
        connection.execute(
            """
            INSERT INTO property_version(
                object_uuid, property_name, valid_from_revision, value_kind, is_null,
                boolean_value, integer_value, number_value, text_value, date_value,
                timestamp_epoch_seconds, timestamp_nanosecond, timestamp_text, row_digest
            ) VALUES (
                :object_uuid, :property_name, :revision, :value_kind, :is_null,
                :boolean_value, :integer_value, :number_value, :text_value, :date_value,
                :timestamp_epoch_seconds, :timestamp_nanosecond, :timestamp_text, :row_digest
            )
            """,
            {
                **columns,
                "object_uuid": value.uuid,
                "property_name": name,
                "revision": revision,
                "row_digest": digest,
            },
        )
        descriptors.append(RowDescriptor("property_version", identity, digest))
    return descriptors


def _load_associations(
    connection: sqlite3.Connection, state: ResolvedState
) -> dict[str, tuple[str, ...]]:
    rows = connection.execute(
        f"""
        SELECT object_uuid, anchor_uuid
        FROM direct_association_version AS a
        WHERE {interval_sql("a")}
        ORDER BY object_uuid, anchor_uuid
        """,
        interval_parameters(state),
    ).fetchall()
    values: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        values[str(row["object_uuid"])].append(str(row["anchor_uuid"]))
    return {uuid: tuple(anchors) for uuid, anchors in values.items()}


def _load_properties(
    connection: sqlite3.Connection, state: ResolvedState
) -> dict[str, tuple[tuple[str, ScalarValue | None], ...]]:
    rows = connection.execute(
        f"""
        SELECT *
        FROM property_version AS p
        WHERE {interval_sql("p")}
        ORDER BY object_uuid, property_name
        """,
        interval_parameters(state),
    ).fetchall()
    values: dict[str, list[tuple[str, ScalarValue | None]]] = defaultdict(list)
    for row in rows:
        values[str(row["object_uuid"])].append((str(row["property_name"]), property_from_row(row)))
    return {uuid: tuple(properties) for uuid, properties in values.items()}


def _object_from_row(
    row: sqlite3.Row,
    associations: dict[str, tuple[str, ...]],
    properties: dict[str, tuple[tuple[str, ScalarValue | None], ...]],
) -> GraphObject:
    uuid = str(row["uuid"])
    system = SystemEnvelope(
        int(row["created_revision"]),
        int(row["last_changed_revision"]),
        None if row["legacy_v1"] is None else str(row["legacy_v1"]),
    )
    kind = ObjectKind(str(row["kind"]))
    if kind is ObjectKind.ANCHOR:
        return Anchor(uuid, str(row["type_key"]), str(row["display_name"]), system)
    if kind is ObjectKind.ASSOCIATED_DATA:
        return AssociatedData(
            uuid,
            str(row["type_key"]),
            associations.get(uuid, ()),
            properties.get(uuid, ()),
            system,
        )
    return Link(
        uuid,
        str(row["type_key"]),
        str(row["source_uuid"]),
        str(row["target_uuid"]),
        system,
    )


def _required_system(value: GraphObject) -> SystemEnvelope:
    if value.system is None:
        raise ValueError(f"graph object {value.uuid} has no canonical system envelope")
    return value.system
