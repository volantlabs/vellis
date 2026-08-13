"""High-value evidence for bounded normalized NDJSON lifecycle operations."""

import hashlib
import io
import json
import os
from pathlib import Path

import pytest

import vellis.streaming as streaming
from vellis.canonical import Provenance
from vellis.changes import GraphChange, GraphChangeRequest, GraphChangeTarget
from vellis.definitions import AnchorTypeDefinition, GraphDefinitionSet
from vellis.governance import ActivateDefinitionDeltaRequest, DefinitionChange
from vellis.graph import Anchor
from vellis.history import RevisionSelection
from vellis.normalized import (
    graph_entry_digest,
    insert_definition_entry,
    insert_object_value,
    object_identity,
    proposal_entry_digest,
    recomputed_graph_summary,
    semantic_identity,
    semantic_row_summary,
)
from vellis.outcomes import ValidationRequest, ValidationRequestKind, ValidationScope
from vellis.query import (
    AnchorGroup,
    AnchorProjection,
    EvaluatedStateScope,
    GraphQuery,
    ReturnShape,
)
from vellis.store import CanonicalStore, StoreError
from vellis.streaming import export_ndjson, export_tail_ndjson, import_ndjson
from vellis.system import RTGSystem


def _source(path: Path, count: int = 25) -> RTGSystem:
    system = RTGSystem.open(path)
    assert system.initialize_fresh(
        GraphDefinitionSet(anchor_types=(AnchorTypeDefinition("person", "A person."),)),
        provenance=Provenance("owner"),
        initialization_summary="fresh",
    ).accepted
    assert system.apply_graph_change(
        GraphChange(
            anchor_upserts=tuple(
                Anchor(f"a-{index}", "person", f"Person {index}") for index in range(count)
            )
        ),
        provenance=Provenance("owner"),
    ).accepted
    return system


