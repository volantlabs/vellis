from __future__ import annotations

import dataclasses
import json
import threading
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from components.rtg.change_validation.protocol import (
    RtgChangeBatch,
    RtgChangeReference,
    RtgChangeValidator,
    RtgConstraintChangeSet,
    RtgConstraintDefinitionWrite,
    RtgGraphAnchorWrite,
    RtgGraphAssociationChange,
    RtgGraphChangeSet,
    RtgGraphDataObjectWrite,
    RtgGraphLinkWrite,
    RtgGraphLiveStatusChange,
    RtgLiveStatusChange,
    RtgMigrationChangeSet,
    RtgMigrationEvidenceAddition,
    RtgMigrationRecordWrite,
    RtgMigrationStatusChange,
    RtgSchemaChangeSet,
    RtgSchemaDefinitionWrite,
    RtgValidationOptions,
    RtgValidationReport,
)
from components.rtg.constraints.protocol import (
    RtgConstraintCardinalityPayload,
    RtgConstraintDefinition,
    RtgConstraintQueryPatternPayload,
    RtgConstraints,
    RtgConstraintSnapshot,
)
from components.rtg.controller.protocol import (
    RtgAnchorTypeDiscoveryEntry,
    RtgAnchorTypeDiscoveryResult,
    RtgControllerAppliedChanges,
    RtgControllerApplyFailed,
    RtgControllerCandidateCounts,
    RtgControllerConfigurationInvalid,
    RtgControllerCutoverOptions,
    RtgControllerDiscoveryFailed,
    RtgControllerLedgerFailureRecord,
    RtgControllerLiveGraphValidationResult,
    RtgControllerMigrationCounts,
    RtgControllerMigrationHistory,
    RtgControllerObjectNotFound,
    RtgControllerOperationResult,
    RtgControllerPreconditionFailed,
    RtgControllerReplayFailed,
    RtgControllerReplayOptions,
    RtgControllerReplayVerificationResult,
    RtgControllerRestoreOptions,
    RtgControllerSchemaCounts,
    RtgControllerSchemaPack,
    RtgControllerSchemaPackOptions,
    RtgControllerSnapshotFailed,
    RtgControllerSystemState,
    RtgControllerValidationFailed,
    RtgControllerValidationOptions,
    RtgPersistedSnapshotDocument,
    RtgPersistedSnapshotList,
    RtgSystemSnapshot,
)
from components.rtg.diagnostics import rtg_diagnostic
from components.rtg.graph.protocol import (
    JsonObject,
    JsonValue,
    RtgAnchor,
    RtgDataObject,
    RtgGraph,
    RtgGraphObjectNotFound,
    RtgGraphSnapshot,
    RtgGraphUuidInvalid,
    RtgLink,
    RtgObject,
    RtgTypeCountList,
)
from components.rtg.migration.protocol import (
    RtgMigration,
    RtgMigrationCutoverPlan,
    RtgMigrationEvidence,
    RtgMigrationRecord,
    RtgMigrationRecordList,
    RtgMigrationReplacement,
    RtgMigrationSnapshot,
)
from components.rtg.query.protocol import (
    RtgQueryAnchorBucket,
    RtgQueryDataRequirement,
    RtgQueryDiagnosticOptions,
    RtgQueryEngine,
    RtgQueryLinkRequirement,
    RtgQueryOptions,
    RtgQueryPropertyPredicate,
    RtgQueryResult,
    RtgQueryReturnSpec,
    RtgQuerySpec,
)
from components.rtg.schema.protocol import (
    RtgAnchorSchemaPayload,
    RtgDataObjectSchemaPayload,
    RtgLinkSchemaPayload,
    RtgSchema,
    RtgSchemaDefinition,
    RtgSchemaField,
    RtgSchemaSnapshot,
)
from components.storage.json_file.protocol import JsonFileStorage
from components.storage.sql.protocol import SqlStorage

_LEDGER_SCHEMA = """
create table if not exists rtg_controller_ledger (
    ledger_position integer primary key autoincrement,
    transaction_id text not null,
    operation_name text not null,
    record_kind text not null,
    payload_json text not null,
    recorded_at text not null
)
"""


@dataclasses.dataclass(frozen=True, slots=True)
class _GraphPreimage:
    objects: dict[UUID, RtgObject | None]
    data_anchors: dict[UUID, tuple[UUID, ...]]


@dataclasses.dataclass(frozen=True, slots=True)
class _ApplyPreimage:
    graph: _GraphPreimage
    schema: dict[UUID, RtgSchemaDefinition | None]
    constraints: dict[UUID, RtgConstraintDefinition | None]
    migration_snapshot: RtgMigrationSnapshot | None


@dataclasses.dataclass(frozen=True, slots=True)
class _ReplayTransactionMetadata:
    status: str
    ledger_position: int | None
    recorded_at: str | None
    response_payload: JsonObject


