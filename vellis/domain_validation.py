"""Pure validation for Vellis domain values and complete states."""

from __future__ import annotations

import struct
from collections.abc import Iterable, Mapping

import re2

from vellis.cardinality_validation import graph_cardinality_findings
from vellis.domain import (
    Anchor,
    AssociatedData,
    AssociatedDataTypeDefinition,
    Cardinality,
    DefinitionKind,
    Finding,
    FindingCode,
    GraphObject,
    Link,
    LinkTypeDefinition,
    PropertyDefinition,
    ScalarValue,
    SystemEnvelope,
    TimestampValue,
    TypeDefinition,
    ValueKind,
    canonical_uuid,
)
from vellis.json_pointer import append_pointer as _path


def scalar_identity(value: ScalarValue) -> tuple[object, ...]:
    content = value.value
    if value.kind is ValueKind.NUMBER:
        assert isinstance(content, float)
        return (value.kind, struct.pack(">d", content))
    if isinstance(content, TimestampValue):
        return (value.kind, content.epoch_seconds, content.nanosecond)
    return (value.kind, content)


def property_definition_findings(
    definition: PropertyDefinition, *, path: str = ""
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    _require_nonempty(definition.name, _path(path, "name"), "property name", findings)
    _require_nonempty(definition.description, _path(path, "description"), "description", findings)
    _validate_allowed_values(definition, path, findings)
    _validate_value_bounds(definition, path, findings)
    _validate_text_constraints(definition, path, findings)
    return _ordered(findings)


def definition_set_findings(
    definitions: Iterable[TypeDefinition], *, require_system: bool
) -> tuple[Finding, ...]:
    values = tuple(definitions)
    findings: list[Finding] = []
    by_key: dict[str, TypeDefinition] = {}
    for index, definition in enumerate(values):
        path = _path("/definitions", index)
        _require_nonempty(definition.type_key, _path(path, "typeKey"), "type key", findings)
        _require_nonempty(
            definition.description, _path(path, "description"), "description", findings
        )
        if definition.type_key in by_key:
            findings.append(
                _finding(
                    FindingCode.DUPLICATE,
                    _path(path, "typeKey"),
                    "duplicate type key",
                )
            )
        else:
            by_key[definition.type_key] = definition
        _validate_system(definition.system, path, require_system, findings)
        _validate_definition_content(definition, path, findings)
    for index, definition in enumerate(values):
        _validate_definition_references(definition, by_key, _path("/definitions", index), findings)
    return _ordered(findings)


def type_definition_findings(
    definition: TypeDefinition,
    referenced_definitions: Iterable[TypeDefinition],
    *,
    require_system: bool,
) -> tuple[Finding, ...]:
    """Validate one definition without materializing the complete definition set."""
    path = _path("/definitions", definition.type_key)
    findings: list[Finding] = []
    _require_nonempty(definition.type_key, _path(path, "typeKey"), "type key", findings)
    _require_nonempty(definition.description, _path(path, "description"), "description", findings)
    _validate_system(definition.system, path, require_system, findings)
    _validate_definition_content(definition, path, findings)
    references = {value.type_key: value for value in referenced_definitions}
    references[definition.type_key] = definition
    _validate_definition_references(definition, references, path, findings)
    return _ordered(findings)


def graph_findings(
    objects: Iterable[GraphObject],
    definitions: Iterable[TypeDefinition],
    *,
    require_system: bool,
) -> tuple[Finding, ...]:
    return _ordered(
        (
            *graph_structure_findings(objects, definitions, require_system=require_system),
            *graph_cardinality_findings(objects, definitions),
        )
    )


def graph_structure_findings(
    objects: Iterable[GraphObject],
    definitions: Iterable[TypeDefinition],
    *,
    require_system: bool,
) -> tuple[Finding, ...]:
    graph = tuple(objects)
    definition_map = {definition.type_key: definition for definition in definitions}
    object_map: dict[str, GraphObject] = {}
    findings: list[Finding] = []
    for value in graph:
        # Address the affected-state subject, as every other object finding does.
        # A position in the validated closure is not a member of any request.
        path = _path("/objects", value.uuid)
        _validate_object_header(value, definition_map, path, require_system, findings)
        try:
            canonical = canonical_uuid(value.uuid)
        except ValueError as error:
            findings.append(_finding(FindingCode.INVALID_VALUE, _path(path, "uuid"), str(error)))
            continue
        if canonical in object_map:
            findings.append(_finding(FindingCode.DUPLICATE, _path(path, "uuid"), "duplicate UUID"))
        else:
            object_map[canonical] = value
    for value in graph:
        _validate_object_content(
            value, definition_map, object_map, _path("/objects", value.uuid), findings
        )
    return _ordered(findings)


def graph_object_findings(
    value: GraphObject,
    definitions: Iterable[TypeDefinition],
    referents: Iterable[GraphObject],
    *,
    require_system: bool,
) -> tuple[Finding, ...]:
    """Validate one object using only its directly referenced objects."""
    definition_map = {definition.type_key: definition for definition in definitions}
    object_map = {item.uuid: item for item in referents}
    object_map[value.uuid] = value
    findings: list[Finding] = []
    path = _path("/objects", value.uuid)
    _validate_object_header(value, definition_map, path, require_system, findings)
    _validate_object_content(value, definition_map, object_map, path, findings)
    return _ordered(findings)


def property_value_findings(
    properties: tuple[tuple[str, ScalarValue | None], ...],
    definitions: tuple[PropertyDefinition, ...],
    *,
    path: str,
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    rules = {definition.name: definition for definition in definitions}
    seen: set[str] = set()
    present: dict[str, ScalarValue | None] = {}
    for name, value in properties:
        item_path = _path(path, name)
        if name in seen:
            findings.append(_finding(FindingCode.DUPLICATE, item_path, "duplicate property name"))
        seen.add(name)
        present[name] = value
        rule = rules.get(name)
        if rule is None:
            findings.append(_finding(FindingCode.UNKNOWN, item_path, "undeclared property"))
        elif value is None:
            if not rule.nullable:
                findings.append(
                    _finding(
                        FindingCode.CONSTRAINT_VIOLATION, item_path, "property is not nullable"
                    )
                )
        else:
            _validate_property_value(value, rule, item_path, findings)
    for name, rule in rules.items():
        if rule.required and name not in present:
            findings.append(
                _finding(
                    FindingCode.MISSING,
                    _path(path, name),
                    "required property is absent",
                )
            )
    return _ordered(findings)


def _validate_allowed_values(
    definition: PropertyDefinition, path: str, findings: list[Finding]
) -> None:
    if definition.allowed_values_present and not definition.allowed_values:
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE,
                _path(path, "allowedValues"),
                "allowed values must be nonempty when supplied",
            )
        )
        return
    if not definition.allowed_values:
        return
    identities: set[tuple[object, ...]] = set()
    for index, value in enumerate(definition.allowed_values):
        item_path = _path(path, "allowedValues", index)
        if value.kind is not definition.value_kind:
            findings.append(
                _finding(FindingCode.KIND_MISMATCH, item_path, "allowed value has another kind")
            )
        identity = scalar_identity(value)
        if identity in identities:
            findings.append(_finding(FindingCode.DUPLICATE, item_path, "duplicate allowed value"))
        identities.add(identity)
        _validate_nonnull_constraints(value, definition, item_path, findings, check_allowed=False)


