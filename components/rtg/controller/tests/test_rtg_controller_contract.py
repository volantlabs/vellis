from __future__ import annotations

import dataclasses
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime
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
    RtgIdentityOverride,
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
    RtgControllerObjectNotFound,
    RtgControllerPreconditionFailed,
    RtgControllerReplayFailed,
    RtgControllerReplayOptions,
    RtgControllerRestoreOptions,
    RtgControllerSnapshotFailed,
    RtgControllerValidationFailed,
    RtgControllerWriteConflict,
)
from components.rtg.graph import InMemoryRtgGraph, RtgAnchor, RtgDataObject
from components.rtg.migration import (
    InMemoryRtgMigration,
    RtgMigrationRecord,
    RtgMigrationSnapshot,
    RtgSchemaEvolutionOp,
)
from components.rtg.query import RtgQueryAnchorBucket, RtgQuerySpec, SimpleRtgQueryEngine
from components.rtg.schema import (
    InMemoryRtgSchema,
    RtgAnchorSchemaPayload,
    RtgDataObjectSchemaPayload,
    RtgIdentityCriterion,
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


def latest_ledger_payload(
    ledger_path: Path,
    operation_name: str,
    record_kind: str,
) -> dict[str, object]:
    rows = (
        SqliteStorage.open(ledger_path)
        .query(
            """
        select payload_json
        from rtg_controller_ledger
        where operation_name = ? and record_kind = ?
        order by ledger_position
        """,
            (operation_name, record_kind),
        )
        .rows
    )
    assert rows
    payload = json.loads(str(rows[-1]["payload_json"]))
    return json_object(payload)


def latest_live_graph_data_uuid(ledger_path: Path) -> UUID:
    request_payload = latest_ledger_payload(
        ledger_path,
        "apply_live_graph_changes",
        "request",
    )
    graph_changes = json_object(request_payload["graph_changes"])
    data_object_writes = cast(list[object], graph_changes["data_object_writes"])
    first_write = json_object(data_object_writes[0])
    ref = json_object(first_write["ref"])
    return UUID(str(ref["resource_id"]))


class InjectedSchemaEvolutionCutoverOptions:
    validation_mode = "skip"
    prune_retired = True
    failure_restore = "restore_pre_cutover_snapshot"

    def __init__(self, schema_evolution_ops: tuple[RtgSchemaEvolutionOp, ...]) -> None:
        self.schema_evolution_ops = schema_evolution_ops


def build_schema(*, include_title: bool = False) -> InMemoryRtgSchema:
    schema = InMemoryRtgSchema.empty()
    profile_properties = {
        "name": RtgSchemaField(required=True, value_kinds=("string",)),
    }
    if include_title:
        profile_properties["title"] = RtgSchemaField(
            required=False,
            value_kinds=("string",),
        )
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="anchor",
            type_key="Person",
            description="Person.",
            payload=RtgAnchorSchemaPayload(required_data_types=("Profile",)),
            time_shape="state_now",
        )
    )
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="data_object",
            type_key="Profile",
            description="Profile.",
            payload=RtgDataObjectSchemaPayload(properties=profile_properties),
            time_shape="state_now",
        )
    )
    return schema


def build_identity_schema() -> InMemoryRtgSchema:
    schema = InMemoryRtgSchema.empty()
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="anchor",
            type_key="Person",
            description="Person.",
            payload=RtgAnchorSchemaPayload(),
            time_shape="state_now",
            identity_criteria=(
                RtgIdentityCriterion(
                    "person_display_name",
                    ("display_name",),
                    "normalized",
                    "same_type",
                ),
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


def build_merge_replace_controller_with_sql(
    tmp_path: Path,
    sql_storage: object,
) -> InProcessRtgController:
    return InProcessRtgController.open(
        InMemoryRtgGraph.empty(),
        build_schema(include_title=True),
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        DeterministicRtgChangeValidator(),
        SimpleRtgQueryEngine(),
        LocalJsonFileStorage.open(tmp_path / "json"),
        sql_storage,
    )


def build_identity_controller_with_sql(
    tmp_path: Path,
    sql_storage: object,
) -> InProcessRtgController:
    return InProcessRtgController.open(
        InMemoryRtgGraph.empty(),
        build_identity_schema(),
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


def create_profile(
    controller: InProcessRtgController,
    *,
    person_uuid: UUID | None = None,
    profile_uuid: UUID | None = None,
) -> tuple[UUID, UUID]:
    person_uuid = person_uuid or uuid4()
    profile_uuid = profile_uuid or uuid4()
    controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            anchor_writes=(
                RtgGraphAnchorWrite(
                    ref=RtgChangeReference(resource_id=person_uuid),
                    type="Person",
                    display_name="Ada",
                ),
            ),
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(resource_id=profile_uuid),
                    type="Profile",
                    mode="merge",
                    properties={"name": "Ada", "title": "Countess"},
                    anchor_refs=(RtgChangeReference(resource_id=person_uuid),),
                ),
            ),
        )
    )
    return person_uuid, profile_uuid


