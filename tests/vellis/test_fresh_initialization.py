"""Evidence for ``VellisVerification::freshInitialization`` and the owned history base.

Also carries the part of ``VellisVerification::durableHistory`` this slice reaches:
one initial record, no transitions, and identical canonical memory after an ordinary
restart.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vellis.canonical import Provenance, canonical_state_equal
from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    GraphDefinitionSet,
    definition_set_equal,
)
from vellis.outcomes import OperationStatus
from vellis.store import CanonicalStore
from vellis.system import RTGSystem
from vellis.validation import assess_graph_conformance

VOCABULARY = GraphDefinitionSet(
    anchor_types=(AnchorTypeDefinition(type_key="person", description="A person."),),
    associated_data_types=(
        AssociatedDataTypeDefinition(
            type_key="note", permitted_anchor_type_keys=("person",), description="A note."
        ),
    ),
)

INVALID = GraphDefinitionSet(
    anchor_types=(AnchorTypeDefinition(type_key="person"),),
)


def _open(tmp_path: Path) -> RTGSystem:
    return RTGSystem.open(tmp_path / "vellis.sqlite3")


def _initialize(system: RTGSystem, definitions: GraphDefinitionSet = VOCABULARY):
    return system.initialize_fresh(
        definitions,
        provenance=Provenance(initiator="owner", source="test"),
        initialization_summary="a fresh start",
    )


@pytest.mark.parametrize("definitions", [GraphDefinitionSet(), VOCABULARY])
def test_a_fresh_rtg_begins_at_revision_zero(
    tmp_path: Path, definitions: GraphDefinitionSet
) -> None:
    system = _open(tmp_path)
    try:
        outcome = _initialize(system, definitions)
        assert outcome.status is OperationStatus.ACCEPTED
        assert outcome.resulting_revision == 0

        state = system.current_state()
        assert state.revision == 0
        assert state.graph.is_empty
        assert state.definition_delta is None
        assert definition_set_equal(state.active_definitions, definitions)
        assert system.store.canonical_record_count() == 1
        assert system.store.activity_record_count() == 0
    finally:
        system.close()


def test_direct_state_the_initial_record_and_replay_all_agree(tmp_path: Path) -> None:
    """Excludes letting the current projection drift from the record that establishes it."""
    system = _open(tmp_path)
    try:
        _initialize(system)
        record = system.initial_record()
        assert record.established_revision == 0
        assert canonical_state_equal(system.current_state(), record.canonical_state)
        assert canonical_state_equal(system.current_state(), system.replay())
        assert record.provenance == Provenance(initiator="owner", source="test")
        assert record.initialization_summary == "a fresh start"
    finally:
        system.close()


def test_an_invalid_initial_definition_set_establishes_no_partial_state(tmp_path: Path) -> None:
    system = _open(tmp_path)
    try:
        outcome = _initialize(system, INVALID)
        assert outcome.status is OperationStatus.REJECTED
        assert outcome.resulting_revision is None
        assert outcome.findings
        assert not system.is_initialized
        assert system.store.canonical_record_count() == 0
        assert system.store.activity_record_count() == 0
    finally:
        system.close()


def test_initializing_an_established_rtg_is_refused_without_effect(tmp_path: Path) -> None:
    """Excludes an initialize that silently re-seeds or overwrites established memory."""
    system = _open(tmp_path)
    try:
        _initialize(system)
        before = system.current_state()
        outcome = _initialize(system, GraphDefinitionSet())
        assert outcome.status is OperationStatus.REJECTED
        assert outcome.resulting_revision is None
        assert canonical_state_equal(system.current_state(), before)
        assert system.store.canonical_record_count() == 1
    finally:
        system.close()


def test_refusal_after_establishment_leaves_the_record_untouched(tmp_path: Path) -> None:
    system = _open(tmp_path)
    try:
        _initialize(system)
        record_before = system.initial_record()
        _initialize(system, VOCABULARY)
        assert canonical_state_equal(
            system.initial_record().canonical_state, record_before.canonical_state
        )
    finally:
        system.close()


def test_canonical_memory_survives_an_ordinary_restart(tmp_path: Path) -> None:
    """Excludes holding canonical state only in process memory."""
    path = tmp_path / "vellis.sqlite3"
    first = RTGSystem.open(path)
    try:
        _initialize(first)
        before = first.current_state()
    finally:
        first.close()

    second = RTGSystem.open(path)
    try:
        assert second.is_initialized
        assert canonical_state_equal(second.current_state(), before)
        assert canonical_state_equal(second.replay(), before)
        assert second.store.canonical_record_count() == 1
    finally:
        second.close()


def test_an_uninitialized_store_reports_no_state(tmp_path: Path) -> None:
    store = CanonicalStore(tmp_path / "vellis.sqlite3")
    try:
        assert not store.is_initialized()
        assert store.canonical_record_count() == 0
    finally:
        store.close()


def test_a_fresh_system_conforms_to_its_own_active_definitions(tmp_path: Path) -> None:
    system = _open(tmp_path)
    try:
        _initialize(system)
        state = system.current_state()
        assert assess_graph_conformance(state.graph, state.active_definitions) == ()
        assert state.revision == 0
        assert canonical_state_equal(state, system.replay())
    finally:
        system.close()


def test_unstorable_record_text_is_refused_without_effect(tmp_path: Path) -> None:
    """Excludes letting the record's own text fail at the write instead of at the gate."""
    system = _open(tmp_path)
    try:
        outcome = system.initialize_fresh(
            GraphDefinitionSet(),
            provenance=Provenance(initiator="owner"),
            initialization_summary="a " + chr(0xD800),
        )
        assert outcome.status is OperationStatus.REJECTED
        assert any("unpaired surrogate" in finding.summary for finding in outcome.findings)
        assert not system.is_initialized
        assert system.store.canonical_record_count() == 0
    finally:
        system.close()


