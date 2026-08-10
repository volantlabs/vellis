"""Lossless JSON encoding of canonical state for durable storage.

The model states that snapshots and ledgers are semantic artifacts, not serialized
formats, and leaves storage form open. This module is that selected form: one
self-describing JSON encoding whose decode is strict, so a corrupted or truncated
store raises rather than silently reconstructing a different canonical meaning.
"""

from __future__ import annotations

from decimal import Decimal

from vellis.canonical import (
    CanonicalChange,
    CanonicalState,
    DefinitionDelta,
    DefinitionDeltaDisposition,
    canonical_state_equal,
)
from vellis.changes import GraphChange
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
    RelationshipConstraint,
    StringPattern,
    ValueRange,
    ValueShape,
)
from vellis.graph import Anchor, AssociatedDataObject, Graph, Link, SystemMetadata
from vellis.json_value import (
    MAXIMUM_STORED_INTEGER_EXPONENT,
    JsonKind,
    JsonValue,
    dumps,
    loads,
)

__all__ = [
    "DecodeError",
    "unreadable_reason",
    "decode_text",
    "decode_canonical_state",
    "decode_definition_set",
    "decode_graph",
    "encode_canonical_state",
    "encode_definition_set",
    "decode_canonical_change",
    "encode_canonical_change",
    "encode_graph",
    "encode_text",
]


class DecodeError(ValueError):
    """Raised when stored text does not decode to canonical meaning."""


# --- Typed readers ------------------------------------------------------------------


