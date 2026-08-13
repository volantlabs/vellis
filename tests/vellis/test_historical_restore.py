"""Evidence for ``VellisVerification::restoreHistory``.

Restoration moves forward. The selected state becomes the next revision and everything
already in the ledger stays where it is, so going back is itself a thing that happened —
and an owner who went back by mistake can go back from that.

The other half is the refusal: a proposal in flight blocks it, because the restored state
carries none and restoring over one would throw away work nobody asked to lose.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import build_rich_definitions

from tests.vellis.evolution_support import activate_clean_delta, stage_complete_fixture
from vellis.canonical import Provenance, TransitionKind, canonical_state_equal, now
from vellis.changes import GraphChange
from vellis.definitions import AnchorTypeDefinition, GraphDefinitionSet
from vellis.graph import Anchor, graph_equal
from vellis.history import RevisionSelection, TimeSelection
from vellis.outcomes import OperationStatus
from vellis.query import EvaluatedStateScope
from vellis.system import RTGSystem

WIDER = GraphDefinitionSet(
    anchor_types=(
        *build_rich_definitions().anchor_types,
        AnchorTypeDefinition(type_key="team", description="A group of people."),
    ),
    associated_data_types=build_rich_definitions().associated_data_types,
    link_types=build_rich_definitions().link_types,
    relationship_constraints=build_rich_definitions().relationship_constraints,
)


def _owner() -> Provenance:
    return Provenance(initiator="owner")


@pytest.fixture
def system(tmp_path: Path):
    """Revision 0: a fresh start. 1: Ada. 2: Grace. 3: Ada removed."""
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    assert system.initialize_fresh(
        build_rich_definitions(), provenance=_owner(), initialization_summary="a fresh start"
    ).accepted
    for uuid, name in (("a-1", "Ada"), ("a-2", "Grace")):
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor(uuid, "person", name),)), provenance=_owner()
        ).accepted
    assert system.apply_graph_change(
        GraphChange(anchor_removals=("a-1",)), provenance=_owner()
    ).accepted
    assert system.current_state().revision == 3
    try:
        yield system
    finally:
        system.close()


def _records(system: RTGSystem):
    return tuple(
        (record.prior_revision, record.resulting_revision, record.kind)
        for record in system.store.transitions()
    )


# --- Going back is a step forward -----------------------------------------------------


def test_restoring_commits_the_selected_state_as_a_new_revision(system: RTGSystem) -> None:
    """Asserted against what revision 2 actually held, not against a rebuild of it."""
    outcome = system.restore_historical_state(RevisionSelection(2), provenance=_owner())

    assert outcome.accepted, outcome.findings
    assert outcome.resulting_revision == 4
    current = system.current_state()
    assert current.revision == 4
    assert {anchor.uuid for anchor in current.graph.anchors} == {"a-1", "a-2"}
    assert current.definition_delta is None


def test_every_earlier_record_is_left_exactly_as_it_was(system: RTGSystem) -> None:
    """Excludes rewriting history to make the past current."""
    before = _records(system)

    assert system.restore_historical_state(RevisionSelection(1), provenance=_owner()).accepted

    after = _records(system)
    assert after[: len(before)] == before
    assert len(after) == len(before) + 1
    assert after[-1] == (3, 4, TransitionKind.HISTORICAL_RESTORATION)


def test_the_restored_state_can_itself_be_left_behind(system: RTGSystem) -> None:
    """An owner who went back by mistake is not stuck there."""
    before = system.current_state()

    assert system.restore_historical_state(RevisionSelection(1), provenance=_owner()).accepted
    assert system.current_state().graph.anchor("a-2") is None

    assert system.restore_historical_state(RevisionSelection(3), provenance=_owner()).accepted

    restored = system.current_state()
    assert restored.revision == 5
    assert graph_equal(restored.graph, before.graph)


def test_restoring_by_time_selects_the_same_state(system: RTGSystem) -> None:
    from vellis.activity import HistoryKind, HistoryQuery

    at_two = next(
        entry.recorded_at
        for entry in system.history(
            HistoryQuery(kind=HistoryKind.CANONICAL, maximum_records=100)
        ).canonical_entries
        if entry.revision == 2
    )
    assert system.restore_historical_state(TimeSelection(at_two), provenance=_owner()).accepted

    assert {anchor.uuid for anchor in system.current_state().graph.anchors} == {"a-1", "a-2"}


def test_a_restored_state_replays_from_the_ledger(system: RTGSystem) -> None:
    """A restoration is an ordinary record: replay reaches the same place."""
    assert system.restore_historical_state(RevisionSelection(1), provenance=_owner()).accepted

    assert canonical_state_equal(system.current_state(), system.replay())


def test_a_restoration_survives_an_ordinary_restart(tmp_path: Path) -> None:
    path = tmp_path / "vellis.sqlite3"
    system = RTGSystem.open(path)
    try:
        assert system.initialize_fresh(
            build_rich_definitions(), provenance=_owner(), initialization_summary="a fresh start"
        ).accepted
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-1", "person", "Ada"),)), provenance=_owner()
        ).accepted
        assert system.restore_historical_state(RevisionSelection(0), provenance=_owner()).accepted
        expected = system.current_state()
    finally:
        system.close()

    reopened = RTGSystem.open(path)
    try:
        assert canonical_state_equal(reopened.current_state(), expected)
        assert canonical_state_equal(reopened.replay(), expected)
    finally:
        reopened.close()


# --- What it refuses ------------------------------------------------------------------


def test_a_proposal_in_flight_blocks_restoration(system: RTGSystem) -> None:
    """Excludes discarding an owner's draft to make room for the past."""
    assert stage_complete_fixture(system, WIDER, provenance=_owner()).accepted
    before = system.current_state()
    records = _records(system)

    outcome = system.restore_historical_state(RevisionSelection(1), provenance=_owner())

    assert outcome.status is OperationStatus.REJECTED
    assert outcome.resulting_revision is None
    assert any("in-flight definition delta" in f.summary for f in outcome.findings)
    assert canonical_state_equal(system.current_state(), before)
    assert _records(system) == records


