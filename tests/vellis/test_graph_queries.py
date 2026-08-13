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

from decimal import Decimal
from pathlib import Path

import pytest
from conftest import build_rich_definitions

from vellis.canonical import Provenance
from vellis.changes import GraphChange
from vellis.graph import Anchor, AssociatedDataObject, Link
from vellis.json_value import normalize
from vellis.outcomes import OperationStatus
from vellis.query import (
    AnchorGroup,
    AnchorProjection,
    AnchorUuidFilter,
    AssociatedDataCondition,
    AssociatedDataProjection,
    DataPropertyCondition,
    DataPropertyProjection,
    GraphQuery,
    LinkProjection,
    LinkUuidFilter,
    PropertyComparison,
    RequiredLink,
    ReturnShape,
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
    return AnchorGroup(name=name, anchor_type="person", **overrides)  # pyright: ignore[reportArgumentType]


def _just_people(maximum_rows: int = 10, uuid_filter: AnchorUuidFilter | None = None) -> GraphQuery:
    return GraphQuery(
        anchor_groups=(AnchorGroup(name="people", anchor_type="person", uuid_filter=uuid_filter),),
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
    assert result.evaluated_revision == system.current_state().revision
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
        "EXPLAIN QUERY PLAN SELECT payload FROM current_graph_object"
        " WHERE object_kind = ? AND type_key = ?",
        ("anchor", "person"),
    ).fetchall()
    data_plan = connection.execute(
        "EXPLAIN QUERY PLAN SELECT o.payload FROM current_data_anchor AS da"
        " JOIN current_graph_object AS o ON o.uuid = da.data_uuid"
        " WHERE da.anchor_uuid = ? AND o.object_kind = ? AND o.type_key = ?",
        ("a-1", "associatedData", "note"),
    ).fetchall()
    link_plan = connection.execute(
        "EXPLAIN QUERY PLAN SELECT payload FROM current_graph_object"
        " WHERE object_kind = ? AND type_key = ? AND source_uuid = ? AND target_uuid = ?",
        ("link", "worksOn", "a-1", "p-1"),
    ).fetchall()

    assert any("current_graph_object_kind_type" in str(row) for row in anchor_plan)
    assert any("current_data_anchor_anchor" in str(row) for row in data_plan)
    assert any("current_graph_link_endpoints" in str(row) for row in link_plan)


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
    # Four linked endpoints and three returned links; 400 unrelated same-type
    # endpoints never become domain objects in the query evaluator.
    assert system.store.current_graph_object_decodes == 7
    assert system.store.current_graph_decodes == 0


def _worked_on(uuid_filter: LinkUuidFilter | None = None) -> GraphQuery:
    return GraphQuery(
        anchor_groups=(_people(), AnchorGroup(name="projects", anchor_type="project")),
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
            anchor_groups=(_people(), AnchorGroup(name="projects", anchor_type="project")),
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
            anchor_groups=(_people(), AnchorGroup("projects", "project")),
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
        # Two anchors, the sole linked note, and the returned link are decoded. The
        # other 99 directly associated, property-matching notes never reach comparison.
        assert system.store.current_graph_object_decodes == 4
    finally:
        system.close()


# --- Shaping --------------------------------------------------------------------------


def test_a_row_carries_only_the_requested_projections(system: RTGSystem) -> None:
    """Excludes returning a selector that only constrained the answer.

    The link and the notes below decide which rows exist and appear in none of them.
    """
    query = GraphQuery(
        anchor_groups=(_people(), AnchorGroup(name="projects", anchor_type="project")),
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
        anchor_groups=(AnchorGroup(name="projects", anchor_type="project"), _people()),
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
    system: RTGSystem, monkeypatch: pytest.MonkeyPatch
) -> None:
    import vellis.query as query_module

    additions = tuple(
        Anchor(f"person-{index}", "person", f"Person {index}") for index in range(30)
    ) + tuple(Anchor(f"project-{index}", "project", f"Project {index}") for index in range(30))
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=additions), provenance=_owner()
    ).accepted
    question = GraphQuery(
        anchor_groups=(
            AnchorGroup(name="people", anchor_type="person"),
            AnchorGroup(name="projects", anchor_type="project"),
        ),
        return_shape=ReturnShape(
            projections=(AnchorProjection(name="who", anchor_group="people"),)
        ),
        maximum_rows=100,
    )

    calls = 0
    original = query_module._project  # noqa: SLF001

    def counted(query, assignment):
        nonlocal calls
        calls += 1
        return original(query, assignment)

    monkeypatch.setattr(query_module, "_project", counted)
    result = system.query_graph(question)

    assert result.accepted, result.findings
    assert len(result.rows) == 32
    assert calls <= 66


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
                    AnchorGroup(name="people", anchor_type="person"),
                    AnchorGroup(name="projects", anchor_type="project"),
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


def test_a_query_changes_no_canonical_state_or_revision(system: RTGSystem) -> None:
    from vellis.canonical import canonical_state_equal

    before = system.current_state()
    records = system.store.canonical_record_count()

    assert system.query_graph(_just_people()).accepted
    assert not system.query_graph(_just_people(maximum_rows=1)).accepted

    assert canonical_state_equal(system.current_state(), before)
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
            AnchorGroup(name="from", anchor_type="person"),
            AnchorGroup(name="to", anchor_type="person"),
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


# --- Projections ----------------------------------------------------------------------


def test_a_projected_link_returns_the_link_that_satisfied_it(sharp: RTGSystem) -> None:
    query = GraphQuery(
        anchor_groups=(
            AnchorGroup(name="from", anchor_type="person"),
            AnchorGroup(name="to", anchor_type="person"),
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
    system.store._connection.execute("DROP TABLE current_state")  # noqa: SLF001

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
                    anchor_type="person",
                    uuid_filter=AnchorUuidFilter(uuids=("a-1",)),
                ),
                AnchorGroup(name="projects", anchor_type="project"),
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
    assert result.evaluated_revision == system.current_state().revision
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
            AnchorGroup(name="from", anchor_type="person"),
            AnchorGroup(name="to", anchor_type="person"),
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
