"""Evidence for ``VellisVerification::definitionDiscovery`` at current state.

The verification case starts an agent with no graph knowledge, so these cases follow the
same order: read the whole anchor vocabulary, then read a focused neighborhood, then show
that comparing the two evaluated revisions is what exposes a stale summary. Historical
selection belongs to the slice that can resolve a revision and is not exercised here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.vellis.oracle import materialize_replay, materialize_state
from tests.vellis.semantic_state import semantic_state_equal
from vellis.canonical import Provenance
from vellis.changes import GraphChange
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
)
from vellis.discovery import DefinitionInspectionRequest
from vellis.graph import Anchor
from vellis.json_value import JsonKind
from vellis.outcomes import OperationStatus
from vellis.system import RTGSystem

PERSON = AnchorTypeDefinition(type_key="person", description="A person the owner knows.")
PROJECT = AnchorTypeDefinition(type_key="project", description="A piece of work.")
RECIPE = AnchorTypeDefinition(type_key="recipe", description="Something to cook.")

NOTE = AssociatedDataTypeDefinition(
    type_key="note",
    permitted_anchor_type_keys=("person",),
    property_constraints=(
        PropertyConstraint(
            property_name="title",
            required=True,
            json_kind=JsonKind.STRING,
            description="What the note is about.",
        ),
    ),
    description="A note about a person.",
)
STEP = AssociatedDataTypeDefinition(
    type_key="step",
    permitted_anchor_type_keys=("recipe",),
    description="One step of a recipe.",
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
CITES = LinkTypeDefinition(
    type_key="cites",
    endpoint_constraint=EndpointConstraint(
        permitted_source_type_keys=("note",),
        permitted_target_type_keys=("note",),
        description="One note citing another.",
    ),
    description="A citation between notes.",
)
FOLLOWS = LinkTypeDefinition(
    type_key="follows",
    endpoint_constraint=EndpointConstraint(
        permitted_source_type_keys=("step",),
        permitted_target_type_keys=("step",),
        description="Step order.",
    ),
    description="An ordering between steps.",
)

PERSON_NOTES = DirectAssociationMultiplicityConstraint(
    constrained_end=DirectAssociationEnd.ANCHOR,
    anchor_type_keys=("person",),
    associated_data_type_keys=("note",),
    lower_bound=0,
    upper_bound=None,
    description="How many notes one person may carry.",
)
RECIPE_STEPS = DirectAssociationMultiplicityConstraint(
    constrained_end=DirectAssociationEnd.ANCHOR,
    anchor_type_keys=("recipe",),
    associated_data_type_keys=("step",),
    lower_bound=1,
    upper_bound=None,
    description="A recipe has at least one step.",
)
WORK_LIMIT = LinkMultiplicityConstraint(
    link_type_key="worksOn",
    constrained_end=LinkEnd.SOURCE,
    constrained_endpoint_type_keys=("person",),
    opposite_endpoint_type_keys=("project",),
    lower_bound=0,
    upper_bound=3,
    description="How many projects one person may work on.",
)

VOCABULARY = GraphDefinitionSet(
    anchor_types=(PERSON, PROJECT, RECIPE),
    associated_data_types=(NOTE, STEP),
    link_types=(WORKS_ON, CITES, FOLLOWS),
    relationship_constraints=(PERSON_NOTES, RECIPE_STEPS, WORK_LIMIT),
)


def _system(tmp_path: Path) -> RTGSystem:
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    assert system.initialize_fresh(
        VOCABULARY,
        provenance=Provenance(initiator="owner"),
        initialization_summary="a fresh start",
    ).accepted
    return system


# --- The shallow read ---------------------------------------------------------------


def test_a_cold_agent_reads_the_whole_anchor_vocabulary(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        result = system.definition_summary()
        assert result.status is OperationStatus.ACCEPTED
        assert [each.type_key for each in result.anchor_types] == ["person", "project", "recipe"]
        assert [each.description for each in result.anchor_types] == [
            "A person the owner knows.",
            "A piece of work.",
            "Something to cook.",
        ]
        assert result.evaluated_revision == 0
        assert result.delta_present is False
    finally:
        system.close()


def test_the_summary_names_each_anchor_type_exactly_once(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        keys = [each.type_key for each in system.definition_summary().anchor_types]
        assert len(keys) == len(set(keys))
        assert set(keys) == {each.type_key for each in VOCABULARY.anchor_types}
    finally:
        system.close()


def test_the_summary_shows_only_anchor_types(tmp_path: Path) -> None:
    """A shallow read is anchors; data and link types are what inspection is for."""
    system = _system(tmp_path)
    try:
        keys = {each.type_key for each in system.definition_summary().anchor_types}
        assert not keys & {"note", "step", "worksOn", "cites", "follows"}
    finally:
        system.close()


def test_a_summary_that_cannot_be_returned_completely_returns_nothing(tmp_path: Path) -> None:
    """Excludes reporting a partial vocabulary, or metadata without one."""
    system = _system(tmp_path)
    try:
        system.store._connection.execute("DROP TABLE state_head")  # noqa: SLF001
        result = system.definition_summary()
        assert result.status is OperationStatus.FAILED
        assert result.anchor_types == ()
        assert result.evaluated_revision is None
        assert result.delta_present is None
        assert result.findings
    finally:
        system.close()


# --- The focused read ---------------------------------------------------------------


def test_a_neighborhood_is_complete_for_its_anchor(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        result = system.inspect_definitions(DefinitionInspectionRequest(("person",)))
        assert result.status is OperationStatus.ACCEPTED
        assert result.evaluated_revision == 0
        assert len(result.anchor_details) == 1
        detail = result.anchor_details[0]
        assert detail.anchor_type == PERSON
        assert {each.type_key for each in detail.associated_data_types} == {"note"}
        assert {each.type_key for each in detail.link_types} == {"worksOn", "cites"}
        assert set(detail.relationship_constraints) == {PERSON_NOTES, WORK_LIMIT}
    finally:
        system.close()


def test_a_neighborhood_omits_unrelated_definitions(tmp_path: Path) -> None:
    """Excludes returning the whole definition set under a selected anchor's name."""
    system = _system(tmp_path)
    try:
        detail = system.inspect_definitions(
            DefinitionInspectionRequest(("recipe",))
        ).anchor_details[0]
        assert {each.type_key for each in detail.associated_data_types} == {"step"}
        assert {each.type_key for each in detail.link_types} == {"follows"}
        assert set(detail.relationship_constraints) == {RECIPE_STEPS}
    finally:
        system.close()


