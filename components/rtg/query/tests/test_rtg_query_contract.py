from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

import pytest

from components.rtg.graph import (
    InMemoryRtgGraph,
    JsonObject,
    RtgAnchor,
    RtgDataObject,
    RtgDataObjectList,
    RtgGraphReadView,
    RtgLink,
    RtgLinkList,
    RtgObject,
    RtgObjectList,
    UuidInput,
)
from components.rtg.query import (
    RtgQueryAggregation,
    RtgQueryAnchorBucket,
    RtgQueryDataRequirement,
    RtgQueryDiagnosticOptions,
    RtgQueryLinkRequirement,
    RtgQueryOptions,
    RtgQueryOrderBy,
    RtgQueryPropertyPredicate,
    RtgQueryReturnSpec,
    RtgQuerySpec,
    RtgQuerySpecInvalid,
    RtgQueryUnsupported,
    SimpleRtgQueryEngine,
)

MODEL_EVIDENCE = {
    "ExecuteRtgQueryContractVerification": (
        "test_query_matches_links_data_predicates_and_shapes_returns",
        "test_query_reports_return_property_diagnostics_for_unresolved_paths",
        "test_query_reports_return_property_diagnostics_for_unbound_requirements",
        "test_query_rejects_unknown_return_property_requirement",
        "test_query_live_filter_and_overlay_do_not_mutate_graph",
        "test_query_orders_by_returned_property_path",
        "test_query_orders_arbitrary_precision_numbers_exactly",
        "test_query_order_by_must_reference_returned_property",
        "test_query_paginates_after_distinct_projection",
        "test_query_count_aggregation_groups_and_counts_distinct_bindings",
        "test_query_paginates_aggregate_rows",
        "test_query_rejects_ambiguous_binding_names_and_invalid_pagination_options",
        "test_optional_link_requirement_preserves_unlinked_source_rows",
        "test_chained_optional_links_preserve_rows_when_intermediate_source_is_unbound",
        "test_optional_link_cycle_with_no_source_context_returns_no_rows",
        "test_query_grouping_preserves_distinct_large_json_integers",
        "test_query_rejects_reserved_aggregation_names",
        "test_query_invalid_operator_has_structured_diagnostic",
        "test_query_json_equality_is_kind_sensitive_and_recursive",
        "test_query_predicate_operator_table_and_case_sensitivity",
        "test_query_rejects_unknown_diagnostic_guidance_with_structured_diagnostic",
        "test_query_regex_uses_re2_dialect_and_declared_flags",
    ),
    "RtgQueryBoundaryVerification": (
        "test_query_accepts_read_view_without_mutation_methods",
        "test_query_live_filter_and_overlay_do_not_mutate_graph",
        "test_query_boundary_is_repeatable_and_defaults_include_non_live",
        "test_query_diagnostics_are_generic_and_do_not_mutate_graph",
        "test_query_unsupported_error_has_structured_diagnostic",
        "test_query_json_equality_is_kind_sensitive_and_recursive",
        "test_query_regex_uses_re2_dialect_and_declared_flags",
    ),
}


def concrete_uuid(value: UUID | None) -> UUID:
    assert value is not None
    return value


def test_query_matches_links_data_predicates_and_shapes_returns() -> None:
    graph = InMemoryRtgGraph.empty()
    person = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Person"))
    meeting = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Meeting"))
    profile = graph.put_data_object(
        RtgDataObject(
            uuid=uuid4(),
            type="Profile",
            properties={"name": "Ada Lovelace", "nested": {"role": "engineer"}},
        ),
        (concrete_uuid(person.uuid),),
    )
    link = graph.put_link(
        RtgLink(
            uuid=uuid4(),
            type="attended",
            source_uuid=concrete_uuid(person.uuid),
            target_uuid=concrete_uuid(meeting.uuid),
        )
    )
    query = RtgQuerySpec(
        anchor_buckets=(
            RtgQueryAnchorBucket("person", ("Person",)),
            RtgQueryAnchorBucket("meeting", ("Meeting",)),
        ),
        link_requirements=(
            RtgQueryLinkRequirement("attendance", "person", "meeting", ("attended",)),
        ),
        data_requirements=(
            RtgQueryDataRequirement(
                "profile",
                "person",
                "Profile",
                predicates=(
                    RtgQueryPropertyPredicate(path=("name",), operator="substring", value="ada"),
                ),
            ),
        ),
        return_spec=RtgQueryReturnSpec(
            anchor_buckets=("person",),
            link_requirements=("attendance",),
            data_requirements=("profile",),
            properties=(("profile", ("nested", "role")),),
        ),
    )

    result = SimpleRtgQueryEngine().execute(graph, query)

    assert len(result.bindings) == 1
    assert result.bindings[0].anchors == {"person": person.uuid, "meeting": meeting.uuid}
    assert result.bindings[0].links == {"attendance": link.uuid}
    assert result.bindings[0].data_objects == {"profile": profile.uuid}
    assert result.returns[0].properties == {"profile": {"nested": {"role": "engineer"}}}


