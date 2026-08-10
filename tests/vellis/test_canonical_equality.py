"""Evidence for ``VellisVerification::canonicalEquality`` over JSON and definitions.

Each case names the nearest plausible wrong implementation it excludes, because most of
these distinctions are exactly the ones a convenient library default erases.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from vellis.canonical import CanonicalState, DefinitionDelta, canonical_state_equal
from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    DirectAssociationEnd,
    DirectAssociationMultiplicityConstraint,
    EndpointConstraint,
    GraphDefinitionSet,
    LinkTypeDefinition,
    PropertyConstraint,
    StringPattern,
    ValueRange,
    ValueShape,
    definition_set_equal,
)
from vellis.graph import Anchor, AssociatedDataObject, Graph, Link, graph_equal
from vellis.json_value import JsonKind, json_equal, json_kind, loads, normalize, value_size

COMPOSED_E_ACUTE = "\u00e9"
DECOMPOSED_E_ACUTE = "e\u0301"


def test_json_kinds_stay_distinct() -> None:
    """Excludes comparing with Python equality, under which True == 1 and 1 == 1.0 == True."""
    assert not json_equal(normalize(True), normalize(1))
    assert not json_equal(normalize(1), normalize("1"))
    assert not json_equal(normalize(None), normalize(False))
    assert not json_equal(normalize([]), normalize({}))
    assert json_kind(normalize(True)) is JsonKind.BOOLEAN
    assert json_kind(normalize(1)) is JsonKind.NUMBER


def test_numbers_compare_by_exact_mathematical_value() -> None:
    """Excludes comparing numbers by literal text or by JSON parser type."""
    assert json_equal(loads("1"), loads("1.0"))
    assert json_equal(loads("1.50"), loads("1.5"))
    assert not json_equal(loads("1"), loads("1.0000000000000001"))


def test_binary_floating_point_noise_does_not_decide_equality() -> None:
    """Excludes parsing numbers as float, where 0.1 + 0.2 leaks into stored meaning."""
    assert json_equal(loads("0.1"), normalize(Decimal("0.1")))
    assert not json_equal(loads("0.1"), loads("0.30000000000000004"))


def test_strings_compare_by_code_point_without_normalization() -> None:
    """Excludes Unicode normalization, which would fuse the two é spellings."""
    assert not json_equal(normalize(COMPOSED_E_ACUTE), normalize(DECOMPOSED_E_ACUTE))
    assert value_size(normalize(COMPOSED_E_ACUTE)) == 1
    assert value_size(normalize(DECOMPOSED_E_ACUTE)) == 2


def test_array_order_matters_and_object_member_order_does_not() -> None:
    """Excludes treating both collections the same way in either direction."""
    assert not json_equal(loads("[1,2]"), loads("[2,1]"))
    assert json_equal(loads('{"a":1,"b":2}'), loads('{"b":2,"a":1}'))


def test_missing_member_differs_from_present_null() -> None:
    """Excludes treating an absent property as a null-valued one."""
    assert not json_equal(loads('{"a":1}'), loads('{"a":1,"b":null}'))


def _anchor(uuid: str = "a-1", display_name: str = "Ada") -> Anchor:
    return Anchor(uuid=uuid, type_key="person", display_name=display_name)


def test_reordering_graph_collections_is_an_effective_no_op() -> None:
    """Excludes comparing owned collections positionally."""
    first = _anchor("a-1")
    second = _anchor("a-2", display_name="Grace")
    assert graph_equal(Graph(anchors=(first, second)), Graph(anchors=(second, first)))


def test_reordering_direct_associations_is_an_effective_no_op() -> None:
    """Excludes treating the identity-free anchor set as an ordered list."""
    forward = AssociatedDataObject(uuid="d-1", type_key="note", anchor_uuids=("a-1", "a-2"))
    reversed_order = AssociatedDataObject(uuid="d-1", type_key="note", anchor_uuids=("a-2", "a-1"))
    assert graph_equal(Graph(associated_data=(forward,)), Graph(associated_data=(reversed_order,)))


def test_changing_a_graph_object_value_is_a_semantic_difference() -> None:
    assert not graph_equal(
        Graph(anchors=(_anchor(),)), Graph(anchors=(_anchor(display_name="Ada L."),))
    )


def test_reversing_a_link_direction_is_a_semantic_difference() -> None:
    """Excludes comparing endpoints as an unordered pair."""
    forward = Link(uuid="l-1", type_key="knows", source_uuid="a-1", target_uuid="a-2")
    backward = Link(uuid="l-1", type_key="knows", source_uuid="a-2", target_uuid="a-1")
    assert not graph_equal(Graph(links=(forward,)), Graph(links=(backward,)))


def _described(type_key: str = "person") -> AnchorTypeDefinition:
    return AnchorTypeDefinition(type_key=type_key, description="A person the owner knows.")


def test_reordering_definitions_is_an_effective_no_op() -> None:
    first = _described("person")
    second = _described("project")
    assert definition_set_equal(
        GraphDefinitionSet(anchor_types=(first, second)),
        GraphDefinitionSet(anchor_types=(second, first)),
    )


def test_changing_a_description_is_a_semantic_difference() -> None:
    """Excludes treating descriptions as documentation outside canonical meaning."""
    assert not definition_set_equal(
        GraphDefinitionSet(anchor_types=(_described(),)),
        GraphDefinitionSet(
            anchor_types=(AnchorTypeDefinition(type_key="person", description="Someone else."),)
        ),
    )


def test_changing_pattern_text_is_a_semantic_difference() -> None:
    """Excludes normalizing equivalent expressions; the model compares text exactly."""
    left = _data_type_with_pattern("[0-9]{4}")
    right = _data_type_with_pattern("[0-9][0-9][0-9][0-9]")
    assert not definition_set_equal(left, right)


def _data_type_with_pattern(expression: str) -> GraphDefinitionSet:
    return GraphDefinitionSet(
        anchor_types=(_described(),),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="note",
                permitted_anchor_type_keys=("person",),
                property_constraints=(
                    PropertyConstraint(
                        property_name="year",
                        required=True,
                        json_kind=JsonKind.STRING,
                        description="The four-digit year.",
                        pattern=StringPattern(expression=expression),
                    ),
                ),
                description="A note about a person.",
            ),
        ),
    )


def test_permitted_value_order_does_not_decide_definition_equality() -> None:
    """Excludes comparing permitted values positionally; they are unique by JSON equality."""
    assert definition_set_equal(
        _data_type_with_permitted(("a", "b")), _data_type_with_permitted(("b", "a"))
    )
    assert not definition_set_equal(
        _data_type_with_permitted(("a", "b")), _data_type_with_permitted(("a", "c"))
    )


def _data_type_with_permitted(values: tuple[str, ...]) -> GraphDefinitionSet:
    return GraphDefinitionSet(
        anchor_types=(_described(),),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="note",
                permitted_anchor_type_keys=("person",),
                property_constraints=(
                    PropertyConstraint(
                        property_name="tag",
                        required=False,
                        json_kind=JsonKind.STRING,
                        description="One of the permitted tags.",
                        value_range=ValueRange(
                            permitted_values=tuple(normalize(each) for each in values)
                        ),
                    ),
                ),
                description="A note about a person.",
            ),
        ),
    )


def test_endpoint_role_is_part_of_link_type_meaning() -> None:
    """Excludes comparing source and target as one unordered endpoint set."""
    forward = _link_type(("person",), ("project",))
    swapped = _link_type(("project",), ("person",))
    assert not definition_set_equal(forward, swapped)


def _link_type(source: tuple[str, ...], target: tuple[str, ...]) -> GraphDefinitionSet:
    return GraphDefinitionSet(
        anchor_types=(_described("person"), _described("project")),
        link_types=(
            LinkTypeDefinition(
                type_key="worksOn",
                endpoint_constraint=EndpointConstraint(
                    permitted_source_type_keys=source,
                    permitted_target_type_keys=target,
                    description="Who works on what.",
                ),
                description="A working relationship.",
            ),
        ),
    )


def test_multiplicity_natural_identity_ignores_participating_order() -> None:
    """Excludes treating the unordered participating type sets as ordered lists."""
    assert definition_set_equal(
        _direct_association(("person", "team")), _direct_association(("team", "person"))
    )


def _direct_association(anchor_types: tuple[str, ...]) -> GraphDefinitionSet:
    return GraphDefinitionSet(
        anchor_types=tuple(_described(each) for each in sorted(anchor_types)),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="note",
                permitted_anchor_type_keys=tuple(sorted(anchor_types)),
                description="A note.",
            ),
        ),
        relationship_constraints=(
            DirectAssociationMultiplicityConstraint(
                constrained_end=DirectAssociationEnd.ANCHOR,
                anchor_type_keys=anchor_types,
                associated_data_type_keys=("note",),
                lower_bound=0,
                upper_bound=None,
                description="How many notes an anchor may carry.",
            ),
        ),
    )


@pytest.mark.parametrize("revision", [0, 1])
def test_canonical_state_equality_includes_revision(revision: int) -> None:
    base = CanonicalState(graph=Graph(), active_definitions=GraphDefinitionSet(), revision=0)
    other = CanonicalState(
        graph=Graph(), active_definitions=GraphDefinitionSet(), revision=revision
    )
    assert canonical_state_equal(base, other) is (revision == 0)


def test_canonical_state_equality_includes_delta_presence_and_content() -> None:
    """Excludes comparing only graph and active definitions."""
    empty = GraphDefinitionSet()
    without = CanonicalState(graph=Graph(), active_definitions=empty, revision=0)
    with_delta = CanonicalState(
        graph=Graph(),
        active_definitions=empty,
        revision=0,
        definition_delta=DefinitionDelta(
            proposed_definitions=GraphDefinitionSet(anchor_types=(_described(),))
        ),
    )
    other_delta = CanonicalState(
        graph=Graph(),
        active_definitions=empty,
        revision=0,
        definition_delta=DefinitionDelta(
            proposed_definitions=GraphDefinitionSet(anchor_types=(_described("project"),))
        ),
    )
    assert not canonical_state_equal(without, with_delta)
    assert not canonical_state_equal(with_delta, other_delta)
    assert canonical_state_equal(with_delta, with_delta)


def test_system_metadata_participates_in_graph_equality() -> None:
    """Excludes comparing graph objects while ignoring their canonical metadata."""
    from vellis.graph import SystemMetadata

    live = Anchor(uuid="a-1", type_key="person", display_name="Ada")
    retired = Anchor(
        uuid="a-1",
        type_key="person",
        display_name="Ada",
        system_metadata=SystemMetadata(members={"live": False}),
    )
    annotated = Anchor(
        uuid="a-1",
        type_key="person",
        display_name="Ada",
        system_metadata=SystemMetadata(members={"live": True, "origin": "import"}),
    )
    assert not graph_equal(Graph(anchors=(live,)), Graph(anchors=(retired,)))
    assert not graph_equal(Graph(anchors=(live,)), Graph(anchors=(annotated,)))


def test_associated_data_properties_participate_in_graph_equality() -> None:
    """Excludes comparing associated data by identity and type alone."""
    first = AssociatedDataObject(
        uuid="d-1", type_key="note", anchor_uuids=("a-1",), properties={"title": "First"}
    )
    second = AssociatedDataObject(
        uuid="d-1", type_key="note", anchor_uuids=("a-1",), properties={"title": "Second"}
    )
    absent = AssociatedDataObject(uuid="d-1", type_key="note", anchor_uuids=("a-1",))
    assert not graph_equal(Graph(associated_data=(first,)), Graph(associated_data=(second,)))
    assert not graph_equal(Graph(associated_data=(first,)), Graph(associated_data=(absent,)))


def test_a_repeated_direct_association_is_not_the_same_as_a_single_one() -> None:
    """Excludes comparing the anchor references only as a set, which hides a duplicate."""
    twice = AssociatedDataObject(uuid="d-1", type_key="note", anchor_uuids=("a-1", "a-1"))
    once = AssociatedDataObject(uuid="d-1", type_key="note", anchor_uuids=("a-1",))
    assert not graph_equal(Graph(associated_data=(twice,)), Graph(associated_data=(once,)))


def test_a_duplicated_graph_object_is_not_the_same_as_a_single_one() -> None:
    """Excludes keying by UUID in a way that silently collapses two objects into one."""
    duplicated = Graph(anchors=(_anchor("a-1"), _anchor("a-1", display_name="Ada L.")))
    single = Graph(anchors=(_anchor("a-1", display_name="Ada L."),))
    assert not graph_equal(duplicated, single)


def test_a_duplicated_definition_is_not_the_same_as_a_single_one() -> None:
    """Excludes collapsing two definitions that share a natural identity into one."""
    duplicated = GraphDefinitionSet(
        anchor_types=(
            AnchorTypeDefinition(type_key="person", description="First meaning."),
            AnchorTypeDefinition(type_key="person", description="Second meaning."),
        )
    )
    single = GraphDefinitionSet(
        anchor_types=(AnchorTypeDefinition(type_key="person", description="Second meaning."),)
    )
    assert not definition_set_equal(duplicated, single)


def test_a_duplicated_multiplicity_rule_is_not_the_same_as_a_single_one() -> None:
    left = _direct_association(("person",))
    doubled = GraphDefinitionSet(
        anchor_types=left.anchor_types,
        associated_data_types=left.associated_data_types,
        link_types=left.link_types,
        relationship_constraints=(
            left.relationship_constraints[0],
            left.relationship_constraints[0],
        ),
    )
    assert not definition_set_equal(doubled, left)


def test_multiplicity_bounds_participate_in_definition_equality() -> None:
    """Excludes comparing multiplicity rules by natural identity alone."""
    from vellis.definitions import DirectAssociationMultiplicityConstraint

    base = _direct_association(("person",))
    original = base.relationship_constraints[0]
    assert isinstance(original, DirectAssociationMultiplicityConstraint)
    widened = GraphDefinitionSet(
        anchor_types=base.anchor_types,
        associated_data_types=base.associated_data_types,
        link_types=base.link_types,
        relationship_constraints=(
            DirectAssociationMultiplicityConstraint(
                constrained_end=original.constrained_end,
                anchor_type_keys=original.anchor_type_keys,
                associated_data_type_keys=original.associated_data_type_keys,
                lower_bound=original.lower_bound,
                upper_bound=9,
                description=original.description,
            ),
        ),
    )
    assert not definition_set_equal(base, widened)


def test_a_python_float_does_not_carry_binary_noise_into_stored_meaning() -> None:
    """Excludes constructing the Decimal from the float's exact binary value."""
    assert json_equal(normalize(0.1), loads("0.1"))
    assert json_equal(normalize(2.675), loads("2.675"))