MODEL_EVIDENCE = {
    "ApplyLiveGraphChangesContractVerification": (
        "test_replay_can_resume_from_a_structurally_valid_skip_mode_snapshot",
        "test_controller_writes_wait_while_replay_owns_system_state",
        "test_live_graph_lane_resolves_local_refs_validates_applies_and_ledgers",
        "test_live_graph_lane_rejects_invalid_batch_without_mutating",
        "test_live_graph_lane_rejects_missing_data_write_mode_without_mutating",
        "test_data_object_reads_issue_stable_tokens_and_merge_replace_are_explicit",
        "test_stale_replace_returns_winning_state_and_ledgers_conflict",
        "test_interleaved_replace_writers_cannot_both_succeed",
        "test_version_tokens_protect_replace_when_ledger_persistence_is_degraded",
        "test_controller_cutover_flips_schema_live_status_and_prunes",
        "test_cutover_rejects_schema_candidate_that_invalidates_live_graph_data",
        "test_controller_maps_cutover_precondition_failures",
        "test_live_graph_lane_rejects_non_live_candidate_creation",
        "test_knowledge_staging_accepts_non_live_graph_candidate_when_migration_scoped",
        "test_ledger_failures_are_queued_and_flushed",
        "test_ledger_failure_degrades_result_and_flush_loads_json_queue",
        "test_replay_accepts_persisted_start_snapshot_path",
        "test_verify_replay_from_ledger_uses_scratch_state_and_preserves_current_state",
        "test_replay_verification_restores_invalid_current_instances_exactly",
        "test_replay_reconstructs_cutover_from_ledgered_request_after_pruning",
        "test_replay_decodes_ledgered_schema_fields_with_null_items",
        "test_failed_strict_cutover_status_is_replayable",
        "test_replay_equivalence_detects_equal_counts_with_different_fact_values",
        "test_rejected_staging_is_projected_from_existing_ledger_error",
        "test_migration_history_is_reconstructed_from_ledger",
        "test_restore_request_response_are_ledgered_and_replayed",
        "test_normal_apply_failure_rolls_back_touched_graph_records",
        "test_cutover_post_state_failure_restores_pre_cutover_state",
    ),
    "StageKnowledgeChangesContractVerification": (
        "test_controller_cutover_flips_schema_live_status_and_prunes",
        "test_cutover_rejects_schema_candidate_that_invalidates_live_graph_data",
        "test_controller_maps_cutover_precondition_failures",
        "test_knowledge_staging_rejects_unscoped_schema_candidate",
        "test_knowledge_staging_rejects_direct_live_schema_write",
        "test_knowledge_staging_accepts_non_live_graph_candidate_when_migration_scoped",
        "test_strict_knowledge_staging_rejects_invalid_cutover_projection",
        "test_replay_reconstructs_cutover_from_ledgered_request_after_pruning",
        "test_replay_decodes_ledgered_schema_fields_with_null_items",
        "test_failed_strict_cutover_status_is_replayable",
        "test_rejected_staging_is_projected_from_existing_ledger_error",
        "test_unprojectable_staging_is_rejected_and_has_a_terminal_ledger_outcome",
        "test_migration_history_is_reconstructed_from_ledger",
        "test_cutover_post_state_failure_restores_pre_cutover_state",
    ),
    "ValidateLiveGraphChangesContractVerification": (
        "test_replay_can_resume_from_a_structurally_valid_skip_mode_snapshot",
        "test_live_graph_lane_resolves_local_refs_validates_applies_and_ledgers",
        "test_validate_live_graph_changes_resolves_without_mutation_or_ledger",
        "test_validate_live_graph_changes_reports_findings_without_mutation",
        "test_cutover_rejects_schema_candidate_that_invalidates_live_graph_data",
        "test_replay_verification_restores_invalid_current_instances_exactly",
        "test_failed_strict_cutover_status_is_replayable",
    ),
    "ApplyMigrationCutoverContractVerification": (
        "test_controller_cutover_flips_schema_live_status_and_prunes",
        "test_cutover_rejects_schema_candidate_that_invalidates_live_graph_data",
        "test_controller_rejects_unsupported_cutover_options",
        "test_controller_maps_cutover_precondition_failures",
        "test_knowledge_staging_accepts_non_live_graph_candidate_when_migration_scoped",
        "test_replay_reconstructs_cutover_from_ledgered_request_after_pruning",
        "test_replay_decodes_ledgered_schema_fields_with_null_items",
        "test_failed_strict_cutover_status_is_replayable",
        "test_migration_history_is_reconstructed_from_ledger",
        "test_cutover_post_state_failure_restores_pre_cutover_state",
        "test_schema_evolution_rename_property_rewrites_live_data_and_replays",
        "test_schema_evolution_delete_property_strips_live_data_with_ledger_evidence",
        "test_cutover_rejects_injected_unstaged_schema_evolution_ops",
        "test_cutover_rejects_unreviewed_schema_property_diff",
    ),
    "AbandonMigrationContractVerification": (
        "test_migration_history_is_reconstructed_from_ledger",
    ),
    "ExecuteControllerQueryContractVerification": (
        "test_live_graph_lane_resolves_local_refs_validates_applies_and_ledgers",
        "test_validate_live_graph_changes_resolves_without_mutation_or_ledger",
        "test_live_graph_lane_rejects_invalid_batch_without_mutating",
        "test_knowledge_staging_accepts_non_live_graph_candidate_when_migration_scoped",
        "test_replay_accepts_persisted_start_snapshot_path",
        "test_restore_request_response_are_ledgered_and_replayed",
        "test_normal_apply_failure_rolls_back_touched_graph_records",
    ),
    "GetSystemStateContractVerification": (
        "test_get_object_maps_invalid_and_missing_graph_ids_to_controller_failure",
        "test_system_state_uses_typed_compact_counts_and_snapshot_paths",
        "test_cutover_rejects_schema_candidate_that_invalidates_live_graph_data",
        "test_strict_knowledge_staging_rejects_invalid_cutover_projection",
        "test_rejected_staging_is_projected_from_existing_ledger_error",
        "test_cutover_post_state_failure_restores_pre_cutover_state",
    ),
    "ExportSystemSnapshotContractVerification": (
        "test_controller_reads_wait_while_restore_replaces_component_handles",
        "test_restore_validates_combined_candidate_before_any_visible_replacement",
        "test_replay_can_resume_from_a_structurally_valid_skip_mode_snapshot",
        "test_failed_recorded_restore_preserves_components_but_may_advance_audit_pointer",
        "test_controller_writes_wait_while_replay_owns_system_state",
        "test_live_graph_lane_resolves_local_refs_validates_applies_and_ledgers",
        "test_validate_live_graph_changes_resolves_without_mutation_or_ledger",
        "test_validate_live_graph_changes_reports_findings_without_mutation",
        "test_controller_rejects_unsupported_discovery_and_restore_options",
        "test_replay_rejects_ambiguous_start_snapshot_options",
        "test_verify_replay_from_ledger_uses_scratch_state_and_preserves_current_state",
        "test_replay_verification_restores_invalid_current_instances_exactly",
        "test_replay_reconstructs_cutover_from_ledgered_request_after_pruning",
        "test_replay_decodes_ledgered_schema_fields_with_null_items",
        "test_failed_strict_cutover_status_is_replayable",
        "test_replay_equivalence_detects_equal_counts_with_different_fact_values",
        "test_restore_request_response_are_ledgered_and_replayed",
        "test_controller_exports_and_persists_snapshot",
    ),
    "RestoreFromSnapshotContractVerification": (
        "test_controller_reads_wait_while_restore_replaces_component_handles",
        "test_restore_validates_combined_candidate_before_any_visible_replacement",
        "test_replay_can_resume_from_a_structurally_valid_skip_mode_snapshot",
        "test_failed_recorded_restore_preserves_components_but_may_advance_audit_pointer",
        "test_controller_rejects_unsupported_discovery_and_restore_options",
        "test_replay_verification_restores_invalid_current_instances_exactly",
        "test_restore_request_response_are_ledgered_and_replayed",
    ),
    "ReplayLedgerContractVerification": (
        "test_replay_can_resume_from_a_structurally_valid_skip_mode_snapshot",
        "test_controller_writes_wait_while_replay_owns_system_state",
        "test_live_graph_lane_resolves_local_refs_validates_applies_and_ledgers",
        "test_replay_rejects_non_empty_state_without_explicit_snapshot",
        "test_replay_accepts_persisted_start_snapshot_path",
        "test_replay_rejects_ambiguous_start_snapshot_options",
        "test_verify_replay_from_ledger_uses_scratch_state_and_preserves_current_state",
        "test_replay_verification_restores_invalid_current_instances_exactly",
        "test_replay_reconstructs_cutover_from_ledgered_request_after_pruning",
        "test_replay_decodes_ledgered_schema_fields_with_null_items",
        "test_failed_strict_cutover_status_is_replayable",
        "test_replay_equivalence_detects_equal_counts_with_different_fact_values",
        "test_restore_request_response_are_ledgered_and_replayed",
    ),
    "VerifyReplayFromLedgerContractVerification": (
        "test_verify_replay_from_ledger_uses_scratch_state_and_preserves_current_state",
        "test_replay_verification_restores_invalid_current_instances_exactly",
        "test_replay_equivalence_detects_equal_counts_with_different_fact_values",
    ),
    "ListMigrationHistoryContractVerification": (
        "test_rejected_staging_is_projected_from_existing_ledger_error",
        "test_unprojectable_staging_is_rejected_and_has_a_terminal_ledger_outcome",
        "test_migration_history_is_reconstructed_from_ledger",
    ),
    "FlushLedgerFailuresContractVerification": (
        "test_ledger_failures_are_queued_and_flushed",
        "test_ledger_failure_degrades_result_and_flush_loads_json_queue",
    ),
    "ControllerGetObjectContractVerification": (
        "test_get_object_maps_invalid_and_missing_graph_ids_to_controller_failure",
        "test_system_state_uses_typed_compact_counts_and_snapshot_paths",
        "test_validate_live_graph_changes_reports_findings_without_mutation",
        "test_cutover_rejects_schema_candidate_that_invalidates_live_graph_data",
        "test_strict_knowledge_staging_rejects_invalid_cutover_projection",
        "test_replay_reconstructs_cutover_from_ledgered_request_after_pruning",
        "test_replay_decodes_ledgered_schema_fields_with_null_items",
        "test_failed_strict_cutover_status_is_replayable",
        "test_rejected_staging_is_projected_from_existing_ledger_error",
        "test_migration_history_is_reconstructed_from_ledger",
        "test_cutover_post_state_failure_restores_pre_cutover_state",
    ),
    "ControllerListMigrationsContractVerification": (
        "test_strict_knowledge_staging_rejects_invalid_cutover_projection",
        "test_replay_reconstructs_cutover_from_ledgered_request_after_pruning",
        "test_rejected_staging_is_projected_from_existing_ledger_error",
    ),
    "ControllerGetMigrationContractVerification": (
        "test_get_object_maps_invalid_and_missing_graph_ids_to_controller_failure",
        "test_system_state_uses_typed_compact_counts_and_snapshot_paths",
        "test_validate_live_graph_changes_reports_findings_without_mutation",
        "test_controller_cutover_flips_schema_live_status_and_prunes",
        "test_cutover_rejects_schema_candidate_that_invalidates_live_graph_data",
        "test_strict_knowledge_staging_rejects_invalid_cutover_projection",
        "test_replay_reconstructs_cutover_from_ledgered_request_after_pruning",
        "test_replay_decodes_ledgered_schema_fields_with_null_items",
        "test_failed_strict_cutover_status_is_replayable",
        "test_rejected_staging_is_projected_from_existing_ledger_error",
        "test_migration_history_is_reconstructed_from_ledger",
        "test_cutover_post_state_failure_restores_pre_cutover_state",
    ),
    "ValidateGraphContractVerification": (
        "test_controller_reads_wait_while_restore_replaces_component_handles",
        "test_restore_validates_combined_candidate_before_any_visible_replacement",
        "test_replay_can_resume_from_a_structurally_valid_skip_mode_snapshot",
        "test_live_graph_lane_resolves_local_refs_validates_applies_and_ledgers",
        "test_validate_live_graph_changes_resolves_without_mutation_or_ledger",
        "test_validate_live_graph_changes_reports_findings_without_mutation",
        "test_cutover_rejects_schema_candidate_that_invalidates_live_graph_data",
        "test_replay_verification_restores_invalid_current_instances_exactly",
        "test_failed_strict_cutover_status_is_replayable",
    ),
    "DiscoverAnchorTypesContractVerification": (
        "test_controller_cutover_flips_schema_live_status_and_prunes",
        "test_cutover_rejects_schema_candidate_that_invalidates_live_graph_data",
        "test_controller_rejects_unsupported_discovery_and_restore_options",
        "test_replay_reconstructs_cutover_from_ledgered_request_after_pruning",
        "test_cutover_post_state_failure_restores_pre_cutover_state",
    ),
    "GetControllerSchemaPackContractVerification": (
        "test_controller_cutover_flips_schema_live_status_and_prunes",
        "test_cutover_rejects_schema_candidate_that_invalidates_live_graph_data",
        "test_strict_knowledge_staging_rejects_invalid_cutover_projection",
        "test_replay_reconstructs_cutover_from_ledgered_request_after_pruning",
        "test_replay_decodes_ledgered_schema_fields_with_null_items",
        "test_failed_strict_cutover_status_is_replayable",
        "test_rejected_staging_is_projected_from_existing_ledger_error",
        "test_migration_history_is_reconstructed_from_ledger",
        "test_cutover_post_state_failure_restores_pre_cutover_state",
    ),
    "PersistSystemSnapshotContractVerification": (
        "test_system_state_uses_typed_compact_counts_and_snapshot_paths",
        "test_replay_accepts_persisted_start_snapshot_path",
        "test_verify_replay_from_ledger_uses_scratch_state_and_preserves_current_state",
        "test_controller_exports_and_persists_snapshot",
    ),
    "ListPersistedSnapshotsContractVerification": (
        "test_replay_accepts_persisted_start_snapshot_path",
    ),
    "LoadPersistedSnapshotContractVerification": (
        "test_system_state_uses_typed_compact_counts_and_snapshot_paths",
        "test_replay_accepts_persisted_start_snapshot_path",
        "test_replay_reconstructs_cutover_from_ledgered_request_after_pruning",
        "test_replay_decodes_ledgered_schema_fields_with_null_items",
        "test_failed_strict_cutover_status_is_replayable",
        "test_controller_exports_and_persists_snapshot",
    ),
    "OpenRtgControllerContractVerification": (
        "test_controller_writes_wait_while_replay_owns_system_state",
        "test_validate_live_graph_changes_resolves_without_mutation_or_ledger",
        "test_live_graph_lane_rejects_invalid_batch_without_mutating",
        "test_cutover_rejects_schema_candidate_that_invalidates_live_graph_data",
        "test_ledger_failures_are_queued_and_flushed",
        "test_ledger_failure_degrades_result_and_flush_loads_json_queue",
        "test_replay_accepts_persisted_start_snapshot_path",
        "test_verify_replay_from_ledger_uses_scratch_state_and_preserves_current_state",
        "test_replay_verification_restores_invalid_current_instances_exactly",
        "test_replay_reconstructs_cutover_from_ledgered_request_after_pruning",
        "test_replay_decodes_ledgered_schema_fields_with_null_items",
        "test_failed_strict_cutover_status_is_replayable",
        "test_replay_equivalence_detects_equal_counts_with_different_fact_values",
        "test_rejected_staging_is_projected_from_existing_ledger_error",
        "test_migration_history_is_reconstructed_from_ledger",
        "test_restore_request_response_are_ledgered_and_replayed",
        "test_normal_apply_failure_rolls_back_touched_graph_records",
        "test_cutover_post_state_failure_restores_pre_cutover_state",
    ),
    "RtgControllerBoundaryVerification": (
        "test_get_object_maps_invalid_and_missing_graph_ids_to_controller_failure",
        "test_controller_reads_wait_while_restore_replaces_component_handles",
        "test_restore_validates_combined_candidate_before_any_visible_replacement",
        "test_replay_can_resume_from_a_structurally_valid_skip_mode_snapshot",
        "test_failed_recorded_restore_preserves_components_but_may_advance_audit_pointer",
        "test_system_state_uses_typed_compact_counts_and_snapshot_paths",
        "test_controller_writes_wait_while_replay_owns_system_state",
        "test_live_graph_lane_resolves_local_refs_validates_applies_and_ledgers",
        "test_validate_live_graph_changes_resolves_without_mutation_or_ledger",
        "test_validate_live_graph_changes_reports_findings_without_mutation",
        "test_live_graph_lane_rejects_invalid_batch_without_mutating",
        "test_controller_cutover_flips_schema_live_status_and_prunes",
        "test_cutover_rejects_schema_candidate_that_invalidates_live_graph_data",
        "test_concrete_controller_has_no_generic_change_batch_bypass",
        "test_controller_rejects_unsupported_cutover_options",
        "test_controller_maps_cutover_precondition_failures",
        "test_controller_rejects_unsupported_discovery_and_restore_options",
        "test_live_graph_lane_rejects_non_live_candidate_creation",
        "test_knowledge_staging_rejects_unscoped_schema_candidate",
        "test_knowledge_staging_rejects_direct_live_schema_write",
        "test_knowledge_staging_accepts_non_live_graph_candidate_when_migration_scoped",
        "test_strict_knowledge_staging_rejects_invalid_cutover_projection",
        "test_ledger_failures_are_queued_and_flushed",
        "test_ledger_failure_degrades_result_and_flush_loads_json_queue",
        "test_replay_rejects_non_empty_state_without_explicit_snapshot",
        "test_replay_accepts_persisted_start_snapshot_path",
        "test_replay_rejects_ambiguous_start_snapshot_options",
        "test_verify_replay_from_ledger_uses_scratch_state_and_preserves_current_state",
        "test_replay_verification_restores_invalid_current_instances_exactly",
        "test_replay_reconstructs_cutover_from_ledgered_request_after_pruning",
        "test_replay_decodes_ledgered_schema_fields_with_null_items",
        "test_failed_strict_cutover_status_is_replayable",
        "test_replay_equivalence_detects_equal_counts_with_different_fact_values",
        "test_rejected_staging_is_projected_from_existing_ledger_error",
        "test_unprojectable_staging_is_rejected_and_has_a_terminal_ledger_outcome",
        "test_migration_history_is_reconstructed_from_ledger",
        "test_restore_request_response_are_ledgered_and_replayed",
        "test_normal_apply_failure_rolls_back_touched_graph_records",
        "test_cutover_post_state_failure_restores_pre_cutover_state",
        "test_controller_exports_and_persists_snapshot",
    ),
}


