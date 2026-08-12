"""Evidence for how Vellis's work grows, and what it refuses to grow with.

Covers ``VellisVerification::currentWorkScaling``,
``VellisVerification::historicalSelectionScaling``, and
``VellisVerification::replayCharacterization``, and with them
``VellisRequirements::historyIndependentCurrentWork`` and
``boundedHistoricalSelectionWork``.

Earlier slices each showed their own operation reading no canonical record. What is
missing until it is done together is the comparison the requirements are actually about:
the same work, over the same current state, behind histories of different lengths. One
system proves nothing about growth — it has one history length — so every claim here is
made against at least two.

The measure is semantic record processing, because that is what the requirements bound.
Duration is recorded where the replay case asks for it, in seconds, and nothing asserts
on its value: a number from this machine is not a budget, and the analysis that would
set one says so itself.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from characterization import (
    OWNER,
    Measurement,
    commit_definition_changes,
    commit_graph_transitions,
    establish,
    ledger_scans,
    measure,
    observe,
)

from vellis.activity import ActivityRecord, HistoryKind, HistoryQuery, HistoryResult
from vellis.canonical import canonical_state_equal
from vellis.changes import GraphChange
from vellis.discovery import DefinitionInspectionRequest
from vellis.graph import Anchor, graph_equal
from vellis.history import RevisionSelection, TimeSelection
from vellis.outcomes import OperationStatus
from vellis.query import AnchorGroup, AnchorProjection, GraphQuery, ReturnShape
from vellis.replay import ReplayRequest
from vellis.system import RTGSystem

CHURN = 30
"""How many extra revisions the long history carries that the short one does not."""

ARRIVAL = Anchor(uuid="arrival", type_key="person", display_name="New")


def _people(maximum_rows: int = 100) -> GraphQuery:
    return GraphQuery(
        anchor_groups=(AnchorGroup(name="people", anchor_type="person"),),
        return_shape=ReturnShape(
            projections=(AnchorProjection(name="who", anchor_group="people"),)
        ),
        maximum_rows=maximum_rows,
    )


def _all_canonical(system: RTGSystem) -> HistoryResult:
    result = system.history(
        HistoryQuery(kind=HistoryKind.CANONICAL, maximum_records=500), provenance=OWNER
    )
    assert result.accepted, result.findings
    return result


# --- Two histories, one current state -------------------------------------------------


def _residents() -> tuple[Anchor, ...]:
    return tuple(
        Anchor(uuid=f"a-{index}", type_key="person", display_name=f"P{index}") for index in range(6)
    )


def _short_history(path: Path) -> RTGSystem:
    """Six people, reached in one revision."""
    system = establish(path)
    outcome = system.apply_graph_change(GraphChange(anchor_upserts=_residents()), provenance=OWNER)
    assert outcome.accepted, outcome.findings
    return system


def _long_history(path: Path) -> RTGSystem:
    """The same six people, reached the long way, behind thirty more revisions.

    The churn adds and then removes a resident, so the graph it leaves is the graph it
    found. That is what makes the two current states comparable while the histories
    behind them are not.
    """
    system = establish(path)
    for resident in _residents():
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(resident,)), provenance=OWNER
        ).accepted
    for index in range(CHURN // 2):
        passing = Anchor(uuid=f"x-{index}", type_key="person", display_name="Passing through")
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(passing,)), provenance=OWNER
        ).accepted
        assert system.apply_graph_change(
            GraphChange(anchor_removals=(passing.uuid,)), provenance=OWNER
        ).accepted
    return system


@pytest.fixture
def histories(tmp_path: Path):
    short = _short_history(tmp_path / "short.sqlite3")
    long = _long_history(tmp_path / "long.sqlite3")
    try:
        yield short, long
    finally:
        short.close()
        long.close()


def test_the_two_histories_carry_the_same_current_state_at_different_lengths(
    histories: tuple[RTGSystem, RTGSystem],
) -> None:
    """Without this, every comparison below could be between two different questions."""
    short, long = histories
    here, there = short.current_state(), long.current_state()

    assert graph_equal(here.graph, there.graph)
    assert here.definition_delta is None and there.definition_delta is None
    assert here.revision != there.revision
    assert long.store.canonical_record_count() == short.store.canonical_record_count() + CHURN + 5


# --- Current work ignores history length ----------------------------------------------


def _current_operations(system: RTGSystem) -> dict[str, Measurement]:
    """Measure each operation the current-work requirement names, once each."""
    inspection = DefinitionInspectionRequest(anchor_type_keys=("person",))
    unwelcome = GraphChange(
        anchor_upserts=(Anchor(uuid="a-0", type_key="unheard-of", display_name="?"),)
    )
    return {
        "definition summary": measure(
            system, lambda: system.definition_summary(provenance=OWNER)
        ).cost,
        "definition inspection": measure(
            system, lambda: system.inspect_definitions(inspection, provenance=OWNER)
        ).cost,
        "graph query": measure(
            system, lambda: system.query_graph(_people(), provenance=OWNER)
        ).cost,
        "conformance assessment": measure(system, lambda: system.check(provenance=OWNER)).cost,
        "delta retrieval": measure(system, lambda: system.definition_delta(provenance=OWNER)).cost,
        "change validation": measure(
            system, lambda: system.apply_graph_change(unwelcome, provenance=OWNER)
        ).cost,
    }


def test_every_named_current_operation_visits_no_record_of_either_ledger(
    histories: tuple[RTGSystem, RTGSystem],
) -> None:
    """``historyIndependentCurrentWork``: current work reads the projection, not history.

    Six operations rather than one, because the requirement names six and an
    implementation that reached for history on only the least-used of them would satisfy
    any narrower check.
    """
    for system in histories:
        for name, cost in _current_operations(system).items():
            assert cost.canonical_record_visits == 0, name
            assert cost.activity_record_visits == 0, name
            assert not cost.touches("canonical_record"), name


def test_current_work_costs_the_same_behind_a_thirty_revision_longer_history(
    histories: tuple[RTGSystem, RTGSystem],
) -> None:
    """Excludes work that grows with history slowly enough for one system to hide it."""
    short, long = histories
    here, there = _current_operations(short), _current_operations(long)

    for name in here:
        assert here[name].canonical_record_visits == there[name].canonical_record_visits, name
        assert len(here[name].statements) == len(there[name].statements), name


def test_current_work_still_grows_with_the_things_it_is_allowed_to_grow_with(
    tmp_path: Path,
) -> None:
    """The requirement permits scaling with current state, and this shows it happening.

    An answer that grew with the graph while reading no record of history is the permitted
    shape, and stating it here keeps the zeros above from reading as a claim that current
    work is free. That the record counter is not simply stuck at zero is shown where it
    reports a real cost: the historical query, the bounded intervals, and replay.
    """
    system = establish(tmp_path / "vellis.sqlite3")
    try:
        commit_graph_transitions(system, 4)
        small = system.query_graph(_people(), provenance=OWNER)
        commit_graph_transitions(system, 20, prefix="more")
        large = system.query_graph(_people(), provenance=OWNER)

        assert small.accepted and large.accepted
        assert len(large.rows) > len(small.rows)
        cost = measure(system, lambda: system.query_graph(_people(), provenance=OWNER)).cost
        assert cost.canonical_record_visits == 0
    finally:
        system.close()


def test_a_returned_result_is_bounded_by_what_was_asked_for_not_by_history(
    histories: tuple[RTGSystem, RTGSystem],
) -> None:
    """Requested return bounds are the other permitted dimension, and they still bind."""
    _, long = histories
    refused = long.query_graph(_people(maximum_rows=2), provenance=OWNER)

    assert refused.status is OperationStatus.REJECTED
    assert not refused.rows


# --- One mutation, and the prefix it leaves alone -------------------------------------


def _prefix(system: RTGSystem) -> tuple[object, ...]:
    """Return every canonical record as it currently reads, for later comparison."""
    return tuple(system.store.canonical_summaries())


def test_one_commit_appends_one_record_and_moves_the_projection_together(
    histories: tuple[RTGSystem, RTGSystem],
) -> None:
    """``atomicCanonicalRevision`` at the terminal position: one effect, one record."""
    for system in histories:
        before = system.current_state()
        records = system.store.canonical_record_count()

        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(ARRIVAL,)), provenance=OWNER
        ).accepted

        after = system.current_state()
        assert after.revision == before.revision + 1
        assert system.store.canonical_record_count() == records + 1
        assert canonical_state_equal(after, system.replay())


def _commit_cost(system: RTGSystem) -> Measurement:
    """Measure one ordinary commit, having recorded the prefix it must leave alone."""
    before = _prefix(system)
    measured = measure(
        system,
        lambda: system.apply_graph_change(GraphChange(anchor_upserts=(ARRIVAL,)), provenance=OWNER),
    )
    assert measured.value.accepted, measured.value.findings
    assert _prefix(system)[: len(before)] == before
    return measured.cost


def test_committing_neither_traverses_nor_rewrites_the_prefix_behind_it(
    histories: tuple[RTGSystem, RTGSystem],
) -> None:
    """``historyIndependentCurrentWork``: terminal-position work, not prefix work.

    Two claims at once, because either alone would miss the other: the commit does not
    *read* the earlier records, and it does not *change* them. A ledger whose earlier
    entries were rewritten on every append would still cost the same to read.
    """
    short, long = histories
    here, there = _commit_cost(short), _commit_cost(long)

    assert here.canonical_record_visits == 0
    assert there.canonical_record_visits == 0
    assert len(here.statements) == len(there.statements)
    assert not ledger_scans(short, here)
    assert not ledger_scans(long, there)


@pytest.mark.parametrize("length", [0, 30])
def test_a_commit_survives_an_ordinary_restart_at_either_history_length(
    tmp_path: Path, length: int
) -> None:
    """Recoverably atomic: what the projection says is what a reopened store says."""
    system = establish(tmp_path / f"vellis-{length}.sqlite3")
    path = system.store.path
    try:
        commit_graph_transitions(system, length)
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(ARRIVAL,)), provenance=OWNER
        ).accepted
        expected = system.current_state()
    finally:
        system.close()

    reopened = RTGSystem.open(path)
    try:
        assert canonical_state_equal(reopened.current_state(), expected)
        assert canonical_state_equal(reopened.replay(), expected)
    finally:
        reopened.close()


def test_appending_activity_visits_no_canonical_record_and_reconstructs_nothing(
    histories: tuple[RTGSystem, RTGSystem],
) -> None:
    """``historyIndependentCurrentWork``: observation stays observational."""
    _, long = histories
    before = long.replay()
    record = ActivityRecord(
        capability="query",
        outcome_category=OperationStatus.ACCEPTED,
        semantic_scope="anchor groups people",
        summary="a read happened",
        provenance=OWNER,
        recorded_at=datetime.now(UTC),
    )

    cost = measure(long, lambda: long.store.append_activity(record)).cost

    assert cost.canonical_record_visits == 0
    assert not cost.touches("canonical_record")
    assert not cost.touches("current_state")
    assert canonical_state_equal(long.replay(), before)


def test_observation_does_not_get_more_expensive_as_observations_accumulate(
    tmp_path: Path,
) -> None:
    """Excludes an append that reads the activity ledger to find its own position."""
    system = establish(tmp_path / "vellis.sqlite3")

    def append() -> None:
        system.store.append_activity(
            ActivityRecord(
                capability="query",
                outcome_category=OperationStatus.ACCEPTED,
                semantic_scope="anchor groups people",
                summary="a read happened",
                provenance=OWNER,
                recorded_at=datetime.now(UTC),
            )
        )

    try:
        early = measure(system, append).cost
        observe(system, 40)
        late = measure(system, append).cost

        assert early.activity_record_visits == 0
        assert late.activity_record_visits == 0
        assert len(early.statements) == len(late.statements)
    finally:
        system.close()


# --- Historical selection pays for the interval, not the prefix -----------------------


@pytest.mark.parametrize("excluded", [4, 40])
def test_a_narrow_canonical_interval_costs_the_interval_whatever_precedes_it(
    tmp_path: Path, excluded: int
) -> None:
    """``boundedHistoricalSelectionWork``: selection plus the interval, and nothing else.

    Run behind two very different prefixes, so a cost proportional to the excluded
    records would show as a difference rather than as one unexplained number.
    """
    system = establish(tmp_path / f"vellis-{excluded}.sqlite3")
    try:
        commit_graph_transitions(system, excluded, prefix="old")
        commit_graph_transitions(system, 3, prefix="wanted")
        window = _all_canonical(system).canonical_entries[-3:]

        measured = measure(
            system,
            lambda: system.history(
                HistoryQuery(
                    kind=HistoryKind.CANONICAL,
                    maximum_records=500,
                    start_time=window[0].recorded_at,
                    end_time=window[-1].recorded_at,
                ),
                provenance=OWNER,
            ),
        )

        assert measured.value.accepted, measured.value.findings
        assert len(measured.value.canonical_entries) == 3
        assert measured.cost.canonical_record_visits == 3
        assert not ledger_scans(system, measured.cost)
    finally:
        system.close()


@pytest.mark.parametrize("excluded", [4, 40])
def test_a_narrow_activity_interval_costs_the_interval_whatever_precedes_it(
    tmp_path: Path, excluded: int
) -> None:
    """The same bound over the other ledger, which the requirement names separately."""
    system = establish(tmp_path / f"vellis-{excluded}.sqlite3")
    try:
        base = datetime(2026, 1, 1, tzinfo=UTC)
        for index in range(excluded + 3):
            system.store.append_activity(
                ActivityRecord(
                    capability="query",
                    outcome_category=OperationStatus.ACCEPTED,
                    semantic_scope="anchor groups people",
                    summary=f"read {index}",
                    provenance=OWNER,
                    recorded_at=base + timedelta(minutes=index),
                )
            )
        start = base + timedelta(minutes=excluded)
        end = base + timedelta(minutes=excluded + 2)

        measured = measure(
            system,
            lambda: system.history(
                HistoryQuery(
                    kind=HistoryKind.ACTIVITY,
                    maximum_records=500,
                    start_time=start,
                    end_time=end,
                ),
                provenance=OWNER,
            ),
        )

        assert measured.value.accepted, measured.value.findings
        assert len(measured.value.activity_entries) == 3
        assert measured.cost.activity_record_visits == 3
        assert not ledger_scans(system, measured.cost)
    finally:
        system.close()


@pytest.mark.parametrize("length", [4, 40])
def test_resolving_a_revision_or_a_time_does_not_depend_on_ledger_length(
    tmp_path: Path, length: int
) -> None:
    """``boundedHistoricalSelectionWork``: a selector is sought, not scanned for.

    A time selector is the one that could quietly walk: the greatest revision at or
    before an instant is also what an aggregate over the whole ledger computes. Two
    records either way — one to resolve the selector, one for the history base — with no
    definition-changing transition in a graph-only history to add to them.
    """
    system = establish(tmp_path / f"vellis-{length}.sqlite3")
    try:
        commit_graph_transitions(system, length, prefix="old")
        wanted = system.current_state().revision - 1
        moment = _all_canonical(system).canonical_entries[-1].recorded_at

        by_revision = measure(
            system,
            lambda: system.definition_summary(
                selection=RevisionSelection(revision=wanted), provenance=OWNER
            ),
        )
        by_time = measure(
            system,
            lambda: system.definition_summary(
                selection=TimeSelection(time=moment), provenance=OWNER
            ),
        )

        for measured in (by_revision, by_time):
            assert measured.value.accepted, measured.value.findings
            assert measured.cost.canonical_record_visits == 2
            assert not ledger_scans(system, measured.cost)
    finally:
        system.close()


@pytest.mark.parametrize("graph_only", [2, 40])
def test_a_historical_vocabulary_does_not_pay_for_unrelated_graph_transitions(
    tmp_path: Path, graph_only: int
) -> None:
    """``boundedHistoricalSelectionWork``: definition history is what a vocabulary costs.

    Definition-changing history is held at three changes while graph-only history varies
    by a factor of twenty. A reconstruction that replayed everything would show it.
    """
    system = establish(tmp_path / f"vellis-{graph_only}.sqlite3")
    try:
        commit_definition_changes(system, 3)
        commit_graph_transitions(system, graph_only)
        revision = system.current_state().revision
        request = DefinitionInspectionRequest(anchor_type_keys=("person",))

        summary = measure(
            system,
            lambda: system.definition_summary(
                selection=RevisionSelection(revision=revision), provenance=OWNER
            ),
        )
        inspection = measure(
            system,
            lambda: system.inspect_definitions(
                request, selection=RevisionSelection(revision=revision), provenance=OWNER
            ),
        )

        for measured in (summary, inspection):
            assert measured.value.accepted, measured.value.findings
            # Resolve the selector, read the base, and read the six definition-changing
            # records — never the graph-only ones, however many of them there are.
            assert measured.cost.canonical_record_visits == 8
    finally:
        system.close()


def test_a_historical_graph_does_pay_for_its_transitions(tmp_path: Path) -> None:
    """The separately characterized case, kept honest by measuring it too.

    The requirement exempts historical graph reconstruction from the bound rather than
    claiming it is free. Showing the exemption is real is what stops the vocabulary
    result above from being read as a claim about graphs as well.
    """
    system = establish(tmp_path / "vellis.sqlite3")
    try:
        commit_graph_transitions(system, 20)
        revision = system.current_state().revision
        measured = measure(
            system,
            lambda: system.query_graph(
                _people(), selection=RevisionSelection(revision=revision), provenance=OWNER
            ),
        )

        assert measured.value.accepted, measured.value.findings
        assert measured.cost.canonical_record_visits > 20
    finally:
        system.close()


# --- Replay is characterized by its required tail -------------------------------------


def _seeded_from_snapshot(source: RTGSystem, path: Path, tail: int) -> RTGSystem:
    """Return a new lineage based on ``source``'s state, advanced by ``tail`` revisions.

    Basing the new ledger on a snapshot is what makes the required replay tail a
    dimension of its own: the state carries the same history behind it either way, but
    only ``tail`` records have to be replayed to reach it.
    """
    captured = source.create_snapshot(provenance=OWNER)
    assert captured.accepted and captured.snapshot is not None
    system = RTGSystem.open(path)
    outcome = system.initialize_from_snapshot(
        ReplayRequest(snapshot=captured.snapshot),
        provenance=OWNER,
        initialization_summary="continued from a snapshot",
    )
    assert outcome.accepted, outcome.findings
    commit_graph_transitions(system, tail, prefix=f"t{tail}")
    return system


@pytest.mark.parametrize("tail", [0, 4, 16])
def test_replay_visits_exactly_its_required_tail_and_reaches_the_same_state(
    tmp_path: Path, tail: int
) -> None:
    """``replayCharacterization``: the dependency is the tail, and replay still agrees."""
    source = establish(tmp_path / "source.sqlite3")
    try:
        commit_graph_transitions(source, 12, prefix="before")
        system = _seeded_from_snapshot(source, tmp_path / f"tail-{tail}.sqlite3", tail)
        try:
            measured = measure(system, system.replay)

            assert canonical_state_equal(measured.value, system.current_state())
            # One base record, and one record for every transition that must be replayed.
            assert measured.cost.canonical_record_visits == tail + 1
            assert measured.cost.duration_seconds >= 0.0
        finally:
            system.close()
    finally:
        source.close()


@pytest.mark.parametrize("depth", [4, 16, 32])
def test_restoring_a_past_state_costs_the_tail_it_has_to_replay(tmp_path: Path, depth: int) -> None:
    """The fourth operation the requirement exempts, and so the fourth to characterize.

    Restoration is not bounded by the selection rule — reaching a past graph means
    replaying the transitions that produced it — but the requirement still says it must
    be characterized rather than left unmeasured. The cost is the tail up to the selected
    revision plus resolving the selector and reading the base; what it is *not* is the
    records after the selected revision, which is why restoring something old from a much
    longer ledger costs what restoring it from a shorter one costs.
    """
    system = establish(tmp_path / f"vellis-{depth}.sqlite3")
    try:
        commit_graph_transitions(system, 40)

        measured = measure(
            system,
            lambda: system.restore_historical_state(
                RevisionSelection(revision=depth), provenance=OWNER
            ),
        )

        assert measured.value.accepted, measured.value.findings
        assert measured.cost.canonical_record_visits == depth + 2
        assert measured.cost.duration_seconds >= 0.0
    finally:
        system.close()


@pytest.mark.parametrize("tail", [0, 4, 16])
def test_an_ordinary_restart_does_not_depend_on_the_required_tail(
    tmp_path: Path, tail: int
) -> None:
    """The other half of the characterization, and the more owner-visible half.

    Starting up ordinarily reads the projection, so it costs the same at every tail
    length. Replay is what the tail is charged to, and the two are different paths.
    """
    source = establish(tmp_path / "source.sqlite3")
    try:
        commit_graph_transitions(source, 12, prefix="before")
        system = _seeded_from_snapshot(source, tmp_path / f"tail-{tail}.sqlite3", tail)
        expected = system.current_state()
        path = system.store.path
        system.close()

        reopened = RTGSystem.open(path)
        try:
            measured = measure(reopened, reopened.current_state)
            assert canonical_state_equal(measured.value, expected)
            assert measured.cost.canonical_record_visits == 0
            assert measured.cost.duration_seconds >= 0.0
        finally:
            reopened.close()
    finally:
        source.close()
