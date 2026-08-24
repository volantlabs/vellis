"""Discriminating Phase 5 evidence for history, activity, restore, audit, and backup."""

from __future__ import annotations

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import vellis.activity_repository as activity_module
import vellis.audit as audit_module
import vellis.backup_operations as backup_module
import vellis.change_operations as change_module
import vellis.discovery_operations as discovery_module
import vellis.history_repository as history_repository
import vellis.restore_operations as restore_module
import vellis.state_validation_repository as validation_module
from vellis.audit import audit_database
from vellis.backup_operations import (
    BackupPublicationDurabilityError,
    backup_database,
    initialize_from_backup,
)
from vellis.change_domain import (
    DraftChangeRequest,
    DraftInspectionRequest,
    ValidationRequest,
    ValidationScope,
)
from vellis.change_operations import apply_graph_change
from vellis.database import connect_database
from vellis.discovery_operations import type_summary
from vellis.domain import (
    Anchor,
    AnchorTypeDefinition,
    AnchorUpsert,
    AssociatedDataTypeDefinition,
    AssociatedDataUpsert,
    Cardinality,
    CurrentState,
    GraphChangeRequest,
    LinkTypeDefinition,
    LinkUpsert,
    OperationStatus,
    PropertyDefinition,
    RevisionState,
    ScalarValue,
    TimeState,
    TransitionKind,
    ValueKind,
    parse_timestamp,
)
from vellis.draft_inspection_operations import inspect_draft
from vellis.draft_operations import activate_draft, change_draft, validate_state
from vellis.draft_repository import computed_draft_fingerprint
from vellis.history_domain import (
    ActivityHistoryPayload,
    ActivityMode,
    CanonicalHistoryEntry,
    CanonicalHistoryPayload,
    HistoryKind,
    HistoryRequest,
    SequenceHistoryRange,
    TimeHistoryRange,
)
from vellis.history_operations import configure_activity_mode, inspect_history
from vellis.operations import initialize_with_definitions, read_state
from vellis.query_domain import GraphQuery, IdentityObjectSelection, IdentitySelection
from vellis.read_operations import query_graph
from vellis.restore_operations import restore_state
from vellis.settings_operations import HttpTokenChangedError, record_http_token_rotation

PERSON = "11111111-1111-4111-8111-111111111111"
DATA = "22222222-2222-4222-8222-222222222222"
LINK = "33333333-3333-4333-8333-333333333333"
INCOMPLETE = "44444444-4444-4444-8444-444444444444"


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "owner" / "vellis.db"
    initialize_with_definitions(
        path,
        (AnchorTypeDefinition("test.person", "Person"),),
        recorded_at="2026-08-20T00:00:00Z",
    )
    return path


def _seed(path: Path) -> None:
    result = apply_graph_change(
        path,
        GraphChangeRequest(0, (AnchorUpsert(PERSON, "test.person", "Alice"),)),
    )
    assert result.resulting_revision == 1


def _rich_database(tmp_path: Path) -> Path:
    path = tmp_path / "rich" / "vellis.db"
    definitions = (
        AnchorTypeDefinition("test.person", "Person"),
        AssociatedDataTypeDefinition(
            "test.details",
            "Details",
            ("test.person",),
            (
                PropertyDefinition(
                    "note",
                    "Note",
                    ValueKind.TEXT,
                    allowed_values=(ScalarValue.text("hello"),),
                ),
            ),
            Cardinality(1, 1),
            Cardinality(0, 1),
        ),
        LinkTypeDefinition(
            "test.related",
            "Related",
            ("test.person",),
            ("test.details",),
            Cardinality(0),
            Cardinality(0),
        ),
    )
    initialize_with_definitions(path, definitions, recorded_at="2026-08-20T00:00:00Z")
    result = apply_graph_change(
        path,
        GraphChangeRequest(
            0,
            (
                AnchorUpsert(PERSON, "test.person", "Alice"),
                AssociatedDataUpsert(
                    DATA,
                    "test.details",
                    (PERSON,),
                    set_properties=(("note", ScalarValue.text("hello")),),
                ),
                LinkUpsert(LINK, "test.related", PERSON, DATA),
            ),
        ),
    )
    assert result.resulting_revision == 1
    return path


def _activity_count(path: Path) -> int:
    connection = connect_database(path, read_only=True)
    try:
        return int(connection.execute("SELECT count(*) FROM activity_header").fetchone()[0])
    finally:
        connection.close()


def _draft_storage_database(tmp_path: Path) -> Path:
    path = _rich_database(tmp_path)
    definition = AssociatedDataTypeDefinition(
        "test.details",
        "Draft details",
        ("test.person",),
        (
            PropertyDefinition(
                "note",
                "Draft note",
                ValueKind.TEXT,
                allowed_values=(ScalarValue.text("hello"),),
            ),
        ),
        Cardinality(1, 1),
        Cardinality(0, 1),
    )
    changed = change_draft(
        path,
        DraftChangeRequest(
            definition_upserts=(definition,),
            object_upserts=(
                AssociatedDataUpsert(
                    DATA,
                    add_anchor_uuids=(PERSON,),
                    set_properties=(("note", ScalarValue.text("hello")),),
                ),
                AnchorUpsert(INCOMPLETE, display_name="Incomplete"),
            ),
        ),
    )
    assert changed.outcome.status is OperationStatus.ACCEPTED
    validate_state(path, ValidationRequest(ValidationScope.DRAFT, 10))
    return path