def _redigest(records: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for record in records[:-1]:
        digest.update((json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode())
    records[-1]["digest"] = digest.hexdigest()
    return "".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in records
    )


def _reseal_single_graph_tail(
    records: list[dict[str, object]], resulting_state_identity: str
) -> None:
    header = records[0]
    record = next(each for each in records if each.get("table") == "canonical_record")
    event = next(each for each in records if each.get("table") == "canonical_graph_event")
    definition = next(each for each in records if each.get("table") == "canonical_definition_event")
    assert isinstance(record["values"], dict)
    assert isinstance(event["values"], dict)
    assert isinstance(definition["values"], dict)
    value_id = event["values"]["object_value_id"]
    value_identity: str | None = None
    if value_id is not None:
        for each in records:
            values = each.get("values")
            if (
                each.get("table") == "object_value"
                and isinstance(values, dict)
                and values["id"] == value_id
            ):
                value_identity = str(values["content_identity"])
                break
        assert value_identity is not None
    empty = (0, "0" * 64)
    graph_summary = semantic_row_summary(
        [
            (
                int(event["values"]["occurrence"]),
                str(event["values"]["operation"]),
                str(event["values"]["object_kind"]),
                str(event["values"]["uuid"]),
                value_identity,
            )
        ]
    )
    event_identity = semantic_identity(
        (
            "canonicalEvents",
            str(record["values"]["record_kind"]),
            empty,
            graph_summary,
            empty,
            empty,
            (
                definition["values"]["active_definition_set_id"],
                definition["values"]["delta_disposition"],
                definition["values"]["proposed_definition_set_id"],
            ),
        )
    )
    record["values"]["event_identity"] = event_identity
    record["values"]["resulting_state_identity"] = resulting_state_identity
    record["values"]["content_identity"] = semantic_identity(
        ("canonicalRecordContent", event_identity, resulting_state_identity)
    )
    record["values"]["record_identity"] = semantic_identity(
        (
            header["sourceLedgerIdentity"],
            record["values"]["prior_record_identity"],
            int(record["values"]["established_revision"]),
            str(record["values"]["record_kind"]),
            str(record["values"]["recorded_at"]),
            str(record["values"]["initiator"]),
            record["values"]["source"],
            str(record["values"]["summary"]),
            record["values"]["content_identity"],
        )
    )
    header["throughRecordIdentity"] = record["values"]["record_identity"]
    header["throughStateIdentity"] = resulting_state_identity


def _reseal_source_records_from(system: RTGSystem, first_revision: int) -> None:
    """Reseal a deliberately forged source suffix for importer counterexamples."""
    connection = system.store._connection  # noqa: SLF001
    ledger = connection.execute("SELECT identity FROM ledger WHERE id = 0").fetchone()
    prior = connection.execute(
        "SELECT record_identity FROM canonical_record WHERE established_revision = ?",
        (first_revision - 1,),
    ).fetchone()
    assert ledger is not None and prior is not None
    prior_identity = str(prior[0])
    rows = connection.execute(
        "SELECT established_revision, record_kind, recorded_at, initiator, source, summary,"
        " resulting_state_identity FROM canonical_record WHERE established_revision >= ?"
        " ORDER BY established_revision",
        (first_revision,),
    ).fetchall()
    for revision, kind, recorded_at, initiator, source, summary, state_identity in rows:
        revision = int(revision)
        event_identity = system.store._record_event_identity_unlocked(  # noqa: SLF001
            revision, str(kind)
        )
        content_identity = semantic_identity(
            ("canonicalRecordContent", event_identity, str(state_identity))
        )
        record_identity = semantic_identity(
            (
                str(ledger[0]),
                prior_identity,
                revision,
                str(kind),
                str(recorded_at),
                str(initiator),
                source,
                str(summary),
                content_identity,
            )
        )
        connection.execute(
            "UPDATE canonical_record SET prior_record_identity = ?, event_identity = ?,"
            " content_identity = ?, record_identity = ? WHERE established_revision = ?",
            (
                prior_identity,
                event_identity,
                content_identity,
                record_identity,
                revision,
            ),
        )
        prior_identity = record_identity


def test_import_rebuilds_live_meaning_on_one_fresh_history_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_path = tmp_path / "source.sqlite3"
    target_path = tmp_path / "target.sqlite3"
    system = _source(source_path)
    query = GraphQuery(
        (AnchorGroup("people", "person"),),
        ReturnShape((AnchorProjection("person", "people"),)),
        maximum_rows=26,
    )
    expected_rows = system.query_graph(query).rows
    source_ledger_identity = system.store.ledger_identity()
    system.close()

    stream = io.StringIO()
    written = export_ndjson(source_path, stream, batch_size=3)
    stream.seek(0)
    read = import_ndjson(stream, target_path)
    restored = RTGSystem.open(target_path)
    try:
        assert read == written
        assert restored.store.canonical_record_count() == 1
        assert restored.store.canonical_summaries()[0][0] == written.revision
        assert restored.store.ledger_identity() != source_ledger_identity
        assert restored.store.activity_record_count() == 0
        assert restored.query_graph(query).rows == expected_rows
    finally:
        restored.close()


def test_changed_stream_establishes_no_destination(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite3"
    target_path = tmp_path / "target.sqlite3"
    system = _source(source_path, 2)
    system.close()
    stream = io.StringIO()
    export_ndjson(source_path, stream)
    changed = stream.getvalue().replace("Person 1", "Changed", 1)

    with pytest.raises(StoreError, match="digest"):
        import_ndjson(io.StringIO(changed), target_path)
    assert not target_path.exists()


def test_snapshot_rejects_invalid_bounds_order_and_concurrent_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_path = tmp_path / "source.sqlite3"
    system = _source(source_path, 2)
    system.close()

    with pytest.raises(ValueError, match="positive"):
        export_ndjson(source_path, io.StringIO(), batch_size=0)

    stream = io.StringIO()
    export_ndjson(source_path, stream)
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    first_row = next(index for index, record in enumerate(records) if record["kind"] == "row")
    second_table = next(
        index
        for index in range(first_row + 1, len(records))
        if records[index].get("table") != records[first_row].get("table")
    )
    records[first_row], records[second_table] = records[second_table], records[first_row]
    with pytest.raises(StoreError, match="canonical order"):
        import_ndjson(io.StringIO(_redigest(records)), tmp_path / "reordered.sqlite3")

    forged = [json.loads(line) for line in stream.getvalue().splitlines()]
    captured = next(record for record in forged if record.get("table") == "canonical_record")
    assert isinstance(captured["values"], dict)
    captured["values"]["prior_record_identity"] = "forged"
    with pytest.raises(StoreError, match="captured-record identity"):
        import_ndjson(io.StringIO(_redigest(forged)), tmp_path / "forged.sqlite3")

    forged_value = [json.loads(line) for line in stream.getvalue().splitlines()]
    value = next(record for record in forged_value if record.get("table") == "object_value")
    assert isinstance(value["values"], dict)
    value["values"]["display_name"] = "Forged"
    with pytest.raises(StoreError, match="semantic identity"):
        import_ndjson(io.StringIO(_redigest(forged_value)), tmp_path / "forged-value.sqlite3")

    target = tmp_path / "concurrent.sqlite3"
    real_link = os.link

    def establish_then_link(source: Path, destination: Path) -> None:
        Path(destination).write_text("somebody else's state", encoding="utf-8")
        real_link(source, destination)

    monkeypatch.setattr(os, "link", establish_then_link)
    with pytest.raises(StoreError, match="concurrently"):
        import_ndjson(io.StringIO(stream.getvalue()), target)
    assert target.read_text(encoding="utf-8") == "somebody else's state"


def test_snapshot_state_is_bound_to_the_exact_captured_record(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite3"
    system = _source(source_path, 2)
    system.close()
    stream = io.StringIO()
    export_ndjson(source_path, stream)
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    header = records[0]
    value = next(
        record
        for record in records
        if record.get("table") == "object_value"
        and isinstance(record.get("values"), dict)
        and record["values"]["uuid"] == "a-0"
    )
    assert isinstance(value["values"], dict)
    forged = Anchor("a-0", "person", "Forged")
    value["values"]["display_name"] = forged.display_name
    value["values"]["content_identity"] = object_identity(forged)
    graph_rows = sorted(
        (
            str(record["values"]["uuid"]),
            str(record["values"]["content_identity"]),
        )
        for record in records
        if record.get("table") == "object_value" and isinstance(record.get("values"), dict)
    )
    head = next(record for record in records if record.get("table") == "state_head")
    captured_record = next(
        record for record in records if record.get("table") == "canonical_record"
    )
    assert isinstance(head["values"], dict)
    assert isinstance(captured_record["values"], dict)
    header["stateIdentity"] = semantic_identity(
        (
            "normalizedState",
            int(head["values"]["revision"]),
            str(head["values"]["active_definition_set_id"]),
            head["values"]["proposed_definition_set_id"],
            semantic_row_summary(graph_rows),
            semantic_identity(("graphOverlay", "0" * 64, 0)),
        )
    )
    captured_record["values"]["resulting_state_identity"] = header["stateIdentity"]

    with pytest.raises(StoreError, match="captured record does not bind"):
        import_ndjson(io.StringIO(_redigest(records)), tmp_path / "forged-state.sqlite3")


def test_in_flight_proposal_survives_streaming_without_carrying_assessments(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.sqlite3"
    target_path = tmp_path / "target.sqlite3"
    system = _source(source_path, 1)
    assert system.set_definition_delta(
        DefinitionChange(anchor_type_upserts=(AnchorTypeDefinition("team", "A team."),)),
        provenance=Provenance("owner"),
    ).accepted
    assert system.apply_graph_change(
        GraphChangeRequest(
            GraphChangeTarget.DEFINITION_DELTA,
            GraphChange(anchor_upserts=(Anchor("t-1", "team", "Core"),)),
        ),
        provenance=Provenance("owner"),
    ).accepted
    source_proposal = system.store.proposal_state()
    system.close()

    stream = io.StringIO()
    export_ndjson(source_path, stream)
    stream.seek(0)
    import_ndjson(stream, target_path)
    restored = RTGSystem.open(target_path)
    try:
        proposal = restored.store.proposal_state()
        assert proposal.proposed_definition_identity == source_proposal.proposed_definition_identity
        assert proposal.graph_overlay_identity == source_proposal.graph_overlay_identity
        assert proposal.staged_anchor_count == 1
        assert proposal.assessment is None
    finally:
        restored.close()


def test_sql_replay_verification_and_restore_construct_no_graph(tmp_path: Path) -> None:
    path = tmp_path / "source.sqlite3"
    system = _source(path, 2)
    try:
        query = GraphQuery(
            (AnchorGroup("people", "person"),),
            ReturnShape((AnchorProjection("person", "people"),)),
            maximum_rows=3,
        )
        expected_rows = system.query_graph(query).rows
        assert system.store.verify_projection_from_ledger() == ()
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=(Anchor("a-0", "person", "Changed"),),
                anchor_removals=("a-1",),
            ),
            provenance=Provenance("owner"),
        ).accepted
        restored = system.restore_historical_state(
            RevisionSelection(1), provenance=Provenance("owner")
        )
        assert restored.accepted
        assert system.store.verify_projection_from_ledger() == ()
        assert system.query_graph(query).rows == expected_rows
    finally:
        system.close()


def test_replay_verifier_binds_transition_kind_to_normalized_events(tmp_path: Path) -> None:
    system = _source(tmp_path / "source.sqlite3", 1)
    try:
        system.store._connection.execute(  # noqa: SLF001
            "UPDATE canonical_record SET record_kind = 'definitionDeltaChange' WHERE ordinal = 1"
        )
        system.store._connection.commit()  # noqa: SLF001

        findings = system.store.verify_projection_from_ledger()

        assert findings
        assert any(
            "events" in finding.summary or "event families" in finding.summary
            for finding in findings
        )
    finally:
        system.close()


def test_stream_write_failure_is_observed(tmp_path: Path) -> None:
    system = _source(tmp_path / "source.sqlite3", 1)

    class FailingWriter(io.StringIO):
        def write(self, _value: str) -> int:
            raise OSError("disk full")

    try:
        before = system.store.activity_record_count()
        with pytest.raises(OSError, match="disk full"):
            system.export_snapshot(FailingWriter(), provenance=Provenance("owner"))
        assert system.store.activity_record_count() == before + 1
    finally:
        system.close()


def test_scale_snapshot_and_tail_import_keep_their_database_row_buffer_fixed(
    tmp_path: Path,
) -> None:
    system = _source(tmp_path / "source.sqlite3", 0)
    try:
        connection = system.store._connection  # noqa: SLF001
        connection.execute("BEGIN IMMEDIATE")
        connection.executemany(
            "INSERT INTO object_value"
            " (content_identity, uuid, object_kind, type_key, display_name)"
            " VALUES (?, ?, 'anchor', 'person', 'x')",
            (
                (object_identity(anchor), anchor.uuid)
                for anchor in (Anchor(f"large-{index}", "person", "x") for index in range(99_000))
            ),
        )
        connection.execute(
            "INSERT INTO graph_presence_interval"
            " (uuid, object_value_id, object_kind, type_key, source_uuid, target_uuid,"
            " valid_from_revision, valid_to_revision)"
            " SELECT uuid, id, object_kind, type_key, NULL, NULL, 0, NULL FROM object_value"
        )
        graph_count, graph_accumulator = recomputed_graph_summary(connection)
        connection.execute(
            "UPDATE state_head SET graph_entry_count = ?, graph_accumulator = ? WHERE id = 0",
            (graph_count, graph_accumulator),
        )
        system.store._seal_record_identity_unlocked(0)  # noqa: SLF001
        connection.execute("COMMIT")
        snapshot_path = tmp_path / "snapshot.ndjson"
        with snapshot_path.open("w", encoding="utf-8") as snapshot:
            captured = export_ndjson(tmp_path / "source.sqlite3", snapshot, batch_size=17)
        assert system.apply_graph_change(
            GraphChange(
                anchor_upserts=tuple(
                    Anchor(f"large-{index}", "person", "x") for index in range(99_000, 100_000)
                )
            ),
            provenance=Provenance("owner"),
        ).accepted
    finally:
        system.close()
    tail_path = tmp_path / "tail.ndjson"
    with tail_path.open("w", encoding="utf-8") as tail:
        metadata = export_tail_ndjson(
            tmp_path / "source.sqlite3",
            tail,
            after_revision=captured.revision,
            after_record_identity=captured.record_identity,
            batch_size=17,
        )
    with snapshot_path.open(encoding="utf-8") as snapshot, tail_path.open(encoding="utf-8") as tail:
        imported = import_ndjson(snapshot, tmp_path / "large.sqlite3", tail=tail)

    assert captured.row_buffer_bound == metadata.row_buffer_bound == 17
    assert imported.revision == metadata.through_revision
    store = CanonicalStore(tmp_path / "large.sqlite3")
    try:
        count = store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM current_graph_object"
        ).fetchone()
        assert count is not None and int(count[0]) == 100_000
    finally:
        store.close()


def test_streamed_tail_reconstructs_later_graph_and_activation_atomically(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.sqlite3"
    target_path = tmp_path / "target.sqlite3"
    system = _source(source_path, 1)
    snapshot = io.StringIO()
    captured = export_ndjson(source_path, snapshot, batch_size=2)

    assert system.set_definition_delta(
        DefinitionChange(anchor_type_upserts=(AnchorTypeDefinition("team", "A team."),)),
        provenance=Provenance("owner"),
    ).accepted
    assert system.apply_graph_change(
        GraphChangeRequest(
            GraphChangeTarget.DEFINITION_DELTA,
            GraphChange(anchor_upserts=(Anchor("t-1", "team", "Core"),)),
        ),
        provenance=Provenance("owner"),
    ).accepted
    assessment = system.check(
        ValidationRequest(
            ValidationRequestKind.ASSESS,
            ValidationScope.DEFINITION_DELTA,
            maximum_findings=10,
        )
    )
    assert assessment.accepted and assessment.assessment_id is not None
    assert system.activate_definition_delta(
        ActivateDefinitionDeltaRequest(assessment.assessment_id),
        provenance=Provenance("owner"),
    ).accepted
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("a-0", "person", "Changed"),)),
        provenance=Provenance("owner"),
    ).accepted
    final_revision = system.store.current_revision()
    system.close()

    tail = io.StringIO()
    written_tail = export_tail_ndjson(
        source_path,
        tail,
        after_revision=captured.revision,
        after_record_identity=captured.record_identity,
        batch_size=2,
    )
    snapshot.seek(0)
    tail.seek(0)
    rebuilt = import_ndjson(snapshot, target_path, tail=tail)
    target = RTGSystem.open(target_path)
    try:
        assert rebuilt.revision == written_tail.through_revision == final_revision
        query = GraphQuery(
            (AnchorGroup("teams", "team"),),
            ReturnShape((AnchorProjection("team", "teams"),)),
            maximum_rows=2,
            state_scope=EvaluatedStateScope.CURRENT,
        )
        assert len(target.query_graph(query).rows) == 1
        assert target.store.canonical_record_count() == 1
        assert target.store.verify_projection_from_ledger() == ()
    finally:
        target.close()


