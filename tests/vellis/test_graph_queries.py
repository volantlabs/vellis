"""Evidence for ``VellisVerification::semanticQuery``.

The verification case walks one arc — query an anchor type broadly, narrow it by known
UUIDs, select associated data by type alone and then by structured comparison, constrain
endpoint groups by directed link, and show each row carries only what was asked for at the
evaluated revision.

Historical evaluation is the same case against a selected revision and a selected time.
Those legs belong to the slice that can resolve one; what is here is the current-state
meaning they will have to agree with.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from conftest import build_rich_definitions

from tests.vellis.oracle import _TestGraphIndex, evaluate_query, materialize_state
from tests.vellis.semantic_state import semantic_state_equal
from vellis.canonical import Provenance
from vellis.changes import GraphChange
from vellis.definitions import AnchorTypeDefinition
from vellis.governance import DefinitionChange
from vellis.graph import Anchor, AssociatedDataObject, Graph, Link
from vellis.history import RevisionSelection
from vellis.json_value import normalize
from vellis.outcomes import OperationStatus
from vellis.query import (
    AggregationOperator,
    AnchorGroup,
    AnchorProjection,
    AnchorUuidFilter,
    AssociatedDataCondition,
    AssociatedDataProjection,
    DataPropertyCondition,
    DataPropertyProjection,
    EvaluatedStateScope,
    GraphQuery,
    GraphQueryResult,
    LinkProjection,
    LinkUuidFilter,
    PropertyComparison,
    QueryAggregation,
    RequiredLink,
    ReturnShape,
    evaluate_indexed_query,
)
from vellis.system import RTGSystem

ADA = Anchor(uuid="a-1", type_key="person", display_name="Ada")
GRACE = Anchor(uuid="a-2", type_key="person", display_name="Grace")
ORBIT = Anchor(uuid="p-1", type_key="project", display_name="Orbit")
COMPILER = Anchor(uuid="p-2", type_key="project", display_name="Compiler")


def _note(uuid: str, anchors: tuple[str, ...], **properties: object) -> AssociatedDataObject:
    values = {"title": normalize("A note")}
    values.update({name: normalize(value) for name, value in properties.items()})
    return AssociatedDataObject(uuid=uuid, type_key="note", anchor_uuids=anchors, properties=values)


def _owner() -> Provenance:
    return Provenance(initiator="owner")


@pytest.fixture
def system(tmp_path: Path):
    """A small graph with enough shape to tell selection from projection apart."""
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    assert system.initialize_fresh(
        build_rich_definitions(), provenance=_owner(), initialization_summary="a fresh start"
    ).accepted
    outcome = system.apply_graph_change(
        GraphChange(
            anchor_upserts=(ADA, GRACE, ORBIT, COMPILER),
            associated_data_upserts=(
                _note("n-1", ("a-1",), rating=4, tag="green"),
                _note("n-2", ("a-1",), rating=2),
                _note("n-3", ("a-2",), rating=5, tag="amber"),
                _note("n-4", ("p-1",)),
            ),
            link_upserts=(
                Link(uuid="l-1", type_key="worksOn", source_uuid="a-1", target_uuid="p-1"),
                Link(uuid="l-2", type_key="worksOn", source_uuid="a-1", target_uuid="p-2"),
                Link(uuid="l-3", type_key="worksOn", source_uuid="a-2", target_uuid="p-1"),
            ),
        ),
        provenance=_owner(),
    )
    assert outcome.accepted, outcome.findings
    try:
        yield system
    finally:
        system.close()


def _system_with(tmp_path: Path, definitions) -> RTGSystem:
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    assert system.initialize_fresh(
        definitions, provenance=_owner(), initialization_summary="a fresh start"
    ).accepted
    return system


def _endpoint_definitions():
    """A vocabulary that permits a note as a link target and a null-valued property."""
    from vellis.definitions import (
        AnchorTypeDefinition,
        AssociatedDataTypeDefinition,
        EndpointConstraint,
        GraphDefinitionSet,
        LinkTypeDefinition,
        PropertyConstraint,
    )
    from vellis.json_value import JsonKind

    return GraphDefinitionSet(
        anchor_types=(
            AnchorTypeDefinition(type_key="person", description="A person the owner knows."),
            AnchorTypeDefinition(type_key="project", description="A piece of work."),
        ),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="note",
                permitted_anchor_type_keys=("person", "project"),
                property_constraints=(
                    PropertyConstraint(
                        property_name="marker",
                        required=False,
                        json_kind=JsonKind.NULL,
                        description="An optional marker that carries no value of its own.",
                    ),
                ),
                description="A note about an anchor.",
            ),
        ),
        link_types=(
            LinkTypeDefinition(
                type_key="mentions",
                endpoint_constraint=EndpointConstraint(
                    permitted_source_type_keys=("person",),
                    permitted_target_type_keys=("note",),
                    description="Who mentions which note.",
                ),
                description="A mention.",
            ),
        ),
    )


def _people(name: str = "people", **overrides: object) -> AnchorGroup:
    return AnchorGroup(name=name, anchor_types=("person",), **overrides)  # pyright: ignore[reportArgumentType]


def _just_people(maximum_rows: int = 10, uuid_filter: AnchorUuidFilter | None = None) -> GraphQuery:
    return GraphQuery(
        anchor_groups=(
            AnchorGroup(name="people", anchor_types=("person",), uuid_filter=uuid_filter),
        ),
        return_shape=ReturnShape(
            projections=(AnchorProjection(name="who", anchor_group="people"),)
        ),
        maximum_rows=maximum_rows,
    )


def _bound_anchors(result) -> set[str]:
    return {binding.anchor.uuid for row in result.rows for binding in row.anchors}


# --- Selection ------------------------------------------------------------------------


def test_one_anchor_type_is_queried_broadly(system: RTGSystem) -> None:
    result = system.query_graph(_just_people())

    assert result.status is OperationStatus.ACCEPTED
    assert result.evaluated_revision == materialize_state(system).revision
    assert _bound_anchors(result) == {"a-1", "a-2"}


def test_current_query_decodes_only_query_relevant_sqlite_rows(system: RTGSystem) -> None:
    """Projects people without assembling projects, data, links, or a complete graph."""
    system.store.reset_instrumentation()

    result = system.query_graph(_just_people())

    assert result.accepted, result.findings
    assert _bound_anchors(result) == {"a-1", "a-2"}
    assert system.store.current_projection_decodes == 0
    assert system.store.current_graph_decodes == 0
    assert system.store.current_graph_object_decodes == 2
    assert system.store.current_definition_decodes == 1
    assert system.store.record_reads == 0


def test_sqlite_candidate_joins_have_matching_indexes(system: RTGSystem) -> None:
    connection = system.store._connection  # noqa: SLF001

    anchor_plan = connection.execute(
        "EXPLAIN QUERY PLAN SELECT object_value_id FROM current_graph_object"
        " WHERE object_kind = ? AND type_key = ?",
        ("anchor", "person"),
    ).fetchall()
    data_plan = connection.execute(
        "EXPLAIN QUERY PLAN SELECT o.object_value_id FROM current_data_anchor AS da"
        " JOIN current_graph_object AS o ON o.uuid = da.data_uuid"
        " WHERE da.anchor_uuid = ? AND o.object_kind = ? AND o.type_key = ?",
        ("a-1", "associatedData", "note"),
    ).fetchall()
    link_plan = connection.execute(
        "EXPLAIN QUERY PLAN SELECT object_value_id FROM current_graph_object"
        " WHERE object_kind = ? AND type_key = ? AND source_uuid = ? AND target_uuid = ?",
        ("link", "worksOn", "a-1", "p-1"),
    ).fetchall()

    assert any(
        index in str(row)
        for row in anchor_plan
        for index in ("graph_presence_current_type", "object_value_type_key")
    )
    assert any("object_anchor_reverse" in str(row) for row in data_plan)
    assert any(
        index in str(row)
        for row in link_plan
        for index in (
            "graph_presence_current_link_source",
            "graph_presence_current_link_target",
            "graph_presence_current_type",
        )
    )


def test_known_uuids_narrow_an_anchor_group(system: RTGSystem) -> None:
    result = system.query_graph(_just_people(uuid_filter=AnchorUuidFilter(uuids=("a-2",))))

    assert result.accepted, result.findings
    assert _bound_anchors(result) == {"a-2"}


def test_associated_data_selects_by_type_and_direct_association_alone(
    system: RTGSystem,
) -> None:
    """A condition with no comparisons expresses existence, not a degenerate filter."""
    query = GraphQuery(
        anchor_groups=(_people(),),
        data_conditions=(
            AssociatedDataCondition(
                name="notes", anchor_group="people", associated_data_type="note"
            ),
        ),
        return_shape=ReturnShape(
            projections=(AnchorProjection(name="who", anchor_group="people"),)
        ),
        maximum_rows=10,
    )

    result = system.query_graph(query)

    assert result.accepted, result.findings
    # Orbit carries a note too, but it is not a person, so it is not a candidate here.
    assert _bound_anchors(result) == {"a-1", "a-2"}


def test_a_structured_comparison_narrows_associated_data(system: RTGSystem) -> None:
    query = GraphQuery(
        anchor_groups=(_people(),),
        data_conditions=(
            AssociatedDataCondition(
                name="notes",
                anchor_group="people",
                associated_data_type="note",
                property_conditions=(
                    DataPropertyCondition(
                        property_name="rating",
                        comparison=PropertyComparison.GREATER_THAN_OR_EQUAL,
                        expected_value=normalize(4),
                    ),
                ),
            ),
        ),
        return_shape=ReturnShape(
            projections=(
                AnchorProjection(name="who", anchor_group="people"),
                AssociatedDataProjection(name="note", data_condition="notes"),
            )
        ),
        maximum_rows=10,
    )

    result = system.query_graph(query)

    assert result.accepted, result.findings
    assert {
        binding.associated_data.uuid for row in result.rows for binding in row.associated_data
    } == {
        "n-1",
        "n-3",
    }


def test_a_directed_link_constrains_two_anchor_groups(system: RTGSystem) -> None:
    result = system.query_graph(_worked_on())

    assert result.accepted, result.findings
    assert {(row.anchors[0].anchor.uuid, row.anchors[1].anchor.uuid) for row in result.rows} == {
        ("a-1", "p-1"),
        ("a-1", "p-2"),
        ("a-2", "p-1"),
    }


def test_sparse_directed_links_constrain_endpoint_decoding_before_join(
    system: RTGSystem,
) -> None:
    unrelated = tuple(
        Anchor(f"extra-person-{index}", "person", f"Person {index}") for index in range(200)
    ) + tuple(
        Anchor(f"extra-project-{index}", "project", f"Project {index}") for index in range(200)
    )
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=unrelated), provenance=_owner()
    ).accepted
    system.store.reset_instrumentation()

    result = system.query_graph(_worked_on())

    assert result.accepted, result.findings
    assert len(result.rows) == 3
    # SQL performs the endpoint/link joins; only the six projected object occurrences
    # are hydrated. The 400 unrelated same-type endpoints never become domain objects.
    assert system.store.current_graph_object_decodes == 6
    assert system.store.current_graph_decodes == 0


def test_multiple_assigned_link_restrictions_are_intersected_before_data_filtering(
    system: RTGSystem,
) -> None:
    assert system.apply_graph_change(
        GraphChange(
            associated_data_upserts=(
                _note("project-note-1", ("p-1",), rating=4),
                _note("project-note-2", ("p-2",), rating=4),
            ),
        ),
        provenance=_owner(),
    ).accepted
    query = GraphQuery(
        anchor_groups=(
            _people("first", uuid_filter=AnchorUuidFilter(("a-1",))),
            _people("second", uuid_filter=AnchorUuidFilter(("a-2",))),
            AnchorGroup("projects", ("project",)),
        ),
        data_conditions=(
            AssociatedDataCondition(
                "projectNotes",
                "projects",
                "note",
                property_conditions=(
                    DataPropertyCondition(
                        "rating", PropertyComparison.GREATER_THAN_OR_EQUAL, normalize(4)
                    ),
                ),
            ),
        ),
        required_links=(
            RequiredLink("firstWork", "first", "projects", "worksOn"),
            RequiredLink("secondWork", "second", "projects", "worksOn"),
        ),
        return_shape=ReturnShape((AnchorProjection("project", "projects"),)),
        maximum_rows=10,
    )
    system.store.reset_instrumentation()

    result = system.query_graph(query)

    assert result.accepted, result.findings
    assert _bound_anchors(result) == {"p-1"}
    # Every unprojected selector remains inside SQLite; only the projected project is
    # hydrated after the complete join and property predicate have succeeded.
    assert system.store.current_graph_object_decodes == 1


def _worked_on(uuid_filter: LinkUuidFilter | None = None) -> GraphQuery:
    return GraphQuery(
        anchor_groups=(_people(), AnchorGroup(name="projects", anchor_types=("project",))),
        required_links=(
            RequiredLink(
                name="works",
                source_group="people",
                target_group="projects",
                link_type="worksOn",
                uuid_filter=uuid_filter,
            ),
        ),
        return_shape=ReturnShape(
            projections=(
                AnchorProjection(name="who", anchor_group="people"),
                AnchorProjection(name="what", anchor_group="projects"),
            )
        ),
        maximum_rows=10,
    )


def test_known_link_uuids_narrow_a_required_link(system: RTGSystem) -> None:
    result = system.query_graph(_worked_on(LinkUuidFilter(uuids=("l-3",))))

    assert result.accepted, result.findings
    assert {(row.anchors[0].anchor.uuid, row.anchors[1].anchor.uuid) for row in result.rows} == {
        ("a-2", "p-1")
    }


def test_an_associated_data_group_may_be_a_link_endpoint(tmp_path: Path) -> None:
    """The model lets directly associated data participate as an endpoint, not only anchors.

    That needs a vocabulary whose link type permits it, so this builds its own rather than
    bending the shared one.
    """
    system = _system_with(tmp_path, _endpoint_definitions())
    try:
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(ADA, ORBIT),
                associated_data_upserts=(
                    AssociatedDataObject(uuid="n-1", type_key="note", anchor_uuids=("p-1",)),
                ),
                link_upserts=(
                    Link(uuid="l-1", type_key="mentions", source_uuid="a-1", target_uuid="n-1"),
                ),
            ),
            provenance=_owner(),
        ).accepted

        query = GraphQuery(
            anchor_groups=(_people(), AnchorGroup(name="projects", anchor_types=("project",))),
            data_conditions=(
                AssociatedDataCondition(
                    name="projectNotes", anchor_group="projects", associated_data_type="note"
                ),
            ),
            required_links=(
                RequiredLink(
                    name="mentions",
                    source_group="people",
                    target_group="projectNotes",
                    link_type="mentions",
                ),
            ),
            return_shape=ReturnShape(
                projections=(
                    AnchorProjection(name="who", anchor_group="people"),
                    AssociatedDataProjection(name="note", data_condition="projectNotes"),
                )
            ),
            maximum_rows=10,
        )

        result = system.query_graph(query)

        assert result.accepted, result.findings
        assert [row.associated_data[0].associated_data.uuid for row in result.rows] == ["n-1"]
    finally:
        system.close()


def test_sparse_links_prune_associated_data_before_property_comparison(tmp_path: Path) -> None:
    system = _system_with(tmp_path, _endpoint_definitions())
    try:
        notes = tuple(
            AssociatedDataObject(
                uuid=f"n-{index}",
                type_key="note",
                anchor_uuids=("p-1",),
                properties={"marker": normalize(None)},
            )
            for index in range(100)
        )
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(ADA, ORBIT),
                associated_data_upserts=notes,
                link_upserts=(Link("l-1", "mentions", source_uuid="a-1", target_uuid="n-1"),),
            ),
            provenance=_owner(),
        ).accepted
        query = GraphQuery(
            anchor_groups=(_people(), AnchorGroup("projects", ("project",))),
            data_conditions=(
                AssociatedDataCondition(
                    "projectNotes",
                    "projects",
                    "note",
                    property_conditions=(
                        DataPropertyCondition("marker", PropertyComparison.EQUAL, normalize(None)),
                    ),
                ),
            ),
            required_links=(RequiredLink("mentions", "people", "projectNotes", "mentions"),),
            return_shape=ReturnShape((AssociatedDataProjection("note", "projectNotes"),)),
            maximum_rows=10,
        )
        system.store.reset_instrumentation()

        result = system.query_graph(query)

        assert result.accepted, result.findings
        assert [row.associated_data[0].associated_data.uuid for row in result.rows] == ["n-1"]
        # The anchors, link, and other 99 notes stay inside SQLite. Only the one projected
        # note is hydrated after the join and property comparison.
        assert system.store.current_graph_object_decodes == 1
    finally:
        system.close()


# --- Shaping --------------------------------------------------------------------------


def test_a_row_carries_only_the_requested_projections(system: RTGSystem) -> None:
    """Excludes returning a selector that only constrained the answer.

    The link and the notes below decide which rows exist and appear in none of them.
    """
    query = GraphQuery(
        anchor_groups=(_people(), AnchorGroup(name="projects", anchor_types=("project",))),
        data_conditions=(
            AssociatedDataCondition(
                name="notes", anchor_group="people", associated_data_type="note"
            ),
        ),
        required_links=(
            RequiredLink(
                name="works", source_group="people", target_group="projects", link_type="worksOn"
            ),
        ),
        return_shape=ReturnShape(
            projections=(AnchorProjection(name="who", anchor_group="people"),)
        ),
        maximum_rows=10,
    )

    result = system.query_graph(query)

    assert result.accepted, result.findings
    for row in result.rows:
        assert len(row.anchors) == 1
        assert row.links == ()
        assert row.associated_data == ()
        assert row.properties == ()
    assert _bound_anchors(result) == {"a-1", "a-2"}


def test_every_binding_identifies_its_projection_and_the_result_its_query(
    system: RTGSystem,
) -> None:
    query = _worked_on()

    result = system.query_graph(query)

    assert result.query is query
    for row in result.rows:
        assert [binding.projection for binding in row.anchors] == ["who", "what"]


def test_identical_projected_tuples_occur_once(system: RTGSystem) -> None:
    """Ada has two notes; projecting only Ada must not answer twice."""
    query = GraphQuery(
        anchor_groups=(_people(),),
        data_conditions=(
            AssociatedDataCondition(
                name="notes", anchor_group="people", associated_data_type="note"
            ),
        ),
        return_shape=ReturnShape(
            projections=(AnchorProjection(name="who", anchor_group="people"),)
        ),
        maximum_rows=10,
    )

    result = system.query_graph(query)

    assert result.accepted, result.findings
    assert len(result.rows) == 2


def test_a_row_is_one_jointly_satisfying_assignment(system: RTGSystem) -> None:
    """Excludes answering each selector independently and pairing the answers up."""
    result = system.query_graph(_worked_on())

    assert result.accepted, result.findings
    # A cross product of two people and two projects would be four rows; only three
    # pairs are actually linked.
    assert len(result.rows) == 3
    assert ("a-2", "p-2") not in {
        (row.anchors[0].anchor.uuid, row.anchors[1].anchor.uuid) for row in result.rows
    }


def _rating_of(result, uuid: str):
    for row in result.rows:
        if row.associated_data[0].associated_data.uuid == uuid:
            return row.properties[0]
    raise AssertionError(f"no row for {uuid}")


def _projected_notes(maximum_rows: int = 10, property_name: str = "rating") -> GraphQuery:
    return GraphQuery(
        anchor_groups=(_people(),),
        data_conditions=(
            AssociatedDataCondition(
                name="notes", anchor_group="people", associated_data_type="note"
            ),
        ),
        return_shape=ReturnShape(
            projections=(
                AssociatedDataProjection(name="note", data_condition="notes"),
                DataPropertyProjection(
                    name="value", data_condition="notes", property_name=property_name
                ),
            )
        ),
        maximum_rows=maximum_rows,
    )


def test_a_missing_optional_property_binds_absent_rather_than_null(tmp_path: Path) -> None:
    """Excludes reporting an omitted property as JSON null.

    Absence and a stored null read the same in Python, so a binding that carried only the
    value could not tell them apart — which is exactly the distinction the model keeps.
    """
    system = _system_with(tmp_path, _endpoint_definitions())
    try:
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(ADA,),
                associated_data_upserts=(
                    AssociatedDataObject(uuid="n-1", type_key="note", anchor_uuids=("a-1",)),
                    AssociatedDataObject(
                        uuid="n-2",
                        type_key="note",
                        anchor_uuids=("a-1",),
                        properties={"marker": normalize(None)},
                    ),
                ),
            ),
            provenance=_owner(),
        ).accepted

        result = system.query_graph(
            GraphQuery(
                anchor_groups=(_people(),),
                data_conditions=(
                    AssociatedDataCondition(
                        name="notes", anchor_group="people", associated_data_type="note"
                    ),
                ),
                return_shape=ReturnShape(
                    projections=(
                        AssociatedDataProjection(name="note", data_condition="notes"),
                        DataPropertyProjection(
                            name="value", data_condition="notes", property_name="marker"
                        ),
                    )
                ),
                maximum_rows=10,
            )
        )

        assert result.accepted, result.findings
        bindings = {
            row.associated_data[0].associated_data.uuid: row.properties[0] for row in result.rows
        }
        assert bindings["n-1"].present is False
        assert bindings["n-1"].value is None
        assert bindings["n-2"].present is True
        assert bindings["n-2"].value is None
    finally:
        system.close()


def test_a_present_non_null_property_binds_its_value(system: RTGSystem) -> None:
    result = system.query_graph(_projected_notes())

    assert result.accepted, result.findings
    assert _rating_of(result, "n-1").value == normalize(4)
    assert _rating_of(result, "n-1").present is True


# --- Meaning does not depend on how it is evaluated -----------------------------------


def test_alternative_evaluation_orders_produce_equivalent_rows(system: RTGSystem) -> None:
    """Excludes a join whose answer depends on the order the groups were written in."""
    forward = _worked_on()
    reversed_groups = GraphQuery(
        anchor_groups=(AnchorGroup(name="projects", anchor_types=("project",)), _people()),
        required_links=forward.required_links,
        return_shape=forward.return_shape,
        maximum_rows=forward.maximum_rows,
    )

    first = system.query_graph(forward)
    second = system.query_graph(reversed_groups)

    assert first.accepted and second.accepted

    def pairs(result):
        return {
            tuple(sorted((b.projection, b.anchor.uuid) for b in row.anchors)) for row in result.rows
        }

    assert pairs(first) == pairs(second)


def test_unprojected_disconnected_population_does_not_multiply_projection_work(
    system: RTGSystem,
) -> None:
    question = GraphQuery(
        anchor_groups=(
            AnchorGroup(name="people", anchor_types=("person",)),
            AnchorGroup(name="projects", anchor_types=("project",)),
        ),
        return_shape=ReturnShape(
            projections=(AnchorProjection(name="who", anchor_group="people"),)
        ),
        maximum_rows=100,
    )

    def measured_steps() -> tuple[GraphQueryResult, int]:
        steps = 0

        def progress() -> int:
            nonlocal steps
            steps += 1
            return 0

        system.store._connection.set_progress_handler(progress, 1)  # noqa: SLF001
        try:
            return system.query_graph(question), steps
        finally:
            system.store._connection.set_progress_handler(None, 0)  # noqa: SLF001

    before, baseline_steps = measured_steps()
    assert system.apply_graph_change(
        GraphChange(
            anchor_upserts=tuple(
                Anchor(f"project-{index}", "project", f"Project {index}") for index in range(1_000)
            )
        ),
        provenance=_owner(),
    ).accepted
    after, expanded_steps = measured_steps()

    assert before.accepted and after.accepted
    assert _bound_anchors(before) == _bound_anchors(after) == {"a-1", "a-2"}
    assert expanded_steps < baseline_steps * 4


def test_unsatisfied_unprojected_component_still_removes_every_row(tmp_path: Path) -> None:
    system = _system_with(tmp_path, build_rich_definitions())
    try:
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("person-only", "person", "Person"),)),
            provenance=_owner(),
        ).accepted
        result = system.query_graph(
            GraphQuery(
                anchor_groups=(
                    AnchorGroup(name="people", anchor_types=("person",)),
                    AnchorGroup(name="projects", anchor_types=("project",)),
                ),
                return_shape=ReturnShape(
                    projections=(AnchorProjection(name="who", anchor_group="people"),)
                ),
                maximum_rows=10,
            )
        )

        assert result.accepted, result.findings
        assert result.rows == ()
    finally:
        system.close()


def test_unsatisfied_disconnected_component_keeps_empty_aggregate_bindings(
    tmp_path: Path,
) -> None:
    """An empty global selection has zero/absent answers, not missing answers."""
    system = _system_with(tmp_path, build_rich_definitions())
    try:
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(ADA,),
                associated_data_upserts=(_note("n-1", ("a-1",), rating=4),),
            ),
            provenance=_owner(),
        ).accepted
        state = materialize_state(system)
        for projections in (
            (),
            (AnchorProjection(name="who", anchor_group="people"),),
        ):
            query = GraphQuery(
                anchor_groups=(
                    AnchorGroup(name="people", anchor_types=("person",)),
                    AnchorGroup(name="projects", anchor_types=("project",)),
                ),
                data_conditions=(
                    AssociatedDataCondition(
                        name="notes",
                        anchor_group="people",
                        associated_data_type="note",
                    ),
                ),
                return_shape=ReturnShape(projections=projections),
                aggregations=(
                    QueryAggregation(
                        name="howMany",
                        operator=AggregationOperator.COUNT,
                        data_condition="notes",
                    ),
                    QueryAggregation(
                        name="total",
                        operator=AggregationOperator.SUM,
                        data_condition="notes",
                        property_name="rating",
                    ),
                ),
                maximum_rows=10,
            )

            stored = system.query_graph(query)
            in_memory = evaluate_query(query, state.active_definitions, state.graph, state.revision)

            assert stored.status is OperationStatus.ACCEPTED, stored.findings
            assert stored.rows == in_memory.rows == ()
            assert stored.aggregates == in_memory.aggregates
            assert [(one.aggregation, one.present, one.value) for one in stored.aggregates] == [
                ("howMany", True, Decimal(0)),
                ("total", False, None),
            ]
    finally:
        system.close()


def test_a_query_changes_no_canonical_state_or_revision(system: RTGSystem) -> None:

    before = materialize_state(system)
    records = system.store.canonical_record_count()

    assert system.query_graph(_just_people()).accepted
    assert not system.query_graph(_just_people(maximum_rows=1)).accepted

    assert semantic_state_equal(materialize_state(system), before)
    assert system.store.canonical_record_count() == records


def test_a_query_visits_no_canonical_record_however_long_the_history(
    system: RTGSystem,
) -> None:
    """Query is named in the current-work requirement, so it may not walk history."""
    for index in range(20):
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(
                    Anchor(uuid=f"a-{index + 10}", type_key="person", display_name=f"P{index}"),
                )
            ),
            provenance=_owner(),
        ).accepted

    system.store.reset_instrumentation()
    for _ in range(10):
        assert system.query_graph(_worked_on()).accepted
    assert system.query_graph(_just_people(maximum_rows=1)).status is OperationStatus.REJECTED

    assert system.store.record_reads == 0


# --- Selection actually selects -------------------------------------------------------
#
# The shared vocabulary has one link type and one associated-data type, so an evaluator
# that ignored both filters would answer these questions correctly by accident. These
# build a vocabulary where getting it wrong shows.


def _discriminating_definitions():
    from vellis.definitions import (
        AnchorTypeDefinition,
        AssociatedDataTypeDefinition,
        EndpointConstraint,
        GraphDefinitionSet,
        LinkTypeDefinition,
        PropertyConstraint,
    )
    from vellis.json_value import JsonKind

    def link(type_key: str, source: tuple[str, ...], target: tuple[str, ...]):
        return LinkTypeDefinition(
            type_key=type_key,
            endpoint_constraint=EndpointConstraint(
                permitted_source_type_keys=source,
                permitted_target_type_keys=target,
                description=f"A {type_key} relationship.",
            ),
            description=f"A {type_key} relationship.",
        )

    return GraphDefinitionSet(
        anchor_types=(
            AnchorTypeDefinition(type_key="person", description="A person the owner knows."),
            AnchorTypeDefinition(type_key="project", description="A piece of work."),
        ),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="note",
                permitted_anchor_type_keys=("person",),
                property_constraints=(
                    PropertyConstraint(
                        property_name="rating",
                        required=False,
                        json_kind=JsonKind.NUMBER,
                        description="An optional rating.",
                    ),
                    PropertyConstraint(
                        property_name="tag",
                        required=False,
                        json_kind=JsonKind.STRING,
                        description="An optional tag.",
                    ),
                ),
                description="A note about a person.",
            ),
            AssociatedDataTypeDefinition(
                type_key="badge",
                permitted_anchor_type_keys=("person",),
                description="A badge a person holds.",
            ),
        ),
        link_types=(
            link("knows", ("person",), ("person",)),
            link("mentors", ("person",), ("person",)),
        ),
    )


@pytest.fixture
def sharp(tmp_path: Path):
    """Ada knows Grace and mentors Hugh; only Ada carries a note."""
    system = _system_with(tmp_path, _discriminating_definitions())
    hugh = Anchor(uuid="a-3", type_key="person", display_name="Hugh")
    assert system.apply_graph_change(
        GraphChange(
            anchor_upserts=(ADA, GRACE, hugh),
            associated_data_upserts=(
                AssociatedDataObject(
                    uuid="n-1",
                    type_key="note",
                    anchor_uuids=("a-1",),
                    properties={"rating": normalize(3), "tag": normalize("green")},
                ),
                AssociatedDataObject(uuid="b-1", type_key="badge", anchor_uuids=("a-2",)),
            ),
            link_upserts=(
                Link(uuid="l-1", type_key="knows", source_uuid="a-1", target_uuid="a-2"),
                Link(uuid="l-2", type_key="mentors", source_uuid="a-1", target_uuid="a-3"),
            ),
        ),
        provenance=_owner(),
    ).accepted
    try:
        yield system
    finally:
        system.close()


def _between(link_type: str = "knows") -> GraphQuery:
    return GraphQuery(
        anchor_groups=(
            AnchorGroup(name="from", anchor_types=("person",)),
            AnchorGroup(name="to", anchor_types=("person",)),
        ),
        required_links=(
            RequiredLink(name="edge", source_group="from", target_group="to", link_type=link_type),
        ),
        return_shape=ReturnShape(
            projections=(
                AnchorProjection(name="a", anchor_group="from"),
                AnchorProjection(name="b", anchor_group="to"),
            )
        ),
        maximum_rows=10,
    )


def test_a_required_link_matches_only_in_its_stated_direction(sharp: RTGSystem) -> None:
    """Excludes an undirected join.

    Both ends select people here, so an evaluator that matched a link either way round
    would answer with the reversed pair as well.
    """
    result = sharp.query_graph(_between())

    assert result.accepted, result.findings
    assert [(row.anchors[0].anchor.uuid, row.anchors[1].anchor.uuid) for row in result.rows] == [
        ("a-1", "a-2")
    ]


def test_a_required_link_matches_only_its_own_type(sharp: RTGSystem) -> None:
    """Excludes ignoring the link type: Ada mentors Hugh, and that is a different edge."""
    result = sharp.query_graph(_between("mentors"))

    assert result.accepted, result.findings
    assert [(row.anchors[0].anchor.uuid, row.anchors[1].anchor.uuid) for row in result.rows] == [
        ("a-1", "a-3")
    ]


def _grounded_in(data_type: str = "note") -> GraphQuery:
    return GraphQuery(
        anchor_groups=(_people(),),
        data_conditions=(
            AssociatedDataCondition(
                name="data", anchor_group="people", associated_data_type=data_type
            ),
        ),
        return_shape=ReturnShape(
            projections=(AnchorProjection(name="who", anchor_group="people"),)
        ),
        maximum_rows=10,
    )


def test_a_data_condition_selects_only_its_own_type(sharp: RTGSystem) -> None:
    """Excludes ignoring the type: Grace's badge is not a note."""
    assert _bound_anchors(sharp.query_graph(_grounded_in("note"))) == {"a-1"}
    assert _bound_anchors(sharp.query_graph(_grounded_in("badge"))) == {"a-2"}


