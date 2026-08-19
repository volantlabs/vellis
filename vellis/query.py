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
the order groups were written in. The pure analyzer describes one positive conjunction;
the selected durable realization compiles it relationally, while tests use an independent
small brute-force oracle.

The bound is on the whole answer rather than on a page of it. A result larger than the
caller asked for is refused entire, because a truncated answer to a question about what
exists is not a smaller true answer — it is a different, false one. Nothing here paginates
or sorts, and the model deliberately leaves both out.

One tagged selection chooses current, prospective, revision, or time state. Resolution and
transaction ownership remain outside these pure request values.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from vellis.definitions import AssociatedDataTypeDefinition, GraphDefinitionSet
from vellis.graph import Anchor, AssociatedDataObject, Link
from vellis.history import (
    CurrentSelection,
    EvaluatedStateSelection,
)
from vellis.json_value import (
    MAXIMUM_STORED_INTEGER_EXPONENT,
    JsonKind,
    JsonValue,
    _json_equality_key,
    json_kind,
    unencodable_reason,
)
from vellis.outcomes import OperationStatus, ValidationFinding
from vellis.patterns import PatternError, compile_pattern

__all__ = [
    "AggregateBinding",
    "AggregationOperator",
    "AnchorBinding",
    "AnchorGroup",
    "AnchorProjection",
    "AggregateQueryOutput",
    "AnalyzedGraphQuery",
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
    "PropertyComparison",
    "QueryAggregation",
    "RequiredLink",
    "QueryOutput",
    "RowQueryOutput",
    "ReturnProjection",
    "ReturnedProperty",
    "UuidFilter",
    "analyze_graph_query",
]

_CLOSED_REQUEST = ConfigDict(extra="forbid")


class PropertyComparison(Enum):
    """How one stored property value is compared with an expected value."""

    EQUAL = "equal"
    NOT_EQUAL = "notEqual"
    LESS_THAN = "lessThan"
    LESS_THAN_OR_EQUAL = "lessThanOrEqual"
    GREATER_THAN = "greaterThan"
    GREATER_THAN_OR_EQUAL = "greaterThanOrEqual"
    MATCHES_PATTERN = "matchesPattern"

    @property
    def ordered(self) -> bool:
        return self in {
            PropertyComparison.LESS_THAN,
            PropertyComparison.LESS_THAN_OR_EQUAL,
            PropertyComparison.GREATER_THAN,
            PropertyComparison.GREATER_THAN_OR_EQUAL,
        }


# The kinds that carry an order of their own. A number orders by exact mathematical value
# and a string by exact code-point sequence, which is the basis equality already uses, so
# neither introduces a second notion of what a stored value is. The rest are left out
# because any order over them would have to be invented here: null and Boolean have too
# few values to be worth one, and an array or object would need a rule about members that
# the model does not state.
ORDERABLE_KINDS = frozenset({JsonKind.NUMBER, JsonKind.STRING})


# --- What a query asks ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UuidFilter:
    """Narrows one selector variable to known identities of its required kind and type."""

    uuids: tuple[str, ...]

    __pydantic_config__ = _CLOSED_REQUEST


@dataclass(frozen=True, slots=True)
class AnchorGroup:
    """A named candidate set of anchors of one or more active types.

    Several types because one question is often about work that takes several
    shapes — what is due, whoever owes it — and asking it once is the difference
    between a graph and a pile of separate indexes.
    """

    name: str
    anchor_types: tuple[str, ...]
    uuid_filter: UuidFilter | None = None

    __pydantic_config__ = _CLOSED_REQUEST


@dataclass(frozen=True, slots=True)
class DataPropertyCondition:
    """A structured comparison against one present property value."""

    property_name: str
    comparison: PropertyComparison
    expected_value: JsonValue

    __pydantic_config__ = _CLOSED_REQUEST


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
    uuid_filter: UuidFilter | None = None

    __pydantic_config__ = _CLOSED_REQUEST


@dataclass(frozen=True, slots=True)
class RequiredLink:
    """A required directed link of one active type between two named groups."""

    name: str
    source_group: str
    target_group: str
    link_type: str
    uuid_filter: UuidFilter | None = None

    __pydantic_config__ = _CLOSED_REQUEST