def test_query_reports_return_property_diagnostics_for_unresolved_paths() -> None:
    graph = InMemoryRtgGraph.empty()
    person = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Person"))
    graph.put_data_object(
        RtgDataObject(uuid=uuid4(), type="Profile", properties={"name": "Ada"}),
        (concrete_uuid(person.uuid),),
    )
    query = RtgQuerySpec(
        anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),),
        data_requirements=(RtgQueryDataRequirement("profile", "person", "Profile"),),
        return_spec=RtgQueryReturnSpec(properties=(("profile", ("missing",)),)),
    )

    result = SimpleRtgQueryEngine().execute(graph, query)

    assert result.returns[0].properties == {}
    assert result.diagnostics[0].code == "query.return_property_path_unresolved"
    assert result.diagnostics[0].severity == "info"
    assert result.diagnostics[0].diagnostic["path"] == "query_spec.return_spec.properties[0][1]"


def test_query_reports_return_property_diagnostics_for_unbound_requirements() -> None:
    graph = InMemoryRtgGraph.empty()
    graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Person"))
    query = RtgQuerySpec(
        anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),),
        data_requirements=(
            RtgQueryDataRequirement("profile", "person", "Profile", required=False),
        ),
        return_spec=RtgQueryReturnSpec(properties=(("profile", ("name",)),)),
    )

    result = SimpleRtgQueryEngine().execute(graph, query)

    assert result.returns[0].properties == {}
    assert result.diagnostics[0].code == "query.return_property_requirement_unbound"
    assert result.diagnostics[0].severity == "info"
    assert result.diagnostics[0].diagnostic["path"] == "query_spec.return_spec.properties[0]"


def test_query_rejects_unknown_return_property_requirement() -> None:
    graph = InMemoryRtgGraph.empty()
    graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Person"))
    query = RtgQuerySpec(
        anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),),
        return_spec=RtgQueryReturnSpec(properties=(("profile", ("name",)),)),
    )

    with pytest.raises(RtgQuerySpecInvalid) as error:
        SimpleRtgQueryEngine().execute(graph, query)

    assert error.value.diagnostic["code"] == "query.spec.invalid"
    assert error.value.diagnostic["path"] == "query_spec.return_spec.properties"


def test_query_accepts_read_view_without_mutation_methods() -> None:
    graph = InMemoryRtgGraph.empty()
    person = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Person"))

    class ReadOnlyView:
        def get_object(self, object_uuid: UuidInput) -> RtgObject:
            return graph.get_object(object_uuid)

        def list_by_type(self, object_type: str) -> RtgObjectList:
            return graph.list_by_type(object_type)

        def list_anchor_data(self, anchor_uuid: UuidInput) -> RtgDataObjectList:
            return graph.list_anchor_data(anchor_uuid)

        def list_incident_links(
            self, object_uuid: UuidInput, direction: str = "both"
        ) -> RtgLinkList:
            return graph.list_incident_links(object_uuid, direction)

    read_view: RtgGraphReadView = ReadOnlyView()
    result = SimpleRtgQueryEngine().execute(
        read_view,
        RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),)),
    )

    assert result.bindings[0].anchors == {"person": person.uuid}
    assert not hasattr(read_view, "put_anchor")


def test_query_live_filter_and_overlay_do_not_mutate_graph() -> None:
    graph = InMemoryRtgGraph.empty()
    candidate = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Component", system={"live": False}))
    query = RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("component", ("Component",)),))
    engine = SimpleRtgQueryEngine()

    hidden = engine.execute(graph, query, RtgQueryOptions(live_filter="live"))
    projected = engine.execute(
        graph,
        query,
        RtgQueryOptions(
            live_filter="live",
            live_status_overlay={concrete_uuid(candidate.uuid): True},
        ),
    )

    assert hidden.bindings == ()
    assert len(projected.bindings) == 1
    assert graph.get_object(concrete_uuid(candidate.uuid)).system["live"] is False


