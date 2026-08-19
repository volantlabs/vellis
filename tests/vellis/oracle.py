"""Small test-only semantic materializers independent of production interfaces.

Production Vellis deliberately has no API that constructs a complete Graph or
CanonicalState. Small conformance fixtures still benefit from an independent readable
oracle, so tests assemble those values directly from normalized SQLite rows here.
"""

from __future__ import annotations

from decimal import Decimal, DecimalException
from itertools import product
from typing import cast

import re2

from tests.vellis.semantic_state import DefinitionDelta, SemanticState
from vellis.changes import GraphChange
from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    GraphDefinitionSet,
    LinkTypeDefinition,
    RelationshipConstraint,
)
from vellis.everyday_life import everyday_life_entries
from vellis.graph import Anchor, AssociatedDataObject, Graph, GraphObject, Link, ObjectKind
from vellis.json_value import JsonValue, json_kind
from vellis.normalized import load_object_value
from vellis.outcomes import OperationStatus, ValidationFinding
from vellis.query import (
    AggregateBinding,
    AggregationOperator,
    AnchorBinding,
    AnchorProjection,
    AssociatedDataBinding,
    AssociatedDataProjection,
    DataPropertyProjection,
    GraphQuery,
    GraphQueryResult,
    GraphQueryRow,
    LinkBinding,
    LinkProjection,
    PropertyComparison,
    ReturnedProperty,
    RowQueryOutput,
)
from vellis.store import CanonicalStore
from vellis.system import RTGSystem


def evaluate_query(
    query: GraphQuery, definitions: GraphDefinitionSet, graph: Graph, revision: int
) -> GraphQueryResult:
    """Brute-force a small positive pattern without production query implementation."""
    del definitions  # Valid generated fixtures already carry definition-conformant operands.
    variables: list[tuple[str, tuple[GraphObject, ...]]] = []
    for group in query.anchor_groups:
        allowed = None if group.uuid_filter is None else frozenset(group.uuid_filter.uuids)
        variables.append(
            (
                group.name,
                tuple(
                    anchor
                    for anchor in graph.anchors
                    if anchor.type_key in group.anchor_types
                    and (allowed is None or anchor.uuid in allowed)
                ),
            )
        )
    for condition in query.data_conditions:
        allowed = None if condition.uuid_filter is None else frozenset(condition.uuid_filter.uuids)
        variables.append(
            (
                condition.name,
                tuple(
                    value
                    for value in graph.associated_data
                    if value.type_key == condition.associated_data_type
                    and (allowed is None or value.uuid in allowed)
                ),
            )
        )
    for required in query.required_links:
        allowed = None if required.uuid_filter is None else frozenset(required.uuid_filter.uuids)
        variables.append(
            (
                required.name,
                tuple(
                    link
                    for link in graph.links
                    if link.type_key == required.link_type
                    and (allowed is None or link.uuid in allowed)
                ),
            )
        )

    row_by_identity: dict[tuple[object, ...], GraphQueryRow] = {}
    aggregate_targets: dict[str, AssociatedDataObject] = {}
    names = tuple(name for name, _ in variables)
    populations = tuple(values for _, values in variables)
    for values in product(*populations):
        assignment = dict(zip(names, values, strict=True))
        if not _assignment_matches(query, assignment):
            continue
        if isinstance(query.output, RowQueryOutput):
            row = _oracle_project(query, assignment)
            row_by_identity.setdefault(row_identity(row), row)
            if len(row_by_identity) > query.output.maximum_rows:
                return _oracle_bound_refusal(query, query.output.maximum_rows)
        else:
            target = cast(AssociatedDataObject, assignment[query.output.data_condition])
            aggregate_targets[target.uuid] = target
            if len(aggregate_targets) > query.output.maximum_matches:
                return _oracle_bound_refusal(query, query.output.maximum_matches)

    if isinstance(query.output, RowQueryOutput):
        rows = tuple(row_by_identity.values())
        if reason := _oracle_unreturnable_reason(rows):
            return GraphQueryResult(
                OperationStatus.REJECTED,
                "the complete result could not be returned, so none of it was",
                query,
                findings=(ValidationFinding(summary=reason),),
            )
        return GraphQueryResult(
            OperationStatus.ACCEPTED,
            f"{len(rows)} rows at revision {revision}",
            query,
            evaluated_revision=revision,
            rows=rows,
        )
    try:
        aggregates = tuple(
            _oracle_aggregate(aggregation, tuple(aggregate_targets.values()))
            for aggregation in query.output.aggregations
        )
    except ArithmeticError as error:
        return GraphQueryResult(
            OperationStatus.REJECTED,
            "the complete aggregate could not be returned",
            query,
            findings=(ValidationFinding(summary=str(error)),),
        )
    return GraphQueryResult(
        OperationStatus.ACCEPTED,
        f"{len(aggregates)} aggregates at revision {revision}",
        query,
        evaluated_revision=revision,
        aggregates=aggregates,
    )