@dataclass(frozen=True, slots=True)
class AnchorProjection:
    """Returns the anchor bound to one anchor group."""

    name: str
    anchor_group: str

    __pydantic_config__ = _CLOSED_REQUEST


@dataclass(frozen=True, slots=True)
class LinkProjection:
    """Returns the link bound to one required link."""

    name: str
    required_link: str

    __pydantic_config__ = _CLOSED_REQUEST


@dataclass(frozen=True, slots=True)
class AssociatedDataProjection:
    """Returns the associated-data object bound to one data condition."""

    name: str
    data_condition: str

    __pydantic_config__ = _CLOSED_REQUEST


@dataclass(frozen=True, slots=True)
class DataPropertyProjection:
    """Returns one property of the object bound to one data condition."""

    name: str
    data_condition: str
    property_name: str

    __pydantic_config__ = _CLOSED_REQUEST


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
    property_name: str | None = None

    __pydantic_config__ = _CLOSED_REQUEST


@dataclass(frozen=True, slots=True)
class RowQueryOutput:
    """One complete bounded set of projected rows."""

    kind: Literal["rows"]
    projections: tuple[ReturnProjection, ...]
    maximum_rows: int

    __pydantic_config__ = _CLOSED_REQUEST


@dataclass(frozen=True, slots=True)
class AggregateQueryOutput:
    """Arithmetic over one bounded distinct associated-data population."""

    kind: Literal["aggregates"]
    data_condition: str
    aggregations: tuple[QueryAggregation, ...]
    maximum_matches: int

    __pydantic_config__ = _CLOSED_REQUEST


QueryOutput = Annotated[
    RowQueryOutput | AggregateQueryOutput,
    Field(discriminator="kind"),
]


@dataclass(frozen=True, slots=True)
class GraphQuery:
    """A complete bounded question about the graph."""

    anchor_groups: tuple[AnchorGroup, ...]
    output: QueryOutput
    required_links: tuple[RequiredLink, ...] = ()
    data_conditions: tuple[AssociatedDataCondition, ...] = ()
    state: EvaluatedStateSelection = field(default_factory=lambda: CurrentSelection(kind="current"))

    __pydantic_config__ = _CLOSED_REQUEST


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
    associated_data_uuid: str
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


@dataclass(frozen=True, slots=True)
class AtomicQueryPredicate:
    """One positive predicate and the named variables whose binding it restricts."""

    kind: str
    variables: tuple[str, ...]
    name: str
    property_name: str | None = None


@dataclass(frozen=True, slots=True)
class OutputIdentityColumn:
    """One ordered component of a distinct row or aggregate-target identity."""

    projection: str
    kind: str
    variable: str
    property_name: str | None = None


@dataclass(frozen=True, slots=True)
class AnalyzedGraphQuery:
    """Pure, immutable semantic analysis consumed by the SQLite compiler."""

    query: GraphQuery
    selector_kinds: tuple[tuple[str, str], ...]
    answer_variables: tuple[str, ...]
    existential_variables: tuple[str, ...]
    existential_links: tuple[str, ...]
    aggregate_target: str | None
    predicates: tuple[AtomicQueryPredicate, ...]
    referenced_type_keys: tuple[str, ...]
    referenced_property_keys: tuple[tuple[str, str], ...]
    identity_columns: tuple[OutputIdentityColumn, ...]


# --- Whether a query means anything --------------------------------------------------


