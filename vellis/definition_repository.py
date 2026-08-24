"""Connection-local VEL2 definition persistence and resolution."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict

from vellis.canonical_encoding import RowDescriptor
from vellis.domain import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    Cardinality,
    DefinitionKind,
    PropertyDefinition,
    ResolvedState,
    SystemEnvelope,
    TypeDefinition,
    ValueKind,
)
from vellis.domain_validation import scalar_identity
from vellis.sqlite_values import (
    bound_columns,
    bound_from_row,
    property_columns,
    property_from_row,
)
from vellis.state_repository import interval_parameters, interval_sql
from vellis.version_encoding import (
    allowed_value_encoding,
    definition_version_encoding,
    permitted_type_encoding,
    property_definition_encoding,
)


def insert_initial_definitions(
    connection: sqlite3.Connection, definitions: tuple[TypeDefinition, ...]
) -> tuple[RowDescriptor, ...]:
    return insert_definition_versions(connection, definitions, 0)


def insert_definition_version(
    connection: sqlite3.Connection, definition: TypeDefinition, revision: int
) -> tuple[RowDescriptor, ...]:
    """Insert one definition while a streaming initializer owns dependency order."""
    if _required_system(definition).last_changed_revision != revision:
        raise ValueError("definition lastChangedRevision must equal its introducing revision")
    _reserve_type_key(connection, definition, revision)
    return tuple(_insert_definition_version(connection, definition, revision))


def insert_definition_versions(
    connection: sqlite3.Connection,
    definitions: tuple[TypeDefinition, ...],
    revision: int,
) -> tuple[RowDescriptor, ...]:
    descriptors: list[RowDescriptor] = []
    for definition in definitions:
        if _required_system(definition).last_changed_revision != revision:
            raise ValueError("definition lastChangedRevision must equal its introducing revision")
    for definition in sorted(definitions, key=lambda value: value.type_key):
        _reserve_type_key(connection, definition, revision)
    for definition in sorted(definitions, key=lambda value: value.type_key):
        descriptors.extend(_insert_definition_version(connection, definition, revision))
    return tuple(descriptors)


def definition_descriptors(
    definitions: tuple[TypeDefinition, ...], revision: int
) -> tuple[RowDescriptor, ...]:
    descriptors: list[RowDescriptor] = []
    for definition in sorted(definitions, key=lambda value: value.type_key):
        system = _required_system(definition)
        identity, digest = definition_version_encoding(definition, revision, system)
        descriptors.append(RowDescriptor("definition_version", identity, digest))
        for role, permitted_key in _permitted_members(definition):
            identity, digest = permitted_type_encoding(
                definition.type_key, role, permitted_key, revision
            )
            descriptors.append(RowDescriptor("definition_permitted_type", identity, digest))
        if isinstance(definition, AssociatedDataTypeDefinition):
            descriptors.extend(_property_descriptors(definition, revision))
    return tuple(descriptors)


def load_definitions(
    connection: sqlite3.Connection,
    state: ResolvedState,
    type_keys: tuple[str, ...] | None = None,
) -> tuple[TypeDefinition, ...]:
    parameters = interval_parameters(state)
    key_sql, key_parameters = _key_filter("v.type_key", type_keys)
    rows = connection.execute(
        f"""
        SELECT v.*, i.created_revision, i.legacy_v1
        FROM definition_version AS v
        JOIN type_key_identity AS i USING (type_key)
        WHERE {interval_sql("v")}{key_sql}
        ORDER BY v.type_key
        """,
        (*parameters, *key_parameters),
    ).fetchall()
    loaded_keys = tuple(str(row["type_key"]) for row in rows)
    permitted = _load_permitted(connection, state, loaded_keys)
    properties = _load_properties(connection, state, loaded_keys)
    return tuple(_definition_from_row(row, permitted, properties) for row in rows)


def close_definition_versions(
    connection: sqlite3.Connection, type_keys: tuple[str, ...], revision: int
) -> tuple[RowDescriptor, ...]:
    """Close cohesive current definitions and return their retirement descriptors."""
    if not type_keys:
        return ()
    encoded = json.dumps(type_keys, ensure_ascii=False, separators=(",", ":"))
    descriptors = _current_definition_descriptors(connection, encoded)
    for relation in (
        "definition_permitted_type",
        "property_definition_allowed_value",
        "property_definition_version",
        "definition_version",
    ):
        connection.execute(
            f"""
            UPDATE {relation} SET valid_to_revision = ?
            WHERE valid_to_revision IS NULL
              AND type_key IN (SELECT value FROM json_each(?))
            """,
            (revision, encoded),
        )
    return descriptors


def _insert_definition_version(
    connection: sqlite3.Connection, definition: TypeDefinition, revision: int
) -> list[RowDescriptor]:
    system = _required_system(definition)
    identity, digest = definition_version_encoding(definition, revision, system)
    bounds = _bounds(definition)
    connection.execute(
        """
        INSERT INTO definition_version(
            type_key, valid_from_revision, kind, description,
            anchors_per_object_minimum, anchors_per_object_maximum,
            objects_per_anchor_minimum, objects_per_anchor_maximum,
            links_per_source_minimum, links_per_source_maximum,
            links_per_target_minimum, links_per_target_maximum,
            last_changed_revision, row_digest
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            definition.type_key,
            revision,
            definition.kind.value,
            definition.description,
            *bounds,
            system.last_changed_revision,
            digest,
        ),
    )
    descriptors = [RowDescriptor("definition_version", identity, digest)]
    descriptors.extend(_insert_permitted(connection, definition, revision))
    descriptors.extend(_insert_properties(connection, definition, revision))
    return descriptors