def _validate_value_bounds(
    definition: PropertyDefinition, path: str, findings: list[Finding]
) -> None:
    bounded = {ValueKind.INTEGER, ValueKind.NUMBER, ValueKind.DATE, ValueKind.TIMESTAMP}
    if (definition.minimum is not None or definition.maximum is not None) and (
        definition.value_kind not in bounded
    ):
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE, path, "value bounds are incompatible with property kind"
            )
        )
    for label, value in (("minimum", definition.minimum), ("maximum", definition.maximum)):
        if value is not None and value.kind is not definition.value_kind:
            findings.append(
                _finding(
                    FindingCode.KIND_MISMATCH,
                    _path(path, label),
                    "bound has another kind",
                )
            )
    if definition.minimum is not None and definition.maximum is not None:
        if _compare(definition.minimum, definition.maximum) > 0:
            findings.append(_finding(FindingCode.INVALID_VALUE, path, "minimum exceeds maximum"))


def _validate_text_constraints(
    definition: PropertyDefinition, path: str, findings: list[Finding]
) -> None:
    has_text_rule = any(
        value is not None
        for value in (definition.minimum_length, definition.maximum_length, definition.pattern)
    )
    if has_text_rule and definition.value_kind is not ValueKind.TEXT:
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE,
                path,
                "text constraint is incompatible with property kind",
            )
        )
    if definition.minimum_length is not None and definition.minimum_length < 0:
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE,
                _path(path, "minimumLength"),
                "minimum length is negative",
            )
        )
    if definition.maximum_length is not None and definition.maximum_length < 0:
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE,
                _path(path, "maximumLength"),
                "maximum length is negative",
            )
        )
    if definition.minimum_length is not None and definition.maximum_length is not None:
        if definition.minimum_length > definition.maximum_length:
            findings.append(
                _finding(FindingCode.INVALID_VALUE, path, "minimum length exceeds maximum length")
            )
    if definition.pattern is not None:
        try:
            re2.compile(definition.pattern)
        except re2.error:
            findings.append(
                _finding(
                    FindingCode.INVALID_VALUE,
                    _path(path, "pattern"),
                    "invalid RE2 pattern",
                )
            )


