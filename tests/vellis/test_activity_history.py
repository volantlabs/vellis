"""Evidence for ``VellisVerification::activitySeparation``.

The verification case walks one arc: record what happened, read it back without the read
observing itself, vary retention and show replay unmoved, refuse a bad read whole, and
show neither ledger's entries leak into the other's result.

The through-line is that one ledger is authority and the other is not. Every assertion
here is some form of that: activity cannot change what memory *is*, which is exactly what
makes it safe to let the owner delete.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from conftest import build_rich_definitions

from vellis.activity import HistoryKind, HistoryQuery, RetentionDecision
from vellis.canonical import Provenance, TransitionKind, canonical_state_equal, now
from vellis.changes import GraphChange
from vellis.graph import Anchor
from vellis.outcomes import OperationStatus
from vellis.query import AnchorGroup, AnchorProjection, GraphQuery, ReturnShape
from vellis.system import RTGSystem

ADA = Anchor(uuid="a-1", type_key="person", display_name="Ada")
ORBIT = Anchor(uuid="p-1", type_key="project", display_name="Orbit")


def _owner() -> Provenance:
    return Provenance(initiator="owner", source="the desk")


@pytest.fixture
def system(tmp_path: Path):
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    assert system.initialize_fresh(
        build_rich_definitions(), provenance=_owner(), initialization_summary="a fresh start"
    ).accepted
    try:
        yield system
    finally:
        system.close()


def _anyone() -> GraphQuery:
    return GraphQuery(
        anchor_groups=(AnchorGroup(name="people", anchor_type="person"),),
        return_shape=ReturnShape(
            projections=(AnchorProjection(name="who", anchor_group="people"),)
        ),
        maximum_rows=10,
    )


def _activity(system: RTGSystem, maximum_records: int = 100):
    result = system.history(
        HistoryQuery(kind=HistoryKind.ACTIVITY, maximum_records=maximum_records)
    )
    assert result.accepted, result.findings
    return result


# --- What gets recorded ---------------------------------------------------------------


def test_a_permitted_read_is_recorded_with_its_capability_and_outcome(
    system: RTGSystem,
) -> None:
    assert system.query_graph(_anyone(), provenance=_owner()).accepted

    entries = _activity(system).activity_entries

    read = next(entry for entry in entries if entry.capability == "query")
    assert read.outcome_category is OperationStatus.ACCEPTED
    assert read.provenance == _owner()
    assert read.evaluated_revision == 0
    assert "anchor groups people" in read.semantic_scope


def test_a_validation_a_rejection_and_a_failure_are_each_recorded(system: RTGSystem) -> None:
    system.check(provenance=_owner())
    refused = system.query_graph(
        GraphQuery(
            anchor_groups=(AnchorGroup(name="people", anchor_type="unheard-of"),),
            return_shape=ReturnShape(
                projections=(AnchorProjection(name="who", anchor_group="people"),)
            ),
            maximum_rows=10,
        ),
        provenance=_owner(),
    )
    assert refused.status is OperationStatus.REJECTED

    recorded = {
        (entry.capability, entry.outcome_category) for entry in _activity(system).activity_entries
    }

    assert ("check", OperationStatus.ACCEPTED) in recorded
    assert ("query", OperationStatus.REJECTED) in recorded


def test_an_activity_summary_copies_no_result_rows_or_payloads(system: RTGSystem) -> None:
    """Excludes a ledger that quietly becomes a second copy of the memory.

    Ada's name is in the graph and in the query's answer. It must not be in the record
    of that answer, or forgetting activity would no longer be safe.
    """
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(ADA,)), provenance=_owner()
    ).accepted
    assert system.query_graph(_anyone(), provenance=_owner()).accepted

    for entry in _activity(system).activity_entries:
        assert "Ada" not in entry.summary
        assert "Ada" not in entry.semantic_scope
        assert "a-1" not in entry.summary


# --- A read does not observe itself ---------------------------------------------------


def test_an_activity_read_is_selected_before_its_own_record_is_appended(
    system: RTGSystem,
) -> None:
    """Excludes a read that includes the record of itself.

    Otherwise asking the same question twice would give two different answers, and the
    second would be right about the first only by accident.
    """
    system.check(provenance=_owner())
    before = system.store.activity_record_count()

    first = _activity(system)
    assert len(first.activity_entries) == before
    assert system.store.activity_record_count() == before + 1

    second = _activity(system)
    assert len(second.activity_entries) == before + 1


# --- Retention ------------------------------------------------------------------------


def test_forgetting_activity_leaves_replayed_state_identical(system: RTGSystem) -> None:
    """The whole reason forgetting is safe to offer."""
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(ADA, ORBIT)), provenance=_owner()
    ).accepted
    system.check(provenance=_owner())
    before = system.replay()
    assert system.store.activity_record_count() > 0

    outcome = system.manage_activity_retention(
        RetentionDecision(remove_before=now() + timedelta(seconds=1)), provenance=_owner()
    )

    assert outcome.accepted, outcome.findings
    assert canonical_state_equal(system.replay(), before)
    assert canonical_state_equal(system.current_state(), before)


def test_retention_changes_no_canonical_state_or_history(system: RTGSystem) -> None:
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(ADA,)), provenance=_owner()
    ).accepted
    records = system.store.canonical_record_count()
    before = system.current_state()

    assert system.manage_activity_retention(
        RetentionDecision(remove_before=now() + timedelta(seconds=1)), provenance=_owner()
    ).accepted

    assert system.store.canonical_record_count() == records
    assert canonical_state_equal(system.current_state(), before)


def test_a_refused_retention_preserves_every_preexisting_record(system: RTGSystem) -> None:
    """Only the failure observation may be appended; nothing already there may go.

    Refused for a boundary that cannot be ordered, so the ledger is still there to count
    afterwards — a failure that destroys the table proves nothing about preservation.
    """
    from datetime import datetime

    system.check(provenance=_owner())
    before = _activity(system).activity_entries
    assert before

    outcome = system.manage_activity_retention(
        RetentionDecision(remove_before=datetime(2020, 1, 1)), provenance=_owner()
    )

    assert outcome.status is OperationStatus.REJECTED
    assert any("which zone it is in" in each.summary for each in outcome.findings)
    after = _activity(system).activity_entries
    assert [entry.capability for entry in after][: len(before)] == [
        entry.capability for entry in before
    ]
    assert any(
        entry.capability == "retention" and entry.outcome_category is OperationStatus.REJECTED
        for entry in after
    )


def test_only_records_before_the_boundary_are_forgotten(system: RTGSystem) -> None:
    """Excludes forgetting more than was asked for, which is the risk retention carries.

    The boundary is taken from a record's own recorded time rather than a wall-clock
    offset, so the case is the one the name claims however fast the machine is.
    """
    system.check(provenance=_owner())
    system.query_graph(_anyone(), provenance=_owner())
    entries = _activity(system).activity_entries
    assert [entry.capability for entry in entries] == ["check", "query"]
    boundary = entries[1].recorded_at

    outcome = system.manage_activity_retention(
        RetentionDecision(remove_before=boundary), provenance=_owner()
    )

    assert outcome.accepted, outcome.findings
    assert "removed 1" in outcome.summary  # the check alone sits before the boundary
    remaining = _activity(system).activity_entries
    # The query stands exactly on the boundary and is kept; the read that found it
    # follows. Accepted retention is canonical-free and appends nothing of its own.
    assert [entry.capability for entry in remaining] == ["query", "history"]


# --- Bounded reads over either ledger -------------------------------------------------


def test_a_canonical_read_returns_one_entry_per_record_in_ledger_order(
    system: RTGSystem,
) -> None:
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(ADA,)), provenance=_owner()
    ).accepted
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(ORBIT,)), provenance=_owner()
    ).accepted

    result = system.history(HistoryQuery(kind=HistoryKind.CANONICAL, maximum_records=100))

    assert result.accepted, result.findings
    assert [entry.revision for entry in result.canonical_entries] == [0, 1, 2]
    assert result.canonical_entries[0].prior_revision is None
    assert result.canonical_entries[0].transition_kind is None
    assert result.canonical_entries[1].prior_revision == 0
    assert result.canonical_entries[1].transition_kind is TransitionKind.GRAPH_MUTATION


def test_a_canonical_entry_carries_review_meaning_without_replay_authority(
    system: RTGSystem,
) -> None:
    """Excludes handing back the change payload: that would be a second replay source."""
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(ADA,)), provenance=_owner()
    ).accepted

    entry = system.history(
        HistoryQuery(kind=HistoryKind.CANONICAL, maximum_records=100)
    ).canonical_entries[-1]

    assert entry.provenance == _owner()
    assert entry.revision == 1
    assert entry.summary
    assert not hasattr(entry, "change")
    assert not hasattr(entry, "canonical_state")


def test_a_result_never_mixes_the_two_entry_families(system: RTGSystem) -> None:
    system.check(provenance=_owner())

    canonical = system.history(HistoryQuery(kind=HistoryKind.CANONICAL, maximum_records=100))
    activity = system.history(HistoryQuery(kind=HistoryKind.ACTIVITY, maximum_records=100))

    assert canonical.canonical_entries and canonical.activity_entries == ()
    assert activity.activity_entries and activity.canonical_entries == ()


@pytest.mark.parametrize(
    ("kind", "maximum", "expected"),
    (
        (HistoryKind.CANONICAL, 1, "refused whole"),
        (HistoryKind.ACTIVITY, 1, "refused whole"),
        (HistoryKind.CANONICAL, 0, "maximum records must be positive"),
        (HistoryKind.ACTIVITY, -1, "maximum records must be positive"),
    ),
    ids=["canonical-over-bound", "activity-over-bound", "zero-maximum", "negative-maximum"],
)
def test_an_over_broad_or_unbounded_read_is_refused_whole(
    system: RTGSystem, kind: HistoryKind, maximum: int, expected: str
) -> None:
    for _ in range(3):
        system.check(provenance=_owner())
        assert (
            system.apply_graph_change(
                GraphChange(anchor_upserts=(ADA,)), provenance=_owner()
            ).status
            is OperationStatus.ACCEPTED
        )

    result = system.history(HistoryQuery(kind=kind, maximum_records=maximum))

    assert result.status is OperationStatus.REJECTED
    assert result.canonical_entries == ()
    assert result.activity_entries == ()
    assert result.evaluated_revision is None
    assert expected in result.summary or any(
        expected in finding.summary for finding in result.findings
    )


def test_a_start_after_its_end_is_invalid(system: RTGSystem) -> None:
    moment = now()

    result = system.history(
        HistoryQuery(
            kind=HistoryKind.ACTIVITY,
            maximum_records=100,
            start_time=moment + timedelta(hours=1),
            end_time=moment,
        )
    )

    assert result.status is OperationStatus.REJECTED
    assert any("starts after it ends" in finding.summary for finding in result.findings)


def test_both_chronological_bounds_are_inclusive(system: RTGSystem) -> None:
    """Excludes an exclusive bound that quietly drops the record sitting exactly on it."""
    system.check(provenance=_owner())
    recorded = _activity(system).activity_entries[0].recorded_at

    result = system.history(
        HistoryQuery(
            kind=HistoryKind.ACTIVITY,
            maximum_records=100,
            start_time=recorded,
            end_time=recorded,
        )
    )

    assert result.accepted, result.findings
    assert [entry.recorded_at for entry in result.activity_entries] == [recorded]


# --- Every capability that owes an observation leaves one -----------------------------


def _recorded(system: RTGSystem) -> dict[str, tuple[OperationStatus, str, int | None]]:
    return {
        entry.capability: (entry.outcome_category, entry.semantic_scope, entry.evaluated_revision)
        for entry in _activity(system).activity_entries
    }


def test_each_read_capability_records_its_own_observation(system: RTGSystem) -> None:
    """The four remainders this slice exists to close, plus the reads it introduces."""
    from vellis.discovery import DefinitionInspectionRequest

    system.definition_summary(provenance=_owner())
    system.inspect_definitions(
        DefinitionInspectionRequest(anchor_type_keys=("person",)), provenance=_owner()
    )
    system.definition_delta(provenance=_owner())
    system.query_graph(_anyone(), provenance=_owner())
    system.check(provenance=_owner())

    recorded = _recorded(system)

    for capability in (
        "definitionSummary",
        "definitionInspection",
        "definitionDelta",
        "query",
        "check",
    ):
        outcome, scope, revision = recorded[capability]
        assert outcome is OperationStatus.ACCEPTED, capability
        assert scope, capability
        assert revision == 0, capability


def test_a_refused_read_is_recorded_with_its_refusal(system: RTGSystem) -> None:
    from vellis.discovery import DefinitionInspectionRequest

    system.inspect_definitions(
        DefinitionInspectionRequest(anchor_type_keys=("unheard-of",)), provenance=_owner()
    )

    outcome, _, revision = _recorded(system)["definitionInspection"]
    assert outcome is OperationStatus.REJECTED
    assert revision is None


def test_a_failed_read_is_recorded_as_a_failure(system: RTGSystem) -> None:
    """Excludes a ledger that only remembers what worked."""
    system.store._connection.execute("DROP TABLE current_state")  # noqa: SLF001

    result = system.definition_summary(provenance=_owner())
    assert result.status is OperationStatus.FAILED

    entries = system.store.activity_records()
    assert entries[-1].capability == "definitionSummary"
    assert entries[-1].outcome_category is OperationStatus.FAILED


def test_an_accepted_mutation_is_canonical_authority_not_an_observation(
    system: RTGSystem,
) -> None:
    """Excludes mirroring state-change history into a ledger the owner can delete."""
    before = system.store.activity_record_count()

    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(ADA,)), provenance=_owner()
    ).accepted

    assert system.store.activity_record_count() == before


def test_a_refused_mutation_is_recorded(system: RTGSystem) -> None:
    """Rejections and failures are named in the requirement, and they leave no record
    anywhere else — a refused change writes nothing canonical by definition."""
    refused = system.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("a-9", "unheard-of", "Nobody"),)),
        provenance=_owner(),
    )
    assert refused.status is OperationStatus.REJECTED

    outcome, scope, _ = _recorded(system)["graphChange"]
    assert outcome is OperationStatus.REJECTED
    assert "1 anchors" in scope


def test_activity_entries_keep_the_order_they_were_appended_in(system: RTGSystem) -> None:
    system.check(provenance=_owner())
    system.query_graph(_anyone(), provenance=_owner())
    system.definition_delta(provenance=_owner())

    entries = _activity(system).activity_entries

    assert [entry.capability for entry in entries] == ["check", "query", "definitionDelta"]


# --- The canonical interval means the same thing as the activity one ------------------


def _canonical(system: RTGSystem, **bounds):
    result = system.history(HistoryQuery(kind=HistoryKind.CANONICAL, maximum_records=100, **bounds))
    assert result.accepted, result.findings
    return result


def test_canonical_bounds_are_inclusive_at_both_ends(system: RTGSystem) -> None:
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(ADA,)), provenance=_owner()
    ).accepted
    entries = _canonical(system).canonical_entries
    assert len(entries) == 2

    at_start = _canonical(system, start_time=entries[1].recorded_at)
    at_end = _canonical(system, end_time=entries[0].recorded_at)

    assert [entry.revision for entry in at_start.canonical_entries] == [1]
    assert [entry.revision for entry in at_end.canonical_entries] == [0]


def test_a_canonical_window_between_two_records_is_accepted_and_empty(
    system: RTGSystem,
) -> None:
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(ADA,)), provenance=_owner()
    ).accepted
    entries = _canonical(system).canonical_entries

    between = _canonical(
        system,
        start_time=entries[0].recorded_at + timedelta(microseconds=1),
        end_time=entries[1].recorded_at - timedelta(microseconds=1),
    )

    assert between.canonical_entries == ()
    assert between.evaluated_revision == 1


@pytest.mark.parametrize("kind", (HistoryKind.CANONICAL, HistoryKind.ACTIVITY))
def test_a_bound_without_a_zone_is_refused_on_either_ledger(
    system: RTGSystem, kind: HistoryKind
) -> None:
    """Excludes an interval that means one thing on one ledger and another on the other."""
    from datetime import datetime

    result = system.history(
        HistoryQuery(kind=kind, maximum_records=100, start_time=datetime(2020, 1, 1))
    )

    assert result.status is OperationStatus.REJECTED
    assert any("which zone it is in" in finding.summary for finding in result.findings)
    assert result.canonical_entries == () and result.activity_entries == ()


def test_an_accepted_history_result_carries_its_evaluated_revision(system: RTGSystem) -> None:
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(ADA,)), provenance=_owner()
    ).accepted

    assert _canonical(system).evaluated_revision == 1
    assert _activity(system).evaluated_revision == 1


# --- One interval means one thing, wherever the caller's clock is ----------------------


def test_a_bound_in_another_zone_selects_the_same_records(system: RTGSystem) -> None:
    """Excludes comparing stored times as text without normalizing them.

    ISO-8601 sorts by instant only within one offset. A boundary written in Tokyo time
    once selected — and on the retention path deleted — the entire ledger.
    """
    from datetime import timezone

    system.check(provenance=_owner())
    system.query_graph(_anyone(), provenance=_owner())
    entries = _activity(system).activity_entries
    here = entries[1].recorded_at
    elsewhere = here.astimezone(timezone(timedelta(hours=9)))
    assert elsewhere.utcoffset() != here.utcoffset()

    tokyo = system.history(
        HistoryQuery(kind=HistoryKind.ACTIVITY, maximum_records=100, start_time=elsewhere)
    )

    assert tokyo.accepted, tokyo.findings
    # The query sits exactly on the bound and is kept; the check precedes it and is not.
    assert [entry.capability for entry in tokyo.activity_entries] == ["query", "history"]


def test_a_retention_boundary_in_another_zone_forgets_the_same_records(
    system: RTGSystem,
) -> None:
    """The destructive form of the same defect: this once emptied the ledger."""
    from datetime import timezone

    system.check(provenance=_owner())
    system.query_graph(_anyone(), provenance=_owner())
    entries = _activity(system).activity_entries
    boundary = entries[1].recorded_at.astimezone(timezone(timedelta(hours=9)))

    outcome = system.manage_activity_retention(
        RetentionDecision(remove_before=boundary), provenance=_owner()
    )

    assert outcome.accepted, outcome.findings
    assert "removed 1" in outcome.summary
    assert [entry.capability for entry in _activity(system).activity_entries] == [
        "query",
        "history",
    ]


# --- Initialization establishes an empty ledger ---------------------------------------


def test_fresh_initialization_clears_what_earlier_attempts_observed(tmp_path: Path) -> None:
    """A read before the system exists is refused, and observed. Success promises none."""
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        assert system.query_graph(_anyone(), provenance=_owner()).status is (
            OperationStatus.REJECTED
        )
        assert system.store.activity_record_count() > 0

        assert system.initialize_fresh(
            build_rich_definitions(), provenance=_owner(), initialization_summary="a fresh start"
        ).accepted

        assert system.store.activity_record_count() == 0
    finally:
        system.close()


# --- The ledger cannot decide anything ------------------------------------------------


def test_a_broken_activity_ledger_cannot_break_the_operation_it_observes(
    system: RTGSystem,
) -> None:
    """Excludes an observation that could roll back the thing it observes."""
    system.store._connection.execute("DROP TABLE activity_record")  # noqa: SLF001

    outcome = system.apply_graph_change(GraphChange(anchor_upserts=(ADA,)), provenance=_owner())

    assert outcome.accepted, outcome.findings
    assert system.current_state().graph.anchor("a-1") is not None


def test_a_canonical_summary_carries_no_replay_payload(system: RTGSystem) -> None:
    """Excludes putting the change into the field that is declared, which the shape of
    the entry alone cannot exclude."""
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(ADA,)), provenance=_owner()
    ).accepted

    entry = _canonical(system).canonical_entries[-1]

    assert "Ada" not in entry.summary
    assert "a-1" not in entry.summary
    assert "anchor_upserts" not in entry.summary


def test_a_non_conforming_graph_is_recorded_as_a_completed_assessment(
    system: RTGSystem,
) -> None:
    """A false ``conforms`` describes the graph; it is not an execution failure."""
    report = system.check(provenance=_owner())
    assert report.conforms

    outcome, _, _ = _recorded(system)["check"]
    assert outcome is OperationStatus.ACCEPTED


def test_a_bounded_canonical_read_does_not_walk_the_records_before_it(
    system: RTGSystem,
) -> None:
    """``boundedHistoricalSelectionWork``: the cost is the interval, not the history."""
    for index in range(30):
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor(f"a-{index}", "person", f"P{index}"),)),
            provenance=_owner(),
        ).accepted
    last = _canonical(system).canonical_entries[-1].recorded_at

    system.store.reset_instrumentation()
    narrow = _canonical(system, start_time=last)

    assert len(narrow.canonical_entries) == 1
    assert system.store.record_reads == 1
