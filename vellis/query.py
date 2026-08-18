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
the order groups were written in. Evaluation asks a realization-neutral candidate index
for identity/type, direct-association, and directed-link joins, then applies property
comparisons. An in-memory graph supplies hash indexes; the selected durable realization
supplies database indexes. The join enumerates in declaration order because some order is
needed to walk it; the result is the same set of rows under any other.

The bound is on the whole answer rather than on a page of it. A result larger than the
caller asked for is refused entire, because a truncated answer to a question about what
exists is not a smaller true answer — it is a different, false one. Nothing here paginates
or sorts, and the model deliberately leaves both out.

Historical selection belongs to the slice that can resolve a revision. A query evaluates
current state until then, and this module does not pretend to offer the choice.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Protocol

from vellis.definitions import AssociatedDataTypeDefinition, GraphDefinitionSet
from vellis.graph import Anchor, AssociatedDataObject, Link, LinkEndpoint
from vellis.history import HistoricalSelection
from vellis.json_value import (
    MAXIMUM_STORED_INTEGER_EXPONENT,
    JsonKind,
    JsonValue,
    json_equal,
    json_kind,
    unencodable_reason,
)
from vellis.outcomes import OperationStatus, ValidationFinding

__all__ = [
    "AggregateBinding",
    "AggregationOperator",
    "AnchorBinding",
    "AnchorGroup",
    "AnchorProjection",
    "AnchorUuidFilter",
    "AssociatedDataBinding",
    "AssociatedDataCondition",
    "AssociatedDataProjection",
    "DataPropertyCondition",
    "DataPropertyProjection",
    "EvaluatedStateScope",
    "GraphQuery",
    "GraphQueryResult",
    "GraphQueryRow",
    "LinkBinding",
    "LinkProjection",
    "LinkUuidFilter",
    "PropertyComparison",
    "QueryAggregation",
    "QueryCandidateIndex",
    "RequiredLink",
    "ReturnShape",
    "ReturnProjection",
    "ReturnedProperty",
    "evaluate_indexed_query",
    "indexed_query_findings",
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


# The kinds that carry an order of their own. A number orders by exact mathematical value
# and a string by exact code-point sequence, which is the basis equality already uses, so
# neither introduces a second notion of what a stored value is. The rest are left out
# because any order over them would have to be invented here: null and Boolean have too
# few values to be worth one, and an array or object would need a rule about members that
# the model does not state.
ORDERABLE_KINDS = frozenset({JsonKind.NUMBER, JsonKind.STRING})


class EvaluatedStateScope(Enum):
    CURRENT = "current"
    PROSPECTIVE = "prospective"
    HISTORICAL = "historical"


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
    """A named candidate set of anchors of one or more active types.

    Several types because one question is often about work that takes several
    shapes — what is due, whoever owes it — and asking it once is the difference
    between a graph and a pile of separate indexes.
    """

    name: str
    anchor_types: tuple[str, ...]
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


class AggregationOperator(Enum):
    """What arithmetic an aggregation performs over matching objects."""

    COUNT = "count"
    SUM = "sum"
    MINIMUM = "minimum"
    MAXIMUM = "maximum"

    @property
    def needs_property(self) -> bool:
        return self is not AggregationOperator.COUNT

    @property
    def orderable_kinds(self) -> frozenset[JsonKind]:
        """The property kinds this operator can work on."""
        if self is AggregationOperator.SUM:
            return frozenset({JsonKind.NUMBER})
        return ORDERABLE_KINDS


@dataclass(frozen=True, slots=True)
class QueryAggregation:
    """One arithmetic answer about a data condition's matching objects.

    Returned instead of the objects. The point is not to save a round trip but to
    save the caller from computing it themselves off a projection, where identical
    tuples collapse and the arithmetic comes out wrong in a way nothing signals.
    """

    name: str
    operator: AggregationOperator
    data_condition: str
    property_name: str | None = None


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
    aggregations: tuple[QueryAggregation, ...] = ()
    required_links: tuple[RequiredLink, ...] = ()
    data_conditions: tuple[AssociatedDataCondition, ...] = ()
    historical_selection: HistoricalSelection | None = None
    state_scope: EvaluatedStateScope = EvaluatedStateScope.CURRENT
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
class AggregateBinding:
    """One aggregation's answer.

    ``present`` carries the modeled ``[0..1]``: a count is always present and zero
    when nothing matched, while a sum, minimum, or maximum is absent when no match
    carried the property, because zero would be a different claim from none.
    """

    aggregation: str
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
    aggregates: tuple[AggregateBinding, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.status is OperationStatus.ACCEPTED


class QueryValidationIndex(Protocol):
    """Bounded identity checks needed before SQL evaluation."""

    def known_anchor_uuids(self, anchor_type: str, uuids: tuple[str, ...]) -> set[str]: ...

    def known_link_uuids(self, link_type: str, uuids: tuple[str, ...]) -> set[str]: ...


class QueryCandidateIndex(QueryValidationIndex, Protocol):
    """Candidate joins used only by an explicitly selected evaluation realization."""

    def anchor_candidates(
        self, group: AnchorGroup, allowed_uuids: frozenset[str] | None = None
    ) -> tuple[Anchor, ...]: ...

    def associated_data_candidates(
        self,
        associated_data_type: str,
        anchor_uuid: str,
        allowed_uuids: frozenset[str] | None = None,
    ) -> tuple[AssociatedDataObject, ...]: ...

    def link_candidates(
        self, required: RequiredLink, source_uuid: str, target_uuid: str
    ) -> tuple[Link, ...]: ...

    def link_endpoint_pairs(self, required: RequiredLink) -> frozenset[tuple[str, str]]: ...


# --- Whether a query means anything --------------------------------------------------


def indexed_query_findings(
    query: GraphQuery, definitions: GraphDefinitionSet, index: QueryValidationIndex
) -> tuple[ValidationFinding, ...]:
    """Validate query meaning with a realization-provided identity index."""
    return _query_findings(query, definitions, index)


def _query_findings(
    query: GraphQuery, definitions: GraphDefinitionSet, index: QueryValidationIndex
) -> tuple[ValidationFinding, ...]:
    findings: list[ValidationFinding] = []
    names = _name_findings(query, findings)
    _group_findings(query, definitions, index, findings)
    _condition_findings(query, definitions, names, findings)
    _link_findings(query, definitions, index, names, findings)
    _projection_findings(query, definitions, names, findings)
    _aggregation_findings(query, definitions, findings)
    if not query.anchor_groups:
        findings.append(ValidationFinding(summary="a query must select at least one anchor group"))
    if not query.return_shape.projections and not query.aggregations:
        findings.append(
            ValidationFinding(
                summary="a query must request at least one binding or one aggregation"
            )
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
        *((aggregation.name, "aggregation") for aggregation in query.aggregations),
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
    index: QueryValidationIndex,
    findings: list[ValidationFinding],
) -> None:
    for group in query.anchor_groups:
        if not group.anchor_types:
            findings.append(
                ValidationFinding(summary=f"anchor group '{group.name}' names no anchor type")
            )
        for type_key in _repeats(group.anchor_types):
            findings.append(
                ValidationFinding(
                    summary=f"anchor group '{group.name}' names '{type_key}' more than once"
                )
            )
        for type_key in group.anchor_types:
            if definitions.anchor_type(type_key) is None:
                findings.append(
                    ValidationFinding(
                        summary=(
                            f"anchor group '{group.name}' names '{type_key}', which is "
                            f"{_why_not(type_key, 'an active anchor type', definitions)}"
                        )
                    )
                )
        known: set[str] = set()
        if group.uuid_filter is not None:
            for type_key in group.anchor_types:
                known |= set(index.known_anchor_uuids(type_key, group.uuid_filter.uuids))
        _uuid_filter_findings(
            group.uuid_filter.uuids if group.uuid_filter is not None else None,
            label=f"anchor group '{group.name}'",
            known=known,
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
        if grounding is not None:
            for type_key in grounding.anchor_types:
                if type_key not in data_type.permitted_anchor_type_keys:
                    findings.append(
                        ValidationFinding(
                            summary=(
                                f"data condition '{condition.name}' grounds on "
                                f"'{grounding.name}' of type '{type_key}', which "
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
    if property_condition.comparison.ordered and constraint.json_kind not in ORDERABLE_KINDS:
        findings.append(
            ValidationFinding(
                summary=(
                    f"{label} orders property '{property_condition.property_name}', which is "
                    f"declared {constraint.json_kind.value}; ordered comparison is valid only "
                    "for number-valued and string-valued properties"
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
    index: QueryValidationIndex,
    names: dict[str, str],
    findings: list[ValidationFinding],
) -> None:
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
            # Every type the group names has to be permitted here. Accepting a
            # group because one of its types fits would make the link silently
            # mean less than the group says, which is worse than a refusal.
            for type_key in endpoint_types[group_name]:
                if type_key not in permitted:
                    findings.append(
                        ValidationFinding(
                            summary=(
                                f"required link '{link.name}' uses '{group_name}' of type "
                                f"'{type_key}' as its {role}, which '{link.link_type}' "
                                "does not permit"
                            )
                        )
                    )
        _uuid_filter_findings(
            link.uuid_filter.uuids if link.uuid_filter is not None else None,
            label=f"required link '{link.name}'",
            known=(
                set()
                if link.uuid_filter is None
                else index.known_link_uuids(link.link_type, link.uuid_filter.uuids)
            ),
            kind="link",
            findings=findings,
        )


def _aggregation_findings(
    query: GraphQuery,
    definitions: GraphDefinitionSet,
    findings: list[ValidationFinding],
) -> None:
    """Report why an aggregation cannot be computed, before any of it is."""
    conditions = {condition.name: condition for condition in query.data_conditions}
    for aggregation in query.aggregations:
        label = f"aggregation '{aggregation.name}'"
        condition = conditions.get(aggregation.data_condition)
        if condition is None:
            findings.append(
                ValidationFinding(
                    summary=(
                        f"{label} names '{aggregation.data_condition}', which is not a data "
                        "condition in this query"
                    )
                )
            )
            continue
        if not aggregation.operator.needs_property:
            if aggregation.property_name is not None:
                findings.append(
                    ValidationFinding(summary=f"{label} counts matches, so it names no property")
                )
            continue
        if aggregation.property_name is None:
            findings.append(
                ValidationFinding(
                    summary=f"{label} applies {aggregation.operator.value} but names no property"
                )
            )
            continue
        data_type = definitions.associated_data_type(condition.associated_data_type)
        if data_type is None:
            continue
        constraint = next(
            (
                rule
                for rule in data_type.property_constraints
                if rule.property_name == aggregation.property_name
            ),
            None,
        )
        if constraint is None:
            findings.append(
                ValidationFinding(
                    summary=(
                        f"{label} applies to property '{aggregation.property_name}', which "
                        f"'{condition.associated_data_type}' does not define"
                    )
                )
            )
            continue
        if constraint.json_kind not in aggregation.operator.orderable_kinds:
            kinds = aggregation.operator.orderable_kinds
            permitted = ", ".join(sorted(kind.value for kind in kinds))
            findings.append(
                ValidationFinding(
                    summary=(
                        f"{label} applies {aggregation.operator.value} to property "
                        f"'{aggregation.property_name}', which is declared "
                        f"{constraint.json_kind.value}; {aggregation.operator.value} applies "
                        f"only to {permitted} properties"
                    )
                )
            )


def _endpoint_type_keys(query: GraphQuery) -> dict[str, tuple[str, ...]]:
    """Return the types each candidate set may bind, by query-local name."""
    return {
        **{group.name: group.anchor_types for group in query.anchor_groups},
        **{
            condition.name: (condition.associated_data_type,) for condition in query.data_conditions
        },
    }


def _repeats(values: Sequence[str]) -> tuple[str, ...]:
    """Return the values that appear more than once, each once, in first order."""
    seen: set[str] = set()
    repeated: list[str] = []
    for value in values:
        if value in seen and value not in repeated:
            repeated.append(value)
        seen.add(value)
    return tuple(repeated)


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


def evaluate_indexed_query(
    query: GraphQuery,
    definitions: GraphDefinitionSet,
    index: QueryCandidateIndex,
    revision: int,
) -> GraphQueryResult:
    """Evaluate with candidates supplied by identity/type/relationship indexes."""
    findings = _query_findings(query, definitions, index)
    if findings:
        return GraphQueryResult(
            status=OperationStatus.REJECTED,
            summary=f"the query was not evaluated ({len(findings)} findings)",
            findings=findings,
            query=query,
        )

    rows, matches = _walk(query, index)
    over_selection = next(
        (
            (name, len(objects))
            for name, objects in matches.items()
            if len(objects) > query.maximum_rows
        ),
        None,
    )
    if over_selection is not None:
        name, _ = over_selection
        # The bound means the same work it means for a projected result. Returning one
        # number is not a reason to have read a population the caller did not permit.
        return GraphQueryResult(
            status=OperationStatus.REJECTED,
            summary=(
                f"the selection aggregated by '{name}' has more than {query.maximum_rows} "
                "matches; it is refused whole rather than aggregated in part"
            ),
            findings=(
                ValidationFinding(
                    summary=(f"the matches of '{name}' exceed the maximum of {query.maximum_rows}")
                ),
            ),
            query=query,
        )
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
    try:
        aggregates = _aggregates(query, definitions, matches)
    except ArithmeticError as error:
        return GraphQueryResult(
            status=OperationStatus.REJECTED,
            summary="the complete aggregate could not be returned, so none of it was",
            findings=(ValidationFinding(summary=str(error)),),
            query=query,
        )
    counts = []
    if query.return_shape.projections:
        counts.append(f"{len(rows)} rows")
    if aggregates:
        counts.append(f"{len(aggregates)} aggregates")
    return GraphQueryResult(
        status=OperationStatus.ACCEPTED,
        summary=f"{' and '.join(counts)} at revision {revision}",
        query=query,
        evaluated_revision=revision,
        rows=rows,
        aggregates=aggregates,
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


def _walk(
    query: GraphQuery, index: QueryCandidateIndex
) -> tuple[tuple[GraphQueryRow, ...], dict[str, dict[str, AssociatedDataObject]]]:
    """Enumerate satisfying assignments once, collecting rows and aggregated matches.

    Rows keep identical projected tuples once, as they always have. Matches keep each
    object once by identity, which is a different thing and is the whole reason an
    aggregate exists: two transactions of the same amount in the same category are one
    row and two matches, and only the second reading answers "how much".

    Stops one past the maximum on whichever the query actually asked for. Knowing an
    answer is too large is all a refusal needs.
    """
    aggregated = {aggregation.data_condition for aggregation in query.aggregations}
    matches: dict[str, dict[str, AssociatedDataObject]] = {name: {} for name in aggregated}
    wants_rows = bool(query.return_shape.projections)
    seen: set[tuple[object, ...]] = set()
    rows: list[GraphQueryRow] = []
    for assignment in _assignments(query, index):
        if wants_rows and len(rows) <= query.maximum_rows:
            row = _project(query, assignment)
            key = semantic_row_identity(row)
            if key not in seen:
                seen.add(key)
                rows.append(row)
        for name in aggregated:
            bound = assignment.endpoints.get(name)
            if isinstance(bound, AssociatedDataObject):
                matches[name][bound.uuid] = bound
        if any(len(objects) > query.maximum_rows for objects in matches.values()):
            break
        if wants_rows and len(rows) > query.maximum_rows:
            break
    return tuple(rows), matches


def _aggregates(
    query: GraphQuery,
    definitions: GraphDefinitionSet,
    matches: dict[str, dict[str, AssociatedDataObject]],
) -> tuple[AggregateBinding, ...]:
    """Compute each aggregation over the objects its condition matched."""
    conditions = {condition.name: condition for condition in query.data_conditions}
    bindings: list[AggregateBinding] = []
    for aggregation in query.aggregations:
        objects = tuple(matches.get(aggregation.data_condition, {}).values())
        if aggregation.operator is AggregationOperator.COUNT:
            bindings.append(
                AggregateBinding(
                    aggregation=aggregation.name, present=True, value=Decimal(len(objects))
                )
            )
            continue
        condition = conditions[aggregation.data_condition]
        data_type = definitions.associated_data_type(condition.associated_data_type)
        declared = next(
            (
                rule.json_kind
                for rule in (data_type.property_constraints if data_type else ())
                if rule.property_name == aggregation.property_name
            ),
            None,
        )
        # Only values of the declared kind take part. A conforming graph has no others,
        # and on one that does not conform this refuses to invent an order between kinds.
        values = [
            value
            for each in objects
            if (value := each.properties.get(aggregation.property_name or "")) is not None
            or aggregation.property_name in each.properties
            if json_kind(value) is declared
        ]
        if not values:
            bindings.append(AggregateBinding(aggregation=aggregation.name, present=False))
            continue
        bindings.append(
            AggregateBinding(
                aggregation=aggregation.name,
                present=True,
                value=_aggregate_value(aggregation.operator, values),
            )
        )
    return tuple(bindings)


def _aggregate_value(operator: AggregationOperator, values: list[JsonValue]) -> JsonValue:
    """Reduce values of one kind, ordering exactly as an ordered comparison does."""
    if operator is AggregationOperator.SUM:
        return _exact_decimal_sum(values)
    ordered = sorted(values)  # pyright: ignore[reportArgumentType]
    return ordered[0] if operator is AggregationOperator.MINIMUM else ordered[-1]


@dataclass(slots=True)
class _ExactDecimalAccumulator:
    """Retain only coefficient places needed by one exact scalar sum."""

    coefficients: dict[int, int] = field(default_factory=dict)
    input_digits: int = 0
    count: int = 0

    def add(self, value: Decimal) -> None:
        shape = value.as_tuple()
        assert isinstance(shape.exponent, int)
        coefficient = 0
        for digit in shape.digits:
            coefficient = coefficient * 10 + digit
        self.input_digits += len(shape.digits)
        exponent = shape.exponent
        while coefficient and coefficient % 10 == 0:
            coefficient //= 10
            exponent += 1
        signed = -coefficient if shape.sign else coefficient
        self.coefficients[exponent] = self.coefficients.get(exponent, 0) + signed
        self.count += 1

    def result(self) -> Decimal:
        if not self.count:
            return Decimal(0)
        return _exact_decimal_result(self.coefficients, self.input_digits, self.count)


def _exact_decimal_sum(values: Sequence[JsonValue]) -> Decimal:
    """Add finite decimals with context-free integer coefficient arithmetic."""
    accumulator = _ExactDecimalAccumulator()
    for value in values:
        assert isinstance(value, Decimal)
        accumulator.add(value)
    return accumulator.result()


def _exact_decimal_result(coefficients: dict[int, int], input_digits: int, count: int) -> Decimal:
    terms: list[tuple[int, int]] = []
    for exponent, coefficient in coefficients.items():
        while coefficient and coefficient % 10 == 0:
            coefficient //= 10
            exponent += 1
        if coefficient:
            terms.append((exponent, coefficient))
    if not terms:
        return Decimal(0)
    lowest_place = min(exponent for exponent, _ in terms)
    highest_place = max(
        exponent + _integer_digit_count(coefficient) - 1 for exponent, coefficient in terms
    )
    permitted_span = max(MAXIMUM_STORED_INTEGER_EXPONENT, input_digits + len(str(count)))
    if highest_place - lowest_place + 1 > permitted_span:
        raise ArithmeticError(
            "the exact aggregate sum would require expanding compact numeric inputs "
            "beyond the finite result materialization bound"
        )
    total = sum(coefficient * 10 ** (exponent - lowest_place) for exponent, coefficient in terms)
    if total == 0:
        return Decimal(0)
    while total % 10 == 0:
        total //= 10
        lowest_place += 1
    sign = int(total < 0)
    remaining = abs(total)
    digits: list[int] = []
    while remaining:
        remaining, digit = divmod(remaining, 10)
        digits.append(digit)
    coefficient_text = "".join(str(digit) for digit in reversed(digits))
    try:
        return Decimal(f"{'-' if sign else ''}{coefficient_text}e{lowest_place}")
    except InvalidOperation as error:
        raise ArithmeticError(
            "the exact aggregate sum is outside the finite decimal result range"
        ) from error


def _integer_digit_count(value: int) -> int:
    """Count coefficient digits without the interpreter's integer-to-text limit."""
    remaining = abs(value)
    digits = 1
    while remaining >= 10:
        remaining //= 10
        digits += 1
    return digits


def _distinct_rows(query: GraphQuery, index: QueryCandidateIndex) -> tuple[GraphQueryRow, ...]:
    """Project satisfying assignments, keeping identical projected tuples once.

    Stops one row past the caller's maximum. Knowing the answer is too large is all a
    refusal needs, and enumerating the rest of a join that will be thrown away is work
    the owner asked not to have done.
    """
    seen: set[tuple[object, ...]] = set()
    rows: list[GraphQueryRow] = []
    for assignment in _assignments(query, index):
        row = _project(query, assignment)
        key = semantic_row_identity(row)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
        if len(rows) > query.maximum_rows:
            break
    return tuple(rows)


def _assignments(query: GraphQuery, index: QueryCandidateIndex):
    """Enumerate result-bearing assignments without multiplying irrelevant components.

    A disconnected component with neither a projection nor an aggregation is an
    existence condition: zero satisfying assignments removes every result, while one or
    a million have the same effect. Result-bearing components are deduplicated by their
    own projected tuple and aggregated object identities before they are combined, so
    variation that can change neither answer cannot manufacture repeated global
    assignments either.
    """
    result_components: list[GraphQuery] = []
    for names in _selector_components(query):
        component = _component_query(query, names)
        if not component.return_shape.projections and not component.aggregations:
            if next(_component_assignments(component, index), None) is None:
                return
            continue
        # Establish emptiness once before combining components. Without this check an
        # empty later component would make an earlier one run to exhaustion without ever
        # yielding an assignment to _walk, where the caller's bound is enforced.
        if next(_component_assignments(component, index), None) is None:
            return
        result_components.append(component)

    def combine(position: int, assignment: _Assignment):
        if position == len(result_components):
            yield assignment
            return
        # This is deliberately a fresh lazy stream for each outer assignment. Caching a
        # whole component would make an over-bound aggregation consume and retain its
        # entire population before _walk could refuse one past the caller's maximum.
        for component_assignment in _distinct_component_assignments(
            result_components[position], index
        ):
            yield from combine(
                position + 1,
                _Assignment(
                    endpoints={**assignment.endpoints, **component_assignment.endpoints},
                    links={**assignment.links, **component_assignment.links},
                ),
            )

    yield from combine(0, _Assignment())


def _selector_components(query: GraphQuery) -> tuple[frozenset[str], ...]:
    """Return connected endpoint-selector components in declaration order."""
    names = [
        *(group.name for group in query.anchor_groups),
        *(condition.name for condition in query.data_conditions),
    ]
    adjacent = {name: set[str]() for name in names}
    for condition in query.data_conditions:
        adjacent[condition.name].add(condition.anchor_group)
        adjacent[condition.anchor_group].add(condition.name)
    for required in query.required_links:
        adjacent[required.source_group].add(required.target_group)
        adjacent[required.target_group].add(required.source_group)

    components: list[frozenset[str]] = []
    visited: set[str] = set()
    for name in names:
        if name in visited:
            continue
        pending = [name]
        members: set[str] = set()
        while pending:
            current = pending.pop()
            if current in members:
                continue
            members.add(current)
            pending.extend(adjacent[current] - members)
        visited.update(members)
        components.append(frozenset(members))
    return tuple(components)


def _component_query(query: GraphQuery, names: frozenset[str]) -> GraphQuery:
    """Project one selector component into a self-contained internal query."""
    links = tuple(
        required
        for required in query.required_links
        if required.source_group in names and required.target_group in names
    )
    link_names = {required.name for required in links}
    projections = tuple(
        projection
        for projection in query.return_shape.projections
        if (
            isinstance(projection, AnchorProjection)
            and projection.anchor_group in names
            or isinstance(projection, (AssociatedDataProjection, DataPropertyProjection))
            and projection.data_condition in names
            or isinstance(projection, LinkProjection)
            and projection.required_link in link_names
        )
    )
    return GraphQuery(
        anchor_groups=tuple(group for group in query.anchor_groups if group.name in names),
        data_conditions=tuple(
            condition for condition in query.data_conditions if condition.name in names
        ),
        required_links=links,
        return_shape=ReturnShape(projections=projections),
        aggregations=tuple(
            aggregation for aggregation in query.aggregations if aggregation.data_condition in names
        ),
        maximum_rows=query.maximum_rows,
        historical_selection=query.historical_selection,
        state_scope=query.state_scope,
    )


def _distinct_component_assignments(
    query: GraphQuery, index: QueryCandidateIndex
) -> Iterator[_Assignment]:
    """Keep assignments that can change a projection or aggregated population."""
    aggregated_conditions = tuple(
        dict.fromkeys(aggregation.data_condition for aggregation in query.aggregations)
    )
    seen: set[tuple[object, ...]] = set()
    for assignment in _component_assignments(query, index):
        key = (
            semantic_row_identity(_project(query, assignment)),
            tuple(
                (
                    name,
                    bound.uuid if (bound := assignment.endpoints.get(name)) is not None else None,
                )
                for name in aggregated_conditions
            ),
        )
        if key in seen:
            continue
        seen.add(key)
        yield assignment


def _component_assignments(query: GraphQuery, index: QueryCandidateIndex):
    """Enumerate satisfying assignments within one connected selector component."""
    link_pair_maps: dict[str, tuple[dict[str, set[str]], dict[str, set[str]]]] = {}
    allowed_by_endpoint: dict[str, frozenset[str]] = {}
    for required in query.required_links:
        targets_by_source: dict[str, set[str]] = {}
        sources_by_target: dict[str, set[str]] = {}
        for source_uuid, target_uuid in index.link_endpoint_pairs(required):
            targets_by_source.setdefault(source_uuid, set()).add(target_uuid)
            sources_by_target.setdefault(target_uuid, set()).add(source_uuid)
        link_pair_maps[required.name] = (targets_by_source, sources_by_target)
        for group_name, permitted in (
            (required.source_group, frozenset(targets_by_source)),
            (required.target_group, frozenset(sources_by_target)),
        ):
            prior = allowed_by_endpoint.get(group_name)
            allowed_by_endpoint[group_name] = permitted if prior is None else prior & permitted
    anchor_candidates = {
        group.name: index.anchor_candidates(group, allowed_by_endpoint.get(group.name))
        for group in query.anchor_groups
    }

    def walk_groups(position: int, assignment: _Assignment):
        if position == len(query.anchor_groups):
            yield from walk_conditions(0, assignment)
            return
        group = query.anchor_groups[position]
        permitted = {anchor.uuid for anchor in anchor_candidates[group.name]}
        for required in query.required_links:
            pair_maps = link_pair_maps.get(required.name)
            if pair_maps is None:
                continue
            targets_by_source, sources_by_target = pair_maps
            if (
                required.target_group == group.name
                and required.source_group in assignment.endpoints
            ):
                source_uuid = assignment.endpoints[required.source_group].uuid
                permitted &= targets_by_source.get(source_uuid, set())
            elif (
                required.source_group == group.name
                and required.target_group in assignment.endpoints
            ):
                target_uuid = assignment.endpoints[required.target_group].uuid
                permitted &= sources_by_target.get(target_uuid, set())
        for anchor in anchor_candidates[group.name]:
            if anchor.uuid not in permitted:
                continue
            yield from walk_groups(
                position + 1,
                _Assignment(
                    endpoints={**assignment.endpoints, group.name: anchor}, links=assignment.links
                ),
            )

    def walk_conditions(position: int, assignment: _Assignment):
        if position == len(query.data_conditions):
            yield from walk_links(0, assignment)
            return
        condition = query.data_conditions[position]
        anchor = assignment.endpoints[condition.anchor_group]
        permitted = allowed_by_endpoint.get(condition.name)
        for required in query.required_links:
            pair_maps = link_pair_maps[required.name]
            targets_by_source, sources_by_target = pair_maps
            if (
                required.target_group == condition.name
                and required.source_group in assignment.endpoints
            ):
                source_uuid = assignment.endpoints[required.source_group].uuid
                linked = frozenset(targets_by_source.get(source_uuid, ()))
                permitted = linked if permitted is None else permitted & linked
            elif (
                required.source_group == condition.name
                and required.target_group in assignment.endpoints
            ):
                target_uuid = assignment.endpoints[required.target_group].uuid
                linked = frozenset(sources_by_target.get(target_uuid, ()))
                permitted = linked if permitted is None else permitted & linked
        for data in index.associated_data_candidates(
            condition.associated_data_type, anchor.uuid, permitted
        ):
            if not all(_satisfies(each, data) for each in condition.property_conditions):
                continue
            yield from walk_conditions(
                position + 1,
                _Assignment(
                    endpoints={**assignment.endpoints, condition.name: data},
                    links=assignment.links,
                ),
            )

    def walk_links(position: int, assignment: _Assignment):
        if position == len(query.required_links):
            yield assignment
            return
        required = query.required_links[position]
        source = assignment.endpoints[required.source_group]
        target = assignment.endpoints[required.target_group]
        for link in index.link_candidates(required, source.uuid, target.uuid):
            yield from walk_links(
                position + 1,
                _Assignment(
                    endpoints=assignment.endpoints,
                    links={**assignment.links, required.name: link},
                ),
            )

    yield from walk_groups(0, _Assignment())


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
    # The expected value is already known to be a number or a string, and to share the
    # property's kind: an ordered comparison against anything else was refused. A stored
    # value of another kind, or of the other orderable kind, can only reach here from a
    # graph that does not conform to its own definitions, and a false answer is the one
    # that claims least about it. Comparing a Decimal with a str would raise instead.
    expected = condition.expected_value
    if isinstance(stored, Decimal) and isinstance(expected, Decimal):
        return _ordered_holds(condition.comparison, stored, expected)
    if isinstance(stored, str) and isinstance(expected, str):
        # Python orders str by code point, which is what the model asks for: no locale
        # collation, no case folding, no normalization — the same basis as equality.
        return _ordered_holds(condition.comparison, stored, expected)
    return False


def _ordered_holds[T: (Decimal, str)](
    comparison: PropertyComparison, stored: T, expected: T
) -> bool:
    """Apply one ordered comparison to two values of the same orderable kind."""
    match comparison:
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


def semantic_row_identity(row: GraphQueryRow) -> tuple[object, ...]:
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