def test_a_bound_too_large_to_store_is_refused_before_it_is_written(tmp_path: Path) -> None:
    """Excludes accepting state the decoder would later refuse, which would brick the store."""
    from vellis.definitions import (
        AssociatedDataTypeDefinition as DataType,
    )
    from vellis.definitions import (
        PropertyConstraint,
        ValueShape,
    )
    from vellis.json_value import JsonKind

    oversized = GraphDefinitionSet(
        anchor_types=(AnchorTypeDefinition(type_key="person", description="A person."),),
        associated_data_types=(
            DataType(
                type_key="note",
                permitted_anchor_type_keys=("person",),
                property_constraints=(
                    PropertyConstraint(
                        property_name="title",
                        required=False,
                        json_kind=JsonKind.STRING,
                        description="A title.",
                        value_shape=ValueShape(maximum_size=10**40),
                    ),
                ),
                description="A note.",
            ),
        ),
    )
    system = _open(tmp_path)
    try:
        outcome = system.initialize_fresh(
            oversized,
            provenance=Provenance(initiator="owner"),
            initialization_summary="a fresh start",
        )
        assert outcome.status is OperationStatus.REJECTED
        assert any("too large to be stored" in finding.summary for finding in outcome.findings)
        assert not system.is_initialized
    finally:
        system.close()


def test_the_recorded_time_is_an_aware_utc_instant(tmp_path: Path) -> None:
    """Excludes a naive local timestamp, which no later reader could place in time.

    ``RTG::'Recorded Time'`` is a chronological instant, and the historical selection a
    later slice resolves against it cannot be correct if the clock is ambiguous.
    """
    from datetime import UTC

    system = _open(tmp_path)
    try:
        _initialize(system)
        recorded = system.initial_record().recorded_at
        assert recorded.tzinfo is not None
        assert recorded.utcoffset() == UTC.utcoffset(None)
    finally:
        system.close()

    # And it survives the round trip through storage as the same instant.
    reopened = RTGSystem.open(tmp_path / "vellis.sqlite3")
    try:
        assert reopened.initial_record().recorded_at.tzinfo is not None
    finally:
        reopened.close()


