from __future__ import annotations

import dataclasses
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from threading import Event
from typing import cast
from uuid import UUID, uuid4

import pytest

from components.rtg.change_validation import (
    DeterministicRtgChangeValidator,
    RtgChangeBatch,
    RtgChangeReference,
    RtgGraphAnchorWrite,
    RtgGraphChangeSet,
    RtgGraphDataObjectWrite,
    RtgGraphLinkWrite,
    RtgMigrationChangeSet,
    RtgMigrationRecordWrite,
    RtgSchemaChangeSet,
    RtgSchemaDefinitionWrite,
    RtgValidationFinding,
    RtgValidationOptions,
    RtgValidationReport,
)
from components.rtg.constraints import InMemoryRtgConstraints
from components.rtg.controller import (
    InProcessRtgController,
    RtgControllerApplyFailed,
    RtgControllerCutoverOptions,
    RtgControllerDiscoveryFailed,
    RtgControllerPreconditionFailed,
    RtgControllerReplayFailed,
    RtgControllerReplayOptions,
    RtgControllerRestoreOptions,
    RtgControllerSnapshotFailed,
    RtgControllerValidationFailed,
)
from components.rtg.graph import InMemoryRtgGraph, RtgAnchor
from components.rtg.migration import (
    InMemoryRtgMigration,
    RtgMigrationRecord,
    RtgMigrationSnapshot,
)
from components.rtg.query import RtgQueryAnchorBucket, RtgQuerySpec, SimpleRtgQueryEngine
from components.rtg.schema import (
    InMemoryRtgSchema,
    RtgAnchorSchemaPayload,
    RtgDataObjectSchemaPayload,
    RtgSchemaDefinition,
    RtgSchemaField,
)
from components.storage.json_file import LocalJsonFileStorage
from components.storage.sql import SqliteStorage


class FlakyLedgerSqlStorage:
    def __init__(self, delegate: object) -> None:
        self.delegate = delegate
        self.fail_ledger_inserts = True

    def execute(self, statement: str, parameters: object = ()) -> object:
        if self.fail_ledger_inserts and "insert into rtg_controller_ledger" in statement:
            raise RuntimeError("ledger unavailable")
        return self.delegate.execute(statement, parameters)  # type: ignore[attr-defined]

    def query(self, statement: str, parameters: object = ()) -> object:
        return self.delegate.query(statement, parameters)  # type: ignore[attr-defined]

    def transaction(self, operations: object) -> object:
        return self.delegate.transaction(operations)  # type: ignore[attr-defined]


class FailingDataPutGraph:
    def __init__(self, delegate: InMemoryRtgGraph) -> None:
        self.delegate = delegate
        self.fail_data_puts = True

    @classmethod
    def import_snapshot(cls, snapshot: object) -> FailingDataPutGraph:
        graph = cls(InMemoryRtgGraph.import_snapshot(snapshot))  # type: ignore[arg-type]
        graph.fail_data_puts = False
        return graph

    def export_snapshot(self) -> object:
        return self.delegate.export_snapshot()

    def put_anchor(self, anchor: object) -> object:
        return self.delegate.put_anchor(anchor)  # type: ignore[arg-type]

    def put_data_object(self, data_object: object, anchor_uuids: object) -> object:
        if self.fail_data_puts:
            raise RuntimeError("data write failed")
        return self.delegate.put_data_object(data_object, anchor_uuids)  # type: ignore[arg-type]

    def put_link(self, link: object) -> object:
        return self.delegate.put_link(link)  # type: ignore[arg-type]

    def __getattr__(self, name: str) -> object:
        return getattr(self.delegate, name)


class PostCutoverRejectingValidator(DeterministicRtgChangeValidator):
    def __init__(self) -> None:
        self.rejected = False

    def validate_graph_state(self, *args: object, **kwargs: object) -> RtgValidationReport:
        if self.rejected:
            return super().validate_graph_state(*args, **kwargs)  # type: ignore[arg-type]
        self.rejected = True
        return RtgValidationReport(
            accepted=False,
            findings=(
                RtgValidationFinding(
                    track="schema_object",
                    severity="blocking",
                    code="test.post_cutover_rejected",
                    message="post-cutover state rejected",
                ),
            ),
        )


class TrackingValidator(DeterministicRtgChangeValidator):
    def __init__(self, validate_graph_started: Event) -> None:
        self.validate_graph_started = validate_graph_started

    def validate_graph_state(
        self,
        graph: object,
        schema: object,
        constraints: object,
        migration: object | None,
        query: object,
        migration_ids: tuple[str, ...] | None = None,
        validation_options: RtgValidationOptions | None = None,
    ) -> RtgValidationReport:
        self.validate_graph_started.set()
        return super().validate_graph_state(
            graph,
            schema,
            constraints,
            migration,
            query,
            migration_ids,
            validation_options,
        )


class BlockingImportGraph:
    restore_started = Event()
    release_restore = Event()

    def __init__(self, delegate: InMemoryRtgGraph) -> None:
        self.delegate = delegate

    @classmethod
    def reset_block(cls) -> None:
        cls.restore_started = Event()
        cls.release_restore = Event()

    @classmethod
    def import_snapshot(cls, snapshot: object) -> BlockingImportGraph:
        cls.restore_started.set()
        if not cls.release_restore.wait(timeout=5):
            raise TimeoutError("timed out waiting to release snapshot import")
        return cls(InMemoryRtgGraph.import_snapshot(snapshot))  # type: ignore[arg-type]

    def export_snapshot(self) -> object:
        return self.delegate.export_snapshot()

    def put_anchor(self, anchor: object) -> object:
        return self.delegate.put_anchor(anchor)  # type: ignore[arg-type]

    def put_data_object(self, data_object: object, anchor_uuids: object) -> object:
        return self.delegate.put_data_object(data_object, anchor_uuids)  # type: ignore[arg-type]

    def put_link(self, link: object) -> object:
        return self.delegate.put_link(link)  # type: ignore[arg-type]

    def get_object(self, object_uuid: object) -> object:
        return self.delegate.get_object(object_uuid)  # type: ignore[arg-type]

    def __getattr__(self, name: str) -> object:
        return getattr(self.delegate, name)