def analyze_graph_query(
    query: GraphQuery, definitions: GraphDefinitionSet
) -> tuple[AnalyzedGraphQuery | None, tuple[ValidationFinding, ...]]:
    """Validate state-independent meaning and describe its positive conjunction.

    UUID existence, kind, and evaluated-state type membership deliberately remain for
    relational validation after selector members are populated. Everything else here is
    pure: no graph candidates, storage, indexes, or object construction are consulted.
    """
    findings = _query_findings(query, definitions)
    if findings:
        return None, findings

    selector_kinds = tuple((group.name, "anchor") for group in query.anchor_groups) + tuple(
        (condition.name, "associatedData") for condition in query.data_conditions
    )
    projected_variables: list[str] = []
    projected_links: set[str] = set()
    identity_columns: list[OutputIdentityColumn] = []
    if isinstance(query.output, RowQueryOutput):
        for projection in query.output.projections:
            if isinstance(projection, AnchorProjection):
                variable, kind, property_name = projection.anchor_group, "anchor", None
            elif isinstance(projection, LinkProjection):
                variable, kind, property_name = projection.required_link, "link", None
                projected_links.add(variable)
            elif isinstance(projection, AssociatedDataProjection):
                variable, kind, property_name = (
                    projection.data_condition,
                    "associatedData",
                    None,
                )
            else:
                variable, kind, property_name = (
                    projection.data_condition,
                    "property",
                    projection.property_name,
                )
            projected_variables.append(variable)
            identity_columns.append(
                OutputIdentityColumn(projection.name, kind, variable, property_name)
            )
        aggregate_target = None
    else:
        aggregate_target = query.output.data_condition
        projected_variables.append(aggregate_target)
        identity_columns.append(
            OutputIdentityColumn(aggregate_target, "associatedData", aggregate_target)
        )

    answer_variables = tuple(dict.fromkeys(projected_variables))
    selector_names = tuple(name for name, _ in selector_kinds)
    predicates: list[AtomicQueryPredicate] = []
    for group in query.anchor_groups:
        predicates.append(AtomicQueryPredicate("anchorType", (group.name,), group.name))
        if group.uuid_filter is not None:
            predicates.append(AtomicQueryPredicate("anchorUuid", (group.name,), group.name))
    for condition in query.data_conditions:
        predicates.append(AtomicQueryPredicate("dataType", (condition.name,), condition.name))
        if condition.uuid_filter is not None:
            predicates.append(AtomicQueryPredicate("dataUuid", (condition.name,), condition.name))
        predicates.append(
            AtomicQueryPredicate(
                "directAssociation",
                (condition.anchor_group, condition.name),
                condition.name,
            )
        )
        predicates.extend(
            AtomicQueryPredicate(
                "property", (condition.name,), condition.name, comparison.property_name
            )
            for comparison in condition.property_conditions
        )
    predicates.extend(
        AtomicQueryPredicate(
            "requiredLink",
            (required.name, required.source_group, required.target_group),
            required.name,
        )
        for required in query.required_links
    )
    referenced_types = tuple(
        dict.fromkeys(
            type_key
            for values in (
                *(group.anchor_types for group in query.anchor_groups),
                *((condition.associated_data_type,) for condition in query.data_conditions),
                *((required.link_type,) for required in query.required_links),
            )
            for type_key in values
        )
    )
    referenced_properties = tuple(
        dict.fromkeys(
            (condition.associated_data_type, property_name)
            for condition in query.data_conditions
            for property_name in (
                *(comparison.property_name for comparison in condition.property_conditions),
                *(
                    projection.property_name
                    for projection in (
                        query.output.projections if isinstance(query.output, RowQueryOutput) else ()
                    )
                    if isinstance(projection, DataPropertyProjection)
                    and projection.data_condition == condition.name
                ),
                *(
                    aggregation.property_name
                    for aggregation in (
                        query.output.aggregations
                        if isinstance(query.output, AggregateQueryOutput)
                        and query.output.data_condition == condition.name
                        else ()
                    )
                    if aggregation.property_name is not None
                ),
            )
        )
    )
    return (
        AnalyzedGraphQuery(
            query=query,
            selector_kinds=selector_kinds,
            answer_variables=answer_variables,
            existential_variables=tuple(
                name for name in selector_names if name not in answer_variables
            ),
            existential_links=tuple(
                required.name
                for required in query.required_links
                if required.name not in projected_links
            ),
            aggregate_target=aggregate_target,
            predicates=tuple(predicates),
            referenced_type_keys=referenced_types,
            referenced_property_keys=referenced_properties,
            identity_columns=tuple(identity_columns),
        ),
        (),
    )