def test_streamed_tail_delete_does_not_resurrect_expired_membership(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite3"
    system = _source(source_path, 1)
    snapshot = io.StringIO()
    captured = export_ndjson(source_path, snapshot)
    assert system.apply_graph_change(
        GraphChange(anchor_removals=("a-0",)), provenance=Provenance("owner")
    ).accepted
    system.close()
    tail = io.StringIO()
    export_tail_ndjson(
        source_path,
        tail,
        after_revision=captured.revision,
        after_record_identity=captured.record_identity,
    )
    snapshot.seek(0)
    tail.seek(0)
    destination = tmp_path / "deleted.sqlite3"
    import_ndjson(snapshot, destination, tail=tail)
    store = CanonicalStore(destination)
    try:
        count = store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM current_graph_object"
        ).fetchone()
        assert count is not None and int(count[0]) == 0
        assert store.verify_projection_from_ledger() == ()
    finally:
        store.close()


@pytest.mark.parametrize(
    "mutation",
    (
        "foreign-base",
        "gap",
        "reorder",
        "wrong-kind",
        "event-value-mismatch",
        "absent-delete",
    ),
)
def test_invalid_streamed_tail_establishes_no_partial_destination(
    tmp_path: Path, mutation: str
) -> None:
    source_path = tmp_path / "source.sqlite3"
    system = _source(source_path, 1)
    snapshot = io.StringIO()
    captured = export_ndjson(source_path, snapshot)
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("later", "person", "Later"),)),
        provenance=Provenance("owner"),
    ).accepted
    system.close()
    tail = io.StringIO()
    export_tail_ndjson(
        source_path,
        tail,
        after_revision=captured.revision,
        after_record_identity=captured.record_identity,
    )
    records = [json.loads(line) for line in tail.getvalue().splitlines()]
    if mutation == "foreign-base":
        records[0]["precedingRecordIdentity"] = "another-ledger-record"
    elif mutation == "gap":
        record = next(each for each in records if each.get("table") == "canonical_record")
        assert isinstance(record["values"], dict)
        record["values"]["prior_revision"] = captured.revision - 1
    elif mutation == "wrong-kind":
        record = next(each for each in records if each.get("table") == "canonical_record")
        assert isinstance(record["values"], dict)
        record["values"]["record_kind"] = "definitionDeltaChange"
        _reseal_single_graph_tail(records, str(records[0]["throughStateIdentity"]))
    elif mutation == "event-value-mismatch":
        event = next(each for each in records if each.get("table") == "canonical_graph_event")
        assert isinstance(event["values"], dict)
        event["values"]["object_kind"] = "link"
        _reseal_single_graph_tail(records, str(records[0]["throughStateIdentity"]))
    elif mutation == "absent-delete":
        event = next(each for each in records if each.get("table") == "canonical_graph_event")
        assert isinstance(event["values"], dict)
        event["values"].update({"operation": "delete", "uuid": "absent", "object_value_id": None})
        snapshot_header = json.loads(snapshot.getvalue().splitlines()[0])
        _reseal_single_graph_tail(records, str(snapshot_header["stateIdentity"]))
    else:
        rows = [index for index, each in enumerate(records) if each.get("kind") == "tailRow"]
        records[rows[0]], records[rows[-1]] = records[rows[-1]], records[rows[0]]
    snapshot.seek(0)
    destination = tmp_path / f"{mutation}.sqlite3"
    with pytest.raises(StoreError):
        import_ndjson(snapshot, destination, tail=io.StringIO(_redigest(records)))
    assert not destination.exists()