def test_restoring_after_the_proposal_is_resolved_succeeds(system: RTGSystem) -> None:
    assert stage_complete_fixture(system, WIDER, provenance=_owner()).accepted
    assert not system.restore_historical_state(RevisionSelection(1), provenance=_owner()).accepted

    assert system.discard_definition_delta(provenance=_owner()).accepted

    assert system.restore_historical_state(RevisionSelection(1), provenance=_owner()).accepted


@pytest.mark.parametrize(
    ("selection", "expected"),
    (
        (RevisionSelection(99), "no record in this ledger established revision 99"),
        (RevisionSelection(-1), "names a committed revision"),
    ),
    ids=["unknown-revision", "negative-revision"],
)
def test_an_unresolvable_selection_changes_nothing(
    system: RTGSystem, selection, expected: str
) -> None:
    before = system.current_state()
    records = _records(system)

    outcome = system.restore_historical_state(selection, provenance=_owner())

    assert outcome.status is OperationStatus.REJECTED
    assert outcome.resulting_revision is None
    assert any(expected in finding.summary for finding in outcome.findings)
    assert canonical_state_equal(system.current_state(), before)
    assert _records(system) == records


def test_a_refused_restoration_is_observed(system: RTGSystem) -> None:
    from vellis.activity import HistoryKind, HistoryQuery

    assert stage_complete_fixture(system, WIDER, provenance=_owner()).accepted
    assert not system.restore_historical_state(RevisionSelection(1), provenance=_owner()).accepted

    entries = system.history(
        HistoryQuery(kind=HistoryKind.ACTIVITY, maximum_records=100)
    ).activity_entries
    recorded = next(entry for entry in entries if entry.capability == "restoration")
    assert recorded.outcome_category is OperationStatus.REJECTED
    assert "revision 1" in recorded.semantic_scope


def test_an_accepted_restoration_is_canonical_authority_not_an_observation(
    system: RTGSystem,
) -> None:
    before = system.store.activity_record_count()

    assert system.restore_historical_state(RevisionSelection(1), provenance=_owner()).accepted

    assert system.store.activity_record_count() == before


# --- The vocabulary goes back too ------------------------------------------------------


@pytest.fixture
def widened(tmp_path: Path):
    """Revision 0: the rich vocabulary. 1: a team anchor. 2: a wider vocabulary activated."""
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    assert system.initialize_fresh(
        build_rich_definitions(), provenance=_owner(), initialization_summary="a fresh start"
    ).accepted
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("a-1", "person", "Ada"),)), provenance=_owner()
    ).accepted
    assert stage_complete_fixture(system, WIDER, provenance=_owner()).accepted
    assert activate_clean_delta(system, provenance=_owner()).accepted
    assert {each.type_key for each in system.current_state().active_definitions.anchor_types} == {
        "person",
        "project",
        "team",
    }
    try:
        yield system
    finally:
        system.close()


