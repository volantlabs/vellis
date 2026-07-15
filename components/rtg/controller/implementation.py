from __future__ import annotations

import dataclasses
import threading
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
    RtgValidationError,
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
    RtgControllerLiveGraphValidationResult,
    RtgControllerMigrationCounts,
    RtgControllerObjectNotFound,
    RtgControllerOperationResult,
    RtgControllerPreconditionFailed,
    RtgControllerRecoveryIndeterminate,
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
    RtgQueryAggregation,
    RtgQueryAggregationFunction,
    RtgQueryAnchorBucket,
    RtgQueryDataRequirement,
    RtgQueryDiagnosticOptions,
    RtgQueryEngine,
    RtgQueryLinkRequirement,
    RtgQueryOperator,
    RtgQueryOptions,
    RtgQueryPropertyPredicate,
    RtgQueryResult,
    RtgQueryReturnSpec,
    RtgQuerySpec,
    RtgQueryUnknownTermGuidance,
)
from components.rtg.schema.protocol import (
    RtgSchema,
    RtgSchemaDefinition,
    RtgSchemaSnapshot,
)
from components.storage.json_file.protocol import JsonFileStorage


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
class _SnapshotValidationView:
    snapshot: object

    def export_snapshot(self) -> object:
        return self.snapshot


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
    ) -> None:
        self._graph = graph
        self._schema = schema
        self._constraints = constraints
        self._migration = migration
        self._change_validator = change_validator
        self._query_engine = query_engine
        self._json_storage = json_storage
        self._lock = threading.RLock()

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
    ) -> InProcessRtgController:
        required = (
            (graph, ("put_anchor", "get_object", "export_snapshot", "replace_snapshot")),
            (
                schema,
                ("put_definition", "list_definitions", "export_snapshot", "replace_snapshot"),
            ),
            (
                constraints,
                ("put_constraint", "list_constraints", "export_snapshot", "replace_snapshot"),
            ),
            (
                migration,
                ("put_migration", "get_migration", "export_snapshot", "replace_snapshot"),
            ),
            (change_validator, ("validate_batch", "validate_graph_state")),
            (query_engine, ("execute",)),
            (json_storage, ("write", "read")),
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
        with self._lock:
            resolved, generated_ids = self._resolve_batch_with_generated_ids(change_batch)
            if operation_name == "apply_live_graph_changes":
                self._validate_live_graph_lane(resolved.graph_changes)
            if operation_name == "stage_knowledge_changes":
                self._validate_knowledge_lane(resolved)
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
                    raise RtgControllerValidationFailed(
                        "change batch has blocking findings",
                        validation_report=validation_report,
                    )
            preimage = self._capture_apply_preimage(resolved)
            try:
                applied = self._apply_resolved_batch(resolved)
            except Exception as error:
                self._restore_apply_preimage(preimage)
                raise RtgControllerApplyFailed(str(error)) from error
            return RtgControllerOperationResult(
                status="applied",
                generated_ids=generated_ids,
                applied_changes=applied,
                validation_report=validation_report,
                details=_operation_details(operation_name, resolved),
            )

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
        saga_id = uuid4()
        with self._lock:
            pre_snapshot = self.export_system_snapshot()
            try:
                migration = self._migration.get_migration(migration_id)
                plan = RtgMigrationCutoverPlan.from_migration(migration)
            except Exception as error:
                raise RtgControllerPreconditionFailed(str(error)) from error
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
                    self._mark_migration_failed(
                        migration_id,
                        saga_id=saga_id,
                        summary="cutover validation has blocking findings",
                        validation_report=validation_report,
                    )
                    raise RtgControllerValidationFailed(
                        "cutover validation has blocking findings",
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
                            guide_topics=("workflow_patterns",),
                            mutation_state="live_state_preserved",
                        ),
                    )
            try:
                applied = self._apply_cutover_plan(
                    plan,
                    migration=migration,
                    options=options,
                    validate_actual_post_state=options.validation_mode == "strict",
                )
            except Exception as error:
                try:
                    self._replace_state_from_snapshot(pre_snapshot, validate_semantics=False)
                except Exception as restore_error:
                    raise RtgControllerRecoveryIndeterminate(
                        f"cutover failed: {error}; compensation failed: {restore_error}",
                        diagnostic=rtg_diagnostic(
                            code="controller.cutover.compensation_failed",
                            category="snapshot_recovery",
                            path="rtg_apply_migration_cutover",
                            problem=(
                                "Cutover failed and the coordinated pre-cutover state could not "
                                "be restored completely."
                            ),
                            remedy=(
                                "Stop writes and recover the managed system from a confirmed "
                                "runtime cursor or coordinated snapshot before continuing."
                            ),
                            mutation_state="indeterminate",
                        ),
                    ) from restore_error
                self._mark_migration_failed(
                    migration_id,
                    saga_id=saga_id,
                    summary=str(error),
                    validation_report=(
                        error.validation_report
                        if isinstance(error, RtgControllerValidationFailed)
                        else None
                    ),
                )
                if isinstance(error, RtgControllerValidationFailed):
                    raise
                raise RtgControllerApplyFailed(str(error)) from error
            return RtgControllerOperationResult(
                status="cutover_applied",
                applied_changes=applied,
                validation_report=validation_report,
            )

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
            try:
                return self._change_validator.validate_graph_state(
                    self._graph,
                    self._schema,
                    self._constraints,
                    self._migration,
                    self._query_engine,
                    migration_ids,
                    RtgValidationOptions(
                        tracks=options.tracks,
                        finding_limit=options.finding_limit,
                    ),
                )
            except RtgValidationError as error:
                raise RtgControllerValidationFailed(str(error)) from error

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
            staged_work = bool(
                non_live_schema
                or non_live_constraints
                or non_live_graph_counts
                or migration_counts["draft"]
                or migration_counts["ready"]
                or migration_counts["failed"]
            )
            if staged_work:
                classification = "has_staged_work"
            elif live_graph_total:
                classification = "populated"
            elif live_schema:
                classification = "schema_only"
            else:
                classification = "empty"
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
                migration_counts_scope="current_migration_store",
                recommended_workflows=_recommended_workflows(classification),
                recommended_next_steps=_recommended_next_steps(classification),
            )

    def export_system_snapshot(self) -> RtgSystemSnapshot:
        with self._lock:
            return RtgSystemSnapshot(
                graph=self._graph.export_snapshot(),
                schema=self._schema.export_snapshot(),
                constraints=self._constraints.export_snapshot(),
                migration=self._migration.export_snapshot(),
            )

    def persist_system_snapshot(self, relative_path: str) -> RtgControllerOperationResult:
        with self._lock:
            snapshot = self.export_system_snapshot()
            try:
                self._json_storage.write(relative_path, _to_json_value(snapshot))
            except Exception as error:
                raise RtgControllerSnapshotFailed(str(error)) from error
            return RtgControllerOperationResult(
                status="snapshot_persisted",
                snapshot=snapshot,
            )

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
                        guide_topics=("workflow_patterns", "snapshot_recovery"),
                        mutation_state="not_mutated",
                    ),
                ) from error
            return RtgPersistedSnapshotDocument(relative_path=relative_path, snapshot=snapshot)

    def abandon_migration(
        self,
        migration_id: str,
        reason: str | None = None,
    ) -> RtgControllerOperationResult:
        with self._lock:
            try:
                migration = self._migration.get_migration(migration_id)
            except Exception as error:
                raise RtgControllerPreconditionFailed(str(error)) from error
            details = self._apply_abandon_migration(
                migration_id,
                reason=reason,
                migration=migration,
            )
            return RtgControllerOperationResult(
                status="migration_abandoned",
                details=details,
            )

    def restore_from_snapshot(
        self,
        snapshot: RtgSystemSnapshot,
    ) -> RtgControllerOperationResult:
        with self._lock:
            try:
                self._replace_state_from_snapshot(snapshot, validate_semantics=True)
            except RtgControllerRecoveryIndeterminate:
                raise
            except Exception as error:
                raise RtgControllerSnapshotFailed(str(error)) from error
            return RtgControllerOperationResult(status="restore_applied")

    def _replace_state_from_snapshot(
        self,
        snapshot: RtgSystemSnapshot,
        *,
        validate_semantics: bool,
    ) -> None:
        candidates = self._snapshot_validation_views(snapshot)
        if validate_semantics:
            validation_report = self._change_validator.validate_graph_state(
                *candidates,
                self._query_engine,
                validation_options=RtgValidationOptions(),
            )
            if not validation_report.accepted:
                codes = ", ".join(sorted({finding.code for finding in validation_report.findings}))
                raise RtgControllerSnapshotFailed(
                    f"snapshot state violates controller invariants: {codes}",
                    diagnostic=rtg_diagnostic(
                        code="controller.snapshot.semantic_validation_failed",
                        category="snapshot_recovery",
                        path="snapshot",
                        problem=(
                            "The coordinated snapshot is structurally valid but semantically "
                            "inconsistent."
                        ),
                        remedy=(
                            "Repair or select a snapshot whose graph, schema, constraints, and "
                            "migration state validate together."
                        ),
                        mutation_state="live_state_preserved",
                    ),
                )
        pre_snapshot = self.export_system_snapshot()
        try:
            self._replace_component_snapshots(snapshot)
        except Exception as error:
            try:
                self._replace_component_snapshots(pre_snapshot)
            except Exception as restore_error:
                raise RtgControllerRecoveryIndeterminate(
                    f"snapshot replacement failed: {error}; "
                    f"compensation failed: {restore_error}",
                    diagnostic=rtg_diagnostic(
                        code="controller.snapshot.compensation_failed",
                        category="snapshot_recovery",
                        path="snapshot",
                        problem=(
                            "Snapshot replacement failed and the coordinated preimage could not "
                            "be restored completely."
                        ),
                        remedy=(
                            "Stop writes and recover the managed system from a confirmed runtime "
                            "cursor or coordinated snapshot before continuing."
                        ),
                        mutation_state="indeterminate",
                    ),
                ) from restore_error
            raise

    def _snapshot_validation_views(
        self, snapshot: RtgSystemSnapshot
    ) -> tuple[object, object, object, object]:
        components_and_snapshots = (
            (self._graph, snapshot.graph),
            (self._schema, snapshot.schema),
            (self._constraints, snapshot.constraints),
            (self._migration, snapshot.migration),
        )
        importers = tuple(
            getattr(type(component), "import_snapshot", None)
            for component, _snapshot in components_and_snapshots
        )
        if all(callable(importer) for importer in importers):
            return tuple(
                cast(Any, importer)(component_snapshot)
                for importer, (_component, component_snapshot) in zip(
                    importers, components_and_snapshots, strict=True
                )
            )  # type: ignore[return-value]
        return tuple(
            _SnapshotValidationView(component_snapshot)
            for _component, component_snapshot in components_and_snapshots
        )  # type: ignore[return-value]

    def _replace_component_snapshots(self, snapshot: RtgSystemSnapshot) -> None:
        self._graph.replace_snapshot(snapshot.graph)
        self._schema.replace_snapshot(snapshot.schema)
        self._constraints.replace_snapshot(snapshot.constraints)
        self._migration.replace_snapshot(snapshot.migration)

    def _apply_abandon_migration(
        self,
        migration_id: str,
        *,
        reason: str | None,
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
        saga_id: UUID,
        summary: str,
        validation_report: RtgValidationReport | None,
    ) -> JsonObject:
        metadata: JsonObject = {
            "saga_id": str(saga_id),
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
            if ref.local_ref not in resolved:
                generated = uuid4()
                resolved[ref.local_ref] = str(generated)
                generated_ids[ref.local_ref] = generated
            value = resolved[ref.local_ref]
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
            self._migration.replace_snapshot(preimage.migration_snapshot)

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
    if classification == "empty":
        return ("connection_state_check", "schema_bootstrap")
    if classification == "schema_only":
        return ("schema_discovery", "data_ingest")
    if classification == "has_staged_work":
        return ("staged_work_review", "cutover_or_abandon")
    return ("query_answer", "safe_update", "snapshot_recovery")


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


def _system_snapshot_from_json(value: object) -> RtgSystemSnapshot:
    data = _object(value)
    return RtgSystemSnapshot(
        graph=_graph_snapshot_from_json(data["graph"]),
        schema=_schema_snapshot_from_json(data["schema"]),
        constraints=_constraint_snapshot_from_json(data["constraints"]),
        migration=_migration_snapshot_from_json(data["migration"]),
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
            group_by_bindings=tuple(
                str(item) for item in _list(payload_data.get("group_by_bindings", []))
            ),
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
                required=bool(item.get("required", True)),
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
        operator=cast(RtgQueryOperator, str(data["operator"])),
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
        group_by=tuple(
            (str(item[0]), tuple(str(path_item) for path_item in _list(item[1])))
            for item in _list(data.get("group_by", []))
            if isinstance(item, list | tuple) and len(item) == 2
        ),
        aggregations=tuple(
            RtgQueryAggregation(
                name=str(item["name"]),
                function=cast(RtgQueryAggregationFunction, str(item["function"])),
                binding=str(item["binding"]),
            )
            for item in _objects(data.get("aggregations", []))
        ),
    )


def _query_diagnostic_options_from_json(value: object) -> RtgQueryDiagnosticOptions:
    data = _object(value)
    return RtgQueryDiagnosticOptions(
        include_non_fatal=bool(data.get("include_non_fatal", True)),
        unknown_term_guidance=cast(
            RtgQueryUnknownTermGuidance,
            str(data.get("unknown_term_guidance", "suggest_discovery")),
        ),
    )


def _uuid_tuple(value: object) -> tuple[UUID, ...]:
    return tuple(UUID(str(item)) for item in _list(value))


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RtgControllerSnapshotFailed("expected JSON object")
    return cast(dict[str, object], value)


def _objects(value: object) -> tuple[dict[str, object], ...]:
    return tuple(_object(item) for item in _list(value))


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise RtgControllerSnapshotFailed("expected JSON list")
    return cast(list[object], value)


def _json_object(value: object) -> JsonObject:
    if not isinstance(value, dict):
        raise RtgControllerSnapshotFailed("expected JSON object")
    return cast(JsonObject, value)
