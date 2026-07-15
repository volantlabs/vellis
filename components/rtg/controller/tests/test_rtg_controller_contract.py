from __future__ import annotations

import dataclasses
import inspect
from concurrent.futures import ThreadPoolExecutor
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
    RtgValidationReport,
)
from components.rtg.constraints import InMemoryRtgConstraints
from components.rtg.controller import (
    InProcessRtgController,
    RtgControllerApplyFailed,
    RtgControllerCutoverOptions,
    RtgControllerDiscoveryFailed,
    RtgControllerObjectNotFound,
    RtgControllerPreconditionFailed,
    RtgControllerRecoveryIndeterminate,
    RtgControllerSnapshotFailed,
    RtgControllerValidationFailed,
)
from components.rtg.controller.reference import create_reference_component
from components.rtg.graph import InMemoryRtgGraph, RtgAnchor
from components.rtg.migration import InMemoryRtgMigration, RtgMigrationRecord
from components.rtg.query import RtgQueryAnchorBucket, RtgQuerySpec, SimpleRtgQueryEngine
from components.rtg.schema import (
    InMemoryRtgSchema,
    RtgAnchorSchemaPayload,
    RtgDataObjectSchemaPayload,
    RtgSchemaDefinition,
    RtgSchemaField,
)
from components.storage.json_file import LocalJsonFileStorage


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

    def get_object(self, object_uuid: object) -> object:
        return self.delegate.get_object(object_uuid)  # type: ignore[arg-type]

    def __getattr__(self, name: str) -> object:
        return getattr(self.delegate, name)


class FailingSnapshotReplacementGraph:
    def __init__(self, delegate: InMemoryRtgGraph) -> None:
        self.delegate = delegate

    @classmethod
    def import_snapshot(cls, snapshot: object) -> FailingSnapshotReplacementGraph:
        return cls(InMemoryRtgGraph.import_snapshot(snapshot))  # type: ignore[arg-type]

    def export_snapshot(self) -> object:
        return self.delegate.export_snapshot()

    def replace_snapshot(self, _snapshot: object) -> None:
        raise RuntimeError("graph snapshot replacement failed")

    def __getattr__(self, name: str) -> object:
        return getattr(self.delegate, name)


class PostCutoverRejectingValidator(DeterministicRtgChangeValidator):
    def validate_graph_state(self, *args: object, **kwargs: object) -> RtgValidationReport:
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


def concrete_uuid(value: UUID | None) -> UUID:
    assert value is not None
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


def build_controller(
    tmp_path: Path,
    *,
    graph: object | None = None,
    validator: object | None = None,
) -> InProcessRtgController:
    return InProcessRtgController.open(
        graph or InMemoryRtgGraph.empty(),
        build_schema(),
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        validator or DeterministicRtgChangeValidator(),
        SimpleRtgQueryEngine(),
        LocalJsonFileStorage.open(tmp_path / "json"),
    )