class BlockingReplayQuerySqlStorage:
    def __init__(self, delegate: object) -> None:
        self.delegate = delegate
        self.query_started = Event()
        self.release_query = Event()
        self.block_replay_query = True

    def execute(self, statement: str, parameters: object = ()) -> object:
        return self.delegate.execute(statement, parameters)  # type: ignore[attr-defined]

    def query(self, statement: str, parameters: object = ()) -> object:
        if self.block_replay_query and "from rtg_controller_ledger" in statement:
            self.query_started.set()
            if not self.release_query.wait(timeout=5):
                raise TimeoutError("timed out waiting to release replay query")
        return self.delegate.query(statement, parameters)  # type: ignore[attr-defined]

    def transaction(self, operations: object) -> object:
        return self.delegate.transaction(operations)  # type: ignore[attr-defined]


def concrete_uuid(value: UUID | None) -> UUID:
    assert value is not None
    return value


def json_object(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def build_schema() -> InMemoryRtgSchema:
    schema = InMemoryRtgSchema.empty()
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="anchor",
            type_key="Person",
            description="Person.",
            payload=RtgAnchorSchemaPayload(required_data_types=("Profile",)),
        )
    )
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="data_object",
            type_key="Profile",
            description="Profile.",
            payload=RtgDataObjectSchemaPayload(
                properties={"name": RtgSchemaField(required=True, value_kinds=("string",))}
            ),
        )
    )
    return schema


def build_controller(tmp_path: Path) -> InProcessRtgController:
    return build_controller_with_sql(
        tmp_path,
        SqliteStorage.open(tmp_path / "ledger.sqlite"),
    )


def build_controller_with_sql(
    tmp_path: Path,
    sql_storage: object,
) -> InProcessRtgController:
    return InProcessRtgController.open(
        InMemoryRtgGraph.empty(),
        build_schema(),
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        DeterministicRtgChangeValidator(),
        SimpleRtgQueryEngine(),
        LocalJsonFileStorage.open(tmp_path / "json"),
        sql_storage,
    )


def build_controller_with_graph_and_validator(
    tmp_path: Path,
    graph: object,
    validator: object,
) -> InProcessRtgController:
    return InProcessRtgController.open(
        graph,
        build_schema(),
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        validator,
        SimpleRtgQueryEngine(),
        LocalJsonFileStorage.open(tmp_path / "json"),
        SqliteStorage.open(tmp_path / "ledger.sqlite"),
    )


def test_controller_reads_wait_while_restore_replaces_component_handles(
    tmp_path: Path,
) -> None:
    BlockingImportGraph.reset_block()
    validate_graph_started = Event()
    controller = build_controller_with_graph_and_validator(
        tmp_path,
        BlockingImportGraph(InMemoryRtgGraph.empty()),
        TrackingValidator(validate_graph_started),
    )
    snapshot = controller.export_system_snapshot()

    with ThreadPoolExecutor(max_workers=2) as executor:
        restore_future = executor.submit(
            controller.restore_from_snapshot,
            snapshot,
            RtgControllerRestoreOptions(ledger_mode="skip"),
        )
        assert BlockingImportGraph.restore_started.wait(timeout=2)

        read_future = executor.submit(controller.validate_graph)

        assert not validate_graph_started.wait(timeout=0.2)
        assert not read_future.done()

        BlockingImportGraph.release_restore.set()

        assert restore_future.result(timeout=2).status == "restore_applied"
        assert read_future.result(timeout=2).accepted is True
        assert validate_graph_started.is_set()


def test_restore_validates_combined_candidate_before_any_visible_replacement(
    tmp_path: Path,
) -> None:
    controller = build_controller(tmp_path)
    before = controller.export_system_snapshot()
    invalid_graph = InMemoryRtgGraph.empty()
    invalid_graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Person"))
    invalid_snapshot = dataclasses.replace(before, graph=invalid_graph.export_snapshot())

    with pytest.raises(RtgControllerSnapshotFailed) as error:
        controller.restore_from_snapshot(
            invalid_snapshot, RtgControllerRestoreOptions(ledger_mode="skip")
        )

    assert "violates controller invariants" in str(error.value)
    assert controller.export_system_snapshot() == before


def test_failed_recorded_restore_preserves_components_but_may_advance_audit_pointer(
    tmp_path: Path,
) -> None:
    controller = build_controller(tmp_path)
    before = controller.export_system_snapshot()
    duplicate = RtgMigrationRecord(migration_id="duplicate", description="Duplicate")
    invalid_snapshot = dataclasses.replace(
        before, migration=RtgMigrationSnapshot((duplicate, duplicate))
    )

    with pytest.raises(RtgControllerSnapshotFailed):
        controller.restore_from_snapshot(invalid_snapshot)

    after = controller.export_system_snapshot()
    assert after.graph == before.graph
    assert after.schema == before.schema
    assert after.constraints == before.constraints
    assert after.migration == before.migration
    assert after.last_ledger_position is not None
    assert after.last_ledger_position != before.last_ledger_position


def test_system_state_uses_typed_compact_counts_and_snapshot_paths(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)
    state = controller.get_system_state()

    assert state.live_schema_counts.total == 2
    assert state.live_schema_counts.anchor == 1
    assert state.live_object_counts.counts == ()
    assert state.non_live_candidate_counts.total == 0
    assert state.migration_counts_by_status.total == 0
    assert state.persisted_snapshot_paths == ()
    assert not hasattr(state, "last_transaction_timestamp")


def test_controller_writes_wait_while_replay_owns_system_state(tmp_path: Path) -> None:
    blocking_sql = BlockingReplayQuerySqlStorage(SqliteStorage.open(tmp_path / "ledger.sqlite"))
    controller = build_controller_with_sql(tmp_path, blocking_sql)
    start_snapshot = controller.export_system_snapshot()

    with ThreadPoolExecutor(max_workers=2) as executor:
        replay_future = executor.submit(
            controller.replay_ledger,
            RtgControllerReplayOptions(start_snapshot=start_snapshot),
        )
        assert blocking_sql.query_started.wait(timeout=2)

        write_future = executor.submit(
            controller.apply_live_graph_changes,
            RtgGraphChangeSet(
                anchor_writes=(
                    RtgGraphAnchorWrite(
                        ref=RtgChangeReference(local_ref="person"),
                        type="Person",
                    ),
                ),
                data_object_writes=(
                    RtgGraphDataObjectWrite(
                        ref=RtgChangeReference(local_ref="profile"),
                        type="Profile",
                        properties={"name": "Ada"},
                        anchor_refs=(RtgChangeReference(local_ref="person"),),
                    ),
                ),
            ),
        )

        with pytest.raises(TimeoutError):
            write_future.result(timeout=0.2)

        blocking_sql.release_query.set()

        assert replay_future.result(timeout=2).status == "replay_applied"
        assert write_future.result(timeout=2).status == "applied"