def test_a_data_condition_selects_only_directly_associated_data(sharp: RTGSystem) -> None:
    """Excludes pairing every object of the type with every anchor.

    Hugh carries nothing, so an evaluator that skipped the grounding test would bind him
    to Ada's note and answer with all three people.
    """
    assert _bound_anchors(sharp.query_graph(_grounded_in())) == {"a-1"}


# --- Comparisons ----------------------------------------------------------------------


def _compared(
    comparison: PropertyComparison, expected, property_name: str = "rating"
) -> GraphQuery:
    return GraphQuery(
        anchor_groups=(_people(),),
        data_conditions=(
            AssociatedDataCondition(
                name="notes",
                anchor_group="people",
                associated_data_type="note",
                property_conditions=(
                    DataPropertyCondition(
                        property_name=property_name,
                        comparison=comparison,
                        expected_value=expected,
                    ),
                ),
            ),
        ),
        return_shape=ReturnShape(
            projections=(AssociatedDataProjection(name="note", data_condition="notes"),)
        ),
        maximum_rows=10,
    )


@pytest.fixture
def rated(tmp_path: Path):
    """Three notes: rating 2, rating 3, and one with no rating at all."""
    system = _system_with(tmp_path, _discriminating_definitions())
    assert system.apply_graph_change(
        GraphChange(
            anchor_upserts=(ADA,),
            associated_data_upserts=(
                AssociatedDataObject(
                    uuid="n-2",
                    type_key="note",
                    anchor_uuids=("a-1",),
                    properties={"rating": normalize(2)},
                ),
                AssociatedDataObject(
                    uuid="n-3",
                    type_key="note",
                    anchor_uuids=("a-1",),
                    properties={"rating": normalize(3)},
                ),
                AssociatedDataObject(uuid="n-4", type_key="note", anchor_uuids=("a-1",)),
            ),
        ),
        provenance=_owner(),
    ).accepted
    try:
        yield system
    finally:
        system.close()


