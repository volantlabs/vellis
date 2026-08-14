"""Evidence that an internally invalid definition set is refused.

Supports ``VellisVerification::graphInvariants`` and
``VellisVerification::freshInitialization``: a fresh RTG accepts only an internally
valid initial definition set, so these are the rules that decide that word.
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
    relationship_label,
    validate_definition_set,
)
from vellis.json_value import JsonKind, normalize

PERSON = AnchorTypeDefinition(type_key="person", description="A person.")


def _property(
    name: str,
    *,
    json_kind: JsonKind = JsonKind.STRING,
    value_shape: ValueShape | None = None,
    value_range: ValueRange | None = None,
) -> PropertyConstraint:
    return PropertyConstraint(
        property_name=name,
        required=False,
        json_kind=json_kind,
        description="A property.",
        value_shape=value_shape,
        value_range=value_range,
    )


def _data_type(constraints: tuple[PropertyConstraint, ...]) -> GraphDefinitionSet:
    return GraphDefinitionSet(
        anchor_types=(PERSON,),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="note",
                permitted_anchor_type_keys=("person",),
                property_constraints=constraints,
                description="A note about a person.",
            ),
        ),
    )


def _summaries(definitions: GraphDefinitionSet, *, require_descriptions: bool = True) -> list[str]:
    return [
        finding.summary
        for finding in validate_definition_set(
            definitions, require_descriptions=require_descriptions
        )
    ]


def test_the_empty_definition_set_is_internally_valid() -> None:
    """The blank first-use start depends on this."""
    assert validate_definition_set(GraphDefinitionSet()) == ()


def test_active_definitions_need_non_empty_descriptions() -> None:
    blank = AnchorTypeDefinition(type_key="person", description="")
    assert any(
        "no non-empty owner-readable description" in each
        for each in _summaries(GraphDefinitionSet(anchor_types=(blank,)))
    )
    missing = AnchorTypeDefinition(type_key="person")
    assert any(
        "no non-empty owner-readable description" in each
        for each in _summaries(GraphDefinitionSet(anchor_types=(missing,)))
    )


def test_a_proposal_may_omit_descriptions_while_it_is_edited() -> None:
    """Excludes treating a missing description as structural corruption in every scope."""
    proposal = GraphDefinitionSet(anchor_types=(AnchorTypeDefinition(type_key="person"),))
    assert _summaries(proposal, require_descriptions=False) == []


def test_type_keys_share_one_namespace_across_kinds() -> None:
    """Excludes keeping a separate key table per object kind."""
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON,),
        link_types=(
            LinkTypeDefinition(
                type_key="person",
                endpoint_constraint=EndpointConstraint(
                    permitted_source_type_keys=("person",),
                    permitted_target_type_keys=("person",),
                    description="A link.",
                ),
                description="A clashing link type.",
            ),
        ),
    )
    assert any("the type-key namespace is shared" in each for each in _summaries(definitions))


def test_an_empty_type_key_is_invalid() -> None:
    definitions = GraphDefinitionSet(
        anchor_types=(AnchorTypeDefinition(type_key="", description="Nameless."),)
    )
    assert any("empty type key" in each for each in _summaries(definitions))


def test_property_names_are_non_empty_and_unique_within_their_type() -> None:
    duplicated = _data_type(
        (
            _property("title"),
            _property("title"),
            _property(""),
        )
    )
    summaries = _summaries(duplicated)
    assert any("more than once" in each for each in summaries)
    assert any("empty name" in each for each in summaries)


@pytest.mark.parametrize(
    ("constraint", "expected"),
    [
        (
            _property("n", json_kind=JsonKind.NUMBER, value_shape=ValueShape(minimum_size=1)),
            "valid only for string, array, or object",
        ),
        (_property("s", value_shape=ValueShape()), "size condition with no bound"),
        (
            _property("s", value_shape=ValueShape(minimum_size=5, maximum_size=2)),
            "inverted size condition",
        ),
        (_property("s", value_range=ValueRange()), "no bound and no permitted value"),
        (
            _property(
                "n",
                json_kind=JsonKind.NUMBER,
                value_range=ValueRange(lower_bound=normalize(5), upper_bound=normalize(1)),
            ),
            "inverted numeric range",
        ),
        (
            _property("s", value_range=ValueRange(lower_bound=normalize(1))),
            "but governs stringValue",
        ),
        (
            _property("s", value_range=ValueRange(permitted_values=(normalize(1),))),
            "but governs stringValue",
        ),
        (
            _property(
                "s", value_range=ValueRange(permitted_values=(normalize("a"), normalize("a")))
            ),
            "duplicate permitted value",
        ),
    ],
)
def test_incompatible_property_rules_are_invalid(
    constraint: PropertyConstraint, expected: str
) -> None:
    assert any(expected in each for each in _summaries(_data_type((constraint,))))


def test_permitted_values_are_unique_by_json_equality_not_by_text() -> None:
    """Excludes de-duplicating permitted values by their literal spelling."""
    constraint = _property(
        "n",
        json_kind=JsonKind.NUMBER,
        value_range=ValueRange(permitted_values=(normalize(1), normalize(1.0))),
    )
    assert any(
        "duplicate permitted value" in each for each in _summaries(_data_type((constraint,)))
    )


def test_references_must_resolve_inside_the_set() -> None:
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON,),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="note",
                permitted_anchor_type_keys=("ghost",),
                description="A note.",
            ),
        ),
    )
    assert any("unknown anchor type" in each for each in _summaries(definitions))


def test_an_associated_data_type_must_permit_at_least_one_anchor_type() -> None:
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON,),
        associated_data_types=(
            AssociatedDataTypeDefinition(type_key="note", description="A note."),
        ),
    )
    assert any("permits no anchor type" in each for each in _summaries(definitions))


def test_duplicate_multiplicity_natural_identity_is_invalid() -> None:
    """Excludes deciding identity by object reference rather than by the modeled tuple."""
    first = DirectAssociationMultiplicityConstraint(
        constrained_end=DirectAssociationEnd.ANCHOR,
        anchor_type_keys=("person",),
        associated_data_type_keys=("note",),
        lower_bound=0,
        upper_bound=1,
        description="One note per person.",
    )
    second = DirectAssociationMultiplicityConstraint(
        constrained_end=DirectAssociationEnd.ANCHOR,
        anchor_type_keys=("person",),
        associated_data_type_keys=("note",),
        lower_bound=0,
        upper_bound=5,
        description="A different bound with the same identity.",
    )
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON,),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="note", permitted_anchor_type_keys=("person",), description="A note."
            ),
        ),
        relationship_constraints=(first, second),
    )
    assert any("duplicates another multiplicity rule" in each for each in _summaries(definitions))


def test_duplicate_participating_members_are_invalid() -> None:
    constraint = DirectAssociationMultiplicityConstraint(
        constrained_end=DirectAssociationEnd.ANCHOR,
        anchor_type_keys=("person", "person"),
        associated_data_type_keys=("note",),
        lower_bound=0,
        description="Duplicated participants.",
    )
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON,),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="note", permitted_anchor_type_keys=("person",), description="A note."
            ),
        ),
        relationship_constraints=(constraint,),
    )
    assert any("more than once" in each for each in _summaries(definitions))


def test_multiplicity_bounds_may_not_invert() -> None:
    constraint = LinkMultiplicityConstraint(
        link_type_key="worksOn",
        constrained_end=LinkEnd.SOURCE,
        constrained_endpoint_type_keys=("person",),
        opposite_endpoint_type_keys=("person",),
        lower_bound=3,
        upper_bound=1,
        description="An impossible bound.",
    )
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON,),
        link_types=(
            LinkTypeDefinition(
                type_key="worksOn",
                endpoint_constraint=EndpointConstraint(
                    permitted_source_type_keys=("person",),
                    permitted_target_type_keys=("person",),
                    description="A link.",
                ),
                description="A link type.",
            ),
        ),
        relationship_constraints=(constraint,),
    )
    assert any("upper bound below its lower bound" in each for each in _summaries(definitions))


def test_negative_multiplicity_and_size_bounds_are_invalid() -> None:
    """Excludes accepting a bound that no population can ever satisfy."""
    negative_size = _property("s", value_shape=ValueShape(minimum_size=-1))
    assert any("negative minimum size" in each for each in _summaries(_data_type((negative_size,))))

    constraint = DirectAssociationMultiplicityConstraint(
        constrained_end=DirectAssociationEnd.ANCHOR,
        anchor_type_keys=("person",),
        associated_data_type_keys=("note",),
        lower_bound=-1,
        description="A negative lower bound.",
    )
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON,),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="note", permitted_anchor_type_keys=("person",), description="A note."
            ),
        ),
        relationship_constraints=(constraint,),
    )
    assert any("negative lower bound" in each for each in _summaries(definitions))


@pytest.mark.parametrize("text", ["NaN", "Infinity", "-Infinity"])
def test_a_non_finite_bound_is_refused_at_construction(text: str) -> None:
    """Excludes a bound that later crashes comparison or silently rejects every value."""
    from decimal import Decimal

    from vellis.json_value import JsonValueError

    with pytest.raises(JsonValueError):
        ValueRange(lower_bound=Decimal(text))
    with pytest.raises(JsonValueError):
        ValueRange(permitted_values=(Decimal(text),))


def test_an_exactly_one_multiplicity_bound_is_valid() -> None:
    """Excludes rejecting lower == upper, which is the ordinary "exactly one" rule."""
    constraint = DirectAssociationMultiplicityConstraint(
        constrained_end=DirectAssociationEnd.ANCHOR,
        anchor_type_keys=("person",),
        associated_data_type_keys=("note",),
        lower_bound=1,
        upper_bound=1,
        description="Exactly one note per person.",
    )
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON,),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="note", permitted_anchor_type_keys=("person",), description="A note."
            ),
        ),
        relationship_constraints=(constraint,),
    )
    assert _summaries(definitions) == []


def _unencodable(field: str) -> GraphDefinitionSet:
    """Return a definition set whose only fault is unencodable text in ``field``."""
    lone = chr(0xD800)
    anchor_description = "A person." if field != "anchor description" else "A " + lone
    anchor_key = "person" if field != "anchor type key" else "person" + lone
    return GraphDefinitionSet(
        anchor_types=(AnchorTypeDefinition(type_key=anchor_key, description=anchor_description),),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="note",
                permitted_anchor_type_keys=(anchor_key,),
                property_constraints=(
                    PropertyConstraint(
                        property_name="title" if field != "property name" else "title" + lone,
                        required=False,
                        json_kind=JsonKind.STRING,
                        description=(
                            "A title." if field != "property description" else "A " + lone
                        ),
                        pattern=(
                            StringPattern(expression="x" + lone)
                            if field == "pattern expression"
                            else None
                        ),
                    ),
                ),
                description="A note." if field != "data description" else "A " + lone,
            ),
        ),
        link_types=(
            LinkTypeDefinition(
                type_key="worksOn",
                endpoint_constraint=EndpointConstraint(
                    permitted_source_type_keys=(anchor_key,),
                    permitted_target_type_keys=("note",),
                    description=(
                        "Who works on what." if field != "endpoint description" else "A " + lone
                    ),
                ),
                description="A link." if field != "link description" else "A " + lone,
            ),
        ),
        relationship_constraints=(
            DirectAssociationMultiplicityConstraint(
                constrained_end=DirectAssociationEnd.ANCHOR,
                anchor_type_keys=(anchor_key,),
                associated_data_type_keys=("note",),
                lower_bound=0,
                description=("A rule." if field != "relationship description" else "A " + lone),
            ),
        ),
    )


@pytest.mark.parametrize(
    "field",
    [
        "anchor type key",
        "anchor description",
        "data description",
        "property name",
        "property description",
        "pattern expression",
        "link description",
        "endpoint description",
        "relationship description",
    ],
)
def test_unencodable_definition_text_is_a_finding_not_a_later_failure(field: str) -> None:
    """Excludes deferring the failure to the store or the pattern engine.

    Definition text is not a JSON value, so nothing else screens it. Every field is
    covered because a screen with one hole is the same defect as no screen.
    """
    assert any("unpaired surrogate" in each for each in _summaries(_unencodable(field)))


def test_unencodable_definition_text_refuses_initialization_without_effect(
    tmp_path: object,
) -> None:
    """The whole point of the finding: initialization reports, it does not explode."""
    from pathlib import Path

    from vellis.canonical import Provenance
    from vellis.outcomes import OperationStatus
    from vellis.system import RTGSystem

    assert isinstance(tmp_path, Path)
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        outcome = system.initialize_fresh(
            GraphDefinitionSet(
                anchor_types=(
                    AnchorTypeDefinition(type_key="person" + chr(0xD800), description="A person."),
                )
            ),
            provenance=Provenance(initiator="owner"),
            initialization_summary="a fresh start",
        )
        assert outcome.status is OperationStatus.REJECTED
        assert not system.is_initialized
        assert system.store.canonical_record_count() == 0
    finally:
        system.close()


def test_an_equal_bound_range_and_shape_are_valid() -> None:
    """Excludes rejecting lower == upper, which is an ordinary exact-value rule."""
    from vellis.json_value import normalize as as_json

    exact_range = _property(
        "n",
        json_kind=JsonKind.NUMBER,
        value_range=ValueRange(lower_bound=as_json(3), upper_bound=as_json(3)),
    )
    exact_size = _property("s", value_shape=ValueShape(minimum_size=4, maximum_size=4))
    assert _summaries(_data_type((exact_range, exact_size))) == []


def test_narrowing_a_permitted_value_list_is_a_semantic_change() -> None:
    """Excludes comparing permitted values without comparing how many there are."""
    from vellis.definitions import definition_set_equal
    from vellis.json_value import normalize as as_json

    def permitting(*values: str) -> GraphDefinitionSet:
        return _data_type(
            (
                _property(
                    "tag",
                    value_range=ValueRange(
                        permitted_values=tuple(as_json(each) for each in values)
                    ),
                ),
            )
        )

    assert not definition_set_equal(permitting("a", "b"), permitting("a"))
    assert definition_set_equal(permitting("a", "b"), permitting("b", "a"))


def _link_type(source: tuple[str, ...], target: tuple[str, ...]) -> LinkTypeDefinition:
    return LinkTypeDefinition(
        type_key="worksOn",
        endpoint_constraint=EndpointConstraint(
            permitted_source_type_keys=source,
            permitted_target_type_keys=target,
            description="Who works on what.",
        ),
        description="A working relationship.",
    )


def _with(
    *,
    link_types: tuple[LinkTypeDefinition, ...] = (),
    relationships: tuple[object, ...] = (),
    permitted_anchors: tuple[str, ...] = ("person",),
) -> GraphDefinitionSet:
    return GraphDefinitionSet(
        anchor_types=(PERSON,),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="note",
                permitted_anchor_type_keys=permitted_anchors,
                description="A note.",
            ),
        ),
        link_types=link_types,
        relationship_constraints=relationships,  # pyright: ignore[reportArgumentType]
    )


def _link_rule(
    *,
    link_type_key: str = "worksOn",
    constrained: tuple[str, ...] = ("person",),
    opposite: tuple[str, ...] = ("note",),
) -> LinkMultiplicityConstraint:
    return LinkMultiplicityConstraint(
        link_type_key=link_type_key,
        constrained_end=LinkEnd.SOURCE,
        constrained_endpoint_type_keys=constrained,
        opposite_endpoint_type_keys=opposite,
        lower_bound=0,
        description="A link multiplicity rule.",
    )


def _association_rule(
    *, anchors: tuple[str, ...] = ("person",), data: tuple[str, ...] = ("note",)
) -> DirectAssociationMultiplicityConstraint:
    return DirectAssociationMultiplicityConstraint(
        constrained_end=DirectAssociationEnd.ANCHOR,
        anchor_type_keys=anchors,
        associated_data_type_keys=data,
        lower_bound=0,
        description="A direct-association rule.",
    )


@pytest.mark.parametrize(
    ("definitions", "expected"),
    [
        (_with(link_types=(_link_type((), ("note",)),)), "permits no source type"),
        (_with(link_types=(_link_type(("person",), ()),)), "permits no target type"),
        (
            _with(link_types=(_link_type(("person", "person"), ("note",)),)),
            "more than once",
        ),
        (
            _with(link_types=(_link_type(("ghost",), ("note",)),)),
            "not an active anchor or associated-data type",
        ),
        (
            _with(
                link_types=(_link_type(("person",), ("note",)),),
                relationships=(_link_rule(link_type_key="ghost"),),
            ),
            "unknown link type",
        ),
        (
            _with(
                link_types=(_link_type(("person",), ("note",)),),
                relationships=(_link_rule(constrained=("ghost",)),),
            ),
            "not an\n                            active anchor or associated-data type".replace(
                "\n                            ", " "
            ),
        ),
        (_with(relationships=(_association_rule(anchors=()),)), "names no anchor type"),
        (_with(relationships=(_association_rule(data=()),)), "names no associated-data type"),
        (
            _with(relationships=(_association_rule(anchors=("ghost",)),)),
            "not an active anchor type",
        ),
        (
            _with(relationships=(_association_rule(data=("ghost",)),)),
            "not an active associated-data type",
        ),
        (_with(permitted_anchors=("person", "person")), "more than once"),
    ],
    ids=[
        "endpoint-no-source",
        "endpoint-no-target",
        "endpoint-duplicate",
        "endpoint-unknown-type",
        "link-rule-unknown-link-type",
        "link-rule-unknown-endpoint-type",
        "association-no-anchor-type",
        "association-no-data-type",
        "association-unknown-anchor-type",
        "association-unknown-data-type",
        "permitted-anchor-duplicate",
    ],
)
def test_every_reference_and_membership_rule_is_enforced(
    definitions: GraphDefinitionSet, expected: str
) -> None:
    """Each rule decides whether an owner's starting vocabulary is accepted at all."""
    assert any(expected in each for each in _summaries(definitions))