def test_get_object_maps_invalid_and_missing_graph_ids_to_controller_failure(
    tmp_path: Path,
) -> None:
    controller = build_controller(tmp_path)

    for object_uuid in ("not-a-uuid", "11111111-1111-1111-1111-111111111111"):
        with pytest.raises(RtgControllerObjectNotFound) as raised:
            controller.get_object(object_uuid)

        assert raised.value.diagnostic["code"] == "controller.object.not_found"
        assert raised.value.diagnostic["mutation_state"] == "not_mutated"


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


def test_replay_can_resume_from_a_structurally_valid_skip_mode_snapshot(
    tmp_path: Path,
) -> None:
    source = build_controller(tmp_path / "source")
    source.apply_live_graph_changes(
        RtgGraphChangeSet(
            anchor_writes=(RtgGraphAnchorWrite(RtgChangeReference(local_ref="person"), "Person"),)
        ),
        validation_mode="skip",
    )
    skip_mode_snapshot = source.export_system_snapshot()
    assert source.validate_graph().accepted is False
    with pytest.raises(RtgControllerSnapshotFailed):
        source.restore_from_snapshot(
            skip_mode_snapshot, RtgControllerRestoreOptions(ledger_mode="skip")
        )

    replay = build_controller(tmp_path / "replay")
    result = replay.replay_ledger(RtgControllerReplayOptions(start_snapshot=skip_mode_snapshot))

    assert result.status == "replay_applied"
    assert replay.export_system_snapshot().graph == skip_mode_snapshot.graph


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
                        mode="merge",
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
                    mode="merge",
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
    anchor_uuid = query_result.bindings[0].anchors["person"]
    applied_anchor = controller.get_object(anchor_uuid).object
    assert isinstance(applied_anchor, RtgAnchor)
    created_at = applied_anchor.system["created_at"]
    updated_at = applied_anchor.system["updated_at"]

    assert result.status == "applied"
    assert result.ledger_position is not None
    assert result.applied_changes.graph_writes == 2
    assert set(result.generated_ids) == {"person", "profile"}
    assert result.generated_ids["person"] == query_result.bindings[0].anchors["person"]
    assert len(query_result.bindings) == 1
    assert isinstance(created_at, str)
    assert isinstance(updated_at, str)
    assert datetime.fromisoformat(created_at)
    assert datetime.fromisoformat(updated_at)
    replay_controller = build_controller(tmp_path)
    ledger_records_seen = replay_controller.replay_ledger(
        RtgControllerReplayOptions(start_snapshot=baseline)
    ).details["ledger_records_seen"]
    replayed_query = replay_controller.execute_query(
        RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),))
    )
    assert isinstance(ledger_records_seen, int)
    assert ledger_records_seen >= 2
    assert replayed_query.bindings[0].anchors["person"] == result.generated_ids["person"]


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
                    mode="merge",
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
                    mode="merge",
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