def test_two_equal_objects_written_in_different_orders_serialize_identically() -> None:
    """Excludes an encoding whose bytes depend on member insertion order."""
    from vellis.json_value import dumps

    assert dumps(normalize({"a": 1, "b": 2})) == dumps(normalize({"b": 2, "a": 1}))


def test_unencodable_text_is_refused_rather_than_carried() -> None:
    """Excludes admitting a lone surrogate that later breaks storage or matching.

    A Python string can hold one and JSON text can produce one, but no UTF-8 encoder
    will take it, so it must be refused where it enters rather than where it explodes.
    """
    from vellis.json_value import JsonValueError

    lone = chr(0xD800)
    with pytest.raises(JsonValueError, match="unpaired surrogate"):
        normalize(lone)
    with pytest.raises(JsonValueError, match="unpaired surrogate"):
        normalize({"text": "a" + lone})
    with pytest.raises(JsonValueError, match="unpaired surrogate"):
        loads('"\\ud800"')


def test_string_equality_is_case_sensitive() -> None:
    """Excludes case-folded comparison; the model compares exact code-point sequences."""
    assert not json_equal(normalize("Ada"), normalize("ada"))
    assert not json_equal(normalize("STRASSE"), normalize("strasse"))


def test_permitted_anchor_types_compare_without_order() -> None:
    """Excludes comparing this unordered reference set positionally."""
    assert definition_set_equal(
        _grounded_note(("person", "project")), _grounded_note(("project", "person"))
    )
    assert not definition_set_equal(
        _grounded_note(("person", "project")), _grounded_note(("person",))
    )