def test_history_is_complete_bounded_ordered_and_excludes_its_own_activity(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    canonical = inspect_history(path, HistoryRequest(HistoryKind.CANONICAL, 2))
    assert canonical.status is OperationStatus.ACCEPTED
    assert isinstance(canonical.payload, CanonicalHistoryPayload)
    assert canonical.payload.head_sequence == 1
    assert tuple(value.revision for value in canonical.payload.entries) == (0, 1)
    assert canonical.payload.entries[1].affected_uuids == (PERSON,)

    refused = inspect_history(path, HistoryRequest(HistoryKind.CANONICAL, 1))
    assert refused.status is OperationStatus.REJECTED
    assert refused.payload is None

    before = _activity_count(path)
    activity = inspect_history(path, HistoryRequest(HistoryKind.ACTIVITY, 100))
    assert isinstance(activity.payload, ActivityHistoryPayload)
    assert activity.payload.head_sequence == before
    assert len(activity.payload.entries) == before
    assert all(value.sequence <= before for value in activity.payload.entries)
    assert _activity_count(path) == before + 1


@pytest.mark.parametrize(
    ("type_keys", "uuids"),
    [
        (("",), ()),
        (("z", "a"), ()),
        (("a", "a"), ()),
        ((), ("AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA",)),
        ((), (PERSON.replace("-", ""),)),
        ((), ("22222222-2222-4222-8222-222222222222", PERSON)),
        ((), (PERSON, PERSON)),
    ],
)
def test_canonical_history_entry_requires_deterministic_affected_identifiers(
    type_keys: tuple[str, ...], uuids: tuple[str, ...]
) -> None:
    with pytest.raises(ValueError):
        CanonicalHistoryEntry(
            0,
            parse_timestamp("2026-08-20T00:00:00Z"),
            "owner",
            None,
            TransitionKind.INITIALIZATION,
            "Initialization",
            type_keys,
            uuids,
        )
    valid = CanonicalHistoryEntry(
        0,
        parse_timestamp("2026-08-20T00:00:00Z"),
        "owner",
        None,
        TransitionKind.INITIALIZATION,
        "Initialization",
        (),
        (),
    )
    assert valid.affected_type_keys == ()
    assert valid.affected_uuids == ()


@pytest.mark.parametrize(
    ("column", "revision", "encoded"),
    [
        ("affected_type_keys", 0, '"test.person"'),
        ("affected_type_keys", 0, '{"key":"test.person"}'),
        ("affected_type_keys", 0, '["test.person","test.person"]'),
        ("affected_type_keys", 0, '["z","a"]'),
        ("affected_type_keys", 0, '[""]'),
        ("affected_type_keys", 0, "["),
        ("affected_uuids", 1, f'["{PERSON}","{PERSON}"]'),
        (
            "affected_uuids",
            1,
            f'["22222222-2222-4222-8222-222222222222","{PERSON}"]',
        ),
        ("affected_uuids", 1, '["AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"]'),
        ("affected_uuids", 1, f'["{PERSON.replace("-", "")}"]'),
        ("affected_uuids", 1, '{"uuid":"' + PERSON + '"}'),
    ],
)
def test_corrupt_canonical_affected_arrays_fail_decode_and_audit(
    tmp_path: Path, column: str, revision: int, encoded: str
) -> None:
    path = _database(tmp_path)
    _seed(path)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            f"UPDATE canonical_record SET {column} = ? WHERE revision = ?",
            (encoded, revision),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises((TypeError, ValueError)):
        inspect_history(path, HistoryRequest(HistoryKind.CANONICAL, 10))
    assert not audit_database(path).clean


def test_history_ranges_use_inclusive_time_and_exclusive_after(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    initialization = parse_timestamp("2026-08-20T00:00:00Z")
    by_time = inspect_history(
        path,
        HistoryRequest(
            HistoryKind.CANONICAL,
            10,
            TimeHistoryRange(initialization, initialization),
        ),
    )
    assert isinstance(by_time.payload, CanonicalHistoryPayload)
    assert tuple(value.revision for value in by_time.payload.entries) == (0,)
    empty = inspect_history(
        path,
        HistoryRequest(
            HistoryKind.CANONICAL,
            10,
            SequenceHistoryRange(after=1, through=1),
        ),
    )
    assert isinstance(empty.payload, CanonicalHistoryPayload)
    assert empty.payload.entries == ()
    reversed_result = inspect_history(
        path,
        HistoryRequest(
            HistoryKind.CANONICAL,
            10,
            TimeHistoryRange(parse_timestamp("2026-08-21T00:00:00Z"), initialization),
        ),
    )
    assert reversed_result.status is OperationStatus.REJECTED
    assert reversed_result.payload is None


@pytest.mark.parametrize("kind", [HistoryKind.CANONICAL, HistoryKind.ACTIVITY])
def test_sequence_ranges_clamp_unbounded_naturals_before_sqlite_binding(
    tmp_path: Path, kind: HistoryKind
) -> None:
    path = _database(tmp_path)
    _seed(path)
    huge = 10**100
    beyond = inspect_history(path, HistoryRequest(kind, 100, SequenceHistoryRange(after=huge)))
    assert beyond.status is OperationStatus.ACCEPTED
    assert beyond.payload is not None
    assert beyond.payload.entries == ()

    through = inspect_history(path, HistoryRequest(kind, 100, SequenceHistoryRange(through=huge)))
    assert through.status is OperationStatus.ACCEPTED
    if kind is HistoryKind.ACTIVITY:
        assert isinstance(through.payload, ActivityHistoryPayload)
        assert tuple(entry.sequence for entry in through.payload.entries) == tuple(
            range(1, through.payload.head_sequence + 1)
        )
    else:
        assert isinstance(through.payload, CanonicalHistoryPayload)
        assert tuple(entry.revision for entry in through.payload.entries) == tuple(
            range(through.payload.head_sequence + 1)
        )


def test_rejected_history_and_draft_inspection_store_complete_findings(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    history = inspect_history(path, HistoryRequest(HistoryKind.CANONICAL, 1))
    inspection = inspect_draft(path, DraftInspectionRequest())
    assert history.status is OperationStatus.REJECTED
    assert inspection.outcome.status is OperationStatus.REJECTED

    connection = connect_database(path, read_only=True)
    try:
        rows = connection.execute(
            """SELECT h.capability, p.semantic_payload
               FROM activity_header h JOIN activity_payload p USING(sequence)
               WHERE h.capability IN ('rtg_history', 'rtg_draft_inspect')
               ORDER BY h.sequence"""
        ).fetchall()
    finally:
        connection.close()
    payloads = {str(row["capability"]): json.loads(str(row["semantic_payload"])) for row in rows}
    assert payloads["rtg_history"]["findings"] == [
        {
            "code": finding.code.value,
            "path": finding.path,
            "summary": finding.summary,
            "type_keys": list(finding.type_keys),
            "uuids": list(finding.uuids),
        }
        for finding in history.findings
    ]
    assert payloads["rtg_draft_inspect"]["findings"] == [
        {
            "code": finding.code.value,
            "path": finding.path,
            "summary": finding.summary,
            "type_keys": list(finding.type_keys),
            "uuids": list(finding.uuids),
        }
        for finding in inspection.outcome.findings
    ]


def test_canonical_and_activity_times_never_decrease_under_a_backward_clock(
    tmp_path: Path, monkeypatch
) -> None:
    path = _database(tmp_path)

    class BackwardDateTime:
        @classmethod
        def now(cls, _timezone):
            return datetime(2020, 1, 1, tzinfo=UTC)

    monkeypatch.setattr(change_module, "datetime", BackwardDateTime)
    _seed(path)
    connection = connect_database(path)
    try:
        connection.execute(
            "UPDATE metadata_setting SET last_activity_time = '2030-01-01T00:00:00Z'"
        )
    finally:
        connection.close()
    monkeypatch.setattr(activity_module, "datetime", BackwardDateTime)
    type_summary(path)
    connection = connect_database(path, read_only=True)
    try:
        canonical_times = [
            row[0]
            for row in connection.execute(
                "SELECT recorded_at FROM canonical_record ORDER BY revision"
            )
        ]
        activity_time = connection.execute(
            "SELECT recorded_at FROM activity_header ORDER BY sequence DESC LIMIT 1"
        ).fetchone()[0]
    finally:
        connection.close()
    assert canonical_times == ["2026-08-20T00:00:00Z", "2026-08-20T00:00:00Z"]
    assert activity_time == "2030-01-01T00:00:00Z"
    assert (
        read_state(path, TimeState(parse_timestamp("2026-08-20T00:00:00Z"))).evaluated_revision == 1
    )


def test_activity_mode_separates_semantic_and_verbose_payloads(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    type_summary(path)
    configure_activity_mode(path, ActivityMode.VERBOSE)
    type_summary(path)
    result = inspect_history(path, HistoryRequest(HistoryKind.ACTIVITY, 100, include_verbose=True))
    assert isinstance(result.payload, ActivityHistoryPayload)
    summaries = [
        entry for entry in result.payload.entries if entry.capability == "rtg_type_summary"
    ]
    assert len(summaries) == 2
    assert summaries[0].verbose_payload is None
    assert summaries[1].verbose_payload is not None
    later = inspect_history(path, HistoryRequest(HistoryKind.ACTIVITY, 100, include_verbose=True))
    assert isinstance(later.payload, ActivityHistoryPayload)
    history_entries = [
        entry for entry in later.payload.entries if entry.capability == "rtg_history"
    ]
    assert len(history_entries) == 1
    assert all("entries" not in json.dumps(entry.semantic_payload) for entry in history_entries)
    assert all("entries" not in json.dumps(entry.verbose_payload) for entry in history_entries)
    assert read_state(path).evaluated_revision == 1


def test_time_history_uses_recorded_time_indexes_after_a_growing_prefix(
    tmp_path: Path, monkeypatch
) -> None:
    path = _database(tmp_path)

    class AdvancingDateTime:
        tick = 0

        @classmethod
        def now(cls, _timezone):
            cls.tick += 1
            return datetime(2026, 8, 21, tzinfo=UTC) + timedelta(microseconds=cls.tick)

    monkeypatch.setattr(change_module, "datetime", AdvancingDateTime)
    monkeypatch.setattr(activity_module, "datetime", AdvancingDateTime)
    for revision in range(1, 49):
        result = apply_graph_change(
            path,
            GraphChangeRequest(
                revision - 1,
                (
                    AnchorUpsert(
                        PERSON,
                        "test.person" if revision == 1 else None,
                        f"Person {revision}",
                    ),
                ),
            ),
        )
        assert result.resulting_revision == revision

    connection = connect_database(path, read_only=True)
    try:
        canonical_time = parse_timestamp(
            str(
                connection.execute(
                    "SELECT recorded_at FROM canonical_record ORDER BY revision DESC LIMIT 1"
                ).fetchone()[0]
            )
        )
        activity_time = parse_timestamp(
            str(
                connection.execute(
                    "SELECT recorded_at FROM activity_header ORDER BY sequence DESC LIMIT 1"
                ).fetchone()[0]
            )
        )
        canonical_request = HistoryRequest(
            HistoryKind.CANONICAL, 10, TimeHistoryRange(canonical_time, canonical_time)
        )
        activity_request = HistoryRequest(
            HistoryKind.ACTIVITY, 10, TimeHistoryRange(activity_time, activity_time)
        )
        canonical_sql, canonical_parameters = history_repository._canonical_statement(
            canonical_request, 48
        )
        activity_sql, activity_parameters = history_repository._activity_statement(
            activity_request, 48
        )
        canonical_plan = " ".join(
            str(row[3])
            for row in connection.execute(
                f"EXPLAIN QUERY PLAN {canonical_sql}", (*canonical_parameters, 11)
            )
        )
        activity_plan = " ".join(
            str(row[3])
            for row in connection.execute(
                f"EXPLAIN QUERY PLAN {activity_sql}", (*activity_parameters, 11)
            )
        )
    finally:
        connection.close()
    assert "canonical_record_time_idx" in canonical_plan
    assert "activity_time_idx" in activity_plan
    assert "SCAN canonical_record" not in canonical_plan
    assert "SCAN h" not in activity_plan
    canonical = inspect_history(path, canonical_request)
    activity = inspect_history(path, activity_request)
    assert isinstance(canonical.payload, CanonicalHistoryPayload)
    assert tuple(entry.revision for entry in canonical.payload.entries) == (48,)
    assert isinstance(activity.payload, ActivityHistoryPayload)
    assert tuple(entry.sequence for entry in activity.payload.entries) == (48,)


def test_activity_keeps_complete_rejected_mutation_and_truthful_bounded_bindings(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    uuids = tuple(f"{index:08x}-0000-4000-8000-{index:012x}" for index in range(1, 102))
    created = apply_graph_change(
        path,
        GraphChangeRequest(
            0,
            tuple(
                AnchorUpsert(uuid, "test.person", f"Person {index}")
                for index, uuid in enumerate(uuids)
            ),
        ),
    )
    assert created.resulting_revision == 1
    query_graph(
        path,
        GraphQuery(IdentitySelection(tuple(IdentityObjectSelection(uuid) for uuid in uuids))),
    )
    rejected_request = GraphChangeRequest(
        1,
        (AnchorUpsert(uuids[0], display_name="Rejected"),),
        (uuids[0],),
    )
    assert apply_graph_change(path, rejected_request).status is OperationStatus.REJECTED
    activity = inspect_history(path, HistoryRequest(HistoryKind.ACTIVITY, 100))
    assert isinstance(activity.payload, ActivityHistoryPayload)
    query_entry = next(
        value for value in activity.payload.entries if value.capability == "rtg_query"
    )
    assert isinstance(query_entry.semantic_payload, dict)
    shape = query_entry.semantic_payload["resultShape"]
    assert isinstance(shape, dict)
    assert shape["bindingCount"] == 101
    assert len(shape["bindings"]) == 100
    rejected_entry = [
        value for value in activity.payload.entries if value.capability == "rtg_change"
    ][-1]
    assert isinstance(rejected_entry.semantic_payload, dict)
    request = rejected_entry.semantic_payload["request"]
    assert isinstance(request, dict)
    assert request["upserts"][0]["kind"] == "anchor"
    assert request["remove_uuids"] == [uuids[0]]


def test_restore_revision_preserves_lineage_metadata_and_intervening_history(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    _seed(path)
    changed = apply_graph_change(
        path,
        GraphChangeRequest(1, (AnchorUpsert(PERSON, display_name="Changed"),)),
    )
    assert changed.resulting_revision == 2
    restored = restore_state(path, RevisionState(1))
    assert restored.status is OperationStatus.ACCEPTED
    assert restored.resulting_revision == 3
    anchor = read_state(path).graph[0]
    assert isinstance(anchor, Anchor)
    assert anchor.display_name == "Alice"
    assert anchor.system is not None
    assert (anchor.system.created_revision, anchor.system.last_changed_revision) == (1, 3)
    history = inspect_history(path, HistoryRequest(HistoryKind.CANONICAL, 10))
    assert isinstance(history.payload, CanonicalHistoryPayload)
    assert tuple(value.revision for value in history.payload.entries) == (0, 1, 2, 3)
    no_op = restore_state(path, RevisionState(3))
    assert no_op.resulting_revision is None
    assert read_state(path).evaluated_revision == 3
    assert audit_database(path).clean


def test_activation_and_restore_activity_reference_complete_canonical_effects(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    _seed(path)
    staged = change_draft(
        path,
        DraftChangeRequest(
            definition_upserts=(AnchorTypeDefinition("test.person", "Draft person"),),
            object_upserts=(AnchorUpsert(PERSON, display_name="Draft Alice"),),
        ),
    )
    assert staged.outcome.status is OperationStatus.ACCEPTED
    assert activate_draft(path).outcome.resulting_revision == 2
    assert restore_state(path, RevisionState(1)).resulting_revision == 3

    connection = connect_database(path, read_only=True)
    try:
        rows = connection.execute(
            """SELECT h.capability, h.resulting_revision, p.semantic_payload,
                      c.affected_type_keys, c.affected_uuids
               FROM activity_header h
               JOIN activity_payload p USING(sequence)
               JOIN canonical_record c ON c.revision = h.resulting_revision
               WHERE h.capability IN ('rtg_draft_activate', 'restore')
               ORDER BY h.sequence"""
        ).fetchall()
    finally:
        connection.close()
    assert [str(row["capability"]) for row in rows] == ["rtg_draft_activate", "restore"]
    for row in rows:
        semantic = json.loads(str(row["semantic_payload"]))
        assert semantic["resultingRevision"] == row["resulting_revision"]
        assert semantic["affectedTypeKeys"] == json.loads(str(row["affected_type_keys"]))
        assert semantic["affectedUuids"] == json.loads(str(row["affected_uuids"]))
        assert "request" not in semantic


def test_restore_by_time_and_present_draft_refusal_have_exact_non_effects(tmp_path: Path) -> None:
    path = _database(tmp_path)
    _seed(path)
    apply_graph_change(path, GraphChangeRequest(1, (AnchorUpsert(PERSON, display_name="Changed"),)))
    before = read_state(path)
    change_draft(
        path, DraftChangeRequest(object_upserts=(AnchorUpsert(PERSON, display_name="Draft"),))
    )
    refused = restore_state(path, TimeState(parse_timestamp("2026-08-20T00:00:00Z")))
    assert refused.status is OperationStatus.REJECTED
    assert read_state(path, CurrentState()) == before


def test_restore_removes_later_definition_and_object_as_one_hashed_transition(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    extra_uuid = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    change_draft(
        path,
        DraftChangeRequest(
            definition_upserts=(AnchorTypeDefinition("test.extra", "Extra"),),
            object_upserts=(AnchorUpsert(extra_uuid, "test.extra", "Later"),),
        ),
    )
    assert activate_draft(path).outcome.resulting_revision == 1
    restored = restore_state(path, RevisionState(0))
    assert restored.resulting_revision == 2
    state = read_state(path)
    assert all(value.type_key != "test.extra" for value in state.definitions)
    assert all(value.uuid != extra_uuid for value in state.graph)
    assert audit_database(path).clean


def test_restore_serialization_failure_rolls_back_revision_and_activity(
    tmp_path: Path, monkeypatch
) -> None:
    path = _database(tmp_path)
    _seed(path)
    apply_graph_change(path, GraphChangeRequest(1, (AnchorUpsert(PERSON, display_name="Changed"),)))
    before = read_state(path)
    activity = _activity_count(path)

    def fail(_value):
        raise RuntimeError("serialization failed")

    monkeypatch.setattr(restore_module, "serialize_wire", fail)
    with pytest.raises(RuntimeError, match="serialization failed"):
        restore_state(path, RevisionState(1))
    assert read_state(path) == before
    assert _activity_count(path) == activity
    assert audit_database(path).clean


def _persistent_snapshot(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        return "\n".join(connection.iterdump())


@pytest.mark.parametrize(
    "capability", ("summary", "inspect", "query", "history", "configure", "restore")
)
def test_shared_public_projection_precedes_every_other_public_commit_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capability: str
) -> None:
    path = _database(tmp_path)
    _seed(path)
    if capability == "restore":
        apply_graph_change(
            path,
            GraphChangeRequest(1, (AnchorUpsert(PERSON, display_name="Changed"),)),
        )
    before = _persistent_snapshot(path)

    def fail(_value):
        raise RuntimeError("public projection failed")

    monkeypatch.setattr("vellis.wire.public_result", fail)
    with pytest.raises(RuntimeError, match="public projection failed"):
        if capability == "summary":
            type_summary(path)
        elif capability == "inspect":
            discovery_module.type_inspect(path, ("test.person",))
        elif capability == "query":
            query_graph(
                path,
                GraphQuery(IdentitySelection((IdentityObjectSelection(PERSON),))),
            )
        elif capability == "history":
            inspect_history(path, HistoryRequest(HistoryKind.CANONICAL, 10))
        elif capability == "configure":
            configure_activity_mode(path, ActivityMode.VERBOSE)
        else:
            restore_state(path, RevisionState(1))
    assert _persistent_snapshot(path) == before


def test_settings_public_projection_failure_precedes_token_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _database(tmp_path)
    before = _persistent_snapshot(path)
    published = False

    def publish() -> None:
        nonlocal published
        published = True

    def fail(_value):
        raise RuntimeError("public projection failed")

    monkeypatch.setattr("vellis.wire.public_result", fail)
    with pytest.raises(RuntimeError, match="public projection failed"):
        record_http_token_rotation(path, publish)
    assert not published
    assert _persistent_snapshot(path) == before


def test_settings_post_token_activity_failure_preserves_changed_truth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _database(tmp_path)
    before = _persistent_snapshot(path)
    published = False

    def publish() -> None:
        nonlocal published
        published = True

    monkeypatch.setattr(
        "vellis.settings_operations.append_activity",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("activity failed")),
    )
    with pytest.raises(HttpTokenChangedError, match="token changed"):
        record_http_token_rotation(path, publish)
    assert published
    assert _persistent_snapshot(path) == before


def test_audit_and_restore_retain_only_one_selected_record_at_a_time(
    tmp_path: Path, monkeypatch
) -> None:
    path = _database(tmp_path)
    uuids = tuple(f"{index:08x}-0000-4000-8000-{index:012x}" for index in range(96))
    created = apply_graph_change(
        path,
        GraphChangeRequest(
            0,
            tuple(
                AnchorUpsert(uuid, "test.person", f"Person {index}")
                for index, uuid in enumerate(uuids)
            ),
        ),
    )
    assert created.resulting_revision == 1
    changed = apply_graph_change(
        path,
        GraphChangeRequest(
            1,
            tuple(
                AnchorUpsert(uuid, display_name=f"Changed {index}")
                for index, uuid in enumerate(uuids)
            ),
        ),
    )
    assert changed.resulting_revision == 2

    original_definitions = audit_module.load_definitions
    original_graph = audit_module.load_graph_objects

    def bounded_definitions(connection, state, type_keys=None):
        assert type_keys is not None and len(type_keys) <= 1
        return original_definitions(connection, state, type_keys)

    def bounded_graph(connection, state, selected=()):
        assert len(selected) <= 1
        return original_graph(connection, state, selected)

    for module in (audit_module, restore_module, validation_module):
        monkeypatch.setattr(module, "load_definitions", bounded_definitions)
        monkeypatch.setattr(module, "load_graph_objects", bounded_graph)
    assert audit_database(path).clean
    restored = restore_state(path, RevisionState(1))
    assert restored.resulting_revision == 3
    assert audit_database(path).clean


def test_audit_finding_accumulator_retains_each_fixed_category_once() -> None:
    findings = audit_module._FindingCategories()
    for _ in range(10_000):
        findings.append("one fixed corruption category")
    assert findings == ["one fixed corruption category"]


def test_audit_scans_activity_and_validation_once_through_governance(tmp_path: Path) -> None:
    path = _draft_storage_database(tmp_path)
    statements: list[str] = []
    connection = connect_database(path, read_only=True)
    try:
        connection.set_trace_callback(statements.append)
        assert audit_module.audit_connection(connection).clean
    finally:
        connection.close()
    normalized = [" ".join(statement.split()) for statement in statements]
    assert (
        sum(
            statement.startswith(
                "SELECT h.*, p.semantic_payload, p.verbose_payload FROM activity_header h"
            )
            for statement in normalized
        )
        == 1
    )
    assert normalized.count("SELECT * FROM validation_run ORDER BY scope") == 1


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE canonical_record SET record_hash = zeroblob(32) WHERE revision = 1",
        "UPDATE graph_object_version SET row_digest = zeroblob(32) "
        "WHERE uuid = '11111111-1111-4111-8111-111111111111'",
        "UPDATE search_document SET content = 'corrupt' "
        "WHERE object_uuid = '11111111-1111-4111-8111-111111111111'",
        "DELETE FROM search_fts_data WHERE id = (SELECT max(id) FROM search_fts_data)",
        "UPDATE activity_payload SET semantic_payload = '{' WHERE sequence = 1",
    ],
)
def test_read_only_audit_detects_independent_relation_corruption(
    tmp_path: Path, mutation: str
) -> None:
    path = _database(tmp_path)
    _seed(path)
    connection = sqlite3.connect(path)
    try:
        connection.execute(mutation)
        connection.commit()
    finally:
        connection.close()
    count = _activity_count(path)
    assert not audit_database(path).clean
    assert _activity_count(path) == count


def test_audit_detects_overlapping_versions_with_individually_valid_intervals(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    _seed(path)
    assert (
        apply_graph_change(
            path,
            GraphChangeRequest(1, (AnchorUpsert(PERSON, display_name="Alice Two"),)),
        ).resulting_revision
        == 2
    )
    assert (
        apply_graph_change(
            path,
            GraphChangeRequest(2, (AnchorUpsert(PERSON, display_name="Alice Three"),)),
        ).resulting_revision
        == 3
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE graph_object_version SET valid_to_revision = 3 "
            "WHERE uuid = ? AND valid_from_revision = 1",
            (PERSON,),
        )
    report = audit_database(path)
    assert any("graph_object_version contains 1 overlapping" in item for item in report.findings)


def test_audit_detects_phrase_changing_fts_token_position_corruption(tmp_path: Path) -> None:
    path = _database(tmp_path)
    assert (
        apply_graph_change(
            path,
            GraphChangeRequest(0, (AnchorUpsert(PERSON, "test.person", "alpha beta"),)),
        ).resulting_revision
        == 1
    )
    with sqlite3.connect(path) as connection:
        document_id = int(
            connection.execute(
                "SELECT document_id FROM search_document "
                "WHERE object_uuid = ? AND valid_to_revision IS NULL",
                (PERSON,),
            ).fetchone()[0]
        )
        connection.execute(
            "INSERT INTO search_fts(search_fts, rowid, content) VALUES ('delete', ?, ?)",
            (document_id, "alpha beta"),
        )
        connection.execute(
            "INSERT INTO search_fts(rowid, content) VALUES (?, ?)",
            (document_id, "beta alpha"),
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM search_fts WHERE search_fts MATCH ?",
                ('"alpha beta"',),
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM search_fts WHERE search_fts MATCH ?",
                ('"beta alpha"',),
            ).fetchone()[0]
            == 1
        )
    report = audit_database(path)
    assert any("search FTS terms differ" in item for item in report.findings)


@pytest.mark.parametrize(
    ("relation", "key_column"),
    [
        ("definition_permitted_type", "type_key"),
        ("property_definition_version", "type_key"),
        ("property_definition_allowed_value", "type_key"),
        ("direct_association_version", "object_uuid"),
        ("property_version", "object_uuid"),
    ],
)
def test_audit_detects_every_version_child_digest_family(
    tmp_path: Path, relation: str, key_column: str
) -> None:
    path = _rich_database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        changed = connection.execute(
            f"UPDATE {relation} SET row_digest = zeroblob(32) "
            f"WHERE {key_column} = (SELECT min({key_column}) FROM {relation})"
        ).rowcount
        assert changed == 1, key_column
        connection.commit()
    finally:
        connection.close()
    assert not audit_database(path).clean


@pytest.mark.parametrize(
    "mutation",
    [
        "DELETE FROM activity_payload WHERE sequence = 1",
        "UPDATE metadata_setting SET last_activity_sequence = 999 WHERE singleton = 1",
        "UPDATE activity_header SET recorded_nanosecond = 1 WHERE sequence = 1",
        "INSERT INTO activity_payload VALUES (999, '{}', NULL)",
        "UPDATE validation_run SET cursor_hash = x'00' WHERE scope = 'current'",
        "UPDATE validation_run SET evaluated_revision = 999 WHERE scope = 'current'",
        "INSERT INTO validation_finding VALUES ('current', 5, '{}')",
    ],
)
def test_audit_detects_activity_and_validation_structural_edges(
    tmp_path: Path, mutation: str
) -> None:
    path = _database(tmp_path)
    _seed(path)
    validate_state(path, ValidationRequest(ValidationScope.CURRENT, 10))
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(mutation)
        connection.commit()
    finally:
        connection.close()
    assert not audit_database(path).clean


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            "UPDATE draft_metadata SET fingerprint = zeroblob(32)",
            "draft fingerprint differs",
        ),
        (
            "UPDATE draft_metadata SET inspect_cursor_hash = zeroblob(32)",
            "draft inspection cursor fields",
        ),
        (
            "DELETE FROM draft_metadata",
            "draft rows exist without draft metadata",
        ),
        (
            "UPDATE draft_definition_entry SET operation = 'bogus' WHERE type_key = 'test.details'",
            "draft definition entry",
        ),
        (
            "UPDATE draft_definition_permitted_type SET role = 'bogus' "
            "WHERE type_key = 'test.details'",
            "draft definition entry",
        ),
        (
            "UPDATE draft_property_definition_entry SET required = 2 "
            "WHERE type_key = 'test.details'",
            "draft definition entry",
        ),
        (
            "UPDATE draft_property_definition_allowed_value SET ordinal = 4 "
            "WHERE type_key = 'test.details'",
            "draft definition entry",
        ),
        (
            "UPDATE draft_graph_object_patch SET has_type_key = 1 WHERE uuid = '" + DATA + "'",
            "draft graph patch",
        ),
        (
            "UPDATE draft_association_operation SET operation = 'bogus' "
            "WHERE object_uuid = '" + DATA + "'",
            "draft graph patch",
        ),
        (
            "UPDATE draft_property_operation SET operation = 'remove', text_value = 'payload' "
            "WHERE object_uuid = '" + DATA + "'",
            "draft graph patch",
        ),
        (
            "UPDATE draft_property_operation SET operation = 'bogus' "
            "WHERE object_uuid = '" + DATA + "'",
            "draft graph patch",
        ),
    ],
)
def test_audit_closes_every_normalized_draft_relation(
    tmp_path: Path, mutation: str, expected: str
) -> None:
    path = _draft_storage_database(tmp_path)
    connection = connect_database(path)
    try:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(mutation)
        if "draft_metadata" not in mutation:
            digest = computed_draft_fingerprint(connection)
            connection.execute(
                "UPDATE draft_metadata SET fingerprint = ? WHERE singleton = 1", (digest,)
            )
        connection.commit()
    finally:
        connection.close()
    report = audit_database(path)
    assert not report.clean
    assert any(expected in finding for finding in report.findings)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            "UPDATE activity_header SET capability = '' WHERE sequence = 1",
            "activity record is not normalized",
        ),
        (
            "UPDATE activity_header SET outcome = 'imagined' WHERE sequence = 1",
            "activity record is not normalized",
        ),
        (
            "UPDATE activity_header SET initiator = '' WHERE sequence = 1",
            "activity record is not normalized",
        ),
        (
            "UPDATE activity_header SET summary = '' WHERE sequence = 1",
            "activity record is not normalized",
        ),
        (
            "UPDATE activity_payload SET semantic_payload = 'NaN' WHERE sequence = 1",
            "activity record is not normalized",
        ),
        (
            "UPDATE activity_payload SET semantic_payload = '1e400' WHERE sequence = 1",
            "activity record is not normalized",
        ),
        (
            "UPDATE activity_payload SET semantic_payload = 'null' WHERE sequence = 1",
            "activity record is not normalized",
        ),
        (
            "UPDATE activity_payload SET verbose_payload = 'NaN' WHERE sequence = 1",
            "activity record is not normalized",
        ),
        (
            "UPDATE validation_finding SET finding = "
            '\'{"code":"imagined","path":null,"summary":"bad",'
            '"type_keys":[],"uuids":[]}\' WHERE scope = \'draft\' AND ordinal = 0',
            "validation finding is not normalized",
        ),
        (
            "UPDATE validation_finding SET finding = "
            '\'{"code":"missing","path":null,"summary":"",'
            '"type_keys":[],"uuids":[]}\' WHERE scope = \'draft\' AND ordinal = 0',
            "validation finding is not normalized",
        ),
        (
            "UPDATE validation_finding SET finding = "
            '\'{"code":"missing","path":null,"summary":"bad",'
            '"type_keys":[],"uuids":["NOT-A-UUID"]}\' '
            "WHERE scope = 'draft' AND ordinal = 0",
            "validation finding is not normalized",
        ),
        (
            "UPDATE validation_run SET cursor_hash = zeroblob(32), next_offset = 1, "
            "page_limit = 1 WHERE scope = 'draft'",
            "validation run is not normalized",
        ),
        (
            "UPDATE validation_run SET raw_draft_entry_count = raw_draft_entry_count + 1 "
            "WHERE scope = 'draft'",
            "validation run is not normalized",
        ),
    ],
)
def test_audit_decodes_activity_and_validation_domain_fields(
    tmp_path: Path, mutation: str, expected: str
) -> None:
    path = _draft_storage_database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        connection.execute(mutation)
        connection.commit()
    finally:
        connection.close()
    report = audit_database(path)
    assert not report.clean
    assert any(expected in finding for finding in report.findings)