def test_live_graph_lane_resolves_local_refs_validates_applies_and_ledgers(
    tmp_path: Path,
) -> None:
    controller = build_controller(tmp_path)
    baseline = controller.export_system_snapshot()
    batch = RtgChangeBatch(
        graph_changes=RtgGraphChangeSet(
            anchor_writes=(
                RtgGraphAnchorWrite(
                    ref=RtgChangeReference(local_ref="person"),
                    type="Person",
                ),
            ),
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(local_ref="profile"),
                    type="Profile",
                    properties={"name": "Ada"},
                    anchor_refs=(RtgChangeReference(local_ref="person"),),
                ),
            ),
        )
    )

    result = controller.apply_live_graph_changes(batch.graph_changes)
    query_result = controller.execute_query(
        RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),))
    )

    assert result.status == "applied"
    assert result.ledger_position is not None
    assert result.applied_changes.graph_writes == 2
    assert len(query_result.bindings) == 1
    replay_controller = build_controller(tmp_path)
    ledger_records_seen = replay_controller.replay_ledger(
        RtgControllerReplayOptions(start_snapshot=baseline)
    ).details["ledger_records_seen"]
    assert isinstance(ledger_records_seen, int)
    assert ledger_records_seen >= 2


def test_validate_live_graph_changes_resolves_without_mutation_or_ledger(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "ledger.sqlite"
    controller = build_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))
    baseline = controller.export_system_snapshot()

    preview = controller.validate_live_graph_changes(
        RtgGraphChangeSet(
            anchor_writes=(
                RtgGraphAnchorWrite(
                    ref=RtgChangeReference(local_ref="person"),
                    type="Person",
                ),
            ),
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(local_ref="profile"),
                    type="Profile",
                    properties={"name": "Ada"},
                    anchor_refs=(RtgChangeReference(local_ref="person"),),
                ),
            ),
        )
    )

    assert preview.status == "validated"
    assert preview.mutation_state == "not_mutated"
    assert preview.accepted is True
    assert set(preview.generated_ids) == {"person", "profile"}
    assert (
        preview.resolved_graph_changes.anchor_writes[0].ref.resource_id
        == preview.generated_ids["person"]
    )
    assert controller.export_system_snapshot() == baseline
    assert (
        controller.execute_query(
            RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),))
        ).bindings
        == ()
    )
    rows = (
        SqliteStorage.open(ledger_path)
        .query("select count(*) as count from rtg_controller_ledger")
        .rows
    )
    assert rows[0]["count"] == 0


def test_validate_live_graph_changes_reports_findings_without_mutation(
    tmp_path: Path,
) -> None:
    controller = build_controller(tmp_path)
    baseline = controller.export_system_snapshot()

    preview = controller.validate_live_graph_changes(
        RtgGraphChangeSet(
            link_writes=(
                RtgGraphLinkWrite(
                    ref=RtgChangeReference(local_ref="bad-link"),
                    type="supports",
                    source_ref=RtgChangeReference(resource_id=uuid4()),
                    target_ref=RtgChangeReference(resource_id=uuid4()),
                ),
            )
        )
    )

    assert preview.accepted is False
    assert "schema_object.reference_missing" in {
        finding.code for finding in preview.validation_report.findings
    }
    assert "graph_changes.link_writes[0].source_ref" in " ".join(
        finding.message for finding in preview.validation_report.findings
    )
    assert controller.export_system_snapshot() == baseline


def test_live_graph_lane_rejects_invalid_batch_without_mutating(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.sqlite"
    controller = build_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))
    batch = RtgChangeBatch(
        graph_changes=RtgGraphChangeSet(
            anchor_writes=(RtgGraphAnchorWrite(RtgChangeReference(local_ref="person"), "Person"),),
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(local_ref="profile"),
                    type="Profile",
                    properties={"extra": "invalid"},
                    anchor_refs=(RtgChangeReference(local_ref="person"),),
                ),
            ),
        )
    )

    with pytest.raises(RtgControllerValidationFailed):
        controller.apply_live_graph_changes(batch.graph_changes)

    assert (
        controller.execute_query(
            RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),))
        ).bindings
        == ()
    )
    rows = (
        SqliteStorage.open(ledger_path)
        .query(
            """
        select operation_name, record_kind, payload_json
        from rtg_controller_ledger
        where operation_name = ?
        order by ledger_position
        """,
            ("apply_live_graph_changes",),
        )
        .rows
    )
    assert [(row["operation_name"], row["record_kind"]) for row in rows] == [
        ("apply_live_graph_changes", "request"),
        ("apply_live_graph_changes", "error"),
    ]


def test_controller_cutover_flips_schema_live_status_and_prunes(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)
    old = controller.get_schema_pack(("Person",)).schema_pack.anchor_schemas[0]
    replacement = RtgSchemaDefinition(
        uuid=uuid4(),
        kind="anchor",
        type_key="Person",
        description="Expanded person.",
        payload=RtgAnchorSchemaPayload(required_data_types=("Profile",)),
        system={"live": False},
    )
    controller.stage_knowledge_changes(
        RtgChangeBatch(
            schema_changes=RtgSchemaChangeSet(
                definition_writes=(
                    RtgSchemaDefinitionWrite(
                        ref=RtgChangeReference(resource_id=concrete_uuid(replacement.uuid)),
                        definition=replacement,
                    ),
                )
            ),
            migration_changes=RtgMigrationChangeSet(
                migration_writes=(
                    RtgMigrationRecordWrite(
                        ref=RtgChangeReference(resource_id="person-schema-v2"),
                        migration=RtgMigrationRecord(
                            migration_id="person-schema-v2",
                            description="Replace Person schema.",
                            status="ready",
                            schema_make_live=(concrete_uuid(replacement.uuid),),
                            schema_make_non_live=(concrete_uuid(old.uuid),),
                        ),
                    ),
                )
            ),
        ),
        validation_mode="skip",
    )

    result = controller.apply_migration_cutover("person-schema-v2")
    discovery = controller.discover_anchor_types()

    assert result.status == "cutover_applied"
    assert result.ledger_position is not None
    assert discovery.anchor_types[0].description == "Expanded person."