def _assignment_matches(query: GraphQuery, assignment: dict[str, GraphObject]) -> bool:
    for condition in query.data_conditions:
        data = cast(AssociatedDataObject, assignment[condition.name])
        anchor = assignment[condition.anchor_group]
        if anchor.uuid not in data.anchor_uuids:
            return False
        if any(
            not _property_matches(
                data,
                comparison.property_name,
                comparison.comparison,
                comparison.expected_value,
            )
            for comparison in condition.property_conditions
        ):
            return False
    for required in query.required_links:
        link = cast(Link, assignment[required.name])
        if (
            link.source_uuid != assignment[required.source_group].uuid
            or link.target_uuid != assignment[required.target_group].uuid
        ):
            return False
    return True


def _property_matches(
    data: AssociatedDataObject, name: str, comparison: PropertyComparison, expected: JsonValue
) -> bool:
    if name not in data.properties:
        return False
    value = data.properties[name]
    if comparison is PropertyComparison.EQUAL:
        return _oracle_value_key(value) == _oracle_value_key(expected)
    if comparison is PropertyComparison.NOT_EQUAL:
        return _oracle_value_key(value) != _oracle_value_key(expected)
    if comparison is PropertyComparison.MATCHES_PATTERN:
        return (
            isinstance(value, str)
            and isinstance(expected, str)
            and _oracle_pattern_matches(expected, value)
        )
    if not isinstance(value, (Decimal, str)) or isinstance(value, bool):
        return False
    if comparison is PropertyComparison.LESS_THAN:
        return value < expected  # type: ignore[operator]
    if comparison is PropertyComparison.LESS_THAN_OR_EQUAL:
        return value <= expected  # type: ignore[operator]
    if comparison is PropertyComparison.GREATER_THAN:
        return value > expected  # type: ignore[operator]
    return value >= expected  # type: ignore[operator]


def _oracle_project(query: GraphQuery, assignment: dict[str, GraphObject]) -> GraphQueryRow:
    assert isinstance(query.output, RowQueryOutput)
    anchors: list[AnchorBinding] = []
    links: list[LinkBinding] = []
    data: list[AssociatedDataBinding] = []
    properties: list[ReturnedProperty] = []
    for projection in query.output.projections:
        if isinstance(projection, AnchorProjection):
            anchors.append(
                AnchorBinding(projection.name, cast(Anchor, assignment[projection.anchor_group]))
            )
        elif isinstance(projection, LinkProjection):
            links.append(
                LinkBinding(projection.name, cast(Link, assignment[projection.required_link]))
            )
        elif isinstance(projection, AssociatedDataProjection):
            data.append(
                AssociatedDataBinding(
                    projection.name,
                    cast(AssociatedDataObject, assignment[projection.data_condition]),
                )
            )
        else:
            assert isinstance(projection, DataPropertyProjection)
            source = cast(AssociatedDataObject, assignment[projection.data_condition])
            properties.append(
                ReturnedProperty(
                    projection.name,
                    source.uuid,
                    projection.property_name in source.properties,
                    source.properties.get(projection.property_name),
                )
            )
    return GraphQueryRow(tuple(anchors), tuple(links), tuple(data), tuple(properties))


def row_identity(row: GraphQueryRow) -> tuple[object, ...]:
    """Return test-only row identity without production query helpers."""
    return (
        tuple((binding.projection, binding.anchor.uuid) for binding in row.anchors),
        tuple((binding.projection, binding.link.uuid) for binding in row.links),
        tuple(
            (binding.projection, binding.associated_data.uuid) for binding in row.associated_data
        ),
        tuple(
            (
                binding.projection,
                binding.associated_data_uuid,
                binding.present,
                _oracle_value_key(binding.value),
            )
            for binding in row.properties
        ),
    )


def _oracle_pattern_matches(expression: str, value: str) -> bool:
    """Evaluate selected RE2 whole-string meaning without the production wrapper."""
    options = re2.Options()
    options.log_errors = False
    try:
        return re2.compile(expression, options).fullmatch(value) is not None
    except re2.error, UnicodeEncodeError:
        return False


