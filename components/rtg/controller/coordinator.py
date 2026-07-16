from __future__ import annotations

import asyncio
import dataclasses
import hashlib
from typing import Never, cast
from uuid import UUID

from components.rtg.change_validation import (
    RTG_CHANGE_VALIDATION_ACTIONS,
    RtgChangeBatch,
    RtgChangeReference,
    RtgConstraintChangeSet,
    RtgGraphChangeSet,
    RtgMigrationChangeSet,
    RtgMigrationStatusChange,
    RtgSchemaChangeSet,
    RtgValidationInputInvalid,
    RtgValidationOptions,
    RtgValidationReport,
)
from components.rtg.constraints import (
    RTG_CONSTRAINTS_ACTIONS,
    RtgConstraintCountSummary,
    RtgConstraintDefinition,
    RtgConstraintSnapshot,
)
from components.rtg.controller.planning import (
    change_batch_from_cutover_plan,
    is_live,
    operation_details,
    resolve_batch_with_generated_ids,
    validate_knowledge_lane,
    validate_live_graph_lane,
)
from components.rtg.controller.protocol import (
    RtgAnchorTypeDiscoveryEntry,
    RtgAnchorTypeDiscoveryResult,
    RtgController,
    RtgControllerAppliedChanges,
    RtgControllerApplyFailed,
    RtgControllerCandidateCounts,
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
    RtgControllerSnapshotFailed,
    RtgControllerSystemState,
    RtgControllerValidationFailed,
    RtgPersistedSnapshotDocument,
    RtgPersistedSnapshotList,
    RtgSnapshotPersistenceResult,
    RtgSnapshotStateCounts,
    RtgSystemSnapshot,
)
from components.rtg.controller.runtime_binding import (
    CONTROLLER_RUNTIME_BINDING,
)
from components.rtg.graph import (
    RTG_GRAPH_ACTIONS,
    RtgDataObject,
    RtgGraphSnapshot,
    RtgLink,
    RtgObject,
    RtgTypeCountList,
)
from components.rtg.migration import (
    RTG_MIGRATION_ACTIONS,
    RtgMigrationCandidateOwners,
    RtgMigrationCountSummary,
    RtgMigrationCutoverPlan,
    RtgMigrationNotFound,
    RtgMigrationRecord,
    RtgMigrationRecordList,
    RtgMigrationSnapshot,
    RtgMigrationStatusInvalid,
)
from components.rtg.query import (
    RTG_QUERY_ACTIONS,
    RtgQueryOptions,
    RtgQueryResult,
    RtgQuerySpec,
    RtgQuerySpecInvalid,
    RtgQueryUnsupported,
)
from components.rtg.schema import (
    RTG_SCHEMA_ACTIONS,
    RtgSchemaAnchorTypeSummaryList,
    RtgSchemaCountSummary,
    RtgSchemaDefinition,
    RtgSchemaDefinitionList,
    RtgSchemaPack,
    RtgSchemaSnapshot,
)
from components.runtime.component_adapter import (
    ComponentAdapter,
    ComponentExecution,
    RuntimeComponentDeadlineExceeded,
    RuntimeRemoteFault,
    create_typed_handler_adapter,
    decode_typed,
    encode_json,
)
from components.runtime.messaging import (
    RuntimeCanonicalEffectReference,
    RuntimeTraceDisposition,
    canonical_json,
)
from components.storage.json_file import (
    JSON_FILE_STORAGE_ACTIONS,
    JsonDocument,
    JsonDocumentList,
    JsonDocumentMetadata,
)