def _validate_definition_content(
    definition: TypeDefinition, path: str, findings: list[Finding]
) -> None:
    if isinstance(definition, AssociatedDataTypeDefinition):
        if not definition.permitted_anchor_type_keys:
            findings.append(
                _finding(
                    FindingCode.MISSING,
                    _path(path, "permittedAnchorTypeKeys"),
                    "permitted anchor types are empty",
                )
            )
        _duplicates(
            definition.permitted_anchor_type_keys,
            _path(path, "permittedAnchorTypeKeys"),
            findings,
        )
        _duplicates(
            (value.name for value in definition.properties),
            _path(path, "properties"),
            findings,
        )
        for value in definition.properties:
            findings.extend(
                property_definition_findings(value, path=_path(path, "properties", value.name))
            )
        _validate_cardinality(
            definition.anchors_per_object,
            _path(path, "anchorsPerObject"),
            1,
            findings,
        )
        _validate_cardinality(
            definition.objects_per_anchor,
            _path(path, "objectsPerAnchor"),
            0,
            findings,
        )
    elif isinstance(definition, LinkTypeDefinition):
        _validate_link_definition(definition, path, findings)


def _validate_link_definition(
    definition: LinkTypeDefinition, path: str, findings: list[Finding]
) -> None:
    if not definition.permitted_source_type_keys:
        findings.append(
            _finding(
                FindingCode.MISSING,
                _path(path, "permittedSourceTypeKeys"),
                "permitted source types are empty",
            )
        )
    if not definition.permitted_target_type_keys:
        findings.append(
            _finding(
                FindingCode.MISSING,
                _path(path, "permittedTargetTypeKeys"),
                "permitted target types are empty",
            )
        )
    _duplicates(
        definition.permitted_source_type_keys,
        _path(path, "permittedSourceTypeKeys"),
        findings,
    )
    _duplicates(
        definition.permitted_target_type_keys,
        _path(path, "permittedTargetTypeKeys"),
        findings,
    )
    _validate_cardinality(definition.links_per_source, _path(path, "linksPerSource"), 0, findings)
    _validate_cardinality(definition.links_per_target, _path(path, "linksPerTarget"), 0, findings)


