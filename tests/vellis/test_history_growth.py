"""The ``VellisVerification::historyGrowth`` characterization.

The analysis case asks for something different from the verification cases beside it. It
does not ask whether Vellis meets a target; it asks what Vellis's work is a function of,
measured along each dimension separately, so that latency, startup, and storage budgets
can be chosen *later* — once a runtime, a hardware profile, and a real owner's data
exist. None of those exist yet, so no number here is a budget and nothing asserts that a
measurement is small enough.

What is asserted is the shape: which dimensions each measure responds to and which it
ignores. That is the durable result. Absolute values belong to the machine that produced
them, so they are emitted with their units rather than frozen into assertions; run

    uv run pytest tests/vellis/test_history_growth.py -s

to read the table this produces here.

The six dimensions are varied one at a time. Varying two at once would produce a table
in which no column could be attributed to anything.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from characterization import (
    OWNER,
    commit_definition_changes,
    commit_graph_transitions,
    establish,
    measure,
    storage_bytes,
)

from vellis.activity import ActivityRecord, HistoryKind, HistoryQuery, RetentionDecision
from vellis.canonical import canonical_state_equal
from vellis.changes import GraphChange
from vellis.graph import Anchor
from vellis.outcomes import OperationStatus
from vellis.query import AnchorGroup, AnchorProjection, GraphQuery, ReturnShape
from vellis.replay import ReplayRequest
from vellis.system import RTGSystem

DIMENSIONS = (
    "current graph size",
    "canonical ledger length",
    "definition change density",
    "activity history length",
    "selected interval size",
    "required replay tail",
)

INTERVAL = 3
"""The interval size held fixed while the dimensions that are not it are varied."""


@dataclass(frozen=True, slots=True)
class Observation:
    """One row of the characterization. Every measure names its own unit."""

    dimension: str
    level: int
    current_work_record_visits: int
    current_work_duration_seconds: float
    selection_record_visits: int
    selected_interval_records: int
    replay_record_visits: int
    replay_duration_seconds: float
    startup_record_visits: int
    startup_duration_seconds: float
    canonical_ledger_records: int
    activity_ledger_records: int
    storage_bytes: int


def _people() -> GraphQuery:
    return GraphQuery(
        anchor_groups=(AnchorGroup(name="people", anchor_type="person"),),
        return_shape=ReturnShape(
            projections=(AnchorProjection(name="who", anchor_group="people"),)
        ),
        maximum_rows=1000,
    )


def _observe_one(system: RTGSystem, *, dimension: str, level: int, interval: int) -> Observation:
    """Take every measure of one system, along one dimension at one level."""
    current = measure(
        system,
        lambda: (
            system.query_graph(_people(), provenance=OWNER),
            system.definition_summary(provenance=OWNER),
        ),
    )
    assert all(answer.accepted for answer in current.value)

    entries = system.history(
        HistoryQuery(kind=HistoryKind.CANONICAL, maximum_records=5000), provenance=OWNER
    ).canonical_entries
    window = entries[-interval:]
    selection = measure(
        system,
        lambda: system.history(
            HistoryQuery(
                kind=HistoryKind.CANONICAL,
                maximum_records=5000,
                start_time=window[0].recorded_at,
                end_time=window[-1].recorded_at,
            ),
            provenance=OWNER,
        ),
    )
    assert selection.value.accepted, selection.value.findings

    replay = measure(system, system.replay)
    assert canonical_state_equal(replay.value, system.current_state())

    reopened = RTGSystem.open(system.store.path)
    try:
        startup = measure(reopened, reopened.current_state)
        assert canonical_state_equal(startup.value, replay.value)
    finally:
        reopened.close()

    return Observation(
        dimension=dimension,
        level=level,
        current_work_record_visits=current.cost.canonical_record_visits,
        current_work_duration_seconds=current.cost.duration_seconds,
        selection_record_visits=selection.cost.canonical_record_visits,
        selected_interval_records=len(selection.value.canonical_entries),
        replay_record_visits=replay.cost.canonical_record_visits,
        replay_duration_seconds=replay.cost.duration_seconds,
        startup_record_visits=startup.cost.canonical_record_visits,
        startup_duration_seconds=startup.cost.duration_seconds,
        canonical_ledger_records=system.store.canonical_record_count(),
        activity_ledger_records=system.store.activity_record_count(),
        storage_bytes=storage_bytes(system),
    )


# --- Building one dimension at a time --------------------------------------------------


def _by_graph_size(path: Path, level: int) -> RTGSystem:
    """Vary the current graph, holding the ledger at one transition."""
    system = establish(path)
    assert system.apply_graph_change(
        GraphChange(
            anchor_upserts=tuple(
                Anchor(uuid=f"a-{index}", type_key="person", display_name=f"P{index}")
                for index in range(level)
            )
        ),
        provenance=OWNER,
    ).accepted
    commit_graph_transitions(system, INTERVAL, prefix="window")
    return system


def _by_ledger_length(path: Path, level: int) -> RTGSystem:
    """Vary how many graph transitions the ledger holds."""
    system = establish(path)
    commit_graph_transitions(system, level)
    return system


def _by_definition_density(path: Path, level: int) -> RTGSystem:
    """Vary how many of a fixed-length history's records changed definitions."""
    system = establish(path)
    commit_definition_changes(system, level)
    commit_graph_transitions(system, INTERVAL, prefix="window")
    return system


