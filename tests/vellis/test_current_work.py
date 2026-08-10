"""Evidence that current work does not traverse canonical history.

Supports ``VellisVerification::currentWorkScaling`` for the operations this slice
establishes. The measure is instrumented semantic record accesses, not wall-clock time,
as the verification case requires.

The whole-system characterization over long histories belongs to the closure slice that
owns it; what this slice must show is that the current projection is reached without
reading canonical records at all, and that the counter would notice if it were.
"""

from __future__ import annotations

from pathlib import Path

from vellis.canonical import Provenance, canonical_state_equal
from vellis.definitions import AnchorTypeDefinition, GraphDefinitionSet
from vellis.system import RTGSystem
from vellis.validation import assess_graph_conformance

VOCABULARY = GraphDefinitionSet(
    anchor_types=(AnchorTypeDefinition(type_key="person", description="A person."),)
)


def _established(tmp_path: Path) -> RTGSystem:
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    system.initialize_fresh(
        VOCABULARY,
        provenance=Provenance(initiator="owner"),
        initialization_summary="a fresh start",
    )
    system.store.reset_instrumentation()
    return system


def test_reading_current_state_visits_no_canonical_record(tmp_path: Path) -> None:
    system = _established(tmp_path)
    try:
        system.current_state()
        assert system.store.record_reads == 0
    finally:
        system.close()


def test_current_conformance_assessment_visits_no_canonical_record(tmp_path: Path) -> None:
    system = _established(tmp_path)
    try:
        state = system.current_state()
        assert assess_graph_conformance(state.graph, state.active_definitions) == ()
        assert system.store.record_reads == 0
    finally:
        system.close()


def test_asking_whether_state_exists_visits_no_canonical_record(tmp_path: Path) -> None:
    system = _established(tmp_path)
    try:
        assert system.is_initialized
        assert system.store.record_reads == 0
    finally:
        system.close()


def test_repeating_current_work_does_not_accumulate_record_reads(tmp_path: Path) -> None:
    system = _established(tmp_path)
    try:
        for _ in range(25):
            state = system.current_state()
            assess_graph_conformance(state.graph, state.active_definitions)
        assert system.store.record_reads == 0
    finally:
        system.close()


def test_the_instrumentation_counts_a_real_record_access(tmp_path: Path) -> None:
    """Without this the zero-access assertions above would pass vacuously."""
    system = _established(tmp_path)
    try:
        system.replay()
        assert system.store.record_reads == 1
        system.initial_record()
        assert system.store.record_reads == 2
        system.store.reset_instrumentation()
        assert system.store.record_reads == 0
    finally:
        system.close()


def test_the_projection_is_the_replayed_state_not_a_second_authority(tmp_path: Path) -> None:
    system = _established(tmp_path)
    try:
        assert canonical_state_equal(system.current_state(), system.replay())
    finally:
        system.close()


def test_current_work_issues_no_statement_against_the_ledger(tmp_path: Path) -> None:
    """Excludes an implementation that reaches the ledger without going through the counter.

    The counter is incremented by hand, so on its own it cannot prove that current work
    left the ledger alone. Tracing the statements actually issued can.
    """
    system = _established(tmp_path)
    statements: list[str] = []
    # Reaching the connection directly is the point: this observes what was really run.
    system.store._connection.set_trace_callback(statements.append)  # noqa: SLF001
    try:
        state = system.current_state()
        assess_graph_conformance(state.graph, state.active_definitions)
        assert system.is_initialized
        assert not any("canonical_record" in statement for statement in statements)
        assert statements

        statements.clear()
        system.replay()
        assert any("canonical_record" in statement for statement in statements)
    finally:
        system.store._connection.set_trace_callback(None)  # noqa: SLF001
        system.close()