def _insert_permitted(
    connection: sqlite3.Connection, definition: TypeDefinition, revision: int
) -> list[RowDescriptor]:
    values = _permitted_members(definition)
    descriptors: list[RowDescriptor] = []
    for role, permitted_key in values:
        identity, digest = permitted_type_encoding(
            definition.type_key, role, permitted_key, revision
        )
        connection.execute(
            """
            INSERT INTO definition_permitted_type(
                type_key, role, permitted_type_key, valid_from_revision, row_digest
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (definition.type_key, role, permitted_key, revision, digest),
        )
        descriptors.append(RowDescriptor("definition_permitted_type", identity, digest))
    return descriptors


def _insert_properties(
    connection: sqlite3.Connection, definition: TypeDefinition, revision: int
) -> list[RowDescriptor]:
    if not isinstance(definition, AssociatedDataTypeDefinition):
        return []
    descriptors: list[RowDescriptor] = []
    for prop in sorted(definition.properties, key=lambda value: value.name):
        identity, digest = property_definition_encoding(definition.type_key, prop, revision)
        columns = {
            **bound_columns(prop.minimum, "minimum"),
            **bound_columns(prop.maximum, "maximum"),
        }
        connection.execute(
            """
            INSERT INTO property_definition_version(
                type_key, property_name, valid_from_revision, description, value_kind,
                required, nullable, minimum_kind, minimum_integer, minimum_number,
                minimum_date, minimum_timestamp_epoch_seconds, minimum_timestamp_nanosecond,
                minimum_timestamp_text, maximum_kind, maximum_integer, maximum_number,
                maximum_date, maximum_timestamp_epoch_seconds, maximum_timestamp_nanosecond,
                maximum_timestamp_text, minimum_length, maximum_length, pattern, row_digest
            ) VALUES (
                :type_key, :property_name, :revision, :description, :value_kind,
                :required, :nullable, :minimum_kind, :minimum_integer, :minimum_number,
                :minimum_date, :minimum_timestamp_epoch_seconds, :minimum_timestamp_nanosecond,
                :minimum_timestamp_text, :maximum_kind, :maximum_integer, :maximum_number,
                :maximum_date, :maximum_timestamp_epoch_seconds, :maximum_timestamp_nanosecond,
                :maximum_timestamp_text, :minimum_length, :maximum_length, :pattern, :row_digest
            )
            """,
            {
                **columns,
                "type_key": definition.type_key,
                "property_name": prop.name,
                "revision": revision,
                "description": prop.description,
                "value_kind": prop.value_kind.value,
                "required": int(prop.required),
                "nullable": int(prop.nullable),
                "minimum_length": _natural_text(prop.minimum_length),
                "maximum_length": _natural_text(prop.maximum_length),
                "pattern": prop.pattern,
                "row_digest": digest,
            },
        )
        descriptors.append(RowDescriptor("property_definition_version", identity, digest))
        descriptors.extend(_insert_allowed_values(connection, definition.type_key, prop, revision))
    return descriptors


def _property_descriptors(
    definition: AssociatedDataTypeDefinition, revision: int
) -> list[RowDescriptor]:
    descriptors: list[RowDescriptor] = []
    for prop in sorted(definition.properties, key=lambda value: value.name):
        identity, digest = property_definition_encoding(definition.type_key, prop, revision)
        descriptors.append(RowDescriptor("property_definition_version", identity, digest))
        for ordinal, value in enumerate(sorted(prop.allowed_values, key=scalar_identity)):
            identity, digest = allowed_value_encoding(
                definition.type_key, prop.name, ordinal, value, revision
            )
            descriptors.append(RowDescriptor("property_definition_allowed_value", identity, digest))
    return descriptors


def _insert_allowed_values(
    connection: sqlite3.Connection,
    type_key: str,
    prop: PropertyDefinition,
    revision: int,
) -> list[RowDescriptor]:
    descriptors: list[RowDescriptor] = []
    values = sorted(prop.allowed_values, key=scalar_identity)
    for ordinal, value in enumerate(values):
        identity, digest = allowed_value_encoding(type_key, prop.name, ordinal, value, revision)
        columns = property_columns(value, value.kind)
        connection.execute(
            """
            INSERT INTO property_definition_allowed_value(
                type_key, property_name, ordinal, valid_from_revision,
                value_kind, boolean_value, integer_value, number_value, text_value,
                date_value, timestamp_epoch_seconds, timestamp_nanosecond, timestamp_text,
                row_digest
            ) VALUES (
                :type_key, :property_name, :ordinal, :revision, :value_kind,
                :boolean_value, :integer_value, :number_value, :text_value,
                :date_value, :timestamp_epoch_seconds, :timestamp_nanosecond,
                :timestamp_text, :row_digest
            )
            """,
            {
                **columns,
                "type_key": type_key,
                "property_name": prop.name,
                "ordinal": ordinal,
                "revision": revision,
                "row_digest": digest,
            },
        )
        descriptors.append(RowDescriptor("property_definition_allowed_value", identity, digest))
    return descriptors


def _load_permitted(
    connection: sqlite3.Connection, state: ResolvedState, type_keys: tuple[str, ...]
) -> dict[str, dict[str, tuple[str, ...]]]:
    key_sql, key_parameters = _key_filter("p.type_key", type_keys)
    rows = connection.execute(
        f"""
        SELECT type_key, role, permitted_type_key
        FROM definition_permitted_type AS p
        WHERE {interval_sql("p")}{key_sql}
        ORDER BY type_key, role, permitted_type_key
        """,
        (*interval_parameters(state), *key_parameters),
    ).fetchall()
    collected: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        collected[str(row["type_key"])][str(row["role"])].append(str(row["permitted_type_key"]))
    return {
        type_key: {role: tuple(values) for role, values in roles.items()}
        for type_key, roles in collected.items()
    }


def _load_properties(
    connection: sqlite3.Connection, state: ResolvedState, type_keys: tuple[str, ...]
) -> dict[str, tuple[PropertyDefinition, ...]]:
    parameters = interval_parameters(state)
    key_sql, key_parameters = _key_filter("p.type_key", type_keys)
    rows = connection.execute(
        f"""
        SELECT *
        FROM property_definition_version AS p
        WHERE {interval_sql("p")}{key_sql}
        ORDER BY type_key, property_name
        """,
        (*parameters, *key_parameters),
    ).fetchall()
    allowed = _load_allowed(connection, state, type_keys)
    collected: dict[str, list[PropertyDefinition]] = defaultdict(list)
    for row in rows:
        key = (str(row["type_key"]), str(row["property_name"]))
        collected[key[0]].append(_property_from_row(row, allowed.get(key, ())))
    return {type_key: tuple(values) for type_key, values in collected.items()}


def _load_allowed(
    connection: sqlite3.Connection, state: ResolvedState, type_keys: tuple[str, ...]
) -> dict[tuple[str, str], tuple]:
    key_sql, key_parameters = _key_filter("a.type_key", type_keys)
    rows = connection.execute(
        f"""
        SELECT *
        FROM property_definition_allowed_value AS a
        WHERE {interval_sql("a")}{key_sql}
        ORDER BY type_key, property_name, ordinal
        """,
        (*interval_parameters(state), *key_parameters),
    ).fetchall()
    collected: dict[tuple[str, str], list] = defaultdict(list)
    for row in rows:
        key = (str(row["type_key"]), str(row["property_name"]))
        value = property_from_row({**dict(row), "is_null": 0})
        assert value is not None
        collected[key].append(value)
    return {key: tuple(values) for key, values in collected.items()}


def _key_filter(column: str, type_keys: tuple[str, ...] | None) -> tuple[str, tuple[object, ...]]:
    if type_keys is None:
        return "", ()
    if not type_keys:
        return " AND 0", ()
    encoded = json.dumps(type_keys, ensure_ascii=False, separators=(",", ":"))
    return f" AND {column} IN (SELECT value FROM json_each(?))", (encoded,)


def _definition_from_row(
    row: sqlite3.Row,
    permitted: dict[str, dict[str, tuple[str, ...]]],
    properties: dict[str, tuple[PropertyDefinition, ...]],
) -> TypeDefinition:
    type_key = str(row["type_key"])
    system = SystemEnvelope(
        int(row["created_revision"]),
        int(row["last_changed_revision"]),
        None if row["legacy_v1"] is None else str(row["legacy_v1"]),
    )
    kind = DefinitionKind(str(row["kind"]))
    if kind is DefinitionKind.ANCHOR:
        return AnchorTypeDefinition(type_key, str(row["description"]), system)
    members = permitted.get(type_key, {})
    if kind is DefinitionKind.ASSOCIATED_DATA:
        return AssociatedDataTypeDefinition(
            type_key,
            str(row["description"]),
            members.get("anchor", ()),
            properties.get(type_key, ()),
            Cardinality(
                int(row["anchors_per_object_minimum"]),
                _optional_int(row["anchors_per_object_maximum"]),
            ),
            Cardinality(
                int(row["objects_per_anchor_minimum"]),
                _optional_int(row["objects_per_anchor_maximum"]),
            ),
            system,
        )
    from vellis.domain import LinkTypeDefinition

    return LinkTypeDefinition(
        type_key,
        str(row["description"]),
        members.get("source", ()),
        members.get("target", ()),
        Cardinality(
            int(row["links_per_source_minimum"]),
            _optional_int(row["links_per_source_maximum"]),
        ),
        Cardinality(
            int(row["links_per_target_minimum"]),
            _optional_int(row["links_per_target_maximum"]),
        ),
        system,
    )


def _property_from_row(row: sqlite3.Row, allowed_values: tuple) -> PropertyDefinition:
    minimum = bound_from_row(row, "minimum")
    maximum = bound_from_row(row, "maximum")
    return PropertyDefinition(
        str(row["property_name"]),
        str(row["description"]),
        ValueKind(str(row["value_kind"])),
        bool(row["required"]),
        bool(row["nullable"]),
        allowed_values,
        minimum,
        maximum,
        _optional_int(row["minimum_length"]),
        _optional_int(row["maximum_length"]),
        None if row["pattern"] is None else str(row["pattern"]),
    )


def _permitted_members(definition: TypeDefinition) -> tuple[tuple[str, str], ...]:
    if isinstance(definition, AssociatedDataTypeDefinition):
        return tuple(("anchor", value) for value in sorted(definition.permitted_anchor_type_keys))
    from vellis.domain import LinkTypeDefinition

    if isinstance(definition, LinkTypeDefinition):
        source = (("source", value) for value in definition.permitted_source_type_keys)
        target = (("target", value) for value in definition.permitted_target_type_keys)
        return tuple(sorted((*source, *target)))
    return ()


def _bounds(definition: TypeDefinition) -> tuple[str | None, ...]:
    if isinstance(definition, AssociatedDataTypeDefinition):
        return (
            _natural_text(definition.anchors_per_object.minimum),
            _natural_text(definition.anchors_per_object.maximum),
            _natural_text(definition.objects_per_anchor.minimum),
            _natural_text(definition.objects_per_anchor.maximum),
            None,
            None,
            None,
            None,
        )
    from vellis.domain import LinkTypeDefinition

    if isinstance(definition, LinkTypeDefinition):
        return (
            None,
            None,
            None,
            None,
            _natural_text(definition.links_per_source.minimum),
            _natural_text(definition.links_per_source.maximum),
            _natural_text(definition.links_per_target.minimum),
            _natural_text(definition.links_per_target.maximum),
        )
    return (None,) * 8


def _required_system(definition: TypeDefinition) -> SystemEnvelope:
    if definition.system is None:
        raise ValueError(f"definition {definition.type_key} has no canonical system envelope")
    return definition.system


def _reserve_type_key(
    connection: sqlite3.Connection, definition: TypeDefinition, revision: int
) -> None:
    system = _required_system(definition)
    row = connection.execute(
        """
        SELECT kind, created_revision, legacy_v1
        FROM type_key_identity WHERE type_key = ?
        """,
        (definition.type_key,),
    ).fetchone()
    if row is not None:
        if str(row["kind"]) != definition.kind.value:
            raise ValueError(f"type key {definition.type_key} is reserved to another kind")
        stored_legacy = None if row["legacy_v1"] is None else str(row["legacy_v1"])
        if (
            int(row["created_revision"]) != system.created_revision
            or stored_legacy != system.legacy_v1
        ):
            raise ValueError(f"type key {definition.type_key} changed reserved system metadata")
        return
    if system.created_revision != revision:
        raise ValueError("a newly reserved type key must be created in the introducing revision")
    connection.execute(
        """
        INSERT INTO type_key_identity(type_key, kind, created_revision, legacy_v1)
        VALUES (?, ?, ?, ?)
        """,
        (
            definition.type_key,
            definition.kind.value,
            system.created_revision,
            system.legacy_v1,
        ),
    )


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _canonical_natural_text(value):
        raise ValueError("stored cardinality representation is invalid")
    return int(value)


def _natural_text(value: int | None) -> str | None:
    return None if value is None else str(value)


def _canonical_natural_text(value: str) -> bool:
    return value == "0" or (value.isascii() and value.isdigit() and not value.startswith("0"))


def _current_definition_descriptors(
    connection: sqlite3.Connection, encoded: str
) -> tuple[RowDescriptor, ...]:
    from vellis.canonical_encoding import Record

    specs = (
        ("definition_version", ("type_key",)),
        ("definition_permitted_type", ("type_key", "role", "permitted_type_key")),
        ("property_definition_version", ("type_key", "property_name")),
        ("property_definition_allowed_value", ("type_key", "property_name", "ordinal")),
    )
    descriptors: list[RowDescriptor] = []
    for relation, keys in specs:
        rows = connection.execute(
            f"""SELECT * FROM {relation} WHERE valid_to_revision IS NULL
                AND type_key IN (SELECT value FROM json_each(?))""",
            (encoded,),
        ).fetchall()
        for row in rows:
            fields = tuple((_camel(key), row[key]) for key in keys)
            identity = Record((*fields, ("validFromRevision", int(row["valid_from_revision"]))))
            descriptors.append(RowDescriptor(relation, identity, bytes(row["row_digest"])))
    return tuple(descriptors)


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.title() for part in tail)
