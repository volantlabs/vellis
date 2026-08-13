"""Evidence that the Everyday Life starter is a usable, ordinary definition set.

Supports S004's contribution to the starter authority: the vocabulary exists, is
internally valid, matches the modeled counts, and behaves like any other definition set
under governance — including the date patterns, which constrain lexical shape only.

Offering it as a first-use choice is a separate obligation, evidenced in
``test_fresh_vocabulary_choice.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.vellis.evolution_support import activate_clean_delta, stage_complete_fixture
from vellis.canonical import Provenance
from vellis.changes import GraphChange
from vellis.definitions import definition_set_equal, validate_definition_set
from vellis.everyday_life import DATE_PATTERN, everyday_life_starter
from vellis.graph import Anchor, AssociatedDataObject
from vellis.json_value import JsonKind, normalize
from vellis.outcomes import OperationStatus
from vellis.patterns import compile_pattern
from vellis.system import RTGSystem

STARTER = everyday_life_starter()


def test_the_starter_matches_the_modeled_counts() -> None:
    """The model declares each collection's multiplicity exactly."""
    assert len(STARTER.anchor_types) == 12
    assert len(STARTER.associated_data_types) == 12
    assert len(STARTER.link_types) == 9
    assert len(STARTER.relationship_constraints) == 24


def test_the_starter_is_internally_valid() -> None:
    assert validate_definition_set(STARTER, require_descriptions=True) == ()


def test_every_starter_definition_carries_a_description() -> None:
    """A cold agent reads descriptions to decide what a type is for."""
    for anchor_type in STARTER.anchor_types:
        assert anchor_type.description
    for data_type in STARTER.associated_data_types:
        assert data_type.description
        for constraint in data_type.property_constraints:
            assert constraint.description
    for link_type in STARTER.link_types:
        assert link_type.description
        assert link_type.endpoint_constraint.description
    for constraint in STARTER.relationship_constraints:
        assert constraint.description


def test_the_starter_carries_no_graph_data(tmp_path: Path) -> None:
    """It is a vocabulary. Starting from it creates no objects."""
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        assert system.initialize_fresh(
            STARTER, provenance=Provenance(initiator="owner"), initialization_summary="starter"
        ).accepted
        assert system.current_state().graph.is_empty
    finally:
        system.close()


def test_every_details_type_grounds_exactly_its_own_anchor() -> None:
    for data_type in STARTER.associated_data_types:
        assert data_type.type_key.endswith(".details")
        anchor_key = data_type.type_key.removesuffix(".details")
        assert data_type.permitted_anchor_type_keys == (anchor_key,)
        assert STARTER.anchor_type(anchor_key) is not None


def test_every_anchor_type_has_exactly_two_profile_rules() -> None:
    """One rule says a profile describes one anchor; the other caps profiles per anchor."""
    from vellis.definitions import DirectAssociationEnd

    for anchor_type in STARTER.anchor_types:
        rules = [
            each
            for each in STARTER.relationship_constraints
            if anchor_type.type_key in each.anchor_type_keys  # pyright: ignore[reportAttributeAccessIssue]
        ]
        assert len(rules) == 2
        ends = {each.constrained_end for each in rules}  # pyright: ignore[reportAttributeAccessIssue]
        assert ends == {DirectAssociationEnd.ANCHOR, DirectAssociationEnd.ASSOCIATED_DATA}


@pytest.mark.parametrize(
    ("value", "matches"),
    [
        ("2026-08-09", True),
        ("2023-02-31", True),
        ("2024-02-29", True),
        ("2024-01-00", False),
        ("2024-01-9", False),
        ("2026-13-01", False),
        ("2026-00-01", False),
        ("2026-01-32", False),
        ("2026-1-01", False),
        ("26-01-01", False),
        ("2026-08-09 ", False),
        ("x2026-08-09", False),
    ],
)
def test_the_starter_date_pattern_constrains_shape_not_the_calendar(
    value: str, matches: bool
) -> None:
    """The model is explicit that 2023-02-31 matches: shape, not calendar validity."""
    assert compile_pattern(DATE_PATTERN).matches(value) is matches