def _oracle_unreturnable_reason(rows: tuple[GraphQueryRow, ...]) -> str | None:
    for row in rows:
        for binding in row.anchors:
            values = (
                binding.projection,
                binding.anchor.uuid,
                binding.anchor.type_key,
                binding.anchor.display_name,
            )
            if any(_not_utf8(value) for value in values) or _oracle_mapping_not_utf8(
                binding.anchor.system_metadata.members
            ):
                return "a returned anchor cannot be returned"
        for binding in row.associated_data:
            value = binding.associated_data
            values = (
                binding.projection,
                value.uuid,
                value.type_key,
                *value.anchor_uuids,
            )
            if (
                any(_not_utf8(member) for member in values)
                or _oracle_mapping_not_utf8(value.properties)
                or _oracle_mapping_not_utf8(value.system_metadata.members)
            ):
                return "returned associated data cannot be returned"
        for binding in row.links:
            value = binding.link
            values = (
                binding.projection,
                value.uuid,
                value.type_key,
                value.source_uuid,
                value.target_uuid,
            )
            if any(_not_utf8(member) for member in values) or _oracle_mapping_not_utf8(
                value.system_metadata.members
            ):
                return "a returned link cannot be returned"
        for binding in row.properties:
            if (
                _not_utf8(binding.projection)
                or _not_utf8(binding.associated_data_uuid)
                or (binding.present and _oracle_value_not_utf8(binding.value))
            ):
                return "a returned property cannot be returned"
    return None


def _not_utf8(value: str) -> bool:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return True
    return False


def _oracle_mapping_not_utf8(value: dict[str, JsonValue]) -> bool:
    return any(_not_utf8(name) or _oracle_value_not_utf8(member) for name, member in value.items())


def _oracle_value_not_utf8(value: JsonValue) -> bool:
    if isinstance(value, str):
        return _not_utf8(value)
    if isinstance(value, list):
        return any(_oracle_value_not_utf8(member) for member in value)
    if isinstance(value, dict):
        return _oracle_mapping_not_utf8(value)
    return False


def _oracle_value_key(value: JsonValue) -> object:
    kind = json_kind(value).value
    if isinstance(value, list):
        return kind, tuple(_oracle_value_key(member) for member in value)
    if isinstance(value, dict):
        return kind, tuple(
            (name, _oracle_value_key(member)) for name, member in sorted(value.items())
        )
    return kind, value


def _oracle_aggregate(aggregation, targets: tuple[AssociatedDataObject, ...]) -> AggregateBinding:
    if aggregation.operator is AggregationOperator.COUNT:
        return AggregateBinding(aggregation.name, True, Decimal(len(targets)))
    values = tuple(
        target.properties[str(aggregation.property_name)]
        for target in targets
        if str(aggregation.property_name) in target.properties
    )
    if not values:
        return AggregateBinding(aggregation.name, False)
    if aggregation.operator is AggregationOperator.SUM:
        total = _oracle_exact_decimal_sum(tuple(cast(Decimal, value) for value in values))
        return AggregateBinding(aggregation.name, True, total)
    ordered = sorted(values)  # type: ignore[type-var]
    value = ordered[0] if aggregation.operator is AggregationOperator.MINIMUM else ordered[-1]
    return AggregateBinding(aggregation.name, True, value)


def _oracle_exact_decimal_sum(values: tuple[Decimal, ...]) -> Decimal:
    """Add finite decimals exactly with a small-fixture integer coefficient oracle."""
    tuples = tuple(value.as_tuple() for value in values)
    exponent = min((value.exponent for value in tuples), default=0)
    if any(int(value.exponent) - int(exponent) > 100_000 for value in tuples):
        raise ArithmeticError("exact sum would require expanding compact numeric inputs")
    coefficient = 0
    for value in tuples:
        digits = int("".join(str(digit) for digit in value.digits) or "0")
        signed = -digits if value.sign else digits
        coefficient += signed * 10 ** (int(value.exponent) - int(exponent))
    if coefficient == 0:
        return Decimal(0)
    sign = int(coefficient < 0)
    digits = tuple(int(digit) for digit in str(abs(coefficient)))
    try:
        return Decimal((sign, digits, int(exponent)))
    except DecimalException as error:
        raise ArithmeticError(
            "exact aggregate is outside the finite decimal result range"
        ) from error


def _oracle_bound_refusal(query: GraphQuery, maximum: int) -> GraphQueryResult:
    return GraphQueryResult(
        OperationStatus.REJECTED,
        f"the complete result exceeds the maximum of {maximum}",
        query,
        findings=(ValidationFinding(summary=f"the complete result exceeds {maximum}"),),
    )


