from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

from components.rtg.graph import (
    InMemoryRtgGraph,
    JsonObject,
    RtgAnchor,
    RtgDataObject,
    RtgLink,
)
from components.rtg.query import (
    RtgQueryAnchorBucket,
    RtgQueryDataRequirement,
    RtgQueryLinkRequirement,
    RtgQueryOptions,
    RtgQueryOrderBy,
    RtgQueryPropertyPredicate,
    RtgQueryReturnSpec,
    RtgQuerySpec,
    RtgQuerySpecInvalid,
    SimpleRtgQueryEngine,
)


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
    assert (
        result.diagnostics[0].diagnostic["path"] == "query_spec.return_spec.properties[0][1]"
    )


def test_query_reports_return_property_diagnostics_for_unbound_requirements() -> None:
    graph = InMemoryRtgGraph.empty()
    graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Person"))
    query = RtgQuerySpec(
        anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),),
        return_spec=RtgQueryReturnSpec(properties=(("profile", ("name",)),)),
    )

    result = SimpleRtgQueryEngine().execute(graph, query)

    assert result.returns[0].properties == {}
    assert result.diagnostics[0].code == "query.return_property_requirement_unbound"
    assert result.diagnostics[0].diagnostic["path"] == "query_spec.return_spec.properties[0]"


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
                    RtgQueryPropertyPredicate(("title",), "sounds_like", value="A"),
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
    assert matches(
        RtgQueryPropertyPredicate(
            ("array",), "equals", value=[True, {"number": 1.0}]
        )
    )
    assert not matches(
        RtgQueryPropertyPredicate(("object",), "equals", value={"a": 1, "b": 1})
    )


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