def test_a_link_role_reached_through_associated_data_is_included(tmp_path: Path) -> None:
    """``cites`` never mentions ``person``; it is in the neighborhood through ``note``."""
    system = _system(tmp_path)
    try:
        detail = system.inspect_definitions(
            DefinitionInspectionRequest(("person",))
        ).anchor_details[0]
        assert "cites" in {each.type_key for each in detail.link_types}
    finally:
        system.close()


def test_property_and_endpoint_rules_ride_along_inside_their_definitions(
    tmp_path: Path,
) -> None:
    system = _system(tmp_path)
    try:
        detail = system.inspect_definitions(
            DefinitionInspectionRequest(("person",))
        ).anchor_details[0]
        note = next(each for each in detail.associated_data_types if each.type_key == "note")
        assert [each.property_name for each in note.property_constraints] == ["title"]
        works_on = next(each for each in detail.link_types if each.type_key == "worksOn")
        assert works_on.endpoint_constraint.permitted_target_type_keys == ("project",)
        assert note.description and works_on.description
    finally:
        system.close()


def test_several_anchors_are_answered_in_the_order_selected(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        result = system.inspect_definitions(
            DefinitionInspectionRequest(("recipe", "person", "project"))
        )
        assert [each.anchor_type.type_key for each in result.anchor_details] == [
            "recipe",
            "person",
            "project",
        ]
    finally:
        system.close()


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        (("person", "ghost"), "not an active anchor type"),
        (("person", "person"), "more than once"),
        ((), "names no anchor type"),
        (("note",), "not an active anchor type"),
    ],
    ids=["unknown", "duplicate", "empty", "not-an-anchor-type"],
)
def test_an_unanswerable_selection_returns_findings_and_no_details(
    tmp_path: Path, keys: tuple[str, ...], expected: str
) -> None:
    """Excludes returning the details that happened to resolve alongside a finding."""
    system = _system(tmp_path)
    try:
        result = system.inspect_definitions(DefinitionInspectionRequest(keys))
        assert result.status is OperationStatus.REJECTED
        assert any(expected in each.summary for each in result.findings), result.findings
        assert result.anchor_details == ()
        assert result.evaluated_revision is None
    finally:
        system.close()


