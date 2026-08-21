"""Closed staging codec for one unpublished v1 recovery candidate."""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

from vellis.domain import (
    Anchor,
    AnchorTypeDefinition,
    AssociatedData,
    AssociatedDataTypeDefinition,
    Cardinality,
    GraphObject,
    Link,
    LinkTypeDefinition,
    PropertyDefinition,
    ScalarValue,
    SystemEnvelope,
    TypeDefinition,
    ValueKind,
)
from vellis.v1_json import decode_legacy_json
from vellis.v1_stage import STAGE_RELATION, put_payload


def stage_definition(connection, value: TypeDefinition, source_pointer: str) -> None:
    put_payload(
        connection,
        "candidateDefinition",
        value.type_key,
        source_pointer,
        _definition_payload(value),
    )


def stage_object(connection, value: GraphObject, source_pointer: str) -> None:
    put_payload(
        connection,
        "candidateObject",
        value.uuid,
        source_pointer,
        _object_payload(value),
    )


def iter_definitions(connection) -> Iterator[TypeDefinition]:
    rows = connection.execute(
        f"SELECT payload FROM {STAGE_RELATION} WHERE category='candidateDefinition' "
        "ORDER BY natural_key"
    )
    for row in rows:
        yield _definition(cast(dict[str, object], decode_legacy_json(str(row[0]))))


def iter_objects(connection, kind: str | None = None) -> Iterator[GraphObject]:
    rows = connection.execute(
        f"SELECT payload FROM {STAGE_RELATION} WHERE category='candidateObject' "
        "ORDER BY natural_key"
    )
    for row in rows:
        value = _object(cast(dict[str, object], decode_legacy_json(str(row[0]))))
        if kind is None or value.kind.value == kind:
            yield value


def load_candidate_definitions(connection, keys: tuple[str, ...]) -> tuple[TypeDefinition, ...]:
    """Decode only selected staged candidate definitions in exact key order."""
    values: list[TypeDefinition] = []
    for key in keys:
        row = connection.execute(
            f"SELECT payload FROM {STAGE_RELATION} "
            "WHERE category='candidateDefinition' AND natural_key=?",
            (key,),
        ).fetchone()
        if row is not None:
            values.append(_definition(cast(dict[str, object], decode_legacy_json(str(row[0])))))
    return tuple(values)


def load_objects(connection, uuids: tuple[str, ...]) -> tuple[GraphObject, ...]:
    """Decode only selected staged candidate objects in exact UUID order."""
    values: list[GraphObject] = []
    for uuid in uuids:
        row = connection.execute(
            f"SELECT payload FROM {STAGE_RELATION} "
            "WHERE category='candidateObject' AND natural_key=?",
            (uuid,),
        ).fetchone()
        if row is not None:
            values.append(_object(cast(dict[str, object], decode_legacy_json(str(row[0])))))
    return tuple(values)


def _definition_payload(value: TypeDefinition) -> dict[str, object]:
    common: dict[str, object] = {
        "kind": value.kind.value,
        "typeKey": value.type_key,
        "description": value.description,
        "legacyV1": _legacy(value.system),
    }
    if isinstance(value, AssociatedDataTypeDefinition):
        common.update(
            {
                "permittedAnchorTypeKeys": list(value.permitted_anchor_type_keys),
                "properties": [_property_payload(item) for item in value.properties],
                "anchorsPerObject": _cardinality(value.anchors_per_object),
                "objectsPerAnchor": _cardinality(value.objects_per_anchor),
            }
        )
    elif isinstance(value, LinkTypeDefinition):
        common.update(
            {
                "permittedSourceTypeKeys": list(value.permitted_source_type_keys),
                "permittedTargetTypeKeys": list(value.permitted_target_type_keys),
                "linksPerSource": _cardinality(value.links_per_source),
                "linksPerTarget": _cardinality(value.links_per_target),
            }
        )
    return common


def _property_payload(value: PropertyDefinition) -> dict[str, object]:
    return {
        "name": value.name,
        "description": value.description,
        "valueKind": value.value_kind.value,
        "required": value.required,
        "nullable": value.nullable,
        "allowedValues": [_scalar_payload(item) for item in value.allowed_values],
        "minimum": None if value.minimum is None else _scalar_payload(value.minimum),
        "maximum": None if value.maximum is None else _scalar_payload(value.maximum),
        "minimumLength": value.minimum_length,
        "maximumLength": value.maximum_length,
        "pattern": value.pattern,
    }