def _grounded_note(anchor_keys: tuple[str, ...]) -> GraphDefinitionSet:
    return GraphDefinitionSet(
        anchor_types=(_described("person"), _described("project")),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="note",
                permitted_anchor_type_keys=anchor_keys,
                description="A note.",
            ),
        ),
    )


def test_link_multiplicity_participating_sets_compare_without_order() -> None:
    """Excludes ordering the link rule's participating sets, which the model calls unordered."""
    assert definition_set_equal(
        _link_multiplicity(("person", "project")), _link_multiplicity(("project", "person"))
    )
    assert not definition_set_equal(
        _link_multiplicity(("person", "project")), _link_multiplicity(("person",))
    )


def _link_multiplicity(opposite: tuple[str, ...]) -> GraphDefinitionSet:
    from vellis.definitions import LinkEnd, LinkMultiplicityConstraint

    base = _link_type(("person",), ("project",))
    return GraphDefinitionSet(
        anchor_types=base.anchor_types,
        link_types=base.link_types,
        relationship_constraints=(
            LinkMultiplicityConstraint(
                link_type_key="worksOn",
                constrained_end=LinkEnd.SOURCE,
                constrained_endpoint_type_keys=("person",),
                opposite_endpoint_type_keys=opposite,
                lower_bound=0,
                upper_bound=None,
                description="How many things one person may work on.",
            ),
        ),
    )