def _matched(system: RTGSystem, query: GraphQuery) -> set[str]:
    result = system.query_graph(query)
    assert result.accepted, result.findings
    return {row.associated_data[0].associated_data.uuid for row in result.rows}


@pytest.mark.parametrize(
    ("comparison", "expected", "matches"),
    [
        (PropertyComparison.EQUAL, 3, {"n-3"}),
        (PropertyComparison.NOT_EQUAL, 3, {"n-2"}),
        (PropertyComparison.LESS_THAN, 3, {"n-2"}),
        (PropertyComparison.LESS_THAN_OR_EQUAL, 3, {"n-2", "n-3"}),
        (PropertyComparison.GREATER_THAN, 2, {"n-3"}),
        (PropertyComparison.GREATER_THAN_OR_EQUAL, 2, {"n-2", "n-3"}),
    ],
    ids=["equal", "not-equal", "less-than", "at-most", "greater-than", "at-least"],
)
def test_each_comparison_selects_at_its_own_boundary(
    rated: RTGSystem, comparison: PropertyComparison, expected: int, matches: set[str]
) -> None:
    """Every operator, each with a stored value exactly on its boundary.

    n-4 carries no rating and appears in none of them, which is the presence rule: an
    omitted property is not a value, so it is neither equal nor unequal to one.
    """
    assert _matched(rated, _compared(comparison, normalize(expected))) == matches


