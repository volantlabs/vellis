"""Compact semantic evidence for bounded prospective-definition governance."""

from pathlib import Path

import pytest

from tests.vellis.evolution_support import activate_clean_delta, stage_complete_fixture
from tests.vellis.oracle import materialize_definitions, materialize_replay, materialize_state
from tests.vellis.semantic_state import semantic_state_equal
from vellis.canonical import Provenance
from vellis.changes import GraphChange
from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    GraphDefinitionSet,
    PropertyConstraint,
    definition_set_equal,
)
from vellis.governance import DefinitionChange
from vellis.graph import Anchor
from vellis.json_value import JsonKind
from vellis.outcomes import (
    OperationStatus,
    ValidationRequest,
    ValidationRequestKind,
    ValidationScope,
)
from vellis.store import StoreError
from vellis.system import RTGSystem

OWNER = Provenance("owner")
PERSON = AnchorTypeDefinition("person", "A person.")
NOTE = AssociatedDataTypeDefinition(
    "note",
    ("person",),
    (PropertyConstraint("title", True, JsonKind.STRING, description="A title."),),
    "A note.",
)
ACTIVE = GraphDefinitionSet(anchor_types=(PERSON,), associated_data_types=(NOTE,))
PROJECT = AnchorTypeDefinition("project", "A project.")
WIDER = GraphDefinitionSet(anchor_types=(PERSON, PROJECT), associated_data_types=(NOTE,))


def _system(tmp_path: Path) -> RTGSystem:
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    assert system.initialize_fresh(
        ACTIVE, provenance=OWNER, initialization_summary="fresh"
    ).accepted
    return system


def _assessment(system: RTGSystem, maximum: int = 100):
    return system.check(
        ValidationRequest(
            ValidationRequestKind.ASSESS,
            ValidationScope.DEFINITION_DELTA,
            maximum,
        ),
        provenance=OWNER,
    )


def test_staging_creates_the_sole_proposal_and_advances_one_revision(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        result = stage_complete_fixture(system, WIDER, provenance=OWNER)
        assert result.accepted and result.resulting_revision == 1
        assert result.proposed_definition_identity is not None
        assert definition_set_equal(materialize_definitions(system, prospective=True), WIDER)
    finally:
        system.close()


def test_staging_the_active_set_cannot_implicitly_discard_a_proposal(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert stage_complete_fixture(system, WIDER, provenance=OWNER).accepted
        before = system.definition_delta()
        refused = stage_complete_fixture(system, ACTIVE, provenance=OWNER)
        after = system.definition_delta()
        assert not refused.accepted
        assert after.proposed_definition_identity == before.proposed_definition_identity
    finally:
        system.close()


def test_restaging_the_same_proposal_is_an_accepted_no_op(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert stage_complete_fixture(system, WIDER, provenance=OWNER).resulting_revision == 1
        repeated = stage_complete_fixture(system, WIDER, provenance=OWNER)
        assert repeated.accepted and repeated.resulting_revision is None
        assert system.store.current_revision() == 1
    finally:
        system.close()


def test_a_valid_activation_replaces_the_active_set_and_clears_the_proposal(
    tmp_path: Path,
) -> None:
    system = _system(tmp_path)
    try:
        assert stage_complete_fixture(system, WIDER, provenance=OWNER).accepted
        activated = activate_clean_delta(system, provenance=OWNER)
        assert activated.accepted
        assert definition_set_equal(materialize_definitions(system), WIDER)
        assert system.definition_delta().proposed_definition_identity is None
    finally:
        system.close()


def test_activation_is_blocked_while_any_description_is_empty(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(AnchorTypeDefinition("project"),)),
            provenance=OWNER,
        ).accepted
        report = _assessment(system)
        assert not report.conforms and report.assessment_id is not None
        before = system.store.current_revision()
        from vellis.governance import ActivateDefinitionDeltaRequest

        refused = system.activate_definition_delta(
            ActivateDefinitionDeltaRequest(report.assessment_id), provenance=OWNER
        )
        assert not refused.accepted and system.store.current_revision() == before
    finally:
        system.close()


def test_discarding_clears_the_proposal_and_commits_one_revision(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert stage_complete_fixture(system, WIDER, provenance=OWNER).accepted
        discarded = system.discard_definition_delta(provenance=OWNER)
        assert discarded.accepted and discarded.resulting_revision == 2
        assert system.definition_delta().proposed_definition_identity is None
    finally:
        system.close()


def test_proposal_work_changes_neither_graph_nor_active_definitions(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a", "person", "Ada"),)), provenance=OWNER
        ).accepted
        before_graph = materialize_state(system).graph
        before_definitions = materialize_definitions(system)
        assert stage_complete_fixture(system, WIDER, provenance=OWNER).accepted
        assert materialize_state(system).graph == before_graph
        assert definition_set_equal(materialize_definitions(system), before_definitions)
    finally:
        system.close()


def test_a_refused_graph_change_leaves_a_standing_proposal_and_the_revision_alone(
    tmp_path: Path,
) -> None:
    system = _system(tmp_path)
    try:
        assert stage_complete_fixture(system, WIDER, provenance=OWNER).accepted
        identity = system.definition_delta().proposed_definition_identity
        revision = system.store.current_revision()
        refused = system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("x", "unknown", "Bad"),)), provenance=OWNER
        )
        assert not refused.accepted
        assert system.store.current_revision() == revision
        assert system.definition_delta().proposed_definition_identity == identity
    finally:
        system.close()