MODEL_EVIDENCE = {
    "ApplyLiveGraphChangesContractVerification": (
        "test_live_graph_mutation_resolves_ids_and_is_queryable",
        "test_rejected_live_mutation_has_no_effect",
        "test_normal_apply_failure_compensates_touched_records",
    ),
    "ValidateLiveGraphChangesContractVerification": (
        "test_validation_preview_resolves_ids_without_mutation",
    ),
    "StageKnowledgeChangesContractVerification": (
        "test_knowledge_staging_requires_migration_scope",
        "test_knowledge_staging_rejects_direct_live_schema_write",
        "test_strict_staging_rejects_invalid_projected_cutover",
        "test_staged_graph_candidate_becomes_live_at_cutover",
    ),
    "ApplyMigrationCutoverContractVerification": (
        "test_schema_cutover_replaces_live_definition",
        "test_failed_cutover_restores_domain_state_and_commits_failed_status",
        "test_cutover_compensation_failure_reports_recovery_indeterminate",
        "test_cutover_options_and_missing_migration_are_rejected",
    ),
    "AbandonMigrationContractVerification": ("test_abandon_migration_prunes_private_candidates",),
    "ExecuteControllerQueryContractVerification": (
        "test_live_graph_mutation_resolves_ids_and_is_queryable",
    ),
    "GetSystemStateContractVerification": (
        "test_system_state_contains_only_domain_and_snapshot_state",
    ),
    "ExportSystemSnapshotContractVerification": (
        "test_snapshot_persist_load_and_restore_round_trip",
        "test_invalid_snapshot_restore_is_atomic",
    ),
    "RestoreFromSnapshotContractVerification": (
        "test_snapshot_persist_load_and_restore_round_trip",
        "test_invalid_snapshot_restore_is_atomic",
        "test_snapshot_compensation_failure_reports_recovery_indeterminate",
        "test_controller_uses_public_snapshot_replacement_contracts",
        "test_controller_serializes_reads_during_coordinated_restore",
    ),
    "ControllerGetObjectContractVerification": ("test_get_object_maps_invalid_and_missing_ids",),
    "ControllerListMigrationsContractVerification": (
        "test_staged_graph_candidate_becomes_live_at_cutover",
    ),
    "ControllerGetMigrationContractVerification": (
        "test_failed_cutover_restores_domain_state_and_commits_failed_status",
    ),
    "ValidateGraphContractVerification": ("test_validate_graph_and_discovery_options",),
    "DiscoverAnchorTypesContractVerification": (
        "test_schema_cutover_replaces_live_definition",
        "test_validate_graph_and_discovery_options",
    ),
    "GetControllerSchemaPackContractVerification": (
        "test_schema_cutover_replaces_live_definition",
    ),
    "PersistSystemSnapshotContractVerification": (
        "test_snapshot_persist_load_and_restore_round_trip",
    ),
    "ListPersistedSnapshotsContractVerification": (
        "test_snapshot_persist_load_and_restore_round_trip",
    ),
    "LoadPersistedSnapshotContractVerification": (
        "test_snapshot_persist_load_and_restore_round_trip",
    ),
    "OpenRtgControllerContractVerification": (
        "test_controller_construction_has_no_sql_or_ledger_dependency",
        "test_controller_uses_public_snapshot_replacement_contracts",
    ),
    "RtgControllerBoundaryVerification": (
        "test_controller_construction_has_no_sql_or_ledger_dependency",
        "test_live_graph_mutation_resolves_ids_and_is_queryable",
        "test_failed_cutover_restores_domain_state_and_commits_failed_status",
        "test_snapshot_persist_load_and_restore_round_trip",
        "test_controller_serializes_reads_during_coordinated_restore",
        "test_live_lane_rejects_non_live_candidate_creation",
        "test_strict_staging_rejects_invalid_projected_cutover",
    ),
}


def person_batch(name: str = "Ada") -> RtgGraphChangeSet:
    return RtgGraphChangeSet(
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
                properties={"name": name},
                anchor_refs=(RtgChangeReference(local_ref="person"),),
            ),
        ),
    )


def person_query() -> RtgQuerySpec:
    return RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),))