def test_a_date_property_rejects_a_misshapen_value_in_a_real_change(tmp_path: Path) -> None:
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        assert system.initialize_fresh(
            STARTER, provenance=Provenance(initiator="owner"), initialization_summary="starter"
        ).accepted

        def task_with(due: str) -> GraphChange:
            return GraphChange(
                anchor_upserts=(Anchor("t-1", "life.task", "Renew passport"),),
                associated_data_upserts=(
                    AssociatedDataObject(
                        uuid="t-1-details",
                        type_key="life.task.details",
                        anchor_uuids=("t-1",),
                        properties={"dueDate": normalize(due)},
                    ),
                ),
            )

        refused = system.apply_graph_change(
            task_with("next Tuesday"), provenance=Provenance(initiator="owner")
        )
        assert refused.status is OperationStatus.REJECTED
        assert any("whole-string pattern" in each.summary for each in refused.findings)

        accepted = system.apply_graph_change(
            task_with("2026-09-01"), provenance=Provenance(initiator="owner")
        )
        assert accepted.accepted, accepted.findings
    finally:
        system.close()


def test_the_starter_supports_an_everyday_shape_of_memory(tmp_path: Path) -> None:
    """A person, a group they belong to, a task, and the note that mentions it."""
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        assert system.initialize_fresh(
            STARTER, provenance=Provenance(initiator="owner"), initialization_summary="starter"
        ).accepted
        from vellis.graph import Link

        outcome = system.apply_graph_change(
            GraphChange(
                anchor_upserts=(
                    Anchor("p-1", "life.person", "Ada"),
                    Anchor("g-1", "life.group", "Book club"),
                    Anchor("t-1", "life.task", "Bring the cake"),
                    Anchor("n-1", "life.note", "Meeting notes"),
                ),
                associated_data_upserts=(
                    AssociatedDataObject(
                        uuid="p-1-details",
                        type_key="life.person.details",
                        anchor_uuids=("p-1",),
                        properties={"relationship": normalize("friend")},
                    ),
                ),
                link_upserts=(
                    Link("l-1", "life.member_of", "p-1", "g-1"),
                    Link("l-2", "life.involves", "t-1", "p-1"),
                    Link("l-3", "life.mentions", "n-1", "t-1"),
                ),
            ),
            provenance=Provenance(initiator="owner"),
        )
        assert outcome.accepted, outcome.findings
        assert system.check().conforms
    finally:
        system.close()


def test_the_starter_is_governed_like_any_other_vocabulary(tmp_path: Path) -> None:
    """Excludes treating it as a protected ontology. The owner can change it."""
    from vellis.definitions import AnchorTypeDefinition, GraphDefinitionSet

    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        assert system.initialize_fresh(
            STARTER, provenance=Provenance(initiator="owner"), initialization_summary="starter"
        ).accepted
        widened = GraphDefinitionSet(
            anchor_types=(
                *STARTER.anchor_types,
                AnchorTypeDefinition("life.pet", "An animal in the owner's care."),
            ),
            associated_data_types=STARTER.associated_data_types,
            link_types=STARTER.link_types,
            relationship_constraints=STARTER.relationship_constraints,
        )
        assert stage_complete_fixture(
            system, widened, provenance=Provenance(initiator="owner")
        ).accepted
        assert activate_clean_delta(system, provenance=Provenance(initiator="owner")).accepted

        active = system.current_state().active_definitions
        assert active.anchor_type("life.pet") is not None
        assert not definition_set_equal(active, STARTER)
    finally:
        system.close()