def test_backup_and_setup_refuse_governance_corruption_without_publication(tmp_path: Path) -> None:
    path = _draft_storage_database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        connection.execute("UPDATE draft_metadata SET fingerprint = zeroblob(32)")
        connection.commit()
    finally:
        connection.close()
    backup = tmp_path / "corrupt-copy.sqlite3"
    with pytest.raises(RuntimeError, match="copied database failed audit"):
        backup_database(path, backup)
    assert not backup.exists()
    destination = tmp_path / "corrupt-owner" / "vellis.db"
    with pytest.raises(RuntimeError, match="backup source failed audit"):
        initialize_from_backup(path, destination)
    assert not destination.exists()
    assert not destination.parent.exists()


@pytest.mark.parametrize("family", ["definition", "object"])
def test_audit_and_copy_refuse_draft_kind_conflicts_with_lineage_reservations(
    tmp_path: Path, family: str
) -> None:
    path = _database(tmp_path / family)
    if family == "definition":
        changed = change_draft(
            path,
            DraftChangeRequest(
                definition_upserts=(AnchorTypeDefinition("test.person", "Draft person"),)
            ),
        )
        mutation = "UPDATE draft_definition_entry SET kind = 'link' WHERE type_key = 'test.person'"
    else:
        _seed(path)
        changed = change_draft(path, DraftChangeRequest(object_removals=(PERSON,)))
        mutation = f"UPDATE draft_graph_object_patch SET kind = 'link' WHERE uuid = '{PERSON}'"
    assert changed.outcome.status is OperationStatus.ACCEPTED
    connection = connect_database(path)
    try:
        connection.execute(mutation)
        digest = computed_draft_fingerprint(connection)
        connection.execute(
            "UPDATE draft_metadata SET fingerprint = ? WHERE singleton = 1", (digest,)
        )
        connection.commit()
    finally:
        connection.close()

    assert not audit_database(path).clean
    backup = tmp_path / f"{family}-conflict.sqlite3"
    with pytest.raises(RuntimeError, match="copied database failed audit"):
        backup_database(path, backup)
    assert not backup.exists()
    destination = tmp_path / f"{family}-owner" / "vellis.db"
    with pytest.raises(RuntimeError, match="backup source failed audit"):
        initialize_from_backup(path, destination)
    assert not destination.exists()


