"""Evidence that the durable store detects disagreement instead of reporting it as truth.

The current projection and the canonical record that establishes it are stored
separately. The model permits the projection as a realization but forbids it from
becoming parallel authority, so the store must notice when the two stop agreeing rather
than quietly serving whichever one was asked for.

Supports ``VellisVerification::durableHistory`` and the atomicity obligation in
``VellisVerification::atomicTransitions`` as far as the owned base reaches.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from conftest import build_rich_definitions

from vellis.canonical import Provenance
from vellis.changes import GraphChange
from vellis.definitions import GraphDefinitionSet
from vellis.graph import Anchor
from vellis.outcomes import OperationStatus
from vellis.store import APPLICATION_ID, CanonicalStore, NotADatabaseError, StoreError
from vellis.system import RTGSystem


def _established(path: Path, definitions: GraphDefinitionSet | None = None) -> None:
    system = RTGSystem.open(path)
    try:
        outcome = system.initialize_fresh(
            build_rich_definitions() if definitions is None else definitions,
            provenance=Provenance(initiator="owner"),
            initialization_summary="a fresh start",
        )
        assert outcome.accepted
    finally:
        system.close()


def test_the_journal_mode_and_application_marker_are_set(tmp_path: Path) -> None:
    """Excludes claiming ordinary-restart durability while running without a write-ahead log."""
    path = tmp_path / "vellis.sqlite3"
    store = CanonicalStore(path)
    try:
        connection = sqlite3.connect(path)
        try:
            assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        finally:
            connection.close()
        assert store.is_initialized() is False
    finally:
        store.close()

    inspect = sqlite3.connect(path)
    try:
        assert int(inspect.execute("PRAGMA application_id").fetchone()[0]) == APPLICATION_ID
    finally:
        inspect.close()


def test_a_projection_whose_row_contradicts_its_payload_is_refused(tmp_path: Path) -> None:
    """Excludes serving a mixed tuple whose revision and content came from different writes.

    Content divergence introduced by editing the file directly is out of scope: detecting
    it would mean decoding a canonical record on every current read, which the
    history-independence requirement forbids.
    """
    path = tmp_path / "vellis.sqlite3"
    _established(path)

    connection = sqlite3.connect(path)
    try:
        connection.execute("UPDATE current_state SET revision = 99 WHERE id = 0")
        connection.commit()
    finally:
        connection.close()

    store = CanonicalStore(path)
    try:
        with pytest.raises(StoreError, match="claims revision"):
            store.current_state()
    finally:
        store.close()


def test_a_record_whose_payload_contradicts_its_revision_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "vellis.sqlite3"
    _established(path)

    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE canonical_record SET payload = replace(payload, '\"revision\":0',"
            " '\"revision\":42') WHERE ordinal = 0"
        )
        connection.commit()
    finally:
        connection.close()

    store = CanonicalStore(path)
    try:
        with pytest.raises(StoreError, match="but carries revision"):
            store.initial_record()
    finally:
        store.close()


def test_unreadable_stored_text_is_refused_rather_than_reinterpreted(tmp_path: Path) -> None:
    path = tmp_path / "vellis.sqlite3"
    _established(path)

    connection = sqlite3.connect(path)
    try:
        connection.execute("UPDATE current_state SET active_definitions = 'not json' WHERE id = 0")
        connection.commit()
    finally:
        connection.close()

    store = CanonicalStore(path)
    try:
        with pytest.raises(StoreError, match="do not decode"):
            store.current_state()
    finally:
        store.close()


def test_indexed_selectors_that_disagree_with_payload_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "vellis.sqlite3"
    system = RTGSystem.open(path)
    try:
        assert system.initialize_fresh(
            build_rich_definitions(),
            provenance=Provenance(initiator="owner"),
            initialization_summary="a fresh start",
        ).accepted
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-1", "person", "Ada"),)),
            provenance=Provenance(initiator="owner"),
        ).accepted
    finally:
        system.close()

    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE current_graph_object SET type_key = 'project' WHERE uuid = 'a-1'"
        )
        connection.commit()
    finally:
        connection.close()

    store = CanonicalStore(path)
    try:
        with pytest.raises(StoreError, match="selectors that disagree"):
            store.current_state()
    finally:
        store.close()


def test_an_unrelated_database_is_refused_not_adopted(tmp_path: Path) -> None:
    """Excludes creating Vellis tables inside somebody else's database."""
    path = tmp_path / "other.sqlite3"
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO schema_meta VALUES ('schema_version', '1')")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(StoreError, match="not a Vellis canonical store"):
        CanonicalStore(path)


def test_a_file_that_is_not_a_database_reports_a_store_error(tmp_path: Path) -> None:
    path = tmp_path / "vellis.sqlite3"
    path.write_text("this is not a database\n", encoding="utf-8")

    with pytest.raises(NotADatabaseError, match="is not a database"):
        CanonicalStore(path)


def test_a_store_missing_its_tables_reports_a_store_error(tmp_path: Path) -> None:
    path = tmp_path / "vellis.sqlite3"
    _established(path)

    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP TABLE current_state")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(StoreError, match="missing its current_state table"):
        CanonicalStore(path)