def test_an_unencodable_member_name_is_refused_like_an_unencodable_value() -> None:
    """Excludes screening only the value side of an object.

    A member name is stored and matched exactly as a value is, so a screen that walks
    values and skips names is a hole, not a simplification.
    """
    from vellis.json_value import JsonValueError

    lone = chr(0xD800)
    with pytest.raises(JsonValueError, match="unpaired surrogate"):
        normalize({lone: 1})
    with pytest.raises(JsonValueError, match="unpaired surrogate"):
        normalize({"outer": {"inner" + lone: 1}})
    with pytest.raises(JsonValueError, match="unpaired surrogate"):
        normalize([{lone: 1}])


def _nested(depth: int) -> dict[str, object]:
    value: dict[str, object] = {"leaf": 1}
    for _ in range(depth):
        value = {"a": value}
    return value


def test_nesting_is_bounded_where_a_value_enters() -> None:
    """Excludes accepting a value too deep to serialize or compare afterwards.

    Normalizing recurses about half as fast as serializing and comparing do, so a value
    accepted here but rejected later would surface as a stack overflow during a store
    write rather than as a finding.
    """
    from vellis.json_value import MAXIMUM_NESTING_DEPTH, JsonValueError, dumps

    within = normalize(_nested(MAXIMUM_NESTING_DEPTH - 2))
    # Whatever normalize accepts, the later traversals must survive.
    assert json_equal(within, normalize(_nested(MAXIMUM_NESTING_DEPTH - 2)))
    assert dumps(within)

    with pytest.raises(JsonValueError, match="nests deeper"):
        normalize(_nested(MAXIMUM_NESTING_DEPTH + 5))
    with pytest.raises(JsonValueError, match="nests deeper"):
        normalize([_nested(MAXIMUM_NESTING_DEPTH + 5)])