class InProcessRtgController:
    """In-process RTG system controller using public component contracts."""

    def __init__(
        self,
        graph: RtgGraph,
        schema: RtgSchema,
        constraints: RtgConstraints,
        migration: RtgMigration,
        change_validator: RtgChangeValidator,
        query_engine: RtgQueryEngine,
        json_storage: JsonFileStorage,
        sql_storage: SqlStorage,
    ) -> None:
        self._graph = graph
        self._schema = schema
        self._constraints = constraints
        self._migration = migration
        self._change_validator = change_validator
        self._query_engine = query_engine
        self._json_storage = json_storage
        self._sql_storage = sql_storage
        self._lock = threading.RLock()
        self._last_ledger_position: int | None = None
        self._last_transaction_id: UUID | None = None
        self._last_transaction_timestamp: str | None = None
        self._ledger_failures: list[RtgControllerLedgerFailureRecord] = []
        self._sql_storage.execute(_LEDGER_SCHEMA)

    @classmethod
    def open(
        cls,
        graph: object,
        schema: object,
        constraints: object,
        migration: object,
        change_validator: object,
        query_engine: object,
        json_storage: object,
        sql_storage: object,
    ) -> InProcessRtgController:
        required = (
            (graph, ("put_anchor", "get_object", "export_snapshot")),
            (schema, ("put_definition", "list_definitions", "export_snapshot")),
            (constraints, ("put_constraint", "list_constraints", "export_snapshot")),
            (migration, ("put_migration", "get_migration", "export_snapshot")),
            (change_validator, ("validate_batch", "validate_graph_state")),
            (query_engine, ("execute",)),
            (json_storage, ("write", "read")),
            (sql_storage, ("execute", "query", "transaction")),
        )
        for dependency, methods in required:
            if not all(hasattr(dependency, method) for method in methods):
                raise RtgControllerConfigurationInvalid(str(methods))
        return cls(
            graph,  # type: ignore[arg-type]
            schema,  # type: ignore[arg-type]
            constraints,  # type: ignore[arg-type]
            migration,  # type: ignore[arg-type]
            change_validator,  # type: ignore[arg-type]
            query_engine,  # type: ignore[arg-type]
            json_storage,  # type: ignore[arg-type]
            sql_storage,  # type: ignore[arg-type]
        )

    def apply_live_graph_changes(
        self,
        graph_changes: RtgGraphChangeSet,
        validation_mode: str = "strict",
    ) -> RtgControllerOperationResult:
        return self._apply_normalized_change_batch(
            RtgChangeBatch(graph_changes=graph_changes),
            validation_mode=validation_mode,
            operation_name="apply_live_graph_changes",
        )

    def validate_live_graph_changes(
        self,
        graph_changes: RtgGraphChangeSet,
        validation_options: RtgControllerValidationOptions | None = None,
    ) -> RtgControllerLiveGraphValidationResult:
        options = validation_options or RtgControllerValidationOptions()
        with self._lock:
            resolved, generated_ids = self._resolve_batch_with_generated_ids(
                RtgChangeBatch(graph_changes=graph_changes)
            )
            self._validate_live_graph_lane(resolved.graph_changes)
            validation_report = self._change_validator.validate_batch(
                self._graph,
                self._schema,
                self._constraints,
                self._migration,
                self._query_engine,
                resolved,
                RtgValidationOptions(
                    tracks=options.tracks,
                    finding_limit=options.finding_limit,
                ),
            )
            return RtgControllerLiveGraphValidationResult(
                status="validated",
                mutation_state="not_mutated",
                accepted=validation_report.accepted,
                generated_ids=generated_ids,
                resolved_graph_changes=resolved.graph_changes,
                validation_report=validation_report,
            )

    def stage_knowledge_changes(
        self,
        knowledge_changes: RtgChangeBatch,
        validation_mode: str = "strict",
    ) -> RtgControllerOperationResult:
        return self._apply_normalized_change_batch(
            knowledge_changes,
            validation_mode=validation_mode,
            operation_name="stage_knowledge_changes",
        )

    def _apply_normalized_change_batch(
        self,
        change_batch: RtgChangeBatch,
        *,
        validation_mode: str,
        operation_name: str,
    ) -> RtgControllerOperationResult:
        if validation_mode not in {"strict", "skip"}:
            raise RtgControllerPreconditionFailed("validation_mode must be strict or skip")
        transaction_id = uuid4()
        with self._lock:
            resolved = self._resolve_batch(change_batch)
            if operation_name == "apply_live_graph_changes":
                self._validate_live_graph_lane(resolved.graph_changes)
            if operation_name == "stage_knowledge_changes":
                self._validate_knowledge_lane(resolved)
            request_failure = self._record_ledger(
                transaction_id, operation_name, "request", resolved
            )
            ledger_position = None if request_failure is not None else self._last_ledger_position
            ledger_failures = [request_failure] if request_failure is not None else []
            validation_report = None
            if validation_mode == "strict":
                validation_report = self._change_validator.validate_batch(
                    self._graph,
                    self._schema,
                    self._constraints,
                    self._migration,
                    self._query_engine,
                    resolved,
                    RtgValidationOptions(),
                )
                if not validation_report.accepted:
                    self._record_ledger(transaction_id, operation_name, "error", validation_report)
                    raise RtgControllerValidationFailed(
                        "change batch has blocking findings",
                        transaction_id=transaction_id,
                        validation_report=validation_report,
                    )
            preimage = self._capture_apply_preimage(resolved)
            try:
                applied = self._apply_resolved_batch(resolved)
            except Exception as error:
                self._restore_apply_preimage(preimage)
                self._record_ledger(transaction_id, operation_name, "error", str(error))
                raise RtgControllerApplyFailed(str(error)) from error
            result = RtgControllerOperationResult(
                status="applied",
                transaction_id=transaction_id,
                applied_changes=applied,
                validation_report=validation_report,
                details=_operation_details(operation_name, resolved),
            )
            response_failure = self._record_ledger(
                transaction_id, operation_name, "response", result
            )
            if response_failure is None:
                ledger_position = self._last_ledger_position
            result = dataclasses.replace(result, ledger_position=ledger_position)
            if response_failure is not None:
                ledger_failures.append(response_failure)
            if ledger_failures:
                result = dataclasses.replace(
                    result,
                    details=_with_ledger_degraded(result.details, ledger_failures),
                )
            return result

    def apply_migration_cutover(
        self,
        migration_id: str,
        cutover_options: RtgControllerCutoverOptions | None = None,
    ) -> RtgControllerOperationResult:
        options = cutover_options or RtgControllerCutoverOptions()
        if options.validation_mode not in {"strict", "skip"}:
            raise RtgControllerPreconditionFailed("validation_mode must be strict or skip")
        if options.failure_restore != "restore_pre_cutover_snapshot":
            raise RtgControllerPreconditionFailed(
                "failure_restore must be restore_pre_cutover_snapshot"
            )
        transaction_id = uuid4()
        with self._lock:
            pre_snapshot = self.export_system_snapshot()
            try:
                migration = self._migration.get_migration(migration_id)
                plan = RtgMigrationCutoverPlan.from_migration(migration)
            except Exception as error:
                raise RtgControllerPreconditionFailed(str(error)) from error
            request_payload = {
                "migration": migration,
                "options": options,
            }
            request_failure = self._record_ledger(
                transaction_id,
                "apply_migration_cutover",
                "request",
                request_payload,
            )
            ledger_position = None if request_failure is not None else self._last_ledger_position
            ledger_failures = [request_failure] if request_failure is not None else []
            validation_report = None
            if options.validation_mode == "strict":
                try:
                    self._assert_cutover_candidates_exist(plan)
                except Exception as error:
                    raise RtgControllerPreconditionFailed(str(error)) from error
                validation_report = self._change_validator.validate_batch(
                    self._graph,
                    self._schema,
                    self._constraints,
                    self._migration,
                    self._query_engine,
                    self._change_batch_from_cutover_plan(plan),
                    RtgValidationOptions(),
                )
                if not validation_report.accepted:
                    status_metadata = self._mark_migration_failed(
                        migration_id,
                        transaction_id=transaction_id,
                        summary="cutover validation has blocking findings",
                        validation_report=validation_report,
                    )
                    self._record_failed_cutover_response(
                        transaction_id,
                        migration_id=migration_id,
                        summary="cutover validation has blocking findings",
                        validation_report=validation_report,
                        status_metadata=status_metadata,
                    )
                    raise RtgControllerValidationFailed(
                        "cutover validation has blocking findings",
                        transaction_id=transaction_id,
                        validation_report=validation_report,
                        diagnostic=rtg_diagnostic(
                            code="controller.cutover.validation_failed",
                            category="migration_lifecycle",
                            path="rtg_apply_migration_cutover",
                            problem=(
                                "Strict cutover validation found blocking issues in the projected "
                                "post-cutover state."
                            ),
                            remedy=(
                                "Inspect validation_report findings, backfill or repair staged "
                                "candidates, retry cutover, or abandon the migration if it was an "
                                "intentional failed-evolution test."
                            ),
                            guide_topics=(
                                "workflow_patterns",
                                "recovery_and_replay",
                                "migration_history",
                            ),
                            mutation_state="live_state_preserved",
                        ),
                    )
            try:
                applied = self._apply_cutover_plan(
                    plan,
                    migration=migration,
                    options=options,
                    validate_actual_post_state=options.validation_mode == "strict",
                    transaction_id=transaction_id,
                )
            except Exception as error:
                try:
                    self.restore_from_snapshot(
                        pre_snapshot, RtgControllerRestoreOptions(ledger_mode="skip")
                    )
                except Exception as restore_error:
                    message = f"{error}; restore failed: {restore_error}"
                    self._record_ledger(
                        transaction_id,
                        "apply_migration_cutover",
                        "error",
                        message,
                    )
                    raise RtgControllerApplyFailed(message) from error
                status_metadata = self._mark_migration_failed(
                    migration_id,
                    transaction_id=transaction_id,
                    summary=str(error),
                    validation_report=(
                        error.validation_report
                        if isinstance(error, RtgControllerValidationFailed)
                        else None
                    ),
                )
                self._record_failed_cutover_response(
                    transaction_id,
                    migration_id=migration_id,
                    summary=str(error),
                    validation_report=(
                        error.validation_report
                        if isinstance(error, RtgControllerValidationFailed)
                        else None
                    ),
                    status_metadata=status_metadata,
                )
                if isinstance(error, RtgControllerValidationFailed):
                    raise
                raise RtgControllerApplyFailed(str(error)) from error
            result = RtgControllerOperationResult(
                status="cutover_applied",
                transaction_id=transaction_id,
                applied_changes=applied,
                validation_report=validation_report,
            )
            response_failure = self._record_ledger(
                transaction_id, "apply_migration_cutover", "response", result
            )
            if response_failure is None:
                ledger_position = self._last_ledger_position
            result = dataclasses.replace(result, ledger_position=ledger_position)
            if response_failure is not None:
                ledger_failures.append(response_failure)
            if ledger_failures:
                result = dataclasses.replace(
                    result,
                    details=_with_ledger_degraded({}, ledger_failures),
                )
            return result

    def execute_query(
        self,
        query_spec: RtgQuerySpec,
        query_options: RtgQueryOptions | None = None,
    ) -> RtgQueryResult:
        with self._lock:
            options = query_options or RtgQueryOptions(live_filter="live")
            return self._query_engine.execute(self._graph, query_spec, options)

    def get_object(self, object_uuid: UUID | str) -> RtgObject:
        with self._lock:
            try:
                return self._graph.get_object(object_uuid)
            except (RtgGraphObjectNotFound, RtgGraphUuidInvalid) as error:
                raise RtgControllerObjectNotFound(
                    str(error),
                    diagnostic=rtg_diagnostic(
                        code="controller.object.not_found",
                        category="request_input",
                        path="rtg_get_object.object_uuid",
                        problem="The requested graph object UUID is invalid or does not exist.",
                        remedy="Use a resource_id returned by a graph write or query result.",
                        guide_topics=("lookup_examples",),
                        mutation_state="not_mutated",
                    ),
                ) from error

    def list_migrations(self, status: str | None = None) -> RtgMigrationRecordList:
        with self._lock:
            return self._migration.list_migrations(status=status)

    def get_migration(self, migration_id: str) -> RtgMigrationRecord:
        with self._lock:
            return self._migration.get_migration(migration_id)

    def validate_graph(
        self,
        migration_ids: tuple[str, ...] | None = None,
        validation_options: RtgControllerValidationOptions | None = None,
    ) -> RtgValidationReport:
        with self._lock:
            options = validation_options or RtgControllerValidationOptions()
            return self._change_validator.validate_graph_state(
                self._graph,
                self._schema,
                self._constraints,
                self._migration,
                self._query_engine,
                migration_ids,
                RtgValidationOptions(tracks=options.tracks, finding_limit=options.finding_limit),
            )

    def discover_anchor_types(
        self,
        discovery_options: object | None = None,
    ) -> RtgAnchorTypeDiscoveryResult:
        with self._lock:
            include_non_live = bool(getattr(discovery_options, "include_non_live", False))
            limit = getattr(discovery_options, "limit", None)
            if limit is not None and limit <= 0:
                raise RtgControllerDiscoveryFailed("limit must be positive")
            live_filter = None if include_non_live else True
            counts = {
                item.type: item.count
                for item in self._graph.count_by_type(kind="anchor", live=True).counts
            }
            summaries = self._schema.list_anchor_type_summaries(live=live_filter).anchor_types
            entries = tuple(
                RtgAnchorTypeDiscoveryEntry(
                    type_key=item.type_key,
                    description=item.description,
                    live_count=counts.get(item.type_key, 0),
                )
                for item in summaries[:limit]
            )
            return RtgAnchorTypeDiscoveryResult(anchor_types=entries)

    def get_schema_pack(
        self,
        anchor_type_keys: tuple[str, ...],
        schema_pack_options: RtgControllerSchemaPackOptions | None = None,
    ) -> RtgControllerSchemaPack:
        with self._lock:
            options = schema_pack_options or RtgControllerSchemaPackOptions()
            try:
                pack = self._schema.get_schema_pack(anchor_type_keys, live=options.live)
            except Exception as error:
                raise RtgControllerDiscoveryFailed(str(error)) from error
            live_counts = {}
            if options.include_live_counts:
                for count in self._graph.count_by_type(live=True).counts:
                    live_counts[count.type] = count.count
            return RtgControllerSchemaPack(schema_pack=pack, live_counts=live_counts)

    def get_system_state(self) -> RtgControllerSystemState:
        with self._lock:
            live_schema = self._schema.list_definitions(live=True).definitions
            non_live_schema = self._schema.list_definitions(live=False).definitions
            non_live_constraints = self._constraints.list_constraints(live=False).constraints
            live_graph_counts = self._graph.count_by_type(live=True).counts
            non_live_graph_counts = self._graph.count_by_type(live=False).counts
            migrations = self._migration.list_migrations().migrations
            migration_counts = {
                status: sum(1 for item in migrations if item.status == status)
                for status in ("draft", "ready", "failed", "applied", "abandoned")
            }
            persisted_snapshot_paths = tuple(
                str(item["relative_path"]) for item in self.list_persisted_snapshots().snapshots
            )
            live_graph_total = sum(item.count for item in live_graph_counts)
            ledger_record_count = self._ledger_record_count()
            staged_work = bool(
                non_live_schema
                or non_live_constraints
                or non_live_graph_counts
                or migration_counts["draft"]
                or migration_counts["ready"]
                or migration_counts["failed"]
            )
            if ledger_record_count and not live_schema and live_graph_total == 0 and not migrations:
                classification = "needs_replay"
            elif staged_work:
                classification = "has_staged_work"
            elif live_graph_total:
                classification = "populated"
            elif live_schema:
                classification = "schema_only"
            else:
                classification = "empty"
            migration_history_available = (
                not any(migration_counts.values()) and self._migration_history_event_count() > 0
            )
            recommended_next_steps = list(_recommended_next_steps(classification))
            if migration_history_available:
                recommended_next_steps.append(
                    "Current migration counts are for the in-memory migration store. "
                    "Call rtg_list_migration_history for ledger-backed staged, applied, failed, "
                    "and abandoned migration events."
                )
            return RtgControllerSystemState(
                state_classification=classification,
                live_schema_counts=RtgControllerSchemaCounts(
                    anchor=sum(1 for item in live_schema if item.kind == "anchor"),
                    data_object=sum(1 for item in live_schema if item.kind == "data_object"),
                    link=sum(1 for item in live_schema if item.kind == "link"),
                    total=len(live_schema),
                ),
                live_object_counts=RtgTypeCountList(counts=tuple(live_graph_counts)),
                non_live_candidate_counts=RtgControllerCandidateCounts(
                    schema=len(non_live_schema),
                    constraints=len(non_live_constraints),
                    graph=sum(item.count for item in non_live_graph_counts),
                    total=(
                        len(non_live_schema)
                        + len(non_live_constraints)
                        + sum(item.count for item in non_live_graph_counts)
                    ),
                ),
                migration_counts_by_status=RtgControllerMigrationCounts(
                    draft=migration_counts["draft"],
                    ready=migration_counts["ready"],
                    failed=migration_counts["failed"],
                    applied=migration_counts["applied"],
                    abandoned=migration_counts["abandoned"],
                    total=sum(migration_counts.values()),
                ),
                persisted_snapshot_paths=persisted_snapshot_paths,
                ledger_record_count=ledger_record_count,
                migration_counts_scope="current_migration_store",
                migration_history_hint=(
                    "Current migration counts are clean; ledger-backed migration events are "
                    "available through rtg_list_migration_history."
                    if migration_history_available
                    else None
                ),
                last_ledger_position=self._last_ledger_position,
                last_transaction_id=self._last_transaction_id,
                recommended_workflows=_recommended_workflows(classification),
                recommended_next_steps=tuple(recommended_next_steps),
            )

    def export_system_snapshot(self) -> RtgSystemSnapshot:
        with self._lock:
            return RtgSystemSnapshot(
                graph=self._graph.export_snapshot(),
                schema=self._schema.export_snapshot(),
                constraints=self._constraints.export_snapshot(),
                migration=self._migration.export_snapshot(),
                last_ledger_position=self._last_ledger_position,
                last_transaction_id=self._last_transaction_id,
                last_transaction_timestamp=self._last_transaction_timestamp,
            )

    def persist_system_snapshot(self, relative_path: str) -> RtgControllerOperationResult:
        with self._lock:
            transaction_id = uuid4()
            snapshot = self.export_system_snapshot()
            try:
                self._json_storage.write(relative_path, _to_json_value(snapshot))
            except Exception as error:
                raise RtgControllerSnapshotFailed(str(error)) from error
            result = RtgControllerOperationResult(
                status="snapshot_persisted",
                transaction_id=transaction_id,
                snapshot=snapshot,
            )
            ledger_failure = self._record_ledger(
                transaction_id, "persist_system_snapshot", "response", result
            )
            ledger_position = None if ledger_failure is not None else self._last_ledger_position
            result = dataclasses.replace(result, ledger_position=ledger_position)
            if ledger_failure is not None:
                result = dataclasses.replace(
                    result,
                    details=_with_ledger_degraded({}, [ledger_failure]),
                )
            return result

    def list_persisted_snapshots(self) -> RtgPersistedSnapshotList:
        with self._lock:
            snapshots: list[JsonObject] = []
            try:
                documents = self._json_storage.list(".").documents
            except Exception as error:
                raise RtgControllerSnapshotFailed(str(error)) from error
            for metadata in documents:
                try:
                    document = self._json_storage.read(metadata.relative_path)
                    if not _looks_like_system_snapshot(document.value):
                        continue
                except Exception:
                    continue
                snapshots.append(
                    {
                        "relative_path": metadata.relative_path,
                        "size_bytes": metadata.size_bytes,
                        "modified_at": metadata.modified_at.isoformat(),
                    }
                )
            return RtgPersistedSnapshotList(snapshots=tuple(snapshots))

    def load_persisted_snapshot(self, relative_path: str) -> RtgPersistedSnapshotDocument:
        with self._lock:
            try:
                document = self._json_storage.read(relative_path)
                snapshot = _system_snapshot_from_json(document.value)
            except Exception as error:
                raise RtgControllerSnapshotFailed(
                    str(error),
                    diagnostic=rtg_diagnostic(
                        code="controller.snapshot.load_failed",
                        category="snapshot_recovery",
                        path="relative_path",
                        problem="The requested persisted snapshot could not be loaded.",
                        remedy=(
                            "Call rtg_list_persisted_snapshots and retry with one of the returned "
                            "JSON File Storage relative paths."
                        ),
                        minimal_example={"relative_path": "snapshots/run.json"},
                        guide_topics=("workflow_patterns", "recovery_and_replay"),
                        mutation_state="not_mutated",
                    ),
                ) from error
            return RtgPersistedSnapshotDocument(relative_path=relative_path, snapshot=snapshot)

    def abandon_migration(
        self,
        migration_id: str,
        reason: str | None = None,
    ) -> RtgControllerOperationResult:
        transaction_id = uuid4()
        with self._lock:
            try:
                migration = self._migration.get_migration(migration_id)
            except Exception as error:
                raise RtgControllerPreconditionFailed(str(error)) from error
            request_failure = self._record_ledger(
                transaction_id,
                "abandon_migration",
                "request",
                {"migration_id": migration_id, "reason": reason},
            )
            details = self._apply_abandon_migration(
                migration_id,
                reason=reason,
                transaction_id=transaction_id,
                migration=migration,
            )
            result = RtgControllerOperationResult(
                status="migration_abandoned",
                transaction_id=transaction_id,
                details=details,
            )
            response_failure = self._record_ledger(
                transaction_id, "abandon_migration", "response", result
            )
            ledger_position = self._last_ledger_position if response_failure is None else None
            result = dataclasses.replace(result, ledger_position=ledger_position)
            failures = [
                failure for failure in (request_failure, response_failure) if failure is not None
            ]
            if failures:
                result = dataclasses.replace(
                    result,
                    details=_with_ledger_degraded(result.details, failures),
                )
            return result

    def restore_from_snapshot(
        self,
        snapshot: RtgSystemSnapshot,
        restore_options: RtgControllerRestoreOptions | None = None,
    ) -> RtgControllerOperationResult:
        with self._lock:
            options = restore_options or RtgControllerRestoreOptions()
            if options.ledger_mode not in {"record", "skip"}:
                raise RtgControllerSnapshotFailed("ledger_mode must be record or skip")
            transaction_id = uuid4()
            should_record = options.ledger_mode == "record"
            ledger_position = None
            ledger_failures: list[RtgControllerLedgerFailureRecord] = []
            if should_record:
                request_failure = self._record_ledger(
                    transaction_id,
                    "restore_from_snapshot",
                    "request",
                    {"snapshot": snapshot, "options": options},
                )
                ledger_position = (
                    None if request_failure is not None else self._last_ledger_position
                )
                if request_failure is not None:
                    ledger_failures.append(request_failure)
            try:
                candidate_graph = type(self._graph).import_snapshot(snapshot.graph)
                candidate_schema = type(self._schema).import_snapshot(snapshot.schema)
                candidate_constraints = type(self._constraints).import_snapshot(
                    snapshot.constraints
                )
                candidate_migration = type(self._migration).import_snapshot(snapshot.migration)
                validation_report = self._change_validator.validate_graph_state(
                    candidate_graph,
                    candidate_schema,
                    candidate_constraints,
                    candidate_migration,
                    self._query_engine,
                    validation_options=RtgValidationOptions(),
                )
                if not validation_report.accepted:
                    codes = ", ".join(
                        sorted({finding.code for finding in validation_report.findings})
                    )
                    raise RtgControllerSnapshotFailed(
                        f"snapshot state violates controller invariants: {codes}",
                        diagnostic=rtg_diagnostic(
                            code="controller.snapshot.semantic_validation_failed",
                            category="snapshot_recovery",
                            path="snapshot",
                            problem=(
                                "The coordinated snapshot is structurally valid but "
                                "semantically inconsistent."
                            ),
                            remedy=(
                                "Repair or select a snapshot whose graph, schema, constraints, "
                                "and migration state validate together."
                            ),
                            mutation_state="live_state_preserved",
                        ),
                    )
                (
                    self._graph,
                    self._schema,
                    self._constraints,
                    self._migration,
                    self._last_ledger_position,
                    self._last_transaction_id,
                    self._last_transaction_timestamp,
                ) = (
                    candidate_graph,
                    candidate_schema,
                    candidate_constraints,
                    candidate_migration,
                    snapshot.last_ledger_position,
                    snapshot.last_transaction_id,
                    snapshot.last_transaction_timestamp,
                )
            except Exception as error:
                if should_record:
                    self._record_ledger(
                        transaction_id, "restore_from_snapshot", "error", str(error)
                    )
                raise RtgControllerSnapshotFailed(str(error)) from error
            result = RtgControllerOperationResult(
                status="restore_applied", transaction_id=transaction_id
            )
            if should_record:
                ledger_failure = self._record_ledger(
                    transaction_id, "restore_from_snapshot", "response", result
                )
                if ledger_failure is None:
                    ledger_position = self._last_ledger_position
                result = dataclasses.replace(result, ledger_position=ledger_position)
                if ledger_failure is not None:
                    ledger_failures.append(ledger_failure)
                if ledger_failures:
                    result = dataclasses.replace(
                        result,
                        details=_with_ledger_degraded({}, ledger_failures),
                    )
            return result

    def replay_ledger(
        self,
        replay_options: RtgControllerReplayOptions | None = None,
    ) -> RtgControllerOperationResult:
        with self._lock:
            options = replay_options or RtgControllerReplayOptions()
            start_source = _replay_start_source(options)
            start_snapshot = self._resolve_replay_start_snapshot(options)
            if start_snapshot is not None:
                self.restore_from_snapshot(
                    start_snapshot, RtgControllerRestoreOptions(ledger_mode="skip")
                )
            elif not self._controller_state_empty():
                raise RtgControllerReplayFailed(
                    "replay requires an empty controller state or an explicit start snapshot; "
                    "valid next actions are: restart or open a fresh controller against the "
                    "same ledger, call replay from empty state, load a persisted snapshot "
                    "and pass it as replay_options.start_snapshot, or pass "
                    "replay_options.start_snapshot_path with a JSON File Storage snapshot path",
                    diagnostic=rtg_diagnostic(
                        code="controller.replay.non_empty_state",
                        category="replay_precondition",
                        path="replay_options",
                        problem="Replay without a start snapshot can only run into empty state.",
                        remedy=(
                            "Restart/open a fresh controller, or provide start_snapshot or "
                            "start_snapshot_path for snapshot-seeded replay."
                        ),
                        minimal_example={
                            "replay_options": {"start_snapshot_path": "snapshots/run.json"}
                        },
                        guide_topics=("workflow_patterns", "recovery_and_replay"),
                        mutation_state="not_mutated",
                    ),
                )
            after = options.after_ledger_position
            if after is None and start_snapshot is not None:
                after = start_snapshot.last_ledger_position
            where = []
            params: list[int] = []
            if after is not None:
                where.append("ledger_position > ?")
                params.append(after)
            if options.through_ledger_position is not None:
                where.append("ledger_position <= ?")
                params.append(options.through_ledger_position)
            clause = f"where {' and '.join(where)}" if where else ""
            statement = (
                "select ledger_position, transaction_id, operation_name, record_kind, "
                "payload_json, recorded_at "
                f"from rtg_controller_ledger {clause} order by ledger_position"
            )
            rows = self._sql_storage.query(statement, tuple(params)).rows
            replay_window = _replay_window(
                start_source=start_source,
                start_snapshot=start_snapshot,
                effective_after_ledger_position=after,
                through_ledger_position=options.through_ledger_position,
                ledger_records_seen=len(rows),
            )
            successful_transactions = _successful_transaction_metadata(rows)
            replayed = 0
            for row in rows:
                if row["record_kind"] != "request":
                    continue
                transaction_id_text = str(row["transaction_id"])
                if transaction_id_text not in successful_transactions:
                    continue
                operation_name = str(row["operation_name"])
                payload_json = row["payload_json"]
                if not isinstance(payload_json, str):
                    raise RtgControllerReplayFailed("ledger payload is not JSON text")
                payload = json.loads(payload_json)
                try:
                    if operation_name in {"apply_live_graph_changes", "stage_knowledge_changes"}:
                        self._apply_resolved_batch(_change_batch_from_json(payload))
                        replayed += 1
                    elif operation_name == "apply_migration_cutover":
                        request = _object(payload)
                        transaction = successful_transactions[transaction_id_text]
                        if transaction.status == "cutover_failed":
                            response_details = _object(
                                transaction.response_payload.get("details", {})
                            )
                            migration_id = str(
                                response_details.get("migration_id")
                                or _object(request["migration"])["migration_id"]
                            )
                            status_metadata = _object(response_details.get("status_metadata", {}))
                            self._set_migration_failed_metadata(
                                migration_id,
                                status_metadata=cast(JsonObject, status_metadata),
                            )
                        else:
                            migration = _migration_record_from_json(request["migration"])
                            options_value = _cutover_options_from_json(request.get("options", {}))
                            self._apply_cutover_plan(
                                RtgMigrationCutoverPlan.from_migration(migration),
                                migration=migration,
                                options=options_value,
                                validate_actual_post_state=False,
                                transaction_id=None,
                            )
                        replayed += 1
                    elif operation_name == "restore_from_snapshot":
                        request = _object(payload)
                        self.restore_from_snapshot(
                            _system_snapshot_from_json(request["snapshot"]),
                            RtgControllerRestoreOptions(ledger_mode="skip"),
                        )
                        replayed += 1
                    elif operation_name == "abandon_migration":
                        request = _object(payload)
                        self._apply_abandon_migration(
                            str(request["migration_id"]),
                            reason=(
                                str(request["reason"])
                                if request.get("reason") is not None
                                else None
                            ),
                            transaction_id=None,
                        )
                        replayed += 1
                    else:
                        raise RtgControllerReplayFailed(operation_name)
                    transaction = successful_transactions[transaction_id_text]
                    self._last_ledger_position = transaction.ledger_position
                    self._last_transaction_id = UUID(transaction_id_text)
                    self._last_transaction_timestamp = transaction.recorded_at
                except Exception as error:
                    raise RtgControllerReplayFailed(str(error)) from error
            return RtgControllerOperationResult(
                status="replay_applied",
                transaction_id=uuid4(),
                details={
                    "ledger_records_seen": len(rows),
                    "mutating_requests_replayed": replayed,
                    "replay_window": replay_window,
                },
            )

    def verify_replay_from_ledger(
        self,
        replay_options: RtgControllerReplayOptions | None = None,
    ) -> RtgControllerReplayVerificationResult:
        with self._lock:
            options = replay_options or RtgControllerReplayOptions()
            start_source = _replay_start_source(options)
            preserved = self.export_system_snapshot()
            start_snapshot = self._resolve_replay_start_snapshot(options)
            if start_snapshot is None:
                start_snapshot = self._empty_system_snapshot()
            pre_summary = _snapshot_summary(start_snapshot)
            try:
                replay_result = self.replay_ledger(
                    dataclasses.replace(
                        options, start_snapshot=start_snapshot, start_snapshot_path=None
                    )
                )
                post_snapshot = self.export_system_snapshot()
                validation_report = self.validate_graph()
                return RtgControllerReplayVerificationResult(
                    status="replay_verified",
                    ledger_records_seen=_json_int(replay_result.details.get("ledger_records_seen")),
                    mutating_requests_replayed=int(
                        _json_int(replay_result.details.get("mutating_requests_replayed"))
                    ),
                    replay_window=cast(
                        JsonObject,
                        {
                            **_object(replay_result.details.get("replay_window", {})),
                            "start_source": start_source,
                        },
                    ),
                    pre_summary=pre_summary,
                    post_summary=_snapshot_summary(post_snapshot),
                    count_diffs=_summary_count_diffs(pre_summary, _snapshot_summary(post_snapshot)),
                    validation_report=validation_report,
                )
            finally:
                self.restore_from_snapshot(
                    preserved, RtgControllerRestoreOptions(ledger_mode="skip")
                )

    def list_migration_history(self) -> RtgControllerMigrationHistory:
        with self._lock:
            rows = self._sql_storage.query(
                """
                select ledger_position, transaction_id, operation_name, record_kind,
                    payload_json, recorded_at
                from rtg_controller_ledger
                order by ledger_position
                """
            ).rows
            successful_transactions = _successful_transaction_metadata(rows)
            events: list[JsonObject] = []
            for row in rows:
                if row["record_kind"] != "request":
                    continue
                transaction_id_text = str(row["transaction_id"])
                transaction = successful_transactions.get(transaction_id_text)
                if transaction is None:
                    continue
                payload_json = row["payload_json"]
                if not isinstance(payload_json, str):
                    continue
                try:
                    payload = _object(json.loads(payload_json))
                except Exception:
                    continue
                events.extend(
                    _migration_history_events_for_request(
                        operation_name=str(row["operation_name"]),
                        payload=cast(JsonObject, payload),
                        transaction_id=transaction_id_text,
                        ledger_position=transaction.ledger_position,
                        recorded_at=transaction.recorded_at,
                        response_payload=transaction.response_payload,
                    )
                )
            return RtgControllerMigrationHistory(events=tuple(events))

    def flush_ledger_failures(self) -> RtgControllerOperationResult:
        with self._lock:
            self._load_persisted_ledger_failures()
            remaining: list[RtgControllerLedgerFailureRecord] = []
            flushed = 0
            for record in self._ledger_failures:
                try:
                    result = self._sql_storage.execute(
                        """
                        insert into rtg_controller_ledger
                            (transaction_id, operation_name, record_kind, payload_json, recorded_at)
                        values (?, ?, ?, ?, ?)
                        """,
                        (
                            str(record.transaction_id),
                            record.operation_name,
                            record.record_kind,
                            record.payload_json,
                            record.last_failed_timestamp,
                        ),
                    )
                    self._last_ledger_position = result.last_inserted_row_id
                    self._last_transaction_id = record.transaction_id
                    self._last_transaction_timestamp = record.last_failed_timestamp
                    flushed += 1
                except Exception:
                    remaining.append(record)
            self._ledger_failures = remaining
            self._persist_ledger_failures()
            return RtgControllerOperationResult(
                status="ledger_failures_flushed",
                transaction_id=uuid4(),
                ledger_position=self._last_ledger_position if flushed else None,
                details={"flushed": flushed, "remaining": len(remaining)},
            )

    def _apply_abandon_migration(
        self,
        migration_id: str,
        *,
        reason: str | None,
        transaction_id: UUID | None,
        migration: RtgMigrationRecord | None = None,
    ) -> JsonObject:
        current = migration or self._migration.get_migration(migration_id)
        if current.status == "applied":
            raise RtgControllerPreconditionFailed("applied migrations cannot be abandoned")
        if current.status != "abandoned":
            self._migration.set_status(
                migration_id,
                "abandoned",
                {
                    "reason": reason or "abandoned through controller",
                    "transaction_id": str(transaction_id) if transaction_id is not None else None,
                },
            )
        shared = self._make_live_references_excluding(migration_id)
        pruned: dict[str, list[str]] = {"schema": [], "constraints": [], "graph": []}
        skipped: dict[str, list[JsonObject]] = {"schema": [], "constraints": [], "graph": []}

        for uuid_value in current.schema_make_live:
            if uuid_value in shared["schema"]:
                skipped["schema"].append({"resource_id": str(uuid_value), "reason": "shared"})
                continue
            try:
                definition = self._schema.get_definition(uuid_value)
            except Exception:
                skipped["schema"].append({"resource_id": str(uuid_value), "reason": "missing"})
                continue
            if _system_live(definition.system):
                skipped["schema"].append({"resource_id": str(uuid_value), "reason": "live"})
                continue
            self._schema.delete_definition(uuid_value)
            pruned["schema"].append(str(uuid_value))

        for uuid_value in current.constraint_make_live:
            if uuid_value in shared["constraints"]:
                skipped["constraints"].append({"resource_id": str(uuid_value), "reason": "shared"})
                continue
            try:
                constraint = self._constraints.get_constraint(uuid_value)
            except Exception:
                skipped["constraints"].append({"resource_id": str(uuid_value), "reason": "missing"})
                continue
            if _system_live(constraint.system):
                skipped["constraints"].append({"resource_id": str(uuid_value), "reason": "live"})
                continue
            self._constraints.delete_constraint(uuid_value)
            pruned["constraints"].append(str(uuid_value))

        for uuid_value in current.graph_make_live:
            if uuid_value in shared["graph"]:
                skipped["graph"].append({"resource_id": str(uuid_value), "reason": "shared"})
                continue
            try:
                graph_object = self._graph.get_object(uuid_value)
            except Exception:
                skipped["graph"].append({"resource_id": str(uuid_value), "reason": "missing"})
                continue
            if _system_live(graph_object.system):
                skipped["graph"].append({"resource_id": str(uuid_value), "reason": "live"})
                continue
            _delete_graph_if_present(self._graph, uuid_value)
            pruned["graph"].append(str(uuid_value))

        deleted_migration = self._migration.delete_migration(migration_id).deleted_migration
        return {
            "migration_id": migration_id,
            "abandoned_status": "abandoned",
            "deleted_migration_status": deleted_migration.status,
            "reason": reason,
            "pruned_candidates": cast(JsonObject, pruned),
            "skipped_candidates": cast(JsonObject, skipped),
        }

    def _make_live_references_excluding(self, migration_id: str) -> dict[str, set[UUID]]:
        shared: dict[str, set[UUID]] = {"schema": set(), "constraints": set(), "graph": set()}
        for migration in self._migration.list_migrations().migrations:
            if migration.migration_id == migration_id:
                continue
            shared["schema"].update(migration.schema_make_live)
            shared["constraints"].update(migration.constraint_make_live)
            shared["graph"].update(migration.graph_make_live)
        return shared

    def _mark_migration_failed(
        self,
        migration_id: str,
        *,
        transaction_id: UUID,
        summary: str,
        validation_report: RtgValidationReport | None,
    ) -> JsonObject:
        metadata: JsonObject = {
            "transaction_id": str(transaction_id),
            "summary": summary,
        }
        if validation_report is not None:
            metadata["validation_report"] = cast(JsonObject, _to_json_value(validation_report))
        try:
            current = self._migration.get_migration(migration_id)
            if current.status in {"applied", "abandoned"}:
                return metadata
            if current.status == "draft":
                self._migration.set_status(migration_id, "ready")
            self._migration.set_status(migration_id, "failed", metadata)
        except Exception:
            return metadata
        return metadata

    def _set_migration_failed_metadata(
        self,
        migration_id: str,
        *,
        status_metadata: JsonObject,
    ) -> None:
        current = self._migration.get_migration(migration_id)
        if current.status in {"applied", "abandoned"}:
            return
        if current.status == "draft":
            self._migration.set_status(migration_id, "ready")
        self._migration.set_status(migration_id, "failed", status_metadata)

    def _record_failed_cutover_response(
        self,
        transaction_id: UUID,
        *,
        migration_id: str,
        summary: str,
        validation_report: RtgValidationReport | None,
        status_metadata: JsonObject,
    ) -> None:
        self._record_ledger(
            transaction_id,
            "apply_migration_cutover",
            "response",
            RtgControllerOperationResult(
                status="cutover_failed",
                transaction_id=transaction_id,
                validation_report=validation_report,
                details={
                    "migration_id": migration_id,
                    "summary": summary,
                    "status_metadata": status_metadata,
                },
            ),
        )

    def _ledger_record_count(self) -> int:
        try:
            rows = self._sql_storage.query(
                "select count(*) as count from rtg_controller_ledger"
            ).rows
        except Exception:
            return 0
        if not rows:
            return 0
        value = rows[0].get("count")
        return int(cast(int, value)) if value is not None else 0

    def _resolve_batch(self, batch: RtgChangeBatch) -> RtgChangeBatch:
        return self._resolve_batch_with_generated_ids(batch)[0]

    def _resolve_batch_with_generated_ids(
        self, batch: RtgChangeBatch
    ) -> tuple[RtgChangeBatch, dict[str, UUID]]:
        resolved: dict[str, UUID | str] = {}
        generated_ids: dict[str, UUID] = {}

        def resolve_uuid(ref: RtgChangeReference) -> UUID:
            if isinstance(ref.resource_id, UUID):
                return ref.resource_id
            if isinstance(ref.resource_id, str):
                return UUID(ref.resource_id)
            if ref.local_ref is None:
                raise RtgControllerPreconditionFailed("missing local reference")
            if ref.local_ref not in resolved:
                generated = uuid4()
                resolved[ref.local_ref] = generated
                generated_ids[ref.local_ref] = generated
            value = resolved[ref.local_ref]
            if not isinstance(value, UUID):
                raise RtgControllerPreconditionFailed("local reference kind mismatch")
            return value

        def resolve_migration_id(ref: RtgChangeReference) -> str:
            if ref.resource_id is not None:
                return str(ref.resource_id)
            if ref.local_ref is None:
                raise RtgControllerPreconditionFailed("missing migration local reference")
            value = resolved.setdefault(ref.local_ref, str(uuid4()))
            if not isinstance(value, str):
                raise RtgControllerPreconditionFailed("local reference kind mismatch")
            return value

        graph_changes = RtgGraphChangeSet(
            anchor_writes=tuple(
                RtgGraphAnchorWrite(
                    ref=RtgChangeReference(resource_id=resolve_uuid(write.ref)),
                    type=write.type,
                    display_name=write.display_name,
                    system=write.system,
                )
                for write in batch.graph_changes.anchor_writes
            ),
            data_object_writes=tuple(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(resource_id=resolve_uuid(write.ref)),
                    type=write.type,
                    properties=write.properties,
                    system=write.system,
                    anchor_refs=tuple(
                        RtgChangeReference(resource_id=resolve_uuid(ref))
                        for ref in write.anchor_refs
                    ),
                )
                for write in batch.graph_changes.data_object_writes
            ),
            link_writes=tuple(
                RtgGraphLinkWrite(
                    ref=RtgChangeReference(resource_id=resolve_uuid(write.ref)),
                    type=write.type,
                    source_ref=RtgChangeReference(resource_id=resolve_uuid(write.source_ref)),
                    target_ref=RtgChangeReference(resource_id=resolve_uuid(write.target_ref)),
                    system=write.system,
                )
                for write in batch.graph_changes.link_writes
            ),
            delete_anchors=tuple(
                RtgChangeReference(resource_id=resolve_uuid(ref))
                for ref in batch.graph_changes.delete_anchors
            ),
            delete_data_objects=tuple(
                RtgChangeReference(resource_id=resolve_uuid(ref))
                for ref in batch.graph_changes.delete_data_objects
            ),
            delete_links=tuple(
                RtgChangeReference(resource_id=resolve_uuid(ref))
                for ref in batch.graph_changes.delete_links
            ),
            associate_data=tuple(
                RtgGraphAssociationChange(
                    anchor_ref=RtgChangeReference(resource_id=resolve_uuid(change.anchor_ref)),
                    data_ref=RtgChangeReference(resource_id=resolve_uuid(change.data_ref)),
                )
                for change in batch.graph_changes.associate_data
            ),
            dissociate_data=tuple(
                RtgGraphAssociationChange(
                    anchor_ref=RtgChangeReference(resource_id=resolve_uuid(change.anchor_ref)),
                    data_ref=RtgChangeReference(resource_id=resolve_uuid(change.data_ref)),
                )
                for change in batch.graph_changes.dissociate_data
            ),
            set_live=tuple(
                RtgGraphLiveStatusChange(
                    object_ref=RtgChangeReference(resource_id=resolve_uuid(change.object_ref)),
                    live=change.live,
                )
                for change in batch.graph_changes.set_live
            ),
        )
        schema_changes = RtgSchemaChangeSet(
            definition_writes=tuple(
                RtgSchemaDefinitionWrite(
                    ref=RtgChangeReference(resource_id=resolve_uuid(write.ref)),
                    definition=dataclasses.replace(write.definition, uuid=resolve_uuid(write.ref)),
                )
                for write in batch.schema_changes.definition_writes
            ),
            delete_definitions=tuple(
                RtgChangeReference(resource_id=resolve_uuid(ref))
                for ref in batch.schema_changes.delete_definitions
            ),
            set_live=tuple(
                RtgLiveStatusChange(
                    target_ref=RtgChangeReference(resource_id=resolve_uuid(change.target_ref)),
                    live=change.live,
                )
                for change in batch.schema_changes.set_live
            ),
        )
        constraint_changes = RtgConstraintChangeSet(
            constraint_writes=tuple(
                RtgConstraintDefinitionWrite(
                    ref=RtgChangeReference(resource_id=resolve_uuid(write.ref)),
                    constraint=dataclasses.replace(write.constraint, uuid=resolve_uuid(write.ref)),
                )
                for write in batch.constraint_changes.constraint_writes
            ),
            delete_constraints=tuple(
                RtgChangeReference(resource_id=resolve_uuid(ref))
                for ref in batch.constraint_changes.delete_constraints
            ),
            set_live=tuple(
                RtgLiveStatusChange(
                    target_ref=RtgChangeReference(resource_id=resolve_uuid(change.target_ref)),
                    live=change.live,
                )
                for change in batch.constraint_changes.set_live
            ),
        )
        migration_changes = RtgMigrationChangeSet(
            migration_writes=tuple(
                RtgMigrationRecordWrite(
                    ref=RtgChangeReference(resource_id=resolve_migration_id(write.ref)),
                    migration=dataclasses.replace(
                        write.migration, migration_id=resolve_migration_id(write.ref)
                    ),
                )
                for write in batch.migration_changes.migration_writes
            ),
            delete_migrations=tuple(
                RtgChangeReference(resource_id=resolve_migration_id(ref))
                for ref in batch.migration_changes.delete_migrations
            ),
            status_changes=tuple(
                RtgMigrationStatusChange(
                    migration_ref=RtgChangeReference(
                        resource_id=resolve_migration_id(change.migration_ref)
                    ),
                    status=change.status,
                    status_metadata=change.status_metadata,
                )
                for change in batch.migration_changes.status_changes
            ),
            evidence_additions=tuple(
                RtgMigrationEvidenceAddition(
                    migration_ref=RtgChangeReference(
                        resource_id=resolve_migration_id(change.migration_ref)
                    ),
                    evidence=change.evidence,
                )
                for change in batch.migration_changes.evidence_additions
            ),
        )
        return (
            RtgChangeBatch(
                graph_changes=graph_changes,
                schema_changes=schema_changes,
                constraint_changes=constraint_changes,
                migration_changes=migration_changes,
            ),
            generated_ids,
        )

    def _apply_resolved_batch(self, batch: RtgChangeBatch) -> RtgControllerAppliedChanges:
        graph_writes = 0
        for write in batch.graph_changes.anchor_writes:
            self._graph.put_anchor(
                RtgAnchor(
                    uuid=_uuid_ref(write.ref),
                    type=write.type,
                    display_name=write.display_name,
                    system=write.system,
                )
            )
            graph_writes += 1
        for write in batch.graph_changes.data_object_writes:
            self._graph.put_data_object(
                RtgDataObject(
                    uuid=_uuid_ref(write.ref),
                    type=write.type,
                    properties=write.properties,
                    system=write.system,
                ),
                tuple(_uuid_ref(ref) for ref in write.anchor_refs),
            )
            graph_writes += 1
        for write in batch.graph_changes.link_writes:
            self._graph.put_link(
                RtgLink(
                    uuid=_uuid_ref(write.ref),
                    type=write.type,
                    source_uuid=_uuid_ref(write.source_ref),
                    target_uuid=_uuid_ref(write.target_ref),
                    system=write.system,
                )
            )
            graph_writes += 1
        for change in batch.graph_changes.associate_data:
            self._graph.associate_data(_uuid_ref(change.anchor_ref), _uuid_ref(change.data_ref))
        for change in batch.graph_changes.dissociate_data:
            self._graph.dissociate_data(_uuid_ref(change.anchor_ref), _uuid_ref(change.data_ref))
        for write in batch.schema_changes.definition_writes:
            self._schema.put_definition(write.definition)
        for write in batch.constraint_changes.constraint_writes:
            self._constraints.put_constraint(write.constraint)
        for write in batch.migration_changes.migration_writes:
            self._migration.put_migration(write.migration)
        deletes = 0
        for ref in batch.graph_changes.delete_links:
            self._graph.delete_link(_uuid_ref(ref))
            deletes += 1
        for ref in batch.graph_changes.delete_data_objects:
            self._graph.delete_data_object(_uuid_ref(ref))
            deletes += 1
        for ref in batch.graph_changes.delete_anchors:
            self._graph.delete_anchor(_uuid_ref(ref))
            deletes += 1
        for ref in batch.schema_changes.delete_definitions:
            self._schema.delete_definition(_uuid_ref(ref))
            deletes += 1
        for ref in batch.constraint_changes.delete_constraints:
            self._constraints.delete_constraint(_uuid_ref(ref))
            deletes += 1
        live_status_changes = 0
        for change in batch.graph_changes.set_live:
            self._apply_graph_live_flips((_uuid_ref(change.object_ref),), change.live)
            live_status_changes += 1
        for change in batch.schema_changes.set_live:
            self._apply_registry_live_flips((_uuid_ref(change.target_ref),), change.live, "schema")
            live_status_changes += 1
        for change in batch.constraint_changes.set_live:
            self._apply_registry_live_flips(
                (_uuid_ref(change.target_ref),), change.live, "constraint"
            )
            live_status_changes += 1
        for change in batch.migration_changes.status_changes:
            self._migration.set_status(
                _text_ref(change.migration_ref), change.status, change.status_metadata
            )
        for change in batch.migration_changes.evidence_additions:
            self._migration.add_evidence(_text_ref(change.migration_ref), change.evidence)
        for ref in batch.migration_changes.delete_migrations:
            self._migration.delete_migration(_text_ref(ref))
            deletes += 1
        return RtgControllerAppliedChanges(
            graph_writes=graph_writes,
            schema_writes=len(batch.schema_changes.definition_writes),
            constraint_writes=len(batch.constraint_changes.constraint_writes),
            migration_writes=len(batch.migration_changes.migration_writes),
            deletes=deletes,
            live_status_changes=live_status_changes,
        )

    def _apply_registry_live_flips(
        self,
        definition_uuids: tuple[UUID, ...],
        live: bool,
        registry: str,
    ) -> None:
        for uuid_value in definition_uuids:
            if registry == "schema":
                definition = self._schema.get_definition(uuid_value)
                self._schema.put_definition(
                    dataclasses.replace(definition, system={**definition.system, "live": live})
                )
            else:
                constraint = self._constraints.get_constraint(uuid_value)
                self._constraints.put_constraint(
                    dataclasses.replace(constraint, system={**constraint.system, "live": live})
                )

    def _apply_graph_live_flips(self, object_uuids: tuple[UUID, ...], live: bool) -> None:
        for uuid_value in object_uuids:
            obj = self._graph.get_object(uuid_value)
            system = {**obj.system, "live": live}
            if isinstance(obj, RtgAnchor):
                self._graph.put_anchor(dataclasses.replace(obj, system=system))
            elif isinstance(obj, RtgDataObject):
                anchors = tuple(
                    anchor.uuid
                    for anchor in self._graph.list_data_anchors(uuid_value).anchors
                    if anchor.uuid
                )
                self._graph.put_data_object(dataclasses.replace(obj, system=system), anchors)
            elif isinstance(obj, RtgLink):
                self._graph.put_link(dataclasses.replace(obj, system=system))

    def _capture_apply_preimage(self, batch: RtgChangeBatch) -> _ApplyPreimage:
        graph_ids = self._graph_touched_ids(batch)
        schema_ids = self._schema_touched_ids(batch)
        constraint_ids = self._constraint_touched_ids(batch)
        migration_touched = bool(
            batch.migration_changes.migration_writes
            or batch.migration_changes.status_changes
            or batch.migration_changes.evidence_additions
            or batch.migration_changes.delete_migrations
        )
        return _ApplyPreimage(
            graph=self._capture_graph_preimage(graph_ids),
            schema={uuid_value: self._try_get_schema(uuid_value) for uuid_value in schema_ids},
            constraints={
                uuid_value: self._try_get_constraint(uuid_value) for uuid_value in constraint_ids
            },
            migration_snapshot=self._migration.export_snapshot() if migration_touched else None,
        )

    def _graph_touched_ids(self, batch: RtgChangeBatch) -> set[UUID]:
        touched: set[UUID] = set()
        touched.update(_uuid_ref(write.ref) for write in batch.graph_changes.anchor_writes)
        touched.update(_uuid_ref(write.ref) for write in batch.graph_changes.data_object_writes)
        touched.update(
            _uuid_ref(ref)
            for write in batch.graph_changes.data_object_writes
            for ref in write.anchor_refs
        )
        touched.update(_uuid_ref(write.ref) for write in batch.graph_changes.link_writes)
        touched.update(_uuid_ref(write.source_ref) for write in batch.graph_changes.link_writes)
        touched.update(_uuid_ref(write.target_ref) for write in batch.graph_changes.link_writes)
        for change in (*batch.graph_changes.associate_data, *batch.graph_changes.dissociate_data):
            touched.add(_uuid_ref(change.anchor_ref))
            touched.add(_uuid_ref(change.data_ref))
        touched.update(_uuid_ref(change.object_ref) for change in batch.graph_changes.set_live)
        for ref in batch.graph_changes.delete_links:
            touched.add(_uuid_ref(ref))
        for ref in batch.graph_changes.delete_data_objects:
            data_uuid = _uuid_ref(ref)
            touched.add(data_uuid)
            try:
                preview = self._graph.preview_delete_data_object(data_uuid)
                touched.update(_record_uuid(item) for item in preview.deleted_links)
                touched.update(anchor for anchor, _data in preview.removed_anchor_data_pairs)
            except Exception:
                pass
        for ref in batch.graph_changes.delete_anchors:
            anchor_uuid = _uuid_ref(ref)
            touched.add(anchor_uuid)
            try:
                preview = self._graph.preview_delete_anchor(anchor_uuid)
                touched.update(_record_uuid(item) for item in preview.deleted_data_objects)
                touched.update(_record_uuid(item) for item in preview.deleted_links)
            except Exception:
                pass
        for change in batch.graph_changes.dissociate_data:
            try:
                preview = self._graph.preview_dissociate_data(
                    _uuid_ref(change.anchor_ref), _uuid_ref(change.data_ref)
                )
                touched.update(_record_uuid(item) for item in preview.deleted_data_objects)
                touched.update(_record_uuid(item) for item in preview.deleted_links)
            except Exception:
                pass
        return touched

    def _schema_touched_ids(self, batch: RtgChangeBatch) -> set[UUID]:
        touched = {_uuid_ref(write.ref) for write in batch.schema_changes.definition_writes}
        touched.update(_uuid_ref(ref) for ref in batch.schema_changes.delete_definitions)
        touched.update(_uuid_ref(change.target_ref) for change in batch.schema_changes.set_live)
        return touched

    def _constraint_touched_ids(self, batch: RtgChangeBatch) -> set[UUID]:
        touched = {_uuid_ref(write.ref) for write in batch.constraint_changes.constraint_writes}
        touched.update(_uuid_ref(ref) for ref in batch.constraint_changes.delete_constraints)
        touched.update(_uuid_ref(change.target_ref) for change in batch.constraint_changes.set_live)
        return touched

    def _capture_graph_preimage(self, object_uuids: set[UUID]) -> _GraphPreimage:
        objects: dict[UUID, RtgObject | None] = {}
        data_anchors: dict[UUID, tuple[UUID, ...]] = {}
        pending = list(object_uuids)
        seen: set[UUID] = set()
        while pending:
            uuid_value = pending.pop()
            if uuid_value in seen:
                continue
            seen.add(uuid_value)
            obj = self._try_get_graph_object(uuid_value)
            objects[uuid_value] = obj
            if isinstance(obj, RtgDataObject):
                anchors = tuple(
                    _record_uuid(anchor)
                    for anchor in self._graph.list_data_anchors(uuid_value).anchors
                )
                data_anchors[uuid_value] = anchors
                pending.extend(anchor for anchor in anchors if anchor not in seen)
            elif isinstance(obj, RtgLink):
                pending.extend(
                    uuid_value
                    for uuid_value in (obj.source_uuid, obj.target_uuid)
                    if uuid_value not in seen
                )
        return _GraphPreimage(objects=objects, data_anchors=data_anchors)

    def _restore_apply_preimage(self, preimage: _ApplyPreimage) -> None:
        self._restore_graph_preimage(preimage.graph)
        for uuid_value in sorted(preimage.schema, key=str):
            _delete_schema_if_present(self._schema, uuid_value)
        for _uuid_value, definition in sorted(
            preimage.schema.items(), key=lambda item: str(item[0])
        ):
            if definition is not None:
                self._schema.put_definition(definition)
        for uuid_value in sorted(preimage.constraints, key=str):
            _delete_constraint_if_present(self._constraints, uuid_value)
        for _uuid_value, constraint in sorted(
            preimage.constraints.items(), key=lambda item: str(item[0])
        ):
            if constraint is not None:
                self._constraints.put_constraint(constraint)
        if preimage.migration_snapshot is not None:
            self._migration = type(self._migration).import_snapshot(preimage.migration_snapshot)

    def _restore_graph_preimage(self, preimage: _GraphPreimage) -> None:
        for uuid_value, _obj in sorted(preimage.objects.items(), key=lambda item: str(item[0])):
            current = self._try_get_graph_object(uuid_value)
            if current is None:
                continue
            if isinstance(current, RtgLink):
                _delete_graph_if_present(self._graph, uuid_value)
        for uuid_value, _obj in sorted(preimage.objects.items(), key=lambda item: str(item[0])):
            current = self._try_get_graph_object(uuid_value)
            if current is None:
                continue
            if isinstance(current, RtgDataObject):
                _delete_graph_if_present(self._graph, uuid_value)
        for uuid_value, obj in sorted(preimage.objects.items(), key=lambda item: str(item[0])):
            current = self._try_get_graph_object(uuid_value)
            if current is None:
                continue
            if isinstance(current, RtgAnchor) and obj is None:
                _delete_graph_if_present(self._graph, uuid_value)
        for obj in sorted(
            (item for item in preimage.objects.values() if isinstance(item, RtgAnchor)),
            key=lambda item: str(_record_uuid(item)),
        ):
            self._graph.put_anchor(obj)
        for obj in sorted(
            (item for item in preimage.objects.values() if isinstance(item, RtgDataObject)),
            key=lambda item: str(_record_uuid(item)),
        ):
            self._graph.put_data_object(obj, preimage.data_anchors[_record_uuid(obj)])
        for obj in sorted(
            (item for item in preimage.objects.values() if isinstance(item, RtgLink)),
            key=lambda item: str(_record_uuid(item)),
        ):
            self._graph.put_link(obj)

    def _try_get_graph_object(self, object_uuid: UUID) -> RtgObject | None:
        try:
            return self._graph.get_object(object_uuid)
        except Exception:
            return None

    def _try_get_schema(self, definition_uuid: UUID) -> RtgSchemaDefinition | None:
        try:
            return self._schema.get_definition(definition_uuid)
        except Exception:
            return None

    def _try_get_constraint(self, constraint_uuid: UUID) -> RtgConstraintDefinition | None:
        try:
            return self._constraints.get_constraint(constraint_uuid)
        except Exception:
            return None

    def _assert_cutover_candidates_exist(self, plan: RtgMigrationCutoverPlan) -> None:
        for uuid_value in (*plan.schema_make_non_live, *plan.schema_make_live):
            self._schema.get_definition(uuid_value)
        for uuid_value in (*plan.constraint_make_non_live, *plan.constraint_make_live):
            self._constraints.get_constraint(uuid_value)
        for uuid_value in (*plan.graph_make_non_live, *plan.graph_make_live):
            self._graph.get_object(uuid_value)

    def _change_batch_from_cutover_plan(self, plan: RtgMigrationCutoverPlan) -> RtgChangeBatch:
        return RtgChangeBatch(
            graph_changes=RtgGraphChangeSet(
                set_live=tuple(
                    RtgGraphLiveStatusChange(
                        object_ref=RtgChangeReference(resource_id=uuid_value),
                        live=live,
                    )
                    for uuid_value, live in (
                        *((uuid_value, False) for uuid_value in plan.graph_make_non_live),
                        *((uuid_value, True) for uuid_value in plan.graph_make_live),
                    )
                )
            ),
            schema_changes=RtgSchemaChangeSet(
                set_live=tuple(
                    RtgLiveStatusChange(
                        target_ref=RtgChangeReference(resource_id=uuid_value),
                        live=live,
                    )
                    for uuid_value, live in (
                        *((uuid_value, False) for uuid_value in plan.schema_make_non_live),
                        *((uuid_value, True) for uuid_value in plan.schema_make_live),
                    )
                )
            ),
            constraint_changes=RtgConstraintChangeSet(
                set_live=tuple(
                    RtgLiveStatusChange(
                        target_ref=RtgChangeReference(resource_id=uuid_value),
                        live=live,
                    )
                    for uuid_value, live in (
                        *((uuid_value, False) for uuid_value in plan.constraint_make_non_live),
                        *((uuid_value, True) for uuid_value in plan.constraint_make_live),
                    )
                )
            ),
        )

    def _apply_cutover_plan(
        self,
        plan: RtgMigrationCutoverPlan,
        *,
        migration: RtgMigrationRecord,
        options: RtgControllerCutoverOptions,
        validate_actual_post_state: bool,
        transaction_id: UUID | None,
    ) -> RtgControllerAppliedChanges:
        self._apply_registry_live_flips(plan.schema_make_non_live, False, "schema")
        self._apply_registry_live_flips(plan.schema_make_live, True, "schema")
        self._apply_registry_live_flips(plan.constraint_make_non_live, False, "constraint")
        self._apply_registry_live_flips(plan.constraint_make_live, True, "constraint")
        self._apply_graph_live_flips(plan.graph_make_non_live, False)
        self._apply_graph_live_flips(plan.graph_make_live, True)
        migration_id = _concrete_migration_id(migration.migration_id)
        if _migration_exists(self._migration, migration_id):
            if migration.status == "draft":
                self._migration.set_status(migration_id, "ready")
            current = self._migration.get_migration(migration_id)
            if current.status != "applied":
                self._migration.set_status(migration_id, "applied")
        if validate_actual_post_state:
            post_report = self._change_validator.validate_graph_state(
                self._graph,
                self._schema,
                self._constraints,
                self._migration,
                self._query_engine,
                None,
                RtgValidationOptions(),
            )
            if not post_report.accepted:
                raise RtgControllerValidationFailed(
                    "post-cutover validation has blocking findings",
                    transaction_id=transaction_id,
                    validation_report=post_report,
                )
        deleted = 0
        if options.prune_retired:
            for uuid_value in plan.schema_make_non_live:
                self._schema.delete_definition(uuid_value)
                deleted += 1
            for uuid_value in plan.constraint_make_non_live:
                self._constraints.delete_constraint(uuid_value)
                deleted += 1
            if _migration_exists(self._migration, migration_id):
                self._migration.delete_migration(migration_id)
                deleted += 1
        return RtgControllerAppliedChanges(
            deletes=deleted,
            live_status_changes=len(plan.schema_make_live)
            + len(plan.schema_make_non_live)
            + len(plan.constraint_make_live)
            + len(plan.constraint_make_non_live)
            + len(plan.graph_make_live)
            + len(plan.graph_make_non_live),
        )

    def _apply_cutover_without_ledger(
        self,
        migration_id: str,
        options: RtgControllerCutoverOptions,
    ) -> RtgControllerAppliedChanges:
        pre_snapshot = self.export_system_snapshot()
        migration = self._migration.get_migration(migration_id)
        plan = RtgMigrationCutoverPlan.from_migration(migration)
        try:
            return self._apply_cutover_plan(
                plan,
                migration=migration,
                options=options,
                validate_actual_post_state=False,
                transaction_id=None,
            )
        except Exception:
            self.restore_from_snapshot(
                pre_snapshot, RtgControllerRestoreOptions(ledger_mode="skip")
            )
            raise

    def _validate_live_graph_lane(self, graph_changes: RtgGraphChangeSet) -> None:
        for write in (
            *graph_changes.anchor_writes,
            *graph_changes.data_object_writes,
            *graph_changes.link_writes,
        ):
            if write.system.get("live", True) is not True:
                raise RtgControllerPreconditionFailed(
                    "live graph lane cannot create non-live graph candidates"
                )
        for change in graph_changes.set_live:
            if change.live is not True:
                raise RtgControllerPreconditionFailed(
                    "live graph lane cannot make graph objects non-live"
                )

    def _validate_knowledge_lane(self, batch: RtgChangeBatch) -> None:
        if batch.graph_changes.set_live:
            raise RtgControllerPreconditionFailed("knowledge staging cannot apply graph live flips")
        if batch.schema_changes.set_live or batch.constraint_changes.set_live:
            raise RtgControllerPreconditionFailed(
                "knowledge staging cannot apply schema or constraint live flips"
            )
        if batch.schema_changes.delete_definitions or batch.constraint_changes.delete_constraints:
            raise RtgControllerPreconditionFailed(
                "knowledge staging cannot delete schema or constraint definitions"
            )

        migration_records = tuple(
            write.migration for write in batch.migration_changes.migration_writes
        )
        schema_make_live = {
            uuid_value
            for migration in migration_records
            for uuid_value in migration.schema_make_live
        }
        constraint_make_live = {
            uuid_value
            for migration in migration_records
            for uuid_value in migration.constraint_make_live
        }
        graph_make_live = {
            uuid_value
            for migration in migration_records
            for uuid_value in migration.graph_make_live
        }

        for write in batch.schema_changes.definition_writes:
            if write.definition.system.get("live", True) is not False:
                raise RtgControllerPreconditionFailed(
                    "knowledge staging schema definitions must be non-live candidates"
                )
            if write.definition.uuid not in schema_make_live:
                raise RtgControllerPreconditionFailed(
                    "staged schema definitions must be referenced by a migration"
                )
        for write in batch.constraint_changes.constraint_writes:
            if write.constraint.system.get("live", True) is not False:
                raise RtgControllerPreconditionFailed(
                    "knowledge staging constraints must be non-live candidates"
                )
            if write.constraint.uuid not in constraint_make_live:
                raise RtgControllerPreconditionFailed(
                    "staged constraints must be referenced by a migration"
                )
        for write in (
            *batch.graph_changes.anchor_writes,
            *batch.graph_changes.data_object_writes,
            *batch.graph_changes.link_writes,
        ):
            if write.system.get("live", True) is not False:
                raise RtgControllerPreconditionFailed(
                    "knowledge staging graph writes must be non-live candidates"
                )
            if _nullable_uuid_ref(write.ref) not in graph_make_live:
                raise RtgControllerPreconditionFailed(
                    "staged graph candidates must be referenced by a migration"
                )

    def _record_ledger(
        self,
        transaction_id: UUID,
        operation_name: str,
        record_kind: str,
        payload: object,
    ) -> RtgControllerLedgerFailureRecord | None:
        payload_json = json.dumps(_to_json_value(payload), sort_keys=True)
        timestamp = datetime.now(UTC).isoformat()
        failure_message = ""
        for _attempt in range(3):
            try:
                result = self._sql_storage.execute(
                    """
                    insert into rtg_controller_ledger
                        (transaction_id, operation_name, record_kind, payload_json, recorded_at)
                    values (?, ?, ?, ?, ?)
                    """,
                    (str(transaction_id), operation_name, record_kind, payload_json, timestamp),
                )
                self._last_ledger_position = result.last_inserted_row_id
                self._last_transaction_id = transaction_id
                self._last_transaction_timestamp = timestamp
                return None
            except Exception as error:
                failure_message = str(error)
        failure = RtgControllerLedgerFailureRecord(
            transaction_id=transaction_id,
            ledger_position=None,
            operation_name=operation_name,
            record_kind=record_kind,
            payload_json=payload_json,
            failure_message=failure_message,
            retry_count=3,
            first_failed_timestamp=timestamp,
            last_failed_timestamp=datetime.now(UTC).isoformat(),
        )
        self._ledger_failures.append(failure)
        self._persist_ledger_failures()
        return failure

    def _persist_ledger_failures(self) -> None:
        try:
            self._json_storage.write(
                "system/ledger_failures.json",
                [_to_json_value(item) for item in self._ledger_failures],
            )
        except Exception:
            return

    def _load_persisted_ledger_failures(self) -> None:
        try:
            document = self._json_storage.read("system/ledger_failures.json")
        except Exception:
            return
        if not isinstance(document.value, list):
            return
        existing = {
            (
                str(item.transaction_id),
                item.operation_name,
                item.record_kind,
                item.payload_json,
            )
            for item in self._ledger_failures
        }
        for item in document.value:
            try:
                record = _ledger_failure_from_json(item)
            except Exception:
                continue
            key = (
                str(record.transaction_id),
                record.operation_name,
                record.record_kind,
                record.payload_json,
            )
            if key not in existing:
                self._ledger_failures.append(record)
                existing.add(key)

    def _controller_state_empty(self) -> bool:
        snapshot = self.export_system_snapshot()
        return (
            not snapshot.graph.anchors
            and not snapshot.graph.data_objects
            and not snapshot.graph.links
            and not snapshot.schema.definitions
            and not snapshot.constraints.constraints
            and not snapshot.migration.migrations
        )

    def _resolve_replay_start_snapshot(
        self,
        options: RtgControllerReplayOptions,
    ) -> RtgSystemSnapshot | None:
        if options.start_snapshot is not None and options.start_snapshot_path is not None:
            raise RtgControllerReplayFailed(
                "replay_options may include start_snapshot or start_snapshot_path, not both",
                diagnostic=rtg_diagnostic(
                    code="controller.replay.ambiguous_start",
                    category="replay_precondition",
                    path="replay_options",
                    problem="Replay was given two mutually exclusive start snapshots.",
                    remedy="Provide either start_snapshot or start_snapshot_path, not both.",
                    minimal_example={
                        "replay_options": {"start_snapshot_path": "snapshots/run.json"}
                    },
                    guide_topics=("workflow_patterns", "recovery_and_replay"),
                    mutation_state="not_mutated",
                ),
            )
        if options.start_snapshot_path is None:
            return options.start_snapshot
        return self.load_persisted_snapshot(options.start_snapshot_path).snapshot

    def _empty_system_snapshot(self) -> RtgSystemSnapshot:
        try:
            graph = type(self._graph).empty().export_snapshot()
            schema = type(self._schema).empty().export_snapshot()
            constraints = type(self._constraints).empty().export_snapshot()
            migration = type(self._migration).empty().export_snapshot()
        except Exception as error:
            raise RtgControllerReplayFailed(
                "verify replay requires dependencies that can create empty scratch state"
            ) from error
        return RtgSystemSnapshot(
            graph=graph,
            schema=schema,
            constraints=constraints,
            migration=migration,
        )

    def _migration_history_event_count(self) -> int:
        rows = self._sql_storage.query(
            """
            select ledger_position, transaction_id, operation_name, record_kind,
                payload_json, recorded_at
            from rtg_controller_ledger
            order by ledger_position
            """
        ).rows
        successful_transactions = _successful_transaction_metadata(rows)
        count = 0
        for row in rows:
            if row["record_kind"] != "request":
                continue
            transaction_id_text = str(row["transaction_id"])
            transaction = successful_transactions.get(transaction_id_text)
            if transaction is None:
                continue
            payload_json = row["payload_json"]
            if not isinstance(payload_json, str):
                continue
            try:
                payload = _object(json.loads(payload_json))
            except Exception:
                continue
            count += len(
                _migration_history_events_for_request(
                    operation_name=str(row["operation_name"]),
                    payload=cast(JsonObject, payload),
                    transaction_id=transaction_id_text,
                    ledger_position=transaction.ledger_position,
                    recorded_at=transaction.recorded_at,
                    response_payload=transaction.response_payload,
                )
            )
        return count