def test_query_boundary_is_repeatable_and_defaults_include_non_live() -> None:
    graph = InMemoryRtgGraph.empty()
    candidate = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Component", system={"live": False}))
    query = RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("component", ("Component",)),))
    engine = SimpleRtgQueryEngine()

    first = engine.execute(graph, query)
    second = engine.execute(graph, query)

    assert first == second
    assert first.bindings[0].anchors == {"component": candidate.uuid}


def test_query_diagnostics_are_generic_and_do_not_mutate_graph() -> None:
    graph = InMemoryRtgGraph.empty()
    graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Person"))
    before = graph.export_snapshot()
    query = RtgQuerySpec(
        anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),),
        data_requirements=(
            RtgQueryDataRequirement("profile", "person", "Profile", required=False),
        ),
        return_spec=RtgQueryReturnSpec(properties=(("profile", ("name",)),)),
    )

    result = SimpleRtgQueryEngine().execute(graph, query)

    assert graph.export_snapshot() == before
    suggestion = result.diagnostics[0].suggestion
    assert suggestion is not None
    assert "data requirement name" in suggestion
    assert "Person" not in suggestion


def test_query_orders_by_returned_property_path() -> None:
    graph = InMemoryRtgGraph.empty()
    for title, due in (
        ("Later", "2026-07-10"),
        ("Sooner", "2026-07-07"),
        ("No due", None),
    ):
        task = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Task"))
        properties: JsonObject = {"title": title}
        if due is not None:
            properties["due"] = due
        graph.put_data_object(
            RtgDataObject(uuid=uuid4(), type="TaskFacts", properties=properties),
            (concrete_uuid(task.uuid),),
        )
    query = RtgQuerySpec(
        anchor_buckets=(RtgQueryAnchorBucket("task", ("Task",)),),
        data_requirements=(RtgQueryDataRequirement("facts", "task", "TaskFacts"),),
        return_spec=RtgQueryReturnSpec(
            data_requirements=("facts",),
            properties=(("facts", ("title",)), ("facts", ("due",))),
        ),
    )

    result = SimpleRtgQueryEngine().execute(
        graph,
        query,
        RtgQueryOptions(order_by=(RtgQueryOrderBy("facts", ("due",)),)),
    )
    descending = SimpleRtgQueryEngine().execute(
        graph,
        query,
        RtgQueryOptions(order_by=(RtgQueryOrderBy("facts", ("due",), direction="descending"),)),
    )

    assert [_returned_title(row.properties) for row in result.returns] == [
        "Sooner",
        "Later",
        "No due",
    ]
    assert [_returned_title(row.properties) for row in descending.returns] == [
        "Later",
        "Sooner",
        "No due",
    ]


def test_query_orders_arbitrary_precision_numbers_exactly() -> None:
    graph = InMemoryRtgGraph.empty()
    values = (10**40 + 2, 10**40 + 1)
    for index, value in enumerate(values, start=1):
        anchor_uuid = UUID(int=index)
        graph.put_anchor(RtgAnchor(uuid=anchor_uuid, type="Thing"))
        graph.put_data_object(
            RtgDataObject(
                uuid=UUID(int=index + 100),
                type="Facts",
                properties={"value": value},
            ),
            (anchor_uuid,),
        )
    query = RtgQuerySpec(
        anchor_buckets=(RtgQueryAnchorBucket("thing", ("Thing",)),),
        data_requirements=(RtgQueryDataRequirement("facts", "thing", "Facts"),),
        return_spec=RtgQueryReturnSpec(properties=(("facts", ("value",)),)),
    )

    result = SimpleRtgQueryEngine().execute(
        graph,
        query,
        RtgQueryOptions(order_by=(RtgQueryOrderBy("facts", ("value",)),)),
    )

    returned_values = [cast(JsonObject, row.properties["facts"])["value"] for row in result.returns]
    assert returned_values == sorted(values)


