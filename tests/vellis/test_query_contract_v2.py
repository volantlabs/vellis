"""Focused W003 evidence for the closed positive-pattern query contract and analyzer."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from random import Random

import pytest
from pydantic import TypeAdapter, ValidationError

from tests.vellis.oracle import evaluate_query
from tests.vellis.oracle import row_identity as oracle_row_identity
from vellis.canonical import Provenance
from vellis.changes import GraphChange
from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    EndpointConstraint,
    GraphDefinitionSet,
    LinkTypeDefinition,
    PropertyConstraint,
)
from vellis.graph import Anchor, AssociatedDataObject, Graph, Link
from vellis.history import CurrentSelection
from vellis.json_value import JsonKind
from vellis.outcomes import OperationStatus
from vellis.patterns import compile_pattern
from vellis.query import (
    AggregateQueryOutput,
    AggregationOperator,
    AnchorGroup,
    AnchorProjection,
    AssociatedDataCondition,
    DataPropertyCondition,
    DataPropertyProjection,
    GraphQuery,
    LinkProjection,
    PropertyComparison,
    QueryAggregation,
    RequiredLink,
    ReturnedProperty,
    ReturnProjection,
    RowQueryOutput,
    UuidFilter,
    analyze_graph_query,
    semantic_row_identity,
)
from vellis.system import RTGSystem


def _definitions() -> GraphDefinitionSet:
    endpoint = EndpointConstraint(
        permitted_source_type_keys=("person", "note"),
        permitted_target_type_keys=("person", "note"),
        description="Any selected endpoint may relate to another.",
    )
    return GraphDefinitionSet(
        anchor_types=(AnchorTypeDefinition("person", "A person."),),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                "note",
                permitted_anchor_type_keys=("person",),
                property_constraints=(
                    PropertyConstraint("text", False, JsonKind.STRING, description="Note text."),
                ),
                description="A note.",
            ),
        ),
        link_types=(LinkTypeDefinition("relates", endpoint, "A relation."),),
    )


def _pattern() -> GraphQuery:
    return GraphQuery(
        anchor_groups=(
            AnchorGroup("a", ("person",)),
            AnchorGroup("b", ("person",)),
        ),
        data_conditions=(
            AssociatedDataCondition(
                "d",
                "a",
                "note",
                property_conditions=(
                    DataPropertyCondition("text", PropertyComparison.MATCHES_PATTERN, "(?s).*"),
                ),
            ),
        ),
        required_links=(
            RequiredLink("parallelOne", "a", "b", "relates"),
            RequiredLink("parallelTwo", "a", "b", "relates"),
            RequiredLink("self", "a", "a", "relates"),
            RequiredLink("cycleClose", "b", "d", "relates"),
        ),
        output=RowQueryOutput(
            kind="rows",
            projections=(
                AnchorProjection("anchor", "a"),
                DataPropertyProjection("text", "d", "text"),
            ),
            maximum_rows=20,
        ),
    )


def test_analyzer_accepts_parallel_self_link_and_cyclic_positive_predicates() -> None:
    analyzed, findings = analyze_graph_query(_pattern(), _definitions())

    assert findings == ()
    assert analyzed is not None
    assert analyzed.answer_variables == ("a", "d")
    assert analyzed.existential_variables == ("b",)
    assert analyzed.existential_links == (
        "parallelOne",
        "parallelTwo",
        "self",
        "cycleClose",
    )
    assert {predicate.kind for predicate in analyzed.predicates} >= {
        "anchorType",
        "dataType",
        "directAssociation",
        "property",
        "requiredLink",
    }


def test_explicit_variants_are_tagged_and_request_objects_are_closed() -> None:
    adapter = TypeAdapter(GraphQuery)
    query = _pattern()
    payload = {
        "anchor_groups": [{"name": "a", "anchor_types": ["person"]}],
        "output": {
            "kind": "rows",
            "projections": [{"name": "a", "anchor_group": "a"}],
            "maximum_rows": 10,
        },
    }

    parsed = adapter.validate_python(payload)
    assert parsed.state == CurrentSelection(kind="current")
    with pytest.raises(ValidationError):
        adapter.validate_python({**payload, "state": {}})
    with pytest.raises(ValidationError):
        adapter.validate_python({**payload, "maximum_rows": 10})
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                **payload,
                "output": {**payload["output"], "aggregations": []},
            }
        )
    assert query.output.kind == "rows"


def test_empty_uuid_filter_is_semantic_invalidity_after_typed_construction() -> None:
    query = GraphQuery(
        anchor_groups=(AnchorGroup("a", ("person",), UuidFilter(())),),
        output=RowQueryOutput(
            kind="rows", projections=(AnchorProjection("a", "a"),), maximum_rows=1
        ),
    )

    analyzed, findings = analyze_graph_query(query, _definitions())
    assert analyzed is None
    assert any("empty UUID restriction" in finding.summary for finding in findings)


def test_property_row_identity_includes_its_source_object() -> None:
    from vellis.query import GraphQueryRow

    first = GraphQueryRow(properties=(ReturnedProperty("text", "d-1", True, Decimal(1)),))
    second = GraphQueryRow(properties=(ReturnedProperty("text", "d-2", True, Decimal("1.0")),))

    assert semantic_row_identity(first) != semantic_row_identity(second)


def test_oracle_value_identity_does_not_share_production_kind_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A production Boolean/number kind collapse cannot make the oracle agree with it."""
    import vellis.json_value as json_value_module
    from vellis.query import GraphQueryRow

    monkeypatch.setattr(json_value_module, "json_kind", lambda value: JsonKind.NULL)
    boolean = GraphQueryRow(properties=(ReturnedProperty("value", "d", True, True),))
    number = GraphQueryRow(properties=(ReturnedProperty("value", "d", True, Decimal(1)),))

    assert oracle_row_identity(boolean) != oracle_row_identity(number)