def _by_activity_length(path: Path, level: int) -> RTGSystem:
    """Vary the observational ledger, holding the canonical one fixed."""
    system = establish(path)
    commit_graph_transitions(system, INTERVAL, prefix="window")
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(level):
        system.store.append_activity(
            ActivityRecord(
                capability="query",
                outcome_category=OperationStatus.ACCEPTED,
                semantic_scope="anchor groups people",
                summary=f"read {index}",
                provenance=OWNER,
                recorded_at=base + timedelta(seconds=index),
            )
        )
    return system


def _by_replay_tail(path: Path, level: int) -> RTGSystem:
    """Vary how many records a rebuild must replay, holding the state's depth fixed."""
    source = establish(path.with_name(f"source-{level}.sqlite3"))
    try:
        commit_graph_transitions(source, 12, prefix="before")
        captured = source.create_snapshot(provenance=OWNER)
        assert captured.accepted and captured.snapshot is not None
    finally:
        source.close()
    system = RTGSystem.open(path)
    assert system.initialize_from_snapshot(
        ReplayRequest(snapshot=captured.snapshot),
        provenance=OWNER,
        initialization_summary="continued from a snapshot",
    ).accepted
    commit_graph_transitions(system, max(level, INTERVAL), prefix="tail")
    return system


BUILDERS = {
    "current graph size": _by_graph_size,
    "canonical ledger length": _by_ledger_length,
    "definition change density": _by_definition_density,
    "activity history length": _by_activity_length,
    "required replay tail": _by_replay_tail,
}

LEVELS = (4, 16, 48)


@pytest.fixture(scope="module")
def characterization(tmp_path_factory: pytest.TempPathFactory) -> tuple[Observation, ...]:
    """Measure every dimension at every level once, and emit the table it produces."""
    root = tmp_path_factory.mktemp("history-growth")
    observations: list[Observation] = []
    for dimension, build in BUILDERS.items():
        for level in LEVELS:
            system = build(root / f"{dimension.replace(' ', '-')}-{level}.sqlite3", level)
            try:
                observations.append(
                    _observe_one(system, dimension=dimension, level=level, interval=INTERVAL)
                )
            finally:
                system.close()

    # The interval is the one dimension that is a property of the question rather than of
    # the system, so it is varied against one fixed history instead of against many.
    system = _by_ledger_length(root / "selected-interval.sqlite3", max(LEVELS))
    try:
        for level in LEVELS:
            observations.append(
                _observe_one(
                    system, dimension="selected interval size", level=level, interval=level
                )
            )
    finally:
        system.close()

    print(_table(observations))
    return tuple(observations)