def test_deeply_nested_stored_text_is_refused_as_a_json_error() -> None:
    """Excludes a stack overflow escaping the reader as an untyped failure."""
    from vellis.json_value import JsonValueError

    text = "[" * 5000 + "]" * 5000
    with pytest.raises(JsonValueError):
        loads(text)


# --- Every discriminator, not one representative per collection ---------------------
#
# Proving one field of a comparator participates in equality says nothing about its
# siblings. These tables change exactly one field at a time so that no discriminator can
# quietly stop mattering.


def _graph_variants() -> dict[str, tuple[Graph, Graph]]:
    from vellis.graph import SystemMetadata

    base_anchor = Anchor(uuid="a-1", type_key="person", display_name="Ada")
    base_data = AssociatedDataObject(
        uuid="d-1", type_key="note", anchor_uuids=("a-1",), properties={"title": "First"}
    )
    base_link = Link(uuid="l-1", type_key="knows", source_uuid="a-1", target_uuid="a-2")
    return {
        "anchor type key": (
            Graph(anchors=(base_anchor,)),
            Graph(anchors=(Anchor(uuid="a-1", type_key="project", display_name="Ada"),)),
        ),
        "anchor display name": (
            Graph(anchors=(base_anchor,)),
            Graph(anchors=(Anchor(uuid="a-1", type_key="person", display_name="Grace"),)),
        ),
        "anchor metadata": (
            Graph(anchors=(base_anchor,)),
            Graph(
                anchors=(
                    Anchor(
                        uuid="a-1",
                        type_key="person",
                        display_name="Ada",
                        system_metadata=SystemMetadata(members={"live": False}),
                    ),
                )
            ),
        ),
        "data type key": (
            Graph(associated_data=(base_data,)),
            Graph(
                associated_data=(
                    AssociatedDataObject(
                        uuid="d-1",
                        type_key="task",
                        anchor_uuids=("a-1",),
                        properties={"title": "First"},
                    ),
                )
            ),
        ),
        "data properties": (
            Graph(associated_data=(base_data,)),
            Graph(
                associated_data=(
                    AssociatedDataObject(
                        uuid="d-1",
                        type_key="note",
                        anchor_uuids=("a-1",),
                        properties={"title": "Second"},
                    ),
                )
            ),
        ),
        "data associations": (
            Graph(associated_data=(base_data,)),
            Graph(
                associated_data=(
                    AssociatedDataObject(
                        uuid="d-1",
                        type_key="note",
                        anchor_uuids=("a-2",),
                        properties={"title": "First"},
                    ),
                )
            ),
        ),
        "link type key": (
            Graph(links=(base_link,)),
            Graph(
                links=(Link(uuid="l-1", type_key="manages", source_uuid="a-1", target_uuid="a-2"),)
            ),
        ),
        "link source": (
            Graph(links=(base_link,)),
            Graph(
                links=(Link(uuid="l-1", type_key="knows", source_uuid="a-3", target_uuid="a-2"),)
            ),
        ),
        "link metadata": (
            Graph(links=(base_link,)),
            Graph(
                links=(
                    Link(
                        uuid="l-1",
                        type_key="knows",
                        source_uuid="a-1",
                        target_uuid="a-2",
                        system_metadata=SystemMetadata(members={"live": False}),
                    ),
                )
            ),
        ),
        "duplicate associated data": (
            Graph(associated_data=(base_data, base_data)),
            Graph(associated_data=(base_data,)),
        ),
        "duplicate link": (Graph(links=(base_link, base_link)), Graph(links=(base_link,))),
    }


