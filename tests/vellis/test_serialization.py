"""Evidence that stored canonical state decodes back to the same canonical meaning.

Durability is only worth the word if what comes back is semantically identical to what
went in. These cases exercise every encoded structure, and each negative case names the
silent loss it would otherwise permit: a dropped pattern, a swapped endpoint role, or a
delta that disappears would all leave the rest of the suite green.
"""

from __future__ import annotations

import pytest

from vellis.canonical import CanonicalState, canonical_state_equal
from vellis.definitions import GraphDefinitionSet, definition_set_equal
from vellis.graph import Graph, graph_equal
from vellis.json_value import JsonValue, loads, normalize
from vellis.serialization import (
    DecodeError,
    decode_canonical_state,
    decode_definition_set,
    decode_graph,
    decode_text,
    encode_canonical_state,
    encode_definition_set,
    encode_graph,
    encode_text,
    unreadable_reason,
)


def _round_trip(state: CanonicalState) -> CanonicalState:
    return decode_canonical_state(decode_text(encode_text(encode_canonical_state(state))))


def test_a_complete_canonical_state_round_trips_through_text(rich_state: CanonicalState) -> None:
    assert canonical_state_equal(_round_trip(rich_state), rich_state)


def test_re_encoding_a_decoded_state_is_byte_stable(rich_state: CanonicalState) -> None:
    """Excludes an encoding whose output depends on dictionary insertion order."""
    once = encode_text(encode_canonical_state(rich_state))
    twice = encode_text(encode_canonical_state(_round_trip(rich_state)))
    assert once == twice


def test_the_graph_round_trips_with_metadata_associations_and_direction(
    rich_graph: Graph,
) -> None:
    decoded = decode_graph(decode_text(encode_text(encode_graph(rich_graph))))
    assert graph_equal(decoded, rich_graph)
    original = rich_graph.associated_data[0]
    restored = decoded.associated_data_object("d-1")
    assert restored is not None
    assert restored.anchor_uuids == original.anchor_uuids
    assert restored.system_metadata.live is False
    assert decoded.anchors[0].system_metadata.members["origin"] == "import"
    link = decoded.link("l-1")
    assert link is not None
    assert (link.source_uuid, link.target_uuid) == ("a-1", "a-2")


def test_endpoint_roles_survive_the_round_trip(rich_definitions: GraphDefinitionSet) -> None:
    """Excludes an encoding that swaps permitted source and target types."""
    decoded = decode_definition_set(
        decode_text(encode_text(encode_definition_set(rich_definitions)))
    )
    constraint = decoded.link_types[0].endpoint_constraint
    assert constraint.permitted_source_type_keys == ("person",)
    assert constraint.permitted_target_type_keys == ("project",)
    assert definition_set_equal(decoded, rich_definitions)


def test_property_rules_survive_the_round_trip(rich_definitions: GraphDefinitionSet) -> None:
    """Excludes dropping a pattern, a shape bound, a range, or a permitted value."""
    decoded = decode_definition_set(
        decode_text(encode_text(encode_definition_set(rich_definitions)))
    )
    properties = {
        constraint.property_name: constraint
        for constraint in decoded.associated_data_types[0].property_constraints
    }
    year = properties["year"]
    assert year.pattern is not None and year.pattern.expression == "[0-9]{4}"
    title = properties["title"]
    assert title.value_shape is not None
    assert (title.value_shape.minimum_size, title.value_shape.maximum_size) == (1, 80)
    rating = properties["rating"]
    assert rating.value_range is not None
    assert rating.value_range.lower_bound == normalize(1)
    assert rating.value_range.upper_bound == normalize(5)
    tag = properties["tag"]
    assert tag.value_range is not None
    assert len(tag.value_range.permitted_values) == 2
    assert properties["title"].required is True
    assert properties["rating"].required is False


def test_multiplicity_constraints_survive_the_round_trip(
    rich_definitions: GraphDefinitionSet,
) -> None:
    decoded = decode_definition_set(
        decode_text(encode_text(encode_definition_set(rich_definitions)))
    )
    assert len(decoded.relationship_constraints) == 2
    assert definition_set_equal(decoded, rich_definitions)


def test_an_in_flight_delta_survives_the_round_trip(rich_state: CanonicalState) -> None:
    """Excludes encoding the delta as absent, which no in-memory comparison would catch."""
    decoded = _round_trip(rich_state)
    assert decoded.definition_delta is not None
    assert rich_state.definition_delta is not None
    assert definition_set_equal(
        decoded.definition_delta.proposed_definitions,
        rich_state.definition_delta.proposed_definitions,
    )


def test_delta_absence_survives_the_round_trip(rich_state: CanonicalState) -> None:
    without = CanonicalState(
        graph=rich_state.graph,
        active_definitions=rich_state.active_definitions,
        revision=rich_state.revision,
        definition_delta=None,
    )
    assert _round_trip(without).definition_delta is None


def test_exact_numeric_text_survives_the_round_trip() -> None:
    """Excludes a float-based encoding that would round 1.50 or lose a large exponent."""
    graph = decode_graph(
        decode_text(
            encode_text(
                encode_graph(
                    Graph(
                        associated_data=(
                            _data_with(
                                {
                                    "exact": loads("1.50"),
                                    "large": loads("1E+400"),
                                    "tiny": loads("0.1"),
                                }
                            ),
                        )
                    )
                )
            )
        )
    )
    properties = graph.associated_data[0].properties
    assert str(properties["exact"]) == "1.50"
    assert properties["large"] == loads("1E+400")
    assert properties["tiny"] == loads("0.1")