def _table(observations: list[Observation]) -> str:
    """Render the measurements as Markdown, units included, for a human to read."""
    columns = list(asdict(observations[0]))
    lines = [
        "",
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for observation in observations:
        row = asdict(observation)
        lines.append(
            "| "
            + " | ".join(
                f"{row[column]:.6f}" if isinstance(row[column], float) else str(row[column])
                for column in columns
            )
            + " |"
        )
    return "\n".join(lines)


def _along(observations: tuple[Observation, ...], dimension: str) -> list[Observation]:
    return sorted(
        (each for each in observations if each.dimension == dimension), key=lambda each: each.level
    )


# --- What the measurements say ---------------------------------------------------------


def test_the_characterization_covers_every_dimension_the_analysis_names(
    characterization: tuple[Observation, ...],
) -> None:
    """An analysis missing a dimension cannot support a budget over it later."""
    assert {each.dimension for each in characterization} == set(DIMENSIONS)
    for dimension in DIMENSIONS:
        assert [each.level for each in _along(characterization, dimension)] == list(LEVELS)


def test_every_measure_carries_its_unit_in_its_own_name(
    characterization: tuple[Observation, ...],
) -> None:
    """A duration without its unit is not a measurement anyone can reuse."""
    measures = [name for name in asdict(characterization[0]) if name not in {"dimension", "level"}]

    assert measures
    for name in measures:
        assert name.endswith(("_visits", "_seconds", "_bytes", "_records")), name


def test_current_work_responds_to_no_dimension_of_history(
    characterization: tuple[Observation, ...],
) -> None:
    """The strongest result in the table, and the one an owner feels every day."""
    assert {each.current_work_record_visits for each in characterization} == {0}
    assert {each.startup_record_visits for each in characterization} == {0}


def test_selection_work_is_the_interval_and_only_the_interval(
    characterization: tuple[Observation, ...],
) -> None:
    """Selection responds to the returned interval, not to what precedes it."""
    for each in characterization:
        assert each.selection_record_visits == each.selected_interval_records

    fixed = [
        each
        for each in characterization
        if each.dimension in {"canonical ledger length", "activity history length"}
    ]
    assert {each.selection_record_visits for each in fixed} == {INTERVAL}

    varied = _along(characterization, "selected interval size")
    assert [each.selection_record_visits for each in varied] == list(LEVELS)


def test_replay_responds_to_ledger_length_and_required_tail_alone(
    characterization: tuple[Observation, ...],
) -> None:
    """Replay is the work the requirement exempts, so the exemption is what to measure."""
    for dimension in ("canonical ledger length", "required replay tail"):
        visits = [each.replay_record_visits for each in _along(characterization, dimension)]
        assert visits == sorted(visits)
        assert visits[0] < visits[-1]

    unaffected = [
        each.replay_record_visits for each in _along(characterization, "current graph size")
    ]
    assert len(set(unaffected)) == 1


def test_definition_density_adds_replay_records(
    characterization: tuple[Observation, ...],
) -> None:
    """Definition changes are records too, and replay is charged for them like any other.

    Worth measuring separately from ledger length because a vocabulary change costs two
    records rather than one, so a history of the same length made of definition work is
    a longer replay than one made of graph work.
    """
    density = _along(characterization, "definition change density")
    visits = [each.replay_record_visits for each in density]

    assert visits == sorted(visits)
    assert visits[0] < visits[-1]


def test_storage_grows_with_both_ledgers_including_the_one_reading_grows(
    characterization: tuple[Observation, ...],
) -> None:
    """Storage is the budget most likely to be set first, so its drivers matter.

    Reading is one of them, which is easy to miss and worth having measured: every
    permitted read is observed, so a system that is only ever asked questions still
    grows. It grows in the observational ledger alone — the canonical one is unmoved —
    which is why forgetting activity is where that growth can be answered without
    touching what memory is.
    """
    for dimension in ("canonical ledger length", "activity history length"):
        sizes = [each.storage_bytes for each in _along(characterization, dimension)]
        assert sizes == sorted(sizes)
        assert sizes[0] < sizes[-1]

    asking = _along(characterization, "selected interval size")
    assert len({each.canonical_ledger_records for each in asking}) == 1
    activity = [each.activity_ledger_records for each in asking]
    assert activity == sorted(activity)
    assert activity[0] < activity[-1]


def test_forgetting_activity_bounds_further_growth_without_returning_the_file(
    tmp_path: Path,
) -> None:
    """What retention does to storage, measured rather than assumed.

    The obvious reading of "the owner can forget activity" is that the file gets smaller.
    It does not: the records go, their pages are reused for what comes next, and the file
    stays the size it reached. That is the difference between bounding growth and
    reclaiming space, and a storage budget written on the wrong one of those would be
    wrong in the direction that hurts — so it is measured here rather than inferred.
    """
    system = establish(tmp_path / "vellis.sqlite3")
    try:
        base = datetime(2026, 1, 1, tzinfo=UTC)
        for index in range(400):
            system.store.append_activity(
                ActivityRecord(
                    capability="query",
                    outcome_category=OperationStatus.ACCEPTED,
                    semantic_scope="anchor groups people",
                    summary=f"read {index}",
                    provenance=OWNER,
                    recorded_at=base + timedelta(seconds=index),
                )
            )
        before_records = system.store.activity_record_count()
        before_bytes = storage_bytes(system)

        forgotten = system.manage_activity_retention(
            RetentionDecision(remove_before=base + timedelta(seconds=390)), provenance=OWNER
        )

        assert forgotten.accepted, forgotten.findings
        assert system.store.activity_record_count() < before_records
        assert storage_bytes(system) >= before_bytes
    finally:
        system.close()


def test_every_duration_was_actually_timed(
    characterization: tuple[Observation, ...],
) -> None:
    """No target is asserted; that a duration exists in seconds still has to be true."""
    for each in characterization:
        assert each.current_work_duration_seconds > 0.0
        assert each.replay_duration_seconds > 0.0
        assert each.startup_duration_seconds > 0.0