def _validate_definition_references(
    definition: TypeDefinition,
    definitions: Mapping[str, TypeDefinition],
    path: str,
    findings: list[Finding],
) -> None:
    if isinstance(definition, AssociatedDataTypeDefinition):
        for key in definition.permitted_anchor_type_keys:
            target = definitions.get(key)
            if target is None:
                findings.append(
                    _finding(
                        FindingCode.UNKNOWN,
                        _path(path, "permittedAnchorTypeKeys", key),
                        "unknown anchor type",
                        type_keys=(key,),
                    )
                )
            elif target.kind is not DefinitionKind.ANCHOR:
                findings.append(
                    _finding(
                        FindingCode.KIND_MISMATCH,
                        _path(path, "permittedAnchorTypeKeys", key),
                        "permitted type is not an anchor",
                        type_keys=(key,),
                    )
                )
    elif isinstance(definition, LinkTypeDefinition):
        _validate_endpoint_types(
            definition.permitted_source_type_keys,
            definitions,
            _path(path, "permittedSourceTypeKeys"),
            findings,
        )
        _validate_endpoint_types(
            definition.permitted_target_type_keys,
            definitions,
            _path(path, "permittedTargetTypeKeys"),
            findings,
        )


def _validate_endpoint_types(
    keys: tuple[str, ...],
    definitions: Mapping[str, TypeDefinition],
    path: str,
    findings: list[Finding],
) -> None:
    for key in keys:
        target = definitions.get(key)
        if target is None:
            findings.append(
                _finding(
                    FindingCode.UNKNOWN,
                    _path(path, key),
                    "unknown endpoint type",
                    type_keys=(key,),
                )
            )
        elif target.kind is DefinitionKind.LINK:
            findings.append(
                _finding(
                    FindingCode.KIND_MISMATCH,
                    _path(path, key),
                    "link type cannot be an endpoint type",
                    type_keys=(key,),
                )
            )


def _validate_object_header(
    value: GraphObject,
    definitions: Mapping[str, TypeDefinition],
    path: str,
    require_system: bool,
    findings: list[Finding],
) -> None:
    _require_nonempty(value.type_key, _path(path, "typeKey"), "type key", findings)
    _validate_system(value.system, path, require_system, findings)
    definition = definitions.get(value.type_key)
    if definition is None:
        findings.append(
            _finding(
                FindingCode.UNKNOWN,
                _path(path, "typeKey"),
                "unknown object type",
                type_keys=(value.type_key,),
            )
        )
    elif definition.kind.value != value.kind.value:
        findings.append(
            _finding(
                FindingCode.KIND_MISMATCH,
                _path(path, "typeKey"),
                "object and definition kinds differ",
                type_keys=(value.type_key,),
                uuids=(value.uuid,),
            )
        )
    if isinstance(value, Anchor):
        _require_nonempty(value.display_name, _path(path, "displayName"), "display name", findings)


def _validate_object_content(
    value: GraphObject,
    definitions: Mapping[str, TypeDefinition],
    objects: Mapping[str, GraphObject],
    path: str,
    findings: list[Finding],
) -> None:
    if isinstance(value, AssociatedData):
        _validate_associated_data(value, definitions, objects, path, findings)
    elif isinstance(value, Link):
        _validate_link(value, definitions, objects, path, findings)