def test_tail_rejects_a_proposal_identity_mismatch_hidden_by_later_discard(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "definition-source.sqlite3"
    system = _source(source_path, 0)
    snapshot = io.StringIO()
    captured = export_ndjson(source_path, snapshot)
    assert system.set_definition_delta(
        DefinitionChange(anchor_type_upserts=(AnchorTypeDefinition("team", "The claimed team."),)),
        provenance=Provenance("owner"),
    ).accepted
    assert system.discard_definition_delta(provenance=Provenance("owner")).accepted

    connection = system.store._connection  # noqa: SLF001
    substituted = insert_definition_entry(
        connection,
        GraphDefinitionSet(anchor_types=(AnchorTypeDefinition("team", "Different team meaning."),)),
    )
    connection.execute(
        "UPDATE canonical_definition_proposal_event SET value_set_id = ?"
        " WHERE established_revision = ? AND entity_kind = 'type' AND natural_key = 'team'",
        (substituted, captured.revision + 1),
    )
    _reseal_source_records_from(system, captured.revision + 1)
    tail = io.StringIO()
    export_tail_ndjson(
        source_path,
        tail,
        after_revision=captured.revision,
        after_record_identity=captured.record_identity,
    )
    system.close()

    snapshot.seek(0)
    tail.seek(0)
    destination = tmp_path / "definition-mismatch.sqlite3"
    with pytest.raises(StoreError, match="do not produce their claimed identity"):
        import_ndjson(snapshot, destination, tail=tail)
    assert not destination.exists()


def test_tail_rejects_an_invalid_active_revision_hidden_by_later_repair(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "graph-source.sqlite3"
    system = _source(source_path, 0)
    snapshot = io.StringIO()
    captured = export_ndjson(source_path, snapshot)
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("temporary", "person", "Temporary"),)),
        provenance=Provenance("owner"),
    ).accepted
    assert system.apply_graph_change(
        GraphChange(anchor_removals=("temporary",)), provenance=Provenance("owner")
    ).accepted

    connection = system.store._connection  # noqa: SLF001
    invalid = Anchor("temporary", "unknown-type", "Temporary")
    invalid_value_id = insert_object_value(connection, invalid)
    invalid_graph_accumulator = graph_entry_digest(invalid.uuid, object_identity(invalid))
    active = connection.execute(
        "SELECT active_definition_set_id FROM state_head WHERE id = 0"
    ).fetchone()
    assert active is not None
    invalid_state_identity = semantic_identity(
        (
            "normalizedState",
            captured.revision + 1,
            str(active[0]),
            None,
            (1, invalid_graph_accumulator),
            semantic_identity(("graphOverlay", "0" * 64, 0)),
        )
    )
    connection.execute(
        "UPDATE canonical_graph_event SET object_value_id = ? WHERE established_revision = ?",
        (invalid_value_id, captured.revision + 1),
    )
    connection.execute(
        "UPDATE canonical_record SET resulting_state_identity = ? WHERE established_revision = ?",
        (invalid_state_identity, captured.revision + 1),
    )
    _reseal_source_records_from(system, captured.revision + 1)
    tail = io.StringIO()
    export_tail_ndjson(
        source_path,
        tail,
        after_revision=captured.revision,
        after_record_identity=captured.record_identity,
    )
    system.close()

    snapshot.seek(0)
    tail.seek(0)
    destination = tmp_path / "invalid-intermediate.sqlite3"
    with pytest.raises(StoreError, match="unknown-type"):
        import_ndjson(snapshot, destination, tail=tail)
    assert not destination.exists()