def test_an_omitted_property_satisfies_neither_equality_nor_inequality(
    rated: RTGSystem,
) -> None:
    """Excludes reading an absent property as null and comparing that.

    This is the distinction the model keeps everywhere: absence is not a value. Under
    ``notEqual`` in particular, treating it as one would make the note with no rating
    match every comparison rather than none.
    """
    assert "n-4" not in _matched(rated, _compared(PropertyComparison.EQUAL, normalize(3)))
    assert "n-4" not in _matched(rated, _compared(PropertyComparison.NOT_EQUAL, normalize(3)))
    assert "n-4" not in _matched(rated, _compared(PropertyComparison.GREATER_THAN, normalize(0)))


def test_equality_compares_lossless_json_values(rated: RTGSystem) -> None:
    """Excludes comparing numbers by their stored text: 3 and 3.00 are one number."""
    assert _matched(rated, _compared(PropertyComparison.EQUAL, normalize(Decimal("3.00")))) == {
        "n-3"
    }
    assert _matched(rated, _compared(PropertyComparison.EQUAL, normalize(Decimal("3e0")))) == {
        "n-3"
    }
    assert _matched(rated, _compared(PropertyComparison.NOT_EQUAL, normalize(Decimal("3.00")))) == {
        "n-2"
    }


def test_number_equality_does_not_distinguish_signed_zero(rated: RTGSystem) -> None:
    assert rated.apply_graph_change(
        GraphChange(
            anchor_upserts=(Anchor("zero-anchor", "person", "Zero"),),
            associated_data_upserts=(
                AssociatedDataObject(
                    "n-zero",
                    "note",
                    ("zero-anchor",),
                    {"rating": normalize(Decimal("-0"))},
                ),
            ),
        ),
        provenance=_owner(),
    ).accepted

    assert "n-zero" in _matched(rated, _compared(PropertyComparison.EQUAL, normalize(Decimal("0"))))
    assert "n-zero" not in _matched(
        rated, _compared(PropertyComparison.NOT_EQUAL, normalize(Decimal("0")))
    )