def _uuid_ref(ref: RtgChangeReference) -> UUID:
    if isinstance(ref.resource_id, UUID):
        return ref.resource_id
    if isinstance(ref.resource_id, str):
        return UUID(ref.resource_id)
    raise RtgControllerPreconditionFailed("reference is not resolved")


def _record_uuid(record: RtgObject) -> UUID:
    if record.uuid is None:
        raise RtgControllerPreconditionFailed("record UUID is not concrete")
    return record.uuid


def _nullable_uuid_ref(ref: RtgChangeReference) -> UUID | None:
    if ref.resource_id is None:
        return None
    if isinstance(ref.resource_id, UUID):
        return ref.resource_id
    return UUID(ref.resource_id)


def _text_ref(ref: RtgChangeReference) -> str:
    if ref.resource_id is not None:
        return str(ref.resource_id)
    if ref.local_ref is not None:
        return ref.local_ref
    raise RtgControllerPreconditionFailed("reference is not resolved")


def _concrete_migration_id(value: str | None) -> str:
    if value is None:
        raise RtgControllerPreconditionFailed("migration ID is not concrete")
    return value


def _migration_exists(migration: RtgMigration, migration_id: str) -> bool:
    try:
        migration.get_migration(migration_id)
        return True
    except Exception:
        return False


