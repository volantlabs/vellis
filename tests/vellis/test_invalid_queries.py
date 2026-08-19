"""Evidence for ``VellisVerification::invalidQuery``.

The verification case enumerates what a query may get wrong — names, type keys,
references, endpoint directions, identities, properties, comparisons, projections, and
bounds — and asks for the same answer to all of them: findings, no partial rows, and
nothing in canonical state moved.

A refusal here is not an error condition of the system. A query is a question, and a
question that cannot mean anything is answered by saying so, which is why every case
below returns an outcome rather than raising.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import build_rich_definitions

from tests.vellis.oracle import materialize_state
from tests.vellis.semantic_state import semantic_state_equal
from vellis.canonical import Provenance
from vellis.changes import GraphChange
from vellis.graph import Anchor, AssociatedDataObject, Graph, Link, SystemMetadata
from vellis.json_value import normalize
from vellis.outcomes import OperationStatus
from vellis.query import (
    AggregateQueryOutput,
    AggregationOperator,
    AnchorGroup,
    AnchorProjection,
    AssociatedDataCondition,
    AssociatedDataProjection,
    DataPropertyCondition,
    DataPropertyProjection,
    GraphQuery,
    LinkProjection,
    PropertyComparison,
    QueryAggregation,
    RequiredLink,
    RowQueryOutput,
    UuidFilter,
)
from vellis.system import RTGSystem

ADA = Anchor(uuid="a-1", type_key="person", display_name="Ada")
GRACE = Anchor(uuid="a-2", type_key="person", display_name="Grace")
ORBIT = Anchor(uuid="p-1", type_key="project", display_name="Orbit")
WORKS = Link(uuid="l-1", type_key="worksOn", source_uuid="a-1", target_uuid="p-1")
NOTE = AssociatedDataObject(
    uuid="n-1",
    type_key="note",
    anchor_uuids=("a-1",),
    properties={"title": normalize("First"), "rating": normalize(3)},
)


def _owner() -> Provenance:
    return Provenance(initiator="owner")


@pytest.fixture
def system(tmp_path: Path):
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    assert system.initialize_fresh(
        build_rich_definitions(), provenance=_owner(), initialization_summary="a fresh start"
    ).accepted
    assert system.apply_graph_change(
        GraphChange(
            anchor_upserts=(ADA, GRACE, ORBIT),
            associated_data_upserts=(NOTE,),
            link_upserts=(WORKS,),
        ),
        provenance=_owner(),
    ).accepted
    try:
        yield system
    finally:
        system.close()


def _people(**overrides: object) -> AnchorGroup:
    return AnchorGroup(name="people", anchor_types=("person",), **overrides)  # pyright: ignore[reportArgumentType]


def _who(name: str = "who", group: str = "people"):
    return (AnchorProjection(name=name, anchor_group=group),)


def _query(**overrides: object) -> GraphQuery:
    projections = overrides.pop("projections", _who())
    maximum = overrides.pop("maximum_rows", 10)
    aggregations = overrides.pop("aggregations", None)
    output = (
        AggregateQueryOutput(
            kind="aggregates",
            data_condition=str(overrides.pop("aggregate_target", "notes")),
            aggregations=aggregations,  # pyright: ignore[reportArgumentType]
            maximum_matches=maximum,  # pyright: ignore[reportArgumentType]
        )
        if aggregations is not None
        else RowQueryOutput(
            kind="rows",
            projections=projections,  # pyright: ignore[reportArgumentType]
            maximum_rows=maximum,  # pyright: ignore[reportArgumentType]
        )
    )
    fields: dict[str, object] = {
        "anchor_groups": (_people(),),
        "output": output,
    }
    fields.update(overrides)
    return GraphQuery(**fields)  # pyright: ignore[reportArgumentType]


def _notes(**overrides: object) -> AssociatedDataCondition:
    fields: dict[str, object] = {
        "name": "notes",
        "anchor_group": "people",
        "associated_data_type": "note",
    }
    fields.update(overrides)
    return AssociatedDataCondition(**fields)  # pyright: ignore[reportArgumentType]


def _link(**overrides: object) -> RequiredLink:
    fields: dict[str, object] = {
        "name": "works",
        "source_group": "people",
        "target_group": "projects",
        "link_type": "worksOn",
    }
    fields.update(overrides)
    return RequiredLink(**fields)  # pyright: ignore[reportArgumentType]


PROJECTS = AnchorGroup(name="projects", anchor_types=("project",))


INVALID: tuple[tuple[str, GraphQuery, str], ...] = (
    (
        "empty-name",
        _query(anchor_groups=(AnchorGroup(name="", anchor_types=("person",)),)),
        "empty query-local name",
    ),
    (
        "duplicate-name",
        _query(
            anchor_groups=(_people(), AnchorGroup(name="people", anchor_types=("project",))),
        ),
        "used by more than one selector",
    ),
    (
        "unknown-anchor-type",
        _query(anchor_groups=(AnchorGroup(name="people", anchor_types=("unheard-of",)),)),
        "cannot be",
    ),
    (
        "unknown-data-type",
        _query(data_conditions=(_notes(associated_data_type="unheard-of"),)),
        "cannot be",
    ),
    (
        "unknown-link-type",
        _query(
            anchor_groups=(_people(), PROJECTS),
            required_links=(_link(link_type="unheard-of"),),
        ),
        "cannot be",
    ),
    (
        "out-of-query-grounding",
        _query(data_conditions=(_notes(anchor_group="nobody"),)),
        "not an anchor group in this query",
    ),
    (
        "out-of-query-link-endpoint",
        _query(required_links=(_link(target_group="nowhere"),)),
        "not a candidate set in this query",
    ),
    (
        "out-of-query-projection",
        _query(projections=_who(group="nobody")),
        "not an anchor group in this query",
    ),
    (
        "reversed-endpoint-direction",
        _query(
            anchor_groups=(_people(), PROJECTS),
            required_links=(_link(source_group="projects", target_group="people"),),
        ),
        "does not permit",
    ),
    (
        "unknown-anchor-uuid",
        _query(anchor_groups=(_people(uuid_filter=UuidFilter(uuids=("a-9",))),)),
        "restricts unknown anchor UUID",
    ),
    (
        "anchor-uuid-of-another-type",
        _query(anchor_groups=(_people(uuid_filter=UuidFilter(uuids=("p-1",))),)),
        "restricts unknown anchor UUID",
    ),
    (
        "unknown-link-uuid",
        _query(
            anchor_groups=(_people(), PROJECTS),
            required_links=(_link(uuid_filter=UuidFilter(uuids=("l-9",))),),
        ),
        "restricts unknown link UUID",
    ),
    (
        "duplicate-anchor-uuid",
        _query(anchor_groups=(_people(uuid_filter=UuidFilter(uuids=("a-1", "a-1"))),)),
        "more than once",
    ),
    (
        "empty-uuid-restriction",
        _query(anchor_groups=(_people(uuid_filter=UuidFilter(uuids=())),)),
        "empty UUID restriction",
    ),
    (
        "unknown-property-name",
        _query(
            data_conditions=(
                _notes(
                    property_conditions=(
                        DataPropertyCondition(
                            property_name="unheard-of",
                            comparison=PropertyComparison.EQUAL,
                            expected_value=normalize("x"),
                        ),
                    )
                ),
            )
        ),
        "does not define",
    ),
    (
        "ordered-comparison-on-an-object",
        _query(
            data_conditions=(
                _notes(
                    property_conditions=(
                        DataPropertyCondition(
                            property_name="details",
                            comparison=PropertyComparison.GREATER_THAN,
                            expected_value=normalize({"a": 1}),
                        ),
                    )
                ),
            )
        ),
        "ordered comparison is valid only for number-valued and string-valued properties",
    ),
    (
        "aggregation-of-an-unknown-condition",
        _query(
            aggregations=(
                QueryAggregation(
                    name="total",
                    operator=AggregationOperator.COUNT,
                ),
            )
        ),
        "not a data condition in this query",
    ),
    (
        "aggregation-missing-its-property",
        _query(
            data_conditions=(_notes(),),
            aggregations=(
                QueryAggregation(
                    name="total",
                    operator=AggregationOperator.SUM,
                ),
            ),
        ),
        "names no property",
    ),
    (
        "aggregation-of-an-undefined-property",
        _query(
            data_conditions=(_notes(),),
            aggregations=(
                QueryAggregation(
                    name="total",
                    operator=AggregationOperator.SUM,
                    property_name="unheard-of",
                ),
            ),
        ),
        "does not define",
    ),
    (
        "sum-of-a-string-property",
        _query(
            data_conditions=(_notes(),),
            aggregations=(
                QueryAggregation(
                    name="total",
                    operator=AggregationOperator.SUM,
                    property_name="title",
                ),
            ),
        ),
        "applies only to",
    ),
    (
        "maximum-of-an-object-property",
        _query(
            data_conditions=(_notes(),),
            aggregations=(
                QueryAggregation(
                    name="biggest",
                    operator=AggregationOperator.MAXIMUM,
                    property_name="details",
                ),
            ),
        ),
        "applies only to",
    ),
    (
        "comparison-value-of-the-wrong-kind",
        _query(
            data_conditions=(
                _notes(
                    property_conditions=(
                        DataPropertyCondition(
                            property_name="rating",
                            comparison=PropertyComparison.EQUAL,
                            expected_value=normalize("four"),
                        ),
                    )
                ),
            )
        ),
        "but it is declared numberValue",
    ),
    (
        "projected-property-that-is-not-defined",
        _query(
            data_conditions=(_notes(),),
            projections=(
                DataPropertyProjection(
                    name="value", data_condition="notes", property_name="unheard-of"
                ),
            ),
        ),
        "does not define",
    ),
    (
        "projection-of-the-wrong-selector-kind",
        _query(
            data_conditions=(_notes(),),
            projections=(AssociatedDataProjection(name="note", data_condition="people"),),
        ),
        "not a data condition in this query",
    ),
    (
        "link-projection-without-its-link",
        _query(projections=(LinkProjection(name="works", required_link="works"),)),
        "not a required link in this query",
    ),
    (
        "incompatible-anchor-type",
        _query(anchor_groups=(AnchorGroup(name="people", anchor_types=("note",)),)),
        "which is not an active anchor type",
    ),
    (
        "incompatible-data-type",
        _query(data_conditions=(_notes(associated_data_type="person"),)),
        "which is not an active associated-data type",
    ),
    (
        "incompatible-link-type",
        _query(
            anchor_groups=(_people(), PROJECTS),
            required_links=(_link(link_type="note"),),
        ),
        "which is not an active link type",
    ),
    (
        "null-compared-with-a-string-property",
        _query(
            data_conditions=(
                _notes(
                    property_conditions=(
                        DataPropertyCondition(
                            property_name="title",
                            comparison=PropertyComparison.NOT_EQUAL,
                            expected_value=None,
                        ),
                    )
                ),
            )
        ),
        "with a nullValue, but it is declared stringValue",
    ),
    ("no-anchor-groups", _query(anchor_groups=()), "at least one anchor group"),
    (
        "no-projections",
        _query(projections=()),
        "row output must request a projection",
    ),
    ("zero-maximum", _query(maximum_rows=0), "maximum rows must be positive"),
    ("negative-maximum", _query(maximum_rows=-1), "maximum rows must be positive"),
)


@pytest.mark.parametrize(
    ("query", "expected"),
    [(query, expected) for _, query, expected in INVALID],
    ids=[name for name, _, _ in INVALID],
)
def test_an_invalid_query_reports_findings_and_returns_no_rows(
    system: RTGSystem, query: GraphQuery, expected: str
) -> None:
    before = materialize_state(system)
    records = system.store.canonical_record_count()

    result = system.query_graph(query)

    assert result.status is OperationStatus.REJECTED
    assert result.rows == ()
    assert result.evaluated_revision is None
    assert any(expected in finding.summary for finding in result.findings), result.findings
    assert semantic_state_equal(materialize_state(system), before)
    assert system.store.canonical_record_count() == records


def test_a_result_above_its_maximum_is_refused_whole_rather_than_truncated(
    system: RTGSystem,
) -> None:
    """Excludes returning the first row of a two-row answer.

    A bounded question asks whether the whole answer fits, so a truncated result is not a
    smaller true answer to it.
    """
    assert len(system.query_graph(_query()).rows) == 2

    result = system.query_graph(_query(maximum_rows=1))

    assert result.status is OperationStatus.REJECTED
    assert result.rows == ()
    assert result.evaluated_revision is None
    assert "refused whole rather than truncated" in result.summary
    assert any("exceeds the maximum" in each.summary for each in result.findings)


def test_a_result_exactly_at_its_maximum_is_returned(system: RTGSystem) -> None:
    """The bound is a maximum, not a strict one; excludes an off-by-one refusal."""
    result = system.query_graph(_query(maximum_rows=2))

    assert result.accepted, result.findings
    assert len(result.rows) == 2


def test_a_result_that_cannot_be_returned_completely_is_refused_whole() -> None:
    """Excludes dropping the row that cannot be returned and answering with the rest.

    Exercised directly on evaluation, because the store refuses unencodable text on the
    way in and on the way out: no graph it hands back can carry this. The guard is for a
    graph that reached memory another way, and the model is explicit that such a result is
    refused whole rather than quietly shortened.
    """
    from tests.vellis.oracle import evaluate_query
    from vellis.graph import Graph

    definitions = build_rich_definitions()
    graph = Graph(anchors=(ADA, Anchor(uuid="a-2", type_key="person", display_name="Gr\ud800ce")))

    result = evaluate_query(_query(), definitions, graph, revision=1)

    assert result.status is OperationStatus.REJECTED
    assert result.rows == ()
    assert result.evaluated_revision is None
    assert any("cannot be returned" in each.summary for each in result.findings)


def test_a_grounding_the_active_definitions_forbid_is_refused(tmp_path: Path) -> None:
    """The same principle the link endpoint roles enforce, on the grounding side.

    The shared vocabulary permits a note on either anchor type, so this needs one that
    does not: a definition set that says where a note may live and a query that puts it
    somewhere else.
    """
    from vellis.definitions import (
        AnchorTypeDefinition,
        AssociatedDataTypeDefinition,
        GraphDefinitionSet,
    )

    definitions = GraphDefinitionSet(
        anchor_types=(
            AnchorTypeDefinition(type_key="person", description="A person the owner knows."),
            AnchorTypeDefinition(type_key="project", description="A piece of work."),
        ),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="note",
                permitted_anchor_type_keys=("person",),
                description="A note about a person.",
            ),
        ),
    )
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        assert system.initialize_fresh(
            definitions, provenance=_owner(), initialization_summary="a fresh start"
        ).accepted

        result = system.query_graph(
            _query(
                anchor_groups=(PROJECTS,),
                data_conditions=(_notes(anchor_group="projects"),),
                projections=_who(group="projects"),
            )
        )

        assert result.status is OperationStatus.REJECTED
        assert result.rows == ()
        assert any("does not permit" in each.summary for each in result.findings)
    finally:
        system.close()


@pytest.mark.parametrize(
    ("field", "graph_of"),
    (
        ("anchor uuid", lambda bad: Graph(anchors=(Anchor(bad, "person", "Ada"),))),
        ("anchor display name", lambda bad: Graph(anchors=(Anchor("a-1", "person", bad),))),
        (
            "anchor metadata name",
            lambda bad: Graph(
                anchors=(
                    Anchor(
                        "a-1", "person", "Ada", system_metadata=SystemMetadata(members={bad: True})
                    ),
                )
            ),
        ),
    ),
    ids=["anchor-uuid", "anchor-display-name", "anchor-metadata-name"],
)
def test_no_field_of_a_returned_anchor_escapes_the_completeness_screen(
    field: str, graph_of
) -> None:
    """Excludes a screen with a hole in it.

    Each of these reaches a row without passing through ``normalize``, so each is a way an
    imported or repaired graph could hand back a result nothing can encode.
    """
    from tests.vellis.oracle import evaluate_query

    result = evaluate_query(_query(), build_rich_definitions(), graph_of("Gr\ud800ce"), revision=1)

    assert result.status is OperationStatus.REJECTED, field
    assert result.rows == ()
    assert any("cannot be returned" in each.summary for each in result.findings)


def _note_graph(**overrides) -> Graph:
    fields: dict[str, object] = {
        "uuid": "n-1",
        "type_key": "note",
        "anchor_uuids": ("a-1",),
        "properties": {"title": normalize("First")},
    }
    fields.update(overrides)
    return Graph(anchors=(ADA,), associated_data=(AssociatedDataObject(**fields),))  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize(
    ("field", "graph"),
    (
        ("data uuid", _note_graph(uuid="n\ud800-1")),
        (
            "grounding uuid",
            Graph(
                anchors=(Anchor("a\ud800-1", "person", "Ada"),),
                associated_data=(
                    AssociatedDataObject(
                        uuid="n-1",
                        type_key="note",
                        anchor_uuids=("a\ud800-1",),
                        properties={"title": normalize("First")},
                    ),
                ),
            ),
        ),
        ("property name", _note_graph(properties={"ti\ud800tle": normalize("First")})),
        (
            "data metadata name",
            _note_graph(system_metadata=SystemMetadata(members={"or\ud800igin": "x"})),
        ),
    ),
    ids=["data-uuid", "grounding-uuid", "property-name", "data-metadata-name"],
)
def test_no_field_of_returned_associated_data_escapes_the_completeness_screen(
    field: str, graph: Graph
) -> None:
    """``AssociatedDataObject`` normalizes property values, not their names or its own ids."""
    from tests.vellis.oracle import evaluate_query

    query = _query(
        data_conditions=(_notes(),),
        projections=(AssociatedDataProjection(name="note", data_condition="notes"),),
    )

    result = evaluate_query(query, build_rich_definitions(), graph, revision=1)

    assert result.status is OperationStatus.REJECTED, field
    assert result.rows == ()
    assert any("cannot be returned" in each.summary for each in result.findings)


@pytest.mark.parametrize(
    ("field", "link"),
    (
        ("link uuid", Link("l\ud800-1", "worksOn", "a-1", "p-1")),
        ("source uuid", Link("l-1", "worksOn", "a\ud800-1", "p-1")),
        ("target uuid", Link("l-1", "worksOn", "a-1", "p\ud800-1")),
        (
            "link metadata name",
            Link(
                "l-1",
                "worksOn",
                "a-1",
                "p-1",
                system_metadata=SystemMetadata(members={"or\ud800igin": "x"}),
            ),
        ),
    ),
    ids=["link-uuid", "source-uuid", "target-uuid", "link-metadata-name"],
)
def test_no_field_of_a_returned_link_escapes_the_completeness_screen(
    field: str, link: Link
) -> None:
    """A projected link carries its endpoints' identities even when neither is projected."""
    from tests.vellis.oracle import evaluate_query

    graph = Graph(
        anchors=(
            Anchor(link.source_uuid, "person", "Ada"),
            Anchor(link.target_uuid, "project", "Orbit"),
        ),
        links=(link,),
    )
    query = _query(
        anchor_groups=(_people(), PROJECTS),
        required_links=(_link(),),
        projections=(LinkProjection(name="edge", required_link="works"),),
    )

    result = evaluate_query(query, build_rich_definitions(), graph, revision=1)

    assert result.status is OperationStatus.REJECTED, field
    assert result.rows == ()
    assert any("cannot be returned" in each.summary for each in result.findings)
