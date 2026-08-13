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

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Protocol

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
    "EvaluatedStateScope",
    "GraphQuery",
    "GraphQueryResult",
    "GraphQueryRow",
    "LinkBinding",
    "LinkProjection",
    "LinkUuidFilter",
    "PropertyComparison",
    "QueryCandidateIndex",
    "RequiredLink",
    "ReturnShape",
    "ReturnProjection",
    "ReturnedProperty",
    "evaluate_query",
    "evaluate_indexed_query",
    "indexed_query_findings",
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


class QueryCandidateIndex(Protocol):
    """The identity joins the query language needs from a current-state realization."""

    def known_anchor_uuids(self, anchor_type: str, uuids: tuple[str, ...]) -> set[str]: ...

    def known_link_uuids(self, link_type: str, uuids: tuple[str, ...]) -> set[str]: ...

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


class _InMemoryQueryIndex:
    """Hash-indexed access over an explicitly materialized graph."""

    def __init__(self, graph: Graph) -> None:
        self._anchors_by_uuid = {anchor.uuid: anchor for anchor in graph.anchors}
        self._links_by_uuid = {link.uuid: link for link in graph.links}
        self._anchors_by_type: dict[str, list[Anchor]] = {}
        self._data_by_type_and_anchor: dict[tuple[str, str], list[AssociatedDataObject]] = {}
        self._links_by_join: dict[tuple[str, str, str], list[Link]] = {}
        self._link_pairs_by_type: dict[str, set[tuple[str, str]]] = {}
        for anchor in graph.anchors:
            self._anchors_by_type.setdefault(anchor.type_key, []).append(anchor)
        for data in graph.associated_data:
            for anchor_uuid in data.anchor_uuids:
                self._data_by_type_and_anchor.setdefault((data.type_key, anchor_uuid), []).append(
                    data
                )
        for link in graph.links:
            self._links_by_join.setdefault(
                (link.type_key, link.source_uuid, link.target_uuid), []
            ).append(link)
            self._link_pairs_by_type.setdefault(link.type_key, set()).add(
                (link.source_uuid, link.target_uuid)
            )

    def known_anchor_uuids(self, anchor_type: str, uuids: tuple[str, ...]) -> set[str]:
        return {
            uuid
            for uuid in uuids
            if (anchor := self._anchors_by_uuid.get(uuid)) is not None
            and anchor.type_key == anchor_type
        }

    def known_link_uuids(self, link_type: str, uuids: tuple[str, ...]) -> set[str]:
        return {
            uuid
            for uuid in uuids
            if (link := self._links_by_uuid.get(uuid)) is not None and link.type_key == link_type
        }

    def anchor_candidates(
        self, group: AnchorGroup, allowed_uuids: frozenset[str] | None = None
    ) -> tuple[Anchor, ...]:
        candidates = self._anchors_by_type.get(group.anchor_type, ())
        permitted = None if group.uuid_filter is None else frozenset(group.uuid_filter.uuids)
        if allowed_uuids is not None:
            permitted = allowed_uuids if permitted is None else permitted & allowed_uuids
        if permitted is None:
            return tuple(candidates)
        return tuple(anchor for anchor in candidates if anchor.uuid in permitted)

    def associated_data_candidates(
        self,
        associated_data_type: str,
        anchor_uuid: str,
        allowed_uuids: frozenset[str] | None = None,
    ) -> tuple[AssociatedDataObject, ...]:
        candidates = self._data_by_type_and_anchor.get((associated_data_type, anchor_uuid), ())
        if allowed_uuids is None:
            return tuple(candidates)
        return tuple(data for data in candidates if data.uuid in allowed_uuids)

    def link_candidates(
        self, required: RequiredLink, source_uuid: str, target_uuid: str
    ) -> tuple[Link, ...]:
        candidates = self._links_by_join.get((required.link_type, source_uuid, target_uuid), ())
        if required.uuid_filter is None:
            return tuple(candidates)
        permitted = frozenset(required.uuid_filter.uuids)
        return tuple(link for link in candidates if link.uuid in permitted)

    def link_endpoint_pairs(self, required: RequiredLink) -> frozenset[tuple[str, str]]:
        pairs = self._link_pairs_by_type.get(required.link_type, set())
        if required.uuid_filter is None:
            return frozenset(pairs)
        permitted = frozenset(required.uuid_filter.uuids)
        return frozenset(
            (link.source_uuid, link.target_uuid)
            for uuid in permitted
            if (link := self._links_by_uuid.get(uuid)) is not None
            and link.type_key == required.link_type
        )