def _validate_associated_data(
    value: AssociatedData,
    definitions: Mapping[str, TypeDefinition],
    objects: Mapping[str, GraphObject],
    path: str,
    findings: list[Finding],
) -> None:
    definition = definitions.get(value.type_key)
    if not value.anchor_uuids:
        findings.append(
            _finding(
                FindingCode.MISSING,
                _path(path, "anchorUuids"),
                "anchor set is empty",
                uuids=(value.uuid,),
            )
        )
    _duplicates(value.anchor_uuids, _path(path, "anchorUuids"), findings)
    for anchor_uuid in value.anchor_uuids:
        anchor_path = _path(path, "anchorUuids", anchor_uuid)
        anchor = objects.get(anchor_uuid)
        if anchor is None:
            findings.append(
                _finding(
                    FindingCode.UNKNOWN,
                    anchor_path,
                    "anchor does not resolve",
                    uuids=(value.uuid, anchor_uuid),
                )
            )
        elif not isinstance(anchor, Anchor):
            findings.append(
                _finding(
                    FindingCode.KIND_MISMATCH,
                    anchor_path,
                    "association endpoint is not an anchor",
                    uuids=(value.uuid, anchor_uuid),
                )
            )
        elif (
            isinstance(definition, AssociatedDataTypeDefinition)
            and anchor.type_key not in definition.permitted_anchor_type_keys
        ):
            findings.append(
                _finding(
                    FindingCode.CONSTRAINT_VIOLATION,
                    anchor_path,
                    "anchor type is not permitted",
                    type_keys=(anchor.type_key,),
                    uuids=(value.uuid, anchor_uuid),
                )
            )
    if isinstance(definition, AssociatedDataTypeDefinition):
        findings.extend(
            property_value_findings(
                value.properties, definition.properties, path=_path(path, "properties")
            )
        )


def _validate_link(
    value: Link,
    definitions: Mapping[str, TypeDefinition],
    objects: Mapping[str, GraphObject],
    path: str,
    findings: list[Finding],
) -> None:
    definition = definitions.get(value.type_key)
    _validate_link_endpoint(
        value, value.source_uuid, "sourceUuid", objects, definition, True, path, findings
    )
    _validate_link_endpoint(
        value, value.target_uuid, "targetUuid", objects, definition, False, path, findings
    )


def _validate_link_endpoint(
    link: Link,
    uuid: str,
    field: str,
    objects: Mapping[str, GraphObject],
    definition: TypeDefinition | None,
    source: bool,
    path: str,
    findings: list[Finding],
) -> None:
    endpoint = objects.get(uuid)
    if endpoint is None:
        findings.append(
            _finding(
                FindingCode.UNKNOWN,
                _path(path, field),
                "link endpoint does not resolve",
                uuids=(link.uuid, uuid),
            )
        )
        return
    if isinstance(endpoint, Link):
        findings.append(
            _finding(
                FindingCode.KIND_MISMATCH,
                _path(path, field),
                "link cannot be a link endpoint",
                uuids=(link.uuid, uuid),
            )
        )
        return
    if isinstance(definition, LinkTypeDefinition):
        permitted = (
            definition.permitted_source_type_keys
            if source
            else definition.permitted_target_type_keys
        )
        if endpoint.type_key not in permitted:
            findings.append(
                _finding(
                    FindingCode.CONSTRAINT_VIOLATION,
                    _path(path, field),
                    "endpoint type is not permitted",
                    type_keys=(endpoint.type_key,),
                    uuids=(link.uuid, uuid),
                )
            )


def _validate_property_value(
    value: ScalarValue,
    definition: PropertyDefinition,
    path: str,
    findings: list[Finding],
) -> None:
    if value.kind is not definition.value_kind:
        findings.append(
            _finding(FindingCode.KIND_MISMATCH, path, "property value has another kind")
        )
        return
    _validate_nonnull_constraints(value, definition, path, findings, check_allowed=True)


