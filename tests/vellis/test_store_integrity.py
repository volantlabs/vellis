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
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from shutil import copyfile

import pytest
from conftest import build_rich_definitions

from tests.vellis.oracle import materialize_replay, materialize_state
from tests.vellis.semantic_state import semantic_state_equal
from vellis.canonical import Provenance, now
from vellis.changes import GraphChange
from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    EndpointConstraint,
    GraphDefinitionSet,
    LinkEnd,
    LinkMultiplicityConstraint,
    LinkTypeDefinition,
    PropertyConstraint,
    ValueRange,
)
from vellis.graph import Anchor, AssociatedDataObject
from vellis.json_value import JsonKind, normalize
from vellis.normalized import (
    definition_identity,
    insert_object_value,
    load_definition_set,
    load_object_value,
    object_identity,
)
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


def test_close_reports_a_reader_that_prevents_a_complete_checkpoint(tmp_path: Path) -> None:
    """A busy WAL checkpoint cannot be reported as a clean single-file close."""
    path = tmp_path / "vellis.sqlite3"
    system = RTGSystem.open(path)
    assert system.initialize_fresh(
        GraphDefinitionSet(anchor_types=(AnchorTypeDefinition("person", "A person."),)),
        provenance=Provenance("owner"),
        initialization_summary="fresh",
    ).accepted

    reader = sqlite3.connect(path)
    try:
        reader.execute("BEGIN")
        assert reader.execute("SELECT revision FROM state_head WHERE id = 0").fetchone() == (0,)
        assert system.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-1", "person", "Ada"),)),
            provenance=Provenance("owner"),
        ).accepted

        with pytest.raises(StoreError, match="reader prevented the write-ahead log checkpoint"):
            system.close()
        assert path.with_name(f"{path.name}-wal").exists()
    finally:
        reader.close()

    # Once the conflicting reader is gone, a subsequent clean lifecycle can make the
    # named file independently copyable. No WAL or SHM file is copied with it.
    reopened = RTGSystem.open(path)
    assert materialize_state(reopened).revision == 1
    reopened.close()
    copied = tmp_path / "copied.sqlite3"
    copyfile(path, copied)
    copied.chmod(0o600)
    copy = RTGSystem.open(copied)
    try:
        copied_state = materialize_state(copy)
        assert copied_state.revision == 1
        assert {anchor.uuid for anchor in copied_state.graph.anchors} == {"a-1"}
    finally:
        copy.close()


def test_normalized_object_identity_frames_collections_and_fields(tmp_path: Path) -> None:
    store = CanonicalStore(tmp_path / "vellis.sqlite3")
    first = AssociatedDataObject("d", "note", ("0",), {"1": Decimal(2)})
    second = AssociatedDataObject("d", "note", ("0", "1", "2"), {})
    try:
        first_id = insert_object_value(store._connection, first)  # noqa: SLF001
        second_id = insert_object_value(store._connection, second)  # noqa: SLF001

        assert first_id != second_id
        assert load_object_value(store._connection, first_id) == first  # noqa: SLF001
        assert load_object_value(store._connection, second_id) == second  # noqa: SLF001
    finally:
        store.close()


def test_normalized_definition_identity_distinguishes_absence_from_empty_text(
    tmp_path: Path,
) -> None:
    store = CanonicalStore(tmp_path / "vellis.sqlite3")
    absent = GraphDefinitionSet(anchor_types=(AnchorTypeDefinition("person", None),))
    empty = GraphDefinitionSet(anchor_types=(AnchorTypeDefinition("person", ""),))
    try:
        assert definition_identity(absent) != definition_identity(empty)
    finally:
        store.close()


def test_normalized_definition_identity_frames_endpoint_collections(tmp_path: Path) -> None:
    store = CanonicalStore(tmp_path / "vellis.sqlite3")

    def definitions(source: tuple[str, ...], target: tuple[str, ...]) -> GraphDefinitionSet:
        return GraphDefinitionSet(
            link_types=(
                LinkTypeDefinition(
                    "edge",
                    EndpointConstraint(source, target),
                ),
            )
        )

    try:
        left = definition_identity(definitions(("a",), ("b", "c")))
        right = definition_identity(definitions(("a", "b"), ("c",)))
        assert left != right
    finally:
        store.close()