def _system_live(system: JsonObject) -> bool:
    return system.get("live", True) is True


def _recommended_next_steps(classification: str) -> tuple[str, ...]:
    if classification == "needs_replay":
        return (
            "Ledger records exist while in-memory state is empty.",
            "If you expected prior live state after restart, call rtg_replay_ledger({}) or "
            "load a persisted snapshot and replay after it.",
            "If the empty state is intentional, continue without replay and report the ledger "
            "context.",
            "Call rtg_validate_graph({}) after replay or before new writes.",
        )
    if classification == "empty":
        return (
            "Call rtg_get_usage_guide with topic='schema_staging_minimal' for payload shape.",
            "Translate the user task into schema_definitions, stage them with "
            "rtg_stage_schema_migration, then cut the migration over.",
        )
    if classification == "schema_only":
        return (
            "Use rtg_discover_anchor_types and rtg_get_schema_pack before writing data.",
            "Ingest live graph facts with rtg_apply_live_graph_changes.",
        )
    if classification == "has_staged_work":
        return (
            "Inspect migrations with rtg_list_migrations.",
            "Cut over intended ready migrations or abandon accidental staged work.",
        )
    return (
        "Use rtg_execute_query for graph questions.",
        "Persist snapshots before risky schema evolution.",
    )


def _recommended_workflows(classification: str) -> tuple[str, ...]:
    if classification == "needs_replay":
        return ("replay_recovery",)
    if classification == "empty":
        return ("connection_state_check", "schema_bootstrap")
    if classification == "schema_only":
        return ("schema_discovery", "data_ingest")
    if classification == "has_staged_work":
        return ("staged_work_review", "cutover_or_abandon")
    return ("query_answer", "safe_update", "snapshot_replay_check")