def test_live_graph_lane_rejects_missing_data_write_mode_without_mutating(
    tmp_path: Path,
) -> None:
    controller = build_controller(tmp_path)
    person_uuid = uuid4()
    profile_uuid = uuid4()

    with pytest.raises(RtgControllerValidationFailed) as error:
        controller.apply_live_graph_changes(
            RtgGraphChangeSet(
                anchor_writes=(
                    RtgGraphAnchorWrite(
                        ref=RtgChangeReference(resource_id=person_uuid),
                        type="Person",
                    ),
                ),
                data_object_writes=(
                    RtgGraphDataObjectWrite(
                        ref=RtgChangeReference(resource_id=profile_uuid),
                        type="Profile",
                        properties={"name": "Ada"},
                        anchor_refs=(RtgChangeReference(resource_id=person_uuid),),
                    ),
                ),
            )
        )

    assert error.value.validation_report is not None
    assert "schema_object.data_write_mode_missing" in {
        finding.code for finding in error.value.validation_report.findings
    }
    assert controller.export_system_snapshot().graph.data_objects == ()


def test_data_object_reads_issue_stable_tokens_and_merge_replace_are_explicit(
    tmp_path: Path,
) -> None:
    controller = build_merge_replace_controller_with_sql(
        tmp_path,
        SqliteStorage.open(tmp_path / "ledger.sqlite"),
    )
    person_uuid, profile_uuid = create_profile(controller)
    initial = controller.get_object(profile_uuid)

    assert isinstance(initial.object, RtgDataObject)
    assert initial.object.properties == {"name": "Ada", "title": "Countess"}
    assert initial.direct_anchor_refs == (person_uuid,)
    assert initial.version_token is not None
    assert initial.observed_ledger_position is not None

    controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            anchor_writes=(
                RtgGraphAnchorWrite(
                    ref=RtgChangeReference(resource_id=person_uuid),
                    type="Person",
                    display_name="Ada Lovelace",
                ),
            )
        )
    )
    after_unrelated_anchor_write = controller.get_object(profile_uuid)
    assert after_unrelated_anchor_write.version_token == initial.version_token
    assert after_unrelated_anchor_write.observed_ledger_position is not None
    assert after_unrelated_anchor_write.observed_ledger_position > initial.observed_ledger_position

    controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(resource_id=profile_uuid),
                    type="Profile",
                    mode="merge",
                    properties={"title": "Mathematician"},
                    anchor_refs=(RtgChangeReference(resource_id=person_uuid),),
                ),
            )
        )
    )
    merged = controller.get_object(profile_uuid)
    assert isinstance(merged.object, RtgDataObject)
    assert merged.object.properties == {"name": "Ada", "title": "Mathematician"}
    assert merged.version_token != initial.version_token
    assert merged.version_token is not None

    controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(resource_id=profile_uuid),
                    type="Profile",
                    mode="replace",
                    expected_version=merged.version_token,
                    properties={"name": "Ada Lovelace"},
                    anchor_refs=(RtgChangeReference(resource_id=person_uuid),),
                ),
            )
        )
    )
    replaced = controller.get_object(profile_uuid)
    assert isinstance(replaced.object, RtgDataObject)
    assert replaced.object.properties == {"name": "Ada Lovelace"}