# --- Detecting that the ground moved -------------------------------------------------


def test_summary_and_inspection_agree_when_nothing_intervened(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        summary = system.definition_summary()
        inspection = system.inspect_definitions(DefinitionInspectionRequest(("person",)))
        assert summary.evaluated_revision == inspection.evaluated_revision
    finally:
        system.close()


def test_a_revision_that_moved_between_the_two_reads_is_visible_to_the_caller(
    tmp_path: Path,
) -> None:
    """Excludes an evaluated revision a caller cannot use to detect staleness.

    Comparing the two revisions is the whole mechanism the model offers in place of a
    session or a lock, so it has to work without one. Here the revision moves because of
    a graph change; the definition-change variant the verification case names cannot be
    staged until definition activation exists, and is evidenced by the slice that closes
    this authority.
    """
    system = _system(tmp_path)
    try:
        stale = system.definition_summary()
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-1", "person", "Ada"),)),
            provenance=Provenance(initiator="owner"),
        ).accepted
        inspection = system.inspect_definitions(DefinitionInspectionRequest(("person",)))

        assert stale.evaluated_revision != inspection.evaluated_revision

        # Repeating discovery succeeds, with no session to re-establish.
        fresh = system.definition_summary()
        assert fresh.evaluated_revision == inspection.evaluated_revision
    finally:
        system.close()


# --- Non-effects --------------------------------------------------------------------


def test_discovery_neither_changes_state_nor_reads_canonical_history(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        before = materialize_state(system)
        records = system.store.canonical_record_count()
        system.store.reset_instrumentation()
        system.definition_summary()
        system.inspect_definitions(DefinitionInspectionRequest(("person", "recipe")))
        system.inspect_definitions(DefinitionInspectionRequest(("ghost",)))
        assert system.store.record_reads == 0
        assert semantic_state_equal(materialize_state(system), before)
        assert system.store.canonical_record_count() == records
    finally:
        system.close()


def test_an_empty_vocabulary_summarizes_as_empty(tmp_path: Path) -> None:
    """A blank system is a normal accepted answer, not a failure."""
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        assert system.initialize_fresh(
            GraphDefinitionSet(),
            provenance=Provenance(initiator="owner"),
            initialization_summary="blank",
        ).accepted
        result = system.definition_summary()
        assert result.status is OperationStatus.ACCEPTED
        assert result.anchor_types == ()
        assert result.evaluated_revision == 0
        assert result.delta_present is False
    finally:
        system.close()


# --- What belongs in a neighborhood, exactly ----------------------------------------

BILLED_TO = LinkTypeDefinition(
    type_key="billedTo",
    endpoint_constraint=EndpointConstraint(
        permitted_source_type_keys=("person",),
        permitted_target_type_keys=("invoiceLine",),
        description="Who a line is billed to.",
    ),
    description="A billing relationship.",
)
INVOICE_LINE = AssociatedDataTypeDefinition(
    type_key="invoiceLine",
    permitted_anchor_type_keys=("project",),
    property_constraints=(
        PropertyConstraint(
            property_name="amount",
            required=True,
            json_kind=JsonKind.NUMBER,
            description="How much.",
        ),
    ),
    description="One line of an invoice.",
)


def _with(definitions: GraphDefinitionSet, tmp_path: Path) -> RTGSystem:
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    outcome = system.initialize_fresh(
        definitions,
        provenance=Provenance(initiator="owner"),
        initialization_summary="a fresh start",
    )
    assert outcome.accepted, outcome.findings
    return system


def _detail(system: RTGSystem, type_key: str):
    result = system.inspect_definitions(DefinitionInspectionRequest((type_key,)))
    assert result.accepted, result.findings
    return result.anchor_details[0]


def test_associated_data_at_the_far_end_of_a_link_is_included(tmp_path: Path) -> None:
    """Excludes handing an agent a link type it has no way to fill in.

    ``invoiceLine`` never grounds ``person``; it is reachable only as the target of a
    link ``person`` may be the source of, and without its property rules the agent
    cannot compose a conforming change for that link.
    """
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON, PROJECT),
        associated_data_types=(NOTE, INVOICE_LINE),
        link_types=(BILLED_TO,),
    )
    system = _with(definitions, tmp_path)
    try:
        detail = _detail(system, "person")
        assert {each.type_key for each in detail.link_types} == {"billedTo"}
        data_types = {each.type_key: each for each in detail.associated_data_types}
        assert set(data_types) == {"note", "invoiceLine"}
        assert [each.property_name for each in data_types["invoiceLine"].property_constraints] == [
            "amount"
        ]
    finally:
        system.close()