def test_tail_rejects_activation_after_its_staged_base_became_stale(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "stale-activation-source.sqlite3"
    system = _source(source_path, 1)
    snapshot = io.StringIO()
    captured = export_ndjson(source_path, snapshot)
    proposed = Anchor("a-0", "person", "Proposed")
    staged = system.apply_graph_change(
        GraphChangeRequest(
            GraphChangeTarget.DEFINITION_DELTA,
            GraphChange(anchor_upserts=(proposed,)),
        ),
        provenance=Provenance("owner"),
    )
    assert staged.accepted and staged.resulting_revision is not None
    active = system.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("unrelated", "person", "Unrelated"),)),
        provenance=Provenance("owner"),
    )
    assert active.accepted and active.resulting_revision is not None
    assessment = system.check(
        ValidationRequest(
            ValidationRequestKind.ASSESS,
            ValidationScope.DEFINITION_DELTA,
            maximum_findings=10,
        )
    )
    assert assessment.accepted and assessment.conforms and assessment.assessment_id is not None
    activated = system.activate_definition_delta(
        ActivateDefinitionDeltaRequest(assessment.assessment_id),
        provenance=Provenance("owner"),
    )
    assert activated.accepted and activated.resulting_revision is not None

    connection = system.store._connection  # noqa: SLF001
    active_later = Anchor("a-0", "person", "Active later")
    active_later_id = insert_object_value(connection, active_later)
    connection.execute(
        "UPDATE canonical_graph_event SET uuid = ?, object_value_id = ?"
        " WHERE established_revision = ?",
        (active_later.uuid, active_later_id, active.resulting_revision),
    )
    connection.execute(
        "UPDATE graph_presence_interval SET valid_to_revision = ?"
        " WHERE uuid = 'unrelated' AND valid_to_revision IS NULL",
        (activated.resulting_revision,),
    )
    active_definition = connection.execute(
        "SELECT active_definition_set_id FROM state_head WHERE id = 0"
    ).fetchone()
    assert active_definition is not None
    empty_overlay = semantic_identity(("graphOverlay", "0" * 64, 0))
    staged_digest = proposal_entry_digest(
        proposed.uuid, "anchor", "upsert", object_identity(proposed)
    )
    staged_overlay = semantic_identity(("graphOverlay", staged_digest, 1))
    active_later_digest = graph_entry_digest(active_later.uuid, object_identity(active_later))
    proposed_digest = graph_entry_digest(proposed.uuid, object_identity(proposed))
    proposal_identity = str(active_definition[0])
    stale_state_identity = semantic_identity(
        (
            "normalizedState",
            active.resulting_revision,
            str(active_definition[0]),
            proposal_identity,
            (1, active_later_digest),
            staged_overlay,
        )
    )
    activated_state_identity = semantic_identity(
        (
            "normalizedState",
            activated.resulting_revision,
            str(active_definition[0]),
            None,
            (1, proposed_digest),
            empty_overlay,
        )
    )
    connection.execute(
        "UPDATE canonical_record SET resulting_state_identity = ? WHERE established_revision = ?",
        (stale_state_identity, active.resulting_revision),
    )
    connection.execute(
        "UPDATE canonical_record SET resulting_state_identity = ? WHERE established_revision = ?",
        (activated_state_identity, activated.resulting_revision),
    )
    connection.execute(
        "UPDATE state_head SET graph_entry_count = 1, graph_accumulator = ? WHERE id = 0",
        (proposed_digest,),
    )
    _reseal_source_records_from(system, active.resulting_revision)
    tail = io.StringIO()
    export_tail_ndjson(
        source_path,
        tail,
        after_revision=captured.revision,
        after_record_identity=captured.record_identity,
    )
    system.close()

    snapshot.seek(0)
    tail.seek(0)
    destination = tmp_path / "stale-activation.sqlite3"
    with pytest.raises(StoreError, match="stale active base"):
        import_ndjson(snapshot, destination, tail=tail)
    assert not destination.exists()