def _validate_nonnull_constraints(
    value: ScalarValue,
    definition: PropertyDefinition,
    path: str,
    findings: list[Finding],
    *,
    check_allowed: bool,
) -> None:
    if check_allowed and definition.allowed_values:
        allowed = {scalar_identity(each) for each in definition.allowed_values}
        if scalar_identity(value) not in allowed:
            findings.append(
                _finding(FindingCode.CONSTRAINT_VIOLATION, path, "value is not allowed")
            )
    if definition.minimum is not None and _compare(value, definition.minimum) < 0:
        findings.append(_finding(FindingCode.CONSTRAINT_VIOLATION, path, "value is below minimum"))
    if definition.maximum is not None and _compare(value, definition.maximum) > 0:
        findings.append(_finding(FindingCode.CONSTRAINT_VIOLATION, path, "value is above maximum"))
    if value.kind is ValueKind.TEXT:
        assert isinstance(value.value, str)
        _validate_text_value(value.value, definition, path, findings)


def _validate_text_value(
    value: str, definition: PropertyDefinition, path: str, findings: list[Finding]
) -> None:
    if definition.minimum_length is not None and len(value) < definition.minimum_length:
        findings.append(
            _finding(FindingCode.CONSTRAINT_VIOLATION, path, "text is shorter than minimumLength")
        )
    if definition.maximum_length is not None and len(value) > definition.maximum_length:
        findings.append(
            _finding(FindingCode.CONSTRAINT_VIOLATION, path, "text is longer than maximumLength")
        )
    if definition.pattern is not None:
        try:
            matches = re2.fullmatch(definition.pattern, value) is not None
        except re2.error:
            return
        if not matches:
            findings.append(
                _finding(FindingCode.CONSTRAINT_VIOLATION, path, "text does not match pattern")
            )


def _compare(left: ScalarValue, right: ScalarValue) -> int:
    if left.kind is not right.kind:
        return 0
    first = left.value
    second = right.value
    if isinstance(first, TimestampValue) and isinstance(second, TimestampValue):
        one: object = (first.epoch_seconds, first.nanosecond)
        two: object = (second.epoch_seconds, second.nanosecond)
    else:
        one, two = first, second
    if one == two:
        return 0
    return -1 if one < two else 1  # type: ignore[operator]


def _validate_cardinality(
    value: Cardinality, path: str, minimum: int, findings: list[Finding]
) -> None:
    if value.minimum < minimum:
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE,
                _path(path, "minimum"),
                f"minimum must be at least {minimum}",
            )
        )
    if value.maximum is not None and value.maximum < value.minimum:
        findings.append(_finding(FindingCode.INVALID_VALUE, path, "maximum is below minimum"))


def _validate_system(
    value: SystemEnvelope | None,
    path: str,
    required: bool,
    findings: list[Finding],
) -> None:
    if value is None:
        if required:
            findings.append(
                _finding(
                    FindingCode.MISSING,
                    _path(path, "system"),
                    "canonical system envelope is absent",
                )
            )
        return
    if value.created_revision < 0 or value.last_changed_revision < value.created_revision:
        findings.append(
            _finding(
                FindingCode.INVALID_VALUE,
                _path(path, "system"),
                "system revision interval is invalid",
            )
        )


def _duplicates(values: Iterable[str], path: str, findings: list[Finding]) -> None:
    seen: set[str] = set()
    for index, value in enumerate(values):
        if value in seen:
            findings.append(
                _finding(
                    FindingCode.DUPLICATE,
                    _path(path, index),
                    "duplicate value",
                )
            )
        seen.add(value)


def _require_nonempty(value: str, path: str, label: str, findings: list[Finding]) -> None:
    if value == "":
        findings.append(_finding(FindingCode.MISSING, path, f"{label} is empty"))


def _finding(
    code: FindingCode,
    path: str | None,
    summary: str,
    *,
    type_keys: tuple[str, ...] = (),
    uuids: tuple[str, ...] = (),
) -> Finding:
    return Finding(code, summary, path, tuple(sorted(set(type_keys))), tuple(sorted(set(uuids))))


def _ordered(values: Iterable[Finding]) -> tuple[Finding, ...]:
    return tuple(
        sorted(
            values,
            key=lambda value: (
                value.code.value,
                value.path or "",
                value.type_keys,
                value.uuids,
                value.summary,
            ),
        )
    )