def test_nonconforming_definition_draft_is_valid_storage_and_backup_content(tmp_path: Path) -> None:
    path = _database(tmp_path)
    staged = change_draft(
        path,
        DraftChangeRequest(
            definition_upserts=(
                AssociatedDataTypeDefinition(
                    "test.unreadyData",
                    "Intentionally incomplete data type",
                    (),
                    (
                        PropertyDefinition(
                            "text",
                            "Text with a deliberately mismatched allowed value",
                            ValueKind.TEXT,
                            allowed_values=(ScalarValue.integer(1),),
                        ),
                    ),
                    Cardinality(1),
                    Cardinality(0),
                ),
                LinkTypeDefinition(
                    "test.unreadyLink",
                    "Intentionally incomplete link type",
                    (),
                    (),
                    Cardinality(0),
                    Cardinality(0),
                ),
            ),
        ),
    )
    assert staged.outcome.status is OperationStatus.ACCEPTED
    validation = validate_state(path, ValidationRequest(ValidationScope.DRAFT, 100))
    assert validation.payload is not None
    assert not validation.payload.clean
    assert audit_database(path).clean
    backup = tmp_path / "nonconforming-draft.sqlite3"
    assert backup_database(path, backup) == backup
    assert audit_database(backup).clean


def test_invalid_activity_mode_fails_audit_and_backup_without_publication(tmp_path: Path) -> None:
    path = _database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute("UPDATE metadata_setting SET activity_mode = 'imagined'")
        connection.commit()
    finally:
        connection.close()
    report = audit_database(path)
    assert "activity detail mode is invalid" in report.findings
    backup = tmp_path / "invalid-setting.sqlite3"
    with pytest.raises(RuntimeError, match="copied database failed audit"):
        backup_database(path, backup)
    assert not backup.exists()


