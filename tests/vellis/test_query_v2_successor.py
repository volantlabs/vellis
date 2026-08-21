"""Focused public-operation evidence for Phase 3 discovery and query meaning."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

import vellis.definition_repository as definition_repository
import vellis.query_repository as query_repository
import vellis.read_operations as read_operations
from tests.vellis.v2_query_fixture import initialized_query_database
from tests.vellis.v2_query_oracle import evaluate_pattern
from vellis.database import connect_database
from vellis.discovery_operations import type_inspect, type_summary
from vellis.domain import (
    Anchor,
    AnchorTypeDefinition,
    AssociatedData,
    AssociatedDataTypeDefinition,
    Cardinality,
    Link,
    LinkTypeDefinition,
    OperationStatus,
    PropertyDefinition,
    ResolvedState,
    RevisionState,
    ScalarValue,
    TimeState,
    ValueKind,
    parse_timestamp,
)
from vellis.query_domain import (
    DirectAssociation,
    DisplayNameField,
    GraphQuery,
    IdentityObjectSelection,
    IdentityQueryPayload,
    IdentitySelection,
    PatternLink,
    PatternNode,
    PatternNodeKind,
    PatternQueryPayload,
    PatternSelection,
    Predicate,
    PredicateOperator,
    PropertyField,
    PropertySelection,
)
from vellis.read_operations import query_graph

A = "10000000-0000-4000-8000-000000000001"
B = "10000000-0000-4000-8000-000000000002"
P = "10000000-0000-4000-8000-000000000003"
D1 = "20000000-0000-4000-8000-000000000001"
D2 = "20000000-0000-4000-8000-000000000002"
L1 = "30000000-0000-4000-8000-000000000001"
L2 = "30000000-0000-4000-8000-000000000002"
L3 = "30000000-0000-4000-8000-000000000003"
L4 = "30000000-0000-4000-8000-000000000004"
L5 = "30000000-0000-4000-8000-000000000005"
MISSING = "90000000-0000-4000-8000-000000000009"


def _resolve_pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    assert pointer.startswith("/")
    current = document
    for token in pointer[1:].split("/"):
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def test_cold_summary_and_focused_inspection_are_complete_and_ordered(tmp_path: Path) -> None:
    database = _database(tmp_path)
    summary = type_summary(database)
    assert summary.status is OperationStatus.ACCEPTED
    assert summary.evaluated_revision == 1
    assert tuple(value.type_key for value in summary.anchor_types or ()) == (
        "test.person",
        "test.project",
    )
    inspection = type_inspect(database, ("test.person", "test.project"))
    assert inspection.status is OperationStatus.ACCEPTED
    assert inspection.evaluated_revision == 1
    assert inspection.neighborhoods is not None
    person, project = inspection.neighborhoods
    assert person.anchor_type.type_key == "test.person"
    assert tuple(value.type_key for value in person.associated_data_types) == ("test.details",)
    assert tuple(value.type_key for value in person.link_types) == ("test.relates",)
    assert project.anchor_type.type_key == "test.project"
    assert tuple(value.type_key for value in project.associated_data_types) == ("test.details",)
    duplicate = type_inspect(database, ("test.person", "test.person"))
    assert duplicate.status is OperationStatus.REJECTED
    assert duplicate.neighborhoods is None
    unknown = type_inspect(database, ("test.unknown",))
    assert unknown.status is OperationStatus.REJECTED
    assert unknown.neighborhoods is None


def test_identity_selection_reports_missing_and_hydrates_only_requested_fields(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    result = query_graph(
        database,
        GraphQuery(
            IdentitySelection(
                (
                    IdentityObjectSelection(A),
                    IdentityObjectSelection(
                        D1,
                        PropertySelection(("label", "nullable")),
                        include_legacy_system=True,
                    ),
                    IdentityObjectSelection(MISSING, PropertySelection(("notDefined",))),
                    IdentityObjectSelection(L1),
                )
            )
        ),
    )
    assert result.status is OperationStatus.ACCEPTED
    assert isinstance(result.payload, IdentityQueryPayload)
    assert result.payload.found_uuids == (A, D1, L1)
    assert result.payload.missing_uuids == (MISSING,)
    objects = {value.uuid: value for value in result.payload.objects}
    assert objects[A].display_name == "Café Owner"
    assert objects[A].properties is None
    assert objects[D1].anchor_uuids == (A,)
    assert objects[D1].properties == (
        ("label", ScalarValue.text("Résumé Alpha")),
        ("nullable", None),
    )
    system = objects[D1].system
    assert system is not None
    assert system.legacy_v1 == '{"origin":"fixture"}'
    assert objects[L1].source_uuid == A
    assert objects[L1].target_uuid == D1


def test_identity_all_properties_and_semantic_rejections_are_whole(tmp_path: Path) -> None:
    database = _database(tmp_path)
    result = query_graph(
        database,
        GraphQuery(IdentitySelection((IdentityObjectSelection(D1, PropertySelection(all=True)),))),
    )
    assert result.status is OperationStatus.ACCEPTED
    assert isinstance(result.payload, IdentityQueryPayload)
    properties = result.payload.objects[0].properties
    assert properties is not None
    assert tuple(name for name, _ in properties) == (
        "at",
        "due",
        "flag",
        "label",
        "nullable",
        "quantity",
        "score",
    )
    assert result.payload.objects[0].system is not None
    assert result.payload.objects[0].system.legacy_v1 is None

    duplicate = query_graph(
        database,
        GraphQuery(IdentitySelection((IdentityObjectSelection(A), IdentityObjectSelection(A)))),
    )
    assert duplicate.status is OperationStatus.REJECTED
    assert duplicate.payload is None

    mismatch = query_graph(
        database,
        GraphQuery(
            PatternSelection(
                10,
                (
                    PatternNode(
                        "owner",
                        PatternNodeKind.ANCHOR,
                        ("test.project",),
                        (A,),
                    ),
                ),
            )
        ),
    )
    assert mismatch.status is OperationStatus.REJECTED
    assert mismatch.payload is None
    assert mismatch.findings[0].code.value == "kindMismatch"


def test_connected_patterns_bind_every_selector_and_enforce_whole_result_bound(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    selection = PatternSelection(
        2,
        (
            PatternNode("owner", PatternNodeKind.ANCHOR, ("test.person",), (A,)),
            PatternNode(
                "detail",
                PatternNodeKind.ASSOCIATED_DATA,
                ("test.details",),
                properties=PropertySelection(("label",)),
            ),
        ),
        (DirectAssociation("owner", "detail"),),
        (PatternLink("relation", "owner", "detail", ("test.relates",)),),
    )
    result = query_graph(database, GraphQuery(selection))
    assert result.status is OperationStatus.ACCEPTED
    assert isinstance(result.payload, PatternQueryPayload)
    assert result.payload.matches[0].bindings == (("owner", A), ("detail", D1), ("relation", L1))
    assert result.payload.matches[1].bindings == (("owner", A), ("detail", D1), ("relation", L3))
    assert {value.uuid for value in result.payload.objects} == {A, D1, L1, L3}

    over_bound = query_graph(
        database,
        GraphQuery(
            PatternSelection(
                1,
                (PatternNode("owner", PatternNodeKind.ANCHOR, ("test.person",)),),
            )
        ),
    )
    assert over_bound.status is OperationStatus.REJECTED
    assert over_bound.payload is None
    assert over_bound.findings[0].code.value == "resultLimitExceeded"


def test_text_predicates_keep_exact_folded_regex_and_fts_meanings_distinct(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    base = PatternNode("owner", PatternNodeKind.ANCHOR, ("test.person",))
    data = PatternNode("data", PatternNodeKind.ASSOCIATED_DATA, ("test.details",))
    exact = _single_node_query(
        database,
        data,
        Predicate(
            PropertyField("label"),
            PredicateOperator.EQUAL,
            value=ScalarValue.text("Résumé Alpha"),
        ),
    )
    assert _bound_uuids(exact) == (D1,)
    code_point_order = _single_node_query(
        database,
        data,
        Predicate(
            PropertyField("label"),
            PredicateOperator.LESS_THAN,
            value=ScalarValue.text("resume beta"),
        ),
    )
    assert _bound_uuids(code_point_order) == (D1,)
    insensitive = _single_node_query(
        database,
        base,
        Predicate(DisplayNameField(), PredicateOperator.CONTAINS, text="café"),
    )
    assert _bound_uuids(insensitive) == (A,)
    sensitive = _single_node_query(
        database,
        base,
        Predicate(
            DisplayNameField(),
            PredicateOperator.CONTAINS,
            text="café",
            case_sensitive=True,
        ),
    )
    assert _bound_uuids(sensitive) == ()
    no_diacritic_removal = _single_node_query(
        database,
        base,
        Predicate(DisplayNameField(), PredicateOperator.CONTAINS, text="cafe"),
    )
    assert _bound_uuids(no_diacritic_removal) == ()
    prefix = _single_node_query(
        database,
        base,
        Predicate(DisplayNameField(), PredicateOperator.PREFIX, text="CAFÉ"),
    )
    assert _bound_uuids(prefix) == (A,)
    regex = _single_node_query(
        database,
        base,
        Predicate(DisplayNameField(), PredicateOperator.REGEX, text="Owner$"),
    )
    assert _bound_uuids(regex) == (A,)
    full_text = _single_node_query(
        database,
        base,
        Predicate(DisplayNameField(), PredicateOperator.ALL_TERMS, terms=("cafe", "owner")),
    )
    assert _bound_uuids(full_text) == (A,)

    phrase = _single_node_query(
        database,
        PatternNode("detail", PatternNodeKind.ASSOCIATED_DATA, ("test.details",)),
        Predicate(PropertyField("label"), PredicateOperator.PHRASE, text="resume alpha"),
    )
    assert _bound_uuids(phrase) == (D1,)
    any_term = _single_node_query(
        database,
        PatternNode("detail", PatternNodeKind.ASSOCIATED_DATA, ("test.details",)),
        Predicate(
            PropertyField("label"),
            PredicateOperator.ANY_TERMS,
            terms=("alpha", "beta"),
        ),
    )
    assert _bound_uuids(any_term) == (D1, D2)

    data = PatternNode("detail", PatternNodeKind.ASSOCIATED_DATA, ("test.details",))
    score = _single_node_query(
        database,
        data,
        Predicate(
            PropertyField("score"),
            PredicateOperator.GREATER_THAN,
            value=ScalarValue.integer(6),
        ),
    )
    assert _bound_uuids(score) == (D2,)


@pytest.mark.parametrize(
    ("operator", "value", "expected"),
    (
        (PredicateOperator.PRESENT, None, (D1, D2)),
        (PredicateOperator.MISSING, None, ()),
        (PredicateOperator.IS_NULL, None, ()),
        (PredicateOperator.IS_NOT_NULL, None, (D1, D2)),
        (PredicateOperator.EQUAL, ScalarValue.integer(5), (D1,)),
        (PredicateOperator.NOT_EQUAL, ScalarValue.integer(5), (D2,)),
        (PredicateOperator.LESS_THAN, ScalarValue.integer(10), (D1,)),
        (PredicateOperator.LESS_THAN_OR_EQUAL, ScalarValue.integer(5), (D1,)),
        (PredicateOperator.GREATER_THAN_OR_EQUAL, ScalarValue.integer(10), (D2,)),
        (PredicateOperator.ANY_OF, (ScalarValue.integer(5), ScalarValue.integer(10)), (D1, D2)),
    ),
)
def test_property_predicate_closed_set(
    tmp_path: Path, operator: PredicateOperator, value, expected: tuple[str, ...]
) -> None:
    database = _database(tmp_path)
    node = PatternNode("detail", PatternNodeKind.ASSOCIATED_DATA, ("test.details",))
    if operator is PredicateOperator.ANY_OF:
        predicate = Predicate(PropertyField("score"), operator, values=value)
    elif value is None:
        predicate = Predicate(PropertyField("score"), operator)
    else:
        predicate = Predicate(PropertyField("score"), operator, value=value)
    assert _bound_uuids(_single_node_query(database, node, predicate)) == expected


def test_strict_numeric_boundary_rejects_an_inclusive_comparison_mutant(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    scores = {D1: 5, D2: 10}
    intended = tuple(uuid for uuid, score in scores.items() if score > 5)
    inclusive_mutant = tuple(uuid for uuid, score in scores.items() if score >= 5)
    assert intended != inclusive_mutant

    node = PatternNode("detail", PatternNodeKind.ASSOCIATED_DATA, ("test.details",))
    result = _single_node_query(
        database,
        node,
        Predicate(
            PropertyField("score"),
            PredicateOperator.GREATER_THAN,
            value=ScalarValue.integer(5),
        ),
    )
    assert _bound_uuids(result) == intended


def test_property_predicate_missing_type_keys_points_to_the_node_member(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    predicate = Predicate(
        PropertyField("score"),
        PredicateOperator.GREATER_THAN,
        value=ScalarValue.integer(5),
    )
    selection = PatternSelection(
        10,
        (PatternNode("detail", PatternNodeKind.ASSOCIATED_DATA, predicates=(predicate,)),),
    )
    result = query_graph(database, GraphQuery(selection))
    assert result.status is OperationStatus.REJECTED
    finding = next(item for item in result.findings if item.code.value == "missing")
    request = {
        "selection": {
            "nodes": [
                {
                    "name": "detail",
                    "kind": "associatedData",
                    "typeKeys": [],
                    "predicates": [{"field": {"name": "score"}, "operator": "greaterThan"}],
                }
            ]
        }
    }
    assert finding.path == "/selection/nodes/0/typeKeys"
    assert finding.path is not None
    assert _resolve_pointer(request, finding.path) == []


def test_null_presence_and_date_timestamp_number_ordering_are_distinct(tmp_path: Path) -> None:
    database = _database(tmp_path)
    node = PatternNode("detail", PatternNodeKind.ASSOCIATED_DATA, ("test.details",))
    null_result = _single_node_query(
        database,
        node,
        Predicate(PropertyField("nullable"), PredicateOperator.IS_NULL),
    )
    assert _bound_uuids(null_result) == (D1,)
    missing_result = _single_node_query(
        database,
        node,
        Predicate(PropertyField("nullable"), PredicateOperator.MISSING),
    )
    assert _bound_uuids(missing_result) == (D2,)
    boolean_result = _single_node_query(
        database,
        node,
        Predicate(
            PropertyField("flag"),
            PredicateOperator.EQUAL,
            value=ScalarValue.boolean(True),
        ),
    )
    assert _bound_uuids(boolean_result) == (D1,)
    for field, value in (
        ("quantity", ScalarValue.number(1.0)),
        ("due", ScalarValue.date("2026-01-02")),
        ("at", ScalarValue.timestamp("2026-01-01T23:59:59Z")),
    ):
        result = _single_node_query(
            database,
            node,
            Predicate(PropertyField(field), PredicateOperator.GREATER_THAN, value=value),
        )
        assert _bound_uuids(result) == (D1,)


def test_invalid_or_disconnected_query_rejects_wholly(tmp_path: Path) -> None:
    database = _database(tmp_path)
    disconnected = PatternSelection(
        10,
        (
            PatternNode("a", PatternNodeKind.ANCHOR),
            PatternNode("b", PatternNodeKind.ANCHOR),
        ),
    )
    result = query_graph(database, GraphQuery(disconnected))
    assert result.status is OperationStatus.REJECTED
    assert result.payload is None

    untyped_property = PatternSelection(
        10,
        (
            PatternNode(
                "data",
                PatternNodeKind.ASSOCIATED_DATA,
                predicates=(
                    Predicate(
                        PropertyField("label"),
                        PredicateOperator.REGEX,
                        text="(",
                    ),
                ),
            ),
        ),
    )
    result = query_graph(database, GraphQuery(untyped_property))
    assert result.status is OperationStatus.REJECTED
    assert result.payload is None
    assert {finding.code.value for finding in result.findings} >= {"missing"}

    malformed_regex = PatternSelection(
        10,
        (
            PatternNode(
                "data",
                PatternNodeKind.ASSOCIATED_DATA,
                ("test.details",),
                predicates=(
                    Predicate(
                        PropertyField("label"),
                        PredicateOperator.REGEX,
                        text="(",
                    ),
                ),
            ),
        ),
    )
    result = query_graph(database, GraphQuery(malformed_regex))
    assert result.status is OperationStatus.REJECTED
    assert {finding.code.value for finding in result.findings} == {"invalidValue"}

    duplicate_association = PatternSelection(
        10,
        (
            PatternNode("a", PatternNodeKind.ANCHOR),
            PatternNode("d", PatternNodeKind.ASSOCIATED_DATA),
        ),
        (DirectAssociation("a", "d"), DirectAssociation("a", "d")),
    )
    result = query_graph(database, GraphQuery(duplicate_association))
    assert result.status is OperationStatus.REJECTED
    assert {finding.code.value for finding in result.findings} == {"duplicate"}

    unknown_uuid = PatternSelection(
        10,
        (PatternNode("a", PatternNodeKind.ANCHOR, uuids=(MISSING,)),),
    )
    result = query_graph(database, GraphQuery(unknown_uuid))
    assert result.status is OperationStatus.REJECTED
    assert result.payload is None
    assert result.findings[0].code.value == "unknown"

    anchor_properties = query_graph(
        database,
        GraphQuery(IdentitySelection((IdentityObjectSelection(A, PropertySelection(("label",))),))),
    )
    assert anchor_properties.status is OperationStatus.REJECTED
    assert anchor_properties.payload is None


def test_structured_full_text_rejects_multi_token_terms_without_raw_syntax(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    node = PatternNode("owner", PatternNodeKind.ANCHOR, ("test.person",))
    result = _single_node_query(
        database,
        node,
        Predicate(DisplayNameField(), PredicateOperator.ALL_TERMS, terms=("cafe OR owner",)),
    )
    assert result.status is OperationStatus.REJECTED
    assert result.payload is None
    assert "exactly one token" in result.findings[0].summary


def test_historical_query_uses_selected_intervals_for_graph_and_search(tmp_path: Path) -> None:
    database = _database(tmp_path)
    current = GraphQuery(
        PatternSelection(
            10,
            (
                PatternNode(
                    "owner",
                    PatternNodeKind.ANCHOR,
                    predicates=(
                        Predicate(
                            DisplayNameField(),
                            PredicateOperator.ALL_TERMS,
                            terms=("cafe",),
                        ),
                    ),
                ),
            ),
        )
    )
    assert _bound_uuids(query_graph(database, current)) == (A,)
    historical = GraphQuery(current.selection, RevisionState(0))
    assert _bound_uuids(query_graph(database, historical)) == ()
    before_zero = GraphQuery(
        current.selection,
        state=TimeState(parse_timestamp("2025-12-31T23:59:59Z")),
    )
    assert query_graph(database, before_zero).status is OperationStatus.REJECTED


def test_bound_is_checked_before_hydration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = _database(tmp_path)

    connection = connect_database(database, read_only=True)
    traced: list[str] = []
    try:
        connection.set_trace_callback(traced.append)
        selected = PatternSelection(
            1,
            (PatternNode("owner", PatternNodeKind.ANCHOR, ("test.person",)),),
        )
        assert (
            query_repository.select_pattern_bindings(
                connection, read_operations.resolve_state(connection), selected
            )
            is None
        )
        binding_sql = next(value for value in traced if value.startswith("WITH n0"))
        plan = connection.execute(f"EXPLAIN QUERY PLAN {binding_sql}").fetchall()
        assert all("ORDER BY" not in str(row[3]) for row in plan)
    finally:
        connection.close()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("hydration ran before limit rejection")

    monkeypatch.setattr(read_operations, "load_hydrated_objects", forbidden)
    result = query_graph(
        database,
        GraphQuery(
            PatternSelection(
                1,
                (PatternNode("owner", PatternNodeKind.ANCHOR, ("test.person",)),),
            )
        ),
    )
    assert result.status is OperationStatus.REJECTED
    assert result.findings[0].code.value == "resultLimitExceeded"


def test_selected_property_hydration_never_decodes_unrequested_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path)
    original = query_repository.property_from_row
    decoded: list[str] = []

    def observed(row):
        decoded.append(str(row["property_name"]))
        return original(row)

    monkeypatch.setattr(query_repository, "property_from_row", observed)
    result = query_graph(
        database,
        GraphQuery(
            IdentitySelection((IdentityObjectSelection(D1, PropertySelection(("label",))),))
        ),
    )
    assert result.status is OperationStatus.ACCEPTED
    assert decoded == ["label"]


def test_current_discovery_does_not_decode_unrelated_definitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path)
    original_definition = definition_repository._definition_from_row
    decoded_types: list[str] = []

    def observed_definition(row, permitted, properties):
        decoded_types.append(str(row["type_key"]))
        return original_definition(row, permitted, properties)

    monkeypatch.setattr(definition_repository, "_definition_from_row", observed_definition)
    summary = type_summary(database)
    assert summary.status is OperationStatus.ACCEPTED
    assert decoded_types == ["test.person", "test.project"]


def test_sql_topology_matches_independent_oracle_and_catches_distinctness_mutant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path)
    selections = (
        PatternSelection(10, (PatternNode("one", PatternNodeKind.ANCHOR),)),
        PatternSelection(
            10,
            (
                PatternNode("a", PatternNodeKind.ANCHOR, uuids=(A,)),
                PatternNode("d", PatternNodeKind.ASSOCIATED_DATA),
            ),
            (DirectAssociation("a", "d"),),
        ),
        PatternSelection(
            10,
            (PatternNode("a", PatternNodeKind.ANCHOR, uuids=(A,)),),
            links=(PatternLink("self", "a", "a"),),
        ),
        PatternSelection(
            10,
            (
                PatternNode("a", PatternNodeKind.ANCHOR, uuids=(A,)),
                PatternNode("d", PatternNodeKind.ASSOCIATED_DATA, uuids=(D1,)),
            ),
            links=(
                PatternLink("forward", "a", "d"),
                PatternLink("reverse", "d", "a"),
            ),
        ),
        PatternSelection(
            10,
            (
                PatternNode("a", PatternNodeKind.ANCHOR, uuids=(A,)),
                PatternNode("d", PatternNodeKind.ASSOCIATED_DATA, uuids=(D1,)),
                PatternNode("p", PatternNodeKind.ANCHOR, uuids=(P,)),
            ),
            (DirectAssociation("a", "d"),),
            (
                PatternLink("detailLink", "a", "d"),
                PatternLink("projectLink", "a", "p"),
            ),
        ),
    )
    graph = _graph()
    for selection in selections:
        result = query_graph(database, GraphQuery(selection))
        assert isinstance(result.payload, PatternQueryPayload)
        assert result.payload.matches == evaluate_pattern(selection, graph)

    distinct = PatternSelection(
        10,
        (
            PatternNode("left", PatternNodeKind.ANCHOR, uuids=(A,)),
            PatternNode("right", PatternNodeKind.ANCHOR, uuids=(A,)),
        ),
        links=(PatternLink("edge", "left", "right", uuids=(L2,)),),
    )
    assert evaluate_pattern(distinct, graph) == ()
    original_conditions = query_repository._node_join_conditions

    def without_distinctness(state, selection, node_indexes, node_index, added):
        conditions, parameters = original_conditions(
            state, selection, node_indexes, node_index, added
        )
        return [value for value in conditions if "<>" not in value], parameters

    monkeypatch.setattr(query_repository, "_node_join_conditions", without_distinctness)
    mutant = query_graph(database, GraphQuery(distinct))
    assert isinstance(mutant.payload, PatternQueryPayload)
    assert mutant.payload.matches != evaluate_pattern(distinct, graph)


def test_connected_pattern_above_sqlites_flat_join_limit_is_a_domain_result(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    nodes = tuple(PatternNode(f"node{index}", PatternNodeKind.ANCHOR) for index in range(65))
    links = tuple(
        PatternLink(f"link{index}", f"node{index}", f"node{index + 1}") for index in range(64)
    )
    selection = PatternSelection(10, nodes, links=links)
    result = query_graph(database, GraphQuery(selection))
    assert result.status is OperationStatus.ACCEPTED
    assert isinstance(result.payload, PatternQueryPayload)
    assert result.payload.matches == ()
    binding_ctes, _, final_name = query_repository._binding_ctes(ResolvedState(1), selection)
    assert all("AS MATERIALIZED" in value for value in binding_ctes[:-1])
    assert binding_ctes[-1].startswith(f"{final_name} AS (")


def test_case_sensitive_payload_is_rejected_for_non_text_operator(tmp_path: Path) -> None:
    database = _database(tmp_path)
    result = _single_node_query(
        database,
        PatternNode("data", PatternNodeKind.ASSOCIATED_DATA, ("test.details",)),
        Predicate(
            PropertyField("score"),
            PredicateOperator.EQUAL,
            value=ScalarValue.integer(5),
            case_sensitive=True,
        ),
    )
    assert result.status is OperationStatus.REJECTED
    assert any(value.path and value.path.endswith("/caseSensitive") for value in result.findings)


def test_definition_incompatible_relationship_endpoints_reject_wholly(tmp_path: Path) -> None:
    person_only_uuid = "20000000-0000-4000-8000-000000000003"
    data_source_link_uuid = "30000000-0000-4000-8000-000000000006"
    person_only = AssociatedDataTypeDefinition(
        "test.personOnly",
        "Person-only data",
        ("test.person",),
        (),
        Cardinality(1),
        Cardinality(0),
    )
    data_source = LinkTypeDefinition(
        "test.dataSource",
        "Data source only",
        ("test.personOnly",),
        ("test.person",),
        Cardinality(0),
        Cardinality(0),
    )
    database = initialized_query_database(
        tmp_path / "data" / "vellis.db",
        (*_definitions(), person_only, data_source),
        (
            *_graph(),
            AssociatedData(person_only_uuid, "test.personOnly", (A,), ()),
            Link(data_source_link_uuid, "test.dataSource", person_only_uuid, A),
        ),
    )
    direct = PatternSelection(
        10,
        (
            PatternNode("project", PatternNodeKind.ANCHOR, ("test.project",)),
            PatternNode("data", PatternNodeKind.ASSOCIATED_DATA, ("test.personOnly",)),
        ),
        (DirectAssociation("project", "data"),),
    )
    link = PatternSelection(
        10,
        (
            PatternNode("source", PatternNodeKind.ANCHOR),
            PatternNode("target", PatternNodeKind.ANCHOR, ("test.person",)),
        ),
        links=(PatternLink("edge", "source", "target", ("test.dataSource",)),),
    )
    identity_direct = PatternSelection(
        10,
        (
            PatternNode("project", PatternNodeKind.ANCHOR, uuids=(P,)),
            PatternNode("data", PatternNodeKind.ASSOCIATED_DATA, uuids=(person_only_uuid,)),
        ),
        (DirectAssociation("project", "data"),),
    )
    identity_link = PatternSelection(
        10,
        (
            PatternNode("source", PatternNodeKind.ANCHOR, uuids=(A,)),
            PatternNode("target", PatternNodeKind.ANCHOR, uuids=(A,)),
        ),
        links=(
            PatternLink(
                "edge",
                "source",
                "target",
                uuids=(data_source_link_uuid,),
            ),
        ),
    )
    for selection in (direct, link, identity_direct, identity_link):
        result = query_graph(database, GraphQuery(selection))
        assert result.status is OperationStatus.REJECTED
        assert result.payload is None
        assert {value.code.value for value in result.findings} == {"kindMismatch"}

    untyped_database = initialized_query_database(
        tmp_path / "untyped" / "vellis.db",
        (
            AnchorTypeDefinition("test.person", "Person"),
            AnchorTypeDefinition("test.project", "Project"),
            person_only,
            data_source,
        ),
        (),
    )
    untyped_link = PatternSelection(
        10,
        (
            PatternNode("source", PatternNodeKind.ANCHOR, ("test.person",)),
            PatternNode("target", PatternNodeKind.ANCHOR, ("test.person",)),
        ),
        links=(PatternLink("edge", "source", "target"),),
    )
    result = query_graph(untyped_database, GraphQuery(untyped_link))
    assert result.status is OperationStatus.REJECTED
    assert result.payload is None
    assert {value.code.value for value in result.findings} == {"kindMismatch"}

    impossible_untyped_data = PatternSelection(
        10,
        (
            PatternNode("project", PatternNodeKind.ANCHOR, ("test.project",)),
            PatternNode("data", PatternNodeKind.ASSOCIATED_DATA),
        ),
        (DirectAssociation("project", "data"),),
    )
    result = query_graph(untyped_database, GraphQuery(impossible_untyped_data))
    assert result.status is OperationStatus.REJECTED
    assert result.payload is None
    assert {value.code.value for value in result.findings} == {"kindMismatch"}

    valid_untyped_target = PatternSelection(
        10,
        (
            PatternNode("source", PatternNodeKind.ASSOCIATED_DATA, ("test.personOnly",)),
            PatternNode("target", PatternNodeKind.ANCHOR),
        ),
        links=(PatternLink("edge", "source", "target"),),
    )
    result = query_graph(untyped_database, GraphQuery(valid_untyped_target))
    assert result.status is OperationStatus.ACCEPTED
    assert isinstance(result.payload, PatternQueryPayload)
    assert result.payload.matches == ()


def test_large_untyped_link_definition_closure_uses_bounded_sql_parameters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    link_definitions = tuple(
        LinkTypeDefinition(
            f"test.link{index}",
            f"Link {index}",
            ("test.person",),
            ("test.project",),
            Cardinality(0),
            Cardinality(0),
        )
        for index in range(12)
    )
    database = initialized_query_database(
        tmp_path / "large-closure" / "vellis.db",
        (
            AnchorTypeDefinition("test.person", "Person"),
            AnchorTypeDefinition("test.project", "Project"),
            *link_definitions,
        ),
        (),
    )
    original_connect = read_operations.connect_database

    def limited_connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 12)
        return connection

    monkeypatch.setattr(read_operations, "connect_database", limited_connect)
    selection = PatternSelection(
        10,
        (
            PatternNode("person", PatternNodeKind.ANCHOR, ("test.person",)),
            PatternNode("project", PatternNodeKind.ANCHOR, ("test.project",)),
        ),
        links=(PatternLink("edge", "person", "project"),),
    )
    result = query_graph(database, GraphQuery(selection))
    assert result.status is OperationStatus.ACCEPTED
    assert isinstance(result.payload, PatternQueryPayload)
    assert result.payload.matches == ()


def test_maximum_size_any_of_uses_bounded_sql_for_properties_and_names(tmp_path: Path) -> None:
    database = _database(tmp_path)
    property_values = tuple(ScalarValue.integer(value) for value in range(1_000))
    property_result = _single_node_query(
        database,
        PatternNode("data", PatternNodeKind.ASSOCIATED_DATA, ("test.details",)),
        Predicate(PropertyField("score"), PredicateOperator.ANY_OF, values=property_values),
    )
    assert _bound_uuids(property_result) == (D1, D2)

    display_values = tuple(
        ScalarValue.text("Café Owner" if value == 0 else f"display-{value}")
        for value in range(1_000)
    )
    display_result = _single_node_query(
        database,
        PatternNode("anchor", PatternNodeKind.ANCHOR),
        Predicate(DisplayNameField(), PredicateOperator.ANY_OF, values=display_values),
    )
    assert _bound_uuids(display_result) == (A,)


def _single_node_query(database: Path, node: PatternNode, predicate: Predicate):
    selected = PatternNode(
        node.name,
        node.kind,
        node.type_keys,
        node.uuids,
        (predicate,),
        node.properties,
        node.include_legacy_system,
    )
    return query_graph(database, GraphQuery(PatternSelection(10, (selected,))))


def _bound_uuids(result) -> tuple[str, ...]:
    assert result.status is OperationStatus.ACCEPTED
    assert isinstance(result.payload, PatternQueryPayload)
    return tuple(match.bindings[0][1] for match in result.payload.matches)


def _database(tmp_path: Path) -> Path:
    return initialized_query_database(tmp_path / "data" / "vellis.db", _definitions(), _graph())


def _definitions():
    properties = (
        PropertyDefinition("flag", "Flag", ValueKind.BOOLEAN),
        PropertyDefinition("label", "Label", ValueKind.TEXT),
        PropertyDefinition("nullable", "Nullable", ValueKind.TEXT, nullable=True),
        PropertyDefinition("score", "Score", ValueKind.INTEGER),
        PropertyDefinition("quantity", "Quantity", ValueKind.NUMBER),
        PropertyDefinition("due", "Due date", ValueKind.DATE),
        PropertyDefinition("at", "Timestamp", ValueKind.TIMESTAMP),
    )
    return (
        AnchorTypeDefinition("test.person", "Person"),
        AnchorTypeDefinition("test.project", "Project"),
        AssociatedDataTypeDefinition(
            "test.details",
            "Details",
            ("test.person", "test.project"),
            properties,
            Cardinality(1),
            Cardinality(0),
        ),
        LinkTypeDefinition(
            "test.relates",
            "Relates endpoints",
            ("test.person", "test.project", "test.details"),
            ("test.person", "test.project", "test.details"),
            Cardinality(0),
            Cardinality(0),
        ),
    )


def _graph():
    return (
        Anchor(A, "test.person", "Café Owner"),
        Anchor(B, "test.person", "Other Person"),
        Anchor(P, "test.project", "Project"),
        AssociatedData(
            D1,
            "test.details",
            (A,),
            (
                ("at", ScalarValue.timestamp("2026-01-02T00:00:00Z")),
                ("due", ScalarValue.date("2026-01-03")),
                ("flag", ScalarValue.boolean(True)),
                ("label", ScalarValue.text("Résumé Alpha")),
                ("nullable", None),
                ("quantity", ScalarValue.number(1.5)),
                ("score", ScalarValue.integer(5)),
            ),
        ),
        AssociatedData(
            D2,
            "test.details",
            (B,),
            (
                ("flag", ScalarValue.boolean(False)),
                ("label", ScalarValue.text("resume beta")),
                ("score", ScalarValue.integer(10)),
            ),
        ),
        Link(L1, "test.relates", A, D1),
        Link(L2, "test.relates", A, A),
        Link(L3, "test.relates", A, D1),
        Link(L4, "test.relates", D1, A),
        Link(L5, "test.relates", A, P),
    )