# --- Projections ----------------------------------------------------------------------


def test_a_projected_link_returns_the_link_that_satisfied_it(sharp: RTGSystem) -> None:
    query = GraphQuery(
        anchor_groups=(
            AnchorGroup(name="from", anchor_types=("person",)),
            AnchorGroup(name="to", anchor_types=("person",)),
        ),
        required_links=(
            RequiredLink(name="edge", source_group="from", target_group="to", link_type="knows"),
        ),
        return_shape=ReturnShape(projections=(LinkProjection(name="link", required_link="edge"),)),
        maximum_rows=10,
    )

    result = sharp.query_graph(query)

    assert result.accepted, result.findings
    assert [
        (binding.projection, binding.link.uuid) for row in result.rows for binding in row.links
    ] == [("link", "l-1")]
    assert all(row.anchors == () for row in result.rows)


# --- Failure and precondition ---------------------------------------------------------


def test_a_query_against_an_unestablished_rtg_is_refused(tmp_path: Path) -> None:
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        result = system.query_graph(_just_people())

        assert result.status is OperationStatus.REJECTED
        assert result.rows == ()
        assert result.evaluated_revision is None
        assert any("no canonical state is established" in each.summary for each in result.findings)
    finally:
        system.close()


def test_a_query_a_damaged_store_cannot_answer_reports_failure(system: RTGSystem) -> None:
    """Excludes an untyped store error crossing the boundary as an exception."""
    system.store._connection.execute("DROP TABLE state_head")  # noqa: SLF001

    result = system.query_graph(_just_people())

    assert result.status is OperationStatus.FAILED
    assert result.rows == ()
    assert result.evaluated_revision is None
    assert result.findings


def test_a_comparison_no_stored_value_could_satisfy_is_answered_not_refused(
    rated: RTGSystem,
) -> None:
    """Excludes refusing a well-formed question because its answer is empty.

    Shape, range, and pattern are rules about what may be stored. Screening an operand
    against them would also refuse the one question that could find a non-conforming row
    in a graph this system did not establish.
    """
    assert _matched(rated, _compared(PropertyComparison.EQUAL, normalize(Decimal("99")))) == set()
    assert _matched(
        rated, _compared(PropertyComparison.GREATER_THAN, normalize(Decimal("99")))
    ) == (set())
    assert _matched(rated, _compared(PropertyComparison.NOT_EQUAL, normalize(Decimal("99")))) == {
        "n-2",
        "n-3",
    }


def test_a_query_that_matches_nothing_is_accepted_with_no_rows(system: RTGSystem) -> None:
    """An empty answer is the ordinary answer to a question nothing satisfies."""
    result = system.query_graph(
        GraphQuery(
            anchor_groups=(
                AnchorGroup(
                    name="people",
                    anchor_types=("person",),
                    uuid_filter=AnchorUuidFilter(uuids=("a-1",)),
                ),
                AnchorGroup(name="projects", anchor_types=("project",)),
            ),
            # l-3 runs from Grace, and the group above admits only Ada, so no assignment
            # satisfies both.
            required_links=(
                RequiredLink(
                    name="works",
                    source_group="people",
                    target_group="projects",
                    link_type="worksOn",
                    uuid_filter=LinkUuidFilter(uuids=("l-3",)),
                ),
            ),
            return_shape=ReturnShape(
                projections=(AnchorProjection(name="who", anchor_group="people"),)
            ),
            maximum_rows=10,
        )
    )

    assert result.status is OperationStatus.ACCEPTED
    assert result.rows == ()
    assert result.evaluated_revision == materialize_state(system).revision
    assert result.findings == ()


def test_the_evaluated_revision_follows_the_state_it_was_read_at(system: RTGSystem) -> None:
    """Excludes reporting a fixed revision: it must move when canonical state does."""
    first = system.query_graph(_just_people())
    assert first.evaluated_revision == 1

    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor(uuid="a-9", type_key="person", display_name="Ida"),)),
        provenance=_owner(),
    ).accepted

    second = system.query_graph(_just_people())
    assert second.evaluated_revision == 2


def _one_property(property_name: str = "rating") -> GraphQuery:
    """Projects a property and nothing that would separate the rows for it."""
    return GraphQuery(
        anchor_groups=(_people(),),
        data_conditions=(
            AssociatedDataCondition(
                name="notes", anchor_group="people", associated_data_type="note"
            ),
        ),
        return_shape=ReturnShape(
            projections=(
                DataPropertyProjection(
                    name="value", data_condition="notes", property_name=property_name
                ),
            )
        ),
        maximum_rows=10,
    )


def _nested_property_definitions(json_kind):
    from vellis.definitions import PropertyConstraint

    definitions = _endpoint_definitions()
    note = definitions.associated_data_types[0]
    return replace(
        definitions,
        associated_data_types=(
            replace(
                note,
                property_constraints=(
                    *note.property_constraints,
                    PropertyConstraint(
                        property_name="payload",
                        required=False,
                        json_kind=json_kind,
                        description="A nested value used to exercise semantic JSON identity.",
                    ),
                ),
            ),
        ),
    )


def test_a_projected_property_participates_in_row_identity(rated: RTGSystem) -> None:
    """Excludes a dedup key that ignores the property it was asked for.

    Nothing else is projected here, so two notes with different ratings collapse into one
    row unless the value is part of what makes a row distinct — and 3 and 3.00 are one
    number, so they must not.
    """
    result = rated.query_graph(_one_property())
    assert result.accepted, result.findings

    values = sorted(
        (each.present, str(each.value)) for row in result.rows for each in row.properties
    )
    assert values == [(False, "None"), (True, "2"), (True, "3")]