def test_audit_detects_validation_backing_corruption(tmp_path: Path) -> None:
    path = _database(tmp_path)
    validate_state(path, ValidationRequest(ValidationScope.CURRENT, 10))
    connection = sqlite3.connect(path)
    try:
        connection.execute("UPDATE validation_run SET total_findings = 1 WHERE scope = 'current'")
        connection.commit()
    finally:
        connection.close()
    assert not audit_database(path).clean


def test_online_backup_and_initialization_preserve_complete_database_only(
    tmp_path: Path, monkeypatch
) -> None:
    path = _database(tmp_path)
    _seed(path)
    change_draft(
        path, DraftChangeRequest(object_upserts=(AnchorUpsert(PERSON, display_name="Draft"),))
    )
    validate_state(path, ValidationRequest(ValidationScope.DRAFT, 10))
    configure_activity_mode(path, ActivityMode.VERBOSE)
    path.with_name("http-token").write_text("secret", encoding="utf-8")
    path.with_name("v1-import-report.json").write_text("sensitive", encoding="utf-8")
    source_activity = _activity_count(path)
    backup = tmp_path / "copies" / "backup.sqlite3"
    backup.parent.mkdir()

    copy_in_progress = threading.Event()
    writer_finished = threading.Event()

    def pause_online_copy(status: int, remaining: int, total: int) -> None:
        if not copy_in_progress.is_set():
            copy_in_progress.set()
            assert writer_finished.wait(5)

    monkeypatch.setattr(backup_module, "_backup_progress", pause_online_copy)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reads = pool.submit(lambda: [type_summary(path) for _ in range(8)])
        copied = pool.submit(backup_database, path, backup)
        assert copy_in_progress.wait(5)
        try:
            concurrent = apply_graph_change(
                path,
                GraphChangeRequest(1, (AnchorUpsert(PERSON, display_name="Concurrent"),)),
            )
            assert concurrent.resulting_revision == 2
        finally:
            writer_finished.set()
        reads.result()
        assert copied.result() == backup

    assert not tuple(backup.parent.glob(f".{backup.name}.*.tmp-*"))

    assert audit_database(path).clean
    assert audit_database(backup).clean
    assert _activity_count(path) == source_activity + 9
    assert not backup.with_name("http-token").exists()
    assert not backup.with_name("v1-import-report.json").exists()
    connection = connect_database(backup, read_only=True)
    try:
        assert connection.execute("SELECT count(*) FROM draft_metadata").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM validation_run").fetchone()[0] == 1
        lineage = connection.execute(
            "SELECT lineage_uuid, head_revision FROM metadata_setting WHERE singleton = 1"
        ).fetchone()
    finally:
        connection.close()
    restored = tmp_path / "restored" / "vellis.db"
    restored.parent.mkdir(mode=0o700)
    initialized = initialize_from_backup(backup, restored)
    assert initialized.database_path == str(restored)
    assert initialized.resulting_revision == int(lineage["head_revision"])
    assert not tuple(restored.parent.glob(f".{restored.name}.*.tmp-*"))
    restored_connection = connect_database(restored, read_only=True)
    try:
        restored_lineage = restored_connection.execute(
            "SELECT lineage_uuid, head_revision FROM metadata_setting WHERE singleton = 1"
        ).fetchone()
        assert tuple(restored_lineage) == tuple(lineage)
    finally:
        restored_connection.close()
    with pytest.raises(FileExistsError):
        backup_database(path, backup)