@pytest.mark.parametrize("discriminator", sorted(_graph_variants()))
def test_every_graph_discriminator_participates_in_equality(discriminator: str) -> None:
    left, right = _graph_variants()[discriminator]
    assert not graph_equal(left, right)
    assert not graph_equal(right, left)
    if not discriminator.startswith("duplicate"):
        # A value carrying duplicate identities is deliberately not equal to itself:
        # equality fails closed rather than collapsing the duplicates away.
        assert graph_equal(left, left)


def _definition_variants() -> dict[str, tuple[GraphDefinitionSet, GraphDefinitionSet]]:
    from vellis.definitions import (
        DirectAssociationMultiplicityConstraint as Association,
    )

    def data_type(**overrides: object) -> GraphDefinitionSet:
        fields: dict[str, object] = {
            "type_key": "note",
            "permitted_anchor_type_keys": ("person",),
            "description": "A note.",
            "property_constraints": (),
        }
        fields.update(overrides)
        return GraphDefinitionSet(
            anchor_types=(_described(),),
            associated_data_types=(AssociatedDataTypeDefinition(**fields),),  # pyright: ignore[reportArgumentType]
        )

    def constrained(**overrides: object) -> GraphDefinitionSet:
        fields: dict[str, object] = {
            "property_name": "title",
            "required": True,
            "json_kind": JsonKind.STRING,
            "description": "A title.",
        }
        fields.update(overrides)
        return data_type(property_constraints=(PropertyConstraint(**fields),))  # pyright: ignore[reportArgumentType]

    def rule(**overrides: object) -> GraphDefinitionSet:
        fields: dict[str, object] = {
            "constrained_end": DirectAssociationEnd.ANCHOR,
            "anchor_type_keys": ("person",),
            "associated_data_type_keys": ("note",),
            "lower_bound": 0,
            "upper_bound": 5,
            "description": "A rule.",
        }
        fields.update(overrides)
        base = data_type()
        return GraphDefinitionSet(
            anchor_types=base.anchor_types,
            associated_data_types=base.associated_data_types,
            relationship_constraints=(Association(**fields),),  # pyright: ignore[reportArgumentType]
        )

    return {
        "data type description": (data_type(), data_type(description="Something else.")),
        "permitted anchor types": (
            data_type(),
            data_type(permitted_anchor_type_keys=("person", "project")),
        ),
        "property required": (constrained(), constrained(required=False)),
        "property json kind": (constrained(), constrained(json_kind=JsonKind.NUMBER)),
        "property description": (constrained(), constrained(description="Another title.")),
        "property value shape": (
            constrained(),
            constrained(value_shape=ValueShape(minimum_size=1)),
        ),
        "range lower bound": (
            constrained(
                json_kind=JsonKind.NUMBER, value_range=ValueRange(lower_bound=normalize(1))
            ),
            constrained(
                json_kind=JsonKind.NUMBER, value_range=ValueRange(lower_bound=normalize(2))
            ),
        ),
        "range upper bound": (
            constrained(
                json_kind=JsonKind.NUMBER, value_range=ValueRange(upper_bound=normalize(9))
            ),
            constrained(
                json_kind=JsonKind.NUMBER, value_range=ValueRange(upper_bound=normalize(8))
            ),
        ),
        "link type description": (
            _link_type(("person",), ("project",)),
            GraphDefinitionSet(
                anchor_types=_link_type(("person",), ("project",)).anchor_types,
                link_types=(
                    LinkTypeDefinition(
                        type_key="worksOn",
                        endpoint_constraint=EndpointConstraint(
                            permitted_source_type_keys=("person",),
                            permitted_target_type_keys=("project",),
                            description="Who works on what.",
                        ),
                        description="A different relationship.",
                    ),
                ),
            ),
        ),
        "endpoint target types": (
            _link_type(("person",), ("project",)),
            _link_type(("person",), ("project", "person")),
        ),
        "rule lower bound": (rule(), rule(lower_bound=1)),
        "rule description": (rule(), rule(description="Another rule.")),
        "duplicate rule": (rule(), _doubled(rule())),
    }


