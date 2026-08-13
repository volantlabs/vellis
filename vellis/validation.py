"""Graph conformance assessment against active definitions.

Realizes the graph-facing obligations of ``VellisRequirements::graphInvariants`` and
``VellisRequirements::stringPatternValidation``.

This is the assessment capability itself. ``RTGSystem::'Assess graph conformance'``
wraps it in ``RTGSystem.check``, which adds the typed report at the current revision;
the observational record that use case also owes waits for the activity ledger.

Assessment owns no canonical state: it reads a graph and a definition set and returns
findings. A non-conforming graph is a described subject, not an execution failure.

When an object's type key resolves to no active definition of its kind, the checks that
depend on that definition are skipped: one unresolved type key reports one root cause
rather than a cascade of consequences the owner cannot act on separately.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from vellis.definitions import (
    DirectAssociationEnd,
    DirectAssociationMultiplicityConstraint,
    GraphDefinitionSet,
    LinkEnd,
    LinkMultiplicityConstraint,
    PropertyConstraint,
    RelationshipConstraint,
    relationship_label,
)
from vellis.graph import Anchor, AssociatedDataObject, GraphObject, Link, ObjectKind
from vellis.json_value import JsonValue, json_equal, json_kind, value_size
from vellis.outcomes import ValidationFinding
from vellis.patterns import PatternError, compile_pattern

__all__ = ["assess_object_neighborhood", "validate_property_value"]


@dataclass(frozen=True, slots=True)
class _ObjectNeighborhood:
    anchors: tuple[Anchor, ...]
    associated_data: tuple[AssociatedDataObject, ...]
    links: tuple[Link, ...]
    by_uuid: dict[str, GraphObject]

    @classmethod
    def from_values(cls, values: Iterable[GraphObject]) -> _ObjectNeighborhood:
        anchors: list[Anchor] = []
        data: list[AssociatedDataObject] = []
        links: list[Link] = []
        by_uuid: dict[str, GraphObject] = {}
        for value in values:
            by_uuid.setdefault(value.uuid, value)
            if isinstance(value, Anchor):
                anchors.append(value)
            elif isinstance(value, AssociatedDataObject):
                data.append(value)
            else:
                links.append(value)
        return cls(tuple(anchors), tuple(data), tuple(links), by_uuid)

    def objects(self) -> Iterable[GraphObject]:
        yield from self.anchors
        yield from self.associated_data
        yield from self.links

    def anchor(self, uuid: str) -> Anchor | None:
        value = self.by_uuid.get(uuid)
        return value if isinstance(value, Anchor) else None

    def link(self, uuid: str) -> Link | None:
        value = self.by_uuid.get(uuid)
        return value if isinstance(value, Link) else None

    def endpoint(self, uuid: str) -> Anchor | AssociatedDataObject | None:
        value = self.by_uuid.get(uuid)
        return value if isinstance(value, (Anchor, AssociatedDataObject)) else None


def assess_object_neighborhood(
    values: Iterable[GraphObject], definitions: GraphDefinitionSet
) -> tuple[ValidationFinding, ...]:
    """Assess one already-bounded object neighborhood against relevant definitions."""
    graph = _ObjectNeighborhood.from_values(values)
    findings: list[ValidationFinding] = []
    _check_unique_identity(graph, findings)
    for anchor in graph.anchors:
        _check_anchor(anchor, definitions, findings)
    for data in graph.associated_data:
        _check_associated_data(data, graph, definitions, findings)
    for link in graph.links:
        _check_link(link, graph, definitions, findings)
    for constraint in definitions.relationship_constraints:
        _check_multiplicity(constraint, graph, findings)
    return tuple(findings)


def _check_unique_identity(graph: _ObjectNeighborhood, findings: list[ValidationFinding]) -> None:
    seen: set[str] = set()
    for graph_object in graph.objects():
        uuid = graph_object.uuid
        if uuid in seen:
            findings.append(
                ValidationFinding(
                    summary=(
                        f"UUID {uuid!r} identifies more than one graph object; identity is "
                        "globally unique across object kinds"
                    ),
                    implicated_objects=(uuid,),
                )
            )
            continue
        seen.add(uuid)


def _check_anchor(
    anchor: Anchor, definitions: GraphDefinitionSet, findings: list[ValidationFinding]
) -> None:
    if not anchor.display_name:
        findings.append(
            ValidationFinding(
                summary=f"anchor {anchor.uuid!r} has an empty display name",
                implicated_objects=(anchor.uuid,),
            )
        )
    _check_type_key_resolves(anchor.uuid, anchor.type_key, ObjectKind.ANCHOR, definitions, findings)


def _check_type_key_resolves(
    uuid: str,
    type_key: str,
    kind: ObjectKind,
    definitions: GraphDefinitionSet,
    findings: list[ValidationFinding],
) -> bool:
    resolved: dict[ObjectKind, bool] = {
        ObjectKind.ANCHOR: definitions.anchor_type(type_key) is not None,
        ObjectKind.ASSOCIATED_DATA: definitions.associated_data_type(type_key) is not None,
        ObjectKind.LINK: definitions.link_type(type_key) is not None,
    }
    if resolved[kind]:
        return True
    other_kinds = [each.value for each, present in resolved.items() if present and each is not kind]
    if other_kinds:
        findings.append(
            ValidationFinding(
                summary=(
                    f"{kind.value} {uuid!r} uses type key {type_key!r}, which is active as a "
                    f"{other_kinds[0]} type; a type key never changes an object's kind"
                ),
                implicated_definitions=(f"{other_kinds[0]}Type:{type_key}",),
                implicated_objects=(uuid,),
            )
        )
    else:
        findings.append(
            ValidationFinding(
                summary=(
                    f"{kind.value} {uuid!r} uses type key {type_key!r}, which resolves to no "
                    f"active {kind.value} type definition"
                ),
                implicated_objects=(uuid,),
            )
        )
    return False


def _check_associated_data(
    data: AssociatedDataObject,
    graph: _ObjectNeighborhood,
    definitions: GraphDefinitionSet,
    findings: list[ValidationFinding],
) -> None:
    if not _check_type_key_resolves(
        data.uuid, data.type_key, ObjectKind.ASSOCIATED_DATA, definitions, findings
    ):
        return
    definition = definitions.associated_data_type(data.type_key)
    assert definition is not None
    if not data.anchor_uuids:
        findings.append(
            ValidationFinding(
                summary=(
                    f"associated data {data.uuid!r} is grounded by no anchor; at least one is "
                    "required"
                ),
                implicated_objects=(data.uuid,),
            )
        )
    seen_anchors: set[str] = set()
    for anchor_uuid in data.anchor_uuids:
        if anchor_uuid in seen_anchors:
            findings.append(
                ValidationFinding(
                    summary=(
                        f"associated data {data.uuid!r} references anchor {anchor_uuid!r} more "
                        "than once"
                    ),
                    implicated_objects=(data.uuid, anchor_uuid),
                )
            )
            continue
        seen_anchors.add(anchor_uuid)
        anchor = graph.anchor(anchor_uuid)
        if anchor is None:
            findings.append(
                ValidationFinding(
                    summary=(
                        f"associated data {data.uuid!r} references {anchor_uuid!r}, which is no "
                        "anchor owned by this graph"
                    ),
                    implicated_objects=(data.uuid, anchor_uuid),
                )
            )
            continue
        if anchor.type_key not in definition.permitted_anchor_type_keys:
            findings.append(
                ValidationFinding(
                    summary=(
                        f"associated data {data.uuid!r} of type {data.type_key!r} is grounded by "
                        f"anchor type {anchor.type_key!r}, which that type does not permit"
                    ),
                    implicated_definitions=(f"associatedDataType:{data.type_key}",),
                    implicated_objects=(data.uuid, anchor_uuid),
                )
            )
    _check_properties(data, definition.property_constraints, findings)


def _check_properties(
    data: AssociatedDataObject,
    constraints: tuple[PropertyConstraint, ...],
    findings: list[ValidationFinding],
) -> None:
    declared = {constraint.property_name: constraint for constraint in constraints}
    for name in data.properties:
        if name not in declared:
            findings.append(
                ValidationFinding(
                    summary=(
                        f"associated data {data.uuid!r} carries property {name!r}, which its "
                        f"type {data.type_key!r} does not declare"
                    ),
                    implicated_definitions=(f"associatedDataType:{data.type_key}",),
                    implicated_objects=(data.uuid,),
                )
            )
    for name, constraint in declared.items():
        label = f"property:{data.type_key}.{name}"
        if name not in data.properties:
            if constraint.required:
                findings.append(
                    ValidationFinding(
                        summary=(f"associated data {data.uuid!r} omits required property {name!r}"),
                        implicated_definitions=(label,),
                        implicated_objects=(data.uuid,),
                    )
                )
            continue
        for reason in validate_property_value(constraint, data.properties[name]):
            findings.append(
                ValidationFinding(
                    summary=f"associated data {data.uuid!r} property {name!r} {reason}",
                    implicated_definitions=(label,),
                    implicated_objects=(data.uuid,),
                )
            )


def validate_property_value(constraint: PropertyConstraint, value: JsonValue) -> tuple[str, ...]:
    """Return why a present value violates its constraint, or an empty tuple.

    Requiredness, kind, shape, range, and pattern apply conjunctively.
    """
    kind = json_kind(value)
    if kind is not constraint.json_kind:
        return (f"is {kind.value} but is declared {constraint.json_kind.value}",)
    reasons: list[str] = []
    reasons.extend(_shape_reasons(constraint, value))
    reasons.extend(_range_reasons(constraint, value))
    reasons.extend(_pattern_reasons(constraint, value))
    return tuple(reasons)


def _shape_reasons(constraint: PropertyConstraint, value: JsonValue) -> list[str]:
    shape = constraint.value_shape
    if shape is None:
        return []
    size = value_size(value)
    if size is None:
        return []
    reasons: list[str] = []
    if shape.minimum_size is not None and size < shape.minimum_size:
        reasons.append(f"has size {size}, below its minimum of {shape.minimum_size}")
    if shape.maximum_size is not None and size > shape.maximum_size:
        reasons.append(f"has size {size}, above its maximum of {shape.maximum_size}")
    return reasons


def _range_reasons(constraint: PropertyConstraint, value: JsonValue) -> list[str]:
    value_range = constraint.value_range
    if value_range is None:
        return []
    reasons: list[str] = []
    if isinstance(value, Decimal):
        lower, upper = value_range.lower_bound, value_range.upper_bound
        if isinstance(lower, Decimal) and value < lower:
            reasons.append(f"is below its inclusive lower bound {lower}")
        if isinstance(upper, Decimal) and value > upper:
            reasons.append(f"is above its inclusive upper bound {upper}")
    if value_range.permitted_values and not any(
        json_equal(value, permitted) for permitted in value_range.permitted_values
    ):
        reasons.append("is not one of its permitted values")
    return reasons


def _pattern_reasons(constraint: PropertyConstraint, value: JsonValue) -> list[str]:
    pattern = constraint.pattern
    if pattern is None or not isinstance(value, str):
        return []
    try:
        compiled = compile_pattern(pattern.expression)
    except PatternError as error:
        return [f"cannot be validated because its pattern is invalid: {error}"]
    if compiled.matches(value):
        return []
    return [f"does not match its whole-string pattern {pattern.expression!r}"]


def _check_link(
    link: Link,
    graph: _ObjectNeighborhood,
    definitions: GraphDefinitionSet,
    findings: list[ValidationFinding],
) -> None:
    if not _check_type_key_resolves(
        link.uuid, link.type_key, ObjectKind.LINK, definitions, findings
    ):
        return
    definition = definitions.link_type(link.type_key)
    assert definition is not None
    constraint = definition.endpoint_constraint
    ends = (
        ("source", link.source_uuid, constraint.permitted_source_type_keys),
        ("target", link.target_uuid, constraint.permitted_target_type_keys),
    )
    for end_name, uuid, permitted in ends:
        endpoint = graph.endpoint(uuid)
        if endpoint is None:
            detail = (
                "a link, which is never an endpoint"
                if graph.link(uuid) is not None
                else "no anchor or associated data owned by this graph"
            )
            findings.append(
                ValidationFinding(
                    summary=f"link {link.uuid!r} {end_name} {uuid!r} resolves to {detail}",
                    implicated_objects=(link.uuid, uuid),
                )
            )
            continue
        if endpoint.type_key not in permitted:
            findings.append(
                ValidationFinding(
                    summary=(
                        f"link {link.uuid!r} of type {link.type_key!r} has {end_name} type "
                        f"{endpoint.type_key!r}, which its endpoint constraint does not permit"
                    ),
                    implicated_definitions=(f"endpointConstraint:{link.type_key}",),
                    implicated_objects=(link.uuid, uuid),
                )
            )


def _within_bounds(count: int, constraint: RelationshipConstraint) -> bool:
    if count < constraint.lower_bound:
        return False
    return constraint.upper_bound is None or count <= constraint.upper_bound


def _bounds_text(constraint: RelationshipConstraint) -> str:
    upper = "*" if constraint.upper_bound is None else str(constraint.upper_bound)
    return f"{constraint.lower_bound}..{upper}"


def _check_multiplicity(
    constraint: RelationshipConstraint,
    graph: _ObjectNeighborhood,
    findings: list[ValidationFinding],
) -> None:
    if isinstance(constraint, LinkMultiplicityConstraint):
        _check_link_multiplicity(constraint, graph, findings)
    else:
        _check_direct_association_multiplicity(constraint, graph, findings)


def _check_link_multiplicity(
    constraint: LinkMultiplicityConstraint,
    graph: _ObjectNeighborhood,
    findings: list[ValidationFinding],
) -> None:
    label = relationship_label(constraint)
    constrained = frozenset(constraint.constrained_endpoint_type_keys)
    opposite = frozenset(constraint.opposite_endpoint_type_keys)
    at_source = constraint.constrained_end is LinkEnd.SOURCE
    for endpoint in (*graph.anchors, *graph.associated_data):
        if endpoint.type_key not in constrained:
            continue
        count = 0
        for link in graph.links:
            if link.type_key != constraint.link_type_key:
                continue
            near, far = (
                (link.source_uuid, link.target_uuid)
                if at_source
                else (link.target_uuid, link.source_uuid)
            )
            if near != endpoint.uuid:
                continue
            other = graph.endpoint(far)
            if other is not None and other.type_key in opposite:
                count += 1
        if not _within_bounds(count, constraint):
            findings.append(
                ValidationFinding(
                    summary=(
                        f"{endpoint.type_key} {endpoint.uuid!r} participates in {count} "
                        f"{constraint.link_type_key!r} links at its "
                        f"{constraint.constrained_end.value} end, outside "
                        f"{_bounds_text(constraint)}"
                    ),
                    implicated_definitions=(label,),
                    implicated_objects=(endpoint.uuid,),
                )
            )


def _check_direct_association_multiplicity(
    constraint: DirectAssociationMultiplicityConstraint,
    graph: _ObjectNeighborhood,
    findings: list[ValidationFinding],
) -> None:
    label = relationship_label(constraint)
    anchor_types = frozenset(constraint.anchor_type_keys)
    data_types = frozenset(constraint.associated_data_type_keys)
    if constraint.constrained_end is DirectAssociationEnd.ANCHOR:
        for anchor in graph.anchors:
            if anchor.type_key not in anchor_types:
                continue
            count = sum(
                1
                for data in graph.associated_data
                if data.type_key in data_types and anchor.uuid in data.anchor_uuids
            )
            if not _within_bounds(count, constraint):
                findings.append(
                    ValidationFinding(
                        summary=(
                            f"anchor {anchor.uuid!r} is directly associated with {count} "
                            f"matching data objects, outside {_bounds_text(constraint)}"
                        ),
                        implicated_definitions=(label,),
                        implicated_objects=(anchor.uuid,),
                    )
                )
        return
    for data in graph.associated_data:
        if data.type_key not in data_types:
            continue
        count = 0
        for anchor_uuid in frozenset(data.anchor_uuids):
            anchor = graph.anchor(anchor_uuid)
            if anchor is not None and anchor.type_key in anchor_types:
                count += 1
        if not _within_bounds(count, constraint):
            findings.append(
                ValidationFinding(
                    summary=(
                        f"associated data {data.uuid!r} is directly associated with {count} "
                        f"matching anchors, outside {_bounds_text(constraint)}"
                    ),
                    implicated_definitions=(label,),
                    implicated_objects=(data.uuid,),
                )
            )