def test_backup_initialization_leaves_a_single_file_source_unchanged(tmp_path: Path) -> None:
    source = _database(tmp_path)
    _seed(source)
    backup = tmp_path / "single-file.sqlite3"
    assert backup_database(source, backup) == backup
    assert not Path(f"{backup}-wal").exists()
    assert not Path(f"{backup}-shm").exists()

    destination = tmp_path / "recovered" / "vellis.sqlite3"
    initialized = initialize_from_backup(backup, destination)
    assert initialized.resulting_revision == 1
    assert not Path(f"{backup}-wal").exists()
    assert not Path(f"{backup}-shm").exists()
    assert audit_database(destination).clean


@pytest.mark.parametrize("boundary", ["online-copy", "file-flush", "directory-flush", "link"])
def test_backup_failure_before_publication_leaves_no_destination(
    tmp_path: Path, monkeypatch, boundary: str
) -> None:
    source = _database(tmp_path)
    destination = tmp_path / f"{boundary}.sqlite3"
    if boundary == "online-copy":
        monkeypatch.setattr(
            backup_module,
            "_backup_progress",
            lambda status, remaining, total: (_ for _ in ()).throw(OSError("copy failed")),
        )
    elif boundary == "file-flush":
        monkeypatch.setattr(
            backup_module,
            "_flush_file",
            lambda path: (_ for _ in ()).throw(OSError("file flush failed")),
        )
    elif boundary == "directory-flush":
        monkeypatch.setattr(
            backup_module,
            "_flush_directory",
            lambda path: (_ for _ in ()).throw(OSError("directory flush failed")),
        )
    else:
        monkeypatch.setattr(
            backup_module.os,
            "link",
            lambda source_path, destination_path: (_ for _ in ()).throw(OSError("link failed")),
        )
    with pytest.raises(OSError):
        backup_database(source, destination)
    assert not destination.exists()