def _doubled(definitions: GraphDefinitionSet) -> GraphDefinitionSet:
    return GraphDefinitionSet(
        anchor_types=definitions.anchor_types,
        associated_data_types=definitions.associated_data_types,
        link_types=definitions.link_types,
        relationship_constraints=definitions.relationship_constraints * 2,
    )


@pytest.mark.parametrize("discriminator", sorted(_definition_variants()))
def test_every_definition_discriminator_participates_in_equality(discriminator: str) -> None:
    left, right = _definition_variants()[discriminator]
    assert not definition_set_equal(left, right)
    assert not definition_set_equal(right, left)
    if not discriminator.startswith("duplicate"):
        assert definition_set_equal(left, left)


def test_endpoint_roles_are_compared_separately_not_twice_over() -> None:
    """Excludes comparing the source list twice and never comparing the target list."""
    assert not definition_set_equal(
        _link_type(("person",), ("project",)), _link_type(("person",), ("person",))
    )


def test_arrays_of_different_lengths_compare_unequal_without_raising() -> None:
    """Excludes relying on a strict zip, which raises instead of answering."""
    assert not json_equal(loads("[1]"), loads("[1,2]"))
    assert not json_equal(loads("[1,2]"), loads("[1]"))
    assert not json_equal(normalize({"a": [1]}), normalize({"a": [1, 2]}))


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_a_non_finite_float_is_not_a_json_value(value: float) -> None:
    """The Decimal branch is pinned elsewhere; the float branch needs its own case."""
    from vellis.json_value import JsonValueError

    with pytest.raises(JsonValueError, match="non-finite"):
        normalize(value)