def test_query_order_by_must_reference_returned_property() -> None:
    graph = InMemoryRtgGraph.empty()
    task = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Task"))
    graph.put_data_object(
        RtgDataObject(uuid=uuid4(), type="TaskFacts", properties={"title": "A"}),
        (concrete_uuid(task.uuid),),
    )
    query = RtgQuerySpec(
        anchor_buckets=(RtgQueryAnchorBucket("task", ("Task",)),),
        data_requirements=(RtgQueryDataRequirement("facts", "task", "TaskFacts"),),
        return_spec=RtgQueryReturnSpec(properties=(("facts", ("title",)),)),
    )

    try:
        SimpleRtgQueryEngine().execute(
            graph,
            query,
            RtgQueryOptions(order_by=(RtgQueryOrderBy("facts", ("due",)),)),
        )
    except RtgQuerySpecInvalid as error:
        assert "order_by must reference" in str(error)
        assert error.diagnostic["code"] == "query.options.order_by_not_returned"
        assert error.diagnostic["guide_topics"] == [
            "workflow_patterns",
            "query_examples",
            "tool_call_shapes",
        ]
    else:
        raise AssertionError("query should reject non-returned order_by paths")


def test_query_paginates_after_distinct_projection() -> None:
    graph = InMemoryRtgGraph.empty()
    for title in ("Same", "Same", "Different"):
        task = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Task"))
        graph.put_data_object(
            RtgDataObject(uuid=uuid4(), type="TaskFacts", properties={"title": title}),
            (concrete_uuid(task.uuid),),
        )
    query = RtgQuerySpec(
        anchor_buckets=(RtgQueryAnchorBucket("task", ("Task",)),),
        data_requirements=(RtgQueryDataRequirement("facts", "task", "TaskFacts"),),
        return_spec=RtgQueryReturnSpec(properties=(("facts", ("title",)),)),
    )
    result = SimpleRtgQueryEngine().execute(
        graph, query, RtgQueryOptions(distinct_rows=True, limit=1, offset=0)
    )
    assert result.total_row_count == 2
    assert result.returned_row_count == 1
    assert result.next_offset == 1
    assert result.returns[0].row_index == 0


def test_query_count_aggregation_groups_and_counts_distinct_bindings() -> None:
    graph = InMemoryRtgGraph.empty()
    for status in ("next", "next", "waiting"):
        task = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Task"))
        graph.put_data_object(
            RtgDataObject(uuid=uuid4(), type="TaskFacts", properties={"status": status}),
            (concrete_uuid(task.uuid),),
        )
    query = RtgQuerySpec(
        anchor_buckets=(RtgQueryAnchorBucket("task", ("Task",)),),
        data_requirements=(RtgQueryDataRequirement("facts", "task", "TaskFacts"),),
        return_spec=RtgQueryReturnSpec(
            properties=(("facts", ("status",)),),
            group_by=(("facts", ("status",)),),
            aggregations=(RtgQueryAggregation("task_count", "count", "task"),),
        ),
    )
    result = SimpleRtgQueryEngine().execute(graph, query)
    assert result.aggregations == (
        {"row_index": 0, "group_by": {"facts": {"status": "next"}}, "task_count": 2},
        {"row_index": 1, "group_by": {"facts": {"status": "waiting"}}, "task_count": 1},
    )
    assert result.total_row_count == 2
    assert result.bindings == ()
    assert result.returns == ()


def test_query_paginates_aggregate_rows() -> None:
    graph = InMemoryRtgGraph.empty()
    for index, status in enumerate(("next", "waiting"), start=1):
        anchor_uuid = UUID(int=index)
        graph.put_anchor(RtgAnchor(uuid=anchor_uuid, type="Task"))
        graph.put_data_object(
            RtgDataObject(
                uuid=UUID(int=index + 100),
                type="TaskFacts",
                properties={"status": status},
            ),
            (anchor_uuid,),
        )
    query = RtgQuerySpec(
        anchor_buckets=(RtgQueryAnchorBucket("task", ("Task",)),),
        data_requirements=(RtgQueryDataRequirement("facts", "task", "TaskFacts"),),
        return_spec=RtgQueryReturnSpec(
            properties=(("facts", ("status",)),),
            group_by=(("facts", ("status",)),),
            aggregations=(RtgQueryAggregation("task_count", "count", "task"),),
        ),
    )

    result = SimpleRtgQueryEngine().execute(
        graph, query, RtgQueryOptions(limit=1, offset=0)
    )

    assert result.total_row_count == 2
    assert result.returned_row_count == 1
    assert result.next_offset == 1
    assert result.aggregations[0]["row_index"] == 0


