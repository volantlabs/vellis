"""Evidence for ``VellisVerification::definitionWork``.

The verification case walks one arc — create, repeated edit, assessment, invalid
activation, valid activation, discard, replay — and asserts throughout that there is
exactly one active set, at most one proposal, and no change to graph or active
definitions while proposal work is going on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vellis.canonical import (
    DefinitionDeltaDisposition,
    Provenance,
    TransitionKind,
    canonical_state_equal,
)
from vellis.changes import GraphChange
from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    GraphDefinitionSet,
    PropertyConstraint,
    definition_set_equal,
)
from vellis.discovery import DefinitionInspectionRequest
from vellis.graph import Anchor, AssociatedDataObject, graph_equal
from vellis.json_value import JsonKind, normalize
from vellis.outcomes import OperationStatus, ValidationScope
from vellis.store import StoreError
from vellis.system import RTGSystem

PERSON = AnchorTypeDefinition(type_key="person", description="A person the owner knows.")
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
ACTIVE = GraphDefinitionSet(anchor_types=(PERSON,), associated_data_types=(NOTE,))

PROJECT = AnchorTypeDefinition(type_key="project", description="A piece of work.")
WIDER = GraphDefinitionSet(anchor_types=(PERSON, PROJECT), associated_data_types=(NOTE,))
UNDESCRIBED = GraphDefinitionSet(
    anchor_types=(PERSON, AnchorTypeDefinition(type_key="project")),
    associated_data_types=(NOTE,),
)


def _owner() -> Provenance:
    return Provenance(initiator="owner")


def _system(tmp_path: Path, definitions: GraphDefinitionSet = ACTIVE) -> RTGSystem:
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    outcome = system.initialize_fresh(
        definitions, provenance=_owner(), initialization_summary="a fresh start"
    )
    assert outcome.accepted, outcome.findings
    return system


def _stage(system: RTGSystem, proposed: GraphDefinitionSet):
    return system.set_definition_delta(proposed, provenance=_owner())


# --- One active set, at most one proposal -------------------------------------------


def test_there_is_no_proposal_until_one_is_staged(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        result = system.definition_delta()
        assert result.status is OperationStatus.ACCEPTED
        assert result.definition_delta is None
        assert result.assessment is None
        assert result.evaluated_revision == 0
        # Excludes announcing a proposal that is not there.
        assert result.summary == "there is no proposal"
    finally:
        system.close()


def test_staging_creates_the_sole_proposal_and_advances_one_revision(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        result = _stage(system, WIDER)
        assert result.status is OperationStatus.ACCEPTED
        assert result.resulting_revision == 1
        assert result.evaluated_revision == 1
        assert result.definition_delta is not None
        assert definition_set_equal(result.definition_delta.proposed_definitions, WIDER)
        assert result.assessment is not None
        assert result.assessment.evaluated_revision == 1
        assert system.current_state().definition_delta is not None
    finally:
        system.close()


def test_editing_replaces_the_proposal_rather_than_adding_one(tmp_path: Path) -> None:
    """At most one delta: a second staging is an edit, not a second proposal."""
    system = _system(tmp_path)
    try:
        assert _stage(system, WIDER).accepted
        edited = GraphDefinitionSet(
            anchor_types=(PERSON, PROJECT, AnchorTypeDefinition("team", "A group.")),
            associated_data_types=(NOTE,),
        )
        second = _stage(system, edited)
        assert second.accepted
        assert second.resulting_revision == 2
        current = system.definition_delta()
        assert current.definition_delta is not None
        assert definition_set_equal(current.definition_delta.proposed_definitions, edited)
    finally:
        system.close()


def test_a_proposal_may_stand_across_other_work(tmp_path: Path) -> None:
    """A valid proposal does not have to be activated or discarded to get on with things."""
    system = _system(tmp_path)
    try:
        assert _stage(system, WIDER).accepted
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-1", "person", "Ada"),)),
            provenance=_owner(),
        ).accepted
        assert system.definition_summary().delta_present is True
        still_there = system.definition_delta()
        assert still_there.definition_delta is not None
        assert definition_set_equal(still_there.definition_delta.proposed_definitions, WIDER)
        # The assessment follows the graph the change produced rather than pinning the
        # proposal to the revision it was staged at.
        assert still_there.assessment is not None
        assert still_there.evaluated_revision == system.current_state().revision
    finally:
        system.close()


# --- Effective no-ops ----------------------------------------------------------------


def test_staging_the_active_set_with_no_proposal_is_an_accepted_no_op(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        before = system.current_state()
        result = _stage(system, ACTIVE)
        assert result.status is OperationStatus.ACCEPTED
        assert result.resulting_revision is None
        assert result.definition_delta is None
        assert "nothing was staged" in result.summary
        assert canonical_state_equal(system.current_state(), before)
    finally:
        system.close()


def test_restaging_the_same_proposal_is_an_accepted_no_op(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert _stage(system, WIDER).accepted
        before = system.current_state()
        again = _stage(system, WIDER)
        assert again.status is OperationStatus.ACCEPTED
        assert again.resulting_revision is None
        assert again.definition_delta is not None
        assert canonical_state_equal(system.current_state(), before)
    finally:
        system.close()


def test_staging_the_active_set_cannot_implicitly_discard_a_proposal(tmp_path: Path) -> None:
    """Excludes throwing away the owner's draft because the new content matched active."""
    system = _system(tmp_path)
    try:
        assert _stage(system, WIDER).accepted
        before = system.current_state()
        refused = _stage(system, ACTIVE)
        assert refused.status is OperationStatus.REJECTED
        assert refused.definition_delta is None
        assert refused.assessment is None
        assert refused.evaluated_revision is None
        assert refused.resulting_revision is None
        assert canonical_state_equal(system.current_state(), before)
        # The proposal is still retrievable, unchanged.
        current = system.definition_delta()
        assert current.definition_delta is not None
        assert definition_set_equal(current.definition_delta.proposed_definitions, WIDER)
    finally:
        system.close()