def test_replay_carries_a_standing_proposal_across_a_graph_mutation(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert stage_complete_fixture(system, WIDER, provenance=OWNER).accepted
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a", "person", "Ada"),)), provenance=OWNER
        ).accepted
        assert semantic_state_equal(materialize_replay(system.store), materialize_state(system))
    finally:
        system.close()


def test_the_whole_arc_replays_from_the_ledger_alone(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert stage_complete_fixture(system, WIDER, provenance=OWNER).accepted
        assert activate_clean_delta(system, provenance=OWNER).accepted
        assert semantic_state_equal(materialize_replay(system.store), materialize_state(system))
    finally:
        system.close()


def test_an_empty_description_is_reported_while_the_proposal_stays_inspectable(
    tmp_path: Path,
) -> None:
    system = _system(tmp_path)
    try:
        staged = system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(AnchorTypeDefinition("project"),)),
            provenance=OWNER,
        )
        report = _assessment(system)
        assert staged.accepted and staged.proposed_definition_identity is not None
        assert not report.conforms
        assert system.definition_delta().proposed_definition_identity is not None
    finally:
        system.close()


def test_the_assessment_reports_impact_on_the_graph_the_owner_already_has(
    tmp_path: Path,
) -> None:
    system = _system(tmp_path)
    try:
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a", "person", "Ada"),)), provenance=OWNER
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(type_removals=("person",)), provenance=OWNER
        ).accepted
        report = _assessment(system)
        assert not report.conforms and any(
            "a" in finding.implicated_objects for finding in report.returned_findings
        )
    finally:
        system.close()


def test_the_assessment_shares_the_results_evaluated_revision(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        staged = stage_complete_fixture(system, WIDER, provenance=OWNER)
        report = _assessment(system)
        assert report.evaluated_revision == staged.evaluated_revision == 1
    finally:
        system.close()


def test_a_delta_write_that_cannot_be_answered_reports_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system = _system(tmp_path)
    try:
        monkeypatch.setattr(
            system.store,
            "stage_definition_change",
            lambda *args, **kwargs: (_ for _ in ()).throw(StoreError("unavailable")),
        )
        result = system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(PROJECT,)), provenance=OWNER
        )
        assert result.status is OperationStatus.FAILED
    finally:
        system.close()


def test_a_commit_that_cannot_be_appended_reports_failure_without_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system = _system(tmp_path)
    try:
        before = materialize_state(system)
        monkeypatch.setattr(
            system.store,
            "_append_proposal_transition_unlocked",
            lambda *args, **kwargs: (_ for _ in ()).throw(StoreError("unavailable")),
        )
        result = system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(PROJECT,)), provenance=OWNER
        )
        assert result.status is OperationStatus.FAILED
        assert semantic_state_equal(materialize_state(system), before)
    finally:
        system.close()


def test_staging_describes_the_commit_it_made_without_reading_the_store_again(
    tmp_path: Path,
) -> None:
    system = _system(tmp_path)
    try:
        result = system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(PROJECT,)), provenance=OWNER
        )
        assert result.accepted and result.resulting_revision == 1
        assert "revision 1" in result.summary
    finally:
        system.close()


