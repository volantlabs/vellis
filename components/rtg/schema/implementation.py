from __future__ import annotations

import copy
import json
from uuid import UUID, uuid4

from components.rtg.schema.protocol import (
    JsonObject,
    JsonValue,
    RtgAnchorSchemaPayload,
    RtgDataObjectSchemaPayload,
    RtgLinkSchemaPayload,
    RtgSchemaAnchorTypeSummary,
    RtgSchemaAnchorTypeSummaryList,
    RtgSchemaAssociatedDataTypeList,
    RtgSchemaDefinition,
    RtgSchemaDefinitionInvalid,
    RtgSchemaDefinitionKindInvalid,
    RtgSchemaDefinitionList,
    RtgSchemaDefinitionNotFound,
    RtgSchemaDeleteResult,
    RtgSchemaDirectionInvalid,
    RtgSchemaField,
    RtgSchemaLinkParticipation,
    RtgSchemaLinkParticipationList,
    RtgSchemaLiveTypeConflict,
    RtgSchemaPack,
    RtgSchemaPayload,
    RtgSchemaPayloadInvalid,
    RtgSchemaSnapshot,
    RtgSchemaSnapshotInvalid,
    RtgSchemaSystemValueInvalid,
    RtgSchemaTypeKeyInvalid,
    RtgSchemaUuidConflict,
    RtgSchemaUuidInvalid,
    UuidInput,
)

_ANCHOR = "anchor"
_DATA_OBJECT = "data_object"
_LINK = "link"
_KINDS = {_ANCHOR, _DATA_OBJECT, _LINK}
_VALUE_KIND_ORDER = {
    kind: index
    for index, kind in enumerate(
        ("string", "integer", "number", "boolean", "null", "object", "list", "uuid")
    )
}
_VALUE_KINDS = set(_VALUE_KIND_ORDER)
_DIRECTIONS = {"source", "target", "either"}