def test_query_rejects_ambiguous_binding_names_and_invalid_pagination_options() -> None:
    graph = InMemoryRtgGraph.empty()
    anchor = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Thing"))
    graph.put_data_object(
        RtgDataObject(uuid=uuid4(), type="Facts", properties={}),
        (concrete_uuid(anchor.uuid),),
    )
    ambiguous = RtgQuerySpec(
        anchor_buckets=(RtgQueryAnchorBucket("item", ("Thing",)),),
        data_requirements=(RtgQueryDataRequirement("item", "item", "Facts"),),
    )
    with pytest.raises(RtgQuerySpecInvalid, match="globally unique"):
        SimpleRtgQueryEngine().execute(graph, ambiguous)

    query = RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("item", ("Thing",)),))
    for options in (
        RtgQueryOptions(limit=True),
        RtgQueryOptions(offset=False),
        RtgQueryOptions(limit=1.5),  # type: ignore[arg-type]
    ):
        with pytest.raises(RtgQuerySpecInvalid):
            SimpleRtgQueryEngine().execute(graph, query, options)

    aggregate = RtgQuerySpec(
        anchor_buckets=(RtgQueryAnchorBucket("item", ("Thing",)),),
        return_spec=RtgQueryReturnSpec(
            aggregations=(RtgQueryAggregation("item_count", "count", "item"),)
        ),
    )
    with pytest.raises(RtgQuerySpecInvalid, match="distinct_rows"):
        SimpleRtgQueryEngine().execute(graph, aggregate, RtgQueryOptions(distinct_rows=True))


def test_optional_link_requirement_preserves_unlinked_source_rows() -> None:
    graph = InMemoryRtgGraph.empty()
    linked = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Project"))
    unlinked = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Project"))
    area = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Area"))
    graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Area"))
    graph.put_link(
        RtgLink(
            uuid=uuid4(),
            type="belongs_to",
            source_uuid=concrete_uuid(linked.uuid),
            target_uuid=concrete_uuid(area.uuid),
        )
    )
    query = RtgQuerySpec(
        anchor_buckets=(
            RtgQueryAnchorBucket("project", ("Project",)),
            RtgQueryAnchorBucket("area", ("Area",)),
        ),
        link_requirements=(
            RtgQueryLinkRequirement(
                "membership", "project", "area", ("belongs_to",), required=False
            ),
        ),
    )
    result = SimpleRtgQueryEngine().execute(graph, query)
    assert len(result.bindings) == 2
    rows = {row.anchors["project"]: row for row in result.bindings}
    assert rows[concrete_uuid(linked.uuid)].links["membership"]
    assert "area" not in rows[concrete_uuid(unlinked.uuid)].anchors


def test_chained_optional_links_preserve_rows_when_intermediate_source_is_unbound() -> None:
    graph = InMemoryRtgGraph.empty()
    project = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Project"))
    graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Area"))
    graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Goal"))
    query = RtgQuerySpec(
        anchor_buckets=(
            RtgQueryAnchorBucket("project", ("Project",)),
            RtgQueryAnchorBucket("area", ("Area",)),
            RtgQueryAnchorBucket("goal", ("Goal",)),
        ),
        link_requirements=(
            RtgQueryLinkRequirement(
                "membership", "project", "area", ("belongs_to",), required=False
            ),
            RtgQueryLinkRequirement("alignment", "area", "goal", ("supports",), required=False),
        ),
    )

    result = SimpleRtgQueryEngine().execute(graph, query)

    assert len(result.bindings) == 1
    assert result.bindings[0].anchors == {"project": concrete_uuid(project.uuid)}
    assert result.bindings[0].links == {}


def test_optional_link_cycle_with_no_source_context_returns_no_rows() -> None:
    graph = InMemoryRtgGraph.empty()
    query = RtgQuerySpec(
        anchor_buckets=(
            RtgQueryAnchorBucket("left", ("MissingLeft",)),
            RtgQueryAnchorBucket("right", ("MissingRight",)),
        ),
        link_requirements=(
            RtgQueryLinkRequirement("forward", "left", "right", ("related",), required=False),
            RtgQueryLinkRequirement("reverse", "right", "left", ("related",), required=False),
        ),
    )

    result = SimpleRtgQueryEngine().execute(graph, query)

    assert result.bindings == ()
    assert result.returns == ()