def test_restoring_takes_the_vocabulary_back_as_well_as_the_graph(widened: RTGSystem) -> None:
    """Excludes restoring the graph while keeping today's vocabulary.

    The requirement says graph *and* active definitions. Without a vocabulary that
    changed between the two revisions, an implementation that kept the current one would
    be indistinguishable.
    """
    assert widened.restore_historical_state(RevisionSelection(1), provenance=_owner()).accepted

    current = widened.current_state()
    assert {each.type_key for each in current.active_definitions.anchor_types} == {
        "person",
        "project",
    }
    assert {anchor.uuid for anchor in current.graph.anchors} == {"a-1"}


def test_the_committed_record_carries_the_historical_vocabulary(widened: RTGSystem) -> None:
    """Excludes a record that says one thing while the projection says another."""
    assert widened.restore_historical_state(RevisionSelection(1), provenance=_owner()).accepted

    record = widened.store.transitions()[-1]
    assert record.kind is TransitionKind.HISTORICAL_RESTORATION
    assert record.change.active_definitions is not None
    assert {each.type_key for each in record.change.active_definitions.anchor_types} == {
        "person",
        "project",
    }
    assert canonical_state_equal(widened.replay(), widened.current_state())


def test_a_historical_summary_after_a_restoration_reports_the_restored_vocabulary(
    widened: RTGSystem,
) -> None:
    assert widened.restore_historical_state(RevisionSelection(1), provenance=_owner()).accepted

    summary = widened.definition_summary(
        state_scope=EvaluatedStateScope.HISTORICAL,
        selection=RevisionSelection(widened.current_state().revision),
        provenance=_owner(),
    )

    assert summary.accepted, summary.findings
    assert {each.type_key for each in summary.anchor_types} == {"person", "project"}


# --- Restoring where you already are ---------------------------------------------------


def test_restoring_the_state_already_current_creates_neither_revision_nor_record(
    system: RTGSystem,
) -> None:
    """``atomicTransitions``: an effective no-op creates neither revision nor record."""
    before = system.current_state()
    records = _records(system)

    outcome = system.restore_historical_state(RevisionSelection(3), provenance=_owner())

    assert outcome.status is OperationStatus.ACCEPTED
    assert outcome.resulting_revision is None
    assert canonical_state_equal(system.current_state(), before)
    assert _records(system) == records


def test_restoring_twice_over_moves_only_once(system: RTGSystem) -> None:
    assert system.restore_historical_state(RevisionSelection(1), provenance=_owner()).accepted
    after_first = _records(system)

    second = system.restore_historical_state(RevisionSelection(1), provenance=_owner())

    assert second.accepted, second.findings
    assert second.resulting_revision is None
    assert _records(system) == after_first


# --- Failure and precondition ----------------------------------------------------------


def test_restoring_before_a_system_exists_is_refused(tmp_path: Path) -> None:
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        outcome = system.restore_historical_state(RevisionSelection(0), provenance=_owner())

        assert outcome.status is OperationStatus.REJECTED
        assert outcome.resulting_revision is None
        assert not system.is_initialized
    finally:
        system.close()


def test_a_ledger_that_cannot_be_replayed_reports_a_failure(system: RTGSystem) -> None:
    """Explicit SQL replay verification reports projection/ledger divergence."""
    system.store._connection.execute(  # noqa: SLF001
        "UPDATE canonical_graph_event SET operation = 'delete', object_value_id = NULL"
        " WHERE established_revision = 2"
    )
    system.store._connection.commit()  # noqa: SLF001

    findings = system.store.verify_projection_from_ledger()

    assert findings
    assert "normalized events" in findings[0].summary


def test_a_time_selection_is_named_in_its_observation(system: RTGSystem) -> None:
    from vellis.activity import HistoryKind, HistoryQuery

    assert stage_complete_fixture(system, WIDER, provenance=_owner()).accepted
    moment = now()
    assert not system.restore_historical_state(TimeSelection(moment), provenance=_owner()).accepted

    entries = system.history(
        HistoryQuery(kind=HistoryKind.ACTIVITY, maximum_records=100)
    ).activity_entries
    recorded = next(entry for entry in entries if entry.capability == "restoration")
    assert moment.isoformat() in recorded.semantic_scope


# --- What it costs ----------------------------------------------------------------------


def test_a_refused_restoration_replays_nothing(system: RTGSystem) -> None:
    """A refusal decidable from state already in hand does not pay for a reconstruction."""
    assert stage_complete_fixture(system, WIDER, provenance=_owner()).accepted

    system.store.reset_instrumentation()
    assert not system.restore_historical_state(RevisionSelection(1), provenance=_owner()).accepted

    assert system.store.record_reads == 0