def test_stale_replace_returns_winning_state_and_ledgers_conflict(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.sqlite"
    controller = build_merge_replace_controller_with_sql(
        tmp_path,
        SqliteStorage.open(ledger_path),
    )
    person_uuid, profile_uuid = create_profile(controller)
    starting = controller.get_object(profile_uuid)
    assert starting.version_token is not None

    controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(resource_id=profile_uuid),
                    type="Profile",
                    mode="replace",
                    expected_version=starting.version_token,
                    properties={"name": "Grace", "title": "Rear Admiral"},
                    anchor_refs=(RtgChangeReference(resource_id=person_uuid),),
                ),
            )
        )
    )
    winning = controller.get_object(profile_uuid)
    baseline = controller.export_system_snapshot()

    with pytest.raises(RtgControllerWriteConflict) as error:
        controller.apply_live_graph_changes(
            RtgGraphChangeSet(
                data_object_writes=(
                    RtgGraphDataObjectWrite(
                        ref=RtgChangeReference(resource_id=profile_uuid),
                        type="Profile",
                        mode="replace",
                        expected_version=starting.version_token,
                        properties={"name": "Katherine"},
                        anchor_refs=(RtgChangeReference(resource_id=person_uuid),),
                    ),
                )
            )
        )

    conflict = error.value.conflicts[0]
    assert conflict.object_uuid == profile_uuid
    assert conflict.current_version == winning.version_token
    assert conflict.current_object == winning.object
    assert conflict.current_direct_anchor_refs == (person_uuid,)
    assert controller.export_system_snapshot().graph == baseline.graph
    error_payload = latest_ledger_payload(ledger_path, "apply_live_graph_changes", "error")
    assert error_payload["status"] == "write_conflict"


def test_interleaved_replace_writers_cannot_both_succeed(tmp_path: Path) -> None:
    controller = build_merge_replace_controller_with_sql(
        tmp_path,
        SqliteStorage.open(tmp_path / "ledger.sqlite"),
    )
    person_uuid, profile_uuid = create_profile(controller)
    starting = controller.get_object(profile_uuid)
    assert starting.version_token is not None

    def replace_name(name: str) -> str:
        try:
            controller.apply_live_graph_changes(
                RtgGraphChangeSet(
                    data_object_writes=(
                        RtgGraphDataObjectWrite(
                            ref=RtgChangeReference(resource_id=profile_uuid),
                            type="Profile",
                            mode="replace",
                            expected_version=starting.version_token,
                            properties={"name": name},
                            anchor_refs=(RtgChangeReference(resource_id=person_uuid),),
                        ),
                    )
                )
            )
        except RtgControllerWriteConflict:
            return "conflict"
        return "applied"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(replace_name, ("Grace", "Katherine")))

    assert sorted(outcomes) == ["applied", "conflict"]


def test_version_tokens_protect_replace_when_ledger_persistence_is_degraded(
    tmp_path: Path,
) -> None:
    controller = build_merge_replace_controller_with_sql(
        tmp_path,
        FlakyLedgerSqlStorage(SqliteStorage.open(tmp_path / "ledger.sqlite")),
    )
    person_uuid, profile_uuid = create_profile(controller)
    current = controller.get_object(profile_uuid)
    assert current.version_token is not None
    assert current.observed_ledger_position is None

    result = controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(resource_id=profile_uuid),
                    type="Profile",
                    mode="replace",
                    expected_version=current.version_token,
                    properties={"name": "Grace"},
                    anchor_refs=(RtgChangeReference(resource_id=person_uuid),),
                ),
            )
        )
    )

    assert result.status == "applied"
    assert result.details["audit_degraded"] is True
    replaced = controller.get_object(profile_uuid)
    assert isinstance(replaced.object, RtgDataObject)
    assert replaced.object.properties == {"name": "Grace"}
    assert replaced.version_token != current.version_token


def test_strict_live_graph_apply_blocks_identity_merge_candidate_before_mutation(
    tmp_path: Path,
) -> None:
    controller = build_identity_controller_with_sql(
        tmp_path,
        SqliteStorage.open(tmp_path / "ledger.sqlite"),
    )
    controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            anchor_writes=(
                RtgGraphAnchorWrite(
                    ref=RtgChangeReference(local_ref="ada"),
                    type="Person",
                    display_name="Ada Lovelace",
                ),
            )
        )
    )
    baseline = controller.export_system_snapshot()
    existing_uuid = (
        controller.execute_query(
            RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),))
        )
        .bindings[0]
        .anchors["person"]
    )

    with pytest.raises(RtgControllerValidationFailed) as error:
        controller.apply_live_graph_changes(
            RtgGraphChangeSet(
                anchor_writes=(
                    RtgGraphAnchorWrite(
                        ref=RtgChangeReference(local_ref="ada-again"),
                        type="Person",
                        display_name="ada lovelace",
                    ),
                )
            )
        )

    assert error.value.validation_report is not None
    finding = next(
        finding
        for finding in error.value.validation_report.findings
        if finding.code == "merge_candidate.identity_match"
    )
    assert finding.track == "merge_candidate"
    assert finding.diagnostic["candidate_uuids"] == [str(existing_uuid)]
    after = controller.export_system_snapshot()
    assert after.graph == baseline.graph
    assert after.schema == baseline.schema
    assert after.constraints == baseline.constraints
    assert after.migration == baseline.migration


