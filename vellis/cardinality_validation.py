"""Pure complete-state validation for the four local cardinality roles."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

from vellis.domain import (
    Anchor,
    AssociatedData,
    AssociatedDataTypeDefinition,
    Cardinality,
    Finding,
    FindingCode,
    GraphObject,
    Link,
    LinkTypeDefinition,
    TypeDefinition,
)
from vellis.json_pointer import append_pointer


def graph_cardinality_findings(
    objects: Iterable[GraphObject], definitions: Iterable[TypeDefinition]
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    _validate_complete_cardinality(
        tuple(objects), {value.type_key: value for value in definitions}, findings
    )
    return tuple(
        sorted(
            findings,
            key=lambda value: (
                value.code.value,
                value.path or "",
                value.type_keys,
                value.uuids,
                value.summary,
            ),
        )
    )


def _validate_complete_cardinality(
    objects: tuple[GraphObject, ...],
    definitions: Mapping[str, TypeDefinition],
    findings: list[Finding],
) -> None:
    anchors = tuple(value for value in objects if isinstance(value, Anchor))
    endpoints = tuple(value for value in objects if not isinstance(value, Link))
    data = tuple(value for value in objects if isinstance(value, AssociatedData))
    links = tuple(value for value in objects if isinstance(value, Link))
    for definition in definitions.values():
        if isinstance(definition, AssociatedDataTypeDefinition):
            _validate_data_counts(definition, anchors, data, findings)
        elif isinstance(definition, LinkTypeDefinition):
            _validate_link_counts(definition, endpoints, links, findings)


def _validate_data_counts(
    definition: AssociatedDataTypeDefinition,
    anchors: tuple[Anchor, ...],
    objects: tuple[AssociatedData, ...],
    findings: list[Finding],
) -> None:
    typed = tuple(value for value in objects if value.type_key == definition.type_key)
    for value in typed:
        _check_count(
            len(value.anchor_uuids),
            definition.anchors_per_object,
            "anchors per object",
            definition.type_key,
            value.uuid,
            findings,
        )
    counts = Counter(anchor for value in typed for anchor in value.anchor_uuids)
    for anchor in anchors:
        if anchor.type_key in definition.permitted_anchor_type_keys:
            _check_count(
                counts[anchor.uuid],
                definition.objects_per_anchor,
                "objects per anchor",
                definition.type_key,
                anchor.uuid,
                findings,
            )


def _validate_link_counts(
    definition: LinkTypeDefinition,
    endpoints: tuple[Anchor | AssociatedData, ...],
    links: tuple[Link, ...],
    findings: list[Finding],
) -> None:
    typed = tuple(value for value in links if value.type_key == definition.type_key)
    source_counts = Counter(value.source_uuid for value in typed)
    target_counts = Counter(value.target_uuid for value in typed)
    for endpoint in endpoints:
        if endpoint.type_key in definition.permitted_source_type_keys:
            _check_count(
                source_counts[endpoint.uuid],
                definition.links_per_source,
                "links per source",
                definition.type_key,
                endpoint.uuid,
                findings,
            )
        if endpoint.type_key in definition.permitted_target_type_keys:
            _check_count(
                target_counts[endpoint.uuid],
                definition.links_per_target,
                "links per target",
                definition.type_key,
                endpoint.uuid,
                findings,
            )


def _check_count(
    count: int,
    cardinality: Cardinality,
    label: str,
    type_key: str,
    uuid: str,
    findings: list[Finding],
) -> None:
    if count < cardinality.minimum or (
        cardinality.maximum is not None and count > cardinality.maximum
    ):
        findings.append(
            Finding(
                FindingCode.CARDINALITY_VIOLATION,
                f"{label} is {count}, outside its inclusive bound",
                append_pointer("/objects", uuid),
                type_keys=(type_key,),
                uuids=(uuid,),
            )
        )