# --- Nothing else moves while a proposal is worked on --------------------------------


def test_proposal_work_changes_neither_graph_nor_active_definitions(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-1", "person", "Ada"),)),
            provenance=_owner(),
        ).accepted
        before = system.current_state()

        assert _stage(system, WIDER).accepted
        assert system.definition_delta().accepted
        assert _stage(system, UNDESCRIBED).accepted
        # Refused: an undescribed proposal cannot activate, which is what keeps the
        # active set still for the comparison below.
        assert not system.activate_definition_delta(provenance=_owner()).accepted

        after = system.current_state()
        assert definition_set_equal(after.active_definitions, before.active_definitions)
        assert graph_equal(after.graph, before.graph)
    finally:
        system.close()


# --- Nor does a graph change move the proposal -----------------------------------------
#
# ``RTGSystem::'Apply graph change'`` promises success leaves "active definitions and the
# delta unchanged" and that refusal "changes no canonical state or revision". Neither can
# be shown where no proposal can exist, so the graph-change slice could only watch an
# absent delta stay absent. These watch a standing one survive.


def test_a_refused_graph_change_leaves_a_standing_proposal_and_the_revision_alone(
    tmp_path: Path,
) -> None:
    system = _system(tmp_path)
    try:
        assert _stage(system, WIDER).accepted
        before = system.current_state()
        assert before.definition_delta is not None

        refused = system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-9", "unheard-of", "Nobody"),)),
            provenance=_owner(),
        )
        assert not refused.accepted
        assert refused.findings

        after = system.current_state()
        assert canonical_state_equal(after, before)
        assert after.revision == before.revision
        assert after.definition_delta is not None
    finally:
        system.close()


def test_replay_carries_a_standing_proposal_across_a_graph_mutation(tmp_path: Path) -> None:
    """A mutation that says it left the delta alone must replay as having left it alone.

    The delta-operation arc never produces this record: every step there changes the
    delta, so ``UNCHANGED`` only ever appears where no proposal exists to preserve.
    """
    system = _system(tmp_path)
    try:
        assert _stage(system, WIDER).accepted
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-1", "person", "Ada"),)),
            provenance=_owner(),
        ).accepted

        replayed = system.replay()
        assert canonical_state_equal(system.current_state(), replayed)
        assert replayed.definition_delta is not None
        assert definition_set_equal(replayed.definition_delta.proposed_definitions, WIDER)

        # And it survives an activation that follows the mutation.
        assert system.activate_definition_delta(provenance=_owner()).accepted
        assert canonical_state_equal(system.current_state(), system.replay())
        assert definition_set_equal(system.replay().active_definitions, WIDER)
    finally:
        system.close()