def test_property_kinds_match_the_modeled_shapes() -> None:
    """Boolean properties are Boolean; date properties are strings carrying the pattern."""
    by_key = {each.type_key: each for each in STARTER.associated_data_types}
    area = {each.property_name: each for each in by_key["life.area.details"].property_constraints}
    assert area["active"].json_kind is JsonKind.BOOLEAN
    assert area["active"].pattern is None

    goal = {each.property_name: each for each in by_key["life.goal.details"].property_constraints}
    assert goal["targetDate"].json_kind is JsonKind.STRING
    assert goal["targetDate"].pattern is not None
    assert goal["targetDate"].pattern.expression == DATE_PATTERN
    assert all(not each.required for each in by_key["life.goal.details"].property_constraints)


def _started(tmp_path: Path) -> RTGSystem:
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    assert system.initialize_fresh(
        STARTER, provenance=Provenance(initiator="owner"), initialization_summary="starter"
    ).accepted
    return system


def _anchors(*pairs: tuple[str, str]) -> tuple[Anchor, ...]:
    return tuple(
        Anchor(uuid=uuid, type_key=type_key, display_name=uuid) for uuid, type_key in pairs
    )


@pytest.mark.parametrize(
    ("link_type", "source", "target"),
    [
        ("life.member_of", ("g-1", "life.group"), ("g-2", "life.group")),
        ("life.located_at", ("p-1", "life.person"), ("pl-1", "life.place")),
        ("life.involves", ("n-1", "life.note"), ("p-1", "life.person")),
        ("life.depends_on", ("n-1", "life.note"), ("t-1", "life.task")),
        ("life.belongs_to", ("g-1", "life.goal"), ("g-2", "life.goal")),
        ("life.responsible_for", ("p-1", "life.person"), ("n-1", "life.note")),
        ("life.mentions", ("p-1", "life.person"), ("t-1", "life.task")),
        ("life.supports", ("a-1", "life.area"), ("g-1", "life.goal")),
    ],
    ids=[
        "member_of-from-group",
        "located_at-from-person",
        "involves-from-note",
        "depends_on-from-note",
        "belongs_to-to-goal",
        "responsible_for-to-note",
        "mentions-from-person",
        "supports-from-area",
    ],
)
def test_the_starter_refuses_a_link_outside_its_endpoint_types(
    tmp_path: Path, link_type: str, source: tuple[str, str], target: tuple[str, str]
) -> None:
    """The starter's value is that a cold agent can trust these rules when writing.

    Each case is a plausible mistake the endpoint sets exist to catch; without them the
    malformed memory would be accepted and stored permanently.
    """
    from vellis.graph import Link

    system = _started(tmp_path)
    try:
        outcome = system.apply_graph_change(
            GraphChange(
                anchor_upserts=_anchors(source, target),
                link_upserts=(Link("l-1", link_type, source[0], target[0]),),
            ),
            provenance=Provenance(initiator="owner"),
        )
        assert outcome.status is OperationStatus.REJECTED
        assert any(
            "endpoint constraint does not permit" in each.summary for each in outcome.findings
        )
    finally:
        system.close()


def test_an_anchor_may_carry_at_most_one_details_object(tmp_path: Path) -> None:
    """Excludes two contradictory current profiles on one anchor."""
    system = _started(tmp_path)
    try:
        outcome = system.apply_graph_change(
            GraphChange(
                anchor_upserts=_anchors(("p-1", "life.person")),
                associated_data_upserts=(
                    AssociatedDataObject("d-1", "life.person.details", ("p-1",)),
                    AssociatedDataObject("d-2", "life.person.details", ("p-1",)),
                ),
            ),
            provenance=Provenance(initiator="owner"),
        )
        assert outcome.status is OperationStatus.REJECTED
        assert any("outside 0..1" in each.summary for each in outcome.findings)
    finally:
        system.close()