@pytest.mark.parametrize(
    "values",
    [
        ({"n": Decimal("3")}, {"n": Decimal("3.00")}),
        ([Decimal("3")], [Decimal("3.00")]),
    ],
    ids=["nested-object-number", "nested-array-number"],
)
@pytest.mark.parametrize(
    "state_scope",
    [
        EvaluatedStateScope.CURRENT,
        EvaluatedStateScope.PROSPECTIVE,
        EvaluatedStateScope.HISTORICAL,
    ],
    ids=["current", "prospective", "historical"],
)
def test_nested_numeric_spellings_are_one_bounded_semantic_row(
    tmp_path: Path, values: tuple[object, object], state_scope: EvaluatedStateScope
) -> None:
    """Storage spelling cannot turn one JSON value into an over-limit answer."""
    from vellis.json_value import JsonKind

    kind = JsonKind.ARRAY if isinstance(values[0], list) else JsonKind.OBJECT
    system = _system_with(tmp_path, _nested_property_definitions(kind))
    try:
        outcome = system.apply_graph_change(
            GraphChange(
                anchor_upserts=(ADA,),
                associated_data_upserts=tuple(
                    AssociatedDataObject(
                        uuid=f"n-{index}",
                        type_key="note",
                        anchor_uuids=("a-1",),
                        properties={"payload": normalize(value)},
                    )
                    for index, value in enumerate(values, start=1)
                ),
            ),
            provenance=_owner(),
        )
        assert outcome.accepted and outcome.resulting_revision is not None
        if state_scope is EvaluatedStateScope.PROSPECTIVE:
            assert system.set_definition_delta(
                DefinitionChange(
                    anchor_type_upserts=(
                        AnchorTypeDefinition("query-fixture-only", "An unrelated proposed type."),
                    )
                ),
                provenance=_owner(),
            ).accepted
        selection = (
            RevisionSelection(outcome.resulting_revision)
            if state_scope is EvaluatedStateScope.HISTORICAL
            else None
        )
        query = replace(
            _one_property("payload"),
            maximum_rows=1,
            state_scope=state_scope,
            historical_selection=selection,
        )

        result = system.query_graph(query)

        assert result.accepted, result.findings
        assert len(result.rows) == 1
    finally:
        system.close()


def test_many_serialized_spellings_stream_without_a_global_sql_distinct_set(
    tmp_path: Path,
) -> None:
    """Semantic duplicates cannot create an unbounded SQLite DISTINCT materialization."""
    from vellis.json_value import JsonKind

    system = _system_with(tmp_path, _nested_property_definitions(JsonKind.OBJECT))
    statements: list[str] = []
    try:
        spellings = tuple(Decimal("3." + ("0" * places)) for places in range(1, 257))
        outcome = system.apply_graph_change(
            GraphChange(
                anchor_upserts=(ADA,),
                associated_data_upserts=tuple(
                    AssociatedDataObject(
                        uuid=f"n-{index}",
                        type_key="note",
                        anchor_uuids=("a-1",),
                        properties={"payload": normalize({"n": spelling})},
                    )
                    for index, spelling in enumerate(spellings, start=1)
                ),
            ),
            provenance=_owner(),
        )
        assert outcome.accepted
        query = replace(_one_property("payload"), maximum_rows=1)
        system.store._connection.set_trace_callback(statements.append)  # noqa: SLF001

        result = system.query_graph(query)

        assert result.accepted, result.findings
        assert len(result.rows) == 1
        projection_statements = [
            statement for statement in statements if "object_property AS pp0" in statement
        ]
        assert len(projection_statements) == 1, [
            statement for statement in statements if "object_property" in statement
        ]
        assert "SELECT DISTINCT" not in projection_statements[0].upper()
    finally:
        system.store._connection.set_trace_callback(None)  # noqa: SLF001
        system.close()


def test_maximum_rows_rejects_genuinely_unequal_nested_values(tmp_path: Path) -> None:
    from vellis.json_value import JsonKind

    system = _system_with(tmp_path, _nested_property_definitions(JsonKind.OBJECT))
    try:
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(ADA,),
                associated_data_upserts=(
                    AssociatedDataObject(
                        "n-1", "note", ("a-1",), {"payload": normalize({"n": Decimal("3")})}
                    ),
                    AssociatedDataObject(
                        "n-2",
                        "note",
                        ("a-1",),
                        {"payload": normalize({"n": Decimal("3.01")})},
                    ),
                ),
            ),
            provenance=_owner(),
        ).accepted

        result = system.query_graph(replace(_one_property("payload"), maximum_rows=1))

        assert result.status is OperationStatus.REJECTED
        assert result.rows == ()
        assert "exceeds the maximum of 1" in result.findings[0].summary
    finally:
        system.close()


def test_semantic_projection_deduplication_does_not_change_object_aggregation(
    tmp_path: Path,
) -> None:
    from vellis.json_value import JsonKind

    system = _system_with(tmp_path, _nested_property_definitions(JsonKind.ARRAY))
    try:
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(ADA,),
                associated_data_upserts=(
                    AssociatedDataObject(
                        "n-1", "note", ("a-1",), {"payload": normalize([Decimal("3")])}
                    ),
                    AssociatedDataObject(
                        "n-2", "note", ("a-1",), {"payload": normalize([Decimal("3.00")])}
                    ),
                ),
            ),
            provenance=_owner(),
        ).accepted
        query = replace(
            _one_property("payload"),
            aggregations=(
                QueryAggregation(
                    name="note-count", operator=AggregationOperator.COUNT, data_condition="notes"
                ),
            ),
            maximum_rows=2,
        )

        result = system.query_graph(query)

        assert result.accepted, result.findings
        assert len(result.rows) == 1
        assert result.aggregates[0].value == Decimal(2)
    finally:
        system.close()


def test_presence_alone_distinguishes_two_rows(tmp_path: Path) -> None:
    """An absent property and a stored null are two answers, not one."""
    system = _system_with(tmp_path, _endpoint_definitions())
    try:
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(ADA,),
                associated_data_upserts=(
                    AssociatedDataObject(uuid="n-1", type_key="note", anchor_uuids=("a-1",)),
                    AssociatedDataObject(
                        uuid="n-2",
                        type_key="note",
                        anchor_uuids=("a-1",),
                        properties={"marker": normalize(None)},
                    ),
                ),
            ),
            provenance=_owner(),
        ).accepted

        result = system.query_graph(_one_property("marker"))

        assert result.accepted, result.findings
        assert sorted(each.present for row in result.rows for each in row.properties) == [
            False,
            True,
        ]
    finally:
        system.close()


def test_a_projected_link_participates_in_row_identity(sharp: RTGSystem) -> None:
    """Excludes a dedup key that ignores the link it was asked for.

    Two links of the same type between the same pair are two distinct facts. With only
    the link projected, nothing else separates them.
    """
    assert sharp.apply_graph_change(
        GraphChange(
            link_upserts=(Link(uuid="l-9", type_key="knows", source_uuid="a-1", target_uuid="a-2"),)
        ),
        provenance=_owner(),
    ).accepted

    query = GraphQuery(
        anchor_groups=(
            AnchorGroup(name="from", anchor_types=("person",)),
            AnchorGroup(name="to", anchor_types=("person",)),
        ),
        required_links=(
            RequiredLink(name="edge", source_group="from", target_group="to", link_type="knows"),
        ),
        return_shape=ReturnShape(projections=(LinkProjection(name="link", required_link="edge"),)),
        maximum_rows=10,
    )

    result = sharp.query_graph(query)

    assert result.accepted, result.findings
    assert sorted(binding.link.uuid for row in result.rows for binding in row.links) == [
        "l-1",
        "l-9",
    ]


def test_a_string_property_orders_by_code_point(tmp_path: Path) -> None:
    """Ordering a string is what makes a date range askable.

    The starter writes dates as patterned strings, so an owner asking what falls before a
    date is asking this. Code point is the basis equality already uses, so ordering adds
    no second notion of what a stored string is — and it is deliberately not case folding
    or locale collation, which is why an uppercase value that sorts before every lowercase
    one is in the fixture rather than a tidier set.
    """
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        assert system.initialize_fresh(
            build_rich_definitions(), provenance=_owner(), initialization_summary="a fresh start"
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(ADA,),
                associated_data_upserts=(
                    _note("n-1", ("a-1",), year="2024"),
                    _note("n-2", ("a-1",), year="2026"),
                    _note("n-3", ("a-1",), year="2028"),
                    _note("n-4", ("a-1",), tag="green"),
                ),
            ),
            provenance=_owner(),
        ).accepted

        def years(comparison: PropertyComparison, expected: str) -> set[str]:
            result = system.query_graph(
                GraphQuery(
                    anchor_groups=(AnchorGroup(name="people", anchor_types=("person",)),),
                    data_conditions=(
                        AssociatedDataCondition(
                            name="notes",
                            anchor_group="people",
                            associated_data_type="note",
                            property_conditions=(
                                DataPropertyCondition(
                                    property_name="year",
                                    comparison=comparison,
                                    expected_value=normalize(expected),
                                ),
                            ),
                        ),
                    ),
                    return_shape=ReturnShape(
                        projections=(
                            DataPropertyProjection(
                                name="year", data_condition="notes", property_name="year"
                            ),
                        )
                    ),
                    maximum_rows=20,
                )
            )
            assert result.status is OperationStatus.ACCEPTED, result.findings
            return {
                str(each.value) for row in result.rows for each in row.properties if each.present
            }

        assert years(PropertyComparison.LESS_THAN, "2026") == {"2024"}
        assert years(PropertyComparison.LESS_THAN_OR_EQUAL, "2026") == {"2024", "2026"}
        assert years(PropertyComparison.GREATER_THAN, "2026") == {"2028"}
        assert years(PropertyComparison.GREATER_THAN_OR_EQUAL, "2024") == {"2024", "2026", "2028"}
        # The note carrying no year is never selected: omission is not a value to order.
        assert years(PropertyComparison.GREATER_THAN, "0000") == {"2024", "2026", "2028"}
    finally:
        system.close()