def test_cutover_rejects_schema_candidate_that_invalidates_live_graph_data(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "ledger.sqlite"
    controller = build_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))
    controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            anchor_writes=(RtgGraphAnchorWrite(RtgChangeReference(local_ref="person"), "Person"),),
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(local_ref="profile"),
                    type="Profile",
                    properties={"name": "Ada"},
                    anchor_refs=(RtgChangeReference(local_ref="person"),),
                ),
            ),
        )
    )
    old = controller.get_schema_pack(("Person",)).schema_pack.anchor_schemas[0]
    replacement = RtgSchemaDefinition(
        uuid=uuid4(),
        kind="anchor",
        type_key="Person",
        description="Person now requires badge data.",
        payload=RtgAnchorSchemaPayload(required_data_types=("Profile", "Badge")),
        system={"live": False},
    )
    controller.stage_knowledge_changes(
        RtgChangeBatch(
            schema_changes=RtgSchemaChangeSet(
                definition_writes=(
                    RtgSchemaDefinitionWrite(
                        ref=RtgChangeReference(resource_id=concrete_uuid(replacement.uuid)),
                        definition=replacement,
                    ),
                )
            ),
            migration_changes=RtgMigrationChangeSet(
                migration_writes=(
                    RtgMigrationRecordWrite(
                        ref=RtgChangeReference(resource_id="person-badge-schema"),
                        migration=RtgMigrationRecord(
                            migration_id="person-badge-schema",
                            description="Require badge data.",
                            status="ready",
                            schema_make_live=(concrete_uuid(replacement.uuid),),
                            schema_make_non_live=(concrete_uuid(old.uuid),),
                        ),
                    ),
                )
            ),
        ),
        validation_mode="skip",
    )

    projected = controller.validate_graph(migration_ids=("person-badge-schema",))

    assert projected.accepted is False
    assert {finding.code for finding in projected.findings} >= {
        "schema_object.missing_required_associated_data",
        "migration_cutover.post_state_invalid",
    }

    with pytest.raises(RtgControllerValidationFailed) as error:
        controller.apply_migration_cutover("person-badge-schema")
    assert error.value.diagnostic["code"] == "controller.cutover.validation_failed"
    assert error.value.diagnostic["mutation_state"] == "live_state_preserved"

    assert controller.discover_anchor_types().anchor_types[0].description == "Person."
    rows = (
        SqliteStorage.open(ledger_path)
        .query(
            """
        select operation_name, record_kind, payload_json
        from rtg_controller_ledger
        where operation_name = ?
        order by ledger_position
        """,
            ("apply_migration_cutover",),
        )
        .rows
    )
    assert [(row["operation_name"], row["record_kind"]) for row in rows] == [
        ("apply_migration_cutover", "request"),
        ("apply_migration_cutover", "response"),
    ]
    response_payload = json.loads(str(rows[1]["payload_json"]))
    assert response_payload["status"] == "cutover_failed"


def test_concrete_controller_has_no_generic_change_batch_bypass(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)

    assert not hasattr(controller, "apply_change_batch")
    assert not hasattr(controller, "import_schema_constraint_pack")


def test_controller_rejects_unsupported_cutover_options(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)

    with pytest.raises(RtgControllerPreconditionFailed, match="validation_mode"):
        controller.apply_migration_cutover(
            "missing",
            RtgControllerCutoverOptions(validation_mode="relaxed"),
        )

    with pytest.raises(RtgControllerPreconditionFailed, match="failure_restore"):
        controller.apply_migration_cutover(
            "missing",
            RtgControllerCutoverOptions(failure_restore="keep_partial_state"),
        )


def test_controller_maps_cutover_precondition_failures(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)
    missing_schema_uuid = uuid4()

    with pytest.raises(RtgControllerPreconditionFailed, match="missing"):
        controller.apply_migration_cutover("missing")

    controller.stage_knowledge_changes(
        RtgChangeBatch(
            migration_changes=RtgMigrationChangeSet(
                migration_writes=(
                    RtgMigrationRecordWrite(
                        ref=RtgChangeReference(resource_id="missing-schema-candidate"),
                        migration=RtgMigrationRecord(
                            migration_id="missing-schema-candidate",
                            description="References a missing schema candidate.",
                            status="ready",
                            schema_make_live=(missing_schema_uuid,),
                        ),
                    ),
                )
            )
        ),
        validation_mode="skip",
    )

    with pytest.raises(RtgControllerPreconditionFailed, match=str(missing_schema_uuid)):
        controller.apply_migration_cutover("missing-schema-candidate")


def test_controller_rejects_unsupported_discovery_and_restore_options(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)
    snapshot = controller.export_system_snapshot()

    with pytest.raises(RtgControllerDiscoveryFailed, match="limit"):
        controller.discover_anchor_types(type("Options", (), {"limit": 0})())

    with pytest.raises(RtgControllerSnapshotFailed, match="ledger_mode"):
        controller.restore_from_snapshot(
            snapshot,
            RtgControllerRestoreOptions(ledger_mode="silent"),
        )


def test_live_graph_lane_rejects_non_live_candidate_creation(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)

    with pytest.raises(RtgControllerPreconditionFailed):
        controller.apply_live_graph_changes(
            RtgGraphChangeSet(
                anchor_writes=(
                    RtgGraphAnchorWrite(
                        ref=RtgChangeReference(local_ref="person"),
                        type="Person",
                        system={"live": False},
                    ),
                )
            )
        )


def test_knowledge_staging_rejects_unscoped_schema_candidate(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)
    candidate = RtgSchemaDefinition(
        uuid=uuid4(),
        kind="anchor",
        type_key="Project",
        description="Project.",
        payload=RtgAnchorSchemaPayload(),
        system={"live": False},
    )

    with pytest.raises(RtgControllerPreconditionFailed):
        controller.stage_knowledge_changes(
            RtgChangeBatch(
                schema_changes=RtgSchemaChangeSet(
                    definition_writes=(
                        RtgSchemaDefinitionWrite(
                            ref=RtgChangeReference(resource_id=concrete_uuid(candidate.uuid)),
                            definition=candidate,
                        ),
                    )
                )
            )
        )