# --- Assessment ----------------------------------------------------------------------


def test_an_empty_description_is_reported_while_the_proposal_stays_inspectable(
    tmp_path: Path,
) -> None:
    """A working proposal may carry findings; that is what makes it a draft."""
    system = _system(tmp_path)
    try:
        staged = _stage(system, UNDESCRIBED)
        assert staged.status is OperationStatus.ACCEPTED
        assert staged.assessment is not None
        assert not staged.assessment.conforms
        assert staged.assessment.scope is ValidationScope.DEFINITION_DELTA
        assert any(
            "no non-empty owner-readable description" in each.summary
            for each in staged.assessment.findings
        )
        retrieved = system.definition_delta()
        assert retrieved.definition_delta is not None
    finally:
        system.close()


def test_the_assessment_reports_impact_on_the_graph_the_owner_already_has(
    tmp_path: Path,
) -> None:
    """Excludes assessing a proposal only in the abstract.

    The narrowed proposal is internally valid; what makes it unusable is the memory that
    already exists, and the owner has to be told that before activating it.
    """
    system = _system(tmp_path)
    try:
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(Anchor("a-1", "person", "Ada"),),
                associated_data_upserts=(
                    AssociatedDataObject(
                        uuid="d-1",
                        type_key="note",
                        anchor_uuids=("a-1",),
                        properties={"title": normalize("First")},
                    ),
                ),
            ),
            provenance=_owner(),
        ).accepted

        narrowed = GraphDefinitionSet(anchor_types=(PERSON,))
        staged = _stage(system, narrowed)
        assert staged.accepted
        assert staged.assessment is not None
        assert not staged.assessment.conforms
        assert any(
            "resolves to no active associatedData type definition" in each.summary
            for each in staged.assessment.findings
        )
    finally:
        system.close()


