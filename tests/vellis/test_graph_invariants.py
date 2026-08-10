"""Evidence for ``VellisVerification::graphInvariants`` against a stored graph.

Assessment describes a subject; it never changes canonical state. Every case below
either accepts a conforming graph or names the exact invariant a finding must catch.
"""

from __future__ import annotations

import pytest

from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    DirectAssociationEnd,
    DirectAssociationMultiplicityConstraint,
    EndpointConstraint,
    GraphDefinitionSet,
    LinkEnd,
    LinkMultiplicityConstraint,
    LinkTypeDefinition,
    PropertyConstraint,
    StringPattern,
    ValueRange,
    ValueShape,
)
from vellis.graph import Anchor, AssociatedDataObject, Graph, Link, MetadataError, SystemMetadata
from vellis.json_value import JsonKind, JsonValue, normalize
from vellis.validation import assess_graph_conformance

PERSON = AnchorTypeDefinition(type_key="person", description="A person the owner knows.")
PROJECT = AnchorTypeDefinition(type_key="project", description="A piece of work.")

NOTE = AssociatedDataTypeDefinition(
    type_key="note",
    permitted_anchor_type_keys=("person",),
    property_constraints=(
        PropertyConstraint(
            property_name="title",
            required=True,
            json_kind=JsonKind.STRING,
            description="What the note is about.",
            value_shape=ValueShape(minimum_size=1, maximum_size=80),
        ),
        PropertyConstraint(
            property_name="rating",
            required=False,
            json_kind=JsonKind.NUMBER,
            description="An optional 1-5 rating.",
            value_range=ValueRange(lower_bound=normalize(1), upper_bound=normalize(5)),
        ),
        PropertyConstraint(
            property_name="year",
            required=False,
            json_kind=JsonKind.STRING,
            description="An optional four-digit year.",
            pattern=StringPattern(expression="[0-9]{4}"),
        ),
    ),
    description="A note about a person.",
)

WORKS_ON = LinkTypeDefinition(
    type_key="worksOn",
    endpoint_constraint=EndpointConstraint(
        permitted_source_type_keys=("person",),
        permitted_target_type_keys=("project",),
        description="Who works on what.",
    ),
    description="A working relationship.",
)

DEFINITIONS = GraphDefinitionSet(
    anchor_types=(PERSON, PROJECT),
    associated_data_types=(NOTE,),
    link_types=(WORKS_ON,),
)

ADA = Anchor(uuid="a-1", type_key="person", display_name="Ada")
ORBIT = Anchor(uuid="a-2", type_key="project", display_name="Orbit")


def _note(
    uuid: str = "d-1", properties: dict[str, JsonValue] | None = None
) -> AssociatedDataObject:
    values: dict[str, JsonValue] = {"title": normalize("First meeting")}
    values.update(properties or {})
    return AssociatedDataObject(
        uuid=uuid, type_key="note", anchor_uuids=("a-1",), properties=values
    )


def _summaries(graph: Graph, definitions: GraphDefinitionSet = DEFINITIONS) -> list[str]:
    return [finding.summary for finding in assess_graph_conformance(graph, definitions)]


def test_a_conforming_graph_produces_no_findings() -> None:
    graph = Graph(
        anchors=(ADA, ORBIT),
        associated_data=(_note(properties={"rating": normalize(4), "year": normalize("2026")}),),
        links=(Link(uuid="l-1", type_key="worksOn", source_uuid="a-1", target_uuid="a-2"),),
    )
    assert _summaries(graph) == []


def test_identity_is_globally_unique_across_object_kinds() -> None:
    """Excludes making UUIDs unique only within each collection."""
    clash = Link(uuid="a-1", type_key="worksOn", source_uuid="a-1", target_uuid="a-2")
    summaries = _summaries(Graph(anchors=(ADA, ORBIT), links=(clash,)))
    assert any("identifies more than one graph object" in each for each in summaries)


def test_every_anchor_needs_a_non_empty_display_name() -> None:
    blank = Anchor(uuid="a-3", type_key="person", display_name="")
    assert any("empty display name" in each for each in _summaries(Graph(anchors=(blank,))))