def test_knowledge_staging_rejects_direct_live_schema_write(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)
    candidate_uuid = uuid4()
    candidate = RtgSchemaDefinition(
        uuid=candidate_uuid,
        kind="anchor",
        type_key="Project",
        description="Project.",
        payload=RtgAnchorSchemaPayload(),
    )

    with pytest.raises(RtgControllerPreconditionFailed):
        controller.stage_knowledge_changes(
            RtgChangeBatch(
                schema_changes=RtgSchemaChangeSet(
                    definition_writes=(
                        RtgSchemaDefinitionWrite(
                            ref=RtgChangeReference(resource_id=candidate_uuid),
                            definition=candidate,
                        ),
                    )
                ),
                migration_changes=RtgMigrationChangeSet(
                    migration_writes=(
                        RtgMigrationRecordWrite(
                            ref=RtgChangeReference(resource_id="project-schema"),
                            migration=RtgMigrationRecord(
                                migration_id="project-schema",
                                description="Stage project schema.",
                                schema_make_live=(candidate_uuid,),
                            ),
                        ),
                    )
                ),
            )
        )


def test_knowledge_staging_accepts_non_live_graph_candidate_when_migration_scoped(
    tmp_path: Path,
) -> None:
    controller = build_controller(tmp_path)
    person_uuid = uuid4()
    profile_uuid = uuid4()
    controller.stage_knowledge_changes(
        RtgChangeBatch(
            graph_changes=RtgGraphChangeSet(
                anchor_writes=(
                    RtgGraphAnchorWrite(
                        ref=RtgChangeReference(resource_id=person_uuid),
                        type="Person",
                        system={"live": False},
                    ),
                ),
                data_object_writes=(
                    RtgGraphDataObjectWrite(
                        ref=RtgChangeReference(resource_id=profile_uuid),
                        type="Profile",
                        properties={"name": "Grace"},
                        system={"live": False},
                        anchor_refs=(RtgChangeReference(resource_id=person_uuid),),
                    ),
                ),
            ),
            migration_changes=RtgMigrationChangeSet(
                migration_writes=(
                    RtgMigrationRecordWrite(
                        ref=RtgChangeReference(resource_id="person-candidate"),
                        migration=RtgMigrationRecord(
                            migration_id="person-candidate",
                            description="Stage non-live person candidate.",
                            status="ready",
                            graph_make_live=(person_uuid, profile_uuid),
                        ),
                    ),
                )
            ),
        )
    )

    assert (
        controller.execute_query(
            RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),))
        ).bindings
        == ()
    )
    controller.apply_migration_cutover("person-candidate")
    assert (
        len(
            controller.execute_query(
                RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),))
            ).bindings
        )
        == 1
    )


def test_strict_knowledge_staging_rejects_invalid_cutover_projection(
    tmp_path: Path,
) -> None:
    controller = build_controller(tmp_path)
    schema_pack = controller.get_schema_pack(("Person",)).schema_pack
    old_profile = schema_pack.associated_data_object_schemas[0]
    replacement_profile = RtgSchemaDefinition(
        uuid=uuid4(),
        kind="data_object",
        type_key="Profile",
        description="Profile with numeric age.",
        payload=RtgDataObjectSchemaPayload(
            properties={"age": RtgSchemaField(required=True, value_kinds=("integer",))}
        ),
        system={"live": False},
    )
    person_uuid = uuid4()
    profile_uuid = uuid4()

    with pytest.raises(RtgControllerValidationFailed) as error:
        controller.stage_knowledge_changes(
            RtgChangeBatch(
                schema_changes=RtgSchemaChangeSet(
                    definition_writes=(
                        RtgSchemaDefinitionWrite(
                            ref=RtgChangeReference(
                                resource_id=concrete_uuid(replacement_profile.uuid)
                            ),
                            definition=replacement_profile,
                        ),
                    )
                ),
                graph_changes=RtgGraphChangeSet(
                    anchor_writes=(
                        RtgGraphAnchorWrite(
                            ref=RtgChangeReference(resource_id=person_uuid),
                            type="Person",
                            system={"live": False},
                        ),
                    ),
                    data_object_writes=(
                        RtgGraphDataObjectWrite(
                            ref=RtgChangeReference(resource_id=profile_uuid),
                            type="Profile",
                            properties={"age": "not an integer"},
                            system={"live": False},
                            anchor_refs=(RtgChangeReference(resource_id=person_uuid),),
                        ),
                    ),
                ),
                migration_changes=RtgMigrationChangeSet(
                    migration_writes=(
                        RtgMigrationRecordWrite(
                            ref=RtgChangeReference(resource_id="profile-schema-v2"),
                            migration=RtgMigrationRecord(
                                migration_id="profile-schema-v2",
                                description="Replace Profile and publish candidate data.",
                                status="ready",
                                schema_make_live=(concrete_uuid(replacement_profile.uuid),),
                                schema_make_non_live=(concrete_uuid(old_profile.uuid),),
                                graph_make_live=(person_uuid, profile_uuid),
                            ),
                        ),
                    )
                ),
            )
        )

    assert error.value.validation_report is not None
    assert {finding.code for finding in error.value.validation_report.findings} >= {
        "schema_object.property_kind_mismatch",
        "migration_cutover.post_state_invalid",
    }
    assert controller.list_migrations().migrations == ()


def test_ledger_failures_are_queued_and_flushed(tmp_path: Path) -> None:
    flaky_sql = FlakyLedgerSqlStorage(SqliteStorage.open(tmp_path / "ledger.sqlite"))
    controller = build_controller_with_sql(tmp_path, flaky_sql)

    result = controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            anchor_writes=(
                RtgGraphAnchorWrite(
                    ref=RtgChangeReference(local_ref="person"),
                    type="Person",
                ),
            ),
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(local_ref="profile"),
                    type="Profile",
                    properties={"name": "Ada"},
                    anchor_refs=(RtgChangeReference(local_ref="person"),),
                ),
            ),
        )
    )

    flaky_sql.fail_ledger_inserts = False
    result = controller.flush_ledger_failures()

    assert result.details["flushed"] == 2
    assert result.details["remaining"] == 0