def stage_person_schema_replacement(
    controller: InProcessRtgController,
    *,
    migration_id: str = "person-schema-v2",
) -> RtgSchemaDefinition:
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
                        ref=RtgChangeReference(resource_id=migration_id),
                        migration=RtgMigrationRecord(
                            migration_id=migration_id,
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
    return replacement


def test_controller_construction_has_no_sql_or_ledger_dependency(tmp_path: Path) -> None:
    parameters = inspect.signature(InProcessRtgController.open).parameters
    controller = build_controller(tmp_path)
    reference = create_reference_component(
        InMemoryRtgGraph.empty(),
        build_schema(),
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        DeterministicRtgChangeValidator(),
        SimpleRtgQueryEngine(),
        LocalJsonFileStorage.open(tmp_path / "reference-json"),
    )

    assert "sql_storage" not in parameters
    assert not hasattr(controller, "replay_ledger")
    assert not hasattr(controller, "verify_replay_from_ledger")
    assert not hasattr(controller, "list_migration_history")
    assert not hasattr(controller, "flush_ledger_failures")
    assert not hasattr(controller, "apply_change_batch")
    assert reference.get_system_state().state_classification == "schema_only"


def test_controller_uses_public_snapshot_replacement_contracts(tmp_path: Path) -> None:
    graph = InMemoryRtgGraph.empty()
    schema = build_schema()
    constraints = InMemoryRtgConstraints.empty()
    migration = InMemoryRtgMigration.empty()
    calls: list[str] = []
    for name, component in (
        ("graph", graph),
        ("schema", schema),
        ("constraints", constraints),
        ("migration", migration),
    ):
        original = component.replace_snapshot

        def tracked(snapshot: object, *, name: str = name, original=original) -> None:
            calls.append(name)
            original(snapshot)  # type: ignore[arg-type]

        component.replace_snapshot = tracked  # type: ignore[method-assign]
    controller = InProcessRtgController.open(
        graph,
        schema,
        constraints,
        migration,
        DeterministicRtgChangeValidator(),
        SimpleRtgQueryEngine(),
        LocalJsonFileStorage.open(tmp_path / "json"),
    )
    snapshot = controller.export_system_snapshot()

    result = controller.restore_from_snapshot(snapshot)

    assert result.status == "restore_applied"
    assert calls == ["graph", "schema", "constraints", "migration"]
    assert "coordinated_state_replacer" not in inspect.signature(
        InProcessRtgController.open
    ).parameters


def test_controller_serializes_reads_during_coordinated_restore(tmp_path: Path) -> None:
    BlockingImportGraph.reset_block()
    controller = build_controller(
        tmp_path,
        graph=BlockingImportGraph(InMemoryRtgGraph.empty()),
    )
    snapshot = controller.export_system_snapshot()

    with ThreadPoolExecutor(max_workers=2) as executor:
        restore_future = executor.submit(controller.restore_from_snapshot, snapshot)
        assert BlockingImportGraph.restore_started.wait(timeout=2)

        read_future = executor.submit(controller.get_system_state)
        assert not read_future.done()

        BlockingImportGraph.release_restore.set()

        assert restore_future.result(timeout=2).status == "restore_applied"
        assert read_future.result(timeout=2).state_classification == "schema_only"


def test_live_graph_mutation_resolves_ids_and_is_queryable(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)

    result = controller.apply_live_graph_changes(person_batch())
    query_result = controller.execute_query(person_query())

    assert result.status == "applied"
    assert result.applied_changes.graph_writes == 2
    assert set(result.generated_ids) == {"person", "profile"}
    assert query_result.bindings[0].anchors["person"] == result.generated_ids["person"]
    assert not hasattr(result, "transaction_id")
    assert not hasattr(result, "ledger_position")


def test_validation_preview_resolves_ids_without_mutation(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)
    baseline = controller.export_system_snapshot()

    preview = controller.validate_live_graph_changes(person_batch())

    assert preview.accepted is True
    assert set(preview.generated_ids) == {"person", "profile"}
    assert controller.export_system_snapshot() == baseline
    assert controller.execute_query(person_query()).bindings == ()


def test_rejected_live_mutation_has_no_effect(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)
    baseline = controller.export_system_snapshot()

    with pytest.raises(RtgControllerValidationFailed):
        controller.apply_live_graph_changes(
            RtgGraphChangeSet(
                anchor_writes=(
                    RtgGraphAnchorWrite(RtgChangeReference(local_ref="person"), "Person"),
                ),
                data_object_writes=(
                    RtgGraphDataObjectWrite(
                        ref=RtgChangeReference(local_ref="profile"),
                        type="Profile",
                        properties={"unexpected": "invalid"},
                        anchor_refs=(RtgChangeReference(local_ref="person"),),
                    ),
                ),
            )
        )

    assert controller.export_system_snapshot() == baseline


def test_live_lane_rejects_non_live_candidate_creation(tmp_path: Path) -> None:
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


def test_normal_apply_failure_compensates_touched_records(tmp_path: Path) -> None:
    graph = FailingDataPutGraph(InMemoryRtgGraph.empty())
    controller = build_controller(tmp_path, graph=graph)

    with pytest.raises(RtgControllerApplyFailed):
        controller.apply_live_graph_changes(person_batch())

    graph.fail_data_puts = False
    assert controller.execute_query(person_query()).bindings == ()


def test_get_object_maps_invalid_and_missing_ids(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)

    for object_uuid in ("not-a-uuid", "11111111-1111-1111-1111-111111111111"):
        with pytest.raises(RtgControllerObjectNotFound) as raised:
            controller.get_object(object_uuid)
        assert raised.value.diagnostic["mutation_state"] == "not_mutated"


def test_knowledge_staging_requires_migration_scope(tmp_path: Path) -> None:
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


def test_strict_staging_rejects_invalid_projected_cutover(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)
    old_profile = controller.get_schema_pack(
        ("Person",)
    ).schema_pack.associated_data_object_schemas[0]
    replacement = RtgSchemaDefinition(
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

    with pytest.raises(RtgControllerValidationFailed) as raised:
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
                                schema_make_live=(concrete_uuid(replacement.uuid),),
                                schema_make_non_live=(concrete_uuid(old_profile.uuid),),
                                graph_make_live=(person_uuid, profile_uuid),
                            ),
                        ),
                    )
                ),
            )
        )

    assert raised.value.validation_report is not None
    assert "migration_cutover.post_state_invalid" in {
        finding.code for finding in raised.value.validation_report.findings
    }
    assert controller.list_migrations().migrations == ()