def test_unknown_type_key_does_not_resolve() -> None:
    unknown = Anchor(uuid="a-3", type_key="ghost", display_name="Nobody")
    summaries = _summaries(Graph(anchors=(unknown,)))
    assert any("resolves to no active anchor type definition" in each for each in summaries)


def test_a_type_key_never_changes_an_objects_kind() -> None:
    """Excludes resolving a type key in one shared table without checking object kind."""
    confused = Anchor(uuid="a-3", type_key="worksOn", display_name="Not a link")
    summaries = _summaries(Graph(anchors=(confused,)))
    assert any("active as a link type" in each for each in summaries)


def test_associated_data_must_be_grounded_by_at_least_one_anchor() -> None:
    orphan = AssociatedDataObject(
        uuid="d-1", type_key="note", anchor_uuids=(), properties={"title": "x"}
    )
    summaries = _summaries(Graph(anchors=(ADA,), associated_data=(orphan,)))
    assert any("grounded by no anchor" in each for each in summaries)


def test_direct_associations_must_resolve_inside_the_same_graph() -> None:
    dangling = AssociatedDataObject(
        uuid="d-1", type_key="note", anchor_uuids=("a-9",), properties={"title": "x"}
    )
    summaries = _summaries(Graph(anchors=(ADA,), associated_data=(dangling,)))
    assert any("no anchor owned by this graph" in each for each in summaries)


def test_grounding_anchor_type_must_be_permitted() -> None:
    wrong = AssociatedDataObject(
        uuid="d-1", type_key="note", anchor_uuids=("a-2",), properties={"title": "x"}
    )
    summaries = _summaries(Graph(anchors=(ADA, ORBIT), associated_data=(wrong,)))
    assert any("which that type does not permit" in each for each in summaries)


def test_undeclared_property_is_invalid() -> None:
    graph = Graph(
        anchors=(ADA,), associated_data=(_note(properties={"colour": normalize("blue")}),)
    )
    assert any("does not declare" in each for each in _summaries(graph))


def test_missing_required_property_is_invalid_but_absent_optional_is_fine() -> None:
    missing = AssociatedDataObject(uuid="d-1", type_key="note", anchor_uuids=("a-1",))
    assert any("omits required property" in each for each in _summaries(Graph((ADA,), (missing,))))
    assert _summaries(Graph(anchors=(ADA,), associated_data=(_note(),))) == []


def test_present_null_is_not_an_absent_property() -> None:
    """Excludes treating a present JSON null as though the property were omitted."""
    graph = Graph(anchors=(ADA,), associated_data=(_note(properties={"rating": None}),))
    assert any("declared numberValue" in each for each in _summaries(graph))


@pytest.mark.parametrize(
    ("properties", "expected"),
    [
        ({"title": normalize("")}, "below its minimum"),
        ({"title": normalize("x" * 81)}, "above its maximum"),
        ({"rating": normalize(0)}, "below its inclusive lower bound"),
        ({"rating": normalize(6)}, "above its inclusive upper bound"),
        ({"year": normalize("2026-08")}, "does not match its whole-string pattern"),
        ({"rating": normalize("4")}, "declared numberValue"),
    ],
)
def test_stored_values_are_validated_against_their_declared_rule(
    properties: dict[str, JsonValue], expected: str
) -> None:
    graph = Graph(anchors=(ADA,), associated_data=(_note(properties=properties),))
    assert any(expected in each for each in _summaries(graph))


def test_inclusive_numeric_bounds_accept_their_endpoints() -> None:
    """Excludes reading the modeled bounds as exclusive."""
    for value in (1, 5):
        graph = Graph(
            anchors=(ADA,), associated_data=(_note(properties={"rating": normalize(value)}),)
        )
        assert _summaries(graph) == []