# --- Whether a query means anything --------------------------------------------------


def query_findings(
    query: GraphQuery, definitions: GraphDefinitionSet, graph: Graph
) -> tuple[ValidationFinding, ...]:
    """Return every reason ``query`` cannot be evaluated.

    A restriction to an identity that does not exist is a finding rather than an empty
    answer: the caller named something it believed it knew, and reporting nothing found
    would answer a question it did not ask.
    """
    return _query_findings(query, definitions, _InMemoryQueryIndex(graph))


def indexed_query_findings(
    query: GraphQuery, definitions: GraphDefinitionSet, index: QueryCandidateIndex
) -> tuple[ValidationFinding, ...]:
    """Validate query meaning with a realization-provided identity index."""
    return _query_findings(query, definitions, index)


def _query_findings(
    query: GraphQuery, definitions: GraphDefinitionSet, index: QueryCandidateIndex
) -> tuple[ValidationFinding, ...]:
    findings: list[ValidationFinding] = []
    names = _name_findings(query, findings)
    _group_findings(query, definitions, index, findings)
    _condition_findings(query, definitions, names, findings)
    _link_findings(query, definitions, index, names, findings)
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
    index: QueryCandidateIndex,
    findings: list[ValidationFinding],
) -> None:
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
            known=(
                set()
                if group.uuid_filter is None
                else index.known_anchor_uuids(group.anchor_type, group.uuid_filter.uuids)
            ),
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
    index: QueryCandidateIndex,
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
            known=(
                set()
                if link.uuid_filter is None
                else index.known_link_uuids(link.link_type, link.uuid_filter.uuids)
            ),
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
    return evaluate_indexed_query(query, definitions, _InMemoryQueryIndex(graph), revision)


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

    rows = _distinct_rows(query, index)
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
        key = _row_identity(row)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
        if len(rows) > query.maximum_rows:
            break
    return tuple(rows)


def _assignments(query: GraphQuery, index: QueryCandidateIndex):
    """Enumerate projected assignments without multiplying irrelevant components.

    A disconnected component with no projection is an existence condition: zero
    satisfying assignments removes every row, while one or a million have the same
    effect. Projected components are deduplicated by their own projected tuple before
    they are combined, so unprojected variation inside a component cannot manufacture
    repeated global assignments either.
    """
    projected_components: list[tuple[_Assignment, ...]] = []
    for names in _selector_components(query):
        component = _component_query(query, names)
        if not component.return_shape.projections:
            if next(_component_assignments(component, index), None) is None:
                return
            continue
        distinct = _distinct_component_assignments(component, index)
        if not distinct:
            return
        projected_components.append(distinct)

    def combine(index: int, assignment: _Assignment):
        if index == len(projected_components):
            yield assignment
            return
        for component_assignment in projected_components[index]:
            yield from combine(
                index + 1,
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
        maximum_rows=query.maximum_rows,
    )


def _distinct_component_assignments(
    query: GraphQuery, index: QueryCandidateIndex
) -> tuple[_Assignment, ...]:
    """Keep one assignment for each distinct projection inside one component."""
    seen: set[tuple[object, ...]] = set()
    assignments: list[_Assignment] = []
    for assignment in _component_assignments(query, index):
        key = _row_identity(_project(query, assignment))
        if key in seen:
            continue
        seen.add(key)
        assignments.append(assignment)
        if len(assignments) > query.maximum_rows:
            break
    return tuple(assignments)


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
