"""Evidence for ``VellisVerification::atomicTransitions`` on the graph-mutation family.

The verification case is specific about what must be refused — duplicate commands,
upsert/removal conflicts, unknown removals, kind changes, invalid references, and an
assumed cascade — and about what an accepted record must carry: the semantic upserts and
removals, never a complete replacement graph.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import build_rich_definitions

from tests.vellis.oracle import materialize_replay, materialize_state
from tests.vellis.semantic_state import semantic_state_equal
from vellis.canonical import (
    DefinitionDeltaDisposition,
    Provenance,
    TransitionKind,
)
from vellis.changes import GraphChange
from vellis.graph import Anchor, AssociatedDataObject, Link
from vellis.json_value import normalize
from vellis.outcomes import OperationStatus
from vellis.system import RTGSystem

ADA = Anchor(uuid="a-1", type_key="person", display_name="Ada")
ORBIT = Anchor(uuid="a-2", type_key="project", display_name="Orbit")
NOTE = AssociatedDataObject(
    uuid="d-1",
    type_key="note",
    anchor_uuids=("a-1",),
    properties={"title": normalize("First meeting")},
)
WORKS_ON = Link(uuid="l-1", type_key="worksOn", source_uuid="a-1", target_uuid="a-2")


def _system(tmp_path: Path) -> RTGSystem:
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    outcome = system.initialize_fresh(
        build_rich_definitions(),
        provenance=Provenance(initiator="owner"),
        initialization_summary="a fresh start",
    )
    assert outcome.accepted
    return system


def _apply(system: RTGSystem, change: GraphChange):
    return system.apply_graph_change(change, provenance=Provenance(initiator="owner"))


def _populated(tmp_path: Path) -> RTGSystem:
    system = _system(tmp_path)
    outcome = _apply(
        system,
        GraphChange(
            anchor_upserts=(ADA, ORBIT),
            associated_data_upserts=(NOTE,),
            link_upserts=(WORKS_ON,),
        ),
    )
    assert outcome.accepted, outcome.findings
    return system


# --- Accepted mutation --------------------------------------------------------------


def test_a_mixed_change_commits_one_revision(tmp_path: Path) -> None:
    system = _system(tmp_path)
    try:
        outcome = _apply(system, GraphChange(anchor_upserts=(ADA, ORBIT)))
        assert outcome.status is OperationStatus.ACCEPTED
        assert outcome.resulting_revision == 1

        second = _apply(
            system,
            GraphChange(
                anchor_upserts=(Anchor(uuid="a-1", type_key="person", display_name="Ada L."),),
                associated_data_upserts=(NOTE,),
                link_upserts=(WORKS_ON,),
                anchor_removals=(),
            ),
        )
        assert second.resulting_revision == 2
        state = materialize_state(system)
        assert state.revision == 2
        anchor = state.graph.anchor("a-1")
        assert anchor is not None and anchor.display_name == "Ada L."
        assert state.graph.associated_data_object("d-1") is not None
        assert state.graph.link("l-1") is not None
    finally:
        system.close()


def test_a_removal_takes_its_object_out(tmp_path: Path) -> None:
    system = _populated(tmp_path)
    try:
        outcome = _apply(system, GraphChange(link_removals=("l-1",)))
        assert outcome.accepted
        assert materialize_state(system).graph.link("l-1") is None
    finally:
        system.close()


def test_direct_associations_move_only_through_a_complete_upsert(tmp_path: Path) -> None:
    """The model gives no way to edit an association except by upserting its object."""
    system = _populated(tmp_path)
    try:
        outcome = _apply(
            system,
            GraphChange(
                associated_data_upserts=(
                    AssociatedDataObject(
                        uuid="d-1",
                        type_key="note",
                        anchor_uuids=("a-1", "a-2"),
                        properties={"title": normalize("First meeting")},
                    ),
                )
            ),
        )
        assert outcome.accepted
        data = materialize_state(system).graph.associated_data_object("d-1")
        assert data is not None
        assert frozenset(data.anchor_uuids) == {"a-1", "a-2"}
    finally:
        system.close()


# --- Non-effects --------------------------------------------------------------------


def test_an_effective_no_op_creates_neither_revision_nor_record(tmp_path: Path) -> None:
    system = _populated(tmp_path)
    try:
        before = materialize_state(system)
        records = system.store.canonical_record_count()

        empty = _apply(system, GraphChange())
        assert empty.status is OperationStatus.ACCEPTED
        assert empty.resulting_revision is None

        rewrite = _apply(system, GraphChange(anchor_upserts=(ADA,)))
        assert rewrite.status is OperationStatus.ACCEPTED
        assert rewrite.resulting_revision is None

        assert semantic_state_equal(materialize_state(system), before)
        assert system.store.canonical_record_count() == records
    finally:
        system.close()


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (
            GraphChange(anchor_upserts=(ADA, Anchor("a-1", "person", "Twice"))),
            "upserted more than once",
        ),
        (GraphChange(anchor_removals=("a-1", "a-1")), "removed more than once"),
        (
            GraphChange(anchor_upserts=(ADA,), anchor_removals=("a-1",)),
            "both upserted and removed",
        ),
        (GraphChange(anchor_removals=("a-9",)), "no such object exists"),
        (GraphChange(link_removals=("a-1",)), "exists as anchor"),
        (
            GraphChange(link_upserts=(Link("a-1", "worksOn", "a-1", "a-2"),)),
            "never changes an object's kind",
        ),
        (GraphChange(anchor_removals=("a-1",)), "rather than relying on a cascade"),
    ],
    ids=[
        "duplicate-upsert",
        "duplicate-removal",
        "upsert-removal-conflict",
        "unknown-removal",
        "removal-kind-mismatch",
        "kind-change",
        "assumed-cascade",
    ],
)
def test_an_incoherent_change_is_refused_without_effect(
    tmp_path: Path, change: GraphChange, expected: str
) -> None:
    system = _populated(tmp_path)
    try:
        before = materialize_state(system)
        records = system.store.canonical_record_count()

        outcome = _apply(system, change)
        assert outcome.status is OperationStatus.REJECTED
        assert outcome.resulting_revision is None
        assert any(expected in finding.summary for finding in outcome.findings), outcome.findings
        assert semantic_state_equal(materialize_state(system), before)
        assert system.store.canonical_record_count() == records
    finally:
        system.close()


def test_a_change_whose_result_would_not_conform_is_refused(tmp_path: Path) -> None:
    """Excludes validating only the objects the change names."""
    system = _populated(tmp_path)
    try:
        before = materialize_state(system)
        outcome = _apply(
            system,
            GraphChange(
                associated_data_upserts=(
                    AssociatedDataObject(
                        uuid="d-2",
                        type_key="note",
                        anchor_uuids=("a-1",),
                        properties={"title": normalize(""), "year": normalize("not-a-year")},
                    ),
                )
            ),
        )
        assert outcome.status is OperationStatus.REJECTED
        assert any("below its minimum" in each.summary for each in outcome.findings)
        assert any("whole-string pattern" in each.summary for each in outcome.findings)
        assert semantic_state_equal(materialize_state(system), before)
    finally:
        system.close()


def test_endpoint_type_change_revalidates_incident_links(tmp_path: Path) -> None:
    system = _populated(tmp_path)
    try:
        before = materialize_state(system)
        outcome = _apply(
            system,
            GraphChange(anchor_upserts=(Anchor("a-1", "project", "Ada as a project"),)),
        )

        assert outcome.status is OperationStatus.REJECTED
        assert any(
            "endpoint constraint does not permit" in each.summary for each in outcome.findings
        )
        assert semantic_state_equal(materialize_state(system), before)
    finally:
        system.close()


def test_a_change_that_breaks_an_untouched_objects_rule_is_refused(tmp_path: Path) -> None:
    """The complete resulting graph is validated, not the delta of it."""
    system = _populated(tmp_path)
    try:
        outcome = _apply(system, GraphChange(anchor_removals=("a-2",), link_removals=("l-1",)))
        assert outcome.accepted
        # Orbit is gone, so a note grounded by it can no longer be added.
        broken = _apply(
            system,
            GraphChange(
                associated_data_upserts=(
                    AssociatedDataObject(
                        uuid="d-3",
                        type_key="note",
                        anchor_uuids=("a-2",),
                        properties={"title": normalize("Orphan")},
                    ),
                )
            ),
        )
        assert broken.status is OperationStatus.REJECTED
        assert any("owned by this graph" in each.summary for each in broken.findings)
    finally:
        system.close()


# --- The record it writes -----------------------------------------------------------


def test_an_accepted_record_carries_the_change_not_a_replacement_graph(
    tmp_path: Path,
) -> None:
    """The model permits a replacement graph only for historical restoration."""
    system = _populated(tmp_path)
    try:
        connection = system.store._connection  # noqa: SLF001
        assert connection.execute(
            "SELECT record_kind FROM canonical_record WHERE ordinal = 1"
        ).fetchone() == (TransitionKind.GRAPH_MUTATION.value,)
        assert connection.execute(
            "SELECT active_definition_set_id, delta_disposition, proposed_definition_set_id"
            " FROM canonical_definition_event WHERE established_revision = 1"
        ).fetchone() == (None, DefinitionDeltaDisposition.UNCHANGED.value, None)
        assert set(
            connection.execute(
                "SELECT object_kind, uuid FROM canonical_graph_event WHERE established_revision = 1"
            )
        ) == {("anchor", "a-1"), ("anchor", "a-2"), ("associatedData", "d-1"), ("link", "l-1")}
    finally:
        system.close()


def test_each_transition_is_contiguous_and_advances_exactly_one_revision(
    tmp_path: Path,
) -> None:
    system = _system(tmp_path)
    try:
        _apply(system, GraphChange(anchor_upserts=(ADA,)))
        _apply(system, GraphChange(anchor_upserts=(ORBIT,)))
        _apply(system, GraphChange(associated_data_upserts=(NOTE,)))
        chain = list(
            system.store._connection.execute(  # noqa: SLF001
                "SELECT prior_revision, established_revision FROM canonical_record"
                " WHERE ordinal > 0 ORDER BY ordinal"
            )
        )
        assert chain == [(0, 1), (1, 2), (2, 3)]
        assert materialize_state(system).revision == 3
    finally:
        system.close()


def test_replay_reconstructs_the_same_state_without_activity_history(tmp_path: Path) -> None:
    """Replay reads the canonical ledger and nothing else.

    Observations exist by now, so this shows they are not consulted rather than that
    they are absent: emptying the activity ledger changes nothing replay reconstructs.
    """
    system = _populated(tmp_path)
    try:
        _apply(system, GraphChange(link_removals=("l-1",)))
        system.check()
        assert system.store.activity_record_count() > 0
        before = materialize_replay(system)
        assert semantic_state_equal(materialize_state(system), before)

        system.store._connection.execute("DELETE FROM activity_record")  # noqa: SLF001
        system.store._connection.commit()  # noqa: SLF001

        assert system.store.activity_record_count() == 0
        assert semantic_state_equal(materialize_replay(system), before)
    finally:
        system.close()


def test_committed_changes_survive_an_ordinary_restart(tmp_path: Path) -> None:
    path = tmp_path / "vellis.sqlite3"
    system = RTGSystem.open(path)
    try:
        system.initialize_fresh(
            build_rich_definitions(),
            provenance=Provenance(initiator="owner"),
            initialization_summary="a fresh start",
        )
        _apply(system, GraphChange(anchor_upserts=(ADA, ORBIT)))
        _apply(system, GraphChange(associated_data_upserts=(NOTE,), link_upserts=(WORKS_ON,)))
        before = materialize_state(system)
    finally:
        system.close()

    reopened = RTGSystem.open(path)
    try:
        assert semantic_state_equal(materialize_state(reopened), before)
        assert semantic_state_equal(materialize_replay(reopened), before)
        assert reopened.store.canonical_record_count() == 3
    finally:
        reopened.close()


def test_a_mutation_leaves_active_definitions_and_the_delta_alone(tmp_path: Path) -> None:
    from vellis.definitions import definition_set_equal

    system = _populated(tmp_path)
    try:
        state = materialize_state(system)
        assert definition_set_equal(state.active_definitions, build_rich_definitions())
        assert state.definition_delta is None
    finally:
        system.close()


def test_an_empty_graph_can_be_reached_again_by_removing_everything(tmp_path: Path) -> None:
    system = _populated(tmp_path)
    try:
        outcome = _apply(
            system,
            GraphChange(
                anchor_removals=("a-1", "a-2"),
                associated_data_removals=("d-1",),
                link_removals=("l-1",),
            ),
        )
        assert outcome.accepted, outcome.findings
        assert materialize_state(system).graph.is_empty
        assert semantic_state_equal(materialize_state(system), materialize_replay(system))
    finally:
        system.close()


def test_replay_agrees_with_the_projection_at_every_revision(tmp_path: Path) -> None:
    """Excludes a projection that drifts from the ledger as transitions accumulate."""
    system = _system(tmp_path)
    try:
        changes = [
            GraphChange(anchor_upserts=(ADA,)),
            GraphChange(anchor_upserts=(ORBIT,)),
            GraphChange(associated_data_upserts=(NOTE,)),
            GraphChange(link_upserts=(WORKS_ON,)),
            GraphChange(link_removals=("l-1",)),
            GraphChange(associated_data_removals=("d-1",)),
        ]
        for change in changes:
            assert _apply(system, change).accepted
            assert semantic_state_equal(materialize_state(system), materialize_replay(system))
        assert materialize_state(system).revision == len(changes)
    finally:
        system.close()


def test_the_graph_is_not_a_valid_endpoint_for_a_link_to_a_link(tmp_path: Path) -> None:
    system = _populated(tmp_path)
    try:
        outcome = _apply(
            system,
            GraphChange(
                link_upserts=(Link("l-2", "worksOn", source_uuid="l-1", target_uuid="a-2"),)
            ),
        )
        assert outcome.status is OperationStatus.REJECTED
        assert any("never an endpoint" in each.summary for each in outcome.findings)
    finally:
        system.close()


def test_a_graph_with_no_established_state_cannot_be_changed(tmp_path: Path) -> None:
    """Reported, not raised: the model asks why the change was not applied.

    Rejected rather than failed — an RTG with no established state is a determinate
    precondition the owner can act on, the mirror of initializing one that already has
    state. ``failed`` is reserved for a store that cannot answer at all.
    """
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        outcome = _apply(system, GraphChange(anchor_upserts=(ADA,)))
        assert outcome.status is OperationStatus.REJECTED
        assert outcome.resulting_revision is None
        assert any("no canonical state is established" in each.summary for each in outcome.findings)
        assert not system.is_initialized
    finally:
        system.close()


def test_current_conformance_is_reported_at_the_current_revision(tmp_path: Path) -> None:
    from vellis.outcomes import ValidationScope

    system = _populated(tmp_path)
    try:
        report = system.check()
        assert report.scope is ValidationScope.GRAPH_CONFORMANCE
        assert report.conforms
        assert report.findings == ()
        assert report.evaluated_revision == materialize_state(system).revision
    finally:
        system.close()


def test_a_non_conforming_graph_is_described_not_raised(tmp_path: Path) -> None:
    """A false conforms value describes the subject; it is not an execution failure.

    The graph is made non-conforming through the store rather than through a change,
    because an accepted change can never produce one.
    """
    from vellis.outcomes import ValidationScope

    system = _populated(tmp_path)
    try:
        state = materialize_state(system)
        system.store._upsert_current_graph_object_unlocked(  # noqa: SLF001
            Link("l-9", "worksOn", "a-2", "a-1"), state.revision
        )
        report = system.check()
        assert report.scope is ValidationScope.GRAPH_CONFORMANCE
        assert not report.conforms
        assert report.returned_findings
        assert report.evaluated_revision == state.revision
    finally:
        system.close()


# --- Transition validity ------------------------------------------------------------


def _record(kind: TransitionKind, change, prior: int = 0, resulting: int = 1):
    from vellis.canonical import CanonicalTransitionRecord

    return CanonicalTransitionRecord(
        prior_revision=prior,
        resulting_revision=resulting,
        kind=kind,
        change=change,
        provenance=Provenance(initiator="owner"),
    )


@pytest.mark.parametrize(
    ("kind", "change", "expected"),
    [
        (TransitionKind.GRAPH_MUTATION, None, "carries no graph change"),
        (TransitionKind.GRAPH_MUTATION, "delta", "changes the definition delta"),
        (TransitionKind.DEFINITION_DELTA_CHANGE, "delta-unchanged", "does not clear the delta"),
        (TransitionKind.DEFINITION_DELTA_CHANGE, "delta-with-graph", "changes the graph"),
        (TransitionKind.DEFINITION_ACTIVATION, None, "bounded transition carrier"),
    ],
    ids=[
        "mutation-without-change",
        "mutation-changing-delta",
        "delta-change-leaving-the-delta",
        "delta-change-touching-the-graph",
        "sqlite-native-activation",
    ],
)
def test_a_transition_must_be_replayable_for_its_kind(
    kind: TransitionKind, change: str | None, expected: str
) -> None:
    """Excludes writing a record no reader could replay.

    A historical restoration carries an explicit normalized difference, as does an
    ordinary mutation; each kind touches only its own facets.
    """
    from vellis.canonical import CanonicalChange, transition_findings

    changes = {
        None: CanonicalChange(),
        "delta": CanonicalChange(
            graph_change=GraphChange(anchor_upserts=(ADA,)),
            delta_disposition=DefinitionDeltaDisposition.PRESENT,
        ),
        "delta-unchanged": CanonicalChange(),
        "delta-with-graph": CanonicalChange(
            graph_change=GraphChange(anchor_upserts=(ADA,)),
            delta_disposition=DefinitionDeltaDisposition.ABSENT,
        ),
    }
    findings = transition_findings(_record(kind, changes[change]))
    assert any(expected in each.summary for each in findings), findings


def test_a_valid_graph_mutation_record_has_no_findings() -> None:
    from vellis.canonical import CanonicalChange, transition_findings

    record = _record(
        TransitionKind.GRAPH_MUTATION,
        CanonicalChange(graph_change=GraphChange(anchor_upserts=(ADA,))),
    )
    assert transition_findings(record) == ()


def test_a_transition_that_skips_a_revision_is_refused() -> None:
    from vellis.canonical import CanonicalChange, transition_findings

    record = _record(
        TransitionKind.GRAPH_MUTATION,
        CanonicalChange(graph_change=GraphChange(anchor_upserts=(ADA,))),
        prior=0,
        resulting=2,
    )
    assert any(
        "does not advance the revision by exactly one" in each.summary
        for each in transition_findings(record)
    )


def test_a_change_prepared_against_a_stale_revision_is_refused(tmp_path: Path) -> None:
    """Excludes two writers both believing they advanced from the same revision."""
    from vellis.canonical import CanonicalChange, CanonicalTransitionRecord
    from vellis.store import ConcurrentRevisionError

    system = _populated(tmp_path)
    try:
        state = materialize_state(system)
        stale = CanonicalTransitionRecord(
            prior_revision=state.revision - 1,
            resulting_revision=state.revision,
            kind=TransitionKind.GRAPH_MUTATION,
            change=CanonicalChange(graph_change=GraphChange(anchor_upserts=(ADA,))),
            provenance=Provenance(initiator="owner"),
        )
        with pytest.raises(ConcurrentRevisionError):
            system.store._append_transition(stale)
        assert semantic_state_equal(materialize_state(system), state)
    finally:
        system.close()


# --- Work that must not grow with history -------------------------------------------


def test_appending_a_transition_does_not_traverse_the_ledger_prefix() -> None:
    """Excludes counting rows to find the next ledger position.

    The model permits constant terminal-position and append work but forbids traversing
    the existing prefix, so an owner's ordinary edits must not get slower as their
    memory accumulates history. A query plan that scans is that traversal.
    """
    import sqlite3

    from vellis.store import NEXT_ORDINAL_SQL

    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            "CREATE TABLE canonical_record (established_revision INTEGER PRIMARY KEY,"
            " ordinal INTEGER NOT NULL UNIQUE)"
        )
        plan = connection.execute(f"EXPLAIN QUERY PLAN {NEXT_ORDINAL_SQL}").fetchall()
    finally:
        connection.close()
    detail = " ".join(str(row[-1]) for row in plan)
    assert "SCAN" not in detail, detail


def _statements_to_commit(system: RTGSystem, uuid: str) -> tuple[int, int]:
    """Return how many statements and record reads one commit costs."""
    system.store.reset_instrumentation()
    statements: list[str] = []
    system.store._connection.set_trace_callback(statements.append)  # noqa: SLF001
    try:
        assert _apply(
            system,
            GraphChange(anchor_upserts=(Anchor(uuid=uuid, type_key="person", display_name="X"),)),
        ).accepted
    finally:
        system.store._connection.set_trace_callback(None)  # noqa: SLF001
    return len(statements), system.store.record_reads


def test_committing_costs_the_same_whatever_the_history_length(tmp_path: Path) -> None:
    """Excludes a commit whose work grows with the number of revisions behind it.

    The terminal-position lookup the model permits is constant; counting the prefix to
    find it is not, and the difference is invisible unless two history lengths are
    compared.
    """
    system = _populated(tmp_path)
    try:
        early = _statements_to_commit(system, "a-100")
        for index in range(30):
            assert _apply(
                system,
                GraphChange(
                    anchor_upserts=(
                        Anchor(uuid=f"a-2{index:02d}", type_key="person", display_name="Bulk"),
                    )
                ),
            ).accepted
        late = _statements_to_commit(system, "a-101")
        assert early == late
        assert late[1] == 0
        assert system.store.canonical_record_count() == 34
    finally:
        system.close()


# --- Record text and readability on the change path ----------------------------------


@pytest.mark.parametrize(
    "provenance",
    [
        Provenance(initiator="own" + chr(0xD800) + "er"),
        Provenance(initiator="owner", source="im" + chr(0xD800) + "port"),
    ],
    ids=["initiator", "source"],
)
def test_unstorable_provenance_is_refused_like_it_is_at_initialization(
    tmp_path: Path, provenance: Provenance
) -> None:
    """Excludes screening the first record's text and not every later record's."""
    system = _populated(tmp_path)
    try:
        before = materialize_state(system)
        outcome = system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-7", "person", "Later"),)),
            provenance=provenance,
        )
        assert outcome.status is OperationStatus.REJECTED
        assert any("unpaired surrogate" in each.summary for each in outcome.findings)
        assert semantic_state_equal(materialize_state(system), before)
    finally:
        system.close()


def test_a_shallower_payload_commits_and_reads_back(tmp_path: Path) -> None:
    """The counterpart: the guard must not refuse what the reader would accept."""
    nested: object = "leaf"
    for _ in range(80):
        nested = {"n": nested}

    path = tmp_path / "vellis.sqlite3"
    system = _populated(tmp_path)
    try:
        assert _apply(
            system,
            GraphChange(
                associated_data_upserts=(
                    AssociatedDataObject(
                        uuid="d-5",
                        type_key="note",
                        anchor_uuids=("a-1",),
                        properties={"title": normalize("Deep"), "details": normalize(nested)},
                    ),
                )
            ),
        ).accepted
    finally:
        system.close()

    reopened = RTGSystem.open(path)
    try:
        assert semantic_state_equal(materialize_state(reopened), materialize_replay(reopened))
    finally:
        reopened.close()


def test_system_metadata_survives_a_committed_change(tmp_path: Path) -> None:
    """Excludes dropping metadata from a stored change, which would split the ledger
    from the projection on the model's own liveness marker."""
    from vellis.graph import SystemMetadata

    path = tmp_path / "vellis.sqlite3"
    system = _populated(tmp_path)
    try:
        assert _apply(
            system,
            GraphChange(
                associated_data_upserts=(
                    AssociatedDataObject(
                        uuid="d-1",
                        type_key="note",
                        anchor_uuids=("a-1",),
                        properties={"title": normalize("First meeting")},
                        system_metadata=SystemMetadata(members={"live": False, "src": "import"}),
                    ),
                ),
                link_upserts=(
                    Link(
                        uuid="l-1",
                        type_key="worksOn",
                        source_uuid="a-1",
                        target_uuid="a-2",
                        system_metadata=SystemMetadata(members={"live": False}),
                    ),
                ),
            ),
        ).accepted
        assert semantic_state_equal(materialize_state(system), materialize_replay(system))
    finally:
        system.close()

    reopened = RTGSystem.open(path)
    try:
        data = materialize_state(reopened).graph.associated_data_object("d-1")
        assert data is not None
        assert data.system_metadata.live is False
        assert data.system_metadata.members["src"] == "import"
        replayed = materialize_replay(reopened).graph.associated_data_object("d-1")
        assert replayed is not None and replayed.system_metadata.live is False
        link = materialize_replay(reopened).graph.link("l-1")
        assert link is not None and link.system_metadata.live is False
    finally:
        reopened.close()


def test_a_removal_is_permitted_when_the_change_moves_its_dependent_away(
    tmp_path: Path,
) -> None:
    """A cascade is refused, but restating the dependent in the same change is not."""
    system = _populated(tmp_path)
    try:
        outcome = _apply(
            system,
            GraphChange(
                associated_data_upserts=(
                    AssociatedDataObject(
                        uuid="d-1",
                        type_key="note",
                        anchor_uuids=("a-2",),
                        properties={"title": normalize("Moved")},
                    ),
                ),
                anchor_removals=("a-1",),
                link_removals=("l-1",),
            ),
        )
        assert outcome.accepted, outcome.findings
        assert materialize_state(system).graph.anchor("a-1") is None
        assert semantic_state_equal(materialize_state(system), materialize_replay(system))
    finally:
        system.close()