def test_staged_graph_candidate_becomes_live_at_cutover(tmp_path: Path) -> None:
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
                            description="Publish staged person.",
                            status="ready",
                            graph_make_live=(person_uuid, profile_uuid),
                        ),
                    ),
                )
            ),
        )
    )

    assert controller.execute_query(person_query()).bindings == ()
    controller.apply_migration_cutover("person-candidate")
    assert len(controller.execute_query(person_query()).bindings) == 1


def test_schema_cutover_replaces_live_definition(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)
    stage_person_schema_replacement(controller)

    result = controller.apply_migration_cutover("person-schema-v2")

    assert result.status == "cutover_applied"
    assert controller.discover_anchor_types().anchor_types[0].description == "Expanded person."


def test_cutover_options_and_missing_migration_are_rejected(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)

    with pytest.raises(RtgControllerPreconditionFailed, match="validation_mode"):
        controller.apply_migration_cutover(
            "missing",
            RtgControllerCutoverOptions(validation_mode="maybe"),
        )
    with pytest.raises(RtgControllerPreconditionFailed):
        controller.apply_migration_cutover("missing")


def test_failed_cutover_restores_domain_state_and_commits_failed_status(
    tmp_path: Path,
) -> None:
    controller = build_controller(
        tmp_path,
        validator=PostCutoverRejectingValidator(),
    )
    stage_person_schema_replacement(controller)

    with pytest.raises(RtgControllerValidationFailed):
        controller.apply_migration_cutover(
            "person-schema-v2",
            RtgControllerCutoverOptions(validation_mode="strict", prune_retired=False),
        )

    assert controller.discover_anchor_types().anchor_types[0].description == "Person."
    failed = controller.get_migration("person-schema-v2")
    status_metadata = cast(dict[str, object], failed.metadata["status_metadata"])
    assert failed.status == "failed"
    assert isinstance(status_metadata["saga_id"], str)
    assert status_metadata["summary"] == "post-cutover validation has blocking findings"