def test_a_link_type_is_found_from_either_end(tmp_path: Path) -> None:
    """Excludes matching only the source side; an anchor may participate as a target."""
    system = _system(tmp_path)
    try:
        assert {each.type_key for each in _detail(system, "project").link_types} == {"worksOn"}
        assert "worksOn" in {each.type_key for each in _detail(system, "person").link_types}
    finally:
        system.close()


def test_a_link_multiplicity_rule_that_names_the_anchor_is_included(tmp_path: Path) -> None:
    """Excludes filtering rules by the link type's permitted endpoints.

    A multiplicity rule may name an endpoint type the link type itself does not permit
    there. It still rejects every graph containing that anchor, so an agent that never
    sees it cannot understand why its change was refused.
    """
    owns = LinkTypeDefinition(
        type_key="owns",
        endpoint_constraint=EndpointConstraint(
            permitted_source_type_keys=("project",),
            permitted_target_type_keys=("project",),
            description="Ownership.",
        ),
        description="An ownership relationship.",
    )
    rule = LinkMultiplicityConstraint(
        link_type_key="owns",
        constrained_end=LinkEnd.SOURCE,
        constrained_endpoint_type_keys=("person",),
        opposite_endpoint_type_keys=("project",),
        lower_bound=1,
        upper_bound=None,
        description="Every person owns at least one project.",
    )
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON, PROJECT),
        associated_data_types=(NOTE,),
        link_types=(owns,),
        relationship_constraints=(rule,),
    )
    system = _with(definitions, tmp_path)
    try:
        assert rule in _detail(system, "person").relationship_constraints
    finally:
        system.close()


def test_a_link_multiplicity_rule_about_other_types_is_excluded(tmp_path: Path) -> None:
    """The counterpart: participation is the criterion, so non-participation excludes."""
    mentions = LinkTypeDefinition(
        type_key="mentions",
        endpoint_constraint=EndpointConstraint(
            permitted_source_type_keys=("person", "project"),
            permitted_target_type_keys=("project",),
            description="Who mentions what.",
        ),
        description="A mention.",
    )
    elsewhere = LinkMultiplicityConstraint(
        link_type_key="mentions",
        constrained_end=LinkEnd.SOURCE,
        constrained_endpoint_type_keys=("project",),
        opposite_endpoint_type_keys=("project",),
        lower_bound=0,
        upper_bound=2,
        description="A project mentions at most two projects.",
    )
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON, PROJECT),
        associated_data_types=(NOTE,),
        link_types=(mentions,),
        relationship_constraints=(elsewhere,),
    )
    system = _with(definitions, tmp_path)
    try:
        detail = _detail(system, "person")
        assert "mentions" in {each.type_key for each in detail.link_types}
        assert elsewhere not in detail.relationship_constraints
    finally:
        system.close()