def test_validate_live_graph_changes_reports_identity_merge_candidate_without_ledger(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "ledger.sqlite"
    controller = build_identity_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))
    controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            anchor_writes=(
                RtgGraphAnchorWrite(
                    ref=RtgChangeReference(local_ref="ada"),
                    type="Person",
                    display_name="Ada Lovelace",
                ),
            )
        )
    )
    baseline = controller.export_system_snapshot()
    starting_ledger_count = (
        SqliteStorage.open(ledger_path)
        .query("select count(*) as count from rtg_controller_ledger")
        .rows[0]["count"]
    )

    preview = controller.validate_live_graph_changes(
        RtgGraphChangeSet(
            anchor_writes=(
                RtgGraphAnchorWrite(
                    ref=RtgChangeReference(local_ref="ada-again"),
                    type="Person",
                    display_name="Ada Lovelace",
                ),
            )
        )
    )

    assert preview.status == "validated"
    assert preview.mutation_state == "not_mutated"
    assert preview.accepted is False
    assert "merge_candidate.identity_match" in {
        finding.code for finding in preview.validation_report.findings
    }
    assert controller.export_system_snapshot() == baseline
    assert (
        SqliteStorage.open(ledger_path)
        .query("select count(*) as count from rtg_controller_ledger")
        .rows[0]["count"]
        == starting_ledger_count
    )


def test_force_create_identity_override_applies_and_is_preserved_in_request_ledger(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "ledger.sqlite"
    controller = build_identity_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))
    controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            anchor_writes=(
                RtgGraphAnchorWrite(
                    ref=RtgChangeReference(local_ref="ada"),
                    type="Person",
                    display_name="Ada Lovelace",
                ),
            )
        )
    )

    result = controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            anchor_writes=(
                RtgGraphAnchorWrite(
                    ref=RtgChangeReference(local_ref="ada-distinct"),
                    type="Person",
                    display_name="Ada Lovelace",
                    identity_override=RtgIdentityOverride(
                        mode="force_create",
                        reason="confirmed distinct person with the same display name",
                        criterion_keys=("person_display_name",),
                    ),
                ),
            )
        )
    )
    rows = (
        SqliteStorage.open(ledger_path)
        .query(
            """
        select payload_json
        from rtg_controller_ledger
        where operation_name = ? and record_kind = ?
        order by ledger_position
        """,
            ("apply_live_graph_changes", "request"),
        )
        .rows
    )
    request_payload = json.loads(str(rows[-1]["payload_json"]))
    anchor_write = request_payload["graph_changes"]["anchor_writes"][0]

    assert result.status == "applied"
    assert result.validation_report is not None
    assert "merge_candidate.force_create_override" in {
        finding.code for finding in result.validation_report.findings
    }
    assert (
        len(
            controller.execute_query(
                RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("person", ("Person",)),))
            ).bindings
        )
        == 2
    )
    assert anchor_write["ref"]["resource_id"]
    assert anchor_write["identity_override"] == {
        "mode": "force_create",
        "reason": "confirmed distinct person with the same display name",
        "criterion_keys": ["person_display_name"],
    }


def test_controller_cutover_flips_schema_live_status_and_prunes(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)
    old = controller.get_schema_pack(("Person",)).schema_pack.anchor_schemas[0]
    replacement = RtgSchemaDefinition(
        uuid=uuid4(),
        kind="anchor",
        type_key="Person",
        description="Expanded person.",
        payload=RtgAnchorSchemaPayload(required_data_types=("Profile",)),
        time_shape="state_now",
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
                    mode="merge",
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
        time_shape="state_now",
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
        time_shape="state_now",
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
        time_shape="state_now",
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
                        mode="merge",
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
        time_shape="state_now",
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
                            mode="merge",
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
                    mode="merge",
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
                    mode="merge",
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
                    mode="merge",
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
                    mode="merge",
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
    assert verified.state_equivalent_to_live is True
    assert verified.replayed_state_digest == verified.live_state_digest
    assert verified.start_summary == verified.pre_summary
    assert verified.replayed_summary == verified.post_summary
    assert verified.replay_delta == verified.count_diffs
    assert verified.ledger_records_scanned == verified.ledger_records_seen
    assert verified.request_records_seen == 1
    assert verified.eligible_mutating_requests == 1
    assert verified.administrative_records_skipped == 1
    assert verified.terminal_records_skipped == 1
    assert verified.ledger_records_scanned == (
        verified.eligible_mutating_requests
        + verified.failed_or_rejected_transactions_skipped
        + verified.administrative_records_skipped
        + verified.terminal_records_skipped
    )
    graph_diffs = json_object(verified.count_diffs["graph_counts"])
    anchor_diffs = json_object(graph_diffs["anchor"])
    assert anchor_diffs["Person"] == 1
    assert controller.export_system_snapshot() == current
    assert baseline.schema.definitions


def test_replay_verification_restores_invalid_current_instances_exactly(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.sqlite"
    controller = build_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))
    baseline = controller.export_system_snapshot()
    first = controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            anchor_writes=(RtgGraphAnchorWrite(RtgChangeReference(local_ref="ada"), "Person"),),
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(local_ref="ada-profile"),
                    type="Profile",
                    mode="merge",
                    properties={"name": "Ada"},
                    anchor_refs=(RtgChangeReference(local_ref="ada"),),
                ),
            ),
        )
    )
    controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            delete_data_objects=(
                RtgChangeReference(resource_id=first.generated_ids["ada-profile"]),
            )
        ),
        validation_mode="skip",
    )
    current = controller.export_system_snapshot()
    assert controller.validate_graph().accepted is False

    verified = controller.verify_replay_from_ledger(
        RtgControllerReplayOptions(
            start_snapshot=baseline,
            through_ledger_position=first.ledger_position,
        )
    )

    assert verified.state_equivalent_to_live is False
    assert verified.validation_report.accepted is True
    assert controller.export_system_snapshot() == current
    assert controller.validate_graph().accepted is False


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
        time_shape="state_now",
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
        time_shape="state_now",
        system={"live": False},
    )
    op = RtgSchemaEvolutionOp(
        op_id="add-profile-preferred-contact",
        op_kind="add_property",
        target_kind="data_object",
        target_type_key="Profile",
        property_key="preferred_contact",
        replacement_field={"required": False, "value_kinds": ["string"]},
        source_definition_uuid=concrete_uuid(old_profile.uuid),
        candidate_definition_uuid=concrete_uuid(replacement.uuid),
        data_implication="no_existing_data_change",
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
                            schema_evolution_ops=(op,),
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


def test_schema_evolution_rename_property_rewrites_live_data_and_replays(
    tmp_path: Path,
) -> None:
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
                    mode="merge",
                    properties={"name": "Ada"},
                    anchor_refs=(RtgChangeReference(local_ref="ada"),),
                ),
            ),
        )
    )
    profile_uuid = latest_live_graph_data_uuid(ledger_path)
    old_profile = controller.get_schema_pack(
        ("Person",)
    ).schema_pack.associated_data_object_schemas[0]
    replacement = RtgSchemaDefinition(
        uuid=uuid4(),
        kind="data_object",
        type_key="Profile",
        description="Profile with renamed full name.",
        payload=RtgDataObjectSchemaPayload(
            properties={"full_name": RtgSchemaField(required=True, value_kinds=("string",))}
        ),
        time_shape="state_now",
        system={"live": False},
    )
    op = RtgSchemaEvolutionOp(
        op_id="rename-profile-name",
        op_kind="rename_property",
        target_kind="data_object",
        target_type_key="Profile",
        property_key="name",
        replacement_key="full_name",
        source_definition_uuid=concrete_uuid(old_profile.uuid),
        candidate_definition_uuid=concrete_uuid(replacement.uuid),
        data_implication="rename_existing_values",
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
                        ref=RtgChangeReference(resource_id="profile-rename"),
                        migration=RtgMigrationRecord(
                            migration_id="profile-rename",
                            description="Rename Profile.name to Profile.full_name.",
                            status="ready",
                            schema_make_live=(concrete_uuid(replacement.uuid),),
                            schema_make_non_live=(concrete_uuid(old_profile.uuid),),
                            schema_evolution_ops=(op,),
                        ),
                    ),
                )
            ),
        ),
        validation_mode="skip",
    )

    result = controller.apply_migration_cutover("profile-rename")
    profile = controller.get_object(profile_uuid).object
    response_payload = latest_ledger_payload(
        ledger_path,
        "apply_migration_cutover",
        "response",
    )
    response_details = json_object(response_payload["details"])
    diff = json_object(response_details["schema_evolution_diff"])
    op_results = cast(list[object], diff["ops"])
    op_result = json_object(op_results[0])

    assert isinstance(profile, RtgDataObject)
    assert result.status == "cutover_applied"
    assert profile.properties == {"full_name": "Ada"}
    assert op_result["op_id"] == "rename-profile-name"
    assert op_result["op_kind"] == "rename_property"
    assert op_result["data_implication"] == "rename_existing_values"
    assert op_result["affected_count"] == 1
    assert op_result["mutation_state"] == "applied"

    replay_controller = build_controller_with_sql(tmp_path, SqliteStorage.open(ledger_path))
    replay = replay_controller.replay_ledger(RtgControllerReplayOptions(start_snapshot=baseline))
    replayed_profile = replay_controller.get_object(profile_uuid).object

    assert replay.details["mutating_requests_replayed"] == 3
    assert isinstance(replayed_profile, RtgDataObject)
    assert replayed_profile.properties == {"full_name": "Ada"}


