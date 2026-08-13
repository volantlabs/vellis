"""Normalized SQLite encoding for Vellis canonical values.

This module is a physical realization, not RTG authority.  It deliberately stores
addressable scalar fields and child occurrences instead of serialized graph objects or
definition-set documents.  Nested JSON arrays and objects remain one property value;
the public language has no path-level meaning to normalize further.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from enum import Enum
from sqlite3 import Connection

from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    DirectAssociationEnd,
    DirectAssociationMultiplicityConstraint,
    EndpointConstraint,
    GraphDefinitionSet,
    LinkEnd,
    LinkMultiplicityConstraint,
    LinkTypeDefinition,
    PropertyConstraint,
    StringPattern,
    ValueRange,
    ValueShape,
    relationship_identity,
)
from vellis.graph import Anchor, AssociatedDataObject, GraphObject, Link, ObjectKind, SystemMetadata
from vellis.json_value import JsonKind, JsonValue, dumps, json_kind, loads

__all__ = [
    "definition_content_stats",
    "definition_entry_digest",
    "definition_identity",
    "definition_identity_from_stats",
    "insert_definition_set",
    "insert_object_value",
    "json_storage_fields",
    "json_storage_value",
    "load_definition_set",
    "load_object_value",
    "object_identity",
    "semantic_identity",
]


def _canonical_decimal(value: Decimal) -> str:
    """Return a context-free exact spelling, collapsing only equal decimal values."""
    if value.is_zero():
        return "0"
    sign, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):
        raise ValueError("a non-finite decimal has no canonical JSON-number identity")
    significant = list(digits)
    while significant[-1] == 0:
        significant.pop()
        exponent += 1
    coefficient = "".join(str(digit) for digit in significant)
    return f"{'-' if sign else ''}{coefficient}e{exponent}"


def semantic_identity(value: object) -> str:
    """Hash a typed, recursively framed semantic value without ambiguous flattening."""
    digest = hashlib.sha256()

    def add(each: object) -> None:
        if each is None:
            digest.update(b"N")
            return
        if isinstance(each, bool):
            digest.update(b"B1" if each else b"B0")
            return
        if isinstance(each, Decimal):
            canonical = _canonical_decimal(each)
            encoded = canonical.encode("ascii")
            digest.update(b"M" + len(encoded).to_bytes(8, "big") + encoded)
            return
        if isinstance(each, Enum):
            add(each.value)
            return
        if isinstance(each, (tuple, list)):
            digest.update(b"L" + len(each).to_bytes(8, "big"))
            for member in each:
                add(member)
            return
        if isinstance(each, (set, frozenset)):
            members = sorted(each, key=semantic_identity)
            digest.update(b"U" + len(members).to_bytes(8, "big"))
            for member in members:
                add(member)
            return
        if isinstance(each, dict):
            members = sorted(each.items())
            digest.update(b"D" + len(members).to_bytes(8, "big"))
            for key, member in members:
                add(key)
                add(member)
            return
        if isinstance(each, int):
            encoded = str(each).encode("ascii")
            digest.update(b"I" + len(encoded).to_bytes(8, "big") + encoded)
            return
        if not isinstance(each, str):
            raise TypeError(f"unsupported semantic identity value: {type(each).__name__}")
        encoded = each.encode("utf-8")
        digest.update(b"S" + len(encoded).to_bytes(8, "big") + encoded)

    add(value)
    return digest.hexdigest()


def json_storage_fields(value: JsonValue) -> tuple[str, int | None, str | None, str | None]:
    kind = json_kind(value)
    if kind is JsonKind.NULL:
        return kind.value, None, None, None
    if kind is JsonKind.BOOLEAN:
        assert isinstance(value, bool)
        return kind.value, int(value), None, None
    if kind is JsonKind.NUMBER:
        assert isinstance(value, Decimal)
        return kind.value, None, _canonical_decimal(value), None
    if kind is JsonKind.STRING:
        assert isinstance(value, str)
        return kind.value, None, None, value
    return kind.value, None, None, dumps(value)


def json_storage_value(kind: object, boolean: object, number: object, text: object) -> JsonValue:
    parsed = JsonKind(str(kind))
    if parsed is JsonKind.NULL:
        return None
    if parsed is JsonKind.BOOLEAN:
        return bool(boolean)
    if parsed is JsonKind.NUMBER:
        return Decimal(str(number))
    if parsed is JsonKind.STRING:
        return str(text)
    return loads(str(text))


def object_identity(value: GraphObject) -> str:
    common = (
        value.uuid,
        value.type_key,
        tuple(sorted(value.system_metadata.members.items())),
    )
    if isinstance(value, Anchor):
        meaning: object = (ObjectKind.ANCHOR.value, common, value.display_name)
    elif isinstance(value, AssociatedDataObject):
        meaning = (
            ObjectKind.ASSOCIATED_DATA.value,
            common,
            tuple(sorted(value.anchor_uuids)),
            tuple(sorted(value.properties.items())),
        )
    else:
        meaning = (ObjectKind.LINK.value, common, value.source_uuid, value.target_uuid)
    return semantic_identity(meaning)


def insert_object_value(connection: Connection, value: GraphObject) -> int:
    identity = object_identity(value)
    existing = connection.execute(
        "SELECT id FROM object_value WHERE content_identity = ?", (identity,)
    ).fetchone()
    if existing is not None:
        return int(existing[0])
    if isinstance(value, Anchor):
        kind = ObjectKind.ANCHOR.value
        display_name, source_uuid, target_uuid = value.display_name, None, None
    elif isinstance(value, AssociatedDataObject):
        kind = ObjectKind.ASSOCIATED_DATA.value
        display_name = source_uuid = target_uuid = None
    else:
        kind = ObjectKind.LINK.value
        display_name = None
        source_uuid, target_uuid = value.source_uuid, value.target_uuid
    cursor = connection.execute(
        "INSERT INTO object_value"
        " (content_identity, uuid, object_kind, type_key, display_name, source_uuid, target_uuid)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (identity, value.uuid, kind, value.type_key, display_name, source_uuid, target_uuid),
    )
    assert cursor.lastrowid is not None
    value_id = int(cursor.lastrowid)
    for ordinal, (name, member) in enumerate(sorted(value.system_metadata.members.items())):
        connection.execute(
            "INSERT INTO object_metadata"
            " (object_value_id, ordinal, name, json_kind, boolean_value, number_value, text_value)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (value_id, ordinal, name, *json_storage_fields(member)),
        )
    if isinstance(value, AssociatedDataObject):
        for ordinal, anchor_uuid in enumerate(value.anchor_uuids):
            connection.execute(
                "INSERT INTO object_anchor"
                " (object_value_id, ordinal, anchor_uuid) VALUES (?, ?, ?)",
                (value_id, ordinal, anchor_uuid),
            )
        for ordinal, (name, member) in enumerate(sorted(value.properties.items())):
            connection.execute(
                "INSERT INTO object_property"
                " (object_value_id, ordinal, name, json_kind, boolean_value,"
                " number_value, text_value)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (value_id, ordinal, name, *json_storage_fields(member)),
            )
    return value_id


def load_object_value(connection: Connection, value_id: int) -> GraphObject:
    row = connection.execute(
        "SELECT uuid, object_kind, type_key, display_name, source_uuid, target_uuid"
        " FROM object_value WHERE id = ?",
        (value_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown object value {value_id}")
    metadata = {
        str(name): json_storage_value(kind, boolean, number, text)
        for name, kind, boolean, number, text in connection.execute(
            "SELECT name, json_kind, boolean_value, number_value, text_value"
            " FROM object_metadata WHERE object_value_id = ? ORDER BY ordinal",
            (value_id,),
        )
    }
    system_metadata = SystemMetadata(metadata)
    uuid, kind, type_key, display_name, source_uuid, target_uuid = row
    if kind == ObjectKind.ANCHOR.value:
        return Anchor(str(uuid), str(type_key), str(display_name), system_metadata)
    if kind == ObjectKind.ASSOCIATED_DATA.value:
        anchors = tuple(
            str(each[0])
            for each in connection.execute(
                "SELECT anchor_uuid FROM object_anchor WHERE object_value_id = ? ORDER BY ordinal",
                (value_id,),
            )
        )
        properties = {
            str(name): json_storage_value(value_kind, boolean, number, text)
            for name, value_kind, boolean, number, text in connection.execute(
                "SELECT name, json_kind, boolean_value, number_value, text_value"
                " FROM object_property WHERE object_value_id = ? ORDER BY ordinal",
                (value_id,),
            )
        }
        return AssociatedDataObject(str(uuid), str(type_key), anchors, properties, system_metadata)
    return Link(str(uuid), str(type_key), str(source_uuid), str(target_uuid), system_metadata)


_IDENTITY_MODULUS = 1 << 256


def _definition_members(definitions: GraphDefinitionSet) -> tuple[object, ...]:
    """Return independently hashable members of unordered definition-set meaning."""

    def ordered(values: list[object]) -> tuple[object, ...]:
        return tuple(sorted(values, key=semantic_identity))

    anchors: list[object] = [
        ("anchor", value.type_key, value.description) for value in definitions.anchor_types
    ]
    data_types: list[object] = []
    for value in definitions.associated_data_types:
        rules: list[object] = []
        for rule in value.property_constraints:
            shape = (
                None
                if rule.value_shape is None
                else (rule.value_shape.minimum_size, rule.value_shape.maximum_size)
            )
            value_range = (
                None
                if rule.value_range is None
                else (
                    rule.value_range.lower_bound,
                    rule.value_range.upper_bound,
                    ordered(list(rule.value_range.permitted_values)),
                )
            )
            rules.append(
                (
                    rule.property_name,
                    rule.required,
                    rule.json_kind.value,
                    rule.description,
                    shape,
                    value_range,
                    None if rule.pattern is None else rule.pattern.expression,
                )
            )
        data_types.append(
            (
                "data",
                value.type_key,
                value.description,
                tuple(sorted(value.permitted_anchor_type_keys)),
                ordered(rules),
            )
        )
    links: list[object] = [
        (
            "link",
            value.type_key,
            value.description,
            value.endpoint_constraint.description,
            tuple(sorted(value.endpoint_constraint.permitted_source_type_keys)),
            tuple(sorted(value.endpoint_constraint.permitted_target_type_keys)),
        )
        for value in definitions.link_types
    ]
    relationships: list[object] = []
    for rule in definitions.relationship_constraints:
        if isinstance(rule, LinkMultiplicityConstraint):
            relationships.append(
                (
                    "linkMultiplicity",
                    rule.link_type_key,
                    rule.constrained_end.value,
                    tuple(sorted(rule.constrained_endpoint_type_keys)),
                    tuple(sorted(rule.opposite_endpoint_type_keys)),
                    rule.lower_bound,
                    rule.upper_bound,
                    rule.description,
                )
            )
        else:
            relationships.append(
                (
                    "directAssociationMultiplicity",
                    rule.constrained_end.value,
                    tuple(sorted(rule.anchor_type_keys)),
                    tuple(sorted(rule.associated_data_type_keys)),
                    rule.lower_bound,
                    rule.upper_bound,
                    rule.description,
                )
            )
    return (*anchors, *data_types, *links, *relationships)


def definition_content_stats(definitions: GraphDefinitionSet) -> tuple[str, int]:
    """Return a composable cryptographic multiset summary of definition meaning.

    Modular addition preserves duplicate occurrences and lets a sparse proposal replace
    one natural-keyed member without traversing the untouched definition population.
    Member digests include their definition kind and complete canonical semantic value.
    """

    members = _definition_members(definitions)
    accumulator = sum(int(semantic_identity(member), 16) for member in members)
    return f"{accumulator % _IDENTITY_MODULUS:064x}", len(members)


def definition_entry_digest(definitions: GraphDefinitionSet) -> str:
    """Return the semantic digest of one normalized definition member."""

    members = _definition_members(definitions)
    if len(members) != 1:
        raise ValueError("a definition entry digest requires exactly one member")
    return semantic_identity(members[0])


def definition_identity_from_stats(accumulator: str, entry_count: int) -> str:
    """Derive the canonical set identity from its composable content summary."""

    return semantic_identity(("definitionSet", entry_count, accumulator))


def definition_identity(definitions: GraphDefinitionSet) -> str:
    """Return a path-independent identity aligned with definition-set equality."""

    return definition_identity_from_stats(*definition_content_stats(definitions))


def insert_definition_set(connection: Connection, definitions: GraphDefinitionSet) -> str:
    accumulator, entry_count = definition_content_stats(definitions)
    identity = definition_identity_from_stats(accumulator, entry_count)
    if connection.execute(
        "SELECT 1 FROM definition_set WHERE identity = ?", (identity,)
    ).fetchone():
        return identity
    connection.execute(
        "INSERT INTO definition_set (identity, content_accumulator, entry_count) VALUES (?, ?, ?)",
        (identity, accumulator, entry_count),
    )
    occurrence = 0
    for kind, values in (
        (ObjectKind.ANCHOR.value, definitions.anchor_types),
        (ObjectKind.ASSOCIATED_DATA.value, definitions.associated_data_types),
        (ObjectKind.LINK.value, definitions.link_types),
    ):
        for value in values:
            connection.execute(
                "INSERT INTO definition_type"
                " (definition_set_id, occurrence, object_kind, type_key, description)"
                " VALUES (?, ?, ?, ?, ?)",
                (identity, occurrence, kind, value.type_key, value.description),
            )
            if isinstance(value, AssociatedDataTypeDefinition):
                for ordinal, anchor_type in enumerate(value.permitted_anchor_type_keys):
                    connection.execute(
                        "INSERT INTO definition_anchor_permission VALUES (?, ?, ?, ?)",
                        (identity, occurrence, ordinal, anchor_type),
                    )
                for ordinal, rule in enumerate(value.property_constraints):
                    shape = rule.value_shape
                    value_range = rule.value_range
                    connection.execute(
                        "INSERT INTO definition_property_rule"
                        " (definition_set_id, type_occurrence, occurrence, property_name, required,"
                        " json_kind, description, minimum_size, maximum_size, lower_kind,"
                        " lower_value, upper_kind, upper_value, pattern)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            identity,
                            occurrence,
                            ordinal,
                            rule.property_name,
                            int(rule.required),
                            rule.json_kind.value,
                            rule.description,
                            None if shape is None else shape.minimum_size,
                            None if shape is None else shape.maximum_size,
                            None
                            if value_range is None or value_range.lower_bound is None
                            else json_kind(value_range.lower_bound).value,
                            None
                            if value_range is None or value_range.lower_bound is None
                            else dumps(value_range.lower_bound),
                            None
                            if value_range is None or value_range.upper_bound is None
                            else json_kind(value_range.upper_bound).value,
                            None
                            if value_range is None or value_range.upper_bound is None
                            else dumps(value_range.upper_bound),
                            None if rule.pattern is None else rule.pattern.expression,
                        ),
                    )
                    if value_range is not None:
                        for permitted_ordinal, permitted in enumerate(value_range.permitted_values):
                            connection.execute(
                                "INSERT INTO definition_permitted_value VALUES (?, ?, ?, ?, ?, ?)",
                                (
                                    identity,
                                    occurrence,
                                    ordinal,
                                    permitted_ordinal,
                                    json_kind(permitted).value,
                                    dumps(permitted),
                                ),
                            )
            elif isinstance(value, LinkTypeDefinition):
                endpoint = value.endpoint_constraint
                connection.execute(
                    "INSERT INTO definition_endpoint_rule VALUES (?, ?, ?)",
                    (identity, occurrence, endpoint.description),
                )
                for role, type_keys in (
                    ("source", endpoint.permitted_source_type_keys),
                    ("target", endpoint.permitted_target_type_keys),
                ):
                    for ordinal, type_key in enumerate(type_keys):
                        connection.execute(
                            "INSERT INTO definition_endpoint_permission VALUES (?, ?, ?, ?, ?)",
                            (identity, occurrence, role, ordinal, type_key),
                        )
            occurrence += 1
    for occurrence, rule in enumerate(definitions.relationship_constraints):
        if isinstance(rule, LinkMultiplicityConstraint):
            kind = "linkMultiplicity"
            link_type_key = rule.link_type_key
            constrained_end = rule.constrained_end.value
            first, second = rule.constrained_endpoint_type_keys, rule.opposite_endpoint_type_keys
        else:
            kind = "directAssociationMultiplicity"
            link_type_key = None
            constrained_end = rule.constrained_end.value
            first, second = rule.anchor_type_keys, rule.associated_data_type_keys
        connection.execute(
            "INSERT INTO definition_multiplicity_rule"
            " (definition_set_id, occurrence, natural_key, rule_kind, link_type_key,"
            " constrained_end,"
            " lower_bound, upper_bound, description)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                identity,
                occurrence,
                semantic_identity(relationship_identity(rule)),
                kind,
                link_type_key,
                constrained_end,
                rule.lower_bound,
                rule.upper_bound,
                rule.description,
            ),
        )
        for role, members in (("first", first), ("second", second)):
            for ordinal, type_key in enumerate(members):
                connection.execute(
                    "INSERT INTO definition_multiplicity_participant VALUES (?, ?, ?, ?, ?)",
                    (identity, occurrence, role, ordinal, type_key),
                )
    return identity


def load_definition_set(
    connection: Connection,
    identity: str,
    *,
    type_keys: set[str] | None = None,
    constrained_type_keys: set[str] | None = None,
    relationship_keys: set[str] | None = None,
) -> GraphDefinitionSet:
    """Load complete or request-local definition meaning from normalized rows.

    ``None`` means the complete collection. An explicit set selects only matching
    natural identities. Relationship rules are selected independently by the type keys
    at their constrained participant end, which is the subset an affected-neighborhood
    mutation can make newly false.
    """
    if (
        connection.execute(
            "SELECT 1 FROM definition_set WHERE identity = ?", (identity,)
        ).fetchone()
        is None
    ):
        raise ValueError(f"unknown definition-set identity {identity!r}")
    anchors: list[AnchorTypeDefinition] = []
    data_types: list[AssociatedDataTypeDefinition] = []
    link_types: list[LinkTypeDefinition] = []
    type_sql = (
        "SELECT occurrence, object_kind, type_key, description FROM definition_type"
        " WHERE definition_set_id = ?"
    )
    type_parameters: list[object] = [identity]
    if type_keys is not None:
        if not type_keys:
            type_rows = ()
        else:
            placeholders = ", ".join("?" for _ in type_keys)
            type_sql += f" AND type_key IN ({placeholders})"
            type_parameters.extend(sorted(type_keys))
            type_rows = connection.execute(
                type_sql + " ORDER BY occurrence", tuple(type_parameters)
            )
    else:
        type_rows = connection.execute(type_sql + " ORDER BY occurrence", tuple(type_parameters))
    for occurrence, kind, type_key, description in type_rows:
        if kind == ObjectKind.ANCHOR.value:
            anchors.append(AnchorTypeDefinition(str(type_key), description))
        elif kind == ObjectKind.ASSOCIATED_DATA.value:
            permitted = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT anchor_type_key FROM definition_anchor_permission"
                    " WHERE definition_set_id = ? AND type_occurrence = ? ORDER BY occurrence",
                    (identity, occurrence),
                )
            )
            properties: list[PropertyConstraint] = []
            for row in connection.execute(
                "SELECT occurrence, property_name, required, json_kind, description,"
                " minimum_size, maximum_size,"
                " lower_kind, lower_value, upper_kind, upper_value, pattern"
                " FROM definition_property_rule WHERE definition_set_id = ?"
                " AND type_occurrence = ? ORDER BY occurrence",
                (identity, occurrence),
            ):
                (
                    rule_occurrence,
                    name,
                    required,
                    kind_name,
                    rule_description,
                    minimum,
                    maximum,
                    lower_kind,
                    lower,
                    upper_kind,
                    upper,
                    pattern,
                ) = row
                permitted_values = tuple(
                    loads(str(value))
                    for _, value in connection.execute(
                        "SELECT json_kind, json_value FROM definition_permitted_value"
                        " WHERE definition_set_id = ? AND type_occurrence = ?"
                        " AND property_occurrence = ? ORDER BY occurrence",
                        (identity, occurrence, rule_occurrence),
                    )
                )
                value_shape = (
                    None if minimum is None and maximum is None else ValueShape(minimum, maximum)
                )
                value_range = None
                if lower is not None or upper is not None or permitted_values:
                    value_range = ValueRange(
                        None if lower is None else loads(str(lower)),
                        None if upper is None else loads(str(upper)),
                        permitted_values,
                    )
                properties.append(
                    PropertyConstraint(
                        str(name),
                        bool(required),
                        JsonKind(str(kind_name)),
                        rule_description,
                        value_shape,
                        value_range,
                        None if pattern is None else StringPattern(str(pattern)),
                    )
                )
            data_types.append(
                AssociatedDataTypeDefinition(
                    str(type_key), permitted, tuple(properties), description
                )
            )
        else:
            endpoint_description_row = connection.execute(
                "SELECT description FROM definition_endpoint_rule"
                " WHERE definition_set_id = ? AND type_occurrence = ?",
                (identity, occurrence),
            ).fetchone()
            source = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT type_key FROM definition_endpoint_permission"
                    " WHERE definition_set_id = ?"
                    " AND type_occurrence = ? AND role = 'source' ORDER BY occurrence",
                    (identity, occurrence),
                )
            )
            target = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT type_key FROM definition_endpoint_permission"
                    " WHERE definition_set_id = ?"
                    " AND type_occurrence = ? AND role = 'target' ORDER BY occurrence",
                    (identity, occurrence),
                )
            )
            link_types.append(
                LinkTypeDefinition(
                    str(type_key),
                    EndpointConstraint(
                        source,
                        target,
                        None if endpoint_description_row is None else endpoint_description_row[0],
                    ),
                    description,
                )
            )
    relationships = []
    relationship_sql = (
        "SELECT r.occurrence, r.rule_kind, r.link_type_key, r.constrained_end,"
        " r.lower_bound, r.upper_bound, r.description"
        " FROM definition_multiplicity_rule AS r"
    )
    relationship_parameters: list[object] = [identity]
    if relationship_keys is not None:
        if not relationship_keys:
            relationship_rows = ()
        else:
            placeholders = ", ".join("?" for _ in relationship_keys)
            relationship_sql += (
                f" WHERE r.definition_set_id = ? AND r.natural_key IN ({placeholders})"
            )
            relationship_parameters.extend(sorted(relationship_keys))
            relationship_rows = connection.execute(
                relationship_sql + " ORDER BY r.occurrence", tuple(relationship_parameters)
            )
    elif constrained_type_keys is not None:
        if not constrained_type_keys:
            relationship_rows = ()
        else:
            placeholders = ", ".join("?" for _ in constrained_type_keys)
            relationship_sql += (
                " JOIN definition_multiplicity_participant AS p"
                " ON p.definition_set_id = r.definition_set_id"
                " AND p.rule_occurrence = r.occurrence AND p.role = 'first'"
                " WHERE r.definition_set_id = ?"
                f" AND p.type_key IN ({placeholders})"
                " GROUP BY r.definition_set_id, r.occurrence"
            )
            relationship_parameters.extend(sorted(constrained_type_keys))
            relationship_rows = connection.execute(
                relationship_sql + " ORDER BY r.occurrence",
                tuple(relationship_parameters),
            )
    else:
        relationship_sql += " WHERE r.definition_set_id = ?"
        relationship_rows = connection.execute(
            relationship_sql + " ORDER BY r.occurrence",
            tuple(relationship_parameters),
        )
    for occurrence, kind, link_type, end, lower, upper, description in relationship_rows:

        def members(role: str, rule_occurrence: int = int(occurrence)) -> tuple[str, ...]:
            return tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT type_key FROM definition_multiplicity_participant"
                    " WHERE definition_set_id = ?"
                    " AND rule_occurrence = ? AND role = ? ORDER BY occurrence",
                    (identity, rule_occurrence, role),
                )
            )

        if kind == "linkMultiplicity":
            relationships.append(
                LinkMultiplicityConstraint(
                    str(link_type),
                    LinkEnd(str(end)),
                    members("first"),
                    members("second"),
                    int(lower),
                    upper,
                    description,
                )
            )
        else:
            relationships.append(
                DirectAssociationMultiplicityConstraint(
                    DirectAssociationEnd(str(end)),
                    members("first"),
                    members("second"),
                    int(lower),
                    upper,
                    description,
                )
            )
    return GraphDefinitionSet(
        tuple(anchors), tuple(data_types), tuple(link_types), tuple(relationships)
    )