def test_another_anchors_association_rule_is_excluded_even_on_a_shared_data_type(
    tmp_path: Path,
) -> None:
    """Excludes over-constraining an anchor with a rule that governs a different one.

    Both anchors carry notes, but a rule that every project carries a note says nothing
    about a person.
    """
    shared_note = AssociatedDataTypeDefinition(
        type_key="note",
        permitted_anchor_type_keys=("person", "project"),
        description="A note about either.",
    )
    project_rule = DirectAssociationMultiplicityConstraint(
        constrained_end=DirectAssociationEnd.ANCHOR,
        anchor_type_keys=("project",),
        associated_data_type_keys=("note",),
        lower_bound=1,
        upper_bound=None,
        description="Every project carries at least one note.",
    )
    person_rule = DirectAssociationMultiplicityConstraint(
        constrained_end=DirectAssociationEnd.ANCHOR,
        anchor_type_keys=("person",),
        associated_data_type_keys=("note",),
        lower_bound=0,
        upper_bound=5,
        description="A person carries at most five notes.",
    )
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON, PROJECT),
        associated_data_types=(shared_note,),
        relationship_constraints=(project_rule, person_rule),
    )
    system = _with(definitions, tmp_path)
    try:
        person = _detail(system, "person")
        assert person.relationship_constraints == (person_rule,)
        project = _detail(system, "project")
        assert project.relationship_constraints == (project_rule,)
    finally:
        system.close()


def test_a_rule_naming_the_anchor_at_the_data_end_is_included(tmp_path: Path) -> None:
    """The constrained end does not change whose neighborhood a rule belongs to."""
    at_data_end = DirectAssociationMultiplicityConstraint(
        constrained_end=DirectAssociationEnd.ASSOCIATED_DATA,
        anchor_type_keys=("person",),
        associated_data_type_keys=("note",),
        lower_bound=1,
        upper_bound=1,
        description="Every note is grounded by exactly one person.",
    )
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON,),
        associated_data_types=(NOTE,),
        relationship_constraints=(at_data_end,),
    )
    system = _with(definitions, tmp_path)
    try:
        assert _detail(system, "person").relationship_constraints == (at_data_end,)
    finally:
        system.close()


# --- The neighborhood is closed over what its rules name ----------------------------


def test_a_rule_brings_the_link_type_it_names_with_it(tmp_path: Path) -> None:
    """Excludes returning a rule whose subject the agent cannot resolve.

    The rule names ``owns``, but ``owns`` permits neither endpoint as ``person``, so
    endpoint matching alone would leave the agent reading a bound on a link type it has
    no definition for.
    """
    owns = LinkTypeDefinition(
        type_key="owns",
        endpoint_constraint=EndpointConstraint(
            permitted_source_type_keys=("project",),
            permitted_target_type_keys=("project",),
            description="Ownership.",
        ),
        description="An ownership relationship.",
    )
    rule = LinkMultiplicityConstraint(
        link_type_key="owns",
        constrained_end=LinkEnd.SOURCE,
        constrained_endpoint_type_keys=("person",),
        opposite_endpoint_type_keys=("project",),
        lower_bound=1,
        upper_bound=None,
        description="Every person owns at least one project.",
    )
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON, PROJECT),
        associated_data_types=(NOTE,),
        link_types=(owns,),
        relationship_constraints=(rule,),
    )
    system = _with(definitions, tmp_path)
    try:
        detail = _detail(system, "person")
        assert rule in detail.relationship_constraints
        assert owns in detail.link_types
    finally:
        system.close()


def test_a_rule_brings_the_associated_data_types_it_names_with_it(tmp_path: Path) -> None:
    """Excludes naming a data type in a rule while withholding its property rules."""
    secret = AssociatedDataTypeDefinition(
        type_key="secret",
        permitted_anchor_type_keys=("project",),
        property_constraints=(
            PropertyConstraint(
                property_name="value",
                required=True,
                json_kind=JsonKind.STRING,
                description="The secret itself.",
            ),
        ),
        description="Something private.",
    )
    rule = DirectAssociationMultiplicityConstraint(
        constrained_end=DirectAssociationEnd.ANCHOR,
        anchor_type_keys=("person",),
        associated_data_type_keys=("secret",),
        lower_bound=1,
        upper_bound=None,
        description="Every person holds at least one secret.",
    )
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON, PROJECT),
        associated_data_types=(NOTE, secret),
        relationship_constraints=(rule,),
    )
    system = _with(definitions, tmp_path)
    try:
        detail = _detail(system, "person")
        assert rule in detail.relationship_constraints
        data_types = {each.type_key: each for each in detail.associated_data_types}
        assert "secret" in data_types
        assert [each.property_name for each in data_types["secret"].property_constraints] == [
            "value"
        ]
    finally:
        system.close()


