"""Focused evidence for the fresh VEL2 persistence foundation."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

import vellis.audit as audit_module
import vellis.operations as operation_module
from vellis.audit import audit_connection, audit_database
from vellis.canonical_encoding import (
    CanonicalHeader,
    Record,
    RowDescriptor,
    canonical_record_hash,
)
from vellis.database import (
    APPLICATION_ID,
    PROTOTYPE_APPLICATION_ID,
    USER_VERSION,
    DatabaseError,
    connect_database,
    require_supported_database,
)
from vellis.definition_repository import insert_definition_versions, load_definitions
from vellis.domain import (
    Anchor,
    AnchorTypeDefinition,
    AssociatedData,
    AssociatedDataTypeDefinition,
    Cardinality,
    CurrentState,
    LinkTypeDefinition,
    PropertyDefinition,
    RevisionState,
    ScalarValue,
    SystemEnvelope,
    TimeState,
    ValueKind,
    parse_timestamp,
)
from vellis.graph_repository import insert_graph_versions, load_graph
from vellis.operations import initialize_blank, initialize_with_definitions, read_state
from vellis.starter import everyday_life_starter
from vellis.state_repository import StateNotFoundError, resolve_state

PERSON_UUID = "12345678-1234-4234-8234-123456789abc"
DATA_UUID = "22345678-1234-4234-8234-123456789abc"


def test_blank_initialization_is_private_auditable_and_has_no_population(tmp_path: Path) -> None:
    path = tmp_path / "owner" / "vellis.db"
    result = initialize_blank(path, recorded_at="2026-08-20T00:00:00Z")
    assert result.resulting_revision == 0
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert oct(path.parent.stat().st_mode & 0o777) == "0o700"
    assert audit_database(path).clean

    connection = connect_database(path, read_only=True)
    try:
        require_supported_database(connection)
        assert int(connection.execute("PRAGMA application_id").fetchone()[0]) == APPLICATION_ID
        assert int(connection.execute("PRAGMA user_version").fetchone()[0]) == USER_VERSION
        assert _application_relations(connection) == _EXPECTED_RELATIONS
        assert "type_key_identity" in _foreign_key_targets(connection, "graph_object_version")
        assert "type_key_identity" in _foreign_key_targets(
            connection, "property_definition_allowed_value"
        )
        for relation in (
            "graph_object_version",
            "definition_version",
            "draft_metadata",
            "activity_header",
            "validation_run",
            "search_document",
        ):
            assert int(connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0]) == 0
        assert int(connection.execute("SELECT count(*) FROM canonical_record").fetchone()[0]) == 1
        assert connection.execute(
            "SELECT summary FROM canonical_record WHERE revision = 0"
        ).fetchone()[0] == (
            "Initialized Vellis database: definitions=0 "
            "(anchor=0, associatedData=0, link=0), graphObjects=0"
        )
    finally:
        connection.close()


def test_existing_nonprivate_data_directory_is_refused_without_mutation(tmp_path: Path) -> None:
    data_directory = tmp_path / "existing"
    data_directory.mkdir(mode=0o755)
    data_directory.chmod(0o755)
    destination = data_directory / "vellis.db"
    with pytest.raises(PermissionError, match="owner-private mode 0700"):
        initialize_blank(destination)
    assert not destination.exists()
    assert data_directory.stat().st_mode & 0o777 == 0o755


@pytest.mark.parametrize(
    "name", ("owner?name.db", "owner#name.db", "owner%name.db", "owner name.db")
)
def test_read_only_connection_escapes_valid_path_metacharacters(tmp_path: Path, name: str) -> None:
    path = tmp_path / name
    initialize_blank(path)
    assert read_state(path).evaluated_revision == 0
    assert audit_database(path).clean
    allowed = {name, f"{name}-wal", f"{name}-shm"}
    assert {candidate.name for candidate in tmp_path.iterdir()} <= allowed


def test_audit_holds_one_read_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "snapshot.db"
    initialize_blank(path)
    connection = connect_database(path, read_only=True)
    observed: list[bool] = []
    original = audit_module._check_sqlite_integrity

    def observe_snapshot(candidate: sqlite3.Connection, findings: list[str]) -> None:
        observed.append(candidate.in_transaction)
        original(candidate, findings)

    monkeypatch.setattr(audit_module, "_check_sqlite_integrity", observe_snapshot)
    try:
        assert audit_connection(connection).clean
        assert observed == [True]
        assert not connection.in_transaction
    finally:
        connection.close()


def test_starter_has_exact_small_typed_vocabulary_and_no_graph(tmp_path: Path) -> None:
    path = tmp_path / "starter.db"
    initialize_with_definitions(
        path,
        everyday_life_starter(),
        recorded_at="2026-08-20T00:00:00Z",
    )
    state = read_state(path)
    assert state.graph == ()
    anchors = tuple(value for value in state.definitions if isinstance(value, AnchorTypeDefinition))
    data = tuple(
        value for value in state.definitions if isinstance(value, AssociatedDataTypeDefinition)
    )
    links = tuple(value for value in state.definitions if isinstance(value, LinkTypeDefinition))
    connection = connect_database(path, read_only=True)
    try:
        summary = str(
            connection.execute(
                "SELECT summary FROM canonical_record WHERE revision = 0"
            ).fetchone()[0]
        )
    finally:
        connection.close()
    assert summary.startswith(
        f"Initialized Vellis database: definitions={len(state.definitions)} "
        f"(anchor={len(anchors)}, associatedData={len(data)}, link={len(links)}), "
        "graphObjects=0"
    )
    assert all(value.anchors_per_object == Cardinality(1, 1) for value in data)
    assert all(value.objects_per_anchor == Cardinality(0, 1) for value in data)
    assert all(
        not rule.required and not rule.nullable for value in data for rule in value.properties
    )
    actual_dates = {
        f"{value.type_key}.{rule.name}"
        for value in data
        for rule in value.properties
        if rule.value_kind is ValueKind.DATE
    }
    assert actual_dates == {
        "life.goal.details.targetDate",
        "life.project.details.nextReviewDate",
        "life.task.details.dueDate",
        "life.event.details.start",
        "life.event.details.end",
        "life.routine.details.nextDueDate",
        "life.decision.details.decisionDate",
        "life.note.details.captureDate",
    }
    assert all(value.links_per_source == Cardinality(0) for value in links)
    assert all(value.links_per_target == Cardinality(0) for value in links)
    # Independent projection captured from accepted model/15-everyday-life-starter.sysml.
    assert _starter_projection_digest(everyday_life_starter()) == (
        "9231f6c8a426189b1e7df5c273c0c7e6e42c30d87308cd6166a65b1bf8a31dd0"
    )


def test_generated_initialization_summary_keeps_counts_when_examples_truncate() -> None:
    definitions = tuple(
        AnchorTypeDefinition(f"test.{index}.{'x' * 100}", "Anchor") for index in range(100)
    )
    summary = operation_module._initialization_summary(definitions)
    assert len(summary.encode("utf-8")) <= 1_024
    assert summary.startswith(
        "Initialized Vellis database: definitions=100 "
        "(anchor=100, associatedData=0, link=0), graphObjects=0"
    )
    assert summary.endswith("...")


def test_revision_and_time_selection_use_the_indexed_canonical_record(tmp_path: Path) -> None:
    path = tmp_path / "history.db"
    initialize_blank(path, recorded_at="2026-08-20T00:00:00.25Z")
    assert read_state(path, RevisionState(0)).evaluated_revision == 0
    assert (
        read_state(path, TimeState(parse_timestamp("2026-08-20T00:00:00.25Z"))).evaluated_revision
        == 0
    )
    with pytest.raises(StateNotFoundError, match="at or before"):
        read_state(path, TimeState(parse_timestamp("2026-08-20T00:00:00.249999999Z")))
    with pytest.raises(StateNotFoundError, match="does not exist"):
        read_state(path, RevisionState(1))
    with pytest.raises(StateNotFoundError, match="does not exist"):
        read_state(path, RevisionState(10**30))


def test_unbounded_definition_naturals_round_trip_without_sqlite_overflow(tmp_path: Path) -> None:
    enormous = 10**30
    definitions = (
        AnchorTypeDefinition("test.anchor", "Anchor"),
        AssociatedDataTypeDefinition(
            "test.data",
            "Data",
            ("test.anchor",),
            (
                PropertyDefinition(
                    "text",
                    "Text",
                    ValueKind.TEXT,
                    minimum_length=enormous,
                    maximum_length=enormous + 1,
                ),
            ),
            Cardinality(1, enormous),
            Cardinality(0, enormous + 1),
        ),
    )
    path = tmp_path / "unbounded-naturals.db"
    initialize_with_definitions(path, definitions)
    stored = read_state(path).definitions
    data = next(value for value in stored if isinstance(value, AssociatedDataTypeDefinition))
    assert data.anchors_per_object == Cardinality(1, enormous)
    assert data.objects_per_anchor == Cardinality(0, enormous + 1)
    assert data.properties[0].minimum_length == enormous
    assert data.properties[0].maximum_length == enormous + 1
    assert audit_database(path).clean


def test_current_resolution_and_reads_do_not_traverse_canonical_history(tmp_path: Path) -> None:
    path = tmp_path / "current.db"
    initialize_with_definitions(path, everyday_life_starter())
    connection = connect_database(path, read_only=True)
    statements: list[str] = []
    connection.set_trace_callback(statements.append)
    try:
        state = resolve_state(connection, CurrentState())
        assert load_definitions(connection, state)
        assert load_graph(connection, state) == ()
    finally:
        connection.close()
    assert not any("from canonical_record" in statement.lower() for statement in statements)


def test_prototype_database_is_refused_without_migration(tmp_path: Path) -> None:
    path = tmp_path / "prototype.db"
    connection = sqlite3.connect(path)
    connection.execute(f"PRAGMA application_id = {PROTOTYPE_APPLICATION_ID}")
    connection.execute("PRAGMA user_version = 5")
    connection.close()
    with pytest.raises(DatabaseError, match="prototype-v2 VEL1"):
        read_state(path)


def test_failure_after_temporary_creation_publishes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "failed.db"

    def fail(*_args: object, **_kwargs: object) -> tuple:
        raise RuntimeError("injected insertion failure")

    monkeypatch.setattr(operation_module, "insert_initial_definitions", fail)
    with pytest.raises(RuntimeError, match="injected"):
        initialize_with_definitions(path, everyday_life_starter())
    assert not path.exists()
    assert list(tmp_path.glob(".failed.db.*")) == []
    probe = sqlite3.connect(tmp_path / "rollback-probe.db", timeout=0)
    probe.execute("BEGIN IMMEDIATE")
    probe.rollback()
    probe.close()


def test_destination_race_never_overwrites_the_raced_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "raced.db"
    actual_flush = operation_module._flush_file

    def race_after_flush(temporary: Path) -> None:
        actual_flush(temporary)
        path.write_bytes(b"racer-owned-content")

    monkeypatch.setattr(operation_module, "_flush_file", race_after_flush)
    with pytest.raises(FileExistsError, match="appeared during publication"):
        initialize_blank(path)
    assert path.read_bytes() == b"racer-owned-content"
    assert list(tmp_path.glob(".raced.db.*")) == []


def test_post_publication_directory_flush_failure_does_not_claim_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "published.db"
    actual_flush = operation_module._flush_directory
    calls = 0

    def fail_second_flush(parent: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected post-publication flush loss")
        actual_flush(parent)

    monkeypatch.setattr(operation_module, "_flush_directory", fail_second_flush)
    result = initialize_blank(path)
    assert result.resulting_revision == 0
    assert path.exists()
    assert audit_database(path).clean


def test_temporary_unlink_failure_rolls_back_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "cleanup-failure.db"
    actual_unlink = operation_module.os.unlink
    calls = 0

    def fail_first_unlink(candidate: str | bytes | Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected temporary cleanup failure")
        actual_unlink(candidate)

    monkeypatch.setattr(operation_module.os, "unlink", fail_first_unlink)
    with pytest.raises(OSError, match="publication rolled back"):
        initialize_blank(path)
    assert not path.exists()
    assert list(tmp_path.glob(".cleanup-failure.db.*")) == []


@pytest.mark.parametrize(
    "mutation",
    (
        "UPDATE definition_version SET description = description || ' changed' "
        "WHERE type_key = 'life.person'",
        "UPDATE definition_version SET row_digest = zeroblob(32) WHERE type_key = 'life.person'",
        "UPDATE canonical_record SET record_hash = zeroblob(32) WHERE revision = 0",
        "UPDATE canonical_record SET affected_type_keys = '[]' WHERE revision = 0",
        "UPDATE canonical_record SET affected_uuids = '[\"unexpected\"]' WHERE revision = 0",
    ),
)
def test_audit_detects_content_digest_and_chain_mutation(tmp_path: Path, mutation: str) -> None:
    source = tmp_path / "source.db"
    initialize_with_definitions(source, everyday_life_starter())
    corrupted = tmp_path / "corrupted.db"
    shutil.copyfile(source, corrupted)
    connection = sqlite3.connect(corrupted)
    connection.execute(mutation)
    connection.commit()
    connection.close()
    assert not audit_database(corrupted).clean


def test_audit_rejects_correctly_hashed_child_only_definition_revision(tmp_path: Path) -> None:
    path = tmp_path / "child-only.db"
    initialize_with_definitions(path, _scalar_definitions(), recorded_at="2026-08-20T00:00:00Z")
    connection = connect_database(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        metadata = connection.execute(
            "SELECT lineage_uuid FROM metadata_setting WHERE singleton = 1"
        ).fetchone()
        prior = connection.execute(
            "SELECT record_hash FROM canonical_record WHERE revision = 0"
        ).fetchone()
        child = connection.execute(
            """
            SELECT row_digest FROM property_definition_version
            WHERE type_key = 'test.data' AND property_name = 'nullable'
              AND valid_from_revision = 0
            """
        ).fetchone()
        timestamp = parse_timestamp("2026-08-20T00:00:01Z")
        connection.execute(
            """
            INSERT INTO canonical_record(
                revision, recorded_at, recorded_epoch_seconds, recorded_nanosecond,
                initiator, transition_kind, summary, previous_hash, record_hash
            ) VALUES (1, ?, ?, ?, 'test', 'graphChange', 'child-only mutation', ?, zeroblob(32))
            """,
            (
                timestamp.canonical,
                timestamp.epoch_seconds,
                timestamp.nanosecond,
                bytes(prior["record_hash"]),
            ),
        )
        connection.execute(
            """
            UPDATE property_definition_version SET valid_to_revision = 1
            WHERE type_key = 'test.data' AND property_name = 'nullable'
              AND valid_from_revision = 0
            """
        )
        retired = RowDescriptor(
            "property_definition_version",
            Record(
                (
                    ("typeKey", "test.data"),
                    ("propertyName", "nullable"),
                    ("validFromRevision", 0),
                )
            ),
            bytes(child["row_digest"]),
        )
        header = CanonicalHeader(
            str(metadata["lineage_uuid"]),
            1,
            timestamp,
            "test",
            None,
            "graphChange",
            "child-only mutation",
        )
        record_hash = canonical_record_hash(bytes(prior["record_hash"]), header, (), (retired,))
        connection.execute(
            "UPDATE canonical_record SET record_hash = ? WHERE revision = 1", (record_hash,)
        )
        connection.execute("UPDATE metadata_setting SET head_revision = 1 WHERE singleton = 1")
        connection.commit()
    finally:
        connection.close()
    findings = audit_database(path).findings
    assert any(
        "property_definition_version contains 1 boundaries without a parent version" in finding
        for finding in findings
    )
    assert not any("canonical record hash differs" in finding for finding in findings)


def test_audit_rejects_correctly_hashed_parent_retirement_with_current_children(
    tmp_path: Path,
) -> None:
    path = tmp_path / "parent-only.db"
    initialize_with_definitions(path, _scalar_definitions(), recorded_at="2026-08-20T00:00:00Z")
    connection = connect_database(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        metadata = connection.execute(
            "SELECT lineage_uuid FROM metadata_setting WHERE singleton = 1"
        ).fetchone()
        prior = connection.execute(
            "SELECT record_hash FROM canonical_record WHERE revision = 0"
        ).fetchone()
        parent = connection.execute(
            "SELECT row_digest FROM definition_version "
            "WHERE type_key = 'test.data' AND valid_from_revision = 0"
        ).fetchone()
        timestamp = parse_timestamp("2026-08-20T00:00:01Z")
        connection.execute(
            """
            INSERT INTO canonical_record(
                revision, recorded_at, recorded_epoch_seconds, recorded_nanosecond,
                initiator, transition_kind, summary, affected_type_keys,
                previous_hash, record_hash
            ) VALUES (1, ?, ?, ?, 'test', 'graphChange', 'parent-only retirement',
                '["test.data"]', ?, zeroblob(32))
            """,
            (
                timestamp.canonical,
                timestamp.epoch_seconds,
                timestamp.nanosecond,
                bytes(prior["record_hash"]),
            ),
        )
        connection.execute(
            "UPDATE definition_version SET valid_to_revision = 1 "
            "WHERE type_key = 'test.data' AND valid_from_revision = 0"
        )
        retired = RowDescriptor(
            "definition_version",
            Record((("typeKey", "test.data"), ("validFromRevision", 0))),
            bytes(parent["row_digest"]),
        )
        header = CanonicalHeader(
            str(metadata["lineage_uuid"]),
            1,
            timestamp,
            "test",
            None,
            "graphChange",
            "parent-only retirement",
        )
        record_hash = canonical_record_hash(bytes(prior["record_hash"]), header, (), (retired,))
        connection.execute(
            "UPDATE canonical_record SET record_hash = ? WHERE revision = 1", (record_hash,)
        )
        connection.execute("UPDATE metadata_setting SET head_revision = 1 WHERE singleton = 1")
        connection.commit()
    finally:
        connection.close()
    findings = audit_database(path).findings
    assert any("definition_permitted_type contains" in finding for finding in findings)
    assert any("property_definition_version contains" in finding for finding in findings)
    assert not any("canonical record hash differs" in finding for finding in findings)


def test_audit_rejects_rehashed_non_uuid_database_lineage(tmp_path: Path) -> None:
    path = tmp_path / "lineage.db"
    initialize_blank(path, recorded_at="2026-08-20T00:00:00Z")
    connection = connect_database(path)
    try:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM canonical_record WHERE revision = 0").fetchone()
        connection.execute(
            "UPDATE metadata_setting SET lineage_uuid = 'not-a-uuid' WHERE singleton = 1"
        )
        header = CanonicalHeader(
            "not-a-uuid",
            0,
            parse_timestamp(str(row["recorded_at"])),
            str(row["initiator"]),
            None if row["source"] is None else str(row["source"]),
            str(row["transition_kind"]),
            str(row["summary"]),
        )
        record_hash = canonical_record_hash(bytes(32), header, (), ())
        connection.execute(
            "UPDATE canonical_record SET record_hash = ? WHERE revision = 0", (record_hash,)
        )
        connection.commit()
    finally:
        connection.close()
    findings = audit_database(path).findings
    assert "database lineage is not a canonical hyphenated UUID" in findings
    assert not any("canonical record hash differs" in finding for finding in findings)


@pytest.mark.parametrize(
    "mutation",
    (
        "UPDATE canonical_record SET recorded_epoch_seconds = recorded_epoch_seconds + 1",
        "UPDATE canonical_record SET recorded_at = '2026-08-20T00:00:00+00:00'",
        "UPDATE metadata_setting SET head_revision = 99",
        "UPDATE property_definition_version "
        "SET minimum_timestamp_epoch_seconds = minimum_timestamp_epoch_seconds + 1 "
        "WHERE property_name = 'timestamp'",
        "UPDATE property_definition_version "
        "SET minimum_timestamp_text = '2000-01-01T00:00:00+00:00' "
        "WHERE property_name = 'timestamp'",
        "UPDATE property_definition_allowed_value "
        "SET timestamp_epoch_seconds = timestamp_epoch_seconds + 1 "
        "WHERE property_name = 'timestamp'",
        "UPDATE property_definition_allowed_value "
        "SET timestamp_text = '2026-08-20T00:00:00+00:00' "
        "WHERE property_name = 'timestamp'",
    ),
)
def test_audit_detects_head_and_redundant_timestamp_corruption(
    tmp_path: Path, mutation: str
) -> None:
    source = tmp_path / "source.db"
    initialize_with_definitions(source, _scalar_definitions())
    corrupted = tmp_path / "corrupted.db"
    shutil.copyfile(source, corrupted)
    connection = sqlite3.connect(corrupted)
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute(mutation)
    connection.commit()
    connection.close()
    assert not audit_database(corrupted).clean


def test_scalar_versions_round_trip_null_and_all_nonnull_kinds(tmp_path: Path) -> None:
    definitions = _scalar_definitions()
    path = tmp_path / "scalars.db"
    initialize_with_definitions(path, definitions, recorded_at="2026-08-20T00:00:00Z")
    connection = connect_database(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        _insert_record(connection, 1)
        canonical_definitions = load_definitions(
            connection, resolve_state(connection, RevisionState(0))
        )
        stored_data = next(
            value
            for value in canonical_definitions
            if isinstance(value, AssociatedDataTypeDefinition)
        )
        source_data = definitions[1]
        assert isinstance(source_data, AssociatedDataTypeDefinition)
        assert {value.name: value for value in stored_data.properties} == {
            value.name: value for value in source_data.properties
        }
        objects = (
            Anchor(PERSON_UUID.upper(), "test.anchor", "Owner", SystemEnvelope(1, 1)),
            AssociatedData(
                DATA_UUID.upper(),
                "test.data",
                (PERSON_UUID.upper(),),
                tuple(
                    sorted(
                        (
                            ("boolean", ScalarValue.boolean(True)),
                            ("integer", ScalarValue.integer(42)),
                            ("number", ScalarValue.number(42)),
                            ("text", ScalarValue.text("é")),
                            ("date", ScalarValue.date("2024-02-29")),
                            ("timestamp", ScalarValue.timestamp("2026-08-20T01:00:00+01:00")),
                            ("nullable", None),
                        )
                    )
                ),
                SystemEnvelope(1, 1),
            ),
        )
        insert_graph_versions(connection, objects, canonical_definitions, 1)
        connection.execute("UPDATE metadata_setting SET head_revision = 1 WHERE singleton = 1")
        connection.commit()
        current = load_graph(connection, resolve_state(connection))
        historical = load_graph(connection, resolve_state(connection, RevisionState(0)))
    finally:
        connection.close()
    assert current == objects
    assert current[0].uuid == PERSON_UUID
    assert isinstance(current[1], AssociatedData)
    assert current[1].uuid == DATA_UUID
    assert current[1].anchor_uuids == (PERSON_UUID,)
    assert historical == ()
    corruption = sqlite3.connect(path)
    corruption.execute(
        """
        UPDATE property_version
        SET timestamp_text = '2026-08-20T00:00:00+00:00'
        WHERE property_name = 'timestamp'
        """
    )
    corruption.commit()
    corruption.close()
    assert any(
        "property_version contains inconsistent timestamp" in finding
        for finding in audit_database(path).findings
    )


def test_version_introduction_requires_current_last_changed_revision(tmp_path: Path) -> None:
    path = tmp_path / "last-changed.db"
    initialize_with_definitions(path, (AnchorTypeDefinition("test.anchor", "Anchor"),))
    connection = connect_database(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        _insert_record(connection, 1)
        with pytest.raises(ValueError, match="lastChangedRevision"):
            insert_graph_versions(
                connection,
                (Anchor(PERSON_UUID, "test.anchor", "Owner", SystemEnvelope(0, 0)),),
                (),
                1,
            )
        with pytest.raises(ValueError, match="lastChangedRevision"):
            insert_definition_versions(
                connection,
                (AnchorTypeDefinition("test.other", "Other", SystemEnvelope(0, 0)),),
                1,
            )
        connection.rollback()
    finally:
        connection.close()


def test_audit_rejects_stale_last_changed_revision(tmp_path: Path) -> None:
    path = tmp_path / "stale-last-changed.db"
    initialize_with_definitions(path, (AnchorTypeDefinition("test.anchor", "Anchor"),))
    connection = connect_database(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        _insert_record(connection, 1)
        connection.execute(
            "UPDATE definition_version SET valid_to_revision = 1 WHERE type_key = 'test.anchor'"
        )
        insert_definition_versions(
            connection,
            (AnchorTypeDefinition("test.anchor", "Changed", SystemEnvelope(0, 1)),),
            1,
        )
        connection.execute("UPDATE metadata_setting SET head_revision = 1 WHERE singleton = 1")
        connection.commit()
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE definition_version SET last_changed_revision = 0 "
            "WHERE type_key = 'test.anchor' AND valid_from_revision = 1"
        )
        connection.commit()
    finally:
        connection.close()
    assert any(
        "definition_version contains 1 stale last-changed revisions" in finding
        for finding in audit_database(path).findings
    )


@pytest.mark.parametrize(
    ("relation", "columns", "values", "expected"),
    (
        (
            "graph_object_identity",
            "uuid, kind, created_revision",
            (PERSON_UUID, "anchor", 0),
            "UUID reservations lack a matching earliest graph-object version",
        ),
        (
            "type_key_identity",
            "type_key, kind, created_revision",
            ("test.orphan", "anchor", 0),
            "type-key reservations lack a matching earliest definition version",
        ),
    ),
)
def test_audit_rejects_orphan_identity_reservations(
    tmp_path: Path,
    relation: str,
    columns: str,
    values: tuple[object, ...],
    expected: str,
) -> None:
    path = tmp_path / f"{relation}.db"
    initialize_blank(path)
    connection = connect_database(path)
    connection.execute(
        f"INSERT INTO {relation}({columns}) VALUES (?, ?, ?)",
        values,
    )
    connection.commit()
    connection.close()
    assert expected in audit_database(path).findings


@pytest.mark.parametrize(
    "mutation",
    (
        "UPDATE definition_version SET anchors_per_object_minimum = 0 WHERE kind = 'anchor'",
        "UPDATE definition_version SET anchors_per_object_minimum = NULL "
        "WHERE kind = 'associatedData'",
    ),
)
def test_audit_reports_kind_incompatible_definition_storage(tmp_path: Path, mutation: str) -> None:
    path = tmp_path / "definition-shape.db"
    initialize_with_definitions(path, _scalar_definitions())
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA ignore_check_constraints = ON")
    connection.execute(mutation)
    connection.commit()
    connection.close()
    report = audit_database(path)
    assert not report.clean
    assert any("definition_version contains" in finding for finding in report.findings)


def test_identity_reservations_allow_same_kind_reactivation_only(tmp_path: Path) -> None:
    path = tmp_path / "reservation.db"
    initialize_with_definitions(path, (AnchorTypeDefinition("test.anchor", "Anchor"),))
    connection = connect_database(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        _insert_record(connection, 1)
        first = Anchor(PERSON_UUID, "test.anchor", "First", SystemEnvelope(1, 1, "{}"))
        insert_graph_versions(connection, (first,), (), 1)
        _insert_record(connection, 2)
        connection.execute(
            "UPDATE graph_object_version SET valid_to_revision = 2 WHERE uuid = ?", (PERSON_UUID,)
        )
        reactivated = Anchor(PERSON_UUID, "test.anchor", "Again", SystemEnvelope(1, 2, "{}"))
        insert_graph_versions(connection, (reactivated,), (), 2)
        with pytest.raises(ValueError, match="another object kind"):
            insert_graph_versions(
                connection,
                (
                    AssociatedData(
                        PERSON_UUID,
                        "test.data",
                        (DATA_UUID,),
                        system=SystemEnvelope(1, 2, "{}"),
                    ),
                ),
                (),
                2,
            )
        connection.rollback()
    finally:
        connection.close()


def test_type_key_reservation_preserves_kind_and_system_metadata(tmp_path: Path) -> None:
    path = tmp_path / "type-reservation.db"
    initialize_with_definitions(path, (AnchorTypeDefinition("test.anchor", "Anchor"),))
    connection = connect_database(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        _insert_record(connection, 1)
        connection.execute(
            "UPDATE definition_version SET valid_to_revision = 1 WHERE type_key = 'test.anchor'"
        )
        replacement = AnchorTypeDefinition("test.anchor", "Changed", SystemEnvelope(0, 1))
        insert_definition_versions(connection, (replacement,), 1)
        with pytest.raises(ValueError, match="another kind"):
            insert_definition_versions(
                connection,
                (
                    LinkTypeDefinition(
                        "test.anchor",
                        "Wrong kind",
                        ("test.anchor",),
                        ("test.anchor",),
                        Cardinality(0),
                        Cardinality(0),
                        SystemEnvelope(0, 1),
                    ),
                ),
                1,
            )
        with pytest.raises(ValueError, match="system metadata"):
            insert_definition_versions(
                connection,
                (AnchorTypeDefinition("test.anchor", "Changed", SystemEnvelope(1, 1)),),
                1,
            )
        connection.rollback()
    finally:
        connection.close()


def _scalar_definitions() -> tuple:
    properties = (
        PropertyDefinition(
            "boolean",
            "boolean property",
            ValueKind.BOOLEAN,
            allowed_values=(ScalarValue.boolean(True),),
        ),
        PropertyDefinition(
            "integer",
            "integer property",
            ValueKind.INTEGER,
            allowed_values=(ScalarValue.integer(42),),
            minimum=ScalarValue.integer(0),
            maximum=ScalarValue.integer(100),
        ),
        PropertyDefinition(
            "number",
            "number property",
            ValueKind.NUMBER,
            allowed_values=(ScalarValue.number(42),),
            minimum=ScalarValue.number(0),
            maximum=ScalarValue.number(100),
        ),
        PropertyDefinition(
            "text",
            "text property",
            ValueKind.TEXT,
            allowed_values=(ScalarValue.text("é"),),
        ),
        PropertyDefinition(
            "date",
            "date property",
            ValueKind.DATE,
            allowed_values=(ScalarValue.date("2024-02-29"),),
            minimum=ScalarValue.date("2000-01-01"),
            maximum=ScalarValue.date("2099-12-31"),
        ),
        PropertyDefinition(
            "timestamp",
            "timestamp property",
            ValueKind.TIMESTAMP,
            allowed_values=(ScalarValue.timestamp("2026-08-20T00:00:00Z"),),
            minimum=ScalarValue.timestamp("2000-01-01T00:00:00Z"),
            maximum=ScalarValue.timestamp("2099-12-31T23:59:59Z"),
        ),
        PropertyDefinition("nullable", "nullable property", ValueKind.TEXT, nullable=True),
    )
    return (
        AnchorTypeDefinition("test.anchor", "Anchor"),
        AssociatedDataTypeDefinition(
            "test.data",
            "Data",
            ("test.anchor",),
            properties,
            Cardinality(1, 1),
            Cardinality(0),
        ),
    )


def _insert_record(connection: sqlite3.Connection, revision: int) -> None:
    connection.execute(
        """
        INSERT INTO canonical_record(
            revision, recorded_at, recorded_epoch_seconds, recorded_nanosecond,
            initiator, transition_kind, summary, previous_hash, record_hash
        ) VALUES (?, ?, ?, 0, 'test', 'graphChange', 'test fixture', zeroblob(32), zeroblob(32))
        """,
        (revision, f"2026-08-20T00:00:0{revision}Z", revision),
    )


def _application_relations(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            """
            SELECT name FROM sqlite_schema
            WHERE type IN ('table', 'view')
              AND name NOT LIKE 'sqlite_%'
              AND name NOT GLOB 'search_fts_*'
            """
        )
    }


def _foreign_key_targets(connection: sqlite3.Connection, relation: str) -> set[str]:
    return {str(row[2]) for row in connection.execute(f"PRAGMA foreign_key_list({relation})")}


def _starter_projection_digest(definitions: tuple) -> str:
    projection: list[dict[str, object]] = []
    for definition in sorted(definitions, key=lambda value: value.type_key):
        item: dict[str, object] = {
            "kind": definition.kind.value,
            "typeKey": definition.type_key,
            "description": definition.description,
        }
        if isinstance(definition, AssociatedDataTypeDefinition):
            item.update(
                {
                    "permittedAnchorTypeKeys": sorted(definition.permitted_anchor_type_keys),
                    "anchorsPerObject": [
                        definition.anchors_per_object.minimum,
                        definition.anchors_per_object.maximum,
                    ],
                    "objectsPerAnchor": [
                        definition.objects_per_anchor.minimum,
                        definition.objects_per_anchor.maximum,
                    ],
                    "properties": [
                        {
                            "name": prop.name,
                            "description": prop.description,
                            "valueKind": prop.value_kind.value,
                            "required": prop.required,
                            "nullable": prop.nullable,
                            "allowedValues": [value.wire_value() for value in prop.allowed_values],
                            "minimum": None if prop.minimum is None else prop.minimum.wire_value(),
                            "maximum": None if prop.maximum is None else prop.maximum.wire_value(),
                            "minimumLength": prop.minimum_length,
                            "maximumLength": prop.maximum_length,
                            "pattern": prop.pattern,
                        }
                        for prop in sorted(definition.properties, key=lambda value: value.name)
                    ],
                }
            )
        elif isinstance(definition, LinkTypeDefinition):
            item.update(
                {
                    "permittedSourceTypeKeys": sorted(definition.permitted_source_type_keys),
                    "permittedTargetTypeKeys": sorted(definition.permitted_target_type_keys),
                    "linksPerSource": [
                        definition.links_per_source.minimum,
                        definition.links_per_source.maximum,
                    ],
                    "linksPerTarget": [
                        definition.links_per_target.minimum,
                        definition.links_per_target.maximum,
                    ],
                }
            )
        projection.append(item)
    encoded = json.dumps(
        projection, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


_EXPECTED_RELATIONS = {
    "metadata_setting",
    "canonical_record",
    "graph_object_identity",
    "graph_object_version",
    "direct_association_version",
    "property_version",
    "type_key_identity",
    "definition_version",
    "definition_permitted_type",
    "property_definition_version",
    "property_definition_allowed_value",
    "draft_metadata",
    "draft_definition_entry",
    "draft_definition_permitted_type",
    "draft_property_definition_entry",
    "draft_property_definition_allowed_value",
    "draft_graph_object_patch",
    "draft_association_operation",
    "draft_property_operation",
    "validation_run",
    "validation_finding",
    "activity_header",
    "activity_payload",
    "search_document",
    "search_fts",
}