def _looks_like_system_snapshot(value: JsonValue) -> bool:
    if not isinstance(value, dict):
        return False
    return all(key in value for key in ("graph", "schema", "constraints", "migration"))


def _delete_graph_if_present(graph: RtgGraph, object_uuid: UUID) -> None:
    try:
        obj = graph.get_object(object_uuid)
    except Exception:
        return
    try:
        if isinstance(obj, RtgLink):
            graph.delete_link(object_uuid)
        elif isinstance(obj, RtgDataObject):
            graph.delete_data_object(object_uuid)
        else:
            graph.delete_anchor(object_uuid)
    except Exception:
        return


def _delete_schema_if_present(schema: RtgSchema, definition_uuid: UUID) -> None:
    try:
        schema.delete_definition(definition_uuid)
    except Exception:
        return


def _delete_constraint_if_present(
    constraints: RtgConstraints,
    constraint_uuid: UUID,
) -> None:
    try:
        constraints.delete_constraint(constraint_uuid)
    except Exception:
        return


def _with_ledger_degraded(
    details: JsonObject,
    failures: list[RtgControllerLedgerFailureRecord],
) -> JsonObject:
    return {
        **details,
        "audit_degraded": True,
        "ledger_failure_count": len(failures),
        "ledger_failures": [
            {
                "operation_name": item.operation_name,
                "record_kind": item.record_kind,
                "failure_message": item.failure_message,
                "retry_count": item.retry_count,
            }
            for item in failures
        ],
    }


