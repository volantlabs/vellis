"""Bounded semantic reads over the current graph.

Realizes ``RTG::'Graph Query'``, ``RTG::'Graph Query Result'``, ``RTG::'Graph Query Row'``
and the bindings they carry, together with ``RTGSystem::'Query graph'`` as far as current
state reaches, carrying ``VellisRequirements::semanticQueryMeaning`` and
``VellisRequirements::querySafety``.

A query names candidate sets and the links required between them, and says which of those
names it wants back. Selection and projection are separate on purpose: a group may exist
only to constrain the answer and never appear in it. What comes back is one row per
jointly satisfying assignment, carrying exactly the requested names and nothing else.

Meaning is stated over sets, not over an evaluation order, so nothing here may depend on
the order groups were written in. The join below enumerates in declaration order because
some order is needed to walk it; the result is the same set of rows under any other.

The bound is on the whole answer rather than on a page of it. A result larger than the
caller asked for is refused entire, because a truncated answer to a question about what
exists is not a smaller true answer — it is a different, false one. Nothing here paginates
or sorts, and the model deliberately leaves both out.

Historical selection belongs to the slice that can resolve a revision. A query evaluates
current state until then, and this module does not pretend to offer the choice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from vellis.definitions import AssociatedDataTypeDefinition, GraphDefinitionSet
from vellis.graph import Anchor, AssociatedDataObject, Graph, Link, LinkEndpoint
from vellis.history import HistoricalSelection
from vellis.json_value import JsonKind, JsonValue, json_equal, json_kind, unencodable_reason
from vellis.outcomes import OperationStatus, ValidationFinding

__all__ = [
    "AnchorBinding",
    "AnchorGroup",
    "AnchorProjection",
    "AnchorUuidFilter",
    "AssociatedDataBinding",
    "AssociatedDataCondition",
    "AssociatedDataProjection",
    "DataPropertyCondition",
    "DataPropertyProjection",
    "GraphQuery",
    "GraphQueryResult",
    "GraphQueryRow",
    "LinkBinding",
    "LinkProjection",
    "LinkUuidFilter",
    "PropertyComparison",
    "RequiredLink",
    "ReturnShape",
    "ReturnProjection",
    "ReturnedProperty",
    "evaluate_query",
    "query_findings",
]


class PropertyComparison(Enum):
    """How one stored property value is compared with an expected value."""

    EQUAL = "equal"
    NOT_EQUAL = "notEqual"
    LESS_THAN = "lessThan"
    LESS_THAN_OR_EQUAL = "lessThanOrEqual"
    GREATER_THAN = "greaterThan"
    GREATER_THAN_OR_EQUAL = "greaterThanOrEqual"

    @property
    def ordered(self) -> bool:
        return self not in {PropertyComparison.EQUAL, PropertyComparison.NOT_EQUAL}


# --- What a query asks ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AnchorUuidFilter:
    """Narrows one anchor group to known anchor identities."""

    uuids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LinkUuidFilter:
    """Narrows one required link to known link identities."""

    uuids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnchorGroup:
    """A named candidate set of anchors of exactly one active type."""

    name: str
    anchor_type: str
    uuid_filter: AnchorUuidFilter | None = None


@dataclass(frozen=True, slots=True)
class DataPropertyCondition:
    """A structured comparison against one present property value."""

    property_name: str
    comparison: PropertyComparison
    expected_value: JsonValue


@dataclass(frozen=True, slots=True)
class AssociatedDataCondition:
    """A named candidate set of associated data grounded by one anchor group.

    With no property conditions this expresses existence of directly associated data of
    that type, which is why the empty case is meaningful rather than degenerate.
    """

    name: str
    anchor_group: str
    associated_data_type: str
    property_conditions: tuple[DataPropertyCondition, ...] = ()


@dataclass(frozen=True, slots=True)
class RequiredLink:
    """A required directed link of one active type between two named groups."""

    name: str
    source_group: str
    target_group: str
    link_type: str
    uuid_filter: LinkUuidFilter | None = None


@dataclass(frozen=True, slots=True)
class AnchorProjection:
    """Returns the anchor bound to one anchor group."""

    name: str
    anchor_group: str


@dataclass(frozen=True, slots=True)
class LinkProjection:
    """Returns the link bound to one required link."""

    name: str
    required_link: str


@dataclass(frozen=True, slots=True)
class AssociatedDataProjection:
    """Returns the associated-data object bound to one data condition."""

    name: str
    data_condition: str


@dataclass(frozen=True, slots=True)
class DataPropertyProjection:
    """Returns one property of the object bound to one data condition."""

    name: str
    data_condition: str
    property_name: str


ReturnProjection = (
    AnchorProjection | LinkProjection | AssociatedDataProjection | DataPropertyProjection
)


@dataclass(frozen=True, slots=True)
class ReturnShape:
    """The named bindings a query wants back."""

    projections: tuple[ReturnProjection, ...]


@dataclass(frozen=True, slots=True)
class GraphQuery:
    """A complete bounded question about the graph."""

    anchor_groups: tuple[AnchorGroup, ...]
    return_shape: ReturnShape
    maximum_rows: int
    required_links: tuple[RequiredLink, ...] = ()
    data_conditions: tuple[AssociatedDataCondition, ...] = ()
    historical_selection: HistoricalSelection | None = None
    """Absent evaluates current state; present evaluates the state it names.

    Part of the question rather than beside it, so one query object means one complete
    request whichever state it is asked of.
    """


# --- What a query answers with -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AnchorBinding:
    projection: str
    anchor: Anchor


@dataclass(frozen=True, slots=True)
class LinkBinding:
    projection: str
    link: Link


@dataclass(frozen=True, slots=True)
class AssociatedDataBinding:
    projection: str
    associated_data: AssociatedDataObject


@dataclass(frozen=True, slots=True)
class ReturnedProperty:
    """One projected property.

    ``present`` is the modeled ``[0..1]`` on the value. It cannot be inferred from the
    value itself, because a stored JSON null is a present value that reads as ``None``.
    """

    projection: str
    present: bool
    value: JsonValue = None


@dataclass(frozen=True, slots=True)
class GraphQueryRow:
    """One jointly satisfying assignment, carrying exactly the requested projections."""

    anchors: tuple[AnchorBinding, ...] = ()
    links: tuple[LinkBinding, ...] = ()
    associated_data: tuple[AssociatedDataBinding, ...] = ()
    properties: tuple[ReturnedProperty, ...] = ()


@dataclass(frozen=True, slots=True)
class GraphQueryResult:
    """The outcome of one query.

    A rejected or failed result carries no rows and no evaluated revision: a caller must
    not be able to read a partial answer out of a refusal.
    """

    status: OperationStatus
    summary: str
    query: GraphQuery
    findings: tuple[ValidationFinding, ...] = ()
    evaluated_revision: int | None = None
    rows: tuple[GraphQueryRow, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.status is OperationStatus.ACCEPTED


# --- Whether a query means anything --------------------------------------------------


def query_findings(
    query: GraphQuery, definitions: GraphDefinitionSet, graph: Graph
) -> tuple[ValidationFinding, ...]:
    """Return every reason ``query`` cannot be evaluated.

    A restriction to an identity that does not exist is a finding rather than an empty
    answer: the caller named something it believed it knew, and reporting nothing found
    would answer a question it did not ask.
    """
    findings: list[ValidationFinding] = []
    names = _name_findings(query, findings)
    _group_findings(query, definitions, graph, findings)
    _condition_findings(query, definitions, names, findings)
    _link_findings(query, definitions, graph, names, findings)
    _projection_findings(query, definitions, names, findings)
    if not query.anchor_groups:
        findings.append(ValidationFinding(summary="a query must select at least one anchor group"))
    if not query.return_shape.projections:
        findings.append(
            ValidationFinding(summary="a return shape must request at least one binding")
        )
    if query.maximum_rows < 1:
        findings.append(
            ValidationFinding(summary=f"maximum rows must be positive, not {query.maximum_rows}")
        )
    return tuple(findings)


def _named(query: GraphQuery) -> list[tuple[str, str]]:
    return [
        *((group.name, "anchor group") for group in query.anchor_groups),
        *((condition.name, "data condition") for condition in query.data_conditions),
        *((link.name, "required link") for link in query.required_links),
        *((projection.name, "projection") for projection in query.return_shape.projections),
    ]


def _name_findings(query: GraphQuery, findings: list[ValidationFinding]) -> dict[str, str]:
    """Collect the query-local namespace, reporting empty and duplicate names."""
    names: dict[str, str] = {}
    for name, role in _named(query):
        if not name:
            findings.append(ValidationFinding(summary=f"a {role} has an empty query-local name"))
            continue
        if name in names:
            findings.append(
                ValidationFinding(
                    summary=f"query-local name '{name}' is used by more than one selector"
                )
            )
            continue
        names[name] = role
    return names


def _group_findings(
    query: GraphQuery,
    definitions: GraphDefinitionSet,
    graph: Graph,
    findings: list[ValidationFinding],
) -> None:
    known_anchors = {anchor.uuid for anchor in graph.anchors}
    for group in query.anchor_groups:
        if definitions.anchor_type(group.anchor_type) is None:
            findings.append(
                ValidationFinding(
                    summary=(
                        f"anchor group '{group.name}' names '{group.anchor_type}', which is "
                        f"{_why_not(group.anchor_type, 'an active anchor type', definitions)}"
                    )
                )
            )
        _uuid_filter_findings(
            group.uuid_filter.uuids if group.uuid_filter is not None else None,
            label=f"anchor group '{group.name}'",
            known=known_anchors,
            kind="anchor",
            findings=findings,
        )


def _why_not(type_key: str, wanted: str, definitions: GraphDefinitionSet) -> str:
    """Say whether a type key is unknown or merely of the wrong family.

    Type keys share one namespace, so a key that resolves to a different kind of
    definition is present and incompatible. Reporting it as missing would send an owner
    looking for something that is right there.
    """
    if (
        definitions.anchor_type(type_key) is not None
        or definitions.associated_data_type(type_key) is not None
        or definitions.link_type(type_key) is not None
    ):
        return f"not {wanted}"
    return f"not an active definition, so it cannot be {wanted}"


def _uuid_filter_findings(
    uuids: tuple[str, ...] | None,
    *,
    label: str,
    known: set[str],
    kind: str,
    findings: list[ValidationFinding],
) -> None:
    if uuids is None:
        return
    if not uuids:
        findings.append(ValidationFinding(summary=f"{label} has an empty UUID restriction"))
        return
    seen: set[str] = set()
    for uuid in uuids:
        if uuid in seen:
            findings.append(
                ValidationFinding(summary=f"{label} restricts UUID '{uuid}' more than once")
            )
        elif uuid not in known:
            findings.append(
                ValidationFinding(summary=f"{label} restricts unknown {kind} UUID '{uuid}'")
            )
        seen.add(uuid)


def _condition_findings(
    query: GraphQuery,
    definitions: GraphDefinitionSet,
    names: dict[str, str],
    findings: list[ValidationFinding],
) -> None:
    for condition in query.data_conditions:
        if names.get(condition.anchor_group) != "anchor group":
            findings.append(
                ValidationFinding(
                    summary=(
                        f"data condition '{condition.name}' grounds on "
                        f"'{condition.anchor_group}', which is not an anchor group in this query"
                    )
                )
            )
        data_type = definitions.associated_data_type(condition.associated_data_type)
        if data_type is None:
            findings.append(
                ValidationFinding(
                    summary=(
                        f"data condition '{condition.name}' names "
                        f"'{condition.associated_data_type}', which is "
                        + _why_not(
                            condition.associated_data_type,
                            "an active associated-data type",
                            definitions,
                        )
                    )
                )
            )
            continue
        grounding = next(
            (group for group in query.anchor_groups if group.name == condition.anchor_group),
            None,
        )
        if (
            grounding is not None
            and grounding.anchor_type not in data_type.permitted_anchor_type_keys
        ):
            findings.append(
                ValidationFinding(
                    summary=(
                        f"data condition '{condition.name}' grounds on '{grounding.name}' of "
                        f"type '{grounding.anchor_type}', which "
                        f"'{condition.associated_data_type}' does not permit"
                    )
                )
            )
        for property_condition in condition.property_conditions:
            _comparison_findings(condition, property_condition, data_type, findings)


def _comparison_findings(
    condition: AssociatedDataCondition,
    property_condition: DataPropertyCondition,
    data_type: AssociatedDataTypeDefinition,
    findings: list[ValidationFinding],
) -> None:
    constraint = next(
        (
            each
            for each in data_type.property_constraints
            if each.property_name == property_condition.property_name
        ),
        None,
    )
    label = f"data condition '{condition.name}'"
    if constraint is None:
        findings.append(
            ValidationFinding(
                summary=(
                    f"{label} compares property '{property_condition.property_name}', which "
                    f"'{condition.associated_data_type}' does not define"
                )
            )
        )
        return
    if property_condition.comparison.ordered and constraint.json_kind is not JsonKind.NUMBER:
        findings.append(
            ValidationFinding(
                summary=(
                    f"{label} orders property '{property_condition.property_name}', which is "
                    f"declared {constraint.json_kind.value}; ordered comparison is valid only "
                    "for number-valued properties"
                )
            )
        )
    expected_kind = json_kind(property_condition.expected_value)
    if expected_kind is not constraint.json_kind:
        findings.append(
            ValidationFinding(
                summary=(
                    f"{label} compares property '{property_condition.property_name}' with a "
                    f"{expected_kind.value}, but it is declared {constraint.json_kind.value}"
                )
            )
        )
        return
    # Shape, range, and pattern are the model's rules for a *stored* value, and querySafety
    # does not list an out-of-range operand among its refusal grounds. Screening one here
    # would also refuse the one question that could find a non-conforming row in an
    # imported graph — turning a findable answer into an error.


def _link_findings(
    query: GraphQuery,
    definitions: GraphDefinitionSet,
    graph: Graph,
    names: dict[str, str],
    findings: list[ValidationFinding],
) -> None:
    known_links = {link.uuid for link in graph.links}
    endpoint_types = _endpoint_type_keys(query)
    for link in query.required_links:
        link_type = definitions.link_type(link.link_type)
        if link_type is None:
            findings.append(
                ValidationFinding(
                    summary=(
                        f"required link '{link.name}' names '{link.link_type}', which is "
                        f"{_why_not(link.link_type, 'an active link type', definitions)}"
                    )
                )
            )
        for role, group_name in (("source", link.source_group), ("target", link.target_group)):
            if names.get(group_name) not in {"anchor group", "data condition"}:
                findings.append(
                    ValidationFinding(
                        summary=(
                            f"required link '{link.name}' names {role} group '{group_name}', "
                            "which is not a candidate set in this query"
                        )
                    )
                )
                continue
            if link_type is None:
                continue
            permitted = (
                link_type.endpoint_constraint.permitted_source_type_keys
                if role == "source"
                else link_type.endpoint_constraint.permitted_target_type_keys
            )
            type_key = endpoint_types[group_name]
            if type_key not in permitted:
                findings.append(
                    ValidationFinding(
                        summary=(
                            f"required link '{link.name}' uses '{group_name}' of type "
                            f"'{type_key}' as its {role}, which '{link.link_type}' does not permit"
                        )
                    )
                )
        _uuid_filter_findings(
            link.uuid_filter.uuids if link.uuid_filter is not None else None,
            label=f"required link '{link.name}'",
            known=known_links,
            kind="link",
            findings=findings,
        )


def _endpoint_type_keys(query: GraphQuery) -> dict[str, str]:
    return {
        **{group.name: group.anchor_type for group in query.anchor_groups},
        **{condition.name: condition.associated_data_type for condition in query.data_conditions},
    }


def _projection_findings(
    query: GraphQuery,
    definitions: GraphDefinitionSet,
    names: dict[str, str],
    findings: list[ValidationFinding],
) -> None:
    conditions = {condition.name: condition for condition in query.data_conditions}
    for projection in query.return_shape.projections:
        label = f"projection '{projection.name}'"
        match projection:
            case AnchorProjection():
                if names.get(projection.anchor_group) != "anchor group":
                    findings.append(
                        ValidationFinding(
                            summary=(
                                f"{label} references '{projection.anchor_group}', which is not "
                                "an anchor group in this query"
                            )
                        )
                    )
            case LinkProjection():
                if names.get(projection.required_link) != "required link":
                    findings.append(
                        ValidationFinding(
                            summary=(
                                f"{label} references '{projection.required_link}', which is not "
                                "a required link in this query"
                            )
                        )
                    )
            case AssociatedDataProjection() | DataPropertyProjection():
                if names.get(projection.data_condition) != "data condition":
                    findings.append(
                        ValidationFinding(
                            summary=(
                                f"{label} references '{projection.data_condition}', which is "
                                "not a data condition in this query"
                            )
                        )
                    )
                    continue
                if isinstance(projection, DataPropertyProjection):
                    _projected_property_findings(
                        projection, conditions, definitions, label, findings
                    )


def _projected_property_findings(
    projection: DataPropertyProjection,
    conditions: dict[str, AssociatedDataCondition],
    definitions: GraphDefinitionSet,
    label: str,
    findings: list[ValidationFinding],
) -> None:
    condition = conditions[projection.data_condition]
    data_type = definitions.associated_data_type(condition.associated_data_type)
    if data_type is None:
        return
    if not any(
        each.property_name == projection.property_name for each in data_type.property_constraints
    ):
        findings.append(
            ValidationFinding(
                summary=(
                    f"{label} projects property '{projection.property_name}', which "
                    f"'{condition.associated_data_type}' does not define"
                )
            )
        )


# --- What a query returns ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Assignment:
    """One partial binding of query-local names to graph objects."""

    endpoints: dict[str, LinkEndpoint] = field(default_factory=dict)
    links: dict[str, Link] = field(default_factory=dict)


def evaluate_query(
    query: GraphQuery, definitions: GraphDefinitionSet, graph: Graph, revision: int
) -> GraphQueryResult:
    """Evaluate ``query`` against current state, or refuse it whole."""
    findings = query_findings(query, definitions, graph)
    if findings:
        return GraphQueryResult(
            status=OperationStatus.REJECTED,
            summary=f"the query was not evaluated ({len(findings)} findings)",
            findings=findings,
            query=query,
        )

    rows = _distinct_rows(query, graph)
    unreturnable = _unreturnable_reason(rows)
    if unreturnable is not None:
        return GraphQueryResult(
            status=OperationStatus.REJECTED,
            summary="the complete result could not be returned, so none of it was",
            findings=(ValidationFinding(summary=unreturnable),),
            query=query,
        )
    if len(rows) > query.maximum_rows:
        return GraphQueryResult(
            status=OperationStatus.REJECTED,
            summary=(
                f"the result has more than {query.maximum_rows} rows; it is refused whole "
                "rather than truncated"
            ),
            findings=(
                ValidationFinding(
                    summary=f"the complete result exceeds the maximum of {query.maximum_rows}"
                ),
            ),
            query=query,
        )
    return GraphQueryResult(
        status=OperationStatus.ACCEPTED,
        summary=f"{len(rows)} rows at revision {revision}",
        query=query,
        evaluated_revision=revision,
        rows=rows,
    )


def _unreturnable_reason(rows: tuple[GraphQueryRow, ...]) -> str | None:
    """Return why the complete result cannot be handed back, or ``None``.

    Screens every piece of text a row carries, because the argument for screening less
    keeps turning out to be wrong: ``AssociatedDataObject`` normalizes property values
    but not their names, and a projected link carries its endpoints' identities even when
    neither endpoint is projected. A screen with one hole in it is the same defect as no
    screen, so this walks the whole returned row rather than the parts that seemed likely.

    Nothing this system established can fail here — the write path screens what it
    stores. A graph it merely found, imported or repaired, can.
    """
    for row in rows:
        for anchor_binding in row.anchors:
            anchor = anchor_binding.anchor
            reason = _first_unencodable(
                anchor.uuid, anchor.display_name, *anchor.system_metadata.members
            )
            if reason is not None:
                return f"anchor '{anchor.uuid}' cannot be returned: {reason}"
        for data_binding in row.associated_data:
            data = data_binding.associated_data
            reason = _first_unencodable(
                data.uuid,
                *data.anchor_uuids,
                *data.properties,
                *data.system_metadata.members,
            )
            if reason is not None:
                return f"associated data '{data.uuid}' cannot be returned: {reason}"
        for link_binding in row.links:
            link = link_binding.link
            reason = _first_unencodable(
                link.uuid, link.source_uuid, link.target_uuid, *link.system_metadata.members
            )
            if reason is not None:
                return f"link '{link.uuid}' cannot be returned: {reason}"
    return None


def _first_unencodable(*values: str) -> str | None:
    return next((r for r in (unencodable_reason(each) for each in values) if r is not None), None)


def _distinct_rows(query: GraphQuery, graph: Graph) -> tuple[GraphQueryRow, ...]:
    """Project satisfying assignments, keeping identical projected tuples once.

    Stops one row past the caller's maximum. Knowing the answer is too large is all a
    refusal needs, and enumerating the rest of a join that will be thrown away is work
    the owner asked not to have done.
    """
    seen: set[tuple[object, ...]] = set()
    rows: list[GraphQueryRow] = []
    for assignment in _assignments(query, graph):
        row = _project(query, assignment)
        key = _row_identity(row)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
        if len(rows) > query.maximum_rows:
            break
    return tuple(rows)


def _assignments(query: GraphQuery, graph: Graph):
    """Enumerate every joint assignment satisfying every group, condition, and link.

    Groups are walked in declaration order because a walk needs one; the satisfying set
    does not depend on it, which is what ``semanticQueryMeaning`` means by evaluation
    strategy not changing meaning.
    """
    anchor_candidates = {
        group.name: _anchor_candidates(group, graph) for group in query.anchor_groups
    }

    def walk_groups(index: int, assignment: _Assignment):
        if index == len(query.anchor_groups):
            yield from walk_conditions(0, assignment)
            return
        group = query.anchor_groups[index]
        for anchor in anchor_candidates[group.name]:
            yield from walk_groups(
                index + 1,
                _Assignment(
                    endpoints={**assignment.endpoints, group.name: anchor}, links=assignment.links
                ),
            )

    def walk_conditions(index: int, assignment: _Assignment):
        if index == len(query.data_conditions):
            yield from walk_links(0, assignment)
            return
        condition = query.data_conditions[index]
        anchor = assignment.endpoints[condition.anchor_group]
        for data in _data_candidates(condition, anchor, graph):
            yield from walk_conditions(
                index + 1,
                _Assignment(
                    endpoints={**assignment.endpoints, condition.name: data},
                    links=assignment.links,
                ),
            )

    def walk_links(index: int, assignment: _Assignment):
        if index == len(query.required_links):
            yield assignment
            return
        required = query.required_links[index]
        source = assignment.endpoints[required.source_group]
        target = assignment.endpoints[required.target_group]
        for link in graph.links:
            if link.type_key != required.link_type:
                continue
            if link.source_uuid != source.uuid or link.target_uuid != target.uuid:
                continue
            if required.uuid_filter is not None and link.uuid not in required.uuid_filter.uuids:
                continue
            yield from walk_links(
                index + 1,
                _Assignment(
                    endpoints=assignment.endpoints,
                    links={**assignment.links, required.name: link},
                ),
            )

    yield from walk_groups(0, _Assignment())


def _anchor_candidates(group: AnchorGroup, graph: Graph) -> tuple[Anchor, ...]:
    return tuple(
        anchor
        for anchor in graph.anchors
        if anchor.type_key == group.anchor_type
        and (group.uuid_filter is None or anchor.uuid in group.uuid_filter.uuids)
    )


def _data_candidates(
    condition: AssociatedDataCondition, anchor: LinkEndpoint, graph: Graph
) -> tuple[AssociatedDataObject, ...]:
    return tuple(
        data
        for data in graph.associated_data
        if data.type_key == condition.associated_data_type
        and anchor.uuid in data.anchor_uuids
        and all(_satisfies(each, data) for each in condition.property_conditions)
    )


def _satisfies(condition: DataPropertyCondition, data: AssociatedDataObject) -> bool:
    """A comparison matches only against a present property.

    Omission is not a value, so it cannot be equal or unequal to one; that keeps an
    absent property distinct from a stored JSON null under every comparison.
    """
    if condition.property_name not in data.properties:
        return False
    stored = data.properties[condition.property_name]
    match condition.comparison:
        case PropertyComparison.EQUAL:
            return json_equal(stored, condition.expected_value)
        case PropertyComparison.NOT_EQUAL:
            return not json_equal(stored, condition.expected_value)
    # The expected value is already known to be a number: an ordered comparison against
    # anything else was refused. A stored value of another kind can only reach here from a
    # graph that does not conform to its own definitions.
    expected = condition.expected_value
    if not isinstance(stored, Decimal) or not isinstance(expected, Decimal):
        return False
    match condition.comparison:
        case PropertyComparison.LESS_THAN:
            return stored < expected
        case PropertyComparison.LESS_THAN_OR_EQUAL:
            return stored <= expected
        case PropertyComparison.GREATER_THAN:
            return stored > expected
        case _:
            return stored >= expected


def _project(query: GraphQuery, assignment: _Assignment) -> GraphQueryRow:
    anchors: list[AnchorBinding] = []
    links: list[LinkBinding] = []
    associated_data: list[AssociatedDataBinding] = []
    properties: list[ReturnedProperty] = []
    for projection in query.return_shape.projections:
        match projection:
            case AnchorProjection():
                bound = assignment.endpoints[projection.anchor_group]
                assert isinstance(bound, Anchor)
                anchors.append(AnchorBinding(projection=projection.name, anchor=bound))
            case LinkProjection():
                links.append(
                    LinkBinding(
                        projection=projection.name, link=assignment.links[projection.required_link]
                    )
                )
            case AssociatedDataProjection():
                bound = assignment.endpoints[projection.data_condition]
                assert isinstance(bound, AssociatedDataObject)
                associated_data.append(
                    AssociatedDataBinding(projection=projection.name, associated_data=bound)
                )
            case DataPropertyProjection():
                bound = assignment.endpoints[projection.data_condition]
                assert isinstance(bound, AssociatedDataObject)
                present = projection.property_name in bound.properties
                properties.append(
                    ReturnedProperty(
                        projection=projection.name,
                        present=present,
                        value=bound.properties.get(projection.property_name),
                    )
                )
    return GraphQueryRow(
        anchors=tuple(anchors),
        links=tuple(links),
        associated_data=tuple(associated_data),
        properties=tuple(properties),
    )


def _row_identity(row: GraphQueryRow) -> tuple[object, ...]:
    """Identify a row by its projected bindings, including property presence.

    Two assignments that project the same objects and the same property presence and
    values are one answer, however differently the unprojected selectors were bound.
    """
    return (
        tuple((each.projection, each.anchor.uuid) for each in row.anchors),
        tuple((each.projection, each.link.uuid) for each in row.links),
        tuple((each.projection, each.associated_data.uuid) for each in row.associated_data),
        tuple(
            (each.projection, each.present, _value_identity(each.value)) for each in row.properties
        ),
    )


def _value_identity(value: JsonValue) -> object:
    """A hashable stand-in that agrees with canonical JSON equality."""
    match value:
        case None | bool() | str():
            return (json_kind(value).value, value)
        case Decimal():
            return (JsonKind.NUMBER.value, value)
        case list():
            return (JsonKind.ARRAY.value, tuple(_value_identity(each) for each in value))
        case _:
            return (
                JsonKind.OBJECT.value,
                tuple(sorted((k, _value_identity(v)) for k, v in value.items())),
            )
