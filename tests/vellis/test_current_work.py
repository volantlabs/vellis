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

import pytest

from tests.vellis.oracle import materialize_replay, materialize_state
from tests.vellis.semantic_state import semantic_state_equal
from vellis.canonical import Provenance
from vellis.changes import GraphChange
from vellis.definitions import AnchorTypeDefinition, GraphDefinitionSet
from vellis.discovery import DefinitionInspectionRequest
from vellis.governance import DefinitionChange
from vellis.graph import Anchor
from vellis.history import RevisionSelection
from vellis.outcomes import OperationStatus
from vellis.query import (
    AnchorGroup,
    AnchorProjection,
    AnchorUuidFilter,
    EvaluatedStateScope,
    GraphQuery,
    ReturnShape,
)
from vellis.system import RTGSystem
from vellis.validation import assess_object_neighborhood

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


def test_current_conformance_assessment_visits_no_canonical_record(tmp_path: Path) -> None:
    system = _established(tmp_path)
    try:
        state = materialize_state(system)
        assert assess_object_neighborhood(state.graph.objects(), state.active_definitions) == ()
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


def test_definition_work_reads_only_the_durable_definition_facet(
    tmp_path: Path,
) -> None:
    path = tmp_path / "vellis.sqlite3"
    system = _established(tmp_path)
    system.close()

    reopened = RTGSystem.open(path)
    try:
        assert reopened.store.current_projection_decodes == 0
        reopened.store.reset_instrumentation()

        for _ in range(25):
            assert reopened.definition_summary().accepted
            assert reopened.inspect_definitions(
                DefinitionInspectionRequest(anchor_type_keys=("person",))
            ).accepted

        assert reopened.store.current_projection_decodes == 0
        assert reopened.store.current_graph_decodes == 0
        assert reopened.store.current_definition_decodes == 25
        assert reopened.store.record_reads == 0
    finally:
        reopened.close()


def test_absent_proposal_retrieval_decodes_no_graph_objects(tmp_path: Path) -> None:
    system = _established(tmp_path)
    try:
        anchors = tuple(Anchor(f"a-{index}", "person", f"Person {index}") for index in range(500))
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=anchors), provenance=Provenance(initiator="owner")
        ).accepted
        system.store.reset_instrumentation()

        result = system.definition_delta()

        assert result.accepted and result.proposed_definition_identity is None
        assert system.store.current_projection_decodes == 0
        assert system.store.current_graph_decodes == 0
        assert system.store.current_graph_object_decodes == 0
        assert system.store.current_definition_decodes == 0
    finally:
        system.close()


def test_definition_only_no_op_and_refusal_decode_no_graph_objects(tmp_path: Path) -> None:
    system = _established(tmp_path)
    wider = DefinitionChange(
        anchor_type_upserts=(
            AnchorTypeDefinition(type_key="person", description="A described person."),
        )
    )
    try:
        anchors = tuple(Anchor(f"a-{index}", "person", f"Person {index}") for index in range(500))
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=anchors), provenance=Provenance(initiator="owner")
        ).accepted
        system.store.reset_instrumentation()

        unchanged = system.set_definition_delta(
            DefinitionChange(), provenance=Provenance(initiator="owner")
        )

        assert unchanged.accepted and unchanged.resulting_revision is None
        assert system.store.current_graph_object_decodes == 0

        assert system.set_definition_delta(wider, provenance=Provenance(initiator="owner")).accepted
        system.store.reset_instrumentation()

        refused = system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=VOCABULARY.anchor_types),
            provenance=Provenance(initiator="owner"),
        )

        assert refused.status is OperationStatus.REJECTED
        assert system.store.current_graph_object_decodes == 0
    finally:
        system.close()


def test_definition_delta_discard_decodes_no_graph_objects(tmp_path: Path) -> None:
    system = _established(tmp_path)
    wider = DefinitionChange(
        anchor_type_upserts=(
            AnchorTypeDefinition(type_key="person", description="A described person."),
        )
    )
    try:
        anchors = tuple(Anchor(f"a-{index}", "person", f"Person {index}") for index in range(500))
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=anchors), provenance=Provenance(initiator="owner")
        ).accepted
        assert system.set_definition_delta(wider, provenance=Provenance(initiator="owner")).accepted
        system.store.reset_instrumentation()

        discarded = system.discard_definition_delta(provenance=Provenance(initiator="owner"))

        assert discarded.accepted
        assert system.store.current_graph_object_decodes == 0
        assert materialize_state(system).definition_delta is None
    finally:
        system.close()


def test_an_external_commit_is_visible_without_a_resident_projection(tmp_path: Path) -> None:
    path = tmp_path / "vellis.sqlite3"
    first = _established(tmp_path)
    second = RTGSystem.open(path)
    try:
        first.store.reset_instrumentation()
        assert second.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-1", "person", "Ada"),)),
            provenance=Provenance(initiator="owner"),
        ).accepted

        assert first.store.current_revision() == 1
        assert first.store.current_projection_decodes == 0
    finally:
        second.close()
        first.close()


def test_complete_state_assembly_uses_one_cross_process_read_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "vellis.sqlite3"
    reader = _established(tmp_path)
    writer = RTGSystem.open(path)
    committed = False

    def commit_between_projection_statements(statement: str) -> None:
        nonlocal committed
        if committed or "FROM current_graph_object" not in statement:
            return
        committed = True
        assert writer.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-1", "person", "Ada"),)),
            provenance=Provenance(initiator="other process"),
        ).accepted

    reader.store._connection.set_trace_callback(  # noqa: SLF001
        commit_between_projection_statements
    )
    try:
        state = materialize_state(reader)

        assert committed
        assert state.revision == 0
        assert state.graph.anchors == ()
        assert materialize_state(writer).revision == 1
    finally:
        reader.store._connection.set_trace_callback(None)  # noqa: SLF001
        writer.close()
        reader.close()