def test_schema_evolution_delete_property_strips_live_data_with_ledger_evidence(
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
                    mode="merge",
                    properties={"name": "Ada"},
                    anchor_refs=(RtgChangeReference(local_ref="ada"),),
                ),
            ),
        )
    )
    profile_uuid = latest_live_graph_data_uuid(ledger_path)
    old_profile = controller.get_schema_pack(
        ("Person",)
    ).schema_pack.associated_data_object_schemas[0]
    replacement = RtgSchemaDefinition(
        uuid=uuid4(),
        kind="data_object",
        type_key="Profile",
        description="Profile without name.",
        payload=RtgDataObjectSchemaPayload(properties={}),
        time_shape="state_now",
        system={"live": False},
    )
    op = RtgSchemaEvolutionOp(
        op_id="delete-profile-name",
        op_kind="delete_property",
        target_kind="data_object",
        target_type_key="Profile",
        property_key="name",
        source_definition_uuid=concrete_uuid(old_profile.uuid),
        candidate_definition_uuid=concrete_uuid(replacement.uuid),
        data_implication="strip_existing_values",
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
                        ref=RtgChangeReference(resource_id="profile-delete-name"),
                        migration=RtgMigrationRecord(
                            migration_id="profile-delete-name",
                            description="Delete Profile.name.",
                            status="ready",
                            schema_make_live=(concrete_uuid(replacement.uuid),),
                            schema_make_non_live=(concrete_uuid(old_profile.uuid),),
                            schema_evolution_ops=(op,),
                        ),
                    ),
                )
            ),
        ),
        validation_mode="skip",
    )

    result = controller.apply_migration_cutover("profile-delete-name")
    profile = controller.get_object(profile_uuid).object
    response_payload = latest_ledger_payload(
        ledger_path,
        "apply_migration_cutover",
        "response",
    )
    diff = json_object(json_object(response_payload["details"])["schema_evolution_diff"])
    op_result = json_object(cast(list[object], diff["ops"])[0])

    assert isinstance(profile, RtgDataObject)
    assert result.status == "cutover_applied"
    assert profile.properties == {}
    assert op_result["op_id"] == "delete-profile-name"
    assert op_result["op_kind"] == "delete_property"
    assert op_result["data_implication"] == "strip_existing_values"
    assert op_result["affected_count"] == 1
    assert op_result["mutation_state"] == "applied"


def test_cutover_rejects_injected_unstaged_schema_evolution_ops(
    tmp_path: Path,
) -> None:
    controller = build_controller(tmp_path)
    old_profile = controller.get_schema_pack(
        ("Person",)
    ).schema_pack.associated_data_object_schemas[0]
    replacement = RtgSchemaDefinition(
        uuid=uuid4(),
        kind="data_object",
        type_key="Profile",
        description="Profile with renamed full name.",
        payload=RtgDataObjectSchemaPayload(
            properties={"full_name": RtgSchemaField(required=True, value_kinds=("string",))}
        ),
        time_shape="state_now",
        system={"live": False},
    )
    reviewed = RtgSchemaEvolutionOp(
        op_id="rename-profile-name",
        op_kind="rename_property",
        target_kind="data_object",
        target_type_key="Profile",
        property_key="name",
        replacement_key="full_name",
        source_definition_uuid=concrete_uuid(old_profile.uuid),
        candidate_definition_uuid=concrete_uuid(replacement.uuid),
        data_implication="rename_existing_values",
    )
    injected = RtgSchemaEvolutionOp(
        op_id="delete-profile-name",
        op_kind="delete_property",
        target_kind="data_object",
        target_type_key="Profile",
        property_key="name",
        source_definition_uuid=concrete_uuid(old_profile.uuid),
        candidate_definition_uuid=concrete_uuid(replacement.uuid),
        data_implication="strip_existing_values",
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
                        ref=RtgChangeReference(resource_id="profile-rename"),
                        migration=RtgMigrationRecord(
                            migration_id="profile-rename",
                            description="Rename Profile.name to Profile.full_name.",
                            status="ready",
                            schema_make_live=(concrete_uuid(replacement.uuid),),
                            schema_make_non_live=(concrete_uuid(old_profile.uuid),),
                            schema_evolution_ops=(reviewed,),
                        ),
                    ),
                )
            ),
        ),
        validation_mode="skip",
    )

    with pytest.raises(RtgControllerPreconditionFailed, match="schema_evolution_ops"):
        controller.apply_migration_cutover(
            "profile-rename",
            cast(
                RtgControllerCutoverOptions,
                InjectedSchemaEvolutionCutoverOptions((injected,)),
            ),
        )

    assert controller.get_migration("profile-rename").status == "ready"