def test_a_link_is_never_an_endpoint() -> None:
    first = Link(uuid="l-1", type_key="worksOn", source_uuid="a-1", target_uuid="a-2")
    second = Link(uuid="l-2", type_key="worksOn", source_uuid="l-1", target_uuid="a-2")
    summaries = _summaries(Graph(anchors=(ADA, ORBIT), links=(first, second)))
    assert any("a link, which is never an endpoint" in each for each in summaries)


def test_link_endpoint_types_must_be_permitted() -> None:
    """Excludes accepting a reversed link because both endpoint types appear somewhere."""
    reversed_link = Link(uuid="l-1", type_key="worksOn", source_uuid="a-2", target_uuid="a-1")
    summaries = _summaries(Graph(anchors=(ADA, ORBIT), links=(reversed_link,)))
    assert any("its endpoint constraint does not permit" in each for each in summaries)


def _with_link_multiplicity(upper: int | None, lower: int = 0) -> GraphDefinitionSet:
    return GraphDefinitionSet(
        anchor_types=(PERSON, PROJECT),
        associated_data_types=(NOTE,),
        link_types=(WORKS_ON,),
        relationship_constraints=(
            LinkMultiplicityConstraint(
                link_type_key="worksOn",
                constrained_end=LinkEnd.SOURCE,
                constrained_endpoint_type_keys=("person",),
                opposite_endpoint_type_keys=("project",),
                lower_bound=lower,
                upper_bound=upper,
                description="How many projects one person may work on.",
            ),
        ),
    )


def test_link_multiplicity_counts_the_constrained_end() -> None:
    second_project = Anchor(uuid="a-3", type_key="project", display_name="Beacon")
    graph = Graph(
        anchors=(ADA, ORBIT, second_project),
        links=(
            Link(uuid="l-1", type_key="worksOn", source_uuid="a-1", target_uuid="a-2"),
            Link(uuid="l-2", type_key="worksOn", source_uuid="a-1", target_uuid="a-3"),
        ),
    )
    assert _summaries(graph, _with_link_multiplicity(upper=2)) == []
    assert any(
        "outside 0..1" in each for each in _summaries(graph, _with_link_multiplicity(upper=1))
    )


def test_distinct_overlapping_multiplicity_rules_all_apply() -> None:
    """Excludes keeping only the last matching rule for an object."""
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON, PROJECT),
        associated_data_types=(NOTE,),
        link_types=(WORKS_ON,),
        relationship_constraints=(
            LinkMultiplicityConstraint(
                link_type_key="worksOn",
                constrained_end=LinkEnd.SOURCE,
                constrained_endpoint_type_keys=("person",),
                opposite_endpoint_type_keys=("project",),
                lower_bound=0,
                upper_bound=5,
                description="A permissive rule.",
            ),
            LinkMultiplicityConstraint(
                link_type_key="worksOn",
                constrained_end=LinkEnd.SOURCE,
                constrained_endpoint_type_keys=("person",),
                opposite_endpoint_type_keys=("project", "person"),
                lower_bound=2,
                upper_bound=None,
                description="A stricter rule over a wider opposite population.",
            ),
        ),
    )
    graph = Graph(
        anchors=(ADA, ORBIT),
        links=(Link(uuid="l-1", type_key="worksOn", source_uuid="a-1", target_uuid="a-2"),),
    )
    assert any("outside 2..*" in each for each in _summaries(graph, definitions))


def _with_direct_association(end: DirectAssociationEnd, upper: int | None) -> GraphDefinitionSet:
    return GraphDefinitionSet(
        anchor_types=(PERSON, PROJECT),
        associated_data_types=(NOTE,),
        link_types=(WORKS_ON,),
        relationship_constraints=(
            DirectAssociationMultiplicityConstraint(
                constrained_end=end,
                anchor_type_keys=("person",),
                associated_data_type_keys=("note",),
                lower_bound=0,
                upper_bound=upper,
                description="How many notes one person may carry.",
            ),
        ),
    )


