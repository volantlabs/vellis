"""Evidence for ``VellisVerification::snapshotReplay`` and the snapshot half of
``::freshInitialization``.

A system can begin from a state that already existed somewhere else. The reconstructed
state becomes this ledger's history base at the revision it reached — not at zero,
because renumbering it would claim transitions this ledger does not have.

No starting vocabulary is offered or overlaid. A snapshot already carries one, and a
fresh-start choice on top of it would answer a question the owner already answered.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import build_rich_definitions

from vellis.canonical import Provenance, canonical_state_equal
from vellis.changes import GraphChange
from vellis.definitions import (
    AnchorTypeDefinition,
    GraphDefinitionSet,
    definition_set_equal,
)
from vellis.everyday_life import everyday_life_starter
from vellis.graph import Anchor
from vellis.history import MAXIMUM_REVISION, RevisionSelection
from vellis.outcomes import OperationStatus
from vellis.query import AnchorGroup, AnchorProjection, GraphQuery, ReturnShape
from vellis.replay import ReplayRequest
from vellis.system import RTGSystem

RICH = build_rich_definitions()
WIDER = GraphDefinitionSet(
    anchor_types=(
        *RICH.anchor_types,
        AnchorTypeDefinition(type_key="team", description="A group of people."),
    ),
    associated_data_types=RICH.associated_data_types,
    link_types=RICH.link_types,
    relationship_constraints=RICH.relationship_constraints,
)


def _owner() -> Provenance:
    return Provenance(initiator="owner")


@pytest.fixture
def source(tmp_path: Path):
    """A system with a history: two anchors, then a widened vocabulary."""
    system = RTGSystem.open(tmp_path / "source.sqlite3")
    assert system.initialize_fresh(
        build_rich_definitions(), provenance=_owner(), initialization_summary="a fresh start"
    ).accepted
    for uuid, name in (("a-1", "Ada"), ("a-2", "Grace")):
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor(uuid, "person", name),)), provenance=_owner()
        ).accepted
    assert system.set_definition_delta(WIDER, provenance=_owner()).accepted
    assert system.activate_definition_delta(provenance=_owner()).accepted
    assert system.current_state().revision == 4
    try:
        yield system
    finally:
        system.close()


def _begin(tmp_path: Path, request: ReplayRequest, name: str = "fresh.sqlite3") -> RTGSystem:
    system = RTGSystem.open(tmp_path / name)
    outcome = system.initialize_from_snapshot(
        request, provenance=_owner(), initialization_summary="begun from a snapshot"
    )
    assert outcome.accepted, outcome.findings
    return system


def _people() -> GraphQuery:
    return GraphQuery(
        anchor_groups=(AnchorGroup(name="who", anchor_type="person"),),
        return_shape=ReturnShape(projections=(AnchorProjection(name="p", anchor_group="who"),)),
        maximum_rows=10,
    )


# --- Beginning from a capture ---------------------------------------------------------


def test_a_snapshot_establishes_the_state_it_captured(tmp_path: Path, source: RTGSystem) -> None:
    snapshot = source.create_snapshot(provenance=_owner()).snapshot
    assert snapshot is not None

    fresh = _begin(tmp_path, ReplayRequest(snapshot=snapshot))
    try:
        current = fresh.current_state()
        assert canonical_state_equal(current, source.current_state())
        assert current.revision == 4
    finally:
        fresh.close()


def test_a_snapshot_and_its_tail_establish_the_replayed_state(
    tmp_path: Path, source: RTGSystem
) -> None:
    """The arc the verification case walks: capture early, keep working, begin from both."""
    snapshot = source.create_snapshot(provenance=_owner()).snapshot
    assert snapshot is not None
    captured_at = snapshot.revision
    assert source.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("a-3", "person", "Hugh"),)), provenance=_owner()
    ).accepted

    fresh = _begin(
        tmp_path,
        ReplayRequest(snapshot=snapshot, tail=source.ledger_tail(after=captured_at)),
    )
    try:
        assert canonical_state_equal(fresh.current_state(), source.current_state())
        assert fresh.current_state().revision == 5
    finally:
        fresh.close()


def test_the_established_revision_is_the_one_the_state_reached(
    tmp_path: Path, source: RTGSystem
) -> None:
    """Excludes renumbering to zero, which would claim transitions this ledger lacks."""
    snapshot = source.create_snapshot(provenance=_owner()).snapshot
    assert snapshot is not None

    fresh = _begin(tmp_path, ReplayRequest(snapshot=snapshot))
    try:
        assert fresh.current_state().revision == 4
        assert fresh.store.initial_record().canonical_state.revision == 4
    finally:
        fresh.close()


def test_the_new_ledger_claims_no_earlier_transitions(tmp_path: Path, source: RTGSystem) -> None:
    """One initial record holding the whole of it, and nothing before."""
    snapshot = source.create_snapshot(provenance=_owner()).snapshot
    assert snapshot is not None

    fresh = _begin(tmp_path, ReplayRequest(snapshot=snapshot))
    try:
        assert fresh.store.transitions() == ()
        assert fresh.store.canonical_record_count() == 1
        base = fresh.store.initial_record()
        assert canonical_state_equal(base.canonical_state, fresh.current_state())
    finally:
        fresh.close()


def test_query_and_replay_agree_with_the_supplied_state(tmp_path: Path, source: RTGSystem) -> None:
    snapshot = source.create_snapshot(provenance=_owner()).snapshot
    assert snapshot is not None
    expected = {
        binding.anchor.uuid
        for row in source.query_graph(_people(), provenance=_owner()).rows
        for binding in row.anchors
    }

    fresh = _begin(tmp_path, ReplayRequest(snapshot=snapshot))
    try:
        result = fresh.query_graph(_people(), provenance=_owner())
        assert result.accepted, result.findings
        assert {b.anchor.uuid for row in result.rows for b in row.anchors} == expected
        assert result.evaluated_revision == 4
        assert canonical_state_equal(fresh.replay(), fresh.current_state())
    finally:
        fresh.close()


def test_an_in_flight_proposal_travels_with_the_snapshot(tmp_path: Path, source: RTGSystem) -> None:
    assert source.set_definition_delta(build_rich_definitions(), provenance=_owner()).accepted
    snapshot = source.create_snapshot(provenance=_owner()).snapshot
    assert snapshot is not None

    fresh = _begin(tmp_path, ReplayRequest(snapshot=snapshot))
    try:
        delta = fresh.definition_delta(provenance=_owner())
        assert delta.definition_delta is not None
        assert definition_set_equal(
            delta.definition_delta.proposed_definitions, build_rich_definitions()
        )
    finally:
        fresh.close()


def test_no_starting_vocabulary_is_overlaid(tmp_path: Path, source: RTGSystem) -> None:
    """Excludes offering a fresh-start choice on top of a vocabulary the snapshot carries."""
    snapshot = source.create_snapshot(provenance=_owner()).snapshot
    assert snapshot is not None

    fresh = _begin(tmp_path, ReplayRequest(snapshot=snapshot))
    try:
        active = fresh.current_state().active_definitions
        assert definition_set_equal(active, WIDER)
        starter = {each.type_key for each in everyday_life_starter().anchor_types}
        assert not starter & {each.type_key for each in active.anchor_types}
    finally:
        fresh.close()


def test_the_new_lineage_can_be_worked_on_from_where_it_starts(
    tmp_path: Path, source: RTGSystem
) -> None:
    """A base above zero is a real base: the next change follows it."""
    snapshot = source.create_snapshot(provenance=_owner()).snapshot
    assert snapshot is not None

    fresh = _begin(tmp_path, ReplayRequest(snapshot=snapshot))
    try:
        outcome = fresh.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-9", "person", "Ida"),)), provenance=_owner()
        )

        assert outcome.accepted, outcome.findings
        assert outcome.resulting_revision == 5
        assert canonical_state_equal(fresh.replay(), fresh.current_state())
    finally:
        fresh.close()


# --- What it refuses ------------------------------------------------------------------


def test_a_refused_reconstruction_establishes_nothing(tmp_path: Path) -> None:
    system = RTGSystem.open(tmp_path / "fresh.sqlite3")
    try:
        outcome = system.initialize_from_snapshot(
            ReplayRequest(), provenance=_owner(), initialization_summary="begun from a snapshot"
        )

        assert outcome.status is OperationStatus.REJECTED
        assert outcome.resulting_revision is None
        assert not system.is_initialized
        assert system.store.canonical_record_count() == 0
    finally:
        system.close()


def test_a_tail_from_another_ledger_establishes_nothing(tmp_path: Path, source: RTGSystem) -> None:
    other = RTGSystem.open(tmp_path / "other.sqlite3")
    system = RTGSystem.open(tmp_path / "fresh.sqlite3")
    try:
        assert other.initialize_fresh(
            build_rich_definitions(), provenance=_owner(), initialization_summary="a fresh start"
        ).accepted
        assert other.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("z-9", "person", "Someone else"),)),
            provenance=_owner(),
        ).accepted
        snapshot = source.create_snapshot(provenance=_owner()).snapshot
        assert snapshot is not None

        outcome = system.initialize_from_snapshot(
            ReplayRequest(snapshot=snapshot, tail=other.ledger_tail(after=0)),
            provenance=_owner(),
            initialization_summary="begun from a snapshot",
        )

        assert outcome.status is OperationStatus.REJECTED
        assert not system.is_initialized
        assert system.store.canonical_record_count() == 0
    finally:
        other.close()
        system.close()


def test_beginning_again_over_an_established_system_is_refused(
    tmp_path: Path, source: RTGSystem
) -> None:
    snapshot = source.create_snapshot(provenance=_owner()).snapshot
    assert snapshot is not None
    fresh = _begin(tmp_path, ReplayRequest(snapshot=snapshot))
    try:
        before = fresh.current_state()

        outcome = fresh.initialize_from_snapshot(
            ReplayRequest(snapshot=snapshot),
            provenance=_owner(),
            initialization_summary="again",
        )

        assert outcome.status is OperationStatus.REJECTED
        assert canonical_state_equal(fresh.current_state(), before)
    finally:
        fresh.close()


def test_a_state_that_does_not_conform_establishes_nothing(tmp_path: Path) -> None:
    """A history base has to be a state this system could have committed."""
    from vellis.canonical import CanonicalState
    from vellis.graph import Graph
    from vellis.replay import CanonicalSnapshot

    damaged = CanonicalSnapshot(
        canonical_state=CanonicalState(
            graph=Graph(anchors=(Anchor("x-1", "no-such-type", "X"),)),
            active_definitions=build_rich_definitions(),
            revision=7,
        ),
        captured_through="whatever",
    )
    system = RTGSystem.open(tmp_path / "fresh.sqlite3")
    try:
        outcome = system.initialize_from_snapshot(
            ReplayRequest(snapshot=damaged),
            provenance=_owner(),
            initialization_summary="begun from a snapshot",
        )

        assert outcome.status is OperationStatus.REJECTED
        assert not system.is_initialized
        assert system.store.canonical_record_count() == 0
    finally:
        system.close()


def test_a_snapshot_beginning_leaves_an_empty_activity_ledger(
    tmp_path: Path, source: RTGSystem
) -> None:
    snapshot = source.create_snapshot(provenance=_owner()).snapshot
    assert snapshot is not None
    system = RTGSystem.open(tmp_path / "fresh.sqlite3")
    try:
        assert system.query_graph(_people(), provenance=_owner()).status is (
            OperationStatus.REJECTED
        )
        assert system.store.activity_record_count() > 0

        assert system.initialize_from_snapshot(
            ReplayRequest(snapshot=snapshot),
            provenance=_owner(),
            initialization_summary="begun from a snapshot",
        ).accepted

        assert system.store.activity_record_count() == 0
    finally:
        system.close()


# --- A base above zero is a real base ---------------------------------------------------


def _snapshot_of(system: RTGSystem):
    snapshot = system.create_snapshot(provenance=_owner()).snapshot
    assert snapshot is not None
    return snapshot


def test_a_snapshot_founded_ledger_survives_an_ordinary_restart(
    tmp_path: Path, source: RTGSystem
) -> None:
    """The first ledger shape whose base is not revision zero."""
    path = tmp_path / "fresh.sqlite3"
    fresh = _begin(tmp_path, ReplayRequest(snapshot=_snapshot_of(source)))
    try:
        expected = fresh.current_state()
    finally:
        fresh.close()

    reopened = RTGSystem.open(path)
    try:
        assert canonical_state_equal(reopened.current_state(), expected)
        assert canonical_state_equal(reopened.replay(), expected)
        assert reopened.store.initial_record().canonical_state.revision == 4
    finally:
        reopened.close()


def test_a_snapshot_founded_ledger_can_itself_be_captured_and_tailed(
    tmp_path: Path, source: RTGSystem
) -> None:
    """Excludes anything downstream that assumed a ledger starts at zero."""
    second = _begin(tmp_path, ReplayRequest(snapshot=_snapshot_of(source)), "second.sqlite3")
    try:
        captured = _snapshot_of(second)
        assert second.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-9", "person", "Ida"),)), provenance=_owner()
        ).accepted
        tail = second.ledger_tail(after=captured.revision)

        third = _begin(tmp_path, ReplayRequest(snapshot=captured, tail=tail), "third.sqlite3")
        try:
            assert canonical_state_equal(third.current_state(), second.current_state())
            assert third.current_state().revision == 5
        finally:
            third.close()
    finally:
        second.close()


def test_a_selection_below_the_base_names_no_record(tmp_path: Path, source: RTGSystem) -> None:
    """The lineage starts partway through, and says so rather than inventing a past."""
    fresh = _begin(tmp_path, ReplayRequest(snapshot=_snapshot_of(source)))
    try:
        below = fresh.definition_summary(selection=RevisionSelection(1), provenance=_owner())
        at_base = fresh.definition_summary(selection=RevisionSelection(4), provenance=_owner())

        assert below.status is OperationStatus.REJECTED
        assert below.evaluated_revision is None
        assert at_base.accepted, at_base.findings
        assert at_base.evaluated_revision == 4
    finally:
        fresh.close()


def test_the_base_projects_as_an_initial_history_entry_at_its_own_revision(
    tmp_path: Path, source: RTGSystem
) -> None:
    from vellis.activity import HistoryKind, HistoryQuery

    fresh = _begin(tmp_path, ReplayRequest(snapshot=_snapshot_of(source)))
    try:
        entries = fresh.history(
            HistoryQuery(kind=HistoryKind.CANONICAL, maximum_records=100)
        ).canonical_entries

        assert len(entries) == 1
        assert entries[0].revision == 4
        assert entries[0].prior_revision is None
        assert entries[0].transition_kind is None
    finally:
        fresh.close()


# --- Bounds and failures ----------------------------------------------------------------


@pytest.mark.parametrize("revision", (-1, MAXIMUM_REVISION + 1), ids=["below-zero", "above-range"])
def test_a_base_revision_no_ledger_could_hold_establishes_nothing(
    tmp_path: Path, revision: int
) -> None:
    """Excludes a history whose own base no read path can name.

    Below zero every selector refuses it; above the ledger's range the next transition
    could never be written. Either way the memory would be founded on a number it cannot
    live with.
    """
    from vellis.canonical import CanonicalState
    from vellis.graph import Graph
    from vellis.replay import CanonicalSnapshot

    system = RTGSystem.open(tmp_path / "fresh.sqlite3")
    try:
        outcome = system.initialize_from_snapshot(
            ReplayRequest(
                snapshot=CanonicalSnapshot(
                    canonical_state=CanonicalState(
                        graph=Graph(), active_definitions=RICH, revision=revision
                    ),
                    captured_through="whatever",
                )
            ),
            provenance=_owner(),
            initialization_summary="begun from a snapshot",
        )

        assert outcome.status is OperationStatus.REJECTED
        assert outcome.resulting_revision is None
        assert not system.is_initialized
    finally:
        system.close()


def test_unstorable_record_text_establishes_nothing(tmp_path: Path, source: RTGSystem) -> None:
    system = RTGSystem.open(tmp_path / "fresh.sqlite3")
    try:
        outcome = system.initialize_from_snapshot(
            ReplayRequest(snapshot=_snapshot_of(source)),
            provenance=Provenance(initiator="Gr\ud800ce"),
            initialization_summary="begun from a snapshot",
        )

        assert outcome.status is OperationStatus.REJECTED
        assert not system.is_initialized
    finally:
        system.close()


def test_the_outcome_reports_the_revision_it_established(tmp_path: Path, source: RTGSystem) -> None:
    """Excludes an outcome that says zero while the ledger says otherwise."""
    system = RTGSystem.open(tmp_path / "fresh.sqlite3")
    try:
        outcome = system.initialize_from_snapshot(
            ReplayRequest(snapshot=_snapshot_of(source)),
            provenance=_owner(),
            initialization_summary="begun from a snapshot",
        )

        assert outcome.accepted, outcome.findings
        assert outcome.resulting_revision == 4
        assert "revision 4" in outcome.summary
    finally:
        system.close()