def test_a_details_object_describes_exactly_one_anchor(tmp_path: Path) -> None:
    """Excludes one profile claiming to be the current details of two people."""
    system = _started(tmp_path)
    try:
        outcome = system.apply_graph_change(
            GraphChange(
                anchor_upserts=_anchors(("p-1", "life.person"), ("p-2", "life.person")),
                associated_data_upserts=(
                    AssociatedDataObject("d-1", "life.person.details", ("p-1", "p-2")),
                ),
            ),
            provenance=Provenance(initiator="owner"),
        )
        assert outcome.status is OperationStatus.REJECTED
        assert any("outside 1..1" in each.summary for each in outcome.findings)
    finally:
        system.close()


def test_a_details_object_must_be_grounded_by_its_own_anchor_type(tmp_path: Path) -> None:
    system = _started(tmp_path)
    try:
        outcome = system.apply_graph_change(
            GraphChange(
                anchor_upserts=_anchors(("g-1", "life.group")),
                associated_data_upserts=(
                    AssociatedDataObject("d-1", "life.person.details", ("g-1",)),
                ),
            ),
            provenance=Provenance(initiator="owner"),
        )
        assert outcome.status is OperationStatus.REJECTED
        assert any("does not permit" in each.summary for each in outcome.findings)
    finally:
        system.close()


@pytest.mark.parametrize(
    ("link_type", "source", "target"),
    [
        ("life.member_of", ("p-1", "life.person"), ("g-1", "life.group")),
        ("life.located_at", ("t-1", "life.task"), ("pl-1", "life.place")),
        ("life.involves", ("t-1", "life.task"), ("p-1", "life.person")),
        ("life.depends_on", ("t-1", "life.task"), ("g-1", "life.goal")),
        ("life.belongs_to", ("t-1", "life.task"), ("a-1", "life.area")),
        ("life.responsible_for", ("p-1", "life.person"), ("a-1", "life.area")),
        ("life.mentions", ("n-1", "life.note"), ("p-1", "life.person")),
        ("life.supports", ("t-1", "life.task"), ("g-1", "life.goal")),
        ("life.documents", ("r-1", "life.resource"), ("pl-1", "life.place")),
    ],
)
def test_the_starter_accepts_the_links_it_is_meant_to(
    tmp_path: Path, link_type: str, source: tuple[str, str], target: tuple[str, str]
) -> None:
    """The counterpart: the endpoint sets must not be so narrow they refuse real use."""
    from vellis.graph import Link

    system = _started(tmp_path)
    try:
        outcome = system.apply_graph_change(
            GraphChange(
                anchor_upserts=_anchors(source, target),
                link_upserts=(Link("l-1", link_type, source[0], target[0]),),
            ),
            provenance=Provenance(initiator="owner"),
        )
        assert outcome.accepted, outcome.findings
    finally:
        system.close()


@pytest.mark.parametrize(
    ("link_type", "source", "target"),
    [
        ("life.member_of", ("p-1", "life.person"), ("p-2", "life.person")),
        ("life.located_at", ("t-1", "life.task"), ("g-1", "life.goal")),
        ("life.involves", ("t-1", "life.task"), ("a-1", "life.area")),
        ("life.depends_on", ("t-1", "life.task"), ("n-1", "life.note")),
        ("life.belongs_to", ("t-1", "life.task"), ("g-1", "life.goal")),
        ("life.responsible_for", ("g-1", "life.group"), ("n-1", "life.note")),
        ("life.mentions", ("n-1", "life.note"), ("x-1", "life.note")),
        ("life.supports", ("t-1", "life.task"), ("a-1", "life.area")),
        ("life.documents", ("t-1", "life.task"), ("pl-1", "life.place")),
    ],
    ids=[
        "member_of-to-person",
        "located_at-to-goal",
        "involves-to-area",
        "depends_on-to-note",
        "belongs_to-to-goal",
        "responsible_for-to-note",
        "mentions-to-note-is-allowed",
        "supports-to-area",
        "documents-from-task",
    ],
)
def test_the_starter_constrains_both_ends_of_every_link_type(
    tmp_path: Path, link_type: str, source: tuple[str, str], target: tuple[str, str]
) -> None:
    """Each case violates the end the earlier suite left unpinned.

    ``mentions`` note-to-note is genuinely permitted — every starter anchor is a valid
    target — so it is included as the control that keeps this table honest.
    """
    from vellis.graph import Link

    system = _started(tmp_path)
    try:
        outcome = system.apply_graph_change(
            GraphChange(
                anchor_upserts=_anchors(source, target),
                link_upserts=(Link("l-1", link_type, source[0], target[0]),),
            ),
            provenance=Provenance(initiator="owner"),
        )
        permitted = link_type == "life.mentions"
        assert outcome.accepted is permitted, outcome.findings
        if not permitted:
            assert any(
                "endpoint constraint does not permit" in each.summary for each in outcome.findings
            )
    finally:
        system.close()