def test_cutover_rejects_unreviewed_schema_property_diff(tmp_path: Path) -> None:
    controller = build_controller(tmp_path)
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
        time_shape="state_now",
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
                        ref=RtgChangeReference(resource_id="profile-unreviewed-diff"),
                        migration=RtgMigrationRecord(
                            migration_id="profile-unreviewed-diff",
                            description="Try property add without reviewed op.",
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

    with pytest.raises(RtgControllerPreconditionFailed, match="unreviewed schema evolution op"):
        controller.apply_migration_cutover("profile-unreviewed-diff")

    assert controller.get_migration("profile-unreviewed-diff").status == "ready"


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
                    mode="merge",
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
        time_shape="state_now",
        system={"live": False},
    )
    add_age = RtgSchemaEvolutionOp(
        op_id="add-profile-age",
        op_kind="add_property",
        target_kind="data_object",
        target_type_key="Profile",
        property_key="age",
        replacement_field={"required": True, "value_kinds": ["integer"]},
        source_definition_uuid=concrete_uuid(old_profile.uuid),
        candidate_definition_uuid=concrete_uuid(replacement.uuid),
        data_implication="requires_backfill",
    )
    delete_name = RtgSchemaEvolutionOp(
        op_id="delete-profile-name",
        op_kind="delete_property",
        target_kind="data_object",
        target_type_key="Profile",
        property_key="name",
        source_definition_uuid=concrete_uuid(old_profile.uuid),
        candidate_definition_uuid=concrete_uuid(replacement.uuid),
        data_implication="strip_existing_values",
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
                            schema_evolution_ops=(add_age, delete_name),
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


def test_replay_equivalence_detects_equal_counts_with_different_fact_values(
    tmp_path: Path,
) -> None:
    controller = build_controller_with_sql(tmp_path, SqliteStorage.open(tmp_path / "ledger.sqlite"))
    baseline = controller.export_system_snapshot()
    first = controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            anchor_writes=(RtgGraphAnchorWrite(RtgChangeReference(local_ref="person"), "Person"),),
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    RtgChangeReference(local_ref="profile"),
                    "Profile",
                    {"name": "Ada"},
                    mode="merge",
                    anchor_refs=(RtgChangeReference(local_ref="person"),),
                ),
            ),
        )
    )
    profile_id = first.generated_ids["profile"]
    controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    RtgChangeReference(resource_id=profile_id),
                    "Profile",
                    {"name": "Grace"},
                    mode="merge",
                    anchor_refs=(RtgChangeReference(resource_id=first.generated_ids["person"]),),
                ),
            )
        )
    )
    verified = controller.verify_replay_from_ledger(
        RtgControllerReplayOptions(
            start_snapshot=baseline, through_ledger_position=first.ledger_position
        )
    )
    assert verified.live_count_diffs["graph_counts"] == {
        "anchor": {"Person": 0},
        "data_object": {"Profile": 0},
        "link": {},
    }
    assert verified.state_equivalent_to_live is False
    assert verified.replayed_state_digest != verified.live_state_digest


def test_rejected_staging_is_projected_from_existing_ledger_error(
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
                    mode="merge",
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
        description="Profile requiring a missing sponsor.",
        payload=RtgDataObjectSchemaPayload(
            properties={"sponsor": RtgSchemaField(True, ("string",))}
        ),
        system={"live": False},
    )
    with pytest.raises(RtgControllerValidationFailed):
        controller.stage_knowledge_changes(
            RtgChangeBatch(
                schema_changes=RtgSchemaChangeSet(
                    definition_writes=(
                        RtgSchemaDefinitionWrite(
                            RtgChangeReference(resource_id=concrete_uuid(replacement.uuid)),
                            replacement,
                        ),
                    )
                ),
                migration_changes=RtgMigrationChangeSet(
                    migration_writes=(
                        RtgMigrationRecordWrite(
                            RtgChangeReference(resource_id="rejected-profile-v2"),
                            RtgMigrationRecord(
                                migration_id="rejected-profile-v2",
                                description="Reject incompatible required sponsor.",
                                status="ready",
                                schema_make_live=(concrete_uuid(replacement.uuid),),
                                schema_make_non_live=(concrete_uuid(old_profile.uuid),),
                            ),
                        ),
                    )
                ),
            )
        )
    assert controller.list_migrations().migrations == ()
    event = controller.list_migration_history().events[-1]
    assert event.event_type == "staging_rejected"
    assert event.migration_id == "rejected-profile-v2"
    assert event.staged is False
    assert event.mutation_state == "not_mutated"
    assert event.finding_count > 0
    assert event.validation_report is not None
    assert event.validation_report.accepted is False


def test_unprojectable_staging_is_rejected_and_has_a_terminal_ledger_outcome(
    tmp_path: Path,
) -> None:
    controller = build_controller(tmp_path)
    missing = uuid4()

    with pytest.raises(RtgControllerValidationFailed) as raised:
        controller.stage_knowledge_changes(
            RtgChangeBatch(
                graph_changes=RtgGraphChangeSet(
                    delete_anchors=(RtgChangeReference(resource_id=missing),)
                ),
                migration_changes=RtgMigrationChangeSet(
                    migration_writes=(
                        RtgMigrationRecordWrite(
                            RtgChangeReference(resource_id="unprojectable-staging"),
                            RtgMigrationRecord(
                                migration_id="unprojectable-staging",
                                description="Must be rejected with a terminal outcome.",
                                status="ready",
                            ),
                        ),
                    )
                ),
            )
        )

    assert raised.value.validation_report is not None
    assert raised.value.validation_report.findings[0].code == "change_projection.failed"
    event = controller.list_migration_history().events[-1]
    assert event.event_type == "staging_rejected"
    assert event.migration_id == "unprojectable-staging"
    assert event.finding_codes == ("change_projection.failed",)


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
                    mode="merge",
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
        time_shape="state_now",
        system={"live": False},
    )
    add_age = RtgSchemaEvolutionOp(
        op_id="add-profile-age",
        op_kind="add_property",
        target_kind="data_object",
        target_type_key="Profile",
        property_key="age",
        replacement_field={"required": True, "value_kinds": ["integer"]},
        source_definition_uuid=concrete_uuid(old_profile.uuid),
        candidate_definition_uuid=concrete_uuid(replacement.uuid),
        data_implication="requires_backfill",
    )
    delete_name = RtgSchemaEvolutionOp(
        op_id="delete-profile-name",
        op_kind="delete_property",
        target_kind="data_object",
        target_type_key="Profile",
        property_key="name",
        source_definition_uuid=concrete_uuid(old_profile.uuid),
        candidate_definition_uuid=concrete_uuid(replacement.uuid),
        data_implication="strip_existing_values",
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
                            schema_evolution_ops=(add_age, delete_name),
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
    event_types = [event.event_type for event in history.events]

    assert event_types == ["staged", "cutover_failed", "abandoned"]
    assert {event.migration_id for event in history.events} == {"profile-schema-v2"}
    assert all(event.ledger_position > 0 for event in history.events)
    staged, cutover_failed, abandoned = history.events
    assert staged.finding_count == 0
    assert abandoned.finding_count == 0
    assert cutover_failed.finding_count > 0
    assert cutover_failed.finding_codes
    assert cutover_failed.validation_report is not None
    assert cutover_failed.validation_report.accepted is False


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
                    mode="merge",
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
                    mode="merge",
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
                        mode="merge",
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
        time_shape="state_now",
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