def test_a_rich_vocabulary_survives_an_ordinary_restart(tmp_path: Path) -> None:
    """Excludes a durability claim proven only with a vocabulary that has no rules."""
    from vellis.canonical import canonical_state_equal
    from vellis.definitions import definition_set_equal

    path = tmp_path / "vellis.sqlite3"
    definitions = build_rich_definitions()
    _established(path, definitions)

    system = RTGSystem.open(path)
    try:
        state = system.current_state()
        assert definition_set_equal(state.active_definitions, definitions)
        assert canonical_state_equal(state, system.replay())
        restored = state.active_definitions.associated_data_type("note")
        assert restored is not None
        year = next(each for each in restored.property_constraints if each.property_name == "year")
        assert year.pattern is not None and year.pattern.expression == "[0-9]{4}"
    finally:
        system.close()


def test_synchronous_durability_is_actually_enabled(tmp_path: Path) -> None:
    """Excludes proving restart durability while running with synchronous writes off."""
    store = CanonicalStore(tmp_path / "vellis.sqlite3")
    try:
        # FULL is 2; anything lower does not survive an operating-system crash.
        assert int(store._connection.execute("PRAGMA synchronous").fetchone()[0]) == 2  # noqa: SLF001
    finally:
        store.close()


def test_a_database_holding_other_objects_is_refused(tmp_path: Path) -> None:
    """Excludes creating the Vellis schema inside an unrelated database."""
    path = tmp_path / "payroll.sqlite3"
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE payroll (name TEXT)")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(StoreError, match="already holds other objects"):
        CanonicalStore(path)

    inspect = sqlite3.connect(path)
    try:
        remaining = {
            row[0]
            for row in inspect.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert remaining == {"payroll"}
    finally:
        inspect.close()


def test_a_database_marked_by_another_application_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "other.sqlite3"
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA application_id = 305419896")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(StoreError, match="belongs to another application"):
        CanonicalStore(path)


def test_refusing_a_foreign_database_leaves_it_byte_identical(tmp_path: Path) -> None:
    """Excludes a refusal that has already rewritten the header or dropped sidecar files."""
    path = tmp_path / "payroll.sqlite3"
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE payroll (name TEXT)")
        connection.execute("INSERT INTO payroll VALUES ('Ada')")
        connection.commit()
    finally:
        connection.close()

    before = path.read_bytes()
    siblings_before = sorted(each.name for each in tmp_path.iterdir())

    with pytest.raises(StoreError, match="already holds other objects"):
        CanonicalStore(path)

    assert path.read_bytes() == before
    assert sorted(each.name for each in tmp_path.iterdir()) == siblings_before


def test_a_database_holding_only_a_view_is_also_refused(tmp_path: Path) -> None:
    """Excludes screening for tables alone; a view is somebody else's database too."""
    path = tmp_path / "reports.sqlite3"
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE VIEW summary AS SELECT 1")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(StoreError, match="already holds other objects"):
        CanonicalStore(path)
    assert sorted(each.name for each in tmp_path.iterdir()) == ["reports.sqlite3"]


def test_a_failure_between_the_record_and_the_projection_establishes_nothing(
    tmp_path: Path,
) -> None:
    """Excludes committing the record and the projection as two separate effects.

    A trigger makes the projection insert fail after the record insert has run. If the
    two were separate commits, the record would survive; and if the failure left the
    transaction open, the store would be unusable afterwards.
    """
    from vellis.canonical import CanonicalState, InitialStateRecord, Provenance
    from vellis.graph import Graph

    path = tmp_path / "vellis.sqlite3"
    store = CanonicalStore(path)
    record = InitialStateRecord(
        canonical_state=CanonicalState(
            graph=Graph(), active_definitions=build_rich_definitions(), revision=0
        ),
        initialization_summary="a fresh start",
        provenance=Provenance(initiator="owner"),
    )
    try:
        blocker = sqlite3.connect(path)
        try:
            blocker.execute(
                "CREATE TRIGGER refuse_projection BEFORE INSERT ON current_state "
                "BEGIN SELECT RAISE(ABORT, 'disk went away'); END"
            )
            blocker.commit()
        finally:
            blocker.close()

        with pytest.raises(StoreError, match="could not establish canonical state"):
            store.initialize(record)
        assert not store.is_initialized()
        assert store.canonical_record_count() == 0

        remover = sqlite3.connect(path)
        try:
            remover.execute("DROP TRIGGER refuse_projection")
            remover.commit()
        finally:
            remover.close()

        # An open transaction left behind by the failure would refuse this.
        store.initialize(record)
        assert store.is_initialized()
        assert store.canonical_record_count() == 1
    finally:
        store.close()


def test_a_transition_projection_failure_rolls_back_every_table(tmp_path: Path) -> None:
    path = tmp_path / "vellis.sqlite3"
    system = RTGSystem.open(path)
    try:
        assert system.initialize_fresh(
            build_rich_definitions(),
            provenance=Provenance(initiator="owner"),
            initialization_summary="a fresh start",
        ).accepted
        blocker = sqlite3.connect(path)
        try:
            blocker.execute(
                "CREATE TRIGGER refuse_graph_projection BEFORE INSERT ON current_graph_object "
                "BEGIN SELECT RAISE(ABORT, 'projection failed'); END"
            )
            blocker.commit()
        finally:
            blocker.close()

        outcome = system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-1", "person", "Ada"),)),
            provenance=Provenance(initiator="owner"),
        )
        assert outcome.status is OperationStatus.FAILED
        assert system.current_state().revision == 0
        assert system.current_state().graph.is_empty
        assert system.store.canonical_record_count() == 1

        remover = sqlite3.connect(path)
        try:
            remover.execute("DROP TRIGGER refuse_graph_projection")
            remover.commit()
        finally:
            remover.close()
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-1", "person", "Ada"),)),
            provenance=Provenance(initiator="owner"),
        ).accepted
    finally:
        system.close()