def test_the_assessment_shares_the_results_evaluated_revision(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        staged = _stage(system, WIDER)
        assert staged.assessment is not None
        assert staged.assessment.evaluated_revision == staged.evaluated_revision
        assert staged.resulting_revision == staged.evaluated_revision
        retrieved = system.definition_delta()
        assert retrieved.assessment is not None
        assert retrieved.assessment.evaluated_revision == retrieved.evaluated_revision
    finally:
        system.close()


# --- Activation ----------------------------------------------------------------------


def test_activation_is_blocked_while_any_description_is_empty(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert _stage(system, UNDESCRIBED).accepted
        before = system.current_state()
        refused = system.activate_definition_delta(provenance=_owner())
        assert refused.status is OperationStatus.REJECTED
        assert refused.resulting_revision is None
        assert any(
            "no non-empty owner-readable description" in each.summary for each in refused.findings
        )
        assert canonical_state_equal(system.current_state(), before)
    finally:
        system.close()


def test_activation_is_blocked_while_the_graph_would_not_conform(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-1", "person", "Ada"),)),
            provenance=_owner(),
        ).accepted
        assert _stage(system, GraphDefinitionSet(anchor_types=(PROJECT,))).accepted
        before = system.current_state()
        refused = system.activate_definition_delta(provenance=_owner())
        assert refused.status is OperationStatus.REJECTED
        assert canonical_state_equal(system.current_state(), before)
    finally:
        system.close()


def test_a_valid_activation_replaces_the_active_set_and_clears_the_proposal(
    tmp_path: Path,
) -> None:
    system = _system(tmp_path)
    try:
        assert _stage(system, WIDER).accepted
        outcome = system.activate_definition_delta(provenance=_owner())
        assert outcome.status is OperationStatus.ACCEPTED
        assert outcome.resulting_revision == 2

        state = system.current_state()
        assert definition_set_equal(state.active_definitions, WIDER)
        assert state.definition_delta is None
        assert system.definition_delta().definition_delta is None
        assert system.definition_summary().delta_present is False
        assert canonical_state_equal(state, system.replay())
    finally:
        system.close()


def test_activation_without_a_proposal_is_refused(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        before = system.current_state()
        refused = system.activate_definition_delta(provenance=_owner())
        assert refused.status is OperationStatus.REJECTED
        assert refused.resulting_revision is None
        assert canonical_state_equal(system.current_state(), before)
    finally:
        system.close()


def test_activation_that_clears_a_delta_is_a_canonical_transition(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert _stage(system, WIDER).accepted
        assert system.activate_definition_delta(provenance=_owner()).accepted
        transitions = system.store.transitions()
        assert [each.kind for each in transitions] == [
            TransitionKind.DEFINITION_DELTA_CHANGE,
            TransitionKind.DEFINITION_ACTIVATION,
        ]
        activation = transitions[-1]
        assert activation.change.delta_disposition is DefinitionDeltaDisposition.ABSENT
        assert activation.change.active_definitions is not None
        assert activation.change.graph_change is None
        assert activation.change.replacement_graph is None
    finally:
        system.close()


# --- Discard -------------------------------------------------------------------------


def test_discarding_clears_the_proposal_and_commits_one_revision(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert _stage(system, WIDER).accepted
        before = system.current_state()
        outcome = system.discard_definition_delta(provenance=_owner())
        assert outcome.status is OperationStatus.ACCEPTED
        assert outcome.resulting_revision == before.revision + 1

        state = system.current_state()
        assert state.definition_delta is None
        assert definition_set_equal(state.active_definitions, ACTIVE)
        assert canonical_state_equal(state, system.replay())
    finally:
        system.close()


def test_discarding_nothing_is_refused(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        before = system.current_state()
        refused = system.discard_definition_delta(provenance=_owner())
        assert refused.status is OperationStatus.REJECTED
        assert refused.resulting_revision is None
        assert canonical_state_equal(system.current_state(), before)
    finally:
        system.close()


# --- Replay --------------------------------------------------------------------------


def test_the_whole_arc_replays_from_the_ledger_alone(tmp_path: Path) -> None:
    """Create, edit, activate, stage again, discard — and replay agrees at every step."""
    path = tmp_path / "vellis.sqlite3"
    system = _system(tmp_path)
    try:
        steps = (
            lambda: _stage(system, UNDESCRIBED),
            lambda: _stage(system, WIDER),
            lambda: system.activate_definition_delta(provenance=_owner()),
            lambda: _stage(
                system,
                GraphDefinitionSet(
                    anchor_types=(PERSON, PROJECT, AnchorTypeDefinition("team", "A group.")),
                    associated_data_types=(NOTE,),
                ),
            ),
            lambda: system.discard_definition_delta(provenance=_owner()),
        )
        for step in steps:
            assert step().accepted
            assert canonical_state_equal(system.current_state(), system.replay())
        final = system.current_state()
        assert final.revision == len(steps)
        assert final.definition_delta is None
        assert definition_set_equal(final.active_definitions, WIDER)
    finally:
        system.close()

    reopened = RTGSystem.open(path)
    try:
        assert canonical_state_equal(reopened.current_state(), reopened.replay())
        assert definition_set_equal(reopened.current_state().active_definitions, WIDER)
    finally:
        reopened.close()


@pytest.mark.parametrize(
    "operation",
    ["stage", "activate", "discard"],
)
def test_unstorable_provenance_is_refused_on_every_governance_operation(
    tmp_path: Path, operation: str
) -> None:
    system = _system(tmp_path)
    try:
        if operation != "stage":
            assert _stage(system, WIDER).accepted
        before = system.current_state()
        bad = Provenance(initiator="own" + chr(0xD800) + "er")
        if operation == "stage":
            result = system.set_definition_delta(WIDER, provenance=bad)
        elif operation == "activate":
            result = system.activate_definition_delta(provenance=bad)
        else:
            result = system.discard_definition_delta(provenance=bad)
        assert result.status is OperationStatus.REJECTED
        assert canonical_state_equal(system.current_state(), before)
    finally:
        system.close()


@pytest.mark.parametrize(
    "draft",
    ["duplicate anchor type", "duplicate property", "duplicate rule"],
)
def test_restaging_an_invalid_draft_is_still_a_no_op(tmp_path: Path, draft: str) -> None:
    """Excludes an equality that is not reflexive on the drafts staging invites.

    A proposal may carry findings while it is edited, so a duplicated entry is an
    ordinary typo. If re-staging it were not recognised as unchanged, an agent in an
    edit loop would grow the ledger a revision at a time, and the committed state would
    stop matching its own replay.
    """
    from vellis.definitions import (
        DirectAssociationEnd,
        DirectAssociationMultiplicityConstraint,
    )

    rule = DirectAssociationMultiplicityConstraint(
        constrained_end=DirectAssociationEnd.ANCHOR,
        anchor_type_keys=("person",),
        associated_data_type_keys=("note",),
        lower_bound=0,
        upper_bound=1,
        description="At most one note per person.",
    )
    # Both drafts also add PROJECT, so neither can be mistaken for the active set
    # and refused as an implicit discard.
    drafts = {
        "duplicate anchor type": GraphDefinitionSet(
            anchor_types=(PERSON, PERSON), associated_data_types=(NOTE,)
        ),
        "duplicate property": GraphDefinitionSet(
            anchor_types=(PERSON, PROJECT),
            associated_data_types=(
                AssociatedDataTypeDefinition(
                    type_key="note",
                    permitted_anchor_type_keys=("person",),
                    property_constraints=(
                        NOTE.property_constraints[0],
                        NOTE.property_constraints[0],
                    ),
                    description="A note about a person.",
                ),
            ),
        ),
        "duplicate rule": GraphDefinitionSet(
            anchor_types=(PERSON, PROJECT),
            associated_data_types=(NOTE,),
            relationship_constraints=(rule, rule),
        ),
    }
    proposed = drafts[draft]

    system = _system(tmp_path)
    try:
        first = _stage(system, proposed)
        assert first.accepted
        assert first.resulting_revision == 1
        # The draft is invalid, and says so, and is still staged.
        assert first.assessment is not None and not first.assessment.conforms

        before = system.current_state()
        for _ in range(3):
            again = _stage(system, proposed)
            assert again.status is OperationStatus.ACCEPTED
            assert again.resulting_revision is None
        assert canonical_state_equal(system.current_state(), before)
        assert canonical_state_equal(system.current_state(), system.replay())
        assert system.store.canonical_record_count() == 2
    finally:
        system.close()


def test_a_correction_to_a_duplicated_draft_is_not_read_as_unchanged(tmp_path: Path) -> None:
    """Excludes discarding the owner's fix because equality reused a matched entry."""
    mixed = GraphDefinitionSet(
        anchor_types=(
            PERSON,
            AnchorTypeDefinition("person", "A human being."),
        ),
        associated_data_types=(NOTE,),
    )
    corrected = GraphDefinitionSet(anchor_types=(PERSON, PERSON), associated_data_types=(NOTE,))

    system = _system(tmp_path)
    try:
        assert _stage(system, mixed).resulting_revision == 1
        second = _stage(system, corrected)
        assert second.resulting_revision == 2
        stored = system.definition_delta()
        assert stored.definition_delta is not None
        assert [
            each.description for each in stored.definition_delta.proposed_definitions.anchor_types
        ] == [
            "A person the owner knows.",
            "A person the owner knows.",
        ]
    finally:
        system.close()


def test_a_delta_read_that_cannot_be_answered_reports_failure(tmp_path: Path) -> None:
    """Excludes reading a store failure as "there is no proposal"."""
    system = _system(tmp_path)
    try:
        assert _stage(system, WIDER).accepted
        system.store._connection.execute("DROP TABLE state_head")  # noqa: SLF001
        result = system.definition_delta()
        assert result.status is OperationStatus.FAILED
        assert result.findings
        assert result.definition_delta is None
        assert result.assessment is None
        assert result.evaluated_revision is None
    finally:
        system.close()


@pytest.mark.parametrize(
    ("name", "operate"),
    (
        ("stage", lambda system: _stage(system, WIDER)),
        ("activate", lambda system: system.activate_definition_delta(provenance=_owner())),
        ("discard", lambda system: system.discard_definition_delta(provenance=_owner())),
    ),
)
def test_a_delta_write_that_cannot_be_answered_reports_failure(
    tmp_path: Path, name: str, operate
) -> None:
    """Excludes a store failure escaping the boundary as an untyped exception.

    Each of the three use cases names a failure outcome whose non-effect is preserved.
    Nothing has been written when the state cannot be read, so the status is reportable.
    """
    system = _system(tmp_path)
    try:
        system.store._connection.execute("DROP TABLE state_head")  # noqa: SLF001
        outcome = operate(system)
        assert outcome.status is OperationStatus.FAILED, name
        assert outcome.findings
        assert outcome.resulting_revision is None
    finally:
        system.close()


def test_staging_describes_the_commit_it_made_without_reading_the_store_again(
    tmp_path: Path,
) -> None:
    """Excludes describing a commit by re-reading it.

    A read that fails after the write would report failure for work that landed, and the
    owner's retry would then be an accepted no-op reporting no revision at all — two
    answers, neither of them the truth. So the first read must succeed and only a later
    one fail, which is the case the guarded pre-read alone cannot reach.
    """
    system = _system(tmp_path)
    try:
        original = system.current_state
        reads = {"count": 0}

        def fail_after_the_first_read():
            reads["count"] += 1
            if reads["count"] > 1:
                raise StoreError("transient read failure")
            return original()

        system.current_state = fail_after_the_first_read  # type: ignore[method-assign]
        result = system.set_definition_delta(WIDER, provenance=_owner())
        system.current_state = original  # type: ignore[method-assign]

        assert result.status is OperationStatus.ACCEPTED
        assert result.resulting_revision == 1
        assert result.definition_delta is not None
        assert definition_set_equal(result.definition_delta.proposed_definitions, WIDER)
        assert system.current_state().revision == 1
    finally:
        system.close()


def test_a_commit_that_cannot_be_appended_reports_failure_without_effect(
    tmp_path: Path,
) -> None:
    """The write half: the store rolls back, so the status is reportable, not raised."""
    system = _system(tmp_path)
    try:
        assert _stage(system, WIDER).accepted
        before = system.current_state()
        # Fail the next append after validation but before any projection can commit.
        system.store._connection.execute(  # noqa: SLF001
            "CREATE TRIGGER refuse_next_record BEFORE INSERT ON canonical_record "
            "BEGIN SELECT RAISE(ABORT, 'record append failed'); END"
        )

        outcome = system.discard_definition_delta(provenance=_owner())
        assert outcome.status is OperationStatus.FAILED
        assert outcome.resulting_revision is None
        assert canonical_state_equal(system.current_state(), before)
    finally:
        system.close()


def test_a_structurally_invalid_change_leaves_a_standing_proposal_alone(tmp_path: Path) -> None:
    """The other refusal branch: refused before the resulting graph is ever assembled."""
    system = _system(tmp_path)
    try:
        assert _stage(system, WIDER).accepted
        before = system.current_state()
        ada = Anchor("a-1", "person", "Ada")

        refused = system.apply_graph_change(
            GraphChange(anchor_upserts=(ada, ada)), provenance=_owner()
        )
        assert not refused.accepted
        assert refused.findings

        assert canonical_state_equal(system.current_state(), before)
        assert system.current_state().definition_delta is not None
    finally:
        system.close()


def test_the_whole_proposal_can_be_compared_with_focused_active_views(tmp_path: Path) -> None:
    """The review use case's evidence clause, and why there is no server-side diff.

    The system returns the proposal whole and the active neighbourhood focused; putting
    them side by side is the caller's work, and it is enough to see what would change.
    """
    system = _system(tmp_path)
    try:
        assert _stage(system, WIDER).accepted
        retrieved = system.definition_delta()
        assert retrieved.definition_delta is not None
        proposed = retrieved.definition_delta.proposed_definitions

        active = system.inspect_definitions(
            DefinitionInspectionRequest(anchor_type_keys=("person",))
        )
        assert active.accepted
        assert active.evaluated_revision == retrieved.evaluated_revision

        # Nothing the system returned is a diff; the comparison is the caller's.
        proposed_keys = {each.type_key for each in proposed.anchor_types}
        active_keys = {
            each.type_key for each in system.current_state().active_definitions.anchor_types
        }
        assert proposed_keys - active_keys == {"project"}
        assert active_keys - proposed_keys == set()
    finally:
        system.close()


def test_governance_reads_and_writes_visit_no_canonical_record(tmp_path: Path) -> None:
    """Delta retrieval is named in the current-work requirement, so it may not walk history."""
    system = _system(tmp_path)
    try:
        system.store.reset_instrumentation()
        system.definition_delta()
        assert _stage(system, WIDER).accepted
        for _ in range(20):
            system.definition_delta()
        assert system.activate_definition_delta(provenance=_owner()).accepted
        assert system.discard_definition_delta(provenance=_owner()).status is (
            OperationStatus.REJECTED
        )
        assert system.store.record_reads == 0
    finally:
        system.close()


@pytest.mark.parametrize(
    "field", ["permitted anchor types", "endpoint sources", "rule participants"]
)
def test_correcting_a_duplicated_member_of_a_referenced_set_is_a_real_change(
    tmp_path: Path, field: str
) -> None:
    """Excludes comparing referenced type-key lists as sets.

    A repeated member is an ordinary typo in a draft, and it is reported as a finding.
    If the corrected draft compared equal to the uncorrected one, staging the fix would
    report success while writing nothing, and activation would refuse forever on a
    finding the owner had already fixed.

    Both drafts also add PROJECT, so neither can be mistaken for the active set and
    refused as an implicit discard.
    """
    from vellis.definitions import (
        DirectAssociationEnd,
        DirectAssociationMultiplicityConstraint,
        EndpointConstraint,
        LinkTypeDefinition,
    )

    anchors = (PERSON, PROJECT)

    def with_note(keys: tuple[str, ...]) -> GraphDefinitionSet:
        return GraphDefinitionSet(
            anchor_types=anchors,
            associated_data_types=(
                AssociatedDataTypeDefinition(
                    type_key="note",
                    permitted_anchor_type_keys=keys,
                    property_constraints=NOTE.property_constraints,
                    description="A note about a person.",
                ),
            ),
        )

    def with_link(keys: tuple[str, ...]) -> GraphDefinitionSet:
        return GraphDefinitionSet(
            anchor_types=anchors,
            associated_data_types=(NOTE,),
            link_types=(
                LinkTypeDefinition(
                    type_key="worksOn",
                    endpoint_constraint=EndpointConstraint(
                        permitted_source_type_keys=keys,
                        permitted_target_type_keys=("project",),
                        description="Who works on what.",
                    ),
                    description="A working relationship.",
                ),
            ),
        )

    def with_rule(keys: tuple[str, ...]) -> GraphDefinitionSet:
        return GraphDefinitionSet(
            anchor_types=anchors,
            associated_data_types=(NOTE,),
            relationship_constraints=(
                DirectAssociationMultiplicityConstraint(
                    constrained_end=DirectAssociationEnd.ANCHOR,
                    anchor_type_keys=keys,
                    associated_data_type_keys=("note",),
                    lower_bound=0,
                    upper_bound=1,
                    description="At most one note per person.",
                ),
            ),
        )

    build = {
        "permitted anchor types": with_note,
        "endpoint sources": with_link,
        "rule participants": with_rule,
    }[field]
    typo, corrected = build(("person", "person")), build(("person",))

    system = _system(tmp_path)
    try:
        first = _stage(system, typo)
        assert first.resulting_revision == 1
        assert first.assessment is not None and not first.assessment.conforms

        fixed = _stage(system, corrected)
        assert fixed.resulting_revision == 2, "the correction must be a real change"
        assert fixed.assessment is not None and fixed.assessment.conforms
        assert system.activate_definition_delta(provenance=_owner()).accepted
    finally:
        system.close()
