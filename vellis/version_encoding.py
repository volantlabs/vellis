"""Canonical identities and content for each VEL2 version-row family."""

from __future__ import annotations

from vellis.canonical_encoding import ABSENT, CanonicalValue, Record, row_digest
from vellis.domain import (
    GraphObject,
    PropertyDefinition,
    ScalarValue,
    SystemEnvelope,
    TypeDefinition,
)


def definition_version_encoding(
    definition: TypeDefinition, revision: int, system: SystemEnvelope
) -> tuple[Record, bytes]:
    identity = Record((("typeKey", definition.type_key), ("validFromRevision", revision)))
    bounds = _definition_bounds(definition)
    content = Record(
        (
            ("kind", definition.kind.value),
            ("description", definition.description),
            *bounds,
            ("createdRevision", system.created_revision),
            ("lastChangedRevision", system.last_changed_revision),
            ("legacyV1", ABSENT if system.legacy_v1 is None else system.legacy_v1),
        )
    )
    return identity, row_digest("definition_version", identity, content)


def permitted_type_encoding(
    type_key: str, role: str, permitted_type_key: str, revision: int
) -> tuple[Record, bytes]:
    identity = Record(
        (
            ("typeKey", type_key),
            ("role", role),
            ("permittedTypeKey", permitted_type_key),
            ("validFromRevision", revision),
        )
    )
    return identity, row_digest("definition_permitted_type", identity, Record(()))


def property_definition_encoding(
    type_key: str, definition: PropertyDefinition, revision: int
) -> tuple[Record, bytes]:
    identity = Record(
        (
            ("typeKey", type_key),
            ("propertyName", definition.name),
            ("validFromRevision", revision),
        )
    )
    content = Record(
        (
            ("description", definition.description),
            ("valueKind", definition.value_kind.value),
            ("required", definition.required),
            ("nullable", definition.nullable),
            ("minimum", _optional_scalar(definition.minimum)),
            ("maximum", _optional_scalar(definition.maximum)),
            (
                "minimumLength",
                ABSENT if definition.minimum_length is None else definition.minimum_length,
            ),
            (
                "maximumLength",
                ABSENT if definition.maximum_length is None else definition.maximum_length,
            ),
            ("pattern", ABSENT if definition.pattern is None else definition.pattern),
        )
    )
    return identity, row_digest("property_definition_version", identity, content)


def allowed_value_encoding(
    type_key: str,
    property_name: str,
    ordinal: int,
    value: ScalarValue,
    revision: int,
) -> tuple[Record, bytes]:
    identity = Record(
        (
            ("typeKey", type_key),
            ("propertyName", property_name),
            ("ordinal", ordinal),
            ("validFromRevision", revision),
        )
    )
    content = Record((("value", value),))
    return identity, row_digest("property_definition_allowed_value", identity, content)


def graph_object_version_encoding(
    value: GraphObject, revision: int, system: SystemEnvelope
) -> tuple[Record, bytes]:
    identity = Record((("uuid", value.uuid), ("validFromRevision", revision)))
    structural = _graph_structural_fields(value)
    content = Record(
        (
            ("kind", value.kind.value),
            ("typeKey", value.type_key),
            *structural,
            ("createdRevision", system.created_revision),
            ("lastChangedRevision", system.last_changed_revision),
            ("legacyV1", ABSENT if system.legacy_v1 is None else system.legacy_v1),
        )
    )
    return identity, row_digest("graph_object_version", identity, content)


def association_version_encoding(
    object_uuid: str, anchor_uuid: str, revision: int
) -> tuple[Record, bytes]:
    identity = Record(
        (
            ("objectUuid", object_uuid),
            ("anchorUuid", anchor_uuid),
            ("validFromRevision", revision),
        )
    )
    return identity, row_digest("direct_association_version", identity, Record(()))


def property_version_encoding(
    object_uuid: str,
    property_name: str,
    value: ScalarValue | None,
    declared_kind: str,
    revision: int,
) -> tuple[Record, bytes]:
    identity = Record(
        (
            ("objectUuid", object_uuid),
            ("propertyName", property_name),
            ("validFromRevision", revision),
        )
    )
    content = Record(
        (
            ("valueKind", declared_kind),
            ("value", value),
        )
    )
    return identity, row_digest("property_version", identity, content)


def _optional_scalar(value: ScalarValue | None) -> CanonicalValue:
    return ABSENT if value is None else value


def _definition_bounds(definition: TypeDefinition) -> tuple[tuple[str, CanonicalValue], ...]:
    from vellis.domain import AssociatedDataTypeDefinition, LinkTypeDefinition

    if isinstance(definition, AssociatedDataTypeDefinition):
        return (
            ("anchorsPerObjectMinimum", definition.anchors_per_object.minimum),
            (
                "anchorsPerObjectMaximum",
                ABSENT
                if definition.anchors_per_object.maximum is None
                else definition.anchors_per_object.maximum,
            ),
            ("objectsPerAnchorMinimum", definition.objects_per_anchor.minimum),
            (
                "objectsPerAnchorMaximum",
                ABSENT
                if definition.objects_per_anchor.maximum is None
                else definition.objects_per_anchor.maximum,
            ),
        )
    if isinstance(definition, LinkTypeDefinition):
        return (
            ("linksPerSourceMinimum", definition.links_per_source.minimum),
            (
                "linksPerSourceMaximum",
                ABSENT
                if definition.links_per_source.maximum is None
                else definition.links_per_source.maximum,
            ),
            ("linksPerTargetMinimum", definition.links_per_target.minimum),
            (
                "linksPerTargetMaximum",
                ABSENT
                if definition.links_per_target.maximum is None
                else definition.links_per_target.maximum,
            ),
        )
    return ()


def _graph_structural_fields(value: GraphObject) -> tuple[tuple[str, CanonicalValue], ...]:
    from vellis.domain import Anchor, AssociatedData, Link

    if isinstance(value, Anchor):
        return (("displayName", value.display_name),)
    if isinstance(value, AssociatedData):
        return ()
    assert isinstance(value, Link)
    return (("sourceUuid", value.source_uuid), ("targetUuid", value.target_uuid))