def test_objects_of_equal_size_with_different_member_names_are_unequal() -> None:
    """Excludes comparing member count in place of member names.

    A length check satisfies every existing member-name case, but it lets two objects
    with disjoint names fall through to a lookup that raises instead of answering.
    """
    assert not json_equal(loads('{"a":1}'), loads('{"b":1}'))
    assert not json_equal(loads('{"a":1,"b":2}'), loads('{"a":1,"c":2}'))
    assert not graph_equal(
        Graph(
            associated_data=(
                AssociatedDataObject(
                    uuid="d-1", type_key="note", anchor_uuids=("a-1",), properties={"title": "x"}
                ),
            )
        ),
        Graph(
            associated_data=(
                AssociatedDataObject(
                    uuid="d-1", type_key="note", anchor_uuids=("a-1",), properties={"body": "x"}
                ),
            )
        ),
    )


def test_canonical_state_equality_includes_its_graph_and_its_definitions() -> None:
    """Excludes comparing only revision and delta at the canonical-state level."""
    definitions = GraphDefinitionSet(anchor_types=(_described(),))
    other_definitions = GraphDefinitionSet(anchor_types=(_described("project"),))
    graph = Graph(anchors=(_anchor("a-1"),))

    base = CanonicalState(graph=graph, active_definitions=definitions, revision=0)
    other_graph = CanonicalState(
        graph=Graph(anchors=(_anchor("a-2"),)), active_definitions=definitions, revision=0
    )
    other_vocabulary = CanonicalState(graph=graph, active_definitions=other_definitions, revision=0)

    assert canonical_state_equal(base, base)
    assert not canonical_state_equal(base, other_graph)
    assert not canonical_state_equal(base, other_vocabulary)


def test_narrowing_a_permitted_value_set_is_not_an_effective_no_op() -> None:
    """Excludes comparing permitted values without comparing how many there are."""
    from vellis.definitions import PropertyConstraint as Constraint

    def permitting(*values: object) -> GraphDefinitionSet:
        return GraphDefinitionSet(
            anchor_types=(_described(),),
            associated_data_types=(
                AssociatedDataTypeDefinition(
                    type_key="note",
                    permitted_anchor_type_keys=("person",),
                    property_constraints=(
                        Constraint(
                            property_name="tag",
                            required=False,
                            json_kind=JsonKind.STRING,
                            description="A tag.",
                            value_range=ValueRange(
                                permitted_values=tuple(normalize(each) for each in values)
                            ),
                        ),
                    ),
                    description="A note.",
                ),
            ),
        )

    assert not definition_set_equal(permitting("a"), permitting("a", "b"))
    assert not definition_set_equal(permitting("a", "b"), permitting("a"))