def test_direct_association_multiplicity_counts_each_end() -> None:
    graph = Graph(anchors=(ADA,), associated_data=(_note("d-1"), _note("d-2")))
    at_anchor = _summaries(graph, _with_direct_association(DirectAssociationEnd.ANCHOR, upper=1))
    assert any("outside 0..1" in each for each in at_anchor)
    at_data = _summaries(
        graph, _with_direct_association(DirectAssociationEnd.ASSOCIATED_DATA, upper=1)
    )
    assert at_data == []


def test_system_metadata_live_must_be_boolean() -> None:
    """Excludes accepting a truthy string or number where the model requires a Boolean."""
    with pytest.raises(MetadataError):
        SystemMetadata(members={"live": normalize("yes")})
    assert SystemMetadata().live is True
    assert SystemMetadata(members={"live": False}).live is False


def test_assessment_leaves_the_graph_unchanged() -> None:
    graph = Graph(anchors=(ADA,), associated_data=(_note(),))
    before = (graph.anchors, graph.associated_data, graph.links)
    assess_graph_conformance(graph, DEFINITIONS)
    assert (graph.anchors, graph.associated_data, graph.links) == before


def test_a_repeated_direct_association_counts_once_and_is_reported() -> None:
    """Excludes counting one anchor twice toward a direct-association multiplicity bound."""
    repeated = AssociatedDataObject(
        uuid="d-1",
        type_key="note",
        anchor_uuids=("a-1", "a-1"),
        properties={"title": normalize("Repeated")},
    )
    graph = Graph(anchors=(ADA,), associated_data=(repeated,))
    summaries = _summaries(
        graph, _with_direct_association(DirectAssociationEnd.ASSOCIATED_DATA, upper=1)
    )
    assert not any("outside 0..1" in each for each in summaries)
    assert any("more than once" in each for each in summaries)


def test_object_sizes_are_constrained_by_a_value_shape() -> None:
    """Excludes a size rule that silently ignores object-valued properties."""
    from vellis.json_value import value_size

    assert value_size(normalize({"a": 1, "b": 2})) == 2
    assert value_size(normalize([1, 2, 3])) == 3
    assert value_size(normalize(4)) is None


def test_an_unresolved_type_key_reports_one_root_cause() -> None:
    """Pins the documented policy: dependent checks are skipped, not cascaded."""
    unknown = AssociatedDataObject(
        uuid="d-1", type_key="ghost", anchor_uuids=("a-9",), properties={"nope": normalize(1)}
    )
    summaries = _summaries(Graph(anchors=(ADA,), associated_data=(unknown,)))
    assert len(summaries) == 1
    assert "resolves to no active associatedData type definition" in summaries[0]


def test_link_multiplicity_ignores_objects_outside_its_participating_types() -> None:
    """Excludes applying a person/project rule to unrelated objects or opposite types."""
    other_person = Anchor(uuid="a-4", type_key="person", display_name="Grace")
    graph = Graph(
        anchors=(ADA, ORBIT, other_person),
        links=(
            Link(uuid="l-1", type_key="worksOn", source_uuid="a-1", target_uuid="a-2"),
            # A person-to-person link: outside the rule's opposite type set.
            Link(uuid="l-2", type_key="worksOn", source_uuid="a-1", target_uuid="a-4"),
        ),
    )
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON, PROJECT),
        associated_data_types=(NOTE,),
        link_types=(
            LinkTypeDefinition(
                type_key="worksOn",
                endpoint_constraint=EndpointConstraint(
                    permitted_source_type_keys=("person",),
                    permitted_target_type_keys=("project", "person"),
                    description="Who works with what.",
                ),
                description="A working relationship.",
            ),
        ),
        relationship_constraints=(
            LinkMultiplicityConstraint(
                link_type_key="worksOn",
                constrained_end=LinkEnd.SOURCE,
                constrained_endpoint_type_keys=("person",),
                opposite_endpoint_type_keys=("project",),
                lower_bound=0,
                upper_bound=1,
                description="At most one project per person.",
            ),
        ),
    )
    # Only the person-to-project link counts, so the bound of one is satisfied.
    assert _summaries(graph, definitions) == []