def test_string_ordering_agrees_between_the_stored_and_replayed_graph(tmp_path: Path) -> None:
    """Both realizations must order the same way, or memory depends on where it is read.

    SQLite compares text byte-wise over UTF-8 while the in-memory path compares Python
    strings by code point. Those agree, but only because UTF-8 byte order is code-point
    order — a collation on the column would silently break it, and only a value outside
    ASCII would notice.
    """
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        assert system.initialize_fresh(
            build_rich_definitions(), provenance=_owner(), initialization_summary="a fresh start"
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(ADA,),
                associated_data_upserts=(
                    _note("n-1", ("a-1",), title="Zebra"),
                    _note("n-2", ("a-1",), title="apple"),
                    _note("n-3", ("a-1",), title="Ábaco"),
                    _note("n-4", ("a-1",), title="🍞 bread"),
                ),
            ),
            provenance=_owner(),
        ).accepted
        stored = materialize_state(system)
        titles = sorted(str(each.properties["title"]) for each in stored.graph.associated_data)

        selected = system.query_graph(
            GraphQuery(
                anchor_groups=(AnchorGroup(name="people", anchor_types=("person",)),),
                data_conditions=(
                    AssociatedDataCondition(
                        name="notes",
                        anchor_group="people",
                        associated_data_type="note",
                        property_conditions=(
                            DataPropertyCondition(
                                property_name="title",
                                comparison=PropertyComparison.LESS_THAN,
                                expected_value=normalize("apple"),
                            ),
                        ),
                    ),
                ),
                return_shape=ReturnShape(
                    projections=(
                        DataPropertyProjection(
                            name="title", data_condition="notes", property_name="title"
                        ),
                    )
                ),
                maximum_rows=20,
            )
        )
        assert selected.status is OperationStatus.ACCEPTED, selected.findings
        returned = {
            str(each.value) for row in selected.rows for each in row.properties if each.present
        }
        # Python's own code-point order is the oracle; the query must reproduce exactly it.
        assert returned == {title for title in titles if title < "apple"}
        assert "Zebra" in returned and "apple" not in returned
    finally:
        system.close()


def test_an_anchor_group_may_name_several_types(system: RTGSystem) -> None:
    """One question about work of several shapes should be one question.

    The union has to mean exactly what the separate queries meant together, or an owner
    asking "everything" gets a different answer from an owner asking twice and adding.
    """
    both = system.query_graph(
        GraphQuery(
            anchor_groups=(AnchorGroup(name="things", anchor_types=("person", "project")),),
            return_shape=ReturnShape(
                projections=(AnchorProjection(name="thing", anchor_group="things"),)
            ),
            maximum_rows=20,
        )
    )
    assert both.status is OperationStatus.ACCEPTED, both.findings
    separate: set[str] = set()
    for type_key in ("person", "project"):
        one = system.query_graph(
            GraphQuery(
                anchor_groups=(AnchorGroup(name="things", anchor_types=(type_key,)),),
                return_shape=ReturnShape(
                    projections=(AnchorProjection(name="thing", anchor_group="things"),)
                ),
                maximum_rows=20,
            )
        )
        assert one.status is OperationStatus.ACCEPTED, one.findings
        separate |= {row.anchors[0].anchor.uuid for row in one.rows}
    assert {row.anchors[0].anchor.uuid for row in both.rows} == separate
    assert len(both.rows) == len(separate)


def test_projecting_anchors_preserves_identity_for_exact_object_counts(
    system: RTGSystem,
) -> None:
    """Two indistinguishable display values remain two identity-bearing rows."""
    changed = system.apply_graph_change(
        GraphChange(
            anchor_upserts=(
                Anchor("a-3", "person", "Call the dentist"),
                Anchor("a-4", "person", "Call the dentist"),
            )
        ),
        provenance=_owner(),
    )
    assert changed.accepted, changed.findings

    result = system.query_graph(_just_people(maximum_rows=10))

    assert result.accepted, result.findings
    assert _bound_anchors(result) == {"a-1", "a-2", "a-3", "a-4"}
    assert len(result.rows) == 4


def test_anchor_count_uses_distinct_identity_when_other_projections_repeat_it(
    system: RTGSystem,
) -> None:
    """One anchor with two matching data objects legitimately occupies two tuples."""
    result = system.query_graph(
        GraphQuery(
            anchor_groups=(AnchorGroup(name="people", anchor_types=("person",)),),
            data_conditions=(
                AssociatedDataCondition(
                    name="notes", anchor_group="people", associated_data_type="note"
                ),
            ),
            return_shape=ReturnShape(
                projections=(
                    AnchorProjection(name="person", anchor_group="people"),
                    AssociatedDataProjection(name="note", data_condition="notes"),
                )
            ),
            maximum_rows=10,
        )
    )

    assert result.accepted, result.findings
    assert len(result.rows) == 3
    assert {row.anchors[0].anchor.uuid for row in result.rows} == {"a-1", "a-2"}


def _rating_query(*aggregations: QueryAggregation, maximum: int = 20) -> GraphQuery:
    return GraphQuery(
        anchor_groups=(AnchorGroup(name="people", anchor_types=("person",)),),
        data_conditions=(
            AssociatedDataCondition(
                name="notes", anchor_group="people", associated_data_type="note"
            ),
        ),
        return_shape=ReturnShape(projections=()),
        aggregations=aggregations,
        maximum_rows=maximum,
    )


def test_aggregation_counts_matching_objects_not_distinct_projected_tuples(
    tmp_path: Path,
) -> None:
    """The whole reason to aggregate in the system is that projections deduplicate.

    Two notes carrying the same rating are one projected tuple and two objects. Summing a
    projection of those values silently answers a smaller question, and nothing about the
    result says so, which is why the arithmetic belongs here.
    """
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        assert system.initialize_fresh(
            build_rich_definitions(), provenance=_owner(), initialization_summary="a fresh start"
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(ADA,),
                associated_data_upserts=(
                    _note("n-1", ("a-1",), rating=2),
                    _note("n-2", ("a-1",), rating=2),
                    _note("n-3", ("a-1",), rating=5),
                    _note("n-4", ("a-1",)),
                ),
            ),
            provenance=_owner(),
        ).accepted

        result = system.query_graph(
            _rating_query(
                QueryAggregation(
                    name="howMany", operator=AggregationOperator.COUNT, data_condition="notes"
                ),
                QueryAggregation(
                    name="total",
                    operator=AggregationOperator.SUM,
                    data_condition="notes",
                    property_name="rating",
                ),
                QueryAggregation(
                    name="lowest",
                    operator=AggregationOperator.MINIMUM,
                    data_condition="notes",
                    property_name="rating",
                ),
                QueryAggregation(
                    name="highest",
                    operator=AggregationOperator.MAXIMUM,
                    data_condition="notes",
                    property_name="rating",
                ),
            )
        )
        assert result.status is OperationStatus.ACCEPTED, result.findings
        answers = {each.aggregation: each for each in result.aggregates}
        assert answers["howMany"].value == Decimal(4)
        # Nine, not seven: the two ratings of 2 are two objects even though a projection
        # of them would be one row.
        assert answers["total"].value == Decimal(9)
        assert answers["lowest"].value == Decimal(2)
        assert answers["highest"].value == Decimal(5)
    finally:
        system.close()


def test_sum_preserves_exact_numbers_beyond_the_decimal_context(tmp_path: Path) -> None:
    """A carry beyond 28 digits must not be rounded by the process-wide context."""
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        definitions = build_rich_definitions()
        note_type = definitions.associated_data_types[0]
        definitions = replace(
            definitions,
            associated_data_types=(
                replace(
                    note_type,
                    property_constraints=tuple(
                        replace(rule, value_range=None) if rule.property_name == "rating" else rule
                        for rule in note_type.property_constraints
                    ),
                ),
            ),
        )
        assert system.initialize_fresh(
            definitions, provenance=_owner(), initialization_summary="a fresh start"
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(ADA,),
                associated_data_upserts=(
                    _note("n-1", ("a-1",), rating=Decimal("123456789012345678901234567890")),
                    _note("n-2", ("a-1",), rating=1),
                ),
            ),
            provenance=_owner(),
        ).accepted
        query = _rating_query(
            QueryAggregation(
                name="total",
                operator=AggregationOperator.SUM,
                data_condition="notes",
                property_name="rating",
            )
        )

        stored = system.query_graph(query)
        state = materialize_state(system)
        in_memory = evaluate_query(query, definitions, state.graph, state.revision)
        exact = Decimal("123456789012345678901234567891")

        assert stored.status is OperationStatus.ACCEPTED, stored.findings
        assert stored.aggregates[0].value == exact
        assert in_memory.aggregates[0].value == exact
    finally:
        system.close()