def test_a_rule_counted_at_the_data_end_binds_every_object_of_that_type(
    tmp_path: Path,
) -> None:
    """Excludes scoping both ends of an association rule by its named anchor types.

    Counted at the data end the rule runs over every note, so it binds the notes this
    anchor grounds even though it names a different anchor — and the agent's change is
    refused by it.
    """
    shared_note = AssociatedDataTypeDefinition(
        type_key="note",
        permitted_anchor_type_keys=("person", "project"),
        description="A note about either.",
    )
    at_data_end = DirectAssociationMultiplicityConstraint(
        constrained_end=DirectAssociationEnd.ASSOCIATED_DATA,
        anchor_type_keys=("project",),
        associated_data_type_keys=("note",),
        lower_bound=1,
        upper_bound=None,
        description="Every note is grounded by at least one project.",
    )
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON, PROJECT),
        associated_data_types=(shared_note,),
        relationship_constraints=(at_data_end,),
    )
    system = _with(definitions, tmp_path)
    try:
        assert at_data_end in _detail(system, "person").relationship_constraints
    finally:
        system.close()


def test_a_link_rule_reaching_the_anchor_only_through_its_data_type_is_included(
    tmp_path: Path,
) -> None:
    """Excludes matching a rule's participants against the anchor key alone."""
    rule = LinkMultiplicityConstraint(
        link_type_key="cites",
        constrained_end=LinkEnd.SOURCE,
        constrained_endpoint_type_keys=("note",),
        opposite_endpoint_type_keys=("note",),
        lower_bound=0,
        upper_bound=2,
        description="A note cites at most two notes.",
    )
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON,),
        associated_data_types=(NOTE,),
        link_types=(CITES,),
        relationship_constraints=(rule,),
    )
    system = _with(definitions, tmp_path)
    try:
        detail = _detail(system, "person")
        assert rule in detail.relationship_constraints
        assert CITES in detail.link_types
    finally:
        system.close()


def test_a_neighborhood_names_each_definition_once(tmp_path: Path) -> None:
    """Excludes listing a data type twice when it is both grounding and referenced."""
    system = _system(tmp_path)
    try:
        detail = _detail(system, "person")
        keys = [each.type_key for each in detail.associated_data_types]
        assert len(keys) == len(set(keys))
        link_keys = [each.type_key for each in detail.link_types]
        assert len(link_keys) == len(set(link_keys))
    finally:
        system.close()


def test_an_inspection_that_cannot_be_answered_returns_no_details(tmp_path: Path) -> None:
    """Excludes reporting an unreadable RTG as an anchor with no rules.

    An accepted empty neighborhood and an unanswerable one look identical to a caller
    unless the status distinguishes them — and a cold agent that reads the first as the
    second composes a change against no constraints at all.
    """
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        result = system.inspect_definitions(DefinitionInspectionRequest(("person",)))
        assert result.status is OperationStatus.FAILED
        assert result.findings
        assert result.anchor_details == ()
        assert result.evaluated_revision is None
        assert result.request.anchor_type_keys == ("person",)
    finally:
        system.close()


def test_an_inspection_against_an_unreadable_store_reports_rather_than_raises(
    tmp_path: Path,
) -> None:
    system = _system(tmp_path)
    try:
        system.store._connection.execute("DROP TABLE state_head")  # noqa: SLF001
        result = system.inspect_definitions(DefinitionInspectionRequest(("person",)))
        assert result.status is OperationStatus.FAILED
        assert result.anchor_details == ()
        assert result.evaluated_revision is None
    finally:
        system.close()