def _operation_details(operation_name: str, batch: RtgChangeBatch) -> JsonObject:
    if operation_name != "stage_knowledge_changes":
        return {}
    migration_writes = batch.migration_changes.migration_writes
    if not migration_writes:
        return {}
    schema_candidates = [
        str(_uuid_ref(write.ref)) for write in batch.schema_changes.definition_writes
    ]
    constraint_candidates = [
        str(_uuid_ref(write.ref)) for write in batch.constraint_changes.constraint_writes
    ]
    graph_candidates = [
        str(_uuid_ref(write.ref))
        for write in (
            *batch.graph_changes.anchor_writes,
            *batch.graph_changes.data_object_writes,
            *batch.graph_changes.link_writes,
        )
    ]
    return cast(
        JsonObject,
        {
            "operation_effect": "staged_candidates_written",
            "requires_cutover": any(
                write.migration.schema_make_live
                or write.migration.schema_make_non_live
                or write.migration.constraint_make_live
                or write.migration.constraint_make_non_live
                or write.migration.graph_make_live
                or write.migration.graph_make_non_live
                for write in migration_writes
            ),
            "staged_migration_ids": [write.migration.migration_id for write in migration_writes],
            "candidate_counts": {
                "schema": len(schema_candidates),
                "constraints": len(constraint_candidates),
                "graph": len(graph_candidates),
            },
            "candidate_ids": {
                "schema": schema_candidates,
                "constraints": constraint_candidates,
                "graph": graph_candidates,
            },
        },
    )