def test_sqlite_compiler_matches_parallel_self_and_cyclic_pattern(tmp_path: Path) -> None:
    """Hidden relationship aliases prove existence without multiplying the one answer."""
    system = RTGSystem.open(tmp_path / "positive-pattern.sqlite3")
    owner = Provenance(initiator="owner")
    assert system.initialize_fresh(
        _definitions(), provenance=owner, initialization_summary="compiler fixture"
    ).accepted
    anchors = (Anchor("a", "person", "A"), Anchor("b", "person", "B"))
    data = (
        AssociatedDataObject("d", "note", ("a",), {"text": "hello"}),
        AssociatedDataObject("d2", "note", ("a",), {"text": "hello"}),
    )
    links = (
        Link("parallel", "relates", "a", "b"),
        Link("parallel2", "relates", "a", "b"),
        Link("self", "relates", "a", "a"),
        Link("close", "relates", "b", "d"),
    )
    graph = Graph(anchors=anchors, associated_data=data, links=links)
    changed = system.apply_graph_change(
        GraphChange(
            anchor_upserts=anchors,
            associated_data_upserts=data,
            link_upserts=links,
        ),
        provenance=owner,
    )
    assert changed.accepted, changed.findings
    try:
        result = system.query_graph(_pattern(), provenance=owner)
        assert result.accepted, result.findings
        assert len(result.rows) == 1
        assert result.rows[0].anchors[0].anchor.uuid == "a"
        assert result.rows[0].properties == (ReturnedProperty("text", "d", True, "hello"),)
        oracle = evaluate_query(_pattern(), _definitions(), graph, result.evaluated_revision or -1)
        assert result.rows == oracle.rows

        source_rows = system.query_graph(
            GraphQuery(
                anchor_groups=(AnchorGroup("a", ("person",), UuidFilter(("a",))),),
                data_conditions=(AssociatedDataCondition("d", "a", "note"),),
                output=RowQueryOutput(
                    kind="rows",
                    projections=(DataPropertyProjection("text", "d", "text"),),
                    maximum_rows=3,
                ),
            ),
            provenance=owner,
        )
        assert source_rows.accepted, source_rows.findings
        assert {row.properties[0].associated_data_uuid for row in source_rows.rows} == {"d", "d2"}

        aggregates = system.query_graph(
            GraphQuery(
                anchor_groups=(
                    AnchorGroup("a", ("person",), UuidFilter(("a",))),
                    AnchorGroup("b", ("person",), UuidFilter(("b",))),
                ),
                data_conditions=(AssociatedDataCondition("d", "a", "note"),),
                required_links=(RequiredLink("witness", "a", "b", "relates"),),
                output=AggregateQueryOutput(
                    kind="aggregates",
                    data_condition="d",
                    aggregations=(QueryAggregation("count", AggregationOperator.COUNT),),
                    maximum_matches=3,
                ),
            ),
            provenance=owner,
        )
        assert aggregates.accepted, aggregates.findings
        assert aggregates.aggregates[0].value == Decimal(2)
        oracle_aggregates = evaluate_query(
            aggregates.query, _definitions(), graph, aggregates.evaluated_revision or -1
        )
        assert aggregates.aggregates == oracle_aggregates.aggregates
    finally:
        system.close()