def test_an_unreadable_record_time_is_reported_as_a_store_error(tmp_path: Path) -> None:
    path = tmp_path / "vellis.sqlite3"
    _established(path)

    connection = sqlite3.connect(path)
    try:
        connection.execute("UPDATE canonical_record SET recorded_at = 'not-a-time'")
        connection.commit()
    finally:
        connection.close()

    store = CanonicalStore(path)
    try:
        with pytest.raises(StoreError, match="unreadable time"):
            store.initial_record()
    finally:
        store.close()


def test_refusing_a_non_vellis_database_named_like_ours_leaves_it_untouched(
    tmp_path: Path,
) -> None:
    """Excludes screening only for foreign tables; ``schema_meta`` is a generic name.

    A database carrying that table is refused by the marker check, and that check has to
    run before the pragmas rewrite the file header.
    """
    path = tmp_path / "other.sqlite3"
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO schema_meta VALUES ('schema_version', '1')")
        connection.execute("CREATE TABLE payroll (name TEXT)")
        connection.commit()
    finally:
        connection.close()

    before = path.read_bytes()
    siblings = sorted(each.name for each in tmp_path.iterdir())

    with pytest.raises(StoreError, match="not a Vellis canonical store"):
        CanonicalStore(path)

    assert path.read_bytes() == before
    assert sorted(each.name for each in tmp_path.iterdir()) == siblings


def test_a_store_written_by_a_later_build_is_refused(tmp_path: Path) -> None:
    """Excludes reading a schema this build does not understand."""
    path = tmp_path / "vellis.sqlite3"
    _established(path)

    connection = sqlite3.connect(path)
    try:
        connection.execute("UPDATE schema_meta SET value = '999' WHERE key = 'schema_version'")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(StoreError, match="schema version 999"):
        CanonicalStore(path)


def test_concurrent_initialization_establishes_exactly_one_base(tmp_path: Path) -> None:
    """Excludes a deferred transaction, which turns a clean refusal into a lock error."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from vellis.canonical import Provenance
    from vellis.outcomes import OperationStatus

    path = tmp_path / "vellis.sqlite3"
    definitions = build_rich_definitions()

    barrier = threading.Barrier(6)

    def attempt(_: int) -> OperationStatus:
        system = RTGSystem.open(path)
        try:
            # Start together, so the race this test exists to exercise actually happens.
            barrier.wait()
            return system.initialize_fresh(
                definitions,
                provenance=Provenance(initiator="owner"),
                initialization_summary="a fresh start",
            ).status
        finally:
            system.close()

    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(attempt, range(6)))

    assert outcomes.count(OperationStatus.ACCEPTED) == 1
    assert outcomes.count(OperationStatus.REJECTED) == 5

    store = CanonicalStore(path)
    try:
        assert store.canonical_record_count() == 1
        assert store.current_state().revision == 0
    finally:
        store.close()


def test_a_stored_number_outside_the_decimal_range_is_a_store_error(tmp_path: Path) -> None:
    """Every unreadable stored payload must reach the caller as StoreError."""
    path = tmp_path / "vellis.sqlite3"
    _established(path)

    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE canonical_record SET payload = replace(payload, '\"revision\":0',"
            " '\"revision\":1e1000000000000000000') WHERE ordinal = 0"
        )
        connection.commit()
    finally:
        connection.close()

    store = CanonicalStore(path)
    try:
        with pytest.raises(StoreError, match="does not decode"):
            store.initial_record()
    finally:
        store.close()


def test_a_failed_read_is_reported_as_a_store_error_not_a_driver_exception(
    tmp_path: Path,
) -> None:
    """Callers handle StoreError; a driver exception would become a traceback instead."""
    path = tmp_path / "vellis.sqlite3"
    _established(path)
    store = CanonicalStore(path)
    try:
        store._connection.execute("DROP TABLE current_state")  # noqa: SLF001
        with pytest.raises(StoreError, match="could not read"):
            store.current_state()
        with pytest.raises(StoreError, match="could not read"):
            store.is_initialized()
        store._connection.execute("DROP TABLE canonical_record")  # noqa: SLF001
        with pytest.raises(StoreError, match="could not read"):
            store.initial_record()
        with pytest.raises(StoreError, match="could not read"):
            store.transitions()
    finally:
        store.close()
