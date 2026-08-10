"""Shared canonical fixtures.

The rich fixtures exercise every structure ``RTG::'Graph Definition Set'`` and
``RTG::Graph`` can carry: required and optional properties of each constrained JSON
kind, a value shape with both bounds, an inclusive numeric range, permitted values, an
RE2 pattern, an endpoint constraint whose source and target differ, both multiplicity
constraint kinds, non-default system metadata, nested JSON, and an in-flight definition
delta. A fixture that only carried the trivial cases would let a whole encoding branch
or comparison be wrong without any test noticing.
"""

from __future__ import annotations

import pytest

from vellis.canonical import CanonicalState, DefinitionDelta
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
from vellis.graph import Anchor, AssociatedDataObject, Graph, Link, SystemMetadata
from vellis.json_value import JsonKind, JsonValue, normalize


def build_rich_definitions() -> GraphDefinitionSet:
    """Return a definition set that uses every structure the model defines."""
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
                    PropertyConstraint(
                        property_name="tag",
                        required=False,
                        json_kind=JsonKind.STRING,
                        description="One of the permitted tags.",
                        value_range=ValueRange(
                            permitted_values=(normalize("green"), normalize("amber"))
                        ),
                    ),
                    PropertyConstraint(
                        property_name="details",
                        required=False,
                        json_kind=JsonKind.OBJECT,
                        description="Free-form nested detail.",
                        value_shape=ValueShape(maximum_size=8),
                    ),
                ),
                description="A note about an anchor.",
            ),
        ),
        link_types=(
            LinkTypeDefinition(
                type_key="worksOn",
                endpoint_constraint=EndpointConstraint(
                    permitted_source_type_keys=("person",),
                    permitted_target_type_keys=("project",),
                    description="Who works on what.",
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
                upper_bound=3,
                description="How many projects one person may work on.",
            ),
            DirectAssociationMultiplicityConstraint(
                constrained_end=DirectAssociationEnd.ANCHOR,
                anchor_type_keys=("person",),
                associated_data_type_keys=("note",),
                lower_bound=0,
                upper_bound=None,
                description="How many notes one person may carry.",
            ),
        ),
    )


def _note_properties() -> dict[str, JsonValue]:
    return {
        "title": normalize("First meeting"),
        "rating": normalize(4),
        "year": normalize("2026"),
        "tag": normalize("green"),
        "details": normalize({"where": "office", "attendees": [1, 2], "notes": None}),
    }


def build_rich_graph() -> Graph:
    """Return a graph that conforms to :func:`build_rich_definitions`."""
    return Graph(
        anchors=(
            Anchor(
                uuid="a-1",
                type_key="person",
                display_name="Ada",
                system_metadata=SystemMetadata(members={"live": True, "origin": "import"}),
            ),
            Anchor(uuid="a-2", type_key="project", display_name="Orbit"),
        ),
        associated_data=(
            AssociatedDataObject(
                uuid="d-1",
                type_key="note",
                anchor_uuids=("a-1", "a-2"),
                properties=_note_properties(),
                system_metadata=SystemMetadata(members={"live": False}),
            ),
        ),
        links=(Link(uuid="l-1", type_key="worksOn", source_uuid="a-1", target_uuid="a-2"),),
    )


def build_rich_state(revision: int = 7) -> CanonicalState:
    """Return a canonical state carrying a graph, definitions, and an in-flight delta."""
    definitions = build_rich_definitions()
    proposed = GraphDefinitionSet(
        anchor_types=(
            *definitions.anchor_types,
            AnchorTypeDefinition(type_key="team", description="A group of people."),
        ),
        associated_data_types=definitions.associated_data_types,
        link_types=definitions.link_types,
        relationship_constraints=definitions.relationship_constraints,
    )
    return CanonicalState(
        graph=build_rich_graph(),
        active_definitions=definitions,
        revision=revision,
        definition_delta=DefinitionDelta(proposed_definitions=proposed),
    )


@pytest.fixture
def rich_definitions() -> GraphDefinitionSet:
    return build_rich_definitions()


@pytest.fixture
def rich_graph() -> Graph:
    return build_rich_graph()


@pytest.fixture
def rich_state() -> CanonicalState:
    return build_rich_state()