class RtgControllerCoordinator:
    """One ordinary component whose actions coordinate RTG occurrences by messages."""

    def __init__(
        self,
        *,
        graph_key: str = "vellis.graph.primary",
        schema_key: str = "vellis.schema.primary",
        constraints_key: str = "vellis.constraints.primary",
        migration_key: str = "vellis.migration.primary",
        query_key: str = "vellis.query.primary",
        validation_key: str = "vellis.validation.primary",
        json_storage_key: str = "vellis.storage.json.primary",
    ) -> None:
        self._keys = {
            "graph": graph_key,
            "schema": schema_key,
            "constraints": constraints_key,
            "migration": migration_key,
            "query": query_key,
            "validation": validation_key,
            "json": json_storage_key,
        }

    def create_adapter(self) -> ComponentAdapter:
        handlers = {
            action.method_name: self._handler(action.method_name)
            for action in CONTROLLER_RUNTIME_BINDING.actions
        }
        return create_typed_handler_adapter(
            RtgController,
            binding=CONTROLLER_RUNTIME_BINDING,
            failure_types=(),
            handlers=handlers,
        )

    def _handler(self, name: str):
        async def handle(
            _args: tuple[object, ...],
            kwargs: dict[str, object],
            execution: ComponentExecution,
        ) -> None:
            result = await self._execute(name, kwargs, execution)
            if not execution.completed:
                await execution.complete(result)

        return handle

    async def _execute(
        self,
        name: str,
        kwargs: dict[str, object],
        execution: ComponentExecution,
    ) -> object:
        if name == "execute_query":
            return await self._execute_query(kwargs, execution)
        if name == "validate_graph":
            return await self._validate_graph(kwargs, execution)
        if name == "validate_live_graph_changes":
            return await self._validate_live(kwargs, execution)
        if name in {"apply_live_graph_changes", "stage_knowledge_changes"}:
            return await self._apply_batch(name, kwargs, execution)
        if name == "apply_migration_cutover":
            return await self._apply_migration_cutover(kwargs, execution)
        if name == "abandon_migration":
            return await self._abandon_migration(kwargs, execution)
        if name == "restore_from_snapshot":
            return await self._restore(kwargs, execution)
        if name == "persist_system_snapshot":
            return await self._persist_snapshot(kwargs, execution)
        if name == "list_persisted_snapshots":
            return await self._list_persisted(kwargs, execution)
        if name == "load_persisted_snapshot":
            return await self._load_persisted(kwargs, execution)
        if name == "get_object":
            return await self._get_object(kwargs, execution)
        if name == "list_migrations":
            return await self._list_migrations(kwargs, execution)
        if name == "get_migration":
            return await self._get_migration(kwargs, execution)
        if name == "discover_anchor_types":
            return await self._discover_anchor_types(kwargs, execution)
        if name == "get_schema_pack":
            return await self._get_schema_pack(kwargs, execution)
        if name == "list_schema_definitions_by_type_key":
            return await self._list_schema_definitions_by_type_key(kwargs, execution)
        if name == "get_system_state":
            return await self._get_system_state(execution)

        if name == "export_system_snapshot":
            return await self._snapshot(execution, prefix="export")
        raise RtgControllerPreconditionFailed(f"unsupported controller action: {name}")

    async def _list_schema_definitions_by_type_key(
        self, kwargs: dict[str, object], execution: ComponentExecution
    ) -> RtgSchemaDefinitionList:
        try:
            value = await execution.call(
                "schema-list-definitions-by-type-key",
                RTG_SCHEMA_ACTIONS["list_definitions_by_type_key"],
                {
                    "schema_type_key": kwargs["type_key"],
                    "kind": kwargs.get("kind"),
                    "live": kwargs.get("live"),
                    "offset": kwargs.get("offset", 0),
                    "limit": kwargs.get("limit"),
                },
                target=execution.address_for(self._keys["schema"]),
            )
            return decode_typed(value, RtgSchemaDefinitionList)
        except RuntimeRemoteFault as error:
            raise RtgControllerPreconditionFailed(str(error)) from error

    async def _get_object(
        self, kwargs: dict[str, object], execution: ComponentExecution
    ) -> RtgObject:
        try:
            value = await execution.call(
                "graph-get-object",
                RTG_GRAPH_ACTIONS["get_object"],
                {"object_uuid": kwargs["object_uuid"]},
                target=execution.address_for(self._keys["graph"]),
            )
        except RuntimeRemoteFault as error:
            raise RtgControllerObjectNotFound(str(error)) from error
        return cast(RtgObject, decode_typed(value, RtgObject))

    async def _list_migrations(
        self, kwargs: dict[str, object], execution: ComponentExecution
    ) -> RtgMigrationRecordList:
        try:
            value = await execution.call(
                "migration-list",
                RTG_MIGRATION_ACTIONS["list_migrations"],
                {
                    "status": kwargs.get("status"),
                    "offset": kwargs.get("offset", 0),
                    "limit": kwargs.get("limit", 100),
                },
                target=execution.address_for(self._keys["migration"]),
            )
        except RuntimeRemoteFault as error:
            self._raise_remote(error, (RtgMigrationStatusInvalid,))
        return cast(RtgMigrationRecordList, decode_typed(value, RtgMigrationRecordList))

    async def _get_migration(
        self, kwargs: dict[str, object], execution: ComponentExecution
    ) -> RtgMigrationRecord:
        try:
            value = await execution.call(
                "migration-get",
                RTG_MIGRATION_ACTIONS["get_migration"],
                {"migration_id": kwargs["migration_id"]},
                target=execution.address_for(self._keys["migration"]),
            )
        except RuntimeRemoteFault as error:
            self._raise_remote(error, (RtgMigrationNotFound,))
        return cast(RtgMigrationRecord, decode_typed(value, RtgMigrationRecord))

    async def _discover_anchor_types(
        self, kwargs: dict[str, object], execution: ComponentExecution
    ) -> RtgAnchorTypeDiscoveryResult:
        options = kwargs.get("discovery_options")
        include_non_live = bool(getattr(options, "include_non_live", False))
        limit = getattr(options, "limit", None)
        if limit is not None and limit <= 0:
            raise RtgControllerDiscoveryFailed("limit must be positive")
        try:
            counts_value, summaries_value = await asyncio.gather(
                execution.call(
                    "discovery-anchor-counts",
                    RTG_GRAPH_ACTIONS["count_by_type"],
                    {"kind": "anchor", "live": True},
                    target=execution.address_for(self._keys["graph"]),
                ),
                execution.call(
                    "discovery-anchor-summaries",
                    RTG_SCHEMA_ACTIONS["list_anchor_type_summaries"],
                    {"live": None if include_non_live else True},
                    target=execution.address_for(self._keys["schema"]),
                ),
            )
        except RuntimeRemoteFault as error:
            raise RtgControllerDiscoveryFailed(str(error)) from error
        counts = cast(RtgTypeCountList, decode_typed(counts_value, RtgTypeCountList))
        summaries = cast(
            RtgSchemaAnchorTypeSummaryList,
            decode_typed(summaries_value, RtgSchemaAnchorTypeSummaryList),
        )
        live_counts = {item.type: item.count for item in counts.counts}
        return RtgAnchorTypeDiscoveryResult(
            tuple(
                RtgAnchorTypeDiscoveryEntry(
                    item.type_key,
                    item.description,
                    live_counts.get(item.type_key, 0),
                )
                for item in summaries.anchor_types[:limit]
            )
        )

    async def _get_schema_pack(
        self, kwargs: dict[str, object], execution: ComponentExecution
    ) -> RtgControllerSchemaPack:
        options = kwargs.get("schema_pack_options")
        live = getattr(options, "live", True)
        include_counts = bool(getattr(options, "include_live_counts", True))
        try:
            pack_value = await execution.call(
                "schema-pack",
                RTG_SCHEMA_ACTIONS["get_schema_pack"],
                {
                    "anchor_type_keys": kwargs["anchor_type_keys"],
                    "live": live,
                },
                target=execution.address_for(self._keys["schema"]),
            )
            count_value = (
                await execution.call(
                    "schema-pack-live-counts",
                    RTG_GRAPH_ACTIONS["count_by_type"],
                    {"kind": None, "live": True},
                    target=execution.address_for(self._keys["graph"]),
                )
                if include_counts
                else None
            )
        except RuntimeRemoteFault as error:
            raise RtgControllerDiscoveryFailed(str(error)) from error
        pack = cast(RtgSchemaPack, decode_typed(pack_value, RtgSchemaPack))
        counts = (
            cast(RtgTypeCountList, decode_typed(count_value, RtgTypeCountList)).counts
            if count_value is not None
            else ()
        )
        return RtgControllerSchemaPack(pack, {item.type: item.count for item in counts})

    async def _get_system_state(self, execution: ComponentExecution) -> RtgControllerSystemState:
        try:
            (
                schema_summary_value,
                constraint_summary_value,
                live_graph_value,
                non_live_graph_value,
                migration_summary_value,
                persisted,
            ) = await asyncio.gather(
                execution.call(
                    "state-schema-summary",
                    RTG_SCHEMA_ACTIONS["count_summary"],
                    {},
                    target=execution.address_for(self._keys["schema"]),
                ),
                execution.call(
                    "state-constraint-summary",
                    RTG_CONSTRAINTS_ACTIONS["count_summary"],
                    {},
                    target=execution.address_for(self._keys["constraints"]),
                ),
                execution.call(
                    "state-live-graph",
                    RTG_GRAPH_ACTIONS["count_by_type"],
                    {"kind": None, "live": True},
                    target=execution.address_for(self._keys["graph"]),
                ),
                execution.call(
                    "state-non-live-graph",
                    RTG_GRAPH_ACTIONS["count_by_type"],
                    {"kind": None, "live": False},
                    target=execution.address_for(self._keys["graph"]),
                ),
                execution.call(
                    "state-migration-summary",
                    RTG_MIGRATION_ACTIONS["count_summary"],
                    {},
                    target=execution.address_for(self._keys["migration"]),
                ),
                self._list_persisted({"offset": 0, "limit": 100}, execution),
            )
        except RuntimeRemoteFault as error:
            raise RtgControllerDiscoveryFailed(str(error)) from error
        schema_summary = decode_typed(schema_summary_value, RtgSchemaCountSummary)
        constraint_summary = decode_typed(constraint_summary_value, RtgConstraintCountSummary)
        live_graph = cast(RtgTypeCountList, decode_typed(live_graph_value, RtgTypeCountList))
        non_live_graph = cast(
            RtgTypeCountList,
            decode_typed(non_live_graph_value, RtgTypeCountList),
        )
        migration_summary = decode_typed(migration_summary_value, RtgMigrationCountSummary)
        non_live_graph_total = sum(item.count for item in non_live_graph.counts)
        live_graph_total = sum(item.count for item in live_graph.counts)
        staged = bool(
            schema_summary.non_live_total
            or constraint_summary.non_live_total
            or non_live_graph_total
            or migration_summary.draft
            or migration_summary.ready
            or migration_summary.failed
        )
        classification = (
            "has_staged_work"
            if staged
            else "populated"
            if live_graph_total
            else "schema_only"
            if schema_summary.live_total
            else "empty"
        )
        return RtgControllerSystemState(
            classification,
            RtgControllerSchemaCounts(
                schema_summary.anchor_live,
                schema_summary.data_object_live,
                schema_summary.link_live,
                schema_summary.live_total,
            ),
            live_graph,
            RtgControllerCandidateCounts(
                schema_summary.non_live_total,
                constraint_summary.non_live_total,
                non_live_graph_total,
                schema_summary.non_live_total
                + constraint_summary.non_live_total
                + non_live_graph_total,
            ),
            RtgControllerMigrationCounts(
                migration_summary.draft,
                migration_summary.ready,
                migration_summary.failed,
                migration_summary.applied,
                migration_summary.abandoned,
                migration_summary.total,
            ),
            tuple(str(item["relative_path"]) for item in persisted.snapshots),
            recommended_workflows=_recommended_workflows(classification),
            recommended_next_steps=_recommended_next_steps(classification),
        )

    async def _execute_query(
        self, kwargs: dict[str, object], execution: ComponentExecution
    ) -> RtgQueryResult:
        try:
            value = await execution.call(
                "execute-query",
                RTG_QUERY_ACTIONS["execute"],
                {
                    "query_spec": cast(RtgQuerySpec, kwargs["query_spec"]),
                    "query_options": cast(RtgQueryOptions | None, kwargs.get("query_options")),
                },
                target=execution.address_for(self._keys["query"]),
            )
        except RuntimeRemoteFault as error:
            self._raise_remote(error, (RtgQuerySpecInvalid, RtgQueryUnsupported))
        return cast(RtgQueryResult, decode_typed(value, RtgQueryResult))

    async def _validate_graph(
        self, kwargs: dict[str, object], execution: ComponentExecution
    ) -> RtgValidationReport:
        return await self._validation_call(
            "validate_graph_state",
            {
                "migration_ids": kwargs.get("migration_ids"),
                "validation_options": _validation_options(kwargs.get("validation_options")),
            },
            execution,
        )

    async def _validate_live(
        self, kwargs: dict[str, object], execution: ComponentExecution
    ) -> RtgControllerLiveGraphValidationResult:
        batch = RtgChangeBatch(graph_changes=cast(RtgGraphChangeSet, kwargs["graph_changes"]))
        resolved, generated_ids = await asyncio.to_thread(resolve_batch_with_generated_ids, batch)
        validate_live_graph_lane(resolved.graph_changes)
        report = await self._validation_call(
            "validate_batch",
            {
                "change_batch": resolved,
                "validation_options": _validation_options(kwargs.get("validation_options")),
            },
            execution,
        )
        return RtgControllerLiveGraphValidationResult(
            status="validated",
            mutation_state="not_mutated",
            accepted=report.accepted,
            generated_ids=generated_ids,
            validation_report=report,
        )

    async def _apply_batch(
        self,
        name: str,
        kwargs: dict[str, object],
        execution: ComponentExecution,
    ) -> RtgControllerOperationResult:
        mode = str(kwargs.get("validation_mode", "strict"))
        if mode not in {"strict", "skip"}:
            raise RtgControllerPreconditionFailed("validation_mode must be strict or skip")
        batch = (
            RtgChangeBatch(graph_changes=cast(RtgGraphChangeSet, kwargs["graph_changes"]))
            if name == "apply_live_graph_changes"
            else cast(RtgChangeBatch, kwargs["knowledge_changes"])
        )
        resolved, generated_ids = await asyncio.to_thread(resolve_batch_with_generated_ids, batch)
        if name == "apply_live_graph_changes":
            validate_live_graph_lane(resolved.graph_changes)
        else:
            validate_knowledge_lane(resolved)
        report = None
        if mode == "strict":
            report = await self._validation_call(
                "validate_batch",
                {
                    "change_batch": resolved,
                    "validation_options": RtgValidationOptions(finding_limit=100),
                },
                execution,
            )
            if not report.accepted:
                raise RtgControllerValidationFailed(
                    "change batch has blocking findings",
                    validation_report=report,
                )
        try:
            applied = await self._apply_resolved_batch(resolved, execution, prefix=name)
        except asyncio.CancelledError as error:
            raise RuntimeComponentDeadlineExceeded(f"{name} deadline expired") from error
        except RtgControllerRecoveryIndeterminate:
            raise
        except Exception as error:
            raise RtgControllerApplyFailed(str(error)) from error
        return RtgControllerOperationResult(
            status="applied",
            generated_ids=generated_ids,
            applied_changes=applied,
            validation_report=report,
            details=operation_details(name, resolved),
        )

    async def _apply_migration_cutover(
        self,
        kwargs: dict[str, object],
        execution: ComponentExecution,
    ) -> RtgControllerOperationResult:
        migration_id = str(kwargs["migration_id"])
        options = cast(
            RtgControllerCutoverOptions,
            kwargs.get("cutover_options") or RtgControllerCutoverOptions(),
        )
        if options.validation_mode not in {"strict", "skip"}:
            raise RtgControllerPreconditionFailed("validation_mode must be strict or skip")
        if options.failure_restore != "restore_pre_cutover_snapshot":
            raise RtgControllerPreconditionFailed(
                "failure_restore must be restore_pre_cutover_snapshot"
            )

        try:
            migration = await self._get_migration({"migration_id": migration_id}, execution)
            plan = RtgMigrationCutoverPlan.from_migration(migration)
        except Exception as error:
            raise RtgControllerPreconditionFailed(str(error)) from error
        change_batch = change_batch_from_cutover_plan(plan)
        status_changes = (
            (
                RtgMigrationStatusChange(RtgChangeReference(resource_id=migration_id), "ready", {}),
                RtgMigrationStatusChange(
                    RtgChangeReference(resource_id=migration_id), "applied", {}
                ),
            )
            if migration.status == "draft"
            else (
                RtgMigrationStatusChange(
                    RtgChangeReference(resource_id=migration_id), "applied", {}
                ),
            )
        )
        change_batch = dataclasses.replace(
            change_batch,
            migration_changes=RtgMigrationChangeSet(status_changes=status_changes),
        )
        validation_report: RtgValidationReport | None = None

        if options.validation_mode == "strict":
            await self._assert_cutover_candidates(plan, execution)
            validation_report = await self._validation_call(
                "validate_batch",
                {
                    "change_batch": change_batch,
                    "validation_options": RtgValidationOptions(finding_limit=100),
                },
                execution,
            )
            if not validation_report.accepted:
                await self._commit_failed_cutover(
                    migration,
                    "cutover validation has blocking findings",
                    validation_report,
                    execution,
                    RtgControllerValidationFailed(
                        "cutover validation has blocking findings",
                        validation_report=validation_report,
                    ),
                )
                return RtgControllerOperationResult(status="cutover_failed")

        try:
            applied = await self._apply_resolved_batch(
                change_batch,
                execution,
                prefix="cutover-live",
            )
            if options.validation_mode == "strict":
                post_report = await self._validation_call(
                    "validate_graph_state",
                    {
                        "migration_ids": None,
                        "validation_options": RtgValidationOptions(finding_limit=100),
                    },
                    execution,
                )
                if not post_report.accepted:
                    raise RtgControllerValidationFailed(
                        "post-cutover validation has blocking findings",
                        validation_report=post_report,
                    )
            if options.prune_retired:
                prune = RtgChangeBatch(
                    schema_changes=RtgSchemaChangeSet(
                        delete_definitions=tuple(
                            RtgChangeReference(resource_id=item)
                            for item in plan.schema_make_non_live
                        )
                    ),
                    constraint_changes=RtgConstraintChangeSet(
                        delete_constraints=tuple(
                            RtgChangeReference(resource_id=item)
                            for item in plan.constraint_make_non_live
                        )
                    ),
                    migration_changes=RtgMigrationChangeSet(
                        delete_migrations=(RtgChangeReference(resource_id=migration_id),)
                    ),
                )
                pruned = await self._apply_resolved_batch(
                    prune,
                    execution,
                    prefix="cutover-prune",
                )
                applied = dataclasses.replace(applied, deletes=applied.deletes + pruned.deletes)
        except asyncio.CancelledError as error:
            raise RtgControllerRecoveryIndeterminate(
                "cutover deadline expired after mutation began; reconstruction is required"
            ) from error
        except RtgControllerRecoveryIndeterminate:
            raise
        except Exception as error:
            raise RtgControllerRecoveryIndeterminate(
                f"cutover failed after component mutation began: {error}"
            ) from error
        return RtgControllerOperationResult(
            status="cutover_applied",
            applied_changes=applied,
            validation_report=validation_report,
        )

    async def _abandon_migration(
        self,
        kwargs: dict[str, object],
        execution: ComponentExecution,
    ) -> RtgControllerOperationResult:
        migration_id = str(kwargs["migration_id"])
        reason = cast(str | None, kwargs.get("reason"))
        try:
            migration = await self._get_migration({"migration_id": migration_id}, execution)
        except Exception as error:
            raise RtgControllerPreconditionFailed(str(error)) from error
        if migration.status == "applied":
            raise RtgControllerPreconditionFailed("applied migrations cannot be abandoned")
        shared = await self._shared_candidate_ids(migration, execution)
        pruned: dict[str, list[str]] = {"schema": [], "constraints": [], "graph": []}
        skipped: dict[str, list[dict[str, object]]] = {
            "schema": [],
            "constraints": [],
            "graph": [],
        }
        try:
            await self._prune_abandoned_candidates(
                migration,
                shared,
                pruned,
                skipped,
                execution,
            )
            await self._apply_resolved_batch(
                RtgChangeBatch(
                    migration_changes=RtgMigrationChangeSet(
                        status_changes=(
                            (
                                RtgMigrationStatusChange(
                                    RtgChangeReference(resource_id=migration_id),
                                    "abandoned",
                                    {"reason": reason or "abandoned through controller"},
                                ),
                            )
                            if migration.status != "abandoned"
                            else ()
                        ),
                        delete_migrations=(RtgChangeReference(resource_id=migration_id),),
                    )
                ),
                execution,
                prefix="abandon-migration",
            )
        except asyncio.CancelledError as error:
            raise RtgControllerRecoveryIndeterminate(
                "abandon deadline expired after mutation began; reconstruction is required"
            ) from error
        except Exception as error:
            raise RtgControllerRecoveryIndeterminate(
                f"abandon failed after mutation began: {error}"
            ) from error
        return RtgControllerOperationResult(
            status="migration_abandoned",
            details=cast(
                dict,
                {
                    "migration_id": migration_id,
                    "abandoned_status": "abandoned",
                    "deleted_migration_status": "abandoned",
                    "reason": reason,
                    "pruned_candidates": pruned,
                    "skipped_candidates": skipped,
                },
            ),
        )

    async def _assert_cutover_candidates(
        self,
        plan: RtgMigrationCutoverPlan,
        execution: ComponentExecution,
    ) -> None:
        calls = (
            *(
                ("schema", RTG_SCHEMA_ACTIONS["get_definition"], "definition_uuid", item)
                for item in (*plan.schema_make_non_live, *plan.schema_make_live)
            ),
            *(
                (
                    "constraints",
                    RTG_CONSTRAINTS_ACTIONS["get_constraint"],
                    "constraint_uuid",
                    item,
                )
                for item in (*plan.constraint_make_non_live, *plan.constraint_make_live)
            ),
            *(
                ("graph", RTG_GRAPH_ACTIONS["get_object"], "object_uuid", item)
                for item in (*plan.graph_make_non_live, *plan.graph_make_live)
            ),
        )
        for index, (component, action, argument, item) in enumerate(calls):
            try:
                await execution.call(
                    f"cutover-candidate-{index}-{component}",
                    action,
                    {argument: item},
                    target=execution.address_for(self._keys[component]),
                )
            except RuntimeRemoteFault as error:
                raise RtgControllerPreconditionFailed(str(error)) from error

    async def _mark_migration_failed(
        self,
        migration: RtgMigrationRecord,
        summary: str,
        report: RtgValidationReport | None,
        execution: ComponentExecution,
    ) -> tuple[RuntimeCanonicalEffectReference, ...]:
        migration_id = migration.migration_id
        if migration_id is None or migration.status in {"applied", "abandoned"}:
            return ()
        metadata: dict[str, object] = {
            "saga_id": str(execution.request.message_id),
            "summary": summary,
        }
        if report is not None:
            encoded_report = encode_json(report)
            metadata.update(
                {
                    "finding_count": len(report.findings),
                    "blocking_finding_count": sum(
                        finding.severity == "blocking" for finding in report.findings
                    ),
                    "validation_report_digest": hashlib.sha256(
                        canonical_json(encoded_report).encode()
                    ).hexdigest(),
                }
            )
        status_changes = (
            (
                RtgMigrationStatusChange(RtgChangeReference(resource_id=migration_id), "ready", {}),
                RtgMigrationStatusChange(
                    RtgChangeReference(resource_id=migration_id),
                    "failed",
                    cast(dict, metadata),
                ),
            )
            if migration.status == "draft"
            else (
                RtgMigrationStatusChange(
                    RtgChangeReference(resource_id=migration_id),
                    "failed",
                    cast(dict, metadata),
                ),
            )
        )
        step_key = "failed-cutover-migration-batch"
        try:
            await execution.call(
                step_key,
                RTG_MIGRATION_ACTIONS["apply_batch"],
                {"changes": RtgMigrationChangeSet(status_changes=status_changes)},
                target=execution.address_for(self._keys["migration"]),
            )
        except RuntimeRemoteFault as error:
            self._raise_remote(error, (RtgMigrationNotFound, RtgMigrationStatusInvalid))
        return (await execution.effect_reference(step_key),)

    async def _commit_failed_cutover(
        self,
        migration: RtgMigrationRecord,
        summary: str,
        report: RtgValidationReport | None,
        execution: ComponentExecution,
        error: Exception,
    ) -> None:
        references = await self._mark_migration_failed(
            migration,
            summary,
            report,
            execution,
        )
        if not references:
            raise RtgControllerRecoveryIndeterminate(
                "failed cutover status did not produce a replayable effect"
            )
        await execution.fault(
            error,
            canonical_effect=execution.superseding_aggregate_effect(references),
            disposition=RuntimeTraceDisposition.COMMITTED,
        )

    async def _prune_abandoned_candidates(
        self,
        migration: RtgMigrationRecord,
        shared: dict[str, set[UUID]],
        pruned: dict[str, list[str]],
        skipped: dict[str, list[dict[str, object]]],
        execution: ComponentExecution,
    ) -> None:
        sequence = 0
        delete_schema: list[RtgChangeReference] = []
        delete_constraints: list[RtgChangeReference] = []
        delete_anchors: list[RtgChangeReference] = []
        delete_data: list[RtgChangeReference] = []
        delete_links: list[RtgChangeReference] = []

        async def candidate(
            component: str,
            action: object,
            argument: str,
            item: UUID,
            value_type: object,
        ) -> object | None:
            nonlocal sequence
            sequence += 1
            try:
                value = await execution.call(
                    f"abandon-inspect-{sequence}-{component}",
                    action,  # type: ignore[arg-type]
                    {argument: item},
                    target=execution.address_for(self._keys[component]),
                )
            except RuntimeRemoteFault:
                return None
            return decode_typed(value, value_type)

        for item in migration.schema_make_live:
            if item in shared["schema"]:
                skipped["schema"].append({"resource_id": str(item), "reason": "shared"})
                continue
            definition = await candidate(
                "schema",
                RTG_SCHEMA_ACTIONS["get_definition"],
                "definition_uuid",
                item,
                RtgSchemaDefinition,
            )
            if definition is None:
                skipped["schema"].append({"resource_id": str(item), "reason": "missing"})
            elif is_live(definition):
                skipped["schema"].append({"resource_id": str(item), "reason": "live"})
            else:
                delete_schema.append(RtgChangeReference(resource_id=item))
                pruned["schema"].append(str(item))

        for item in migration.constraint_make_live:
            if item in shared["constraints"]:
                skipped["constraints"].append({"resource_id": str(item), "reason": "shared"})
                continue
            constraint = await candidate(
                "constraints",
                RTG_CONSTRAINTS_ACTIONS["get_constraint"],
                "constraint_uuid",
                item,
                RtgConstraintDefinition,
            )
            if constraint is None:
                skipped["constraints"].append({"resource_id": str(item), "reason": "missing"})
            elif is_live(constraint):
                skipped["constraints"].append({"resource_id": str(item), "reason": "live"})
            else:
                delete_constraints.append(RtgChangeReference(resource_id=item))
                pruned["constraints"].append(str(item))

        for item in migration.graph_make_live:
            if item in shared["graph"]:
                skipped["graph"].append({"resource_id": str(item), "reason": "shared"})
                continue
            graph_object = await candidate(
                "graph",
                RTG_GRAPH_ACTIONS["get_object"],
                "object_uuid",
                item,
                RtgObject,
            )
            if graph_object is None:
                skipped["graph"].append({"resource_id": str(item), "reason": "missing"})
            elif is_live(graph_object):
                skipped["graph"].append({"resource_id": str(item), "reason": "live"})
            else:
                if isinstance(graph_object, RtgLink):
                    delete_links.append(RtgChangeReference(resource_id=item))
                elif isinstance(graph_object, RtgDataObject):
                    delete_data.append(RtgChangeReference(resource_id=item))
                else:
                    delete_anchors.append(RtgChangeReference(resource_id=item))
                pruned["graph"].append(str(item))

        await self._apply_resolved_batch(
            RtgChangeBatch(
                graph_changes=RtgGraphChangeSet(
                    delete_anchors=tuple(delete_anchors),
                    delete_data_objects=tuple(delete_data),
                    delete_links=tuple(delete_links),
                ),
                schema_changes=RtgSchemaChangeSet(delete_definitions=tuple(delete_schema)),
                constraint_changes=RtgConstraintChangeSet(
                    delete_constraints=tuple(delete_constraints)
                ),
            ),
            execution,
            prefix="abandon-prune",
        )

    async def _shared_candidate_ids(
        self,
        migration: RtgMigrationRecord,
        execution: ComponentExecution,
    ) -> dict[str, set[UUID]]:
        migration_id = migration.migration_id
        declarations = (
            ("schema", migration.schema_make_live),
            ("constraints", migration.constraint_make_live),
            ("graph", migration.graph_make_live),
        )

        async def is_shared(kind: str, resource_id: UUID, index: int) -> tuple[str, UUID, bool]:
            value = await execution.call(
                f"abandon-owner-{kind}-{index}",
                RTG_MIGRATION_ACTIONS["find_candidate_owners"],
                {"kind": kind, "resource_id": resource_id},
                target=execution.address_for(self._keys["migration"]),
            )
            owners = decode_typed(value, RtgMigrationCandidateOwners).migration_ids
            return kind, resource_id, any(owner != migration_id for owner in owners)

        checks = await asyncio.gather(
            *(
                is_shared(kind, resource_id, index)
                for kind, resource_ids in declarations
                for index, resource_id in enumerate(resource_ids)
            )
        )
        shared: dict[str, set[UUID]] = {
            "schema": set(),
            "constraints": set(),
            "graph": set(),
        }
        for kind, resource_id, value in checks:
            if value:
                shared[kind].add(resource_id)
        return shared

    async def _apply_resolved_batch(
        self,
        batch: RtgChangeBatch,
        execution: ComponentExecution,
        *,
        prefix: str,
    ) -> RtgControllerAppliedChanges:
        declarations = (
            (
                "schema",
                RTG_SCHEMA_ACTIONS["apply_batch"],
                batch.schema_changes,
                RtgSchemaChangeSet(),
            ),
            (
                "constraints",
                RTG_CONSTRAINTS_ACTIONS["apply_batch"],
                batch.constraint_changes,
                RtgConstraintChangeSet(),
            ),
            (
                "graph",
                RTG_GRAPH_ACTIONS["apply_batch"],
                batch.graph_changes,
                RtgGraphChangeSet(),
            ),
            (
                "migration",
                RTG_MIGRATION_ACTIONS["apply_batch"],
                batch.migration_changes,
                RtgMigrationChangeSet(),
            ),
        )
        committed: list[str] = []
        for component, action, changes, empty in declarations:
            if changes == empty:
                continue
            try:
                await execution.call(
                    f"{prefix}-batch-{component}",
                    action,
                    {"changes": changes},
                    target=execution.address_for(self._keys[component]),
                )
                committed.append(component)
            except BaseException as error:
                if committed:
                    raise RtgControllerRecoveryIndeterminate(
                        f"{component} batch did not complete after committed owners "
                        f"{', '.join(committed)}; reconstruction is required"
                    ) from error
                if isinstance(error, asyncio.CancelledError):
                    raise
                raise RtgControllerApplyFailed(str(error)) from error

        graph_writes = (
            len(batch.graph_changes.anchor_writes)
            + len(batch.graph_changes.data_object_writes)
            + len(batch.graph_changes.link_writes)
        )
        deletes = (
            len(batch.graph_changes.delete_anchors)
            + len(batch.graph_changes.delete_data_objects)
            + len(batch.graph_changes.delete_links)
            + len(batch.schema_changes.delete_definitions)
            + len(batch.constraint_changes.delete_constraints)
            + len(batch.migration_changes.delete_migrations)
        )
        live_changes = (
            len(batch.graph_changes.set_live)
            + len(batch.schema_changes.set_live)
            + len(batch.constraint_changes.set_live)
        )
        return RtgControllerAppliedChanges(
            graph_writes,
            len(batch.schema_changes.definition_writes),
            len(batch.constraint_changes.constraint_writes),
            len(batch.migration_changes.migration_writes),
            deletes,
            live_changes,
        )

    async def _restore(
        self, kwargs: dict[str, object], execution: ComponentExecution
    ) -> RtgControllerOperationResult:
        target = cast(RtgSystemSnapshot, kwargs["snapshot"])
        try:
            await self._replace_snapshot(target, execution, prefix="restore")
            report = await self._validation_call(
                "validate_graph_state",
                {
                    "migration_ids": None,
                    "validation_options": RtgValidationOptions(finding_limit=100),
                },
                execution,
            )
            if not report.accepted:
                raise RtgControllerRecoveryIndeterminate(
                    "restored state violates controller invariants; reconstruction is required"
                )
        except asyncio.CancelledError as error:
            raise RtgControllerRecoveryIndeterminate(
                "restore deadline expired after replacement began; reconstruction is required"
            ) from error
        return RtgControllerOperationResult(status="restore_applied")

    async def _snapshot(
        self,
        execution: ComponentExecution,
        *,
        prefix: str,
    ) -> RtgSystemSnapshot:
        calls = (
            (
                "graph",
                RTG_GRAPH_ACTIONS["export_snapshot"],
                RtgGraphSnapshot,
            ),
            ("schema", RTG_SCHEMA_ACTIONS["export_snapshot"], RtgSchemaSnapshot),
            (
                "constraints",
                RTG_CONSTRAINTS_ACTIONS["export_snapshot"],
                RtgConstraintSnapshot,
            ),
            (
                "migration",
                RTG_MIGRATION_ACTIONS["export_snapshot"],
                RtgMigrationSnapshot,
            ),
        )

        async def read(name: str, action: object, value_type: object) -> object:
            try:
                value = await execution.call(
                    f"{prefix}-snapshot-{name}",
                    action,  # type: ignore[arg-type]
                    {},
                    target=execution.address_for(self._keys[name]),
                )
            except RuntimeRemoteFault as error:
                raise RtgControllerSnapshotFailed(str(error)) from error
            return decode_typed(value, value_type)

        graph, schema, constraints, migration = await asyncio.gather(
            *(read(*call) for call in calls)
        )
        return RtgSystemSnapshot(
            cast(RtgGraphSnapshot, graph),
            cast(RtgSchemaSnapshot, schema),
            cast(RtgConstraintSnapshot, constraints),
            cast(RtgMigrationSnapshot, migration),
        )

    async def _validation_call(
        self,
        action_name: str,
        extra: dict[str, object],
        execution: ComponentExecution,
    ) -> RtgValidationReport:
        try:
            value = await execution.call(
                f"validation-{action_name}",
                RTG_CHANGE_VALIDATION_ACTIONS[action_name],
                extra,
                target=execution.address_for(self._keys["validation"]),
            )
        except RuntimeRemoteFault as error:
            self._raise_remote(error, (RtgValidationInputInvalid,))
        return cast(RtgValidationReport, decode_typed(value, RtgValidationReport))

    async def _replace_snapshot(
        self,
        after: RtgSystemSnapshot,
        execution: ComponentExecution,
        *,
        prefix: str,
    ) -> None:
        changes = (
            ("graph", RTG_GRAPH_ACTIONS["replace_snapshot"], after.graph),
            ("schema", RTG_SCHEMA_ACTIONS["replace_snapshot"], after.schema),
            (
                "constraints",
                RTG_CONSTRAINTS_ACTIONS["replace_snapshot"],
                after.constraints,
            ),
            (
                "migration",
                RTG_MIGRATION_ACTIONS["replace_snapshot"],
                after.migration,
            ),
        )
        completed: list[str] = []
        try:
            for name, action, replacement in changes:
                await execution.call(
                    f"{prefix}-commit-{name}",
                    action,  # type: ignore[arg-type]
                    {"snapshot": replacement},
                    target=execution.address_for(self._keys[name]),
                )
                completed.append(name)
        except (Exception, asyncio.CancelledError) as error:
            if completed:
                raise RtgControllerRecoveryIndeterminate(
                    f"component replacement failed after {', '.join(completed)} committed; "
                    "reconstruction is required"
                ) from error
            if isinstance(error, asyncio.CancelledError):
                raise
            raise RtgControllerApplyFailed(str(error)) from error

    async def _persist_snapshot(
        self, kwargs: dict[str, object], execution: ComponentExecution
    ) -> RtgSnapshotPersistenceResult:
        snapshot = await self._snapshot(execution, prefix="persist")
        try:
            written = await execution.call(
                "persist-snapshot",
                JSON_FILE_STORAGE_ACTIONS["write"],
                {
                    "relative_path": str(kwargs["relative_path"]),
                    "json_value": encode_json(snapshot),
                },
                target=execution.address_for(self._keys["json"]),
            )
        except RuntimeRemoteFault as error:
            raise RtgControllerSnapshotFailed(str(error)) from error
        metadata = decode_typed(written, JsonDocumentMetadata)
        return RtgSnapshotPersistenceResult(
            status="snapshot_persisted",
            relative_path=metadata.relative_path,
            size_bytes=metadata.size_bytes,
            digest=hashlib.sha256(canonical_json(snapshot).encode("utf-8")).hexdigest(),
            state_counts=RtgSnapshotStateCounts(
                anchors=len(snapshot.graph.anchors),
                data_objects=len(snapshot.graph.data_objects),
                links=len(snapshot.graph.links),
                schema_definitions=len(snapshot.schema.definitions),
                constraints=len(snapshot.constraints.constraints),
                migrations=len(snapshot.migration.migrations),
            ),
        )

    async def _list_persisted(
        self, kwargs: dict[str, object], execution: ComponentExecution
    ) -> RtgPersistedSnapshotList:
        offset_value = kwargs.get("offset", 0)
        limit_value = kwargs.get("limit", 100)
        if (
            isinstance(offset_value, bool)
            or not isinstance(offset_value, int)
            or isinstance(limit_value, bool)
            or not isinstance(limit_value, int)
        ):
            raise RtgControllerSnapshotFailed("offset and limit must be integers")
        offset = offset_value
        limit = limit_value
        try:
            value = await execution.call(
                "list-snapshots",
                JSON_FILE_STORAGE_ACTIONS["list"],
                {
                    "relative_directory_path": ".",
                    "offset": offset,
                    "limit": limit,
                },
                target=execution.address_for(self._keys["json"]),
            )
            listing = cast(JsonDocumentList, decode_typed(value, JsonDocumentList))
        except RuntimeRemoteFault as error:
            raise RtgControllerSnapshotFailed(str(error)) from error
        snapshots: list[dict[str, object]] = []
        for index, metadata in enumerate(listing.documents):
            try:
                document_value = await execution.call(
                    f"inspect-snapshot-{index}",
                    JSON_FILE_STORAGE_ACTIONS["read"],
                    {"relative_path": metadata.relative_path},
                    target=execution.address_for(self._keys["json"]),
                )
                document = cast(JsonDocument, decode_typed(document_value, JsonDocument))
            except RuntimeRemoteFault:
                continue
            if _looks_like_system_snapshot(document.value):
                snapshots.append(
                    {
                        "relative_path": metadata.relative_path,
                        "size_bytes": metadata.size_bytes,
                        "modified_at": metadata.modified_at.isoformat(),
                    }
                )
        return RtgPersistedSnapshotList(
            cast(tuple, tuple(snapshots)), listing.total, listing.next_offset
        )

    async def _load_persisted(
        self, kwargs: dict[str, object], execution: ComponentExecution
    ) -> RtgPersistedSnapshotDocument:
        relative_path = str(kwargs["relative_path"])
        try:
            value = await execution.call(
                "load-snapshot",
                JSON_FILE_STORAGE_ACTIONS["read"],
                {"relative_path": relative_path},
                target=execution.address_for(self._keys["json"]),
            )
            document = cast(JsonDocument, decode_typed(value, JsonDocument))
            snapshot = cast(
                RtgSystemSnapshot,
                decode_typed(document.value, RtgSystemSnapshot),
            )
        except Exception as error:
            raise RtgControllerSnapshotFailed(str(error)) from error
        return RtgPersistedSnapshotDocument(relative_path, snapshot)

    @staticmethod
    def _raise_remote(
        error: RuntimeRemoteFault,
        allowed: tuple[type[Exception], ...],
    ) -> Never:
        name = str(error.payload.get("type", ""))
        message = str(error.payload.get("message", name or "remote component fault"))
        error_type = next((item for item in allowed if item.__name__ == name), None)
        if error_type is None:
            raise error
        raise error_type(message) from error


def _validation_options(value: object | None) -> RtgValidationOptions:
    if value is None:
        return RtgValidationOptions(finding_limit=100)
    requested_limit = getattr(value, "finding_limit", None)
    if requested_limit is not None and (requested_limit < 1 or requested_limit > 500):
        raise RtgValidationInputInvalid("finding_limit must be between 1 and 500")
    return RtgValidationOptions(
        tracks=getattr(value, "tracks", "all"),
        finding_limit=requested_limit or 100,
    )


def _looks_like_system_snapshot(value: object) -> bool:
    return isinstance(value, dict) and all(
        key in value for key in ("graph", "schema", "constraints", "migration")
    )


def _recommended_next_steps(classification: str) -> tuple[str, ...]:
    if classification == "empty":
        return (
            "Call rtg_get_usage_guide with topic='schema_staging_minimal' for payload shape.",
            "Translate the user task into schema definitions, stage them, then cut over.",
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