def _snapshot_summary(snapshot: RtgSystemSnapshot) -> JsonObject:
    graph_counts: dict[str, dict[str, int]] = {
        "anchor": {},
        "data_object": {},
        "link": {},
    }
    for anchor in snapshot.graph.anchors:
        _increment_type_count(graph_counts["anchor"], str(anchor.get("type", "")))
    for data_object in snapshot.graph.data_objects:
        _increment_type_count(graph_counts["data_object"], str(data_object.get("type", "")))
    for link in snapshot.graph.links:
        _increment_type_count(graph_counts["link"], str(link.get("type", "")))
    schema_counts: dict[str, int] = {"anchor": 0, "data_object": 0, "link": 0}
    live_schema_types: dict[str, list[str]] = {"anchor": [], "data_object": [], "link": []}
    for definition in snapshot.schema.definitions:
        kind = str(definition.get("kind", ""))
        if kind in schema_counts:
            schema_counts[kind] += 1
            system = definition.get("system", {})
            if isinstance(system, dict) and system.get("live", True) is True:
                live_schema_types[kind].append(str(definition.get("type_key", "")))
    migration_counts = {
        status: sum(1 for item in snapshot.migration.migrations if item.status == status)
        for status in ("draft", "ready", "failed", "applied", "abandoned")
    }
    return cast(
        JsonObject,
        {
            "graph_counts": graph_counts,
            "schema_counts": schema_counts,
            "live_schema_types": {key: sorted(value) for key, value in live_schema_types.items()},
            "constraint_count": len(snapshot.constraints.constraints),
            "migration_counts_by_status": cast(JsonObject, migration_counts),
            "last_ledger_position": snapshot.last_ledger_position,
            "last_transaction_id": (
                str(snapshot.last_transaction_id)
                if snapshot.last_transaction_id is not None
                else None
            ),
            "last_transaction_timestamp": snapshot.last_transaction_timestamp,
        },
    )


def _replay_start_source(options: RtgControllerReplayOptions) -> str:
    if options.start_snapshot_path is not None:
        return "start_snapshot_path"
    if options.start_snapshot is not None:
        return "start_snapshot"
    return "empty"


def _replay_window(
    *,
    start_source: str,
    start_snapshot: RtgSystemSnapshot | None,
    effective_after_ledger_position: int | None,
    through_ledger_position: int | None,
    ledger_records_seen: int,
) -> JsonObject:
    start_ledger_position = (
        start_snapshot.last_ledger_position if start_snapshot is not None else None
    )
    note = (
        "Replay applies ledger records with ledger_position greater than "
        "effective_after_ledger_position."
    )
    if start_snapshot is not None:
        note = (
            "Replay starts after the snapshot ledger position; it applies ledger records "
            "with ledger_position greater than effective_after_ledger_position."
        )
    return cast(
        JsonObject,
        {
            "start_source": start_source,
            "start_ledger_position": start_ledger_position,
            "effective_after_ledger_position": effective_after_ledger_position,
            "through_ledger_position": through_ledger_position,
            "ledger_records_seen": ledger_records_seen,
            "note": note,
        },
    )


def _increment_type_count(target: dict[str, int], type_key: str) -> None:
    if not type_key:
        return
    target[type_key] = target.get(type_key, 0) + 1


def _summary_count_diffs(before: JsonObject, after: JsonObject) -> JsonObject:
    return {
        "graph_counts": _nested_count_diff(
            cast(JsonObject, _object(before.get("graph_counts", {}))),
            cast(JsonObject, _object(after.get("graph_counts", {}))),
        ),
        "schema_counts": _count_diff(
            cast(JsonObject, _object(before.get("schema_counts", {}))),
            cast(JsonObject, _object(after.get("schema_counts", {}))),
        ),
        "constraint_count": _json_int(after.get("constraint_count"))
        - _json_int(before.get("constraint_count")),
        "migration_counts_by_status": _count_diff(
            cast(JsonObject, _object(before.get("migration_counts_by_status", {}))),
            cast(JsonObject, _object(after.get("migration_counts_by_status", {}))),
        ),
    }


def _nested_count_diff(before: JsonObject, after: JsonObject) -> JsonObject:
    keys = sorted(set(before) | set(after))
    return {
        key: _count_diff(
            cast(JsonObject, _object(before.get(key, {}))),
            cast(JsonObject, _object(after.get(key, {}))),
        )
        for key in keys
    }


def _count_diff(before: JsonObject, after: JsonObject) -> JsonObject:
    keys = sorted(set(before) | set(after))
    return {key: _json_int(after.get(key)) - _json_int(before.get(key)) for key in keys}


def _json_int(value: JsonValue) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int | float | str):
        return int(value)
    return 0


def _migration_history_events_for_request(
    *,
    operation_name: str,
    payload: JsonObject,
    transaction_id: str,
    ledger_position: int | None,
    recorded_at: str | None,
    response_payload: JsonObject,
) -> list[JsonObject]:
    if operation_name == "stage_knowledge_changes":
        batch = _change_batch_from_json(payload)
        return [
            _migration_history_event(
                event_type="staged",
                migration_id=_concrete_migration_id(write.migration.migration_id),
                description=write.migration.description,
                status=write.migration.status,
                summary="candidate records written",
                transaction_id=transaction_id,
                ledger_position=ledger_position,
                recorded_at=recorded_at,
            )
            for write in batch.migration_changes.migration_writes
        ]
    if operation_name == "apply_migration_cutover":
        request_migration = _migration_record_from_json(_object(payload["migration"]))
        migration_id = _concrete_migration_id(request_migration.migration_id)
        status = str(response_payload.get("status"))
        details = _object(response_payload.get("details", {}))
        return [
            _migration_history_event(
                event_type=("cutover_failed" if status == "cutover_failed" else "cutover_applied"),
                migration_id=migration_id,
                description=request_migration.description,
                status=status,
                summary=str(
                    details.get("summary")
                    or details.get("failure_summary")
                    or "migration cutover recorded"
                ),
                transaction_id=transaction_id,
                ledger_position=ledger_position,
                recorded_at=recorded_at,
            )
        ]
    if operation_name == "abandon_migration":
        return [
            _migration_history_event(
                event_type="abandoned",
                migration_id=str(payload.get("migration_id", "")),
                description=None,
                status="abandoned",
                summary=str(payload.get("reason") or "migration abandoned"),
                transaction_id=transaction_id,
                ledger_position=ledger_position,
                recorded_at=recorded_at,
            )
        ]
    return []


def _migration_history_event(
    *,
    event_type: str,
    migration_id: str,
    description: str | None,
    status: str,
    summary: str,
    transaction_id: str,
    ledger_position: int | None,
    recorded_at: str | None,
) -> JsonObject:
    return {
        "event_type": event_type,
        "migration_id": migration_id,
        "description": description,
        "transaction_id": transaction_id,
        "ledger_position": ledger_position,
        "recorded_at": recorded_at,
        "status": status,
        "summary": summary,
    }


def _successful_transaction_metadata(rows: object) -> dict[str, _ReplayTransactionMetadata]:
    successful: dict[str, _ReplayTransactionMetadata] = {}
    for row in cast(Any, rows):
        if row["record_kind"] != "response":
            continue
        payload_json = row["payload_json"]
        if not isinstance(payload_json, str):
            continue
        try:
            payload = _object(json.loads(payload_json))
        except Exception:
            continue
        status = payload.get("status")
        if status in {
            "applied",
            "cutover_applied",
            "cutover_failed",
            "restore_applied",
            "migration_abandoned",
        }:
            ledger_position = row["ledger_position"]
            recorded_at = row.get("recorded_at")
            successful[str(row["transaction_id"])] = _ReplayTransactionMetadata(
                status=str(status),
                ledger_position=(
                    int(cast(int, ledger_position)) if ledger_position is not None else None
                ),
                recorded_at=str(recorded_at) if recorded_at is not None else None,
                response_payload=cast(JsonObject, payload),
            )
    return successful