def test_a_non_numeric_range_bound_is_invalid() -> None:
    from vellis.json_value import normalize as as_json

    constraint = _property(
        "n", json_kind=JsonKind.NUMBER, value_range=ValueRange(lower_bound=as_json("low"))
    )
    assert any("non-numeric lower bound" in each for each in _summaries(_data_type((constraint,))))


def test_an_unencodable_member_name_in_a_permitted_value_is_a_finding() -> None:
    """The whole path: an object-valued permitted value reaches the store through here."""
    from vellis.json_value import JsonValueError

    with pytest.raises(JsonValueError, match="unpaired surrogate"):
        ValueRange(permitted_values=({chr(0xD800): 1},))  # pyright: ignore[reportArgumentType]


def test_the_largest_storable_bound_is_accepted_and_the_next_one_is_not() -> None:
    """Pins the contract between the validity check and the decoder at its boundary.

    The write side must never accept a bound the read side refuses, and must not refuse
    one the read side would accept.
    """
    from vellis.json_value import MAXIMUM_STORED_INTEGER_EXPONENT

    largest = 10**MAXIMUM_STORED_INTEGER_EXPONENT - 1
    accepted = _data_type((_property("s", value_shape=ValueShape(maximum_size=largest)),))
    assert _summaries(accepted) == []

    refused = _data_type((_property("s", value_shape=ValueShape(maximum_size=largest + 1)),))
    assert any("too large to be stored" in each for each in _summaries(refused))