def test_pattern_matching_visits_only_relationally_relevant_candidates(tmp_path: Path) -> None:
    """Same-type, same-property rows outside the selected anchor add no query work."""

    def measured(population: int, *, project_anchor: bool) -> tuple[int, int]:
        mode = "projected" if project_anchor else "hidden"
        system = RTGSystem.open(tmp_path / f"pattern-locality-{mode}-{population}.sqlite3")
        owner = Provenance(initiator="owner")
        assert system.initialize_fresh(
            _definitions(), provenance=owner, initialization_summary="pattern locality"
        ).accepted
        anchors = (Anchor("a", "person", "A"),) + tuple(
            Anchor(f"other-{index}", "person", "Other") for index in range(population)
        )
        data = (AssociatedDataObject("wanted", "note", ("a",), {"text": "match"}),) + tuple(
            AssociatedDataObject(
                f"other-note-{index}",
                "note",
                (f"other-{index}",),
                {"text": "match"},
            )
            for index in range(population)
        )
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=anchors, associated_data_upserts=data), provenance=owner
        ).accepted
        calls = 0
        steps = 0
        compiled = compile_pattern("match")

        def counted(value: object, expression: object) -> int:
            nonlocal calls
            calls += 1
            return int(isinstance(value, str) and expression == "match" and compiled.matches(value))

        def progress() -> int:
            nonlocal steps
            steps += 1
            return 0

        system.store._connection.create_function(  # noqa: SLF001
            "vellis_re2_full_match", 2, counted, deterministic=True
        )
        system.store._connection.set_progress_handler(progress, 1)  # noqa: SLF001
        projections: tuple[ReturnProjection, ...] = (DataPropertyProjection("text", "d", "text"),)
        if project_anchor:
            projections = (AnchorProjection("anchor", "a"), *projections)
        query = GraphQuery(
            anchor_groups=(AnchorGroup("a", ("person",), UuidFilter(("a",))),),
            data_conditions=(
                AssociatedDataCondition(
                    "d",
                    "a",
                    "note",
                    property_conditions=(
                        DataPropertyCondition("text", PropertyComparison.MATCHES_PATTERN, "match"),
                    ),
                ),
            ),
            output=RowQueryOutput(
                kind="rows",
                projections=projections,
                maximum_rows=2,
            ),
        )
        try:
            result = system.store.evaluate_current_query(query)
            assert result.accepted, result.findings
            assert len(result.rows) == 1
            return steps, calls
        finally:
            system.store._connection.set_progress_handler(None, 0)  # noqa: SLF001
            system.close()

    for project_anchor in (False, True):
        costs = [
            measured(population, project_anchor=project_anchor) for population in (10, 100, 500)
        ]
        assert [calls for _, calls in costs] == [1, 1, 1]
        assert len({steps for steps, _ in costs}) == 1