def test_query_grouping_preserves_distinct_large_json_integers() -> None:
    graph = InMemoryRtgGraph.empty()
    values = (10**40 + 1, 10**40 + 2)
    for value in values:
        thing = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Thing"))
        graph.put_data_object(
            RtgDataObject(uuid=uuid4(), type="Facts", properties={"value": value}),
            (concrete_uuid(thing.uuid),),
        )
    query = RtgQuerySpec(
        anchor_buckets=(RtgQueryAnchorBucket("thing", ("Thing",)),),
        data_requirements=(RtgQueryDataRequirement("facts", "thing", "Facts"),),
        return_spec=RtgQueryReturnSpec(
            properties=(("facts", ("value",)),),
            group_by=(("facts", ("value",)),),
            aggregations=(RtgQueryAggregation("thing_count", "count", "thing"),),
        ),
    )

    result = SimpleRtgQueryEngine().execute(graph, query)

    grouped_values: list[int] = []
    counts: list[int] = []
    for row in result.aggregations:
        group_by = cast(JsonObject, row["group_by"])
        facts = cast(JsonObject, group_by["facts"])
        grouped_values.append(cast(int, facts["value"]))
        counts.append(cast(int, row["thing_count"]))
    assert set(grouped_values) == set(values)
    assert set(counts) == {1}


@pytest.mark.parametrize("name", ["row_index", "group_by"])
def test_query_rejects_reserved_aggregation_names(name: str) -> None:
    graph = InMemoryRtgGraph.empty()
    graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Thing"))
    query = RtgQuerySpec(
        anchor_buckets=(RtgQueryAnchorBucket("thing", ("Thing",)),),
        return_spec=RtgQueryReturnSpec(aggregations=(RtgQueryAggregation(name, "count", "thing"),)),
    )

    with pytest.raises(RtgQuerySpecInvalid) as error:
        SimpleRtgQueryEngine().execute(graph, query)

    assert error.value.diagnostic["code"] == "query.aggregation.reserved_name"


def test_query_invalid_operator_has_structured_diagnostic() -> None:
    graph = InMemoryRtgGraph.empty()
    query = RtgQuerySpec(
        anchor_buckets=(RtgQueryAnchorBucket("task", ("Task",)),),
        data_requirements=(
            RtgQueryDataRequirement(
                "facts",
                "task",
                "TaskFacts",
                predicates=(
                    RtgQueryPropertyPredicate(
                        ("title",),
                        "sounds_like",  # type: ignore[arg-type]
                        value="A",
                    ),
                ),
            ),
        ),
    )

    try:
        SimpleRtgQueryEngine().execute(graph, query)
    except RtgQuerySpecInvalid as error:
        assert "unsupported predicate operator" in str(error)
        assert error.diagnostic["code"] == "query.predicate.unsupported_operator"
        accepted_fields = error.diagnostic["accepted_fields"]
        assert isinstance(accepted_fields, list)
        assert "equals" in accepted_fields
    else:
        raise AssertionError("query should reject unsupported predicate operator")


def test_query_json_equality_is_kind_sensitive_and_recursive() -> None:
    graph = InMemoryRtgGraph.empty()
    anchor = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Thing"))
    graph.put_data_object(
        RtgDataObject(
            uuid=uuid4(),
            type="Facts",
            properties={
                "boolean": True,
                "number": 1,
                "array": [True, {"number": 1}],
                "object": {"a": True, "b": 1},
            },
        ),
        (concrete_uuid(anchor.uuid),),
    )

    def matches(predicate: RtgQueryPropertyPredicate) -> bool:
        query = RtgQuerySpec(
            anchor_buckets=(RtgQueryAnchorBucket("thing", ("Thing",)),),
            data_requirements=(
                RtgQueryDataRequirement("facts", "thing", "Facts", predicates=(predicate,)),
            ),
        )
        return bool(SimpleRtgQueryEngine().execute(graph, query).bindings)

    assert not matches(RtgQueryPropertyPredicate(("boolean",), "equals", value=1))
    assert matches(RtgQueryPropertyPredicate(("number",), "equals", value=1.0))
    assert not matches(RtgQueryPropertyPredicate(("array",), "contains", value=1))
    assert matches(RtgQueryPropertyPredicate(("array",), "equals", value=[True, {"number": 1.0}]))
    assert not matches(RtgQueryPropertyPredicate(("object",), "equals", value={"a": 1, "b": 1}))
    assert not matches(RtgQueryPropertyPredicate(("number",), "lt", value="2"))
    assert not matches(RtgQueryPropertyPredicate(("number",), "substring", value="1"))