def test_a_deeply_nested_permitted_value_is_refused_before_it_reaches_the_store() -> None:
    """Excludes a definition the validity gate calls valid but the write cannot serialize."""
    from vellis.json_value import MAXIMUM_NESTING_DEPTH, JsonValueError

    deep: object = {"leaf": 1}
    for _ in range(MAXIMUM_NESTING_DEPTH + 5):
        deep = {"a": deep}

    with pytest.raises(JsonValueError, match="nests deeper"):
        ValueRange(permitted_values=(deep,))  # pyright: ignore[reportArgumentType]


def test_an_associated_data_type_may_be_a_permitted_link_endpoint() -> None:
    """Excludes resolving permitted endpoint types against anchor types alone.

    A vocabulary that links two facts together is ordinary, and initialization refuses
    on any finding, so a regression here would stop such an owner from starting at all.
    """
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON,),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="employment",
                permitted_anchor_type_keys=("person",),
                description="An employment fact.",
            ),
        ),
        link_types=(
            LinkTypeDefinition(
                type_key="cites",
                endpoint_constraint=EndpointConstraint(
                    permitted_source_type_keys=("employment",),
                    permitted_target_type_keys=("employment",),
                    description="One fact citing another.",
                ),
                description="A citation.",
            ),
        ),
    )
    assert _summaries(definitions) == []