def _object(value: JsonValue, where: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise DecodeError(f"{where} is not a JSON object")
    return value


def _member(value: dict[str, JsonValue], name: str, where: str) -> JsonValue:
    if name not in value:
        raise DecodeError(f"{where} has no {name!r} member")
    return value[name]


def _string(value: JsonValue, where: str) -> str:
    if not isinstance(value, str):
        raise DecodeError(f"{where} is not a string")
    return value


def _optional_string(value: JsonValue, where: str) -> str | None:
    return None if value is None else _string(value, where)


def _bool(value: JsonValue, where: str) -> bool:
    if not isinstance(value, bool):
        raise DecodeError(f"{where} is not a Boolean")
    return value


def _int(value: JsonValue, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise DecodeError(f"{where} is not a number")
    if value.adjusted() >= MAXIMUM_STORED_INTEGER_EXPONENT:
        raise DecodeError(f"{where} is too large to be a stored integer")
    if value != value.to_integral_value():
        raise DecodeError(f"{where} is not an integer")
    return int(value)


def _optional_int(value: JsonValue, where: str) -> int | None:
    return None if value is None else _int(value, where)


def _array(value: JsonValue, where: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise DecodeError(f"{where} is not a JSON array")
    return value


def _strings(value: JsonValue, where: str) -> tuple[str, ...]:
    return tuple(_string(each, f"{where} member") for each in _array(value, where))


def _enum[E: (JsonKind, LinkEnd, DirectAssociationEnd, DefinitionDeltaDisposition)](
    enum_type: type[E], value: JsonValue, where: str
) -> E:
    text = _string(value, where)
    try:
        return enum_type(text)
    except ValueError as error:
        raise DecodeError(f"{where} has unknown value {text!r}") from error


# --- Graph --------------------------------------------------------------------------


def _encode_metadata(metadata: SystemMetadata) -> JsonValue:
    return dict(metadata.members)


def _decode_metadata(value: JsonValue, where: str) -> SystemMetadata:
    return SystemMetadata(members=dict(_object(value, where)))


def encode_graph(graph: Graph) -> JsonValue:
    """Encode canonical graph state."""
    return {
        "anchors": [
            {
                "uuid": anchor.uuid,
                "typeKey": anchor.type_key,
                "displayName": anchor.display_name,
                "systemMetadata": _encode_metadata(anchor.system_metadata),
            }
            for anchor in graph.anchors
        ],
        "associatedData": [
            {
                "uuid": data.uuid,
                "typeKey": data.type_key,
                "anchorUuids": list(data.anchor_uuids),
                "properties": dict(data.properties),
                "systemMetadata": _encode_metadata(data.system_metadata),
            }
            for data in graph.associated_data
        ],
        "links": [
            {
                "uuid": link.uuid,
                "typeKey": link.type_key,
                "sourceUuid": link.source_uuid,
                "targetUuid": link.target_uuid,
                "systemMetadata": _encode_metadata(link.system_metadata),
            }
            for link in graph.links
        ],
    }


def decode_graph(value: JsonValue) -> Graph:
    """Decode canonical graph state."""
    members = _object(value, "graph")
    anchors: list[Anchor] = []
    for each in _array(_member(members, "anchors", "graph"), "graph anchors"):
        anchor = _object(each, "anchor")
        anchors.append(
            Anchor(
                uuid=_string(_member(anchor, "uuid", "anchor"), "anchor uuid"),
                type_key=_string(_member(anchor, "typeKey", "anchor"), "anchor typeKey"),
                display_name=_string(
                    _member(anchor, "displayName", "anchor"), "anchor displayName"
                ),
                system_metadata=_decode_metadata(
                    _member(anchor, "systemMetadata", "anchor"), "anchor systemMetadata"
                ),
            )
        )
    associated: list[AssociatedDataObject] = []
    for each in _array(_member(members, "associatedData", "graph"), "graph associatedData"):
        data = _object(each, "associated data")
        associated.append(
            AssociatedDataObject(
                uuid=_string(_member(data, "uuid", "associated data"), "associated data uuid"),
                type_key=_string(
                    _member(data, "typeKey", "associated data"), "associated data typeKey"
                ),
                anchor_uuids=_strings(
                    _member(data, "anchorUuids", "associated data"), "associated data anchorUuids"
                ),
                properties=dict(
                    _object(
                        _member(data, "properties", "associated data"),
                        "associated data properties",
                    )
                ),
                system_metadata=_decode_metadata(
                    _member(data, "systemMetadata", "associated data"),
                    "associated data systemMetadata",
                ),
            )
        )
    links: list[Link] = []
    for each in _array(_member(members, "links", "graph"), "graph links"):
        link = _object(each, "link")
        links.append(
            Link(
                uuid=_string(_member(link, "uuid", "link"), "link uuid"),
                type_key=_string(_member(link, "typeKey", "link"), "link typeKey"),
                source_uuid=_string(_member(link, "sourceUuid", "link"), "link sourceUuid"),
                target_uuid=_string(_member(link, "targetUuid", "link"), "link targetUuid"),
                system_metadata=_decode_metadata(
                    _member(link, "systemMetadata", "link"), "link systemMetadata"
                ),
            )
        )
    return Graph(anchors=tuple(anchors), associated_data=tuple(associated), links=tuple(links))


# --- Definitions --------------------------------------------------------------------


def _encode_value_shape(shape: ValueShape | None) -> JsonValue:
    if shape is None:
        return None
    return {
        "minimumSize": None if shape.minimum_size is None else Decimal(shape.minimum_size),
        "maximumSize": None if shape.maximum_size is None else Decimal(shape.maximum_size),
    }


def _decode_value_shape(value: JsonValue) -> ValueShape | None:
    if value is None:
        return None
    members = _object(value, "value shape")
    return ValueShape(
        minimum_size=_optional_int(
            _member(members, "minimumSize", "value shape"), "value shape minimumSize"
        ),
        maximum_size=_optional_int(
            _member(members, "maximumSize", "value shape"), "value shape maximumSize"
        ),
    )


def _encode_value_range(value_range: ValueRange | None) -> JsonValue:
    if value_range is None:
        return None
    return {
        "lowerBound": value_range.lower_bound,
        "upperBound": value_range.upper_bound,
        "permittedValues": list(value_range.permitted_values),
    }


def _decode_value_range(value: JsonValue) -> ValueRange | None:
    if value is None:
        return None
    members = _object(value, "value range")
    return ValueRange(
        lower_bound=_member(members, "lowerBound", "value range"),
        upper_bound=_member(members, "upperBound", "value range"),
        permitted_values=tuple(
            _array(_member(members, "permittedValues", "value range"), "permitted values")
        ),
    )


def _encode_pattern(pattern: StringPattern | None) -> JsonValue:
    return None if pattern is None else {"expression": pattern.expression}


def _decode_pattern(value: JsonValue) -> StringPattern | None:
    if value is None:
        return None
    members = _object(value, "string pattern")
    return StringPattern(
        expression=_string(_member(members, "expression", "string pattern"), "pattern expression")
    )


def _encode_property(constraint: PropertyConstraint) -> JsonValue:
    return {
        "propertyName": constraint.property_name,
        "required": constraint.required,
        "jsonKind": constraint.json_kind.value,
        "description": constraint.description,
        "valueShape": _encode_value_shape(constraint.value_shape),
        "valueRange": _encode_value_range(constraint.value_range),
        "pattern": _encode_pattern(constraint.pattern),
    }


def _decode_property(value: JsonValue) -> PropertyConstraint:
    members = _object(value, "property constraint")
    where = "property constraint"
    return PropertyConstraint(
        property_name=_string(_member(members, "propertyName", where), f"{where} propertyName"),
        required=_bool(_member(members, "required", where), f"{where} required"),
        json_kind=_enum(JsonKind, _member(members, "jsonKind", where), f"{where} jsonKind"),
        description=_optional_string(
            _member(members, "description", where), f"{where} description"
        ),
        value_shape=_decode_value_shape(_member(members, "valueShape", where)),
        value_range=_decode_value_range(_member(members, "valueRange", where)),
        pattern=_decode_pattern(_member(members, "pattern", where)),
    )


def _encode_endpoint_constraint(constraint: EndpointConstraint) -> JsonValue:
    return {
        "permittedSourceTypeKeys": list(constraint.permitted_source_type_keys),
        "permittedTargetTypeKeys": list(constraint.permitted_target_type_keys),
        "description": constraint.description,
    }


def _decode_endpoint_constraint(value: JsonValue) -> EndpointConstraint:
    members = _object(value, "endpoint constraint")
    where = "endpoint constraint"
    return EndpointConstraint(
        permitted_source_type_keys=_strings(
            _member(members, "permittedSourceTypeKeys", where), f"{where} source types"
        ),
        permitted_target_type_keys=_strings(
            _member(members, "permittedTargetTypeKeys", where), f"{where} target types"
        ),
        description=_optional_string(
            _member(members, "description", where), f"{where} description"
        ),
    )


def _encode_relationship(constraint: RelationshipConstraint) -> JsonValue:
    common: dict[str, JsonValue] = {
        "lowerBound": Decimal(constraint.lower_bound),
        "upperBound": (None if constraint.upper_bound is None else Decimal(constraint.upper_bound)),
        "description": constraint.description,
    }
    if isinstance(constraint, LinkMultiplicityConstraint):
        return {
            "kind": "linkMultiplicity",
            "linkTypeKey": constraint.link_type_key,
            "constrainedEnd": constraint.constrained_end.value,
            "constrainedEndpointTypeKeys": list(constraint.constrained_endpoint_type_keys),
            "oppositeEndpointTypeKeys": list(constraint.opposite_endpoint_type_keys),
            **common,
        }
    return {
        "kind": "directAssociationMultiplicity",
        "constrainedEnd": constraint.constrained_end.value,
        "anchorTypeKeys": list(constraint.anchor_type_keys),
        "associatedDataTypeKeys": list(constraint.associated_data_type_keys),
        **common,
    }


def _decode_relationship(value: JsonValue) -> RelationshipConstraint:
    members = _object(value, "relationship constraint")
    where = "relationship constraint"
    kind = _string(_member(members, "kind", where), f"{where} kind")
    lower = _int(_member(members, "lowerBound", where), f"{where} lowerBound")
    upper = _optional_int(_member(members, "upperBound", where), f"{where} upperBound")
    description = _optional_string(_member(members, "description", where), f"{where} description")
    if kind == "linkMultiplicity":
        return LinkMultiplicityConstraint(
            link_type_key=_string(_member(members, "linkTypeKey", where), f"{where} linkTypeKey"),
            constrained_end=_enum(
                LinkEnd, _member(members, "constrainedEnd", where), f"{where} constrainedEnd"
            ),
            constrained_endpoint_type_keys=_strings(
                _member(members, "constrainedEndpointTypeKeys", where), f"{where} constrained"
            ),
            opposite_endpoint_type_keys=_strings(
                _member(members, "oppositeEndpointTypeKeys", where), f"{where} opposite"
            ),
            lower_bound=lower,
            upper_bound=upper,
            description=description,
        )
    if kind == "directAssociationMultiplicity":
        return DirectAssociationMultiplicityConstraint(
            constrained_end=_enum(
                DirectAssociationEnd,
                _member(members, "constrainedEnd", where),
                f"{where} constrainedEnd",
            ),
            anchor_type_keys=_strings(
                _member(members, "anchorTypeKeys", where), f"{where} anchorTypeKeys"
            ),
            associated_data_type_keys=_strings(
                _member(members, "associatedDataTypeKeys", where),
                f"{where} associatedDataTypeKeys",
            ),
            lower_bound=lower,
            upper_bound=upper,
            description=description,
        )
    raise DecodeError(f"{where} has unknown kind {kind!r}")


def encode_definition_set(definitions: GraphDefinitionSet) -> JsonValue:
    """Encode a complete graph definition set."""
    return {
        "anchorTypes": [
            {"typeKey": each.type_key, "description": each.description}
            for each in definitions.anchor_types
        ],
        "associatedDataTypes": [
            {
                "typeKey": each.type_key,
                "permittedAnchorTypeKeys": list(each.permitted_anchor_type_keys),
                "propertyConstraints": [
                    _encode_property(constraint) for constraint in each.property_constraints
                ],
                "description": each.description,
            }
            for each in definitions.associated_data_types
        ],
        "linkTypes": [
            {
                "typeKey": each.type_key,
                "endpointConstraint": _encode_endpoint_constraint(each.endpoint_constraint),
                "description": each.description,
            }
            for each in definitions.link_types
        ],
        "relationshipConstraints": [
            _encode_relationship(each) for each in definitions.relationship_constraints
        ],
    }


def decode_definition_set(value: JsonValue) -> GraphDefinitionSet:
    """Decode a complete graph definition set."""
    members = _object(value, "definition set")
    anchor_types = tuple(
        AnchorTypeDefinition(
            type_key=_string(
                _member(_object(each, "anchor type"), "typeKey", "anchor type"), "typeKey"
            ),
            description=_optional_string(
                _member(_object(each, "anchor type"), "description", "anchor type"), "description"
            ),
        )
        for each in _array(_member(members, "anchorTypes", "definition set"), "anchorTypes")
    )
    associated_data_types: list[AssociatedDataTypeDefinition] = []
    for each in _array(
        _member(members, "associatedDataTypes", "definition set"), "associatedDataTypes"
    ):
        data_type = _object(each, "associated data type")
        where = "associated data type"
        associated_data_types.append(
            AssociatedDataTypeDefinition(
                type_key=_string(_member(data_type, "typeKey", where), f"{where} typeKey"),
                permitted_anchor_type_keys=_strings(
                    _member(data_type, "permittedAnchorTypeKeys", where), f"{where} anchor types"
                ),
                property_constraints=tuple(
                    _decode_property(constraint)
                    for constraint in _array(
                        _member(data_type, "propertyConstraints", where), f"{where} properties"
                    )
                ),
                description=_optional_string(
                    _member(data_type, "description", where), f"{where} description"
                ),
            )
        )
    link_types: list[LinkTypeDefinition] = []
    for each in _array(_member(members, "linkTypes", "definition set"), "linkTypes"):
        link_type = _object(each, "link type")
        link_types.append(
            LinkTypeDefinition(
                type_key=_string(_member(link_type, "typeKey", "link type"), "link type typeKey"),
                endpoint_constraint=_decode_endpoint_constraint(
                    _member(link_type, "endpointConstraint", "link type")
                ),
                description=_optional_string(
                    _member(link_type, "description", "link type"), "link type description"
                ),
            )
        )
    relationships = tuple(
        _decode_relationship(each)
        for each in _array(
            _member(members, "relationshipConstraints", "definition set"),
            "relationshipConstraints",
        )
    )
    return GraphDefinitionSet(
        anchor_types=anchor_types,
        associated_data_types=tuple(associated_data_types),
        link_types=tuple(link_types),
        relationship_constraints=relationships,
    )


# --- Graph changes ------------------------------------------------------------------


def _encode_anchor(anchor: Anchor) -> JsonValue:
    return {
        "uuid": anchor.uuid,
        "typeKey": anchor.type_key,
        "displayName": anchor.display_name,
        "systemMetadata": _encode_metadata(anchor.system_metadata),
    }


def _encode_associated_data(data: AssociatedDataObject) -> JsonValue:
    return {
        "uuid": data.uuid,
        "typeKey": data.type_key,
        "anchorUuids": list(data.anchor_uuids),
        "properties": dict(data.properties),
        "systemMetadata": _encode_metadata(data.system_metadata),
    }


def _encode_link(link: Link) -> JsonValue:
    return {
        "uuid": link.uuid,
        "typeKey": link.type_key,
        "sourceUuid": link.source_uuid,
        "targetUuid": link.target_uuid,
        "systemMetadata": _encode_metadata(link.system_metadata),
    }


def encode_graph_change(change: GraphChange) -> JsonValue:
    """Encode the semantic upserts and removals a transition carries."""
    return {
        "anchorUpserts": [_encode_anchor(each) for each in change.anchor_upserts],
        "associatedDataUpserts": [
            _encode_associated_data(each) for each in change.associated_data_upserts
        ],
        "linkUpserts": [_encode_link(each) for each in change.link_upserts],
        "anchorRemovals": list(change.anchor_removals),
        "associatedDataRemovals": list(change.associated_data_removals),
        "linkRemovals": list(change.link_removals),
    }


def decode_graph_change(value: JsonValue) -> GraphChange:
    """Decode a graph change."""
    members = _object(value, "graph change")
    where = "graph change"
    graph = decode_graph(
        {
            "anchors": _member(members, "anchorUpserts", where),
            "associatedData": _member(members, "associatedDataUpserts", where),
            "links": _member(members, "linkUpserts", where),
        }
    )
    return GraphChange(
        anchor_upserts=graph.anchors,
        associated_data_upserts=graph.associated_data,
        link_upserts=graph.links,
        anchor_removals=_strings(_member(members, "anchorRemovals", where), f"{where} anchors"),
        associated_data_removals=_strings(
            _member(members, "associatedDataRemovals", where), f"{where} associated data"
        ),
        link_removals=_strings(_member(members, "linkRemovals", where), f"{where} links"),
    )


def encode_canonical_change(change: CanonicalChange) -> JsonValue:
    """Encode one transition's replay-sufficient change."""
    delta: JsonValue = None
    if change.definition_delta is not None:
        delta = {
            "proposedDefinitions": encode_definition_set(
                change.definition_delta.proposed_definitions
            )
        }
    return {
        "deltaDisposition": change.delta_disposition.value,
        "graphChange": (
            None if change.graph_change is None else encode_graph_change(change.graph_change)
        ),
        "replacementGraph": (
            None if change.replacement_graph is None else encode_graph(change.replacement_graph)
        ),
        "activeDefinitions": (
            None
            if change.active_definitions is None
            else encode_definition_set(change.active_definitions)
        ),
        "definitionDelta": delta,
    }


def decode_canonical_change(value: JsonValue) -> CanonicalChange:
    """Decode one transition's replay-sufficient change."""
    members = _object(value, "canonical change")
    where = "canonical change"
    raw_delta = _member(members, "definitionDelta", where)
    delta: DefinitionDelta | None = None
    if raw_delta is not None:
        delta = DefinitionDelta(
            proposed_definitions=decode_definition_set(
                _member(_object(raw_delta, "definition delta"), "proposedDefinitions", where)
            )
        )
    raw_graph_change = _member(members, "graphChange", where)
    raw_replacement = _member(members, "replacementGraph", where)
    raw_definitions = _member(members, "activeDefinitions", where)
    return CanonicalChange(
        delta_disposition=_enum(
            DefinitionDeltaDisposition,
            _member(members, "deltaDisposition", where),
            f"{where} deltaDisposition",
        ),
        graph_change=None if raw_graph_change is None else decode_graph_change(raw_graph_change),
        replacement_graph=None if raw_replacement is None else decode_graph(raw_replacement),
        active_definitions=(
            None if raw_definitions is None else decode_definition_set(raw_definitions)
        ),
        definition_delta=delta,
    )


# --- Canonical state ----------------------------------------------------------------


def encode_canonical_state(state: CanonicalState) -> JsonValue:
    """Encode one complete canonical-state tuple."""
    delta: JsonValue = None
    if state.definition_delta is not None:
        delta = {
            "proposedDefinitions": encode_definition_set(
                state.definition_delta.proposed_definitions
            )
        }
    return {
        "revision": Decimal(state.revision),
        "graph": encode_graph(state.graph),
        "activeDefinitions": encode_definition_set(state.active_definitions),
        "definitionDelta": delta,
    }


def decode_canonical_state(value: JsonValue) -> CanonicalState:
    """Decode one complete canonical-state tuple."""
    members = _object(value, "canonical state")
    where = "canonical state"
    raw_delta = _member(members, "definitionDelta", where)
    delta: DefinitionDelta | None = None
    if raw_delta is not None:
        delta_members = _object(raw_delta, "definition delta")
        delta = DefinitionDelta(
            proposed_definitions=decode_definition_set(
                _member(delta_members, "proposedDefinitions", "definition delta")
            )
        )
    return CanonicalState(
        graph=decode_graph(_member(members, "graph", where)),
        active_definitions=decode_definition_set(_member(members, "activeDefinitions", where)),
        revision=_int(_member(members, "revision", where), f"{where} revision"),
        definition_delta=delta,
    )


def encode_text(value: JsonValue) -> str:
    """Serialize an encoded canonical structure for storage."""
    return dumps(value)


def decode_text(text: str) -> JsonValue:
    """Parse stored text back into lossless JSON values."""
    return loads(text)


def unreadable_reason(state: CanonicalState) -> str | None:
    """Return why ``state`` could not be read back after storage, or ``None``.

    Encoding and decoding are not exact inverses by construction: a limit applied to one
    value as it enters is not the same limit applied to the whole document that later
    contains it, and the same is true of any future constraint on the stored form. Rather
    than keep two sets of rules in step by inspection, this asks the actual question —
    round-trip the state and see. A caller can then refuse the request instead of
    committing canonical state that no later read could reconstruct.
    """
    try:
        restored = decode_canonical_state(decode_text(encode_text(encode_canonical_state(state))))
    except (DecodeError, ValueError, ArithmeticError, RecursionError) as error:
        return str(error)
    if not canonical_state_equal(restored, state):
        # Decodability is not fidelity. A lossy encoding reads back cleanly and means
        # something else, which is the one failure a revision check cannot see.
        return "the stored form does not read back as the same canonical state"
    return None