def test_ledger_failure_degrades_result_and_flush_loads_json_queue(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.sqlite"
    flaky_sql = FlakyLedgerSqlStorage(SqliteStorage.open(ledger_path))
    controller = build_controller_with_sql(tmp_path, flaky_sql)

    applied = controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            anchor_writes=(
                RtgGraphAnchorWrite(
                    ref=RtgChangeReference(local_ref="person"),
                    type="Person",
                ),
            ),
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(local_ref="profile"),
                    type="Profile",
                    properties={"name": "Ada"},
                    anchor_refs=(RtgChangeReference(local_ref="person"),),
                ),
            ),
        )
    )

    reloaded = build_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))
    flush = reloaded.flush_ledger_failures()

    assert applied.details["audit_degraded"] is True
    assert applied.details["ledger_failure_count"] == 2
    assert flush.details["flushed"] == 2
    assert flush.details["remaining"] == 0
    assert flush.ledger_position is not None


def test_replay_rejects_non_empty_state_without_explicit_snapshot(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)

    with pytest.raises(RtgControllerReplayFailed) as error:
        controller.replay_ledger()
    assert error.value.diagnostic["code"] == "controller.replay.non_empty_state"
    assert error.value.diagnostic["guide_topics"] == ["workflow_patterns", "recovery_and_replay"]
    assert error.value.diagnostic["mutation_state"] == "not_mutated"


def test_replay_accepts_persisted_start_snapshot_path(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.sqlite"
    controller = build_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))
    controller.persist_system_snapshot("snapshots/start.json")
    controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            anchor_writes=(RtgGraphAnchorWrite(RtgChangeReference(local_ref="ada"), "Person"),),
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(local_ref="ada-profile"),
                    type="Profile",
                    properties={"name": "Ada"},
                    anchor_refs=(RtgChangeReference(local_ref="ada"),),
                ),
            ),
        )
    )
    replay_controller = build_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))

    replay = replay_controller.replay_ledger(
        RtgControllerReplayOptions(start_snapshot_path="snapshots/start.json")
    )

    assert replay.details["mutating_requests_replayed"] == 1
    replay_window = json_object(replay.details["replay_window"])
    assert replay_window["start_source"] == "start_snapshot_path"
    assert (
        replay_window["effective_after_ledger_position"] == replay_window["start_ledger_position"]
    )
    assert "snapshot ledger position" in str(replay_window["note"])
    assert (
        len(
            replay_controller.execute_query(
                RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),))
            ).bindings
        )
        == 1
    )


def test_replay_rejects_ambiguous_start_snapshot_options(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)
    snapshot = controller.export_system_snapshot()

    with pytest.raises(RtgControllerReplayFailed, match="not both") as error:
        controller.replay_ledger(
            RtgControllerReplayOptions(
                start_snapshot=snapshot,
                start_snapshot_path="snapshots/start.json",
            )
        )
    assert error.value.diagnostic["code"] == "controller.replay.ambiguous_start"


def test_verify_replay_from_ledger_uses_scratch_state_and_preserves_current_state(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "ledger.sqlite"
    controller = build_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))
    baseline = controller.export_system_snapshot()
    controller.persist_system_snapshot("snapshots/start.json")
    controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            anchor_writes=(RtgGraphAnchorWrite(RtgChangeReference(local_ref="ada"), "Person"),),
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(local_ref="ada-profile"),
                    type="Profile",
                    properties={"name": "Ada"},
                    anchor_refs=(RtgChangeReference(local_ref="ada"),),
                ),
            ),
        )
    )
    current = controller.export_system_snapshot()

    verified = controller.verify_replay_from_ledger(
        RtgControllerReplayOptions(start_snapshot_path="snapshots/start.json")
    )

    assert verified.status == "replay_verified"
    assert verified.mutating_requests_replayed == 1
    assert verified.replay_window["start_source"] == "start_snapshot_path"
    assert (
        verified.replay_window["effective_after_ledger_position"]
        == verified.replay_window["start_ledger_position"]
    )
    assert verified.validation_report.accepted is True
    graph_diffs = json_object(verified.count_diffs["graph_counts"])
    anchor_diffs = json_object(graph_diffs["anchor"])
    assert anchor_diffs["Person"] == 1
    assert controller.export_system_snapshot() == current
    assert baseline.schema.definitions


def test_replay_reconstructs_cutover_from_ledgered_request_after_pruning(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "ledger.sqlite"
    controller = build_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))
    baseline = controller.export_system_snapshot()
    old = controller.get_schema_pack(("Person",)).schema_pack.anchor_schemas[0]
    replacement = RtgSchemaDefinition(
        uuid=uuid4(),
        kind="anchor",
        type_key="Person",
        description="Expanded person.",
        payload=RtgAnchorSchemaPayload(required_data_types=("Profile",)),
        system={"live": False},
    )
    staged = controller.stage_knowledge_changes(
        RtgChangeBatch(
            schema_changes=RtgSchemaChangeSet(
                definition_writes=(
                    RtgSchemaDefinitionWrite(
                        ref=RtgChangeReference(resource_id=concrete_uuid(replacement.uuid)),
                        definition=replacement,
                    ),
                )
            ),
            migration_changes=RtgMigrationChangeSet(
                migration_writes=(
                    RtgMigrationRecordWrite(
                        ref=RtgChangeReference(resource_id="person-schema-v2"),
                        migration=RtgMigrationRecord(
                            migration_id="person-schema-v2",
                            description="Replace Person schema.",
                            status="ready",
                            schema_make_live=(concrete_uuid(replacement.uuid),),
                            schema_make_non_live=(concrete_uuid(old.uuid),),
                        ),
                    ),
                )
            ),
        ),
        validation_mode="skip",
    )
    assert staged.details["operation_effect"] == "staged_candidates_written"
    assert staged.details["requires_cutover"] is True
    candidate_counts = json_object(staged.details["candidate_counts"])
    assert candidate_counts["schema"] == 1
    controller.apply_migration_cutover("person-schema-v2")
    assert controller.list_migrations().migrations == ()

    replay_controller = build_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))
    replay = replay_controller.replay_ledger(RtgControllerReplayOptions(start_snapshot=baseline))

    assert replay.details["mutating_requests_replayed"] == 2
    assert replay_controller.list_migrations().migrations == ()
    assert (
        replay_controller.discover_anchor_types().anchor_types[0].description == "Expanded person."
    )