def _object_payload(value: GraphObject) -> dict[str, object]:
    common: dict[str, object] = {
        "kind": value.kind.value,
        "uuid": value.uuid,
        "typeKey": value.type_key,
        "legacyV1": _legacy(value.system),
    }
    if isinstance(value, Anchor):
        common["displayName"] = value.display_name
    elif isinstance(value, AssociatedData):
        common["anchorUuids"] = list(value.anchor_uuids)
        common["properties"] = [
            {"name": name, "value": None if item is None else _scalar_payload(item)}
            for name, item in value.properties
        ]
    else:
        common["sourceUuid"] = value.source_uuid
        common["targetUuid"] = value.target_uuid
    return common


def _definition(value: dict[str, object]) -> TypeDefinition:
    system = SystemEnvelope(0, 0, cast(str | None, value.get("legacyV1")))
    kind = value["kind"]
    if kind == "anchor":
        return AnchorTypeDefinition(str(value["typeKey"]), str(value["description"]), system)
    if kind == "associatedData":
        return AssociatedDataTypeDefinition(
            str(value["typeKey"]),
            str(value["description"]),
            tuple(cast(list[str], value["permittedAnchorTypeKeys"])),
            tuple(
                _property(cast(dict[str, object], item)) for item in cast(list, value["properties"])
            ),
            _read_cardinality(cast(dict[str, object], value["anchorsPerObject"])),
            _read_cardinality(cast(dict[str, object], value["objectsPerAnchor"])),
            system,
        )
    return LinkTypeDefinition(
        str(value["typeKey"]),
        str(value["description"]),
        tuple(cast(list[str], value["permittedSourceTypeKeys"])),
        tuple(cast(list[str], value["permittedTargetTypeKeys"])),
        _read_cardinality(cast(dict[str, object], value["linksPerSource"])),
        _read_cardinality(cast(dict[str, object], value["linksPerTarget"])),
        system,
    )


def _property(value: dict[str, object]) -> PropertyDefinition:
    return PropertyDefinition(
        str(value["name"]),
        str(value["description"]),
        ValueKind(str(value["valueKind"])),
        bool(value["required"]),
        bool(value["nullable"]),
        tuple(
            _scalar(cast(dict[str, object], item)) for item in cast(list, value["allowedValues"])
        ),
        None if value["minimum"] is None else _scalar(cast(dict, value["minimum"])),
        None if value["maximum"] is None else _scalar(cast(dict, value["maximum"])),
        cast(int | None, value["minimumLength"]),
        cast(int | None, value["maximumLength"]),
        cast(str | None, value["pattern"]),
    )


def _object(value: dict[str, object]) -> GraphObject:
    system = SystemEnvelope(0, 0, cast(str | None, value.get("legacyV1")))
    kind = value["kind"]
    if kind == "anchor":
        return Anchor(str(value["uuid"]), str(value["typeKey"]), str(value["displayName"]), system)
    if kind == "associatedData":
        properties = tuple(
            (
                str(item["name"]),
                None if item["value"] is None else _scalar(cast(dict[str, object], item["value"])),
            )
            for item in cast(list[dict[str, object]], value["properties"])
        )
        return AssociatedData(
            str(value["uuid"]),
            str(value["typeKey"]),
            tuple(cast(list[str], value["anchorUuids"])),
            properties,
            system,
        )
    return Link(
        str(value["uuid"]),
        str(value["typeKey"]),
        str(value["sourceUuid"]),
        str(value["targetUuid"]),
        system,
    )


def _scalar_payload(value: ScalarValue) -> dict[str, object]:
    content: object = value.wire_value()
    if value.kind is ValueKind.NUMBER:
        assert isinstance(value.value, float)
        content = value.value.hex()
    return {"kind": value.kind.value, "value": content}


def _scalar(value: dict[str, object]) -> ScalarValue:
    kind = ValueKind(str(value["kind"]))
    content = value["value"]
    if kind is ValueKind.BOOLEAN:
        return ScalarValue.boolean(cast(bool, content))
    if kind is ValueKind.INTEGER:
        return ScalarValue.integer(cast(int, content))
    if kind is ValueKind.NUMBER:
        return ScalarValue.number(float.fromhex(str(content)))
    if kind is ValueKind.TEXT:
        return ScalarValue.text(str(content))
    if kind is ValueKind.DATE:
        return ScalarValue.date(str(content))
    return ScalarValue.timestamp(str(content))


def _cardinality(value: Cardinality) -> dict[str, int | None]:
    return {"minimum": value.minimum, "maximum": value.maximum}


def _read_cardinality(value: dict[str, object]) -> Cardinality:
    return Cardinality(cast(int, value["minimum"]), cast(int | None, value["maximum"]))


def _legacy(value: SystemEnvelope | None) -> str | None:
    return None if value is None else value.legacy_v1