def _data_with(properties: dict[str, JsonValue]):
    from vellis.graph import AssociatedDataObject

    return AssociatedDataObject(
        uuid="d-1", type_key="note", anchor_uuids=("a-1",), properties=properties
    )


@pytest.mark.parametrize(
    "text",
    [
        '{"graph":{"anchors":[],"associatedData":[],"links":[]},"activeDefinitions":{'
        '"anchorTypes":[],"associatedDataTypes":[],"linkTypes":[],'
        '"relationshipConstraints":[]},"definitionDelta":null}',
        '{"revision":"nought","graph":{"anchors":[],"associatedData":[],"links":[]},'
        '"activeDefinitions":{"anchorTypes":[],"associatedDataTypes":[],"linkTypes":[],'
        '"relationshipConstraints":[]},"definitionDelta":null}',
        '{"revision":0,"graph":[],"activeDefinitions":{"anchorTypes":[],'
        '"associatedDataTypes":[],"linkTypes":[],"relationshipConstraints":[]},'
        '"definitionDelta":null}',
    ],
    ids=["missing-revision", "non-numeric-revision", "graph-is-not-an-object"],
)
def test_corrupt_stored_text_is_refused_rather_than_reinterpreted(text: str) -> None:
    with pytest.raises(DecodeError):
        decode_canonical_state(decode_text(text))


def test_an_unknown_relationship_kind_is_refused() -> None:
    text = (
        '{"anchorTypes":[],"associatedDataTypes":[],"linkTypes":[],'
        '"relationshipConstraints":[{"kind":"somethingElse","lowerBound":0,'
        '"upperBound":null,"description":"x"}]}'
    )
    with pytest.raises(DecodeError):
        decode_definition_set(decode_text(text))


def test_a_non_integer_revision_is_refused() -> None:
    text = (
        '{"revision":0.5,"graph":{"anchors":[],"associatedData":[],"links":[]},'
        '"activeDefinitions":{"anchorTypes":[],"associatedDataTypes":[],"linkTypes":[],'
        '"relationshipConstraints":[]},"definitionDelta":null}'
    )
    with pytest.raises(DecodeError):
        decode_canonical_state(decode_text(text))


def test_a_number_outside_the_decimal_range_is_a_json_error() -> None:
    """Excludes an arithmetic exception escaping the reader.

    ``InvalidOperation`` is an ``ArithmeticError``, not a ``ValueError``, so a catch
    written for malformed text alone lets this one class of number through untyped.
    """
    from vellis.json_value import JsonValueError

    with pytest.raises(JsonValueError, match="malformed JSON text"):
        loads("1e1000000000000000000")
    with pytest.raises(JsonValueError, match="malformed JSON text"):
        loads('{"a": -1e1000000000000000000}')


def _sample_change():
    from vellis.changes import GraphChange
    from vellis.graph import Anchor, AssociatedDataObject, Link, SystemMetadata

    return GraphChange(
        anchor_upserts=(
            Anchor(
                uuid="a-1",
                type_key="person",
                display_name="Ada",
                system_metadata=SystemMetadata(members={"live": True, "origin": "import"}),
            ),
        ),
        associated_data_upserts=(
            AssociatedDataObject(
                uuid="d-1",
                type_key="note",
                anchor_uuids=("a-1", "a-2"),
                properties={"title": normalize("First"), "rating": normalize(4)},
            ),
        ),
        link_upserts=(Link(uuid="l-1", type_key="worksOn", source_uuid="a-1", target_uuid="a-2"),),
        anchor_removals=("a-9",),
        associated_data_removals=("d-9",),
        link_removals=("l-9",),
    )


def test_a_graph_change_round_trips_with_every_command_kind() -> None:
    """A transition is only replay-sufficient if its change survives storage intact."""
    from vellis.serialization import decode_graph_change, encode_graph_change

    original = _sample_change()
    restored = decode_graph_change(decode_text(encode_text(encode_graph_change(original))))
    assert restored == original


def test_a_canonical_change_round_trips_with_its_disposition() -> None:
    from vellis.canonical import CanonicalChange, DefinitionDeltaDisposition
    from vellis.serialization import decode_canonical_change, encode_canonical_change

    original = CanonicalChange(graph_change=_sample_change())
    restored = decode_canonical_change(decode_text(encode_text(encode_canonical_change(original))))
    assert restored.graph_change == original.graph_change
    assert restored.replacement_graph is None
    assert restored.active_definitions is None
    assert restored.delta_disposition is DefinitionDeltaDisposition.UNCHANGED


def test_a_lossy_but_decodable_encoding_is_refused_before_it_is_committed(
    rich_state: CanonicalState, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Excludes screening decodability alone.

    A revision check cannot see the one failure that matters here: a form that reads back
    cleanly and means something else. That state would be committed and every later read
    would return it, with nothing left to compare against.
    """
    assert unreadable_reason(rich_state) is None

    import vellis.serialization as serialization

    original = serialization.encode_canonical_state

    def lose_the_delta(state: CanonicalState) -> JsonValue:
        encoded = original(state)
        assert isinstance(encoded, dict)
        return {**encoded, "definitionDelta": None}

    monkeypatch.setattr(serialization, "encode_canonical_state", lose_the_delta)
    reason = unreadable_reason(rich_state)

    assert reason is not None
    assert "same canonical state" in reason
