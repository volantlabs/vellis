"""Evidence for ``VellisVerification::snapshotCompleteness``, ``::snapshotReplay``, and
``::invalidTail``.

Three cases with one shape between them: a snapshot must be complete enough to stand in
for the history it replaces, a tail must rebuild exactly what the live system holds, and
a tail that does not belong must be refused rather than quietly producing a state that
never existed.

Initializing a fresh RTG from a snapshot is the slice that seeds owned history; what is
here is the reconstruction it will use.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import build_rich_definitions

from vellis.canonical import (
    CanonicalChange,
    CanonicalTransitionRecord,
    Provenance,
    TransitionKind,
    canonical_state_equal,
    now,
)
from vellis.changes import GraphChange
from vellis.definitions import AnchorTypeDefinition, GraphDefinitionSet, definition_set_equal
from vellis.graph import Anchor, graph_equal
from vellis.outcomes import OperationStatus
from vellis.replay import LedgerTail, ReplayRequest, reconstruct, record_identity
from vellis.system import RTGSystem

ADA = Anchor(uuid="a-1", type_key="person", display_name="Ada")
ORBIT = Anchor(uuid="p-1", type_key="project", display_name="Orbit")
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


def _fresh(tmp_path: Path, name: str = "vellis.sqlite3") -> RTGSystem:
    system = RTGSystem.open(tmp_path / name)
    assert system.initialize_fresh(
        build_rich_definitions(), provenance=_owner(), initialization_summary="a fresh start"
    ).accepted
    return system


@pytest.fixture
def system(tmp_path: Path):
    system = _fresh(tmp_path)
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(ADA, ORBIT)), provenance=_owner()
    ).accepted
    try:
        yield system
    finally:
        system.close()


# --- A snapshot is complete, and captures nothing but a copy --------------------------


def test_a_snapshot_captures_the_whole_state_at_its_revision(system: RTGSystem) -> None:
    result = system.create_snapshot(provenance=_owner())

    assert result.accepted, result.findings
    snapshot = result.snapshot
    assert snapshot is not None
    live = system.current_state()
    assert snapshot.revision == live.revision
    assert graph_equal(snapshot.canonical_state.graph, live.graph)
    assert definition_set_equal(
        snapshot.canonical_state.active_definitions, live.active_definitions
    )
    assert snapshot.canonical_state.definition_delta is None


def test_a_snapshot_carries_an_in_flight_delta(system: RTGSystem) -> None:
    """Excludes capturing only what is active: the proposal is canonical state too."""
    assert system.set_definition_delta(WIDER, provenance=_owner()).accepted

    snapshot = system.create_snapshot(provenance=_owner()).snapshot

    assert snapshot is not None
    delta = snapshot.canonical_state.definition_delta
    assert delta is not None
    assert definition_set_equal(delta.proposed_definitions, WIDER)


def test_a_snapshot_identifies_the_record_that_established_its_revision(
    system: RTGSystem,
) -> None:
    snapshot = system.create_snapshot(provenance=_owner()).snapshot

    assert snapshot is not None
    assert snapshot.captured_through == record_identity(
        system.store.transitions()[-1], follows=system.base_identity()
    )


def test_capturing_changes_no_canonical_state_revision_or_history(system: RTGSystem) -> None:
    before = system.current_state()
    records = system.store.canonical_record_count()

    assert system.create_snapshot(provenance=_owner()).accepted

    assert canonical_state_equal(system.current_state(), before)
    assert system.store.canonical_record_count() == records


def test_capturing_before_a_system_exists_is_refused(tmp_path: Path) -> None:
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        result = system.create_snapshot(provenance=_owner())

        assert result.status is OperationStatus.REJECTED
        assert result.snapshot is None
    finally:
        system.close()


# --- A snapshot plus its tail rebuilds what the system holds --------------------------


def test_a_snapshot_alone_reconstructs_its_own_revision(system: RTGSystem) -> None:
    snapshot = system.create_snapshot(provenance=_owner()).snapshot
    assert snapshot is not None

    result = system.reconstruct_state(ReplayRequest(snapshot=snapshot), provenance=_owner())

    assert result.accepted, result.findings
    assert canonical_state_equal(result.canonical_state, system.current_state())  # pyright: ignore[reportArgumentType]


def test_a_snapshot_and_its_later_tail_reconstruct_the_current_state(
    system: RTGSystem,
) -> None:
    """The arc the verification case walks: capture early, keep working, rebuild."""
    snapshot = system.create_snapshot(provenance=_owner()).snapshot
    assert snapshot is not None
    captured_at = snapshot.revision

    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("a-2", "person", "Grace"),)), provenance=_owner()
    ).accepted
    assert system.set_definition_delta(WIDER, provenance=_owner()).accepted

    tail = system.ledger_tail(after=captured_at)
    assert tail is not None
    result = system.reconstruct_state(
        ReplayRequest(snapshot=snapshot, tail=tail), provenance=_owner()
    )

    assert result.accepted, result.findings
    rebuilt = result.canonical_state
    assert rebuilt is not None
    live = system.current_state()
    assert rebuilt.revision == live.revision
    assert canonical_state_equal(rebuilt, live)


def test_an_initial_record_and_its_whole_tail_reconstruct_the_current_state(
    system: RTGSystem,
) -> None:
    """The other permitted base, from the beginning of owned history."""
    initial = system.store.initial_record()
    tail = system.ledger_tail(after=initial.canonical_state.revision)
    assert tail is not None

    result = system.reconstruct_state(
        ReplayRequest(initial=initial, tail=tail, base_identity=system.base_identity()),
        provenance=_owner(),
    )

    assert result.accepted, result.findings
    assert canonical_state_equal(result.canonical_state, system.current_state())  # pyright: ignore[reportArgumentType]


def test_reconstruction_reads_no_activity_history(system: RTGSystem) -> None:
    """Excludes a reconstruction that consults the ledger the owner may empty."""
    snapshot = system.create_snapshot(provenance=_owner()).snapshot
    assert snapshot is not None
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("a-2", "person", "Grace"),)), provenance=_owner()
    ).accepted
    tail = system.ledger_tail(after=snapshot.revision)
    assert tail is not None
    before = reconstruct(ReplayRequest(snapshot=snapshot, tail=tail)).canonical_state

    system.store._connection.execute("DELETE FROM activity_record")  # noqa: SLF001
    system.store._connection.commit()  # noqa: SLF001

    after = reconstruct(ReplayRequest(snapshot=snapshot, tail=tail)).canonical_state
    assert canonical_state_equal(after, before)  # pyright: ignore[reportArgumentType]


def test_reconstruction_changes_no_live_state(system: RTGSystem) -> None:
    snapshot = system.create_snapshot(provenance=_owner()).snapshot
    assert snapshot is not None
    before = system.current_state()
    records = system.store.canonical_record_count()

    assert system.reconstruct_state(ReplayRequest(snapshot=snapshot), provenance=_owner()).accepted

    assert canonical_state_equal(system.current_state(), before)
    assert system.store.canonical_record_count() == records


# --- A tail that does not belong is refused -------------------------------------------


def _tail_of(system: RTGSystem) -> LedgerTail:
    return system.ledger_tail(after=0)


def _chained(preceding: str, transitions: tuple[CanonicalTransitionRecord, ...]) -> LedgerTail:
    """Build a tail that correctly names where it ends, so a case tests one thing."""
    identity = preceding
    for record in transitions:
        identity = record_identity(record, follows=identity)
    return LedgerTail(preceding_record=preceding, transitions=transitions, final_record=identity)


def test_two_ledgers_built_from_identical_content_have_different_identities(
    tmp_path: Path,
) -> None:
    """Excludes an identity that is only a digest of what a record contains.

    Two systems seeded the same way hold byte-identical records. If identity came from
    content alone they would be one history, and one's tail would graft onto the other's
    base producing a state neither ever held. The chain is rooted in a value only one
    ledger has, so lineage is part of what a record is.
    """
    first = _fresh(tmp_path, "first.sqlite3")
    second = _fresh(tmp_path, "second.sqlite3")
    try:
        assert canonical_state_equal(first.current_state(), second.current_state())
        assert first.base_identity() != second.base_identity()
    finally:
        first.close()
        second.close()


def test_a_tail_cannot_be_grafted_onto_an_identical_looking_base(tmp_path: Path) -> None:
    """The graft the identity chain exists to refuse, built to be as similar as possible."""
    first = _fresh(tmp_path, "first.sqlite3")
    second = _fresh(tmp_path, "second.sqlite3")
    try:
        assert second.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("z-9", "person", "Someone else"),)),
            provenance=_owner(),
        ).accepted

        result = reconstruct(
            ReplayRequest(
                initial=first.store.initial_record(),
                tail=second.ledger_tail(after=0),
                base_identity=first.base_identity(),
            )
        )

        assert result.status is OperationStatus.REJECTED
        assert result.canonical_state is None
        assert any("different record" in finding.summary for finding in result.findings)
    finally:
        first.close()
        second.close()


@pytest.mark.parametrize(
    "differ",
    (
        "definitions",
        "summary",
        "provenance",
    ),
)
def test_every_distinguishing_field_participates_in_a_base_identity(
    tmp_path: Path, differ: str
) -> None:
    """Excludes an identity that ignores what a record actually says."""
    from vellis.replay import record_identity as identity_of

    base = build_rich_definitions()
    record = RTGSystem.open(tmp_path / "one.sqlite3")
    try:
        assert record.initialize_fresh(
            base, provenance=_owner(), initialization_summary="a fresh start"
        ).accepted
        original = record.store.initial_record()
        ledger = record.store.ledger_identity()
    finally:
        record.close()

    from dataclasses import replace

    altered = {
        "definitions": replace(
            original,
            canonical_state=replace(original.canonical_state, active_definitions=WIDER),
        ),
        "summary": replace(original, initialization_summary="a different start"),
        "provenance": replace(original, provenance=Provenance(initiator="someone else")),
    }[differ]

    assert identity_of(original, follows=ledger) != identity_of(altered, follows=ledger)


def test_a_transition_identity_follows_its_change_and_its_place(system: RTGSystem) -> None:
    from vellis.replay import record_identity as identity_of

    base = system.base_identity()
    original = system.store.transitions()[0]

    from dataclasses import replace

    assert identity_of(original, follows=base) != identity_of(
        replace(original, change=CanonicalChange(graph_change=GraphChange())), follows=base
    )
    assert identity_of(original, follows=base) != identity_of(original, follows="elsewhere")
    assert identity_of(original, follows=base) != identity_of(
        replace(original, prior_revision=5), follows=base
    )
    assert identity_of(original, follows=base) != identity_of(
        replace(original, resulting_revision=6), follows=base
    )


def test_an_identity_survives_the_store_round_trip(tmp_path: Path) -> None:
    """Excludes an identity that changes when a record is read back.

    A tail names what it follows by identity, so a record must have the same identity in
    memory and after it has been through the store — including its recorded time.
    """
    system = _fresh(tmp_path)
    try:
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(ADA,)), provenance=_owner()
        ).accepted
        before = system.base_identity()
        tail_before = system.ledger_tail(after=0)
        path = system.store.path
    finally:
        system.close()

    reopened = RTGSystem.open(path)
    try:
        assert reopened.base_identity() == before
        assert reopened.ledger_tail(after=0).preceding_record == tail_before.preceding_record
        result = reopened.reconstruct_state(
            ReplayRequest(
                initial=reopened.store.initial_record(),
                tail=reopened.ledger_tail(after=0),
                base_identity=reopened.base_identity(),
            ),
            provenance=_owner(),
        )
        assert result.accepted, result.findings
        assert canonical_state_equal(result.canonical_state, reopened.current_state())  # pyright: ignore[reportArgumentType]
    finally:
        reopened.close()


def test_a_tail_after_a_revision_no_record_established_is_refused(system: RTGSystem) -> None:
    """Excludes answering a different question than the one asked.

    Returning every transition and calling it a follower of the base would be a
    well-formed tail for an interval nobody requested.
    """
    with pytest.raises(ValueError, match="no record in this ledger established revision"):
        system.ledger_tail(after=99)


def test_a_tail_whose_result_would_not_conform_is_refused(system: RTGSystem) -> None:
    """Well-formed for its kind is not the same as sound.

    The commit path validates the graph a change would produce. A supplied tail gets the
    same treatment, or a system seeded from this reconstruction would be founded on state
    its own definitions forbid.
    """
    initial = system.store.initial_record()
    identity = system.base_identity()
    unsound = CanonicalTransitionRecord(
        prior_revision=0,
        resulting_revision=1,
        kind=TransitionKind.GRAPH_MUTATION,
        change=CanonicalChange(
            graph_change=GraphChange(anchor_upserts=(Anchor("x-1", "no-such-type", "Nobody"),))
        ),
        provenance=_owner(),
        recorded_at=now(),
    )

    result = reconstruct(
        ReplayRequest(
            initial=initial,
            tail=_chained(identity, (unsound,)),
            base_identity=identity,
        )
    )

    assert result.status is OperationStatus.REJECTED
    assert result.canonical_state is None
    assert any("no active anchor type" in finding.summary for finding in result.findings)


def test_a_tail_from_another_ledger_is_refused_though_its_revision_matches(
    tmp_path: Path, system: RTGSystem
) -> None:
    """The case record identity exists for.

    Both systems sit at revision 1 with a transition following revision 0. Only the
    identity of the record each follows distinguishes them, and joining them would
    produce a state neither ledger ever held.
    """
    other = _fresh(tmp_path, "other.sqlite3")
    try:
        assert other.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-9", "person", "Someone else"),)),
            provenance=_owner(),
        ).accepted
        foreign = _tail_of(other)
        snapshot = system.create_snapshot(provenance=_owner()).snapshot
        assert snapshot is not None
        assert foreign.transitions[0].prior_revision == 0

        result = reconstruct(
            ReplayRequest(
                initial=system.store.initial_record(),
                tail=foreign,
                base_identity=system.base_identity(),
            )
        )

        assert result.status is OperationStatus.REJECTED
        assert result.canonical_state is None
        assert any("different record" in finding.summary for finding in result.findings)
    finally:
        other.close()


def _transition(prior: int, resulting: int) -> CanonicalTransitionRecord:
    return CanonicalTransitionRecord(
        prior_revision=prior,
        resulting_revision=resulting,
        kind=TransitionKind.GRAPH_MUTATION,
        change=CanonicalChange(graph_change=GraphChange(anchor_upserts=(ADA,))),
        provenance=_owner(),
        recorded_at=now(),
    )


def test_a_gapped_duplicated_or_reordered_tail_is_refused(system: RTGSystem) -> None:
    initial = system.store.initial_record()
    identity = system.base_identity()
    real = _tail_of(system).transitions

    for name, transitions in (
        ("gap", (_transition(2, 3),)),
        ("duplicate", (*real, *real)),
        ("reorder", (_transition(1, 2), *real)),
    ):
        result = reconstruct(
            ReplayRequest(
                initial=initial,
                tail=_chained(identity, transitions),
                base_identity=identity,
            )
        )

        assert result.status is OperationStatus.REJECTED, name
        assert result.canonical_state is None, name
        assert result.findings, name


def test_a_kind_incompatible_transition_in_a_tail_is_refused(system: RTGSystem) -> None:
    """A record no reader could replay is refused before it can move the state."""
    initial = system.store.initial_record()
    incompatible = CanonicalTransitionRecord(
        prior_revision=0,
        resulting_revision=1,
        kind=TransitionKind.DEFINITION_ACTIVATION,
        change=CanonicalChange(graph_change=GraphChange(anchor_upserts=(ADA,))),
        provenance=_owner(),
        recorded_at=now(),
    )

    result = reconstruct(
        ReplayRequest(
            initial=initial,
            tail=_chained(system.base_identity(), (incompatible,)),
            base_identity=system.base_identity(),
        )
    )

    assert result.status is OperationStatus.REJECTED
    assert result.canonical_state is None
    assert any("activation" in finding.summary for finding in result.findings)


def test_a_request_needs_exactly_one_base(system: RTGSystem) -> None:
    snapshot = system.create_snapshot(provenance=_owner()).snapshot
    assert snapshot is not None

    neither = reconstruct(ReplayRequest())
    both = reconstruct(ReplayRequest(initial=system.store.initial_record(), snapshot=snapshot))

    assert neither.status is OperationStatus.REJECTED
    assert both.status is OperationStatus.REJECTED
    assert any("needs an initial record or a snapshot" in f.summary for f in neither.findings)
    assert any("exactly one base" in f.summary for f in both.findings)


def test_a_refused_reconstruction_is_observed(system: RTGSystem) -> None:
    from vellis.activity import HistoryKind, HistoryQuery

    assert not system.reconstruct_state(ReplayRequest(), provenance=_owner()).accepted

    entries = system.history(
        HistoryQuery(kind=HistoryKind.ACTIVITY, maximum_records=100)
    ).activity_entries
    recorded = next(entry for entry in entries if entry.capability == "reconstruction")
    assert recorded.outcome_category is OperationStatus.REJECTED


def test_capturing_and_reconstructing_are_observed(system: RTGSystem) -> None:
    from vellis.activity import HistoryKind, HistoryQuery

    snapshot = system.create_snapshot(provenance=_owner()).snapshot
    assert snapshot is not None
    assert system.reconstruct_state(ReplayRequest(snapshot=snapshot), provenance=_owner()).accepted

    recorded = {
        entry.capability: entry
        for entry in system.history(
            HistoryQuery(kind=HistoryKind.ACTIVITY, maximum_records=100)
        ).activity_entries
    }
    assert recorded["snapshot"].outcome_category is OperationStatus.ACCEPTED
    assert recorded["snapshot"].evaluated_revision == snapshot.revision
    assert recorded["reconstruction"].outcome_category is OperationStatus.ACCEPTED


def test_a_tail_whose_interior_came_from_elsewhere_is_refused(tmp_path: Path) -> None:
    """Excludes checking only the seam.

    Two ledgers with the same shape have transitions with the same revision numbers, so
    swapping one out of the middle is invisible to numbers alone. Naming where the run
    ends makes the whole run answer for itself.
    """
    first = _fresh(tmp_path, "first.sqlite3")
    second = _fresh(tmp_path, "second.sqlite3")
    try:
        for system, middle in ((first, "Bob"), (second, "Mallory")):
            for uuid, name in (("a-1", "Ada"), ("a-2", middle), ("a-3", "Cy")):
                assert system.apply_graph_change(
                    GraphChange(anchor_upserts=(Anchor(uuid, "person", name),)),
                    provenance=_owner(),
                ).accepted

        mine = first.ledger_tail(after=0)
        theirs = second.ledger_tail(after=0)
        spliced = LedgerTail(
            preceding_record=mine.preceding_record,
            transitions=(mine.transitions[0], theirs.transitions[1], mine.transitions[2]),
            final_record=mine.final_record,
        )

        result = reconstruct(
            ReplayRequest(
                initial=first.store.initial_record(),
                tail=spliced,
                base_identity=first.base_identity(),
            )
        )

        assert result.status is OperationStatus.REJECTED
        assert result.canonical_state is None
        assert any("does not end at the record it names" in f.summary for f in result.findings)
    finally:
        first.close()
        second.close()


def test_lineage_alone_separates_two_ledgers_recorded_at_the_same_instant(
    tmp_path: Path,
) -> None:
    """Excludes an identity that separates ledgers only by their clock.

    Everything a record contains is equal here, recorded time included. Only the value
    established with each history base tells them apart.
    """
    from dataclasses import replace

    from vellis.replay import record_identity as identity_of

    first = _fresh(tmp_path, "first.sqlite3")
    second = _fresh(tmp_path, "second.sqlite3")
    try:
        moment = now()
        one = replace(first.store.initial_record(), recorded_at=moment)
        two = replace(second.store.initial_record(), recorded_at=moment)
        assert canonical_state_equal(one.canonical_state, two.canonical_state)
        assert one.initialization_summary == two.initialization_summary
        assert one.provenance == two.provenance

        first_root = first.store.ledger_identity()
        second_root = second.store.ledger_identity()

        assert first_root != second_root
        assert identity_of(one, follows=first_root) != identity_of(two, follows=second_root)
        assert identity_of(one, follows=first_root) == identity_of(two, follows=first_root)
        # And the system roots its own chain there rather than anywhere else.
        assert first.base_identity() == identity_of(
            first.store.initial_record(), follows=first_root
        )
    finally:
        first.close()
        second.close()


def test_a_captured_identity_folds_the_whole_chain_not_only_the_last_record(
    system: RTGSystem,
) -> None:
    """Excludes an identity that hashes the final record against the base directly."""
    for uuid in ("a-2", "a-3"):
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor(uuid, "person", uuid),)), provenance=_owner()
        ).accepted
    assert len(system.store.transitions()) >= 3

    snapshot = system.create_snapshot(provenance=_owner()).snapshot
    assert snapshot is not None

    unchained = record_identity(system.store.transitions()[-1], follows=system.base_identity())
    assert snapshot.captured_through != unchained
    assert snapshot.captured_through == system.ledger_tail(after=0).final_record


def test_a_capture_racing_a_commit_is_refused_rather_than_bound_to_the_wrong_record(
    tmp_path: Path,
) -> None:
    """Excludes a snapshot whose state and captured record came from different revisions."""
    system = _fresh(tmp_path)
    other = RTGSystem.open(system.store.path)
    try:
        original = system.current_state

        def commit_then_read():
            assert other.apply_graph_change(
                GraphChange(anchor_upserts=(ADA,)), provenance=_owner()
            ).accepted
            system.current_state = original  # type: ignore[method-assign]
            return original()

        system.current_state = commit_then_read  # type: ignore[method-assign]
        result = system.create_snapshot(provenance=_owner())

        assert not result.accepted
        assert result.snapshot is None
        assert any("while it was being captured" in f.summary for f in result.findings)
    finally:
        other.close()
        system.close()


def test_a_snapshot_whose_state_does_not_conform_is_refused_on_reconstruction(
    system: RTGSystem,
) -> None:
    """A base gets the same scrutiny a tail does; S011 seeds a system from one."""
    from dataclasses import replace

    from vellis.replay import CanonicalSnapshot

    snapshot = system.create_snapshot(provenance=_owner()).snapshot
    assert snapshot is not None
    damaged = CanonicalSnapshot(
        canonical_state=replace(
            snapshot.canonical_state,
            graph=replace(
                snapshot.canonical_state.graph,
                anchors=(*snapshot.canonical_state.graph.anchors, Anchor("x-1", "ghost", "X")),
            ),
        ),
        captured_through=snapshot.captured_through,
    )

    result = reconstruct(ReplayRequest(snapshot=damaged))

    assert result.status is OperationStatus.REJECTED
    assert result.canonical_state is None
    assert any("no active anchor type" in f.summary for f in result.findings)


def test_an_activation_whose_definitions_are_invalid_is_refused(system: RTGSystem) -> None:
    """The live path validates a proposal before activating it; replay does the same."""
    from vellis.canonical import DefinitionDeltaDisposition

    invalid = GraphDefinitionSet(anchor_types=(AnchorTypeDefinition(type_key="ghost"),))
    initial = system.store.initial_record()
    identity = system.base_identity()
    activation = CanonicalTransitionRecord(
        prior_revision=0,
        resulting_revision=1,
        kind=TransitionKind.DEFINITION_ACTIVATION,
        change=CanonicalChange(
            active_definitions=invalid,
            delta_disposition=DefinitionDeltaDisposition.ABSENT,
        ),
        provenance=_owner(),
        recorded_at=now(),
    )

    result = reconstruct(
        ReplayRequest(
            initial=initial,
            tail=_chained(identity, (activation,)),
            base_identity=identity,
        )
    )

    assert result.status is OperationStatus.REJECTED
    assert result.canonical_state is None
    assert result.findings


def test_a_structurally_incoherent_change_in_a_tail_is_refused(system: RTGSystem) -> None:
    """Excludes replaying a change the commit path would have refused outright.

    An unknown removal commanded twice conforms trivially — it changes nothing — so only
    the structural check catches it. Replay applies changes; it must screen them the same
    way the writer did.
    """
    initial = system.store.initial_record()
    identity = system.base_identity()
    incoherent = CanonicalTransitionRecord(
        prior_revision=0,
        resulting_revision=1,
        kind=TransitionKind.GRAPH_MUTATION,
        change=CanonicalChange(graph_change=GraphChange(anchor_removals=("nope", "nope"))),
        provenance=_owner(),
        recorded_at=now(),
    )

    result = reconstruct(
        ReplayRequest(
            initial=initial,
            tail=_chained(identity, (incoherent,)),
            base_identity=identity,
        )
    )

    assert result.status is OperationStatus.REJECTED
    assert result.canonical_state is None
    assert result.findings