def test_direct_association_multiplicity_ignores_unrelated_data_types() -> None:
    """Excludes counting associated data of a type the rule does not name."""
    other_type = AssociatedDataTypeDefinition(
        type_key="task",
        permitted_anchor_type_keys=("person",),
        description="A task for a person.",
    )
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON, PROJECT),
        associated_data_types=(NOTE, other_type),
        link_types=(WORKS_ON,),
        relationship_constraints=(
            DirectAssociationMultiplicityConstraint(
                constrained_end=DirectAssociationEnd.ANCHOR,
                anchor_type_keys=("person",),
                associated_data_type_keys=("note",),
                lower_bound=0,
                upper_bound=1,
                description="At most one note per person.",
            ),
        ),
    )
    task = AssociatedDataObject(uuid="d-2", type_key="task", anchor_uuids=("a-1",))
    graph = Graph(anchors=(ADA,), associated_data=(_note("d-1"), task))
    assert _summaries(graph, definitions) == []


def test_a_value_whose_pattern_is_invalid_is_reported_not_silently_accepted() -> None:
    """Excludes treating an unvalidatable rule as satisfied."""
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON,),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="note",
                permitted_anchor_type_keys=("person",),
                property_constraints=(
                    PropertyConstraint(
                        property_name="title",
                        required=True,
                        json_kind=JsonKind.STRING,
                        description="A title.",
                        pattern=StringPattern(expression="(?=broken)"),
                    ),
                ),
                description="A note.",
            ),
        ),
    )
    graph = Graph(anchors=(ADA,), associated_data=(_note("d-1"),))
    assert any("cannot be validated" in each for each in _summaries(graph, definitions))


CITES = LinkTypeDefinition(
    type_key="cites",
    endpoint_constraint=EndpointConstraint(
        permitted_source_type_keys=("note",),
        permitted_target_type_keys=("note",),
        description="One note citing another.",
    ),
    description="A citation between notes.",
)

WITH_DATA_LINKS = GraphDefinitionSet(
    anchor_types=(PERSON, PROJECT),
    associated_data_types=(NOTE,),
    link_types=(WORKS_ON, CITES),
)


def test_associated_data_may_be_a_link_endpoint() -> None:
    """The model makes a link endpoint an anchor *or* associated data.

    Excludes resolving endpoints against anchors alone, which would report every
    data-to-data link as dangling.
    """
    graph = Graph(
        anchors=(ADA,),
        associated_data=(_note("d-1"), _note("d-2")),
        links=(Link(uuid="l-1", type_key="cites", source_uuid="d-1", target_uuid="d-2"),),
    )
    assert _summaries(graph, WITH_DATA_LINKS) == []


def test_an_associated_data_endpoint_type_must_still_be_permitted() -> None:
    graph = Graph(
        anchors=(ADA,),
        associated_data=(_note("d-1"),),
        links=(Link(uuid="l-1", type_key="cites", source_uuid="d-1", target_uuid="a-1"),),
    )
    summaries = _summaries(graph, WITH_DATA_LINKS)
    assert any("its endpoint constraint does not permit" in each for each in summaries)


def test_a_dangling_associated_data_endpoint_is_reported() -> None:
    graph = Graph(
        anchors=(ADA,),
        associated_data=(_note("d-1"),),
        links=(Link(uuid="l-1", type_key="cites", source_uuid="d-1", target_uuid="d-9"),),
    )
    summaries = _summaries(graph, WITH_DATA_LINKS)
    assert any("no anchor or associated data owned by this graph" in each for each in summaries)


def test_link_multiplicity_counts_associated_data_endpoints() -> None:
    """Excludes a multiplicity walk that visits anchors only."""
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON, PROJECT),
        associated_data_types=(NOTE,),
        link_types=(WORKS_ON, CITES),
        relationship_constraints=(
            LinkMultiplicityConstraint(
                link_type_key="cites",
                constrained_end=LinkEnd.SOURCE,
                constrained_endpoint_type_keys=("note",),
                opposite_endpoint_type_keys=("note",),
                lower_bound=0,
                upper_bound=1,
                description="A note may cite at most one other note.",
            ),
        ),
    )
    graph = Graph(
        anchors=(ADA,),
        associated_data=(_note("d-1"), _note("d-2"), _note("d-3")),
        links=(
            Link(uuid="l-1", type_key="cites", source_uuid="d-1", target_uuid="d-2"),
            Link(uuid="l-2", type_key="cites", source_uuid="d-1", target_uuid="d-3"),
        ),
    )
    assert any("outside 0..1" in each for each in _summaries(graph, definitions))