def test_replay_decodes_ledgered_schema_fields_with_null_items(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.sqlite"
    controller = build_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))
    baseline = controller.export_system_snapshot()
    old_profile = controller.get_schema_pack(
        ("Person",)
    ).schema_pack.associated_data_object_schemas[0]
    replacement = RtgSchemaDefinition(
        uuid=uuid4(),
        kind="data_object",
        type_key="Profile",
        description="Profile with contact preference.",
        payload=RtgDataObjectSchemaPayload(
            properties={
                "name": RtgSchemaField(required=True, value_kinds=("string",)),
                "preferred_contact": RtgSchemaField(required=False, value_kinds=("string",)),
            }
        ),
        system={"live": False},
    )
    controller.stage_knowledge_changes(
        RtgChangeBatch(
            schema_changes=RtgSchemaChangeSet(
                definition_writes=(
                    RtgSchemaDefinitionWrite(
                        ref=RtgChangeReference(resource_id=concrete_uuid(replacement.uuid)),
                        definition=replacement,
                    ),
                )
            ),
            migration_changes=RtgMigrationChangeSet(
                migration_writes=(
                    RtgMigrationRecordWrite(
                        ref=RtgChangeReference(resource_id="profile-schema-v2"),
                        migration=RtgMigrationRecord(
                            migration_id="profile-schema-v2",
                            description="Replace Profile data object schema.",
                            status="ready",
                            schema_make_live=(concrete_uuid(replacement.uuid),),
                            schema_make_non_live=(concrete_uuid(old_profile.uuid),),
                        ),
                    ),
                )
            ),
        )
    )
    controller.apply_migration_cutover("profile-schema-v2")

    replay_controller = build_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))
    replay = replay_controller.replay_ledger(RtgControllerReplayOptions(start_snapshot=baseline))
    replayed_profile = replay_controller.get_schema_pack(
        ("Person",)
    ).schema_pack.associated_data_object_schemas[0]
    assert isinstance(replayed_profile.payload, RtgDataObjectSchemaPayload)
    replayed_properties = replayed_profile.payload.properties

    assert replay.details["mutating_requests_replayed"] == 2
    assert replayed_profile.description == "Profile with contact preference."
    assert "preferred_contact" in replayed_properties
    assert replayed_properties["preferred_contact"].items is None


def test_failed_strict_cutover_status_is_replayable(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.sqlite"
    controller = build_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))
    baseline = controller.export_system_snapshot()
    controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            anchor_writes=(RtgGraphAnchorWrite(RtgChangeReference(local_ref="ada"), "Person"),),
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(local_ref="ada-profile"),
                    type="Profile",
                    properties={"name": "Ada"},
                    anchor_refs=(RtgChangeReference(local_ref="ada"),),
                ),
            ),
        )
    )
    old_profile = controller.get_schema_pack(
        ("Person",)
    ).schema_pack.associated_data_object_schemas[0]
    replacement = RtgSchemaDefinition(
        uuid=uuid4(),
        kind="data_object",
        type_key="Profile",
        description="Profile with required age.",
        payload=RtgDataObjectSchemaPayload(
            properties={"age": RtgSchemaField(required=True, value_kinds=("integer",))}
        ),
        system={"live": False},
    )
    controller.stage_knowledge_changes(
        RtgChangeBatch(
            schema_changes=RtgSchemaChangeSet(
                definition_writes=(
                    RtgSchemaDefinitionWrite(
                        ref=RtgChangeReference(resource_id=concrete_uuid(replacement.uuid)),
                        definition=replacement,
                    ),
                )
            ),
            migration_changes=RtgMigrationChangeSet(
                migration_writes=(
                    RtgMigrationRecordWrite(
                        ref=RtgChangeReference(resource_id="profile-schema-v2"),
                        migration=RtgMigrationRecord(
                            migration_id="profile-schema-v2",
                            description="Replace Profile data object schema.",
                            status="ready",
                            schema_make_live=(concrete_uuid(replacement.uuid),),
                            schema_make_non_live=(concrete_uuid(old_profile.uuid),),
                        ),
                    ),
                )
            ),
        ),
        validation_mode="skip",
    )

    with pytest.raises(RtgControllerValidationFailed):
        controller.apply_migration_cutover("profile-schema-v2")

    failed = controller.get_migration("profile-schema-v2")
    replay_controller = build_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))
    replay = replay_controller.replay_ledger(RtgControllerReplayOptions(start_snapshot=baseline))
    replayed_failed = replay_controller.get_migration("profile-schema-v2")
    status_metadata = cast(dict[str, object], replayed_failed.metadata["status_metadata"])

    assert failed.status == "failed"
    assert replay.details["mutating_requests_replayed"] == 3
    assert replayed_failed.status == "failed"
    assert status_metadata["summary"] == "cutover validation has blocking findings"
    assert replay_controller.validate_graph().accepted is True


def test_migration_history_is_reconstructed_from_ledger(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "ledger.sqlite"
    controller = build_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))
    controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            anchor_writes=(RtgGraphAnchorWrite(RtgChangeReference(local_ref="ada"), "Person"),),
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(local_ref="ada-profile"),
                    type="Profile",
                    properties={"name": "Ada"},
                    anchor_refs=(RtgChangeReference(local_ref="ada"),),
                ),
            ),
        )
    )
    old_profile = controller.get_schema_pack(
        ("Person",)
    ).schema_pack.associated_data_object_schemas[0]
    replacement = RtgSchemaDefinition(
        uuid=uuid4(),
        kind="data_object",
        type_key="Profile",
        description="Profile with required age.",
        payload=RtgDataObjectSchemaPayload(
            properties={"age": RtgSchemaField(required=True, value_kinds=("integer",))}
        ),
        system={"live": False},
    )
    controller.stage_knowledge_changes(
        RtgChangeBatch(
            schema_changes=RtgSchemaChangeSet(
                definition_writes=(
                    RtgSchemaDefinitionWrite(
                        ref=RtgChangeReference(resource_id=concrete_uuid(replacement.uuid)),
                        definition=replacement,
                    ),
                )
            ),
            migration_changes=RtgMigrationChangeSet(
                migration_writes=(
                    RtgMigrationRecordWrite(
                        ref=RtgChangeReference(resource_id="profile-schema-v2"),
                        migration=RtgMigrationRecord(
                            migration_id="profile-schema-v2",
                            description="Replace Profile data object schema.",
                            status="ready",
                            schema_make_live=(concrete_uuid(replacement.uuid),),
                            schema_make_non_live=(concrete_uuid(old_profile.uuid),),
                        ),
                    ),
                )
            ),
        ),
        validation_mode="skip",
    )
    with pytest.raises(RtgControllerValidationFailed):
        controller.apply_migration_cutover("profile-schema-v2")
    controller.abandon_migration("profile-schema-v2", reason="test cleanup")
    reloaded = build_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))

    history = reloaded.list_migration_history()
    event_types = [event["event_type"] for event in history.events]

    assert event_types == ["staged", "cutover_failed", "abandoned"]
    assert {str(event["migration_id"]) for event in history.events} == {"profile-schema-v2"}
    assert all(event["ledger_position"] is not None for event in history.events)