def test_query_predicate_operator_table_and_case_sensitivity() -> None:
    graph = InMemoryRtgGraph.empty()
    anchor = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Thing"))
    graph.put_data_object(
        RtgDataObject(
            uuid=uuid4(),
            type="Facts",
            properties={"name": "Ada", "rank": 2, "tags": ["math"]},
        ),
        (concrete_uuid(anchor.uuid),),
    )

    def matches(predicate: RtgQueryPropertyPredicate) -> bool:
        query = RtgQuerySpec(
            anchor_buckets=(RtgQueryAnchorBucket("thing", ("Thing",)),),
            data_requirements=(
                RtgQueryDataRequirement("facts", "thing", "Facts", predicates=(predicate,)),
            ),
        )
        return bool(SimpleRtgQueryEngine().execute(graph, query).bindings)

    assert matches(RtgQueryPropertyPredicate(("name",), "exists"))
    assert not matches(RtgQueryPropertyPredicate(("missing",), "exists"))
    assert matches(RtgQueryPropertyPredicate(("name",), "not_equals", value="Grace"))
    assert matches(RtgQueryPropertyPredicate(("rank",), "lt", value=3))
    assert matches(RtgQueryPropertyPredicate(("rank",), "lte", value=2))
    assert matches(RtgQueryPropertyPredicate(("rank",), "gt", value=1))
    assert matches(RtgQueryPropertyPredicate(("rank",), "gte", value=2))
    assert matches(RtgQueryPropertyPredicate(("rank",), "in", values=(1, 2, 3)))
    assert matches(RtgQueryPropertyPredicate(("tags",), "contains", value="math"))
    assert matches(RtgQueryPropertyPredicate(("name",), "substring", value="ada"))
    assert not matches(
        RtgQueryPropertyPredicate(
            ("name",), "substring", value="ada", case_sensitive=True
        )
    )


def test_query_rejects_unknown_diagnostic_guidance_with_structured_diagnostic() -> None:
    graph = InMemoryRtgGraph.empty()
    query = RtgQuerySpec(
        anchor_buckets=(RtgQueryAnchorBucket("thing", ("Thing",)),),
        diagnostic_options=RtgQueryDiagnosticOptions(
            unknown_term_guidance="invent_schema"  # type: ignore[arg-type]
        ),
    )

    with pytest.raises(RtgQuerySpecInvalid) as error:
        SimpleRtgQueryEngine().execute(graph, query)

    assert error.value.diagnostic["code"] == "query.spec.invalid"
    assert error.value.diagnostic["path"] == ("query_spec.diagnostic_options.unknown_term_guidance")


def test_query_unsupported_error_has_structured_diagnostic() -> None:
    error = RtgQueryUnsupported("behavior is not implemented")

    assert error.diagnostic["code"] == "query.unsupported"
    assert error.diagnostic["problem"] == "behavior is not implemented"
    assert error.diagnostic["safe_to_retry"] is True
    assert error.diagnostic["mutation_state"] == "not_mutated"


def test_query_regex_uses_re2_dialect_and_declared_flags() -> None:
    graph = InMemoryRtgGraph.empty()
    anchor = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Thing"))
    graph.put_data_object(
        RtgDataObject(uuid=uuid4(), type="Facts", properties={"text": "First\nAda"}),
        (concrete_uuid(anchor.uuid),),
    )

    def execute(pattern: str, flags: tuple[str, ...] = ()) -> bool:
        query = RtgQuerySpec(
            anchor_buckets=(RtgQueryAnchorBucket("thing", ("Thing",)),),
            data_requirements=(
                RtgQueryDataRequirement(
                    "facts",
                    "thing",
                    "Facts",
                    predicates=(
                        RtgQueryPropertyPredicate(
                            ("text",), "regex", value=pattern, regex_flags=flags
                        ),
                    ),
                ),
            ),
        )
        return bool(SimpleRtgQueryEngine().execute(graph, query).bindings)

    assert execute("^ada$", ("case_insensitive", "multiline"))
    for unsupported in (r"(Ada)\1", r"(?P<name>Ada)(?P=name)", r"(?=Ada)"):
        try:
            execute(unsupported)
        except RtgQuerySpecInvalid as error:
            assert "unsupported regex pattern" in str(error)
        else:
            raise AssertionError(f"query should reject unsupported RE2 pattern {unsupported!r}")


def _returned_title(properties: JsonObject) -> object:
    facts = cast(JsonObject, properties["facts"])
    return facts["title"]