def test_a_link_rule_brings_the_data_types_at_its_ends_with_it(tmp_path: Path) -> None:
    """The last closure branch: a link rule's participating types are definitions too.

    The rule bounds ``owns`` links from ``person`` to ``invoiceLine``, but ``owns``
    permits neither type at either end, so nothing else in the derivation reaches
    ``invoiceLine`` — leaving the agent a bound it cannot act on.
    """
    invoice_line = AssociatedDataTypeDefinition(
        type_key="invoiceLine",
        permitted_anchor_type_keys=("project",),
        property_constraints=(
            PropertyConstraint(
                property_name="amount",
                required=True,
                json_kind=JsonKind.NUMBER,
                description="How much.",
            ),
        ),
        description="One line of an invoice.",
    )
    owns = LinkTypeDefinition(
        type_key="owns",
        endpoint_constraint=EndpointConstraint(
            permitted_source_type_keys=("project",),
            permitted_target_type_keys=("project",),
            description="Ownership.",
        ),
        description="An ownership relationship.",
    )
    rule = LinkMultiplicityConstraint(
        link_type_key="owns",
        constrained_end=LinkEnd.SOURCE,
        constrained_endpoint_type_keys=("person",),
        opposite_endpoint_type_keys=("invoiceLine",),
        lower_bound=0,
        upper_bound=1,
        description="A person owns at most one invoice line.",
    )
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON, PROJECT),
        associated_data_types=(NOTE, invoice_line),
        link_types=(owns,),
        relationship_constraints=(rule,),
    )
    system = _with(definitions, tmp_path)
    try:
        detail = _detail(system, "person")
        assert rule in detail.relationship_constraints
        data_types = {each.type_key: each for each in detail.associated_data_types}
        assert "invoiceLine" in data_types
        assert [each.property_name for each in data_types["invoiceLine"].property_constraints] == [
            "amount"
        ]
    finally:
        system.close()


def test_a_link_rule_reaching_the_anchor_only_at_its_opposite_end_is_included(
    tmp_path: Path,
) -> None:
    """Excludes matching a link rule on its constrained end alone.

    Capping fan-in is written this way: the rule is constrained on the target and names
    the anchor as the opposite end. It refuses a link the agent creates, so the agent has
    to be able to see it.
    """
    rule = LinkMultiplicityConstraint(
        link_type_key="worksOn",
        constrained_end=LinkEnd.TARGET,
        constrained_endpoint_type_keys=("project",),
        opposite_endpoint_type_keys=("person",),
        lower_bound=0,
        upper_bound=1,
        description="At most one person works on a project.",
    )
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON, PROJECT),
        associated_data_types=(NOTE,),
        link_types=(WORKS_ON,),
        relationship_constraints=(rule,),
    )
    system = _with(definitions, tmp_path)
    try:
        assert rule in _detail(system, "person").relationship_constraints

        # And the rule is the one that refuses the agent's second link.
        from vellis.graph import Link

        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(
                    Anchor("a-1", "person", "Ada"),
                    Anchor("a-2", "person", "Grace"),
                    Anchor("p-1", "project", "Orbit"),
                ),
                link_upserts=(Link("l-1", "worksOn", "a-1", "p-1"),),
            ),
            provenance=Provenance(initiator="owner"),
        ).accepted
        refused = system.apply_graph_change(
            GraphChange(link_upserts=(Link("l-2", "worksOn", "a-2", "p-1"),)),
            provenance=Provenance(initiator="owner"),
        )
        assert refused.status is OperationStatus.REJECTED
        assert any("target end, outside 0..1" in each.summary for each in refused.findings)
    finally:
        system.close()