class InMemoryRtgSchema:
    """In-memory implementation of the RTG Schema component."""

    def __init__(self) -> None:
        self._definitions: dict[UUID, RtgSchemaDefinition] = {}

    @classmethod
    def empty(cls) -> InMemoryRtgSchema:
        return cls()

    @classmethod
    def import_snapshot(cls, snapshot: RtgSchemaSnapshot) -> InMemoryRtgSchema:
        if not isinstance(snapshot, RtgSchemaSnapshot) or not isinstance(
            snapshot.definitions, tuple
        ):
            raise RtgSchemaSnapshotInvalid("snapshot must contain a definition tuple")
        schema = cls.empty()
        seen_uuids: set[UUID] = set()
        for record in snapshot.definitions:
            definition = _definition_from_json(record)
            definition_uuid = _definition_uuid(definition)
            if definition_uuid in seen_uuids:
                raise RtgSchemaUuidConflict(str(definition_uuid))
            seen_uuids.add(definition_uuid)
            schema.put_definition(definition)
        return schema

    def export_snapshot(self) -> RtgSchemaSnapshot:
        return RtgSchemaSnapshot(
            definitions=tuple(_definition_to_json(item) for item in self._sorted())
        )

    def put_definition(self, definition: RtgSchemaDefinition) -> RtgSchemaDefinition:
        normalized = self._normalize_definition(definition)
        definition_uuid = _definition_uuid(normalized)
        self._validate_live_type_conflict(normalized)
        self._definitions[definition_uuid] = normalized
        return _copy_definition(normalized)

    def get_definition(self, definition_uuid: UuidInput) -> RtgSchemaDefinition:
        uuid_value = _parse_uuid(definition_uuid)
        try:
            return _copy_definition(self._definitions[uuid_value])
        except KeyError as error:
            raise RtgSchemaDefinitionNotFound(str(uuid_value)) from error

    def list_definitions(
        self,
        kind: str | None = None,
        live: bool | None = None,
    ) -> RtgSchemaDefinitionList:
        if kind is not None:
            _validate_kind(kind)
        return RtgSchemaDefinitionList(
            definitions=tuple(
                _copy_definition(item)
                for item in self._sorted()
                if (kind is None or item.kind == kind)
                and (live is None or item.system["live"] == live)
            )
        )

    def list_definitions_by_type_key(
        self,
        schema_type_key: str,
        kind: str | None = None,
        live: bool | None = None,
    ) -> RtgSchemaDefinitionList:
        type_key = _validate_type_key(schema_type_key)
        return RtgSchemaDefinitionList(
            definitions=tuple(
                _copy_definition(item)
                for item in self.list_definitions(kind=kind, live=live).definitions
                if item.type_key == type_key
            )
        )

    def list_anchor_data_type_keys(
        self,
        anchor_type_key: str,
        live: bool | None = True,
    ) -> RtgSchemaAssociatedDataTypeList:
        definition = self._live_or_first_definition(anchor_type_key, _ANCHOR, live)
        if not isinstance(definition.payload, RtgAnchorSchemaPayload):
            raise RtgSchemaPayloadInvalid("anchor definition payload mismatch")
        return RtgSchemaAssociatedDataTypeList(
            required_data_types=tuple(sorted(definition.payload.required_data_types)),
            optional_data_types=tuple(sorted(definition.payload.optional_data_types)),
        )

    def list_link_participation(
        self,
        type_key: str,
        direction: str = "either",
        live: bool | None = True,
    ) -> RtgSchemaLinkParticipationList:
        queried = _validate_type_key(type_key)
        if direction not in _DIRECTIONS:
            raise RtgSchemaDirectionInvalid(f"invalid direction: {direction}")
        links = []
        for definition in self.list_definitions(kind=_LINK, live=live).definitions:
            if not isinstance(definition.payload, RtgLinkSchemaPayload):
                continue
            source = queried in definition.payload.allowed_source_types
            target = queried in definition.payload.allowed_target_types
            if direction == "source" and not source:
                continue
            if direction == "target" and not target:
                continue
            if direction == "either" and not (source or target):
                continue
            relative = "both" if source and target else "source" if source else "target"
            links.append(
                RtgSchemaLinkParticipation(
                    definition_uuid=_definition_uuid(definition),
                    type_key=definition.type_key,
                    direction=relative,
                    allowed_source_types=definition.payload.allowed_source_types,
                    allowed_target_types=definition.payload.allowed_target_types,
                    live=definition.system["live"] is True,
                )
            )
        return RtgSchemaLinkParticipationList(
            links=tuple(sorted(links, key=lambda item: (item.type_key, str(item.definition_uuid))))
        )

    def list_anchor_type_summaries(
        self,
        live: bool | None = True,
    ) -> RtgSchemaAnchorTypeSummaryList:
        return RtgSchemaAnchorTypeSummaryList(
            anchor_types=tuple(
                RtgSchemaAnchorTypeSummary(
                    definition_uuid=_definition_uuid(item),
                    type_key=item.type_key,
                    description=item.description,
                    live=item.system["live"] is True,
                )
                for item in self.list_definitions(kind=_ANCHOR, live=live).definitions
            )
        )

    def get_schema_pack(
        self,
        anchor_type_keys: tuple[str, ...],
        live: bool | None = True,
    ) -> RtgSchemaPack:
        if not isinstance(anchor_type_keys, tuple) or not anchor_type_keys:
            raise RtgSchemaTypeKeyInvalid("anchor type keys must be a non-empty tuple")
        validated_anchor_type_keys = tuple(
            _validate_type_key(type_key) for type_key in anchor_type_keys
        )
        if len(set(validated_anchor_type_keys)) != len(validated_anchor_type_keys):
            raise RtgSchemaTypeKeyInvalid("anchor type keys must be unique")
        anchors = tuple(
            self._live_or_first_definition(anchor_type_key, _ANCHOR, live)
            for anchor_type_key in validated_anchor_type_keys
        )
        data_type_keys: set[str] = set()
        for anchor in anchors:
            if isinstance(anchor.payload, RtgAnchorSchemaPayload):
                data_type_keys.update(anchor.payload.required_data_types)
                data_type_keys.update(anchor.payload.optional_data_types)
        data_defs = tuple(
            item
            for item in self.list_definitions(kind=_DATA_OBJECT, live=live).definitions
            if item.type_key in data_type_keys
        )
        selected_anchor_keys = {item.type_key for item in anchors}
        link_defs = tuple(
            item
            for item in self.list_definitions(kind=_LINK, live=live).definitions
            if isinstance(item.payload, RtgLinkSchemaPayload)
            and (
                selected_anchor_keys.intersection(item.payload.allowed_source_types)
                or selected_anchor_keys.intersection(item.payload.allowed_target_types)
            )
        )
        return RtgSchemaPack(
            anchor_schemas=tuple(_copy_definition(item) for item in anchors),
            associated_data_object_schemas=tuple(_copy_definition(item) for item in data_defs),
            link_schemas=tuple(_copy_definition(item) for item in link_defs),
        )

    def delete_definition(self, definition_uuid: UuidInput) -> RtgSchemaDeleteResult:
        uuid_value = _parse_uuid(definition_uuid)
        try:
            deleted = self._definitions.pop(uuid_value)
        except KeyError as error:
            raise RtgSchemaDefinitionNotFound(str(uuid_value)) from error
        return RtgSchemaDeleteResult(deleted_definition=_copy_definition(deleted))

    def _normalize_definition(self, definition: RtgSchemaDefinition) -> RtgSchemaDefinition:
        kind = _validate_kind(definition.kind)
        payload = _validate_payload(kind, definition.payload)
        return RtgSchemaDefinition(
            uuid=_parse_uuid(definition.uuid)
            if definition.uuid is not None
            else self._generate_uuid(),
            kind=kind,
            type_key=_validate_type_key(definition.type_key),
            description=_validate_description(definition.description),
            payload=payload,
            system=_normalize_system(definition.system),
        )

    def _generate_uuid(self) -> UUID:
        while True:
            uuid_value = uuid4()
            if uuid_value not in self._definitions:
                return uuid_value

    def _validate_live_type_conflict(self, definition: RtgSchemaDefinition) -> None:
        if definition.system["live"] is not True:
            return
        definition_uuid = _definition_uuid(definition)
        for existing in self._definitions.values():
            if (
                _definition_uuid(existing) != definition_uuid
                and existing.system["live"] is True
                and existing.type_key == definition.type_key
            ):
                raise RtgSchemaLiveTypeConflict(definition.type_key)

    def _live_or_first_definition(
        self, type_key: str, kind: str, live: bool | None
    ) -> RtgSchemaDefinition:
        matches = self.list_definitions_by_type_key(
            _validate_type_key(type_key), kind=kind, live=live
        ).definitions
        if not matches:
            raise RtgSchemaDefinitionNotFound(type_key)
        return matches[0]

    def _sorted(self) -> tuple[RtgSchemaDefinition, ...]:
        return tuple(
            sorted(self._definitions.values(), key=lambda item: str(_definition_uuid(item)))
        )