def test_the_whole_proposal_can_be_compared_with_focused_active_views(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        assert stage_complete_fixture(system, WIDER, provenance=OWNER).accepted
        proposal = materialize_definitions(system, prospective=True)
        assert {value.type_key for value in proposal.anchor_types} == {"person", "project"}
        assert system.definition_summary().delta_present is True
    finally:
        system.close()


def test_correcting_a_duplicated_member_of_a_referenced_set_is_a_real_change(
    tmp_path: Path,
) -> None:
    system = _system(tmp_path)
    try:
        invalid = AssociatedDataTypeDefinition("note", ("person", "person"), description="A note.")
        first = system.set_definition_delta(
            DefinitionChange(
                anchor_type_upserts=(PROJECT,), associated_data_type_upserts=(invalid,)
            ),
            provenance=OWNER,
        )
        corrected = system.set_definition_delta(
            DefinitionChange(associated_data_type_upserts=(NOTE,)), provenance=OWNER
        )
        assert first.accepted and corrected.accepted
        assert corrected.resulting_revision == 2
    finally:
        system.close()


def test_a_refused_activation_says_which_of_the_reasons_it_was(tmp_path: Path) -> None:
    """The caller's next move differs by reason, so the refusal has to name one.

    A nonconforming assessment means repair the proposal; a moved proposal or moved staged
    work means assess again. Told only that the assessment is "missing, stale, or
    nonconforming", a caller has to run another assessment to learn what it was already in
    a position to be told.
    """
    from vellis.governance import ActivateDefinitionDeltaRequest

    system = _system(tmp_path)
    try:
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(AnchorTypeDefinition("project"),)),
            provenance=OWNER,
        ).accepted
        nonconforming = _assessment(system)
        assert not nonconforming.conforms and nonconforming.assessment_id is not None
        refused = system.activate_definition_delta(
            ActivateDefinitionDeltaRequest(nonconforming.assessment_id), provenance=OWNER
        )
        assert not refused.accepted
        assert "nonconforming" in refused.findings[0].summary

        unknown = system.activate_definition_delta(
            ActivateDefinitionDeltaRequest("no-such-assessment"), provenance=OWNER
        )
        assert not unknown.accepted
        assert "was ever recorded" in unknown.findings[0].summary

        assert stage_complete_fixture(system, WIDER, provenance=OWNER).accepted
        conforming = _assessment(system)
        assert conforming.conforms and conforming.assessment_id is not None
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(AnchorTypeDefinition("team", "A team."),)),
            provenance=OWNER,
        ).accepted
        moved = system.activate_definition_delta(
            ActivateDefinitionDeltaRequest(conforming.assessment_id), provenance=OWNER
        )
        assert not moved.accepted
        assert "definitions changed" in moved.findings[0].summary
    finally:
        system.close()


def test_a_removal_that_orphans_a_reference_is_refused_after_an_earlier_activation(
    tmp_path: Path,
) -> None:
    """Assessment must keep seeing referencing definitions once the set has an overlay.

    Activating a proposal leaves the active vocabulary resolved through an overlay rather
    than held in one set. Scope selection that looks only in the active set then stops
    finding the untouched definitions that still name a removed type, and the owner is
    told a proposal conforms when activating it would install a vocabulary this system's
    own definition validation rejects. The removal here is the same one a fresh system
    refuses, and the only difference is the unrelated activation before it.
    """
    system = _system(tmp_path)
    try:
        assert stage_complete_fixture(system, WIDER, provenance=OWNER).accepted
        assert activate_clean_delta(system, provenance=OWNER).accepted

        assert system.set_definition_delta(
            DefinitionChange(type_removals=("person",)), provenance=OWNER
        ).accepted
        report = _assessment(system)

        assert not report.conforms, "orphaning 'note' by removing 'person' must not conform"
        assert any(
            "note" in finding.summary and "person" in finding.summary
            for finding in report.returned_findings
        ), [finding.summary for finding in report.returned_findings]
    finally:
        system.close()


def test_a_removal_that_orphans_a_multiplicity_rule_is_refused_after_an_activation(
    tmp_path: Path,
) -> None:
    """The same overlay resolution has to reach multiplicity rules.

    Here nothing but the rule names the removed type: the data type permits 'project', so
    a permission check alone would find nothing. An untouched rule lives in the base set
    after an activation exactly as an untouched type does.
    """
    from vellis.definitions import DirectAssociationEnd, DirectAssociationMultiplicityConstraint

    note_on_project = AssociatedDataTypeDefinition(
        "note",
        ("project",),
        (PropertyConstraint("title", True, JsonKind.STRING, description="A title."),),
        "A note.",
    )
    rule = DirectAssociationMultiplicityConstraint(
        constrained_end=DirectAssociationEnd.ANCHOR,
        anchor_type_keys=("person",),
        associated_data_type_keys=("note",),
        lower_bound=0,
        upper_bound=1,
        description="Each person has at most one note.",
    )
    start = GraphDefinitionSet(
        anchor_types=(PERSON, PROJECT),
        associated_data_types=(note_on_project,),
        relationship_constraints=(rule,),
    )
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        assert system.initialize_fresh(
            start, provenance=OWNER, initialization_summary="fresh"
        ).accepted
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(AnchorTypeDefinition("place", "A place."),)),
            provenance=OWNER,
        ).accepted
        assert activate_clean_delta(system, provenance=OWNER).accepted

        assert system.set_definition_delta(
            DefinitionChange(type_removals=("person",)), provenance=OWNER
        ).accepted
        report = _assessment(system)

        assert not report.conforms, "a rule naming a removed anchor type must not conform"
        assert any("person" in finding.summary for finding in report.returned_findings), [
            finding.summary for finding in report.returned_findings
        ]
    finally:
        system.close()