def test_tail_normalized_values_are_reverified_before_publication(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite3"
    system = _source(source_path, 1)
    snapshot = io.StringIO()
    captured = export_ndjson(source_path, snapshot)
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("later", "person", "Later"),)),
        provenance=Provenance("owner"),
    ).accepted
    system.close()
    tail = io.StringIO()
    export_tail_ndjson(
        source_path,
        tail,
        after_revision=captured.revision,
        after_record_identity=captured.record_identity,
    )
    records = [json.loads(line) for line in tail.getvalue().splitlines()]
    value = next(record for record in records if record.get("table") == "object_value")
    assert isinstance(value["values"], dict)
    value["values"]["display_name"] = "Forged"
    snapshot.seek(0)
    destination = tmp_path / "forged-tail.sqlite3"
    with pytest.raises(StoreError, match="semantic identity"):
        import_ndjson(snapshot, destination, tail=io.StringIO(_redigest(records)))
    assert not destination.exists()


def test_tail_applicability_rejects_active_equivalent_upsert_over_staged_delete(
    tmp_path: Path,
) -> None:
    system = _source(tmp_path / "source.sqlite3", 1)
    try:
        outcome = system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_removals=("a-0",)),
            ),
            provenance=Provenance("owner"),
        )
        assert outcome.accepted and outcome.resulting_revision is not None
        connection = system.store._connection  # noqa: SLF001
        connection.execute(
            "UPDATE canonical_proposal_event SET operation = 'upsert', object_value_id ="
            " (SELECT object_value_id FROM current_graph_object WHERE uuid = 'a-0')"
            " WHERE established_revision = ?",
            (outcome.resulting_revision,),
        )

        error = streaming._tail_event_error(  # noqa: SLF001
            connection, outcome.resulting_revision
        )

        assert error == "tail proposal upsert should unstage active-equivalent meaning"
    finally:
        system.close()