@pytest.mark.parametrize("depth", [93, 96, 99])
def test_a_state_that_could_not_be_read_back_is_never_established(
    tmp_path: Path, depth: int
) -> None:
    """Excludes committing state the store can encode but never decode.

    A limit applied to one value as it enters is not the same limit applied to the whole
    document that later contains it. These depths sit in exactly that gap: each is
    accepted as a value and would, without the round-trip check, commit a system that
    reports itself initialized and then fails every read forever.
    """
    from vellis.definitions import (
        AssociatedDataTypeDefinition,
        PropertyConstraint,
        ValueRange,
    )
    from vellis.json_value import JsonKind

    nested: object = {"leaf": 1}
    for _ in range(depth):
        nested = {"a": nested}

    definitions = GraphDefinitionSet(
        anchor_types=(AnchorTypeDefinition(type_key="person", description="A person."),),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="note",
                permitted_anchor_type_keys=("person",),
                property_constraints=(
                    PropertyConstraint(
                        property_name="payload",
                        required=False,
                        json_kind=JsonKind.OBJECT,
                        description="A nested payload.",
                        value_range=ValueRange(permitted_values=(nested,)),  # pyright: ignore[reportArgumentType]
                    ),
                ),
                description="A note.",
            ),
        ),
    )

    system = _open(tmp_path)
    try:
        outcome = system.initialize_fresh(
            definitions,
            provenance=Provenance(initiator="owner"),
            initialization_summary="a fresh start",
        )
        assert outcome.status is OperationStatus.REJECTED
        assert outcome.findings
        assert not system.is_initialized
        assert system.store.canonical_record_count() == 0
    finally:
        system.close()


def test_a_state_just_inside_the_limit_is_established_and_reads_back(tmp_path: Path) -> None:
    """The counterpart: what the gate accepts must actually survive a restart."""
    from vellis.definitions import (
        AssociatedDataTypeDefinition,
        PropertyConstraint,
        ValueRange,
    )
    from vellis.json_value import JsonKind

    nested: object = {"leaf": 1}
    for _ in range(80):
        nested = {"a": nested}

    definitions = GraphDefinitionSet(
        anchor_types=(AnchorTypeDefinition(type_key="person", description="A person."),),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="note",
                permitted_anchor_type_keys=("person",),
                property_constraints=(
                    PropertyConstraint(
                        property_name="payload",
                        required=False,
                        json_kind=JsonKind.OBJECT,
                        description="A nested payload.",
                        value_range=ValueRange(permitted_values=(nested,)),  # pyright: ignore[reportArgumentType]
                    ),
                ),
                description="A note.",
            ),
        ),
    )

    path = tmp_path / "vellis.sqlite3"
    system = RTGSystem.open(path)
    try:
        outcome = system.initialize_fresh(
            definitions,
            provenance=Provenance(initiator="owner"),
            initialization_summary="a fresh start",
        )
        assert outcome.status is OperationStatus.ACCEPTED
    finally:
        system.close()

    reopened = RTGSystem.open(path)
    try:
        assert definition_set_equal(reopened.current_state().active_definitions, definitions)
        assert canonical_state_equal(reopened.current_state(), reopened.replay())
    finally:
        reopened.close()


def test_unstorable_provenance_source_is_refused_like_the_other_record_text(
    tmp_path: Path,
) -> None:
    """Every record text field is screened, not the ones that happened to get a test."""
    system = _open(tmp_path)
    try:
        outcome = system.initialize_fresh(
            GraphDefinitionSet(),
            provenance=Provenance(initiator="owner", source="import " + chr(0xD800)),
            initialization_summary="a fresh start",
        )
        assert outcome.status is OperationStatus.REJECTED
        assert any("provenance source" in finding.summary for finding in outcome.findings)
        assert not system.is_initialized
    finally:
        system.close()


def test_the_recorded_time_stored_is_the_time_the_record_carries(tmp_path: Path) -> None:
    """Excludes writing a clock reading unrelated to the record being stored."""
    from datetime import UTC, datetime

    from vellis.canonical import CanonicalState, InitialStateRecord
    from vellis.graph import Graph
    from vellis.store import CanonicalStore

    stamped = datetime(2026, 8, 9, 12, 30, 45, tzinfo=UTC)
    store = CanonicalStore(tmp_path / "vellis.sqlite3")
    try:
        store.initialize(
            InitialStateRecord(
                canonical_state=CanonicalState(
                    graph=Graph(), active_definitions=VOCABULARY, revision=0
                ),
                initialization_summary="a fresh start",
                provenance=Provenance(initiator="owner"),
                recorded_at=stamped,
            )
        )
        assert store.initial_record().recorded_at == stamped
    finally:
        store.close()