def test_hidden_witness_fanout_does_not_form_a_quadratic_product(tmp_path: Path) -> None:
    """Two hidden link aliases stop after one joint witness for the projected identity."""

    def measured(fanout: int) -> tuple[int, int]:
        system = RTGSystem.open(tmp_path / f"hidden-fanout-{fanout}.sqlite3")
        owner = Provenance(initiator="owner")
        assert system.initialize_fresh(
            _definitions(), provenance=owner, initialization_summary="hidden fanout"
        ).accepted
        anchors = (Anchor("a", "person", "A"), Anchor("b", "person", "B"))
        links = tuple(Link(f"link-{index}", "relates", "a", "b") for index in range(fanout))
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=anchors, link_upserts=links), provenance=owner
        ).accepted
        query = GraphQuery(
            anchor_groups=(
                AnchorGroup("a", ("person",), UuidFilter(("a",))),
                AnchorGroup("b", ("person",), UuidFilter(("b",))),
            ),
            required_links=(
                RequiredLink("one", "a", "b", "relates"),
                RequiredLink("two", "a", "b", "relates"),
            ),
            output=RowQueryOutput(
                kind="rows",
                projections=(AnchorProjection("answer", "a"),),
                maximum_rows=2,
            ),
        )
        steps = 0

        def progress() -> int:
            nonlocal steps
            steps += 1
            return 0

        system.store.reset_instrumentation()
        system.store._connection.set_progress_handler(progress, 1)  # noqa: SLF001
        try:
            result = system.store.evaluate_current_query(query)
        finally:
            system.store._connection.set_progress_handler(None, 0)  # noqa: SLF001
            decoded = system.store.current_graph_object_decodes
            system.close()
        assert result.accepted, result.findings
        assert len(result.rows) == 1
        return steps, decoded

    costs = [measured(fanout) for fanout in (10, 20, 40)]
    steps = [cost[0] for cost in costs]
    assert [cost[1] for cost in costs] == [1, 1, 1]
    assert steps[1] < steps[0] * 3
    assert steps[2] < steps[1] * 3


def test_aggregate_hidden_witness_fanout_counts_each_target_once(tmp_path: Path) -> None:
    """Aggregate work follows target identities, not pairs of hidden link witnesses."""

    def measured(fanout: int) -> tuple[int, Decimal]:
        system = RTGSystem.open(tmp_path / f"aggregate-hidden-fanout-{fanout}.sqlite3")
        owner = Provenance(initiator="owner")
        assert system.initialize_fresh(
            _definitions(), provenance=owner, initialization_summary="aggregate hidden fanout"
        ).accepted
        anchors = (Anchor("a", "person", "A"), Anchor("b", "person", "B"))
        data = (AssociatedDataObject("d", "note", ("a",), {"text": "answer"}),)
        links = tuple(Link(f"link-{index}", "relates", "a", "b") for index in range(fanout))
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=anchors,
                associated_data_upserts=data,
                link_upserts=links,
            ),
            provenance=owner,
        ).accepted
        query = GraphQuery(
            anchor_groups=(
                AnchorGroup("a", ("person",), UuidFilter(("a",))),
                AnchorGroup("b", ("person",), UuidFilter(("b",))),
            ),
            data_conditions=(AssociatedDataCondition("d", "a", "note"),),
            required_links=(
                RequiredLink("one", "a", "b", "relates"),
                RequiredLink("two", "a", "b", "relates"),
            ),
            output=AggregateQueryOutput(
                kind="aggregates",
                data_condition="d",
                aggregations=(QueryAggregation("count", AggregationOperator.COUNT),),
                maximum_matches=2,
            ),
        )
        steps = 0

        def progress() -> int:
            nonlocal steps
            steps += 1
            return 0

        system.store._connection.set_progress_handler(progress, 1)  # noqa: SLF001
        try:
            result = system.store.evaluate_current_query(query)
        finally:
            system.store._connection.set_progress_handler(None, 0)  # noqa: SLF001
            system.close()
        assert result.accepted, result.findings
        value = result.aggregates[0].value
        assert isinstance(value, Decimal)
        assert value == Decimal(1)
        return steps, value

    costs = [measured(fanout) for fanout in (10, 20, 40)]
    steps = [cost[0] for cost in costs]
    assert [value for _, value in costs] == [Decimal(1), Decimal(1), Decimal(1)]
    assert steps[1] < steps[0] * 3
    assert steps[2] < steps[1] * 3