def _query_findings(
    query: GraphQuery,
    definitions: GraphDefinitionSet,
) -> tuple[ValidationFinding, ...]:
    findings: list[ValidationFinding] = []
    names = _name_findings(query, findings)
    _group_findings(query, definitions, findings)
    _condition_findings(query, definitions, names, findings)
    _link_findings(query, definitions, names, findings)
    _projection_findings(query, definitions, names, findings)
    _aggregation_findings(query, definitions, findings)
    if not query.anchor_groups:
        findings.append(ValidationFinding(summary="a query must select at least one anchor group"))
    if isinstance(query.output, RowQueryOutput):
        if not query.output.projections:
            findings.append(ValidationFinding(summary="row output must request a projection"))
        if query.output.maximum_rows < 1:
            findings.append(
                ValidationFinding(
                    summary=f"maximum rows must be positive, not {query.output.maximum_rows}"
                )
            )
    else:
        if not query.output.aggregations:
            findings.append(
                ValidationFinding(summary="aggregate output must request an aggregation")
            )
        if query.output.maximum_matches < 1:
            findings.append(
                ValidationFinding(
                    summary=(
                        "maximum aggregate matches must be positive, not "
                        f"{query.output.maximum_matches}"
                    )
                )
            )
    return tuple(findings)


def _named(query: GraphQuery) -> list[tuple[str, str]]:
    output_names = (
        ((projection.name, "projection") for projection in query.output.projections)
        if isinstance(query.output, RowQueryOutput)
        else ((aggregation.name, "aggregation") for aggregation in query.output.aggregations)
    )
    return [
        *((group.name, "anchor group") for group in query.anchor_groups),
        *((condition.name, "data condition") for condition in query.data_conditions),
        *((link.name, "required link") for link in query.required_links),
        *output_names,
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
        _uuid_filter_findings(
            group.uuid_filter.uuids if group.uuid_filter is not None else None,
            label=f"anchor group '{group.name}'",
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
        seen.add(uuid)


def _condition_findings(
    query: GraphQuery,
    definitions: GraphDefinitionSet,
    names: dict[str, str],
    findings: list[ValidationFinding],
) -> None:
    for condition in query.data_conditions:
        _uuid_filter_findings(
            condition.uuid_filter.uuids if condition.uuid_filter is not None else None,
            label=f"data condition '{condition.name}'",
            findings=findings,
        )
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
    if property_condition.comparison is PropertyComparison.MATCHES_PATTERN:
        if constraint.json_kind is not JsonKind.STRING:
            findings.append(
                ValidationFinding(
                    summary=(
                        f"{label} pattern-matches property "
                        f"'{property_condition.property_name}', which is declared "
                        f"{constraint.json_kind.value}; pattern comparison is valid only "
                        "for string-valued properties"
                    )
                )
            )
        if isinstance(property_condition.expected_value, str):
            try:
                compile_pattern(property_condition.expected_value)
            except PatternError as error:
                findings.append(
                    ValidationFinding(
                        summary=(
                            f"{label} has an invalid query pattern for "
                            f"'{property_condition.property_name}': {error}"
                        )
                    )
                )
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
            findings=findings,
        )


def _aggregation_findings(
    query: GraphQuery,
    definitions: GraphDefinitionSet,
    findings: list[ValidationFinding],
) -> None:
    """Report why an aggregation cannot be computed, before any of it is."""
    if not isinstance(query.output, AggregateQueryOutput):
        return
    conditions = {condition.name: condition for condition in query.data_conditions}
    target = query.output.data_condition
    for aggregation in query.output.aggregations:
        label = f"aggregation '{aggregation.name}'"
        condition = conditions.get(target)
        if condition is None:
            findings.append(
                ValidationFinding(
                    summary=(
                        f"aggregate output names '{target}', which is not a data "
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
    if not isinstance(query.output, RowQueryOutput):
        return
    for projection in query.output.projections:
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
                anchor_binding.projection, anchor.uuid, anchor.type_key, anchor.display_name
            )
            reason = reason or _mapping_unreturnable_reason(anchor.system_metadata.members)
            if reason is not None:
                return f"a returned anchor cannot be returned: {reason}"
        for data_binding in row.associated_data:
            data = data_binding.associated_data
            reason = _first_unencodable(
                data_binding.projection,
                data.uuid,
                data.type_key,
                *data.anchor_uuids,
            )
            reason = reason or _mapping_unreturnable_reason(data.properties)
            reason = reason or _mapping_unreturnable_reason(data.system_metadata.members)
            if reason is not None:
                return f"returned associated data cannot be returned: {reason}"
        for link_binding in row.links:
            link = link_binding.link
            reason = _first_unencodable(
                link_binding.projection,
                link.uuid,
                link.type_key,
                link.source_uuid,
                link.target_uuid,
            )
            reason = reason or _mapping_unreturnable_reason(link.system_metadata.members)
            if reason is not None:
                return f"a returned link cannot be returned: {reason}"
        for property_binding in row.properties:
            reason = _first_unencodable(
                property_binding.projection, property_binding.associated_data_uuid
            )
            if reason is None and property_binding.present:
                reason = _json_unreturnable_reason(property_binding.value)
            if reason is not None:
                return f"a returned property cannot be returned: {reason}"
    return None


def _first_unencodable(*values: str) -> str | None:
    return next((r for r in (unencodable_reason(each) for each in values) if r is not None), None)


def _mapping_unreturnable_reason(values: dict[str, JsonValue]) -> str | None:
    for name, value in values.items():
        reason = unencodable_reason(name) or _json_unreturnable_reason(value)
        if reason is not None:
            return reason
    return None


def _json_unreturnable_reason(value: JsonValue) -> str | None:
    if isinstance(value, str):
        return unencodable_reason(value)
    if isinstance(value, list):
        return next(
            (
                reason
                for member in value
                if (reason := _json_unreturnable_reason(member)) is not None
            ),
            None,
        )
    if isinstance(value, dict):
        return _mapping_unreturnable_reason(value)
    return None


def _decimal_term(value: Decimal) -> tuple[int, int, int]:
    """Return one finite decimal's normalized exponent, signed coefficient, and digits."""
    shape = value.as_tuple()
    assert isinstance(shape.exponent, int)
    coefficient = 0
    for digit in shape.digits:
        coefficient = coefficient * 10 + digit
    exponent = shape.exponent
    while coefficient and coefficient % 10 == 0:
        coefficient //= 10
        exponent += 1
    return exponent, (-coefficient if shape.sign else coefficient), len(shape.digits)


def _exact_decimal_streamed_result(
    terms: Callable[[], Iterable[tuple[int, int]]], input_digits: int, count: int
) -> Decimal:
    """Materialize an exact scalar from a re-readable, externally retained term stream."""
    lowest_place: int | None = None
    highest_place: int | None = None
    for raw_exponent, raw_coefficient in terms():
        exponent, coefficient = raw_exponent, raw_coefficient
        while coefficient and coefficient % 10 == 0:
            coefficient //= 10
            exponent += 1
        if not coefficient:
            continue
        lowest_place = exponent if lowest_place is None else min(lowest_place, exponent)
        highest = exponent + _integer_digit_count(coefficient) - 1
        highest_place = highest if highest_place is None else max(highest_place, highest)
    if lowest_place is None or highest_place is None:
        return Decimal(0)
    permitted_span = max(MAXIMUM_STORED_INTEGER_EXPONENT, input_digits + len(str(count)))
    if highest_place - lowest_place + 1 > permitted_span:
        raise ArithmeticError(
            "the exact aggregate sum would require expanding compact numeric inputs "
            "beyond the finite result materialization bound"
        )
    total = 0
    for exponent, coefficient in terms():
        total += coefficient * 10 ** (exponent - lowest_place)
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


def _integer_text(value: int) -> str:
    """Encode an integer without the interpreter's integer-to-text digit limit."""
    if not value:
        return "0"
    sign = "-" if value < 0 else ""
    remaining = abs(value)
    digits: list[str] = []
    while remaining:
        remaining, digit = divmod(remaining, 10)
        digits.append(str(digit))
    return sign + "".join(reversed(digits))


def _integer_from_text(value: str) -> int:
    """Decode an integer without the interpreter's text-to-integer digit limit."""
    sign = -1 if value.startswith("-") else 1
    result = 0
    for digit in value.removeprefix("-"):
        result = result * 10 + (ord(digit) - ord("0"))
    return sign * result


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
            (
                each.projection,
                each.associated_data_uuid,
                each.present,
                _json_equality_key(each.value),
            )
            for each in row.properties
        ),
    )