def materialize_everyday_life() -> GraphDefinitionSet:
    """Build the fixed starter aggregate only inside the independent test oracle."""
    entries = tuple(everyday_life_entries())
    return GraphDefinitionSet(
        tuple(value for value in entries if isinstance(value, AnchorTypeDefinition)),
        tuple(value for value in entries if isinstance(value, AssociatedDataTypeDefinition)),
        tuple(value for value in entries if isinstance(value, LinkTypeDefinition)),
        tuple(value for value in entries if isinstance(value, RelationshipConstraint)),
    )


def materialize_definitions(
    system: RTGSystem | CanonicalStore, *, prospective: bool = False
) -> GraphDefinitionSet:
    """Assemble complete definitions directly from normalized rows for tests only."""
    store = system if isinstance(system, CanonicalStore) else system.store
    connection = store._connection  # noqa: SLF001
    head = connection.execute(
        "SELECT active_definition_set_id, proposed_definition_set_id FROM state_head WHERE id = 0"
    ).fetchone()
    assert head is not None
    active_type_keys = set(
        store._effective_type_keys_unlocked("current_graph_object", str(head[0]))
    )  # noqa: SLF001
    active_relationship_keys = set(store._effective_relationship_keys_unlocked(str(head[0])))  # noqa: SLF001
    if not prospective:
        return store._load_definition_set(  # noqa: SLF001
            str(head[0]),
            type_keys=active_type_keys,
            relationship_keys=active_relationship_keys,
        )
    assert head[1] is not None
    type_keys = active_type_keys | {
        str(row[0]) for row in connection.execute("SELECT type_key FROM proposal_definition_type")
    }
    relationship_keys = active_relationship_keys | {
        str(row[0])
        for row in connection.execute("SELECT natural_key FROM proposal_definition_relationship")
    }
    return store._effective_proposed_definitions_unlocked(  # noqa: SLF001
        str(head[0]), type_keys=type_keys, relationship_keys=relationship_keys
    )


def materialize_state(system: RTGSystem | CanonicalStore) -> SemanticState:
    """Assemble one complete semantic state for a small test fixture only."""
    store = system if isinstance(system, CanonicalStore) else system.store
    connection = store._connection  # noqa: SLF001
    with store.read_snapshot():
        revision = store.current_revision()
        values = [
            load_object_value(connection, int(row[0]))
            for row in connection.execute(
                "SELECT object_value_id FROM current_graph_object ORDER BY object_kind, uuid"
            )
        ]
        graph = Graph(
            anchors=tuple(value for value in values if isinstance(value, Anchor)),
            associated_data=tuple(
                value for value in values if isinstance(value, AssociatedDataObject)
            ),
            links=tuple(value for value in values if isinstance(value, Link)),
        )
        active = materialize_definitions(store)
        proposal_present = connection.execute(
            "SELECT proposed_definition_set_id IS NOT NULL FROM state_head WHERE id = 0"
        ).fetchone()[0]
        delta = None
        if proposal_present:
            proposed = materialize_definitions(store, prospective=True)
            delta = DefinitionDelta(
                proposed_definitions=proposed,
                graph_overlay=_materialize_graph_overlay(store),
            )
        return SemanticState(graph, active, revision, delta)


def _materialize_graph_overlay(store: CanonicalStore) -> GraphChange:
    """Assemble the keyed prospective overlay only inside this test oracle."""
    anchors: list[Anchor] = []
    data: list[AssociatedDataObject] = []
    links: list[Link] = []
    removals: dict[ObjectKind, list[str]] = {kind: [] for kind in ObjectKind}
    for uuid, kind_name, operation, value_id in store._connection.execute(  # noqa: SLF001
        "SELECT uuid, object_kind, operation, object_value_id FROM proposal_entry ORDER BY uuid"
    ):
        kind = ObjectKind(str(kind_name))
        if operation == "delete":
            removals[kind].append(str(uuid))
            continue
        value = load_object_value(store._connection, int(value_id))  # noqa: SLF001
        if isinstance(value, Anchor):
            anchors.append(value)
        elif isinstance(value, AssociatedDataObject):
            data.append(value)
        else:
            links.append(value)
    return GraphChange(
        tuple(anchors),
        tuple(data),
        tuple(links),
        tuple(removals[ObjectKind.ANCHOR]),
        tuple(removals[ObjectKind.ASSOCIATED_DATA]),
        tuple(removals[ObjectKind.LINK]),
    )


def materialize_replay(system: RTGSystem | CanonicalStore) -> SemanticState:
    """Require SQL ledger/projection agreement, then materialize the verified projection."""
    store = system if isinstance(system, CanonicalStore) else system.store
    findings = store.verify_projection_from_ledger()
    if findings:
        raise AssertionError(findings[0].summary)
    return materialize_state(system)