def test_a_link_rule_brings_the_data_types_at_its_constrained_end_too(
    tmp_path: Path,
) -> None:
    """The mirror of the opposite-end closure: both ends resolve, not just one."""
    invoice_line = AssociatedDataTypeDefinition(
        type_key="invoiceLine",
        permitted_anchor_type_keys=("project",),
        property_constraints=(
            PropertyConstraint(
                property_name="amount",
                required=True,
                json_kind=JsonKind.NUMBER,
                description="How much.",
            ),
        ),
        description="One line of an invoice.",
    )
    owns = LinkTypeDefinition(
        type_key="owns",
        endpoint_constraint=EndpointConstraint(
            permitted_source_type_keys=("project",),
            permitted_target_type_keys=("project",),
            description="Ownership.",
        ),
        description="An ownership relationship.",
    )
    rule = LinkMultiplicityConstraint(
        link_type_key="owns",
        constrained_end=LinkEnd.SOURCE,
        constrained_endpoint_type_keys=("invoiceLine",),
        opposite_endpoint_type_keys=("person",),
        lower_bound=0,
        upper_bound=1,
        description="An invoice line owns at most one thing belonging to a person.",
    )
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON, PROJECT),
        associated_data_types=(NOTE, invoice_line),
        link_types=(owns,),
        relationship_constraints=(rule,),
    )
    system = _with(definitions, tmp_path)
    try:
        detail = _detail(system, "person")
        assert rule in detail.relationship_constraints
        assert "invoiceLine" in {each.type_key for each in detail.associated_data_types}
    finally:
        system.close()


def test_the_summary_reports_a_delta_that_is_present(tmp_path: Path) -> None:
    """Excludes a delta-presence flag that is always false.

    The shallow read reports proposal presence without returning a whole proposal.
    """
    from vellis.governance import DefinitionChange

    system = _system(tmp_path)
    try:
        assert system.definition_summary().delta_present is False

        state = materialize_state(system)
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(AnchorTypeDefinition("team", "A group."),)),
            provenance=Provenance(initiator="owner"),
        )

        result = system.definition_summary()
        assert result.accepted
        assert result.delta_present is True
        assert result.evaluated_revision == state.revision + 1
        # The active vocabulary is unchanged: a proposal is not an activation.
        assert {each.type_key for each in result.anchor_types} == {
            each.type_key for each in VOCABULARY.anchor_types
        }
        # And replay agrees, so the staged delta is really in the ledger.
        assert semantic_state_equal(materialize_state(system), materialize_replay(system))
    finally:
        system.close()


def test_an_anchor_grounded_by_several_data_types_gets_all_of_them(tmp_path: Path) -> None:
    """Excludes a derivation that keeps only one of an anchor's grounding data types.

    Every other fixture here grounds its anchor in exactly one data type, which would
    let a truncation go unnoticed. This anchor has two, and the second one carries a
    property rule, a link type reachable only through it, and a data-end rule about it —
    each of which the agent needs and none of which anything else in the derivation
    reaches.
    """
    address = AssociatedDataTypeDefinition(
        type_key="address",
        permitted_anchor_type_keys=("person",),
        property_constraints=(
            PropertyConstraint(
                property_name="city",
                required=True,
                json_kind=JsonKind.STRING,
                description="Which city.",
            ),
        ),
        description="Where a person lives.",
    )
    delivers_to = LinkTypeDefinition(
        type_key="deliversTo",
        endpoint_constraint=EndpointConstraint(
            permitted_source_type_keys=("address",),
            permitted_target_type_keys=("address",),
            description="Delivery routing between addresses.",
        ),
        description="A delivery route.",
    )
    address_rule = DirectAssociationMultiplicityConstraint(
        constrained_end=DirectAssociationEnd.ASSOCIATED_DATA,
        anchor_type_keys=("person",),
        associated_data_type_keys=("address",),
        lower_bound=1,
        upper_bound=None,
        description="Every address belongs to at least one person.",
    )
    definitions = GraphDefinitionSet(
        anchor_types=(PERSON,),
        associated_data_types=(NOTE, address),
        link_types=(CITES, delivers_to),
        relationship_constraints=(address_rule,),
    )
    system = _with(definitions, tmp_path)
    try:
        detail = _detail(system, "person")
        data_types = {each.type_key: each for each in detail.associated_data_types}
        assert set(data_types) == {"note", "address"}
        assert [each.property_name for each in data_types["address"].property_constraints] == [
            "city"
        ]
        assert {each.type_key for each in detail.link_types} == {"cites", "deliversTo"}
        assert detail.relationship_constraints == (address_rule,)
    finally:
        system.close()