@pytest.mark.parametrize(
    ("constraint", "expected"),
    [
        (
            _property("s", value_shape=ValueShape(minimum_size=3, maximum_size=2)),
            "inverted size condition",
        ),
        (
            _property(
                "n",
                json_kind=JsonKind.NUMBER,
                value_range=ValueRange(lower_bound=normalize(3), upper_bound=normalize(2)),
            ),
            "inverted numeric range",
        ),
    ],
    ids=["size", "range"],
)
def test_an_inversion_of_exactly_one_is_still_an_inversion(
    constraint: PropertyConstraint, expected: str
) -> None:
    """Excludes an off-by-one that only catches inversions wider than a single step."""
    assert any(expected in each for each in _summaries(_data_type((constraint,))))


def test_a_relationship_label_is_stable_across_declaration_order() -> None:
    """The label lands in a finding's implicated definitions, so it must not vary by run."""
    from vellis.definitions import relationship_label

    forward = _association_rule(anchors=("person", "team", "company"))
    reversed_order = _association_rule(anchors=("company", "person", "team"))
    assert relationship_label(forward) == relationship_label(reversed_order)
    assert "{company,person,team}" in relationship_label(forward)


def test_a_multiplicity_label_names_its_end_in_the_model_s_own_words() -> None:
    """A finding an owner reads should not carry a realization detail.

    The label sits beside type keys that are already their modeled names, so an end
    rendered as its enumeration member is the one part of the identity that stops being
    the owner's vocabulary.
    """
    label = relationship_label(
        DirectAssociationMultiplicityConstraint(
            constrained_end=DirectAssociationEnd.ASSOCIATED_DATA,
            anchor_type_keys=("person",),
            associated_data_type_keys=("person.details",),
            lower_bound=1,
            upper_bound=1,
            description="One each.",
        )
    )

    assert label == "directAssociationMultiplicity:associatedData|{person}|{person.details}"
    assert "DirectAssociationEnd" not in label