def test_restore_request_response_are_ledgered_and_replayed(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.sqlite"
    controller = build_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))
    baseline = controller.export_system_snapshot()
    controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            anchor_writes=(RtgGraphAnchorWrite(RtgChangeReference(local_ref="ada"), "Person"),),
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(local_ref="ada-profile"),
                    type="Profile",
                    properties={"name": "Ada"},
                    anchor_refs=(RtgChangeReference(local_ref="ada"),),
                ),
            ),
        )
    )
    snapshot_after_first_write = controller.export_system_snapshot()
    controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            anchor_writes=(RtgGraphAnchorWrite(RtgChangeReference(local_ref="grace"), "Person"),),
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(local_ref="grace-profile"),
                    type="Profile",
                    properties={"name": "Grace"},
                    anchor_refs=(RtgChangeReference(local_ref="grace"),),
                ),
            ),
        )
    )
    assert (
        len(
            controller.execute_query(
                RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),))
            ).bindings
        )
        == 2
    )

    restore = controller.restore_from_snapshot(snapshot_after_first_write)
    rows = (
        SqliteStorage.open(ledger_path)
        .query(
            """
        select operation_name, record_kind
        from rtg_controller_ledger
        where operation_name = ?
        order by ledger_position
        """,
            ("restore_from_snapshot",),
        )
        .rows
    )
    replay_controller = build_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))
    replay = replay_controller.replay_ledger(RtgControllerReplayOptions(start_snapshot=baseline))

    assert restore.ledger_position is not None
    assert [(row["operation_name"], row["record_kind"]) for row in rows] == [
        ("restore_from_snapshot", "request"),
        ("restore_from_snapshot", "response"),
    ]
    assert replay.details["mutating_requests_replayed"] == 3
    assert (
        replay_controller.export_system_snapshot().last_ledger_position == restore.ledger_position
    )
    assert (
        len(
            replay_controller.execute_query(
                RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),))
            ).bindings
        )
        == 1
    )


def test_normal_apply_failure_rolls_back_touched_graph_records(tmp_path: Path) -> None:
    sql_storage = SqliteStorage.open(tmp_path / "ledger.sqlite")
    failing_graph = FailingDataPutGraph(InMemoryRtgGraph.empty())
    controller = InProcessRtgController.open(
        failing_graph,
        build_schema(),
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        DeterministicRtgChangeValidator(),
        SimpleRtgQueryEngine(),
        LocalJsonFileStorage.open(tmp_path / "json"),
        sql_storage,
    )

    with pytest.raises(RtgControllerApplyFailed):
        controller.apply_live_graph_changes(
            RtgGraphChangeSet(
                anchor_writes=(
                    RtgGraphAnchorWrite(
                        ref=RtgChangeReference(local_ref="person"),
                        type="Person",
                    ),
                ),
                data_object_writes=(
                    RtgGraphDataObjectWrite(
                        ref=RtgChangeReference(local_ref="profile"),
                        type="Profile",
                        properties={"name": "Ada"},
                        anchor_refs=(RtgChangeReference(local_ref="person"),),
                    ),
                ),
            )
        )

    failing_graph.fail_data_puts = False
    assert (
        controller.execute_query(
            RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),))
        ).bindings
        == ()
    )


def test_cutover_post_state_failure_restores_pre_cutover_state(tmp_path: Path) -> None:
    controller = InProcessRtgController.open(
        InMemoryRtgGraph.empty(),
        build_schema(),
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        PostCutoverRejectingValidator(),
        SimpleRtgQueryEngine(),
        LocalJsonFileStorage.open(tmp_path / "json"),
        SqliteStorage.open(tmp_path / "ledger.sqlite"),
    )
    old = controller.get_schema_pack(("Person",)).schema_pack.anchor_schemas[0]
    replacement = RtgSchemaDefinition(
        uuid=uuid4(),
        kind="anchor",
        type_key="Person",
        description="Expanded person.",
        payload=RtgAnchorSchemaPayload(required_data_types=("Profile",)),
        system={"live": False},
    )
    controller.stage_knowledge_changes(
        RtgChangeBatch(
            schema_changes=RtgSchemaChangeSet(
                definition_writes=(
                    RtgSchemaDefinitionWrite(
                        ref=RtgChangeReference(resource_id=concrete_uuid(replacement.uuid)),
                        definition=replacement,
                    ),
                )
            ),
            migration_changes=RtgMigrationChangeSet(
                migration_writes=(
                    RtgMigrationRecordWrite(
                        ref=RtgChangeReference(resource_id="person-schema-v2"),
                        migration=RtgMigrationRecord(
                            migration_id="person-schema-v2",
                            description="Replace Person schema.",
                            status="ready",
                            schema_make_live=(concrete_uuid(replacement.uuid),),
                            schema_make_non_live=(concrete_uuid(old.uuid),),
                        ),
                    ),
                )
            ),
        ),
        validation_mode="skip",
    )

    with pytest.raises(RtgControllerValidationFailed):
        controller.apply_migration_cutover(
            "person-schema-v2",
            RtgControllerCutoverOptions(validation_mode="strict", prune_retired=False),
        )

    assert controller.discover_anchor_types().anchor_types[0].description == "Person."
    failed = controller.get_migration("person-schema-v2")
    status_metadata = cast(dict[str, object], failed.metadata["status_metadata"])
    assert failed.status == "failed"
    assert status_metadata["summary"] == "post-cutover validation has blocking findings"


def test_controller_exports_and_persists_snapshot(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)
    snapshot = controller.export_system_snapshot()
    result = controller.persist_system_snapshot("system/snapshot.json")

    assert snapshot.schema.definitions
    assert result.status == "snapshot_persisted"
    assert result.ledger_position is not None