def _to_json_value(value: object) -> JsonValue:
    if dataclasses.is_dataclass(value):
        data = dataclasses.asdict(cast(Any, value))
        return {key: _to_json_value(item) for key, item in data.items()}
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_to_json_value(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _change_batch_from_json(value: object) -> RtgChangeBatch:
    data = _object(value)
    return RtgChangeBatch(
        graph_changes=_graph_changes_from_json(data.get("graph_changes", {})),
        schema_changes=_schema_changes_from_json(data.get("schema_changes", {})),
        constraint_changes=_constraint_changes_from_json(data.get("constraint_changes", {})),
        migration_changes=_migration_changes_from_json(data.get("migration_changes", {})),
    )


def _system_snapshot_from_json(value: object) -> RtgSystemSnapshot:
    data = _object(value)
    return RtgSystemSnapshot(
        graph=_graph_snapshot_from_json(data["graph"]),
        schema=_schema_snapshot_from_json(data["schema"]),
        constraints=_constraint_snapshot_from_json(data["constraints"]),
        migration=_migration_snapshot_from_json(data["migration"]),
        last_ledger_position=_optional_int_from_json(data.get("last_ledger_position")),
        last_transaction_id=_optional_uuid_from_json(data.get("last_transaction_id")),
        last_transaction_timestamp=(
            str(data["last_transaction_timestamp"])
            if data.get("last_transaction_timestamp") is not None
            else None
        ),
    )


def _graph_snapshot_from_json(value: object) -> RtgGraphSnapshot:
    data = _object(value)
    anchor_data_index = _object(data.get("anchor_data_index", {}))
    return RtgGraphSnapshot(
        anchors=tuple(_json_object(item) for item in _list(data.get("anchors", []))),
        data_objects=tuple(_json_object(item) for item in _list(data.get("data_objects", []))),
        links=tuple(_json_object(item) for item in _list(data.get("links", []))),
        anchor_data_index={
            str(key): tuple(str(item) for item in _list(items))
            for key, items in anchor_data_index.items()
        },
    )


def _schema_snapshot_from_json(value: object) -> RtgSchemaSnapshot:
    data = _object(value)
    return RtgSchemaSnapshot(
        definitions=tuple(_json_object(item) for item in _list(data.get("definitions", [])))
    )


def _constraint_snapshot_from_json(value: object) -> RtgConstraintSnapshot:
    data = _object(value)
    return RtgConstraintSnapshot(
        constraints=tuple(
            _constraint_definition_from_json(item) for item in _list(data.get("constraints", []))
        )
    )


def _migration_snapshot_from_json(value: object) -> RtgMigrationSnapshot:
    data = _object(value)
    return RtgMigrationSnapshot(
        migrations=tuple(
            _migration_record_from_json(item) for item in _list(data.get("migrations", []))
        )
    )


def _graph_changes_from_json(value: object) -> RtgGraphChangeSet:
    data = _object(value)
    return RtgGraphChangeSet(
        anchor_writes=tuple(
            RtgGraphAnchorWrite(
                ref=_ref_from_json(item["ref"]),
                type=str(item["type"]),
                display_name=cast(str | None, item.get("display_name")),
                system=_json_object(item.get("system", {})),
            )
            for item in _objects(data.get("anchor_writes", []))
        ),
        data_object_writes=tuple(
            RtgGraphDataObjectWrite(
                ref=_ref_from_json(item["ref"]),
                type=str(item["type"]),
                properties=_json_object(item.get("properties", {})),
                system=_json_object(item.get("system", {})),
                anchor_refs=tuple(
                    _ref_from_json(ref) for ref in _list(item.get("anchor_refs", []))
                ),
            )
            for item in _objects(data.get("data_object_writes", []))
        ),
        link_writes=tuple(
            RtgGraphLinkWrite(
                ref=_ref_from_json(item["ref"]),
                type=str(item["type"]),
                source_ref=_ref_from_json(item["source_ref"]),
                target_ref=_ref_from_json(item["target_ref"]),
                system=_json_object(item.get("system", {})),
            )
            for item in _objects(data.get("link_writes", []))
        ),
        associate_data=tuple(
            RtgGraphAssociationChange(
                anchor_ref=_ref_from_json(item["anchor_ref"]),
                data_ref=_ref_from_json(item["data_ref"]),
            )
            for item in _objects(data.get("associate_data", []))
        ),
        dissociate_data=tuple(
            RtgGraphAssociationChange(
                anchor_ref=_ref_from_json(item["anchor_ref"]),
                data_ref=_ref_from_json(item["data_ref"]),
            )
            for item in _objects(data.get("dissociate_data", []))
        ),
        delete_anchors=tuple(
            _ref_from_json(item) for item in _list(data.get("delete_anchors", []))
        ),
        delete_data_objects=tuple(
            _ref_from_json(item) for item in _list(data.get("delete_data_objects", []))
        ),
        delete_links=tuple(_ref_from_json(item) for item in _list(data.get("delete_links", []))),
        set_live=tuple(
            RtgGraphLiveStatusChange(
                object_ref=_ref_from_json(item["object_ref"]),
                live=bool(item["live"]),
            )
            for item in _objects(data.get("set_live", []))
        ),
    )


def _schema_changes_from_json(value: object) -> RtgSchemaChangeSet:
    data = _object(value)
    return RtgSchemaChangeSet(
        definition_writes=tuple(
            RtgSchemaDefinitionWrite(
                ref=_ref_from_json(item["ref"]),
                definition=_schema_definition_from_json(item["definition"]),
            )
            for item in _objects(data.get("definition_writes", []))
        ),
        delete_definitions=tuple(
            _ref_from_json(item) for item in _list(data.get("delete_definitions", []))
        ),
        set_live=tuple(
            RtgLiveStatusChange(
                target_ref=_ref_from_json(item["target_ref"]),
                live=bool(item["live"]),
            )
            for item in _objects(data.get("set_live", []))
        ),
    )


def _constraint_changes_from_json(value: object) -> RtgConstraintChangeSet:
    data = _object(value)
    return RtgConstraintChangeSet(
        constraint_writes=tuple(
            RtgConstraintDefinitionWrite(
                ref=_ref_from_json(item["ref"]),
                constraint=_constraint_definition_from_json(item["constraint"]),
            )
            for item in _objects(data.get("constraint_writes", []))
        ),
        delete_constraints=tuple(
            _ref_from_json(item) for item in _list(data.get("delete_constraints", []))
        ),
        set_live=tuple(
            RtgLiveStatusChange(
                target_ref=_ref_from_json(item["target_ref"]),
                live=bool(item["live"]),
            )
            for item in _objects(data.get("set_live", []))
        ),
    )


def _migration_changes_from_json(value: object) -> RtgMigrationChangeSet:
    data = _object(value)
    return RtgMigrationChangeSet(
        migration_writes=tuple(
            RtgMigrationRecordWrite(
                ref=_ref_from_json(item["ref"]),
                migration=_migration_record_from_json(item["migration"]),
            )
            for item in _objects(data.get("migration_writes", []))
        ),
        delete_migrations=tuple(
            _ref_from_json(item) for item in _list(data.get("delete_migrations", []))
        ),
        status_changes=tuple(
            RtgMigrationStatusChange(
                migration_ref=_ref_from_json(item["migration_ref"]),
                status=str(item["status"]),
                status_metadata=_json_object(item.get("status_metadata", {})),
            )
            for item in _objects(data.get("status_changes", []))
        ),
        evidence_additions=tuple(
            RtgMigrationEvidenceAddition(
                migration_ref=_ref_from_json(item["migration_ref"]),
                evidence=_migration_evidence_from_json(item["evidence"]),
            )
            for item in _objects(data.get("evidence_additions", []))
        ),
    )


def _ref_from_json(value: object) -> RtgChangeReference:
    data = _object(value)
    resource_id = data.get("resource_id")
    local_ref = data.get("local_ref")
    return RtgChangeReference(
        resource_id=str(resource_id) if resource_id is not None else None,
        local_ref=str(local_ref) if local_ref is not None else None,
    )


def _schema_definition_from_json(value: object) -> RtgSchemaDefinition:
    data = _object(value)
    kind = str(data["kind"])
    payload_data = _object(data["payload"])
    if kind == "anchor":
        payload = RtgAnchorSchemaPayload(
            required_data_types=tuple(
                str(item) for item in _list(payload_data.get("required_data_types", []))
            ),
            optional_data_types=tuple(
                str(item) for item in _list(payload_data.get("optional_data_types", []))
            ),
        )
    elif kind == "data_object":
        payload = RtgDataObjectSchemaPayload(
            properties={
                str(key): _schema_field_from_json(item)
                for key, item in _object(payload_data.get("properties", {})).items()
            }
        )
    else:
        payload = RtgLinkSchemaPayload(
            allowed_source_types=tuple(
                str(item) for item in _list(payload_data.get("allowed_source_types", []))
            ),
            allowed_target_types=tuple(
                str(item) for item in _list(payload_data.get("allowed_target_types", []))
            ),
        )
    return RtgSchemaDefinition(
        uuid=UUID(str(data["uuid"])) if data.get("uuid") is not None else None,
        kind=kind,
        type_key=str(data["type_key"]),
        description=str(data.get("description", "")),
        payload=payload,
        system=_json_object(data.get("system", {})),
    )


def _schema_field_from_json(value: object) -> RtgSchemaField:
    data = _object(value)
    items = data.get("items")
    required = data.get("required")
    if not isinstance(required, bool):
        raise RtgControllerReplayFailed("schema field required must be boolean")
    return RtgSchemaField(
        required=required,
        value_kinds=tuple(str(item) for item in _list(data.get("value_kinds", []))),
        properties={
            str(key): _schema_field_from_json(item)
            for key, item in _object(data.get("properties", {})).items()
        },
        items=_schema_field_from_json(items) if items is not None else None,
    )


def _constraint_definition_from_json(value: object) -> RtgConstraintDefinition:
    data = _object(value)
    kind = str(data["kind"])
    payload_data = _object(data["payload"])
    if kind == "query_pattern":
        payload = RtgConstraintQueryPatternPayload(
            query_spec=_query_spec_from_json(payload_data["query_spec"]),
            expectation=str(payload_data["expectation"]),
        )
    else:
        payload = RtgConstraintCardinalityPayload(
            query_spec=_query_spec_from_json(payload_data["query_spec"]),
            counted_binding=str(payload_data["counted_binding"]),
            minimum=cast(int | None, payload_data.get("minimum")),
            maximum=cast(int | None, payload_data.get("maximum")),
        )
    return RtgConstraintDefinition(
        uuid=UUID(str(data["uuid"])) if data.get("uuid") is not None else None,
        kind=kind,
        target_type_keys=tuple(str(item) for item in _list(data.get("target_type_keys", []))),
        display_name=str(data.get("display_name", "")),
        description=str(data.get("description", "")),
        payload=payload,
        system=_json_object(data.get("system", {})),
    )


def _migration_record_from_json(value: object) -> RtgMigrationRecord:
    data = _object(value)
    return RtgMigrationRecord(
        migration_id=str(data["migration_id"]) if data.get("migration_id") is not None else None,
        description=str(data["description"]),
        status=str(data.get("status", "draft")),
        schema_make_live=_uuid_tuple(data.get("schema_make_live", [])),
        schema_make_non_live=_uuid_tuple(data.get("schema_make_non_live", [])),
        constraint_make_live=_uuid_tuple(data.get("constraint_make_live", [])),
        constraint_make_non_live=_uuid_tuple(data.get("constraint_make_non_live", [])),
        graph_make_live=_uuid_tuple(data.get("graph_make_live", [])),
        graph_make_non_live=_uuid_tuple(data.get("graph_make_non_live", [])),
        schema_replacements=tuple(
            _migration_replacement_from_json(item)
            for item in _list(data.get("schema_replacements", []))
        ),
        constraint_replacements=tuple(
            _migration_replacement_from_json(item)
            for item in _list(data.get("constraint_replacements", []))
        ),
        graph_replacements=tuple(
            _migration_replacement_from_json(item)
            for item in _list(data.get("graph_replacements", []))
        ),
        evidence=tuple(
            _migration_evidence_from_json(item) for item in _list(data.get("evidence", []))
        ),
        metadata=_json_object(data.get("metadata", {})),
    )


def _migration_replacement_from_json(value: object) -> RtgMigrationReplacement:
    data = _object(value)
    return RtgMigrationReplacement(
        old_resource_id=UUID(str(data["old_resource_id"])),
        new_resource_id=UUID(str(data["new_resource_id"])),
    )


def _migration_evidence_from_json(value: object) -> RtgMigrationEvidence:
    data = _object(value)
    return RtgMigrationEvidence(
        evidence_id=str(data["evidence_id"]),
        kind=str(data["kind"]),
        reference=str(data["reference"]),
        summary=str(data["summary"]),
        metadata=_json_object(data.get("metadata", {})),
    )


def _cutover_options_from_json(value: object) -> RtgControllerCutoverOptions:
    data = _object(value)
    return RtgControllerCutoverOptions(
        validation_mode=str(data.get("validation_mode", "strict")),
        prune_retired=bool(data.get("prune_retired", True)),
        failure_restore=str(data.get("failure_restore", "restore_pre_cutover_snapshot")),
    )


def _ledger_failure_from_json(value: object) -> RtgControllerLedgerFailureRecord:
    data = _object(value)
    ledger_position = data.get("ledger_position")
    return RtgControllerLedgerFailureRecord(
        transaction_id=UUID(str(data["transaction_id"])),
        ledger_position=int(cast(int, ledger_position)) if ledger_position is not None else None,
        operation_name=str(data["operation_name"]),
        record_kind=str(data["record_kind"]),
        payload_json=str(data["payload_json"]),
        failure_message=str(data["failure_message"]),
        retry_count=int(cast(int, data["retry_count"])),
        first_failed_timestamp=str(data["first_failed_timestamp"]),
        last_failed_timestamp=str(data["last_failed_timestamp"]),
    )


def _query_spec_from_json(value: object) -> RtgQuerySpec:
    data = _object(value)
    return RtgQuerySpec(
        anchor_buckets=tuple(
            RtgQueryAnchorBucket(
                name=str(item["name"]),
                anchor_type_keys=tuple(str(key) for key in _list(item["anchor_type_keys"])),
            )
            for item in _objects(data.get("anchor_buckets", []))
        ),
        link_requirements=tuple(
            RtgQueryLinkRequirement(
                name=str(item["name"]),
                source_bucket=str(item["source_bucket"]),
                target_bucket=str(item["target_bucket"]),
                link_type_keys=tuple(str(key) for key in _list(item["link_type_keys"])),
            )
            for item in _objects(data.get("link_requirements", []))
        ),
        data_requirements=tuple(
            RtgQueryDataRequirement(
                name=str(item["name"]),
                anchor_bucket=str(item["anchor_bucket"]),
                data_type_key=str(item["data_type_key"]),
                required=bool(item.get("required", True)),
                predicates=tuple(
                    _query_predicate_from_json(predicate)
                    for predicate in _list(item.get("predicates", []))
                ),
            )
            for item in _objects(data.get("data_requirements", []))
        ),
        return_spec=_query_return_spec_from_json(data.get("return_spec", {})),
        diagnostic_options=_query_diagnostic_options_from_json(data.get("diagnostic_options", {})),
    )


def _query_predicate_from_json(value: object) -> RtgQueryPropertyPredicate:
    data = _object(value)
    return RtgQueryPropertyPredicate(
        path=tuple(str(item) for item in _list(data.get("path", []))),
        operator=str(data["operator"]),
        value=cast(JsonValue, data.get("value")),
        values=tuple(
            cast(str | int | float | bool | None, item) for item in _list(data.get("values", []))
        ),
        case_sensitive=bool(data.get("case_sensitive", False)),
        regex_flags=tuple(str(item) for item in _list(data.get("regex_flags", []))),
    )


def _query_return_spec_from_json(value: object) -> RtgQueryReturnSpec:
    data = _object(value)
    return RtgQueryReturnSpec(
        anchor_buckets=tuple(str(item) for item in _list(data.get("anchor_buckets", []))),
        link_requirements=tuple(str(item) for item in _list(data.get("link_requirements", []))),
        data_requirements=tuple(str(item) for item in _list(data.get("data_requirements", []))),
        properties=tuple(
            (str(item[0]), tuple(str(path_item) for path_item in _list(item[1])))
            for item in _list(data.get("properties", []))
            if isinstance(item, list | tuple) and len(item) == 2
        ),
    )


def _query_diagnostic_options_from_json(value: object) -> RtgQueryDiagnosticOptions:
    data = _object(value)
    return RtgQueryDiagnosticOptions(
        include_non_fatal=bool(data.get("include_non_fatal", True)),
        unknown_term_guidance=str(data.get("unknown_term_guidance", "suggest_discovery")),
    )


def _uuid_tuple(value: object) -> tuple[UUID, ...]:
    return tuple(UUID(str(item)) for item in _list(value))


def _optional_uuid_from_json(value: object) -> UUID | None:
    return None if value is None else UUID(str(value))


def _optional_int_from_json(value: object) -> int | None:
    return None if value is None else int(cast(int, value))


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RtgControllerReplayFailed("expected JSON object")
    return cast(dict[str, object], value)


def _objects(value: object) -> tuple[dict[str, object], ...]:
    return tuple(_object(item) for item in _list(value))


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise RtgControllerReplayFailed("expected JSON list")
    return cast(list[object], value)


def _json_object(value: object) -> JsonObject:
    if not isinstance(value, dict):
        raise RtgControllerReplayFailed("expected JSON object")
    return cast(JsonObject, value)