def _parse_uuid(value: UuidInput) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise RtgSchemaUuidInvalid(str(value)) from error


def _definition_uuid(definition: RtgSchemaDefinition) -> UUID:
    if definition.uuid is None:
        raise RtgSchemaUuidInvalid("definition UUID is not concrete")
    return definition.uuid


def _validate_kind(value: str) -> str:
    if value not in _KINDS:
        raise RtgSchemaDefinitionKindInvalid(str(value))
    return value


def _validate_type_key(value: str) -> str:
    if not isinstance(value, str) or value == "" or value != value.strip():
        raise RtgSchemaTypeKeyInvalid(str(value))
    return value


def _validate_description(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RtgSchemaDefinitionInvalid("description must be non-empty semantic text")
    return value


def _validate_payload(kind: str, payload: RtgSchemaPayload) -> RtgSchemaPayload:
    if kind == _ANCHOR and isinstance(payload, RtgAnchorSchemaPayload):
        required = _normalize_type_key_set(payload.required_data_types, "required_data_types")
        optional = _normalize_type_key_set(payload.optional_data_types, "optional_data_types")
        overlap = set(required).intersection(optional)
        if overlap:
            raise RtgSchemaPayloadInvalid(
                f"required and optional data types must be disjoint: {sorted(overlap)}"
            )
        return RtgAnchorSchemaPayload(
            required_data_types=required,
            optional_data_types=optional,
        )
    if kind == _DATA_OBJECT and isinstance(payload, RtgDataObjectSchemaPayload):
        if not isinstance(payload.properties, dict):
            raise RtgSchemaPayloadInvalid("data object properties must be a property map")
        properties: dict[str, RtgSchemaField] = {}
        for name, field in payload.properties.items():
            if not isinstance(name, str) or not name:
                raise RtgSchemaPayloadInvalid("property names must be non-empty strings")
            properties[name] = _normalize_field(field)
        return RtgDataObjectSchemaPayload(
            properties={name: properties[name] for name in sorted(properties)}
        )
    if kind == _LINK and isinstance(payload, RtgLinkSchemaPayload):
        return RtgLinkSchemaPayload(
            allowed_source_types=_normalize_type_key_set(
                payload.allowed_source_types, "allowed_source_types", nonempty=True
            ),
            allowed_target_types=_normalize_type_key_set(
                payload.allowed_target_types, "allowed_target_types", nonempty=True
            ),
        )
    raise RtgSchemaDefinitionInvalid(f"payload does not match schema kind {kind!r}")


def _normalize_type_key_set(
    values: tuple[str, ...], field_name: str, *, nonempty: bool = False
) -> tuple[str, ...]:
    if not isinstance(values, tuple) or (nonempty and not values):
        qualifier = "non-empty " if nonempty else ""
        raise RtgSchemaPayloadInvalid(f"{field_name} must be a {qualifier}type-key tuple")
    normalized = tuple(_validate_type_key(value) for value in values)
    if len(set(normalized)) != len(normalized):
        raise RtgSchemaPayloadInvalid(f"{field_name} must contain unique type keys")
    return tuple(sorted(normalized))


def _normalize_field(field: RtgSchemaField) -> RtgSchemaField:
    if not isinstance(field, RtgSchemaField):
        raise RtgSchemaPayloadInvalid("properties and items must contain schema fields")
    if not isinstance(field.required, bool):
        raise RtgSchemaPayloadInvalid("field.required must be boolean")
    if not isinstance(field.value_kinds, tuple) or not field.value_kinds:
        raise RtgSchemaPayloadInvalid("field.value_kinds must be a non-empty tuple")
    for value_kind in field.value_kinds:
        if value_kind not in _VALUE_KINDS:
            raise RtgSchemaPayloadInvalid(f"invalid value kind: {value_kind}")
    if len(set(field.value_kinds)) != len(field.value_kinds):
        raise RtgSchemaPayloadInvalid("field.value_kinds must be unique")
    if not isinstance(field.properties, dict):
        raise RtgSchemaPayloadInvalid("field.properties must be a property map")
    if field.properties and "object" not in field.value_kinds:
        raise RtgSchemaPayloadInvalid("field.properties requires object in value_kinds")
    if field.items is not None and "list" not in field.value_kinds:
        raise RtgSchemaPayloadInvalid("field.items requires list in value_kinds")
    properties: dict[str, RtgSchemaField] = {}
    for name, nested in field.properties.items():
        if not isinstance(name, str) or not name:
            raise RtgSchemaPayloadInvalid("nested property names must be non-empty strings")
        properties[name] = _normalize_field(nested)
    items = _normalize_field(field.items) if field.items is not None else None
    return RtgSchemaField(
        required=field.required,
        value_kinds=tuple(sorted(field.value_kinds, key=_VALUE_KIND_ORDER.__getitem__)),
        properties={name: properties[name] for name in sorted(properties)},
        items=items,
    )


def _normalize_system(value: JsonObject) -> JsonObject:
    if not isinstance(value, dict):
        raise RtgSchemaSystemValueInvalid("system must be a JSON object")
    system = _validate_json_object(value)
    live = system.get("live", True)
    if not isinstance(live, bool):
        raise RtgSchemaSystemValueInvalid("system.live must be boolean")
    system["live"] = live
    return system


def _validate_json_object(value: JsonObject) -> JsonObject:
    if not isinstance(value, dict):
        raise RtgSchemaSystemValueInvalid("system must be a JSON object")
    copied = copy.deepcopy(value)
    _validate_json_value(copied)
    return copied


def _validate_json_value(value: JsonValue) -> None:
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise RtgSchemaSystemValueInvalid("JSON object keys must be strings")
        for item in value.values():
            _validate_json_value(item)
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if value is None or isinstance(value, str | int | float | bool):
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise RtgSchemaSystemValueInvalid(str(error)) from error
        return
    raise RtgSchemaSystemValueInvalid(
        f"system value is not JSON serializable: {type(value).__name__}"
    )


def _field_to_json(field: RtgSchemaField) -> JsonObject:
    result: JsonObject = {"required": field.required, "value_kinds": list(field.value_kinds)}
    if field.properties:
        result["properties"] = {
            key: _field_to_json(value) for key, value in field.properties.items()
        }
    if field.items is not None:
        result["items"] = _field_to_json(field.items)
    return result


def _field_from_json(value: JsonValue) -> RtgSchemaField:
    if not isinstance(value, dict):
        raise RtgSchemaPayloadInvalid("field must be an object")
    unknown = set(value).difference({"required", "value_kinds", "properties", "items"})
    if unknown:
        raise RtgSchemaPayloadInvalid(f"unknown field keys: {sorted(unknown)}")
    required = value.get("required")
    if not isinstance(required, bool):
        raise RtgSchemaPayloadInvalid("field.required must be boolean")
    value_kinds = _string_tuple(value.get("value_kinds", []), "value_kinds")
    properties = value.get("properties", {})
    if not isinstance(properties, dict):
        raise RtgSchemaPayloadInvalid("field.properties must be an object")
    return RtgSchemaField(
        required=required,
        value_kinds=value_kinds,
        properties={key: _field_from_json(item) for key, item in properties.items()},
        items=(
            _field_from_json(value["items"])
            if "items" in value and value["items"] is not None
            else None
        ),
    )


def _payload_to_json(payload: RtgSchemaPayload) -> JsonObject:
    if isinstance(payload, RtgAnchorSchemaPayload):
        return {
            "required_data_types": list(payload.required_data_types),
            "optional_data_types": list(payload.optional_data_types),
        }
    if isinstance(payload, RtgDataObjectSchemaPayload):
        return {
            "properties": {key: _field_to_json(value) for key, value in payload.properties.items()}
        }
    return {
        "allowed_source_types": list(payload.allowed_source_types),
        "allowed_target_types": list(payload.allowed_target_types),
    }


def _payload_from_json(kind: str, value: JsonValue) -> RtgSchemaPayload:
    if not isinstance(value, dict):
        raise RtgSchemaPayloadInvalid("payload must be an object")
    if kind == _ANCHOR:
        _reject_payload_keys(value, {"required_data_types", "optional_data_types"})
        return RtgAnchorSchemaPayload(
            required_data_types=_string_tuple(
                value.get("required_data_types", []), "required_data_types"
            ),
            optional_data_types=_string_tuple(
                value.get("optional_data_types", []), "optional_data_types"
            ),
        )
    if kind == _DATA_OBJECT:
        _reject_payload_keys(value, {"properties"})
        properties = value.get("properties", {})
        if not isinstance(properties, dict):
            raise RtgSchemaPayloadInvalid("data object properties must be an object")
        return RtgDataObjectSchemaPayload(
            properties={str(key): _field_from_json(item) for key, item in properties.items()}
        )
    _reject_payload_keys(value, {"allowed_source_types", "allowed_target_types"})
    return RtgLinkSchemaPayload(
        allowed_source_types=_string_tuple(
            value.get("allowed_source_types", []), "allowed_source_types"
        ),
        allowed_target_types=_string_tuple(
            value.get("allowed_target_types", []), "allowed_target_types"
        ),
    )


def _reject_payload_keys(value: JsonObject, allowed: set[str]) -> None:
    unknown = set(value).difference(allowed)
    if unknown:
        raise RtgSchemaPayloadInvalid(f"unknown payload keys: {sorted(unknown)}")


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise RtgSchemaPayloadInvalid(f"{field_name} must be a list")
    if not all(isinstance(item, str) for item in value):
        raise RtgSchemaPayloadInvalid(f"{field_name} must contain strings")
    return tuple(item for item in value if isinstance(item, str))


def _definition_to_json(definition: RtgSchemaDefinition) -> JsonObject:
    return {
        "uuid": str(_definition_uuid(definition)),
        "kind": definition.kind,
        "type_key": definition.type_key,
        "description": definition.description,
        "payload": _payload_to_json(definition.payload),
        "system": copy.deepcopy(definition.system),
    }


def _definition_from_json(value: object) -> RtgSchemaDefinition:
    if not isinstance(value, dict):
        raise RtgSchemaSnapshotInvalid("snapshot definitions must be objects")
    required_keys = {"uuid", "kind", "type_key", "description", "payload"}
    missing = required_keys.difference(value)
    unknown = set(value).difference(required_keys | {"system"})
    if missing or unknown:
        raise RtgSchemaSnapshotInvalid(
            f"definition keys invalid; missing={sorted(missing)}, unknown={sorted(unknown)}"
        )
    uuid_text = value["uuid"]
    kind = value["kind"]
    type_key = value["type_key"]
    description = value["description"]
    if not isinstance(uuid_text, str):
        raise RtgSchemaSnapshotInvalid("definition.uuid must be a string")
    if not isinstance(kind, str):
        raise RtgSchemaSnapshotInvalid("definition.kind must be a string")
    if not isinstance(type_key, str):
        raise RtgSchemaSnapshotInvalid("definition.type_key must be a string")
    if not isinstance(description, str):
        raise RtgSchemaSnapshotInvalid("definition.description must be a string")
    _validate_kind(kind)
    system = value.get("system", {})
    if not isinstance(system, dict):
        raise RtgSchemaSystemValueInvalid("system must be an object")
    return RtgSchemaDefinition(
        uuid=_parse_uuid(uuid_text),
        kind=kind,
        type_key=type_key,
        description=description,
        payload=_payload_from_json(kind, value["payload"]),
        system=system,
    )


def _copy_definition(definition: RtgSchemaDefinition) -> RtgSchemaDefinition:
    return copy.deepcopy(definition)