def test_one_entry_definition_reads_reject_a_multi_entry_identity_before_decode(
    tmp_path: Path,
) -> None:
    system = RTGSystem.open(tmp_path / "vellis.sqlite3")
    definitions = build_rich_definitions()
    try:
        assert system.initialize_fresh(
            definitions, provenance=Provenance("owner"), initialization_summary="fresh"
        ).accepted
        identity = system.store._connection.execute(  # noqa: SLF001
            "SELECT active_definition_set_id FROM state_head WHERE id = 0"
        ).fetchone()[0]

        with pytest.raises(ValueError, match="more than one entry"):
            load_definition_set(system.store._connection, str(identity), one_entry=True)  # noqa: SLF001
    finally:
        system.close()


def test_normalized_identities_follow_canonical_numeric_equality() -> None:
    negative_zero = AssociatedDataObject("d", "note", ("a",), {"number": normalize(Decimal("-0"))})
    positive_zero = AssociatedDataObject("d", "note", ("a",), {"number": normalize(Decimal("0"))})

    def definitions(number: str) -> GraphDefinitionSet:
        return GraphDefinitionSet(
            associated_data_types=(
                AssociatedDataTypeDefinition(
                    "note",
                    property_constraints=(
                        PropertyConstraint(
                            "number",
                            False,
                            JsonKind.NUMBER,
                            value_range=ValueRange(lower_bound=normalize(Decimal(number))),
                        ),
                    ),
                ),
            )
        )

    assert object_identity(negative_zero) == object_identity(positive_zero)
    assert definition_identity(definitions("1")) == definition_identity(definitions("1.0"))


def test_normalized_numbers_preserve_precision_beyond_decimal_context(tmp_path: Path) -> None:
    store = CanonicalStore(tmp_path / "vellis.sqlite3")
    first = AssociatedDataObject(
        "d", "note", ("a",), {"number": normalize(Decimal("12345678901234567890123456789"))}
    )
    second = AssociatedDataObject(
        "d", "note", ("a",), {"number": normalize(Decimal("12345678901234567890123456788"))}
    )
    try:
        first_id = insert_object_value(store._connection, first)  # noqa: SLF001
        second_id = insert_object_value(store._connection, second)  # noqa: SLF001
        assert first_id != second_id
        assert load_object_value(store._connection, first_id) == first  # noqa: SLF001
        assert load_object_value(store._connection, second_id) == second  # noqa: SLF001
    finally:
        store.close()


def test_normalized_relationship_identity_ignores_unordered_participant_order() -> None:
    def definitions(participants: tuple[str, ...]) -> GraphDefinitionSet:
        return GraphDefinitionSet(
            relationship_constraints=(
                LinkMultiplicityConstraint(
                    "edge",
                    LinkEnd.SOURCE,
                    participants,
                    ("target", "other"),
                    0,
                ),
            )
        )

    assert definition_identity(definitions(("a", "b"))) == definition_identity(
        definitions(("b", "a"))
    )


def test_canonical_record_identity_is_bound_to_record_content() -> None:
    moment = datetime.now(UTC)
    common = ("ledger", "prior", 2, "graphMutation", moment, "owner", None, "1")

    assert CanonicalStore._record_identity(*common, "change-a") != (  # noqa: SLF001
        CanonicalStore._record_identity(*common, "change-b")  # noqa: SLF001
    )


def test_a_projection_whose_revision_markers_disagree_is_refused(tmp_path: Path) -> None:
    """Excludes serving a mixed tuple whose revision and content came from different writes.

    Content divergence introduced by editing the file directly is out of scope: detecting
    it would mean decoding a canonical record on every current read, which the
    history-independence requirement forbids.
    """
    path = tmp_path / "vellis.sqlite3"
    _established(path)

    connection = sqlite3.connect(path)
    try:
        connection.execute("UPDATE state_head SET revision = 99 WHERE id = 0")
        connection.commit()
    finally:
        connection.close()

    store = CanonicalStore(path)
    try:
        with pytest.raises(StoreError, match="claims revision"):
            materialize_state(store)
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
    path.chmod(0o600)

    with pytest.raises(StoreError, match="not a Vellis canonical store"):
        CanonicalStore(path)