def test_the_projection_is_the_replayed_state_not_a_second_authority(tmp_path: Path) -> None:
    system = _established(tmp_path)
    try:
        assert semantic_state_equal(materialize_state(system), materialize_replay(system))
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
        state = materialize_state(system)
        assess_object_neighborhood(state.graph.objects(), state.active_definitions)
        assert system.is_initialized
        assert not any("canonical_record" in statement for statement in statements)
        assert statements

        statements.clear()
        materialize_replay(system)
        assert any("canonical_record" in statement for statement in statements)
    finally:
        system.store._connection.set_trace_callback(None)  # noqa: SLF001
        system.close()


@pytest.mark.parametrize("unrelated_population", (250, 1_000, 4_000))
def test_one_object_mutation_decodes_only_its_affected_neighborhood(
    tmp_path: Path, unrelated_population: int
) -> None:
    """A fixed mutation is independent of unrelated current graph population."""
    system = _established(tmp_path)
    try:
        anchors = tuple(
            Anchor(f"a-{index}", "person", f"Person {index}")
            for index in range(unrelated_population)
        )
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=anchors), provenance=Provenance(initiator="owner")
        ).accepted
        system.store.reset_instrumentation()

        outcome = system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-0", "person", "Renamed"),)),
            provenance=Provenance(initiator="owner"),
        )

        assert outcome.accepted
        assert system.store.current_graph_decodes == 0
        assert system.store.current_graph_object_decodes == 1
        assert system.store.record_reads == 0
    finally:
        system.close()


def test_broad_query_hydrates_only_the_bounded_answer(tmp_path: Path) -> None:
    system = _established(tmp_path)
    try:
        anchors = tuple(Anchor(f"a-{index}", "person", f"Person {index}") for index in range(500))
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=anchors), provenance=Provenance(initiator="owner")
        ).accepted
        system.store.reset_instrumentation()

        result = system.query_graph(
            GraphQuery(
                anchor_groups=(AnchorGroup("person", "person"),),
                return_shape=ReturnShape((AnchorProjection("person", "person"),)),
                maximum_rows=10,
            )
        )

        assert result.status is OperationStatus.REJECTED
        assert result.rows == ()
        assert system.store.current_graph_decodes == 0
        assert system.store.current_graph_object_decodes == 0
    finally:
        system.close()


def test_schema_four_has_no_whole_state_definition_object_or_change_payloads(
    tmp_path: Path,
) -> None:
    system = _established(tmp_path)
    try:
        connection = system.store._connection  # noqa: SLF001
        assert connection.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone() == ("4",)
        forbidden = {"payload", "state", "graph", "definitions", "canonical_change"}
        for table in (
            "canonical_record",
            "canonical_graph_event",
            "canonical_definition_event",
            "state_head",
            "object_value",
            "definition_set",
        ):
            columns = {
                str(row[1]).lower() for row in connection.execute(f"PRAGMA table_info({table})")
            }
            assert columns.isdisjoint(forbidden), (table, columns & forbidden)
    finally:
        system.close()


def test_definition_discovery_decodes_only_the_requested_neighborhood(
    tmp_path: Path,
) -> None:
    definitions = GraphDefinitionSet(
        anchor_types=tuple(
            AnchorTypeDefinition(f"type-{index}", f"Type {index}.") for index in range(1_000)
        )
    )
    system = RTGSystem.open(tmp_path / "definitions.sqlite3")
    try:
        assert system.initialize_fresh(
            definitions, provenance=Provenance("owner"), initialization_summary="large"
        ).accepted
        system.store.reset_instrumentation()
        summary = system.definition_summary()
        assert summary.accepted and len(summary.anchor_types) == 1_000
        assert system.store.current_definition_decodes == 0

        inspection = system.inspect_definitions(DefinitionInspectionRequest(("type-0",)))
        assert inspection.accepted and len(inspection.anchor_details) == 1
        assert system.store.current_definition_decodes == 1
    finally:
        system.close()


@pytest.mark.parametrize("population", (10, 1_000, 4_000))
def test_narrow_historical_query_does_not_materialize_the_revision_population(
    tmp_path: Path, population: int
) -> None:
    system = _established(tmp_path)
    try:
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=tuple(
                    Anchor(f"a-{index}", "person", f"Person {index}") for index in range(population)
                )
            ),
            provenance=Provenance(initiator="owner"),
        ).accepted
        query = GraphQuery(
            anchor_groups=(AnchorGroup("person", "person", AnchorUuidFilter(("a-0",))),),
            return_shape=ReturnShape((AnchorProjection("returned-person", "person"),)),
            maximum_rows=1,
            historical_selection=RevisionSelection(1),
            state_scope=EvaluatedStateScope.HISTORICAL,
        )
        steps = 0

        def progress() -> int:
            nonlocal steps
            steps += 1
            return 0

        system.store._connection.set_progress_handler(progress, 1)  # noqa: SLF001
        try:
            result = system.query_graph(query)
        finally:
            system.store._connection.set_progress_handler(None, 0)  # noqa: SLF001

        assert result.accepted and len(result.rows) == 1
        assert steps < 2_000
    finally:
        system.close()