def test_every_starter_type_key_and_description_is_the_modeled_one() -> None:
    """Excludes silent drift in the vocabulary an owner's memory is stored under.

    A typo in a key is not cosmetic: memory would be stored permanently under a key the
    model does not define.
    """
    assert [each.type_key for each in STARTER.anchor_types] == [
        "life.person",
        "life.group",
        "life.area",
        "life.goal",
        "life.project",
        "life.task",
        "life.event",
        "life.routine",
        "life.decision",
        "life.note",
        "life.resource",
        "life.place",
    ]
    assert [each.type_key for each in STARTER.link_types] == [
        "life.belongs_to",
        "life.supports",
        "life.responsible_for",
        "life.member_of",
        "life.involves",
        "life.located_at",
        "life.documents",
        "life.mentions",
        "life.depends_on",
    ]
    by_key = {each.type_key: each for each in STARTER.anchor_types}
    assert by_key["life.place"].description == (
        "A place relevant to the owner's life. Use the anchor display name for its name."
    )
    assert by_key["life.person"].description == (
        "A person known to the owner. Use the anchor display name for the person's name."
    )
    data = {each.type_key: each for each in STARTER.associated_data_types}
    assert data["life.decision.details"].description == (
        "Optional current everyday details about one Decision."
    )
    links = {each.type_key: each for each in STARTER.link_types}
    assert links["life.responsible_for"].endpoint_constraint.description == (
        "Sources are Persons or Groups; targets are Areas, Goals, Projects, Tasks, "
        "Events, or Routines."
    )


def test_every_details_type_declares_exactly_the_modeled_properties() -> None:
    """Excludes losing a modeled field, which would refuse a value the owner may store."""
    expected = {
        "life.person.details": ["relationship", "preferredContact", "notes"],
        "life.group.details": ["kind", "description"],
        "life.area.details": ["domain", "focus", "active"],
        "life.goal.details": ["status", "priority", "targetDate", "desiredOutcome"],
        "life.project.details": ["status", "priority", "desiredOutcome", "nextReviewDate"],
        "life.task.details": ["status", "priority", "dueDate", "context"],
        "life.event.details": ["status", "start", "end", "summary"],
        "life.routine.details": ["cadence", "active", "nextDueDate", "context"],
        "life.decision.details": ["status", "decisionDate", "rationale"],
        "life.note.details": ["topic", "summary", "captureDate"],
        "life.resource.details": ["kind", "locationOrWebAddress", "summary"],
        "life.place.details": ["kind", "address", "notes"],
    }
    actual = {
        each.type_key: [constraint.property_name for constraint in each.property_constraints]
        for each in STARTER.associated_data_types
    }
    assert actual == expected


def test_the_date_shape_wording_names_the_starter_shape() -> None:
    """The description tells an agent which shape to write; vague wording defeats it."""
    data = {each.type_key: each for each in STARTER.associated_data_types}
    due = next(
        each
        for each in data["life.task.details"].property_constraints
        if each.property_name == "dueDate"
    )
    assert due.description == "The Task due date in the starter's lexical YYYY-MM-DD shape."