def test_a_file_that_is_not_a_database_reports_a_store_error(tmp_path: Path) -> None:
    path = tmp_path / "vellis.sqlite3"
    path.write_text("this is not a database\n", encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(NotADatabaseError, match="is not a database"):
        CanonicalStore(path)


def test_a_store_missing_its_tables_reports_a_store_error(tmp_path: Path) -> None:
    path = tmp_path / "vellis.sqlite3"
    _established(path)

    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP TABLE state_head")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(StoreError, match="missing its state_head table"):
        CanonicalStore(path)


def test_a_rich_vocabulary_survives_an_ordinary_restart(tmp_path: Path) -> None:
    """Excludes a durability claim proven only with a vocabulary that has no rules."""
    from vellis.definitions import definition_set_equal

    path = tmp_path / "vellis.sqlite3"
    definitions = build_rich_definitions()
    _established(path, definitions)

    system = RTGSystem.open(path)
    try:
        state = materialize_state(system)
        assert definition_set_equal(state.active_definitions, definitions)
        assert semantic_state_equal(state, materialize_replay(system))
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
    path.chmod(0o600)

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
    path.chmod(0o600)

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
    path.chmod(0o600)

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
    path.chmod(0o600)

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
    from vellis.canonical import Provenance

    path = tmp_path / "vellis.sqlite3"
    store = CanonicalStore(path)
    definitions = build_rich_definitions()
    provenance = Provenance(initiator="owner")
    try:
        blocker = sqlite3.connect(path)
        try:
            blocker.execute(
                "CREATE TRIGGER refuse_projection BEFORE INSERT ON state_head "
                "BEGIN SELECT RAISE(ABORT, 'disk went away'); END"
            )
            blocker.commit()
        finally:
            blocker.close()

        with pytest.raises(StoreError, match="could not establish canonical state"):
            store.initialize_empty(
                definitions,
                provenance=provenance,
                initialization_summary="a fresh start",
                recorded_at=now(),
            )
        assert not store.is_initialized()
        assert store.canonical_record_count() == 0

        remover = sqlite3.connect(path)
        try:
            remover.execute("DROP TRIGGER refuse_projection")
            remover.commit()
        finally:
            remover.close()

        # An open transaction left behind by the failure would refuse this.
        store.initialize_empty(
            definitions,
            provenance=provenance,
            initialization_summary="a fresh start",
            recorded_at=now(),
        )
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
                "CREATE TRIGGER refuse_graph_projection BEFORE INSERT ON graph_presence_interval "
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
        assert materialize_state(system).revision == 0
        assert materialize_state(system).graph.is_empty
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
            store.canonical_summaries()
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
    path.chmod(0o600)

    before = path.read_bytes()
    siblings = sorted(each.name for each in tmp_path.iterdir())

    with pytest.raises(StoreError, match="not a Vellis canonical store"):
        CanonicalStore(path)

    assert path.read_bytes() == before
    assert sorted(each.name for each in tmp_path.iterdir()) == siblings


@pytest.mark.parametrize("unsupported_version", ("4", "999"))
def test_an_unsupported_schema_is_refused(tmp_path: Path, unsupported_version: str) -> None:
    """Excludes both migration of schema four and reading an unknown later schema."""
    path = tmp_path / "vellis.sqlite3"
    _established(path)

    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE schema_meta SET value = ? WHERE key = 'schema_version'",
            (unsupported_version,),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(StoreError, match=f"schema version {unsupported_version}"):
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
        assert materialize_state(store).revision == 0
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
        store._connection.execute("DROP TABLE state_head")  # noqa: SLF001
        with pytest.raises(StoreError, match="could not read"):
            materialize_state(store)
        with pytest.raises(StoreError, match="could not read"):
            store.is_initialized()
        store._connection.execute("PRAGMA foreign_keys = OFF")  # noqa: SLF001
        store._connection.execute("DROP TABLE canonical_record")  # noqa: SLF001
        with pytest.raises(StoreError, match="could not read"):
            store.canonical_summaries()
    finally:
        store.close()
