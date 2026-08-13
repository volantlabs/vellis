"""Evidence for ``VellisVerification::historicalSelection``, and the historical legs of
``::definitionDiscovery`` and ``::semanticQuery``.

One arc: commit a vocabulary, use it, retire part of it, then go back and ask the same
questions of the state as it was. The answers must be the ones that state would have
given — same query meaning, same shaping, same bounds — and a selector that resolves to
nothing must say so rather than quietly answering about now.

A time selector resolves to the greatest revision committed at or before it, so a caller
can ask about a moment when nothing happened and still get one definite answer.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from vellis.canonical import Provenance, canonical_state_equal
from vellis.changes import GraphChange
from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    GraphDefinitionSet,
    PropertyConstraint,
)
from vellis.discovery import DefinitionInspectionRequest
from vellis.graph import Anchor
from vellis.history import RevisionSelection, TimeSelection
from vellis.json_value import JsonKind
from vellis.outcomes import OperationStatus
from vellis.query import AnchorGroup, AnchorProjection, GraphQuery, ReturnShape
from vellis.system import RTGSystem

PERSON = AnchorTypeDefinition(type_key="person", description="A person the owner knows.")
RITUAL = AnchorTypeDefinition(type_key="ritual", description="Something done regularly.")
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
EARLY = GraphDefinitionSet(anchor_types=(PERSON, RITUAL), associated_data_types=(NOTE,))
LATER = GraphDefinitionSet(anchor_types=(PERSON,), associated_data_types=(NOTE,))


def _owner() -> Provenance:
    return Provenance(initiator="owner")


@pytest.fixture
def system(tmp_path: Path):
    """A vocabulary that once had rituals in it, and no longer does.

    Revision 0: person, ritual. 1: Ada. 2: a morning ritual. 3: the ritual object goes.
    4: a proposal that retires the ritual type. 5: that proposal is activated.
    """
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    assert system.initialize_fresh(
        EARLY, provenance=_owner(), initialization_summary="a fresh start"
    ).accepted
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("a-1", "person", "Ada"),)), provenance=_owner()
    ).accepted
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("r-1", "ritual", "Morning walk"),)),
        provenance=_owner(),
    ).accepted
    assert system.apply_graph_change(
        GraphChange(anchor_removals=("r-1",)), provenance=_owner()
    ).accepted
    assert system.set_definition_delta(LATER, provenance=_owner()).accepted
    assert system.activate_definition_delta(provenance=_owner()).accepted
    assert system.current_state().revision == 5
    try:
        yield system
    finally:
        system.close()


def _people() -> GraphQuery:
    return GraphQuery(
        anchor_groups=(AnchorGroup(name="who", anchor_type="person"),),
        return_shape=ReturnShape(projections=(AnchorProjection(name="p", anchor_group="who"),)),
        maximum_rows=10,
    )


def _rituals() -> GraphQuery:
    return GraphQuery(
        anchor_groups=(AnchorGroup(name="what", anchor_type="ritual"),),
        return_shape=ReturnShape(projections=(AnchorProjection(name="r", anchor_group="what"),)),
        maximum_rows=10,
    )


# --- A revision selector -------------------------------------------------------------


def test_a_query_at_a_selected_revision_sees_that_state(system: RTGSystem) -> None:
    at_two = system.query_graph(_rituals(), selection=RevisionSelection(2), provenance=_owner())

    assert at_two.accepted, at_two.findings
    assert at_two.evaluated_revision == 2
    assert [b.anchor.uuid for row in at_two.rows for b in row.anchors] == ["r-1"]


def test_the_same_query_at_a_later_revision_sees_the_later_state(system: RTGSystem) -> None:
    """Excludes evaluating every selection against current state."""
    at_three = system.query_graph(_rituals(), selection=RevisionSelection(3), provenance=_owner())

    assert at_three.accepted, at_three.findings
    assert at_three.rows == ()


def test_a_query_uses_the_definitions_in_force_at_the_selected_revision(
    system: RTGSystem,
) -> None:
    """The ritual type is retired now, so the same query is refused against current state."""
    historical = system.query_graph(_rituals(), selection=RevisionSelection(2), provenance=_owner())
    current = system.query_graph(_rituals(), provenance=_owner())

    assert historical.accepted, historical.findings
    assert current.status is OperationStatus.REJECTED
    assert any("active anchor type" in f.summary for f in current.findings)


def test_historical_evaluation_keeps_current_query_semantics(system: RTGSystem) -> None:
    """The bound, the shaping, and the refusals are the ones a current query would give."""
    over_bound = system.query_graph(
        GraphQuery(
            anchor_groups=(AnchorGroup(name="who", anchor_type="person"),),
            return_shape=ReturnShape(projections=(AnchorProjection(name="p", anchor_group="who"),)),
            maximum_rows=0,
        ),
        selection=RevisionSelection(2),
        provenance=_owner(),
    )

    assert over_bound.status is OperationStatus.REJECTED
    assert any("maximum rows must be positive" in f.summary for f in over_bound.findings)
    assert over_bound.evaluated_revision is None


# --- A time selector -----------------------------------------------------------------


def _recorded_at(system: RTGSystem, revision: int):
    from vellis.activity import HistoryKind, HistoryQuery

    entries = system.history(
        HistoryQuery(kind=HistoryKind.CANONICAL, maximum_records=100)
    ).canonical_entries
    return next(entry.recorded_at for entry in entries if entry.revision == revision)


def test_a_time_resolves_to_the_greatest_revision_at_or_before_it(system: RTGSystem) -> None:
    """Excludes requiring a time to name a moment something happened."""
    between = _recorded_at(system, 2) + timedelta(microseconds=1)

    result = system.definition_summary(selection=TimeSelection(between), provenance=_owner())

    assert result.accepted, result.findings
    assert result.evaluated_revision == 2


def test_a_time_exactly_at_a_commit_selects_that_revision(system: RTGSystem) -> None:
    at_two = _recorded_at(system, 2)

    result = system.definition_summary(selection=TimeSelection(at_two), provenance=_owner())

    assert result.accepted, result.findings
    assert result.evaluated_revision == 2


def test_a_time_before_anything_was_committed_resolves_to_nothing(system: RTGSystem) -> None:
    before = _recorded_at(system, 0) - timedelta(days=1)

    result = system.definition_summary(selection=TimeSelection(before), provenance=_owner())

    assert result.status is OperationStatus.REJECTED
    assert result.evaluated_revision is None
    assert result.anchor_types == ()
    assert any("nothing had been committed" in f.summary for f in result.findings)


def test_a_summarys_resolved_revision_can_be_reused_for_inspection_and_query(
    system: RTGSystem,
) -> None:
    """The arc the verification case names: resolve once by time, then ask by revision."""
    between = _recorded_at(system, 2) + timedelta(microseconds=1)
    summary = system.definition_summary(selection=TimeSelection(between), provenance=_owner())
    assert summary.accepted, summary.findings
    resolved = summary.evaluated_revision
    assert resolved is not None

    inspection = system.inspect_definitions(
        DefinitionInspectionRequest(anchor_type_keys=("ritual",)),
        selection=RevisionSelection(resolved),
        provenance=_owner(),
    )
    query = system.query_graph(
        _rituals(), selection=RevisionSelection(resolved), provenance=_owner()
    )

    assert inspection.accepted, inspection.findings
    assert inspection.evaluated_revision == resolved
    assert query.accepted, query.findings
    assert query.evaluated_revision == resolved
    assert [b.anchor.uuid for row in query.rows for b in row.anchors] == ["r-1"]


# --- Discovery of a vocabulary since retired ------------------------------------------


def test_a_cold_agent_discovers_definitions_later_retired(system: RTGSystem) -> None:
    """Excludes answering historical discovery from the current vocabulary."""
    then = system.definition_summary(selection=RevisionSelection(2), provenance=_owner())
    current = system.definition_summary(provenance=_owner())

    assert then.accepted and current.accepted
    assert {each.type_key for each in then.anchor_types} == {"person", "ritual"}
    assert {each.type_key for each in current.anchor_types} == {"person"}


def test_a_historical_summary_reports_delta_presence_at_that_state(
    system: RTGSystem,
) -> None:
    """A proposal stood at revision 4 and was activated at 5."""
    assert (
        system.definition_summary(selection=RevisionSelection(4), provenance=_owner()).delta_present
        is True
    )
    assert (
        system.definition_summary(selection=RevisionSelection(3), provenance=_owner()).delta_present
        is False
    )
    assert (
        system.definition_summary(selection=RevisionSelection(5), provenance=_owner()).delta_present
        is False
    )


def test_a_historical_inspection_returns_the_neighborhood_as_it_was(
    system: RTGSystem,
) -> None:
    result = system.inspect_definitions(
        DefinitionInspectionRequest(anchor_type_keys=("ritual",)),
        selection=RevisionSelection(0),
        provenance=_owner(),
    )

    assert result.accepted, result.findings
    assert result.evaluated_revision == 0
    assert [detail.anchor_type.type_key for detail in result.anchor_details] == ["ritual"]


def test_an_inspection_of_a_type_not_yet_retired_is_refused_against_current_state(
    system: RTGSystem,
) -> None:
    result = system.inspect_definitions(
        DefinitionInspectionRequest(anchor_type_keys=("ritual",)), provenance=_owner()
    )

    assert result.status is OperationStatus.REJECTED
    assert result.anchor_details == ()


# --- Unresolvable selections ----------------------------------------------------------


@pytest.mark.parametrize(
    ("selection", "expected"),
    (
        (RevisionSelection(99), "no record in this ledger established revision 99"),
        (RevisionSelection(-1), "names a committed revision"),
    ),
    ids=["unknown-revision", "negative-revision"],
)
def test_an_unresolved_selection_returns_no_content_and_no_evaluated_revision(
    system: RTGSystem, selection, expected: str
) -> None:
    before = system.current_state()

    summary = system.definition_summary(selection=selection, provenance=_owner())
    inspection = system.inspect_definitions(
        DefinitionInspectionRequest(anchor_type_keys=("person",)),
        selection=selection,
        provenance=_owner(),
    )
    query = system.query_graph(_people(), selection=selection, provenance=_owner())

    for result in (summary, inspection, query):
        assert result.status is OperationStatus.REJECTED
        assert result.evaluated_revision is None
        assert any(expected in f.summary for f in result.findings)
    assert summary.anchor_types == ()
    assert inspection.anchor_details == ()
    assert query.rows == ()
    assert canonical_state_equal(system.current_state(), before)


def test_a_time_selector_without_a_zone_is_refused(system: RTGSystem) -> None:
    from datetime import datetime

    result = system.definition_summary(
        selection=TimeSelection(datetime(2020, 1, 1)), provenance=_owner()
    )

    assert result.status is OperationStatus.REJECTED
    assert any("which zone it is in" in f.summary for f in result.findings)


def test_a_historical_read_changes_no_canonical_state(system: RTGSystem) -> None:
    before = system.current_state()
    records = system.store.canonical_record_count()

    assert system.query_graph(
        _people(), selection=RevisionSelection(1), provenance=_owner()
    ).accepted
    assert system.definition_summary(selection=RevisionSelection(1), provenance=_owner()).accepted

    assert canonical_state_equal(system.current_state(), before)
    assert system.store.canonical_record_count() == records


def test_delta_retrieval_stays_current_only(system: RTGSystem) -> None:
    """The model keeps whole-delta retrieval current-only; there is no selector for it."""
    import inspect as inspect_module

    parameters = inspect_module.signature(RTGSystem.definition_delta).parameters
    assert "selection" not in parameters


# --- Bounded selection work -----------------------------------------------------------


def _graph_history(system: RTGSystem, count: int, prefix: str) -> None:
    for index in range(count):
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor(f"{prefix}-{index}", "person", f"P{index}"),)),
            provenance=_owner(),
        ).accepted


def test_a_historical_summary_skips_the_graph_work_between_definition_changes(
    tmp_path: Path,
) -> None:
    """Excludes replaying the whole ledger to answer what the vocabulary was.

    The graph mutations sit *between* the two definition changes and below the selected
    revision, so a read that walked everything would grow with them. One that follows
    what changed the answer cannot.
    """

    def cost(mutations: int) -> tuple[int, int]:
        system = RTGSystem.open(tmp_path / f"v{mutations}.sqlite3")
        try:
            assert system.initialize_fresh(
                EARLY, provenance=_owner(), initialization_summary="a fresh start"
            ).accepted
            _graph_history(system, mutations, "m")
            assert system.set_definition_delta(LATER, provenance=_owner()).accepted
            assert system.activate_definition_delta(provenance=_owner()).accepted
            selected = system.current_state().revision

            system.store.reset_instrumentation()
            result = system.definition_summary(
                selection=RevisionSelection(selected), provenance=_owner()
            )
            assert result.accepted, result.findings
            assert {each.type_key for each in result.anchor_types} == {"person"}
            return system.store.record_reads, selected
        finally:
            system.close()

    lean, few = cost(2)
    same, many = cost(40)

    assert many > few
    assert same == lean


def test_definition_history_uses_the_definition_only_partial_index(system: RTGSystem) -> None:
    """A returned-row counter cannot expose graph rows filtered beneath the query."""
    from vellis.store import DEFINITION_TRANSITIONS_SQL

    plan = system.store._connection.execute(  # noqa: SLF001
        f"EXPLAIN QUERY PLAN {DEFINITION_TRANSITIONS_SQL}", (system.current_state().revision,)
    ).fetchall()
    detail = " ".join(str(row[-1]) for row in plan)

    assert "canonical_definition_transition" in detail


def test_resolving_a_time_selector_does_not_walk_the_ledger(tmp_path: Path) -> None:
    """``boundedHistoricalSelectionWork``: resolution is a seek, not a scan.

    The bound sits near the start of a long ledger, which is the case an aggregate over
    the revision key answers by walking everything committed after it.
    """
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        assert system.initialize_fresh(
            EARLY, provenance=_owner(), initialization_summary="a fresh start"
        ).accepted
        _graph_history(system, 3, "early")
        early = _recorded_at(system, 2)
        _graph_history(system, 200, "later")

        system.store.reset_instrumentation()
        result = system.definition_summary(selection=TimeSelection(early), provenance=_owner())

        assert result.accepted, result.findings
        assert result.evaluated_revision == 2
        # The resolution seek, the base record, and the definition-changing records.
        assert system.store.record_reads < 10
    finally:
        system.close()


def test_the_vocabulary_at_a_revision_is_the_one_in_force_then(system: RTGSystem) -> None:
    """Excludes a rebuild that returns the base vocabulary whatever the revision.

    Revision 4 stages the narrower proposal; revision 5 activates it. Only activation
    moves the active set.
    """
    before = system.definition_summary(selection=RevisionSelection(4), provenance=_owner())
    after = system.definition_summary(selection=RevisionSelection(5), provenance=_owner())

    assert {each.type_key for each in before.anchor_types} == {"person", "ritual"}
    assert {each.type_key for each in after.anchor_types} == {"person"}


def test_a_historical_inspection_is_bounded_the_same_way(system: RTGSystem) -> None:
    _graph_history(system, 30, "extra")

    system.store.reset_instrumentation()
    result = system.inspect_definitions(
        DefinitionInspectionRequest(anchor_type_keys=("ritual",)),
        selection=RevisionSelection(2),
        provenance=_owner(),
    )

    assert result.accepted, result.findings
    assert system.store.record_reads < 10


def test_a_time_bound_in_another_zone_resolves_to_the_same_revision(
    system: RTGSystem,
) -> None:
    from datetime import timezone

    here = _recorded_at(system, 2)
    elsewhere = here.astimezone(timezone(timedelta(hours=-7)))
    assert elsewhere.utcoffset() != here.utcoffset()

    assert (
        system.definition_summary(
            selection=TimeSelection(elsewhere), provenance=_owner()
        ).evaluated_revision
        == 2
    )


def test_a_historical_query_at_a_selected_time_means_what_a_revision_query_means(
    system: RTGSystem,
) -> None:
    """``semanticQuery``: current, a selected revision, and a selected time all agree."""
    at_two = _recorded_at(system, 2)

    by_time = system.query_graph(_rituals(), selection=TimeSelection(at_two), provenance=_owner())
    by_revision = system.query_graph(
        _rituals(), selection=RevisionSelection(2), provenance=_owner()
    )

    assert by_time.accepted and by_revision.accepted
    assert by_time.evaluated_revision == by_revision.evaluated_revision == 2
    assert [b.anchor.uuid for row in by_time.rows for b in row.anchors] == [
        b.anchor.uuid for row in by_revision.rows for b in row.anchors
    ]


def test_a_historical_inspection_returns_no_partial_details(system: RTGSystem) -> None:
    """One resolvable type and one retired by the selected revision; neither comes back."""
    result = system.inspect_definitions(
        DefinitionInspectionRequest(anchor_type_keys=("person", "ritual")),
        selection=RevisionSelection(5),
        provenance=_owner(),
    )

    assert result.status is OperationStatus.REJECTED
    assert result.anchor_details == ()
    assert result.evaluated_revision is None


def test_a_historical_read_is_observed_with_the_revision_it_reached(
    system: RTGSystem,
) -> None:
    from vellis.activity import HistoryKind, HistoryQuery

    assert system.definition_summary(selection=RevisionSelection(2), provenance=_owner()).accepted
    assert system.query_graph(
        _rituals(), selection=RevisionSelection(2), provenance=_owner()
    ).accepted

    entries = system.history(
        HistoryQuery(kind=HistoryKind.ACTIVITY, maximum_records=100)
    ).activity_entries
    recorded = {entry.capability: entry for entry in entries}
    assert recorded["definitionSummary"].evaluated_revision == 2
    assert recorded["query"].evaluated_revision == 2


def test_a_store_that_cannot_answer_a_historical_read_reports_a_failure(
    system: RTGSystem,
) -> None:
    """Excludes an exception crossing the boundary where a current read returns an outcome."""
    system.store._connection.execute("DROP TABLE graph_presence_interval")  # noqa: SLF001
    system.store._connection.commit()  # noqa: SLF001

    # Revision 5 can answer from normalized definition rows; revision 2 needs graph rows.
    summary = system.definition_summary(selection=RevisionSelection(5), provenance=_owner())
    query = system.query_graph(_rituals(), selection=RevisionSelection(2), provenance=_owner())

    assert summary.accepted
    assert query.status is OperationStatus.FAILED
    assert query.evaluated_revision is None
    assert query.findings


def test_delta_retrieval_answers_about_now_however_far_back_was_just_read(
    system: RTGSystem,
) -> None:
    """``historicalStateCorrectness``: whole-delta retrieval remains current-only.

    A proposal stood at revision 4 and none stands now, so a retrieval that had been
    influenced by the historical read would say otherwise.
    """
    assert (
        system.definition_summary(selection=RevisionSelection(4), provenance=_owner()).delta_present
        is True
    )

    assert system.definition_delta(provenance=_owner()).definition_delta is None