def test_backup_cleanup_failure_reports_rollback_or_indeterminate_publication(
    tmp_path: Path, monkeypatch
) -> None:
    source = _database(tmp_path)
    original_unlink = Path.unlink
    rolled_back = tmp_path / "rolled-back.sqlite3"
    failed_once = False

    def fail_first_temporary_cleanup(path: Path, *args, **kwargs):
        nonlocal failed_once
        if path.name.startswith(f".{rolled_back.name}.") and not failed_once:
            failed_once = True
            raise OSError("temporary cleanup failed")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_first_temporary_cleanup)
    with pytest.raises(OSError, match="rolled back after cleanup failure"):
        backup_database(source, rolled_back)
    assert not rolled_back.exists()

    indeterminate = tmp_path / "indeterminate.sqlite3"

    def fail_all_publication_cleanup(path: Path, *args, **kwargs):
        if path == indeterminate or path.name.startswith(f".{indeterminate.name}."):
            raise OSError("publication cleanup failed")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_all_publication_cleanup)
    with pytest.raises(OSError, match="destination is indeterminate"):
        backup_database(source, indeterminate)
    assert indeterminate.exists()


@pytest.mark.parametrize("operation", ["backup", "setup"])
def test_post_publication_directory_failure_reports_published_indeterminate_durability(
    tmp_path: Path, monkeypatch, operation: str
) -> None:
    source = _database(tmp_path / "source")
    destination = (
        tmp_path / "published.sqlite3"
        if operation == "backup"
        else tmp_path / "published-owner" / "vellis.db"
    )
    original_flush = backup_module._flush_directory
    flush_count = 0

    def fail_second_directory_flush(path: Path) -> None:
        nonlocal flush_count
        flush_count += 1
        if flush_count == 2:
            raise OSError("post-publication directory flush failed")
        original_flush(path)

    monkeypatch.setattr(backup_module, "_flush_directory", fail_second_directory_flush)
    with pytest.raises(
        BackupPublicationDurabilityError,
        match="destination is published, but directory durability could not be confirmed",
    ):
        if operation == "backup":
            backup_database(source, destination)
        else:
            initialize_from_backup(source, destination)
    assert destination.exists()
    assert audit_database(destination).clean