def test_tail_record_applicability_rejects_noop_discard_and_wrong_activation() -> None:
    empty = {
        "canonical_graph_event": 0,
        "canonical_proposal_event": 0,
        "canonical_definition_proposal_event": 0,
    }
    activation = dict(empty)
    activation["canonical_graph_event"] = 1

    assert not streaming._tail_record_is_compatible(  # noqa: SLF001
        "definitionDeltaChange", empty, (None, "absent", None), None
    )
    assert streaming._tail_record_is_compatible(  # noqa: SLF001
        "definitionDeltaChange", empty, (None, "absent", None), "proposal"
    )
    assert not streaming._tail_record_is_compatible(  # noqa: SLF001
        "definitionActivation", activation, ("other", "absent", None), "proposal"
    )
    assert streaming._tail_record_is_compatible(  # noqa: SLF001
        "definitionActivation", activation, ("proposal", "absent", None), "proposal"
    )


def test_activation_tail_events_must_equal_the_staged_overlay(tmp_path: Path) -> None:
    system = _source(tmp_path / "source.sqlite3", 1)
    try:
        assert system.set_definition_delta(
            DefinitionChange(anchor_type_upserts=(AnchorTypeDefinition("team", "A team."),)),
            provenance=Provenance("owner"),
        ).accepted
        assert system.apply_graph_change(
            GraphChangeRequest(
                GraphChangeTarget.DEFINITION_DELTA,
                GraphChange(anchor_upserts=(Anchor("t-1", "team", "Core"),)),
            ),
            provenance=Provenance("owner"),
        ).accepted
        connection = system.store._connection  # noqa: SLF001
        revision = system.store.current_revision() + 1
        prior = connection.execute(
            "SELECT record_identity FROM canonical_record ORDER BY ordinal DESC LIMIT 1"
        ).fetchone()
        assert prior is not None
        connection.execute(
            "INSERT INTO canonical_record VALUES (?, 999, 'definitionActivation', ?, 'test',"
            " NULL, 'test', ?, 'test-record', ?, 'test-content', 'test-state', 'test-event')",
            (revision, "2026-01-01T00:00:00+00:00", revision - 1, prior[0]),
        )
        staged = connection.execute(
            "SELECT operation, object_kind, uuid, object_value_id FROM proposal_entry"
        ).fetchone()
        assert staged is not None
        connection.execute(
            "INSERT INTO canonical_graph_event VALUES (?, 0, ?, ?, 'substituted', ?)",
            (revision, staged[0], staged[1], staged[3]),
        )
        assert not streaming._activation_events_match_overlay(  # noqa: SLF001
            connection, revision
        )
        connection.execute(
            "UPDATE canonical_graph_event SET uuid = ? WHERE established_revision = ?",
            (staged[2], revision),
        )
        assert streaming._activation_events_match_overlay(  # noqa: SLF001
            connection, revision
        )
    finally:
        system.close()