def test_a_data_to_data_link_survives_the_round_trip() -> None:
    """Endpoint kind must not be lost by the stored form either."""
    from vellis.graph import graph_equal
    from vellis.serialization import decode_graph, decode_text, encode_graph, encode_text

    graph = Graph(
        anchors=(ADA,),
        associated_data=(_note("d-1"), _note("d-2")),
        links=(Link(uuid="l-1", type_key="cites", source_uuid="d-1", target_uuid="d-2"),),
    )
    restored = decode_graph(decode_text(encode_text(encode_graph(graph))))
    assert graph_equal(restored, graph)
    assert _summaries(restored, WITH_DATA_LINKS) == []


def test_a_multiplicity_rule_says_nothing_about_objects_outside_its_scope() -> None:
    """Excludes reporting a conforming graph as invalid.

    Every scoping filter in the multiplicity walk is exercised here at once: the graph
    holds objects of the wrong anchor type, the wrong data type, and links of the wrong
    link type, none of which the rules govern. A rule that stopped scoping would emit a
    finding the owner could not act on.
    """
    other_person = Anchor(uuid="a-4", type_key="person", display_name="Grace")
    task_type = AssociatedDataTypeDefinition(
        type_key="task", permitted_anchor_type_keys=("project",), description="A task."
    )
    mentions = LinkTypeDefinition(
        type_key="mentions",
        endpoint_constraint=EndpointConstraint(
            permitted_source_type_keys=("person",),
            permitted_target_type_keys=("person",),
            description="Who mentions whom.",
        ),
        description="A mention.",
    )
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON, PROJECT),
        associated_data_types=(NOTE, task_type),
        link_types=(WORKS_ON, mentions),
        relationship_constraints=(
            LinkMultiplicityConstraint(
                link_type_key="worksOn",
                constrained_end=LinkEnd.SOURCE,
                constrained_endpoint_type_keys=("person",),
                opposite_endpoint_type_keys=("project",),
                lower_bound=1,
                upper_bound=1,
                description="Exactly one project per person.",
            ),
            DirectAssociationMultiplicityConstraint(
                constrained_end=DirectAssociationEnd.ANCHOR,
                anchor_type_keys=("person",),
                associated_data_type_keys=("note",),
                lower_bound=1,
                upper_bound=1,
                description="Exactly one note per person.",
            ),
            DirectAssociationMultiplicityConstraint(
                constrained_end=DirectAssociationEnd.ASSOCIATED_DATA,
                anchor_type_keys=("project",),
                associated_data_type_keys=("task",),
                lower_bound=1,
                upper_bound=1,
                description="Exactly one project per task.",
            ),
        ),
    )
    graph = Graph(
        anchors=(ADA, ORBIT, other_person),
        associated_data=(
            _note("d-1"),
            AssociatedDataObject(
                uuid="d-2",
                type_key="note",
                anchor_uuids=("a-4",),
                properties={"title": normalize("Second")},
            ),
            AssociatedDataObject(uuid="d-3", type_key="task", anchor_uuids=("a-2",)),
        ),
        links=(
            Link(uuid="l-1", type_key="worksOn", source_uuid="a-1", target_uuid="a-2"),
            Link(uuid="l-2", type_key="worksOn", source_uuid="a-4", target_uuid="a-2"),
            # A link of an unrelated type: the worksOn rule must not count it.
            Link(uuid="l-3", type_key="mentions", source_uuid="a-1", target_uuid="a-4"),
        ),
    )
    assert _summaries(graph, definitions) == []