def test_cutover_compensation_failure_reports_recovery_indeterminate(
    tmp_path: Path,
) -> None:
    controller = build_controller(
        tmp_path,
        graph=FailingSnapshotReplacementGraph(InMemoryRtgGraph.empty()),
        validator=PostCutoverRejectingValidator(),
    )
    stage_person_schema_replacement(controller)

    with pytest.raises(RtgControllerRecoveryIndeterminate) as raised:
        controller.apply_migration_cutover(
            "person-schema-v2",
            RtgControllerCutoverOptions(validation_mode="strict", prune_retired=False),
        )

    assert raised.value.diagnostic["code"] == "controller.cutover.compensation_failed"
    assert raised.value.diagnostic["mutation_state"] == "indeterminate"


def test_abandon_migration_prunes_private_candidates(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)
    replacement = stage_person_schema_replacement(controller)

    result = controller.abandon_migration("person-schema-v2", "not wanted")

    assert result.status == "migration_abandoned"
    assert (
        str(replacement.uuid)
        in cast(dict[str, list[str]], result.details["pruned_candidates"])["schema"]
    )
    assert controller.list_migrations().migrations == ()


def test_system_state_contains_only_domain_and_snapshot_state(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)
    state = controller.get_system_state()

    assert state.state_classification == "schema_only"
    assert state.live_schema_counts.total == 2
    assert state.persisted_snapshot_paths == ()
    assert not hasattr(state, "ledger_record_count")
    assert not hasattr(state, "last_ledger_position")
    assert not hasattr(state, "last_transaction_id")


def test_validate_graph_and_discovery_options(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)

    assert controller.validate_graph().accepted is True
    assert controller.discover_anchor_types().anchor_types[0].type_key == "Person"
    with pytest.raises(RtgControllerDiscoveryFailed, match="limit"):
        controller.discover_anchor_types(type("Options", (), {"limit": 0})())


def test_snapshot_persist_load_and_restore_round_trip(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)
    baseline = controller.export_system_snapshot()
    persisted = controller.persist_system_snapshot("system/snapshot.json")
    controller.apply_live_graph_changes(person_batch())

    listed = controller.list_persisted_snapshots()
    loaded = controller.load_persisted_snapshot("system/snapshot.json")
    restored = controller.restore_from_snapshot(loaded.snapshot)

    assert persisted.snapshot == baseline
    assert listed.snapshots[0]["relative_path"] == "system/snapshot.json"
    assert restored.status == "restore_applied"
    assert controller.export_system_snapshot() == baseline
    assert controller.execute_query(person_query()).bindings == ()


def test_invalid_snapshot_restore_is_atomic(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)
    before = controller.export_system_snapshot()
    invalid_graph = InMemoryRtgGraph.empty()
    invalid_graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Person"))
    invalid_snapshot = dataclasses.replace(before, graph=invalid_graph.export_snapshot())

    with pytest.raises(RtgControllerSnapshotFailed, match="violates controller invariants"):
        controller.restore_from_snapshot(invalid_snapshot)

    assert controller.export_system_snapshot() == before


def test_snapshot_compensation_failure_reports_recovery_indeterminate(
    tmp_path: Path,
) -> None:
    controller = build_controller(
        tmp_path,
        graph=FailingSnapshotReplacementGraph(InMemoryRtgGraph.empty()),
    )
    snapshot = controller.export_system_snapshot()

    with pytest.raises(RtgControllerRecoveryIndeterminate) as raised:
        controller.restore_from_snapshot(snapshot)

    assert raised.value.diagnostic["code"] == "controller.snapshot.compensation_failed"
    assert raised.value.diagnostic["mutation_state"] == "indeterminate"


def test_validation_preview_reports_missing_link_references(tmp_path: Path) -> None:
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
    assert controller.export_system_snapshot() == baseline