def test_sum_preserves_exact_numbers_at_the_decimal_exponent_boundary(tmp_path: Path) -> None:
    """An unrepresentable exact sum is a whole typed refusal, never an exception."""
    enormous = Decimal("9e999999999999999999")
    assert enormous.is_finite()
    base = build_rich_definitions()
    definitions = replace(
        base,
        associated_data_types=(
            replace(
                base.associated_data_types[0],
                property_constraints=tuple(
                    replace(rule, value_range=None) if rule.property_name == "rating" else rule
                    for rule in base.associated_data_types[0].property_constraints
                ),
            ),
        ),
    )
    graph = Graph(
        anchors=(ADA,),
        associated_data=(
            _note("n-1", ("a-1",), rating=enormous),
            _note("n-2", ("a-1",), rating=enormous),
        ),
    )
    query = _rating_query(
        QueryAggregation(
            name="total",
            operator=AggregationOperator.SUM,
            data_condition="notes",
            property_name="rating",
        )
    )
    in_memory = evaluate_query(query, definitions, graph, 0)

    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        assert system.initialize_fresh(
            definitions, provenance=_owner(), initialization_summary="a fresh start"
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=graph.anchors,
                associated_data_upserts=graph.associated_data,
            ),
            provenance=_owner(),
        ).accepted
        stored = system.query_graph(query)
    finally:
        system.close()

    for result in (in_memory, stored):
        assert result.status is OperationStatus.REJECTED
        assert not result.rows and not result.aggregates
        assert "could not be returned" in result.summary
        assert "outside the finite decimal result range" in result.findings[0].summary


def test_sum_refuses_compact_inputs_that_require_population_sized_expansion() -> None:
    """A wide exponent gap is decided before constructing its million-digit coefficient."""
    base = build_rich_definitions()
    note_type = base.associated_data_types[0]
    definitions = replace(
        base,
        associated_data_types=(
            replace(
                note_type,
                property_constraints=tuple(
                    replace(rule, value_range=None) if rule.property_name == "rating" else rule
                    for rule in note_type.property_constraints
                ),
            ),
        ),
    )
    result = evaluate_query(
        _rating_query(
            QueryAggregation(
                name="total",
                operator=AggregationOperator.SUM,
                data_condition="notes",
                property_name="rating",
            )
        ),
        definitions,
        Graph(
            anchors=(ADA,),
            associated_data=(
                _note("n-1", ("a-1",), rating=Decimal(1)),
                _note("n-2", ("a-1",), rating=Decimal("1e-1000000")),
            ),
        ),
        0,
    )

    assert result.status is OperationStatus.REJECTED
    assert not result.rows and not result.aggregates
    assert "expanding compact numeric inputs" in result.findings[0].summary


def test_aggregation_agrees_between_the_stored_and_in_memory_graph(tmp_path: Path) -> None:
    """Component pruning must retain every identity that can change an aggregate."""
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        definitions = build_rich_definitions()
        assert system.initialize_fresh(
            definitions, provenance=_owner(), initialization_summary="a fresh start"
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(ADA,),
                associated_data_upserts=(
                    _note("n-1", ("a-1",), rating=2),
                    _note("n-2", ("a-1",), rating=5),
                ),
            ),
            provenance=_owner(),
        ).accepted
        query = _rating_query(
            QueryAggregation(
                name="howMany", operator=AggregationOperator.COUNT, data_condition="notes"
            ),
            QueryAggregation(
                name="total",
                operator=AggregationOperator.SUM,
                data_condition="notes",
                property_name="rating",
            ),
            QueryAggregation(
                name="lowest",
                operator=AggregationOperator.MINIMUM,
                data_condition="notes",
                property_name="rating",
            ),
            QueryAggregation(
                name="highest",
                operator=AggregationOperator.MAXIMUM,
                data_condition="notes",
                property_name="rating",
            ),
        )

        stored = system.query_graph(query)
        state = materialize_state(system)
        in_memory = evaluate_query(query, definitions, state.graph, state.revision)

        assert stored.status is OperationStatus.ACCEPTED, stored.findings
        assert in_memory.status is OperationStatus.ACCEPTED, in_memory.findings
        assert in_memory.aggregates == stored.aggregates
        assert [(each.aggregation, each.present, each.value) for each in in_memory.aggregates] == [
            ("howMany", True, Decimal(2)),
            ("total", True, Decimal(7)),
            ("lowest", True, Decimal(2)),
            ("highest", True, Decimal(5)),
        ]

        mixed = GraphQuery(
            anchor_groups=query.anchor_groups,
            data_conditions=query.data_conditions,
            return_shape=ReturnShape(
                projections=(AssociatedDataProjection(name="note", data_condition="notes"),)
            ),
            aggregations=query.aggregations,
            maximum_rows=query.maximum_rows,
        )
        stored_mixed = system.query_graph(mixed)
        in_memory_mixed = evaluate_query(mixed, definitions, state.graph, state.revision)

        assert stored_mixed.status is OperationStatus.ACCEPTED, stored_mixed.findings
        assert stored_mixed.rows == in_memory_mixed.rows
        assert stored_mixed.aggregates == in_memory_mixed.aggregates
        assert len(stored_mixed.rows) == 2
        assert len(stored_mixed.aggregates) == 4
    finally:
        system.close()


class _GuardedCandidateTuple(tuple[AssociatedDataObject, ...]):
    """Fail if one candidate stream is consumed past an aggregation's decision point."""

    def __iter__(self):
        for position, value in enumerate(super().__iter__()):
            if position >= 5:
                raise AssertionError("aggregation consumed candidates after its bound was decided")
            yield value


class _BoundedAggregationIndex(_TestGraphIndex):
    def associated_data_candidates(
        self,
        associated_data_type: str,
        anchor_uuid: str,
        allowed_uuids: frozenset[str] | None = None,
    ) -> tuple[AssociatedDataObject, ...]:
        candidates = super().associated_data_candidates(
            associated_data_type, anchor_uuid, allowed_uuids
        )
        return _GuardedCandidateTuple(candidates)


def test_in_memory_aggregation_stops_when_the_maximum_is_decided() -> None:
    """Refusal at five matches must not retain or walk the remaining population."""
    definitions = build_rich_definitions()
    graph = Graph(
        anchors=(ADA,),
        associated_data=tuple(_note(f"n-{index}", ("a-1",), rating=index) for index in range(100)),
    )
    query = _rating_query(
        QueryAggregation(
            name="howMany", operator=AggregationOperator.COUNT, data_condition="notes"
        ),
        maximum=4,
    )

    result = evaluate_indexed_query(query, definitions, _BoundedAggregationIndex(graph), revision=1)

    assert result.status is OperationStatus.REJECTED
    assert result.aggregates == ()
    assert any("exceed the maximum" in finding.summary for finding in result.findings)


def test_an_aggregate_is_absent_when_nothing_carries_the_property(tmp_path: Path) -> None:
    """None is not zero, and a total of nothing should not read as a total of zero."""
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        assert system.initialize_fresh(
            build_rich_definitions(), provenance=_owner(), initialization_summary="a fresh start"
        ).accepted
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(ADA,), associated_data_upserts=(_note("n-1", ("a-1",)),)),
            provenance=_owner(),
        ).accepted

        result = system.query_graph(
            _rating_query(
                QueryAggregation(
                    name="howMany", operator=AggregationOperator.COUNT, data_condition="notes"
                ),
                QueryAggregation(
                    name="total",
                    operator=AggregationOperator.SUM,
                    data_condition="notes",
                    property_name="rating",
                ),
            )
        )
        assert result.status is OperationStatus.ACCEPTED, result.findings
        answers = {each.aggregation: each for each in result.aggregates}
        assert answers["howMany"].present and answers["howMany"].value == Decimal(1)
        assert not answers["total"].present
        assert answers["total"].value is None
    finally:
        system.close()


def test_an_aggregated_selection_larger_than_the_maximum_is_refused_whole(
    tmp_path: Path,
) -> None:
    """Returning one number is not a licence to read an unbounded population.

    The bound has always meant the work a query may do, not just the size of what comes
    back. An aggregate that scanned past it would keep the promise's words and drop its
    meaning, and nothing in the result would show the difference.
    """
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        assert system.initialize_fresh(
            build_rich_definitions(), provenance=_owner(), initialization_summary="a fresh start"
        ).accepted
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(ADA,),
                associated_data_upserts=tuple(
                    _note(f"n-{index}", ("a-1",), rating=1 + index % 5) for index in range(9)
                ),
            ),
            provenance=_owner(),
        ).accepted

        result = system.query_graph(
            _rating_query(
                QueryAggregation(
                    name="howMany", operator=AggregationOperator.COUNT, data_condition="notes"
                ),
                maximum=4,
            )
        )
        assert result.status is OperationStatus.REJECTED
        assert result.aggregates == ()
        assert any("exceed the maximum" in each.summary for each in result.findings)
    finally:
        system.close()