@pytest.mark.parametrize("stage", ("tail", "identity", "conformance", "fresh-lineage"))
def test_unexpected_import_failure_never_publishes_partial_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    source_path = tmp_path / "source.sqlite3"
    system = _source(source_path, 1)
    snapshot = io.StringIO()
    captured = export_ndjson(source_path, snapshot)
    assert system.apply_graph_change(
        GraphChange(anchor_upserts=(Anchor("later", "person", "Later"),)),
        provenance=Provenance("owner"),
    ).accepted
    system.close()
    tail = io.StringIO()
    export_tail_ndjson(
        source_path,
        tail,
        after_revision=captured.revision,
        after_record_identity=captured.record_identity,
    )
    target_name = {
        "tail": "_apply_tail_stream",
        "identity": "verify_normalized_identities",
        "conformance": "_verify_proposal_summaries",
        "fresh-lineage": "_establish_fresh_lineage",
    }[stage]

    def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(f"injected {stage} failure")

    monkeypatch.setattr(streaming, target_name, fail)
    snapshot.seek(0)
    tail.seek(0)
    destination = tmp_path / f"failed-{stage}.sqlite3"
    with pytest.raises(RuntimeError, match=f"injected {stage}"):
        import_ndjson(snapshot, destination, tail=tail)
    assert not destination.exists()