def test_independent_oracle_detects_a_mutated_compiler_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The oracle does not share the production predicate compiler it checks."""
    import vellis.sqlite_query as sqlite_query

    system = RTGSystem.open(tmp_path / "mutated-compiler.sqlite3")
    owner = Provenance(initiator="owner")
    assert system.initialize_fresh(
        _definitions(), provenance=owner, initialization_summary="oracle independence"
    ).accepted
    anchors = (Anchor("a", "person", "A"), Anchor("b", "person", "B"))
    data = (AssociatedDataObject("d", "note", ("a",), {"text": "hello"}),)
    links = (
        Link("parallel", "relates", "a", "b"),
        Link("parallel2", "relates", "a", "b"),
        Link("self", "relates", "a", "a"),
        Link("close", "relates", "b", "d"),
    )
    graph = Graph(anchors=anchors, associated_data=data, links=links)
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=anchors, associated_data_upserts=data, link_upserts=links),
        provenance=owner,
    ).accepted
    original = sqlite_query.compile_query

    def mutated(analysis, relations):
        compiled = original(analysis, relations)
        statement = compiled.populate_answer
        return replace(
            compiled,
            populate_answer=replace(
                statement,
                sql=statement.sql.replace(" LIMIT ?", " AND 0 LIMIT ?"),
            ),
        )

    monkeypatch.setattr(sqlite_query, "compile_query", mutated)
    try:
        production = system.query_graph(_pattern(), provenance=owner)
        oracle = evaluate_query(_pattern(), _definitions(), graph, revision=1)
        assert production.accepted and oracle.accepted
        assert production.rows != oracle.rows
        assert production.rows == ()
        assert len(oracle.rows) == 1
    finally:
        system.close()


def test_fixed_seed_positive_patterns_match_the_independent_oracle(tmp_path: Path) -> None:
    rng = Random(0x0B5E7)
    system = RTGSystem.open(tmp_path / "generated-patterns.sqlite3")
    owner = Provenance(initiator="owner")
    assert system.initialize_fresh(
        _definitions(), provenance=owner, initialization_summary="generated patterns"
    ).accepted
    anchors = tuple(Anchor(name, "person", name.upper()) for name in ("a", "b", "c"))
    data = (
        AssociatedDataObject("d1", "note", ("a",), {"text": "alpha"}),
        AssociatedDataObject("d2", "note", ("a", "b"), {"text": "beta"}),
    )
    links = tuple(
        Link(f"{source}-{target}", "relates", source, target)
        for source in ("a", "b", "c")
        for target in ("a", "b", "c")
    ) + (Link("a-b-second", "relates", "a", "b"),)
    graph = Graph(anchors=anchors, associated_data=data, links=links)
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=anchors, associated_data_upserts=data, link_upserts=links),
        provenance=owner,
    ).accepted
    try:
        for case in range(12):
            groups = tuple(AnchorGroup(name, ("person",)) for name in ("x", "y", "z"))
            conditions = (
                AssociatedDataCondition(
                    "d",
                    rng.choice(("x", "y", "z")),
                    "note",
                    property_conditions=(
                        DataPropertyCondition(
                            "text",
                            rng.choice(
                                (PropertyComparison.EQUAL, PropertyComparison.MATCHES_PATTERN)
                            ),
                            rng.choice(("alpha", "beta", "a.*", ".*")),
                        ),
                    ),
                ),
            )
            required = tuple(
                RequiredLink(
                    f"link-{index}",
                    rng.choice(("x", "y", "z", "d")),
                    rng.choice(("x", "y", "z", "d")),
                    "relates",
                )
                for index in range(rng.randrange(4))
            )
            if case % 3 == 0:
                output = AggregateQueryOutput(
                    kind="aggregates",
                    data_condition="d",
                    aggregations=(QueryAggregation("count", AggregationOperator.COUNT),),
                    maximum_matches=10,
                )
            else:
                projections: list[ReturnProjection] = [
                    AnchorProjection("first", rng.choice(("x", "y", "z")))
                ]
                if required and case % 2:
                    projections.append(LinkProjection("edge", rng.choice(required).name))
                if case % 4 == 0:
                    projections.append(DataPropertyProjection("text", "d", "text"))
                output = RowQueryOutput(
                    kind="rows", projections=tuple(projections), maximum_rows=1_000
                )
            query = GraphQuery(groups, output, required, conditions)
            production = system.store.evaluate_current_query(query)
            oracle = evaluate_query(query, _definitions(), graph, revision=1)
            assert production.status is oracle.status
            assert production.evaluated_revision == oracle.evaluated_revision
            assert {oracle_row_identity(row) for row in production.rows} == {
                oracle_row_identity(row) for row in oracle.rows
            }
            assert production.aggregates == oracle.aggregates
    finally:
        system.close()


def test_compiled_vdbe_capacity_excess_is_a_whole_typed_refusal(tmp_path: Path) -> None:
    system = RTGSystem.open(tmp_path / "capacity-vdbe.sqlite3")
    owner = Provenance(initiator="owner")
    assert system.initialize_fresh(
        _definitions(), provenance=owner, initialization_summary="capacity refusal"
    ).accepted
    before_revision = system.store.current_revision()
    before_records = system.store.canonical_record_count()
    connection = system.store._connection  # noqa: SLF001
    prior = connection.setlimit(sqlite3.SQLITE_LIMIT_VDBE_OP, 100)
    try:
        simple = system.store.evaluate_current_query(
            GraphQuery(
                (AnchorGroup("a", ("person",)),),
                RowQueryOutput("rows", (AnchorProjection("answer", "a"),), 1),
            )
        )
        result = system.store.evaluate_current_query(_pattern())
        assert simple.accepted
        assert result.status is OperationStatus.REJECTED
        assert result.rows == ()
        assert result.aggregates == ()
        assert result.evaluated_revision is None
        assert system.store.current_revision() == before_revision
        assert system.store.canonical_record_count() == before_records
    finally:
        connection.setlimit(sqlite3.SQLITE_LIMIT_VDBE_OP, prior)
        system.close()


@pytest.mark.parametrize(
    ("category", "lowered", "query", "expected"),
    (
        (sqlite3.SQLITE_LIMIT_SQL_LENGTH, 1_000, _pattern(), "SQL bytes"),
        (
            sqlite3.SQLITE_LIMIT_FUNCTION_ARG,
            4,
            replace(
                _pattern(),
                data_conditions=(
                    replace(
                        _pattern().data_conditions[0],
                        property_conditions=(
                            DataPropertyCondition("text", PropertyComparison.EQUAL, "hello"),
                        ),
                    ),
                ),
            ),
            "arguments",
        ),
    ),
)
def test_compiled_artifact_limits_are_typed_before_answer_execution(
    tmp_path: Path,
    category: int,
    lowered: int,
    query: GraphQuery,
    expected: str,
) -> None:
    system = RTGSystem.open(tmp_path / f"compiled-limit-{category}.sqlite3")
    owner = Provenance(initiator="owner")
    assert system.initialize_fresh(
        _definitions(), provenance=owner, initialization_summary="compiled limit"
    ).accepted
    prior = system.store._connection.setlimit(category, lowered)  # noqa: SLF001
    try:
        result = system.store.evaluate_current_query(query)
        assert result.status is OperationStatus.REJECTED
        assert result.evaluated_revision is None
        assert result.rows == () and result.aggregates == ()
        assert expected in result.findings[0].summary
    finally:
        system.store._connection.setlimit(category, prior)  # noqa: SLF001
        system.close()


def test_selector_member_row_length_is_refused_before_temp_population(tmp_path: Path) -> None:
    system = RTGSystem.open(tmp_path / "selector-member-length.sqlite3")
    owner = Provenance(initiator="owner")
    assert system.initialize_fresh(
        _definitions(), provenance=owner, initialization_summary="selector member length"
    ).accepted
    selector = "selector-" + "x" * 120
    query = GraphQuery(
        anchor_groups=(AnchorGroup(selector, ("person",)),),
        output=RowQueryOutput(
            kind="rows",
            projections=(AnchorProjection("answer", selector),),
            maximum_rows=1,
        ),
    )
    connection = system.store._connection  # noqa: SLF001
    prior = connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 100)
    try:
        result = system.store.evaluate_current_query(query)
        assert result.status is OperationStatus.REJECTED
        assert result.evaluated_revision is None
        assert "value capacity" in result.findings[0].summary
        assert connection.execute(
            "SELECT count(*) FROM sqlite_temp_master WHERE name = 'query_selector_member'"
        ).fetchone() == (0,)
    finally:
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, prior)
        system.close()