def test_corrupt_backup_source_publishes_no_initialization_destination(tmp_path: Path) -> None:
    source = _database(tmp_path)
    connection = sqlite3.connect(source)
    try:
        connection.execute("UPDATE canonical_record SET record_hash = zeroblob(32)")
        connection.commit()
    finally:
        connection.close()
    destination = tmp_path / "new-owner" / "vellis.db"
    with pytest.raises(RuntimeError, match="backup source failed audit"):
        initialize_from_backup(source, destination)
    assert not destination.exists()
    assert not destination.parent.exists()


def test_audit_rejects_a_misplaced_transition_even_with_a_consistent_chain(
    tmp_path: Path,
) -> None:
    """The hash chain attests that a label was not altered, not that it may appear there.

    Recomputing the chain over a relabelled record leaves it internally consistent, so
    only a placement rule can reject a lineage whose first record is not initialization.
    """
    path = _database(tmp_path)
    _seed(path)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        lineage = str(
            connection.execute(
                "SELECT lineage_uuid FROM metadata_setting WHERE singleton = 1"
            ).fetchone()[0]
        )
        connection.execute(
            "UPDATE canonical_record SET transition_kind = 'restore' WHERE revision = 0"
        )
        audit_module._prepare_audit_descriptors(connection, [])  # noqa: SLF001
        previous = bytes(32)
        for row in connection.execute("SELECT * FROM canonical_record ORDER BY revision"):
            header = audit_module._header_from_row(row, lineage)  # noqa: SLF001
            recomputed = audit_module._audit_record_hash(  # noqa: SLF001
                connection, previous, header, int(row["revision"])
            )
            connection.execute(
                "UPDATE canonical_record SET previous_hash = ?, record_hash = ? WHERE revision = ?",
                (previous, recomputed, int(row["revision"])),
            )
            previous = recomputed
        connection.commit()
    finally:
        connection.close()

    result = audit_database(path)

    assert not result.clean
    assert any("revision zero is not an initialization record" in each for each in result.findings)


def test_audit_rejects_a_database_missing_a_required_schema_object(tmp_path: Path) -> None:
    """A supported version does not prove the objects a public operation needs still exist.

    Backup publication trusts this audit, so a database whose schema identity matches but
    whose objects do not would otherwise be certified and published.
    """
    path = _database(tmp_path)
    _seed(path)
    assert audit_database(path).clean

    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP INDEX canonical_record_time_idx")
        connection.commit()
    finally:
        connection.close()

    result = audit_database(path)

    assert not result.clean
    assert any("canonical_record_time_idx" in each for each in result.findings)
