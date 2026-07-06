from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from apps.rtg_knowledge_graph.mcp_codec import (
    RtgMcpInputInvalid,
    decode_change_batch,
    decode_cutover_options,
    decode_discovery_options,
    decode_graph_changes,
    decode_query_options,
    decode_query_spec,
    decode_replay_options,
    decode_restore_options,
    decode_schema_pack_options,
    decode_system_snapshot,
    decode_validation_options,
    encode_json,
)
from components.rtg.change_validation import RtgValidationError
from components.rtg.constraints import RtgConstraintError
from components.rtg.controller import (
    InProcessRtgController,
    RtgControllerError,
    RtgControllerValidationFailed,
)
from components.rtg.diagnostics import diagnostic_as_json, rtg_diagnostic
from components.rtg.graph import RtgGraphError
from components.rtg.migration import RtgMigrationError
from components.rtg.query import RtgQueryError
from components.rtg.schema import RtgSchemaError

TOOL_NAMES: tuple[str, ...] = (
    "rtg_get_system_state",
    "rtg_get_usage_guide",
    "rtg_stage_schema_migration",
    "rtg_validate_live_anchor_records",
    "rtg_apply_live_anchor_records",
    "rtg_validate_live_graph_changes",
    "rtg_apply_live_graph_changes",
    "rtg_stage_knowledge_changes",
    "rtg_apply_migration_cutover",
    "rtg_abandon_migration",
    "rtg_execute_query",
    "rtg_resolve_anchor_by_fact",
    "rtg_get_object",
    "rtg_list_migrations",
    "rtg_get_migration",
    "rtg_validate_graph",
    "rtg_discover_anchor_types",
    "rtg_get_schema_pack",
    "rtg_export_system_snapshot",
    "rtg_persist_system_snapshot",
    "rtg_list_persisted_snapshots",
    "rtg_load_persisted_snapshot",
    "rtg_replay_ledger",
    "rtg_verify_replay_from_ledger",
    "rtg_list_migration_history",
    "rtg_flush_ledger_failures",
    "rtg_restore_from_snapshot",
)

TOOL_DESCRIPTIONS: dict[str, str] = {
    "rtg_get_system_state": (
        "Read controller state for MCP-only agents. Returns state_classification "
        "(empty|schema_only|populated|has_staged_work|needs_replay), live schema summary, "
        "live/non-live counts, current migration-store status counts, persisted snapshot paths, "
        "ledger count, last ledger/transaction pointers, migration history hints, and "
        "recommended_workflows plus recommended_next_steps. Use workflow_patterns or "
        "request_patterns when entering cold."
    ),
    "rtg_get_usage_guide": (
        "Return MCP-accessible usage guidance and copy-pastable JSON examples. topic values: "
        "mcp_bootstrap_checklist, operator_card, workflow_patterns, request_patterns, "
        "schema_staging_minimal, tool_call_shapes, live_write, lookup_examples, "
        "query_examples, recovery_and_replay, migration_history, migration_abandonment. "
        "Examples are generic RTG operation examples with complete top-level tool argument "
        "envelopes; domain-specific schemas should be derived from the user's task."
    ),
    "rtg_stage_schema_migration": (
        "Ergonomic schema staging for agents. Inputs: migration_id, description, "
        "schema_definitions[{kind:anchor|data_object|link,type_key,description,payload}], "
        "optional retire_live_schema[{kind,type_key}], validation_mode. Generates candidate "
        "UUIDs, sets system.live=false, fills schema_make_live/schema_make_non_live, submits "
        "the canonical rtg_stage_knowledge_changes payload, and returns that payload. Use after "
        "schema_bootstrap or schema_evolution workflow planning; next call is usually "
        "rtg_apply_migration_cutover."
    ),
    "rtg_validate_live_anchor_records": (
        "Validate ergonomic live anchor records without mutating or ledgering. Inputs: "
        "anchor_records[{ref,type,display_name?,system?,facts:[{ref?,type,properties,system?}]}], "
        "optional link_writes, optional validation_options{tracks,finding_limit}. Compiles to "
        "canonical graph_changes and returns submitted_graph_changes plus validation result."
    ),
    "rtg_apply_live_anchor_records": (
        "Apply ergonomic live anchor records after schema exists. Inputs: "
        "anchor_records[{ref,type,display_name?,system?,facts:[{ref?,type,properties,system?}]}], "
        "optional link_writes, validation_mode(strict|skip). Compiles to canonical graph_changes "
        "and returns submitted_graph_changes plus the underlying operation result."
    ),
    "rtg_apply_live_graph_changes": (
        "Apply normal live graph CRUD only. Use this after the live schema exists. "
        "graph_changes keys: anchor_writes[{ref:{local_ref|resource_id}, type, "
        "display_name?, system?}], data_object_writes[{ref, type, properties, "
        "anchor_refs:[ref], system?}], link_writes[{ref, type, source_ref, target_ref, "
        "system?}], associate_data[{anchor_ref,data_ref}], dissociate_data, delete_anchors, "
        "delete_data_objects, delete_links, set_live[{object_ref,live}]. Link writes require "
        "existing or same-request endpoint anchors and a live link schema allowing their types. "
        "local_ref is request-local only; use resource_id values returned by earlier calls for "
        "existing objects. Strict invalid writes return validation_report findings. Rejects "
        "schema, constraint, migration, and non-live candidate work."
    ),
    "rtg_validate_live_graph_changes": (
        "Validate normal live graph CRUD without mutating or ledgering it. Inputs: "
        "graph_changes with the same shape as rtg_apply_live_graph_changes and optional "
        "validation_options{tracks,finding_limit}. Do not pass validation_options.mode; mutation "
        "tools use validation_mode. Resolves local_ref values exactly like a real write, returns "
        "generated_ids, resolved_graph_changes, and validation_report, and leaves graph state and "
        "the controller ledger unchanged. Use before risky imports, safe_update, or "
        "validation_error_recovery probes."
    ),
    "rtg_stage_knowledge_changes": (
        "Advanced normalized-batch staging for migration-scoped knowledge-engineering changes. "
        "For ordinary schema bootstrap/evolution, prefer rtg_stage_schema_migration because it "
        "generates candidate UUIDs and migration membership. knowledge_changes is a change batch "
        "with schema_changes, constraint_changes, migration_changes, and optional non-live "
        "graph_changes. Schema writes use schema_changes.definition_writes[{ref, "
        "definition:{uuid?, kind: anchor|data_object|link, type_key, description, payload, "
        "system:{live:false}}}], where anchor payload uses "
        "required_data_types/optional_data_types, data_object payload uses "
        "properties:{field:{required,value_kinds,properties?,items?}}, and link payload uses "
        "allowed_source_types/allowed_target_types. Constraint writes use "
        "constraint_changes.constraint_writes[{ref,constraint:{uuid?, kind: "
        "query_pattern|cardinality, target_type_keys, display_name, description, payload, "
        "system:{live:false}}}], where query_pattern payload uses query_spec+expectation and "
        "cardinality payload uses query_spec+counted_binding+minimum/maximum. Migration writes use "
        "migration_changes.migration_writes[{ref, "
        "migration:{migration_id, description, status:ready, schema_make_live?, "
        "schema_make_non_live?, graph_make_live?, constraint_make_live?}}]. New candidates "
        "must be referenced by a migration record in the same request. For non-live "
        "graph_changes, graph_make_live must include every candidate anchor, data object, and "
        "link UUID. Strict staging validates the projected migration cutover; use "
        "validation_mode:skip only for controlled recovery or intentionally invalid cutover tests."
    ),
    "rtg_apply_migration_cutover": (
        "Apply an explicit migration cutover. The migration record decides which staged schema, "
        "constraint, or graph candidates become live and which records retire. Use after "
        "rtg_stage_knowledge_changes returns ok:true. cutover_options keys: validation_mode "
        "(strict|skip, default strict), prune_retired (default true), failure_restore "
        "(only restore_pre_cutover_snapshot in v1). Strict cutover returns validation_report "
        "findings, restores or preserves the previous live state on blocking failures, and marks "
        "the migration failed so replay can reproduce that status."
    ),
    "rtg_abandon_migration": (
        "Abandon draft/ready/failed staged work and prune safe non-live make-live candidates. "
        "Never deletes live records or make-non-live targets. Use when exploratory schema, "
        "constraint, or non-live graph candidates should not proceed."
    ),
    "rtg_execute_query": (
        "Execute a read-only RTG query. query_spec keys: anchor_buckets[{name, "
        "anchor_type_keys}], link_requirements[{name, source_bucket, target_bucket, "
        "link_type_keys}], data_requirements[{name, anchor_bucket, data_type_key, "
        "required?, predicates:[{path:[property,...], operator, value?, values?, "
        "case_sensitive?, regex_flags?}]}], return_spec:{anchor_buckets?, link_requirements?, "
        "data_requirements?, properties:[[data_requirement_name,[property,...]]]}. Operators: "
        "exists, equals, not_equals, lt, lte, gt, gte, contains, in, substring, regex. "
        "query_options keys: live_filter(all|live|non_live), live_status_overlay, "
        "order_by[{data_requirement,path,direction:ascending|descending}]. order_by may "
        "only reference paths listed in return_spec.properties. Optional response_options "
        "supports format:full or properties_only."
    ),
    "rtg_resolve_anchor_by_fact": (
        "Resolve live anchor UUIDs through the canonical query contract. Inputs: anchor_type, "
        "data_type, property_path, value, optional case_sensitive. Compiles to rtg_execute_query "
        "and returns match_count, matches[{resource_id, properties}], submitted_query, and "
        "guidance for zero or multiple matches."
    ),
    "rtg_get_object": "Read one RTG graph object by UUID.",
    "rtg_list_migrations": "List RTG migration records, optionally filtered by status.",
    "rtg_get_migration": "Read one RTG migration record by ID.",
    "rtg_validate_graph": (
        "Validate current or migration-projected RTG state without mutation. Use "
        "rtg_validate_graph({}) as the first MCP smoke check. Pass migration_ids to validate "
        "a staged cutover projection. validation_options keys: tracks (all or list), "
        "finding_limit (positive integer)."
    ),
    "rtg_discover_anchor_types": (
        "Return live anchor type keys and descriptions for discovery. discovery_options keys: "
        "include_non_live, limit (positive integer). Use before guessing anchor_type_keys."
    ),
    "rtg_get_schema_pack": (
        "Return schema details and optional live counts for anchor types. Provide "
        "anchor_type_keys. schema_pack_options keys: live (true, false, or null), "
        "include_live_counts. Use this before writing data_object_writes or query "
        "data_requirements so required data types and property names are known."
    ),
    "rtg_export_system_snapshot": (
        "Export a coordinated JSON-safe RTG system snapshot for graph, schema, constraints, "
        "migration state, and ledger position. Pass summary:true for compact counts and "
        "ledger pointers instead of the full graph payload."
    ),
    "rtg_persist_system_snapshot": (
        "Persist a coordinated system snapshot through JSON File Storage at relative_path. "
        "Pass return_snapshot:false to omit the full snapshot payload and return compact "
        "summary metadata."
    ),
    "rtg_list_persisted_snapshots": (
        "List persisted system snapshots visible through JSON File Storage. Does not expose "
        "arbitrary filesystem access."
    ),
    "rtg_load_persisted_snapshot": (
        "Load one persisted system snapshot by relative JSON File Storage path. Use the returned "
        "snapshot with rtg_restore_from_snapshot or rtg_replay_ledger start_snapshot. Pass "
        "return_snapshot:false to return only relative_path and compact summary."
    ),
    "rtg_replay_ledger": (
        "Replay mutating controller ledger requests into an empty or snapshot-seeded controller. "
        "replay_options keys: start_snapshot, start_snapshot_path, after_ledger_position, "
        "through_ledger_position. Use after restart or restore tests to verify recovery from "
        "persisted ledger state."
    ),
    "rtg_verify_replay_from_ledger": (
        "Replay mutating controller ledger requests into isolated scratch state and restore the "
        "current state before returning. Accepts the same replay_options as rtg_replay_ledger, "
        "including start_snapshot_path. Returns pre/post summaries, count diffs, replay counts, "
        "and validation result without appending ledger entries."
    ),
    "rtg_list_migration_history": (
        "Return ledger-backed migration audit events, including staged, cutover_applied, "
        "cutover_failed, and abandoned events. Applied migrations may be absent from the live "
        "migration store but remain visible here."
    ),
    "rtg_flush_ledger_failures": "Flush queued controller ledger failures to SQL storage.",
    "rtg_restore_from_snapshot": (
        "Restore RTG state from a supplied system snapshot. restore_options keys: "
        "ledger_mode(record|skip). Use with rtg_export_system_snapshot or a persisted "
        "snapshot payload."
    ),
}


def mcp_tool_metadata() -> list[dict[str, str]]:
    return [{"name": name, "description": TOOL_DESCRIPTIONS[name]} for name in TOOL_NAMES]


class RtgMcpToolset:
    def __init__(self, controller: InProcessRtgController) -> None:
        self._controller = controller

    def rtg_get_system_state(self) -> dict[str, Any]:
        return self._response(self._controller.get_system_state)

    def rtg_get_usage_guide(self, topic: str) -> dict[str, Any]:
        return self._response(lambda: _usage_guide(topic))

    def rtg_stage_schema_migration(
        self,
        migration_id: str,
        description: str,
        schema_definitions: list[dict[str, Any]],
        retire_live_schema: list[dict[str, Any]] | None = None,
        validation_mode: str = "strict",
    ) -> dict[str, Any]:
        return self._response(
            lambda: self._stage_schema_migration(
                migration_id,
                description,
                schema_definitions,
                retire_live_schema or [],
                validation_mode,
            )
        )

    def rtg_validate_live_graph_changes(
        self,
        graph_changes: dict[str, Any],
        validation_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._response(
            lambda: self._controller.validate_live_graph_changes(
                decode_graph_changes(graph_changes),
                validation_options=decode_validation_options(validation_options),
            )
        )

    def rtg_validate_live_anchor_records(
        self,
        anchor_records: list[dict[str, Any]],
        link_writes: list[dict[str, Any]] | None = None,
        validation_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._response(
            lambda: self._validate_live_anchor_records(
                anchor_records,
                link_writes or [],
                validation_options,
            )
        )

    def rtg_apply_live_anchor_records(
        self,
        anchor_records: list[dict[str, Any]],
        link_writes: list[dict[str, Any]] | None = None,
        validation_mode: str = "strict",
    ) -> dict[str, Any]:
        return self._response(
            lambda: self._apply_live_anchor_records(
                anchor_records,
                link_writes or [],
                validation_mode,
            )
        )

    def rtg_apply_live_graph_changes(
        self,
        graph_changes: dict[str, Any],
        validation_mode: str = "strict",
    ) -> dict[str, Any]:
        return self._response(
            lambda: self._controller.apply_live_graph_changes(
                decode_graph_changes(graph_changes),
                validation_mode=validation_mode,
            )
        )

    def rtg_stage_knowledge_changes(
        self,
        knowledge_changes: dict[str, Any],
        validation_mode: str = "strict",
    ) -> dict[str, Any]:
        return self._response(
            lambda: self._controller.stage_knowledge_changes(
                decode_change_batch(knowledge_changes),
                validation_mode=validation_mode,
            )
        )

    def rtg_apply_migration_cutover(
        self,
        migration_id: str,
        cutover_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._response(
            lambda: self._controller.apply_migration_cutover(
                migration_id,
                decode_cutover_options(cutover_options),
            )
        )

    def rtg_abandon_migration(
        self,
        migration_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return self._response(lambda: self._controller.abandon_migration(migration_id, reason))

    def rtg_execute_query(
        self,
        query_spec: dict[str, Any],
        query_options: dict[str, Any] | None = None,
        response_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        def execute() -> object:
            decoded_query_spec = decode_query_spec(query_spec)
            return _shape_query_response(
                self._controller.execute_query(
                    decoded_query_spec,
                    decode_query_options(query_options),
                ),
                response_options,
                decoded_query_spec,
            )

        return self._response(execute)

    def rtg_resolve_anchor_by_fact(
        self,
        anchor_type: str,
        data_type: str,
        property_path: list[str],
        value: Any,
        case_sensitive: bool = False,
    ) -> dict[str, Any]:
        return self._response(
            lambda: self._resolve_anchor_by_fact(
                anchor_type,
                data_type,
                property_path,
                value,
                case_sensitive,
            )
        )

    def rtg_get_object(self, object_uuid: str) -> dict[str, Any]:
        return self._response(lambda: self._controller.get_object(object_uuid))

    def rtg_list_migrations(self, status: str | None = None) -> dict[str, Any]:
        return self._response(lambda: self._controller.list_migrations(status=status))

    def rtg_get_migration(self, migration_id: str) -> dict[str, Any]:
        return self._response(lambda: self._controller.get_migration(migration_id))

    def rtg_validate_graph(
        self,
        migration_ids: list[str] | None = None,
        validation_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ids = tuple(migration_ids) if migration_ids is not None else None
        return self._response(
            lambda: self._controller.validate_graph(
                migration_ids=ids,
                validation_options=decode_validation_options(validation_options),
            )
        )

    def rtg_discover_anchor_types(
        self,
        discovery_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._response(
            lambda: self._controller.discover_anchor_types(
                decode_discovery_options(discovery_options)
            )
        )

    def rtg_get_schema_pack(
        self,
        anchor_type_keys: list[str],
        schema_pack_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._response(
            lambda: self._controller.get_schema_pack(
                tuple(anchor_type_keys),
                decode_schema_pack_options(schema_pack_options),
            )
        )

    def rtg_export_system_snapshot(self, summary: bool = False) -> dict[str, Any]:
        if not summary:
            return self._response(self._controller.export_system_snapshot)
        return self._response(
            lambda: {
                "status": "snapshot_exported",
                "summary": _snapshot_summary(self._controller.export_system_snapshot()),
            }
        )

    def rtg_persist_system_snapshot(
        self,
        relative_path: str,
        return_snapshot: bool = True,
    ) -> dict[str, Any]:
        return self._response(
            lambda: _shape_persisted_snapshot_result(
                self._controller.persist_system_snapshot(relative_path),
                relative_path=relative_path,
                return_snapshot=return_snapshot,
            )
        )

    def rtg_list_persisted_snapshots(self) -> dict[str, Any]:
        return self._response(self._controller.list_persisted_snapshots)

    def rtg_load_persisted_snapshot(
        self,
        relative_path: str,
        return_snapshot: bool = True,
    ) -> dict[str, Any]:
        return self._response(
            lambda: _shape_loaded_snapshot_result(
                self._controller.load_persisted_snapshot(relative_path),
                return_snapshot=return_snapshot,
            )
        )

    def rtg_replay_ledger(self, replay_options: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._response(
            lambda: self._controller.replay_ledger(decode_replay_options(replay_options))
        )

    def rtg_verify_replay_from_ledger(
        self,
        replay_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._response(
            lambda: self._controller.verify_replay_from_ledger(
                decode_replay_options(replay_options)
            )
        )

    def rtg_list_migration_history(self) -> dict[str, Any]:
        return self._response(self._controller.list_migration_history)

    def rtg_flush_ledger_failures(self) -> dict[str, Any]:
        return self._response(self._controller.flush_ledger_failures)

    def rtg_restore_from_snapshot(
        self,
        snapshot: dict[str, Any],
        restore_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._response(
            lambda: self._controller.restore_from_snapshot(
                decode_system_snapshot(snapshot),
                decode_restore_options(restore_options),
            )
        )

    def _stage_schema_migration(
        self,
        migration_id: str,
        description: str,
        schema_definitions: list[dict[str, Any]],
        retire_live_schema: list[dict[str, Any]],
        validation_mode: str,
    ) -> dict[str, Any]:
        if not schema_definitions:
            raise RtgMcpInputInvalid("schema_definitions must contain at least one definition")
        definition_writes: list[dict[str, Any]] = []
        generated_ids: dict[str, str] = {}
        schema_make_live: list[str] = []
        for index, source_definition in enumerate(schema_definitions):
            if not isinstance(source_definition, dict):
                raise RtgMcpInputInvalid(f"schema_definitions[{index}] must be an object")
            definition = copy.deepcopy(source_definition)
            kind = _required_text(definition, "kind", f"schema_definitions[{index}].kind")
            type_key = _required_text(
                definition,
                "type_key",
                f"schema_definitions[{index}].type_key",
            )
            candidate_uuid = str(uuid4())
            definition["uuid"] = candidate_uuid
            system = definition.get("system")
            if system is None:
                system = {}
            if not isinstance(system, dict):
                raise RtgMcpInputInvalid(f"schema_definitions[{index}].system must be an object")
            definition["system"] = {**system, "live": False}
            generated_ids[f"{kind}:{type_key}"] = candidate_uuid
            schema_make_live.append(candidate_uuid)
            definition_writes.append(
                {
                    "ref": {"resource_id": candidate_uuid},
                    "definition": definition,
                }
            )

        schema_make_non_live = self._resolve_live_schema_retirements(retire_live_schema)
        knowledge_changes = {
            "schema_changes": {"definition_writes": definition_writes},
            "migration_changes": {
                "migration_writes": [
                    {
                        "ref": {"resource_id": migration_id},
                        "migration": {
                            "migration_id": migration_id,
                            "description": description,
                            "status": "ready",
                            "schema_make_live": schema_make_live,
                            "schema_make_non_live": schema_make_non_live,
                        },
                    }
                ]
            },
        }
        operation = self._controller.stage_knowledge_changes(
            decode_change_batch(knowledge_changes),
            validation_mode=validation_mode,
        )
        return {
            "generated_schema_ids": generated_ids,
            "submitted_knowledge_changes": knowledge_changes,
            "operation": operation,
        }

    def _resolve_live_schema_retirements(
        self,
        retire_live_schema: list[dict[str, Any]],
    ) -> list[str]:
        if not retire_live_schema:
            return []
        snapshot = self._controller.export_system_snapshot()
        definitions = snapshot.schema.definitions
        resolved: list[str] = []
        for index, selector in enumerate(retire_live_schema):
            if not isinstance(selector, dict):
                raise RtgMcpInputInvalid(f"retire_live_schema[{index}] must be an object")
            kind = _required_text(selector, "kind", f"retire_live_schema[{index}].kind")
            type_key = _required_text(
                selector,
                "type_key",
                f"retire_live_schema[{index}].type_key",
            )
            matches = [
                str(item["uuid"])
                for item in definitions
                if _schema_definition_matches(item, kind, type_key)
            ]
            if len(matches) != 1:
                raise RtgMcpInputInvalid(
                    f"retire_live_schema[{index}] expected exactly one live schema definition "
                    f"for kind={kind!r}, type_key={type_key!r}; found {len(matches)}"
                )
            resolved.append(matches[0])
        return resolved

    def _validate_live_anchor_records(
        self,
        anchor_records: list[dict[str, Any]],
        link_writes: list[dict[str, Any]],
        validation_options: dict[str, Any] | None,
    ) -> dict[str, Any]:
        compiled = _compile_live_anchor_records(anchor_records, link_writes)
        validation = self._controller.validate_live_graph_changes(
            decode_graph_changes(compiled["submitted_graph_changes"]),
            validation_options=decode_validation_options(validation_options),
        )
        return {
            **compiled,
            "validation": validation,
        }

    def _apply_live_anchor_records(
        self,
        anchor_records: list[dict[str, Any]],
        link_writes: list[dict[str, Any]],
        validation_mode: str,
    ) -> dict[str, Any]:
        compiled = _compile_live_anchor_records(anchor_records, link_writes)
        operation = self._controller.apply_live_graph_changes(
            decode_graph_changes(compiled["submitted_graph_changes"]),
            validation_mode=validation_mode,
        )
        return {
            **compiled,
            "operation": operation,
        }

    def _resolve_anchor_by_fact(
        self,
        anchor_type: str,
        data_type: str,
        property_path: list[str],
        value: Any,
        case_sensitive: bool,
    ) -> dict[str, Any]:
        submitted_query = _anchor_fact_lookup_query(
            anchor_type=anchor_type,
            data_type=data_type,
            property_path=property_path,
            value=value,
            case_sensitive=case_sensitive,
        )
        result = self._controller.execute_query(
            decode_query_spec(submitted_query["query_spec"]),
            decode_query_options(submitted_query["query_options"]),
        )
        encoded = encode_json(result)
        if not isinstance(encoded, dict):
            raise RtgMcpInputInvalid("query result was not an object")
        matches = _anchor_fact_lookup_matches(encoded)
        return {
            "status": "resolved",
            "match_count": len(matches),
            "matches": matches,
            "submitted_query": submitted_query,
            "diagnostics": encoded.get("diagnostics", []),
            "guidance": _anchor_resolution_guidance(len(matches)),
        }

    def _response(self, action: Callable[[], object]) -> dict[str, Any]:
        try:
            return {"ok": True, "result": encode_json(action())}
        except RtgControllerValidationFailed as error:
            payload: dict[str, Any] = {
                "ok": False,
                "error": _error_payload(error),
            }
            if error.transaction_id is not None:
                payload["transaction_id"] = str(error.transaction_id)
            if error.validation_report is not None:
                payload["validation_report"] = encode_json(error.validation_report)
            return payload
        except (
            RtgControllerError,
            RtgGraphError,
            RtgSchemaError,
            RtgConstraintError,
            RtgMigrationError,
            RtgValidationError,
            RtgQueryError,
            RtgMcpInputInvalid,
        ) as error:
            return {"ok": False, "error": _error_payload(error)}
        except (KeyError, ValueError) as error:
            return {"ok": False, "error": _error_payload(RtgMcpInputInvalid(str(error)))}
        except Exception as error:  # noqa: BLE001 - keep one error shape on the MCP boundary
            return {"ok": False, "error": _error_payload(error)}


def _error_payload(error: Exception) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": type(error).__name__, "message": str(error)}
    diagnostic = diagnostic_as_json(getattr(error, "diagnostic", None))
    if diagnostic:
        payload["diagnostic"] = diagnostic
    return payload


def _compile_live_anchor_records(
    anchor_records: list[dict[str, Any]],
    link_writes: list[dict[str, Any]],
) -> dict[str, Any]:
    anchor_writes: list[dict[str, Any]] = []
    data_object_writes: list[dict[str, Any]] = []
    generated_refs: list[dict[str, Any]] = []
    for anchor_index, source_anchor in enumerate(anchor_records):
        if not isinstance(source_anchor, dict):
            raise RtgMcpInputInvalid(f"anchor_records[{anchor_index}] must be an object")
        anchor = copy.deepcopy(source_anchor)
        _reject_anchor_record_keys(anchor, anchor_index)
        anchor_ref = _required_ref(anchor, f"anchor_records[{anchor_index}].ref")
        anchor_write: dict[str, Any] = {
            "ref": anchor_ref,
            "type": _required_text(anchor, "type", f"anchor_records[{anchor_index}].type"),
        }
        if "display_name" in anchor:
            anchor_write["display_name"] = anchor["display_name"]
        if "system" in anchor:
            anchor_write["system"] = anchor["system"]
        anchor_writes.append(anchor_write)
        for fact_index, source_fact in enumerate(
            _list_value(anchor.get("facts", []), f"anchor_records[{anchor_index}].facts")
        ):
            if not isinstance(source_fact, dict):
                raise RtgMcpInputInvalid(
                    f"anchor_records[{anchor_index}].facts[{fact_index}] must be an object"
                )
            fact = copy.deepcopy(source_fact)
            _reject_fact_record_keys(fact, anchor_index, fact_index)
            fact_ref = fact.get("ref")
            if fact_ref is None:
                fact_ref = {"local_ref": _generated_fact_ref(anchor_ref, anchor_index, fact_index)}
                generated_refs.append(
                    {
                        "anchor_index": anchor_index,
                        "fact_index": fact_index,
                        "local_ref": fact_ref["local_ref"],
                    }
                )
            else:
                fact_ref = _required_ref(
                    {"ref": fact_ref},
                    f"anchor_records[{anchor_index}].facts[{fact_index}].ref",
                )
            data_write: dict[str, Any] = {
                "ref": fact_ref,
                "type": _required_text(
                    fact,
                    "type",
                    f"anchor_records[{anchor_index}].facts[{fact_index}].type",
                ),
                "properties": _required_object(
                    fact,
                    "properties",
                    f"anchor_records[{anchor_index}].facts[{fact_index}].properties",
                ),
                "anchor_refs": [anchor_ref],
            }
            if "system" in fact:
                data_write["system"] = fact["system"]
            data_object_writes.append(data_write)
    submitted_graph_changes = {
        "anchor_writes": anchor_writes,
        "data_object_writes": data_object_writes,
        "link_writes": copy.deepcopy(link_writes),
    }
    return {
        "submitted_graph_changes": submitted_graph_changes,
        "generated_refs": {"facts": generated_refs},
    }


def _reject_anchor_record_keys(anchor: dict[str, Any], anchor_index: int) -> None:
    allowed = {"ref", "type", "display_name", "system", "facts"}
    unknown = sorted(set(anchor) - allowed)
    if unknown:
        fields = ", ".join(map(repr, unknown))
        raise RtgMcpInputInvalid(
            f"anchor_records[{anchor_index}] has unsupported field(s): {fields}"
        )


def _reject_fact_record_keys(fact: dict[str, Any], anchor_index: int, fact_index: int) -> None:
    allowed = {"ref", "type", "properties", "system"}
    unknown = sorted(set(fact) - allowed)
    if unknown:
        raise RtgMcpInputInvalid(
            "anchor_records"
            f"[{anchor_index}].facts[{fact_index}] has unsupported field(s): "
            + ", ".join(map(repr, unknown))
        )


def _required_ref(data: dict[str, Any], label: str) -> dict[str, Any]:
    try:
        value = data["ref"]
    except KeyError as error:
        raise RtgMcpInputInvalid(f"{label} is required") from error
    if not isinstance(value, dict):
        raise RtgMcpInputInvalid(
            f'{label} must be an object like {{"local_ref": "name"}} or {{"resource_id": "<uuid>"}}'
        )
    if ("local_ref" in value) == ("resource_id" in value):
        raise RtgMcpInputInvalid(f"{label} needs exactly one of local_ref or resource_id")
    return copy.deepcopy(value)


def _required_object(data: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    try:
        value = data[key]
    except KeyError as error:
        raise RtgMcpInputInvalid(f"{label} is required") from error
    if not isinstance(value, dict):
        raise RtgMcpInputInvalid(f"{label} must be an object")
    return copy.deepcopy(value)


def _list_value(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise RtgMcpInputInvalid(f"{label} must be a list")
    return value


def _generated_fact_ref(anchor_ref: dict[str, Any], anchor_index: int, fact_index: int) -> str:
    local_ref = anchor_ref.get("local_ref")
    if isinstance(local_ref, str) and local_ref:
        return f"{local_ref}-fact-{fact_index + 1}"
    return f"anchor-{anchor_index + 1}-fact-{fact_index + 1}"


def _shape_query_response(
    result: object,
    response_options: dict[str, Any] | None,
    query_spec: object | None = None,
) -> object:
    options = _response_options(response_options)
    if options["format"] == "full":
        return result
    encoded = encode_json(result)
    if not isinstance(encoded, dict):
        return encoded
    returns = encoded.get("returns", [])
    rows = []
    if isinstance(returns, list):
        for row in returns:
            if isinstance(row, dict):
                rows.append(
                    {
                        "row_index": row.get("row_index"),
                        "properties": row.get("properties", {}),
                    }
                )
    encoded_diagnostics = encoded.get("diagnostics", [])
    diagnostics = list(encoded_diagnostics) if isinstance(encoded_diagnostics, list) else []
    if query_spec is not None and not getattr(
        getattr(query_spec, "return_spec", None), "properties", ()
    ):
        diagnostics.append(
            {
                "severity": "informational",
                "code": "query.return_properties_empty",
                "message": (
                    "properties_only returns row properties only for paths listed in "
                    "query_spec.return_spec.properties."
                ),
                "suggestion": (
                    'Add return_spec.properties such as [["facts", ["title"]]] or use the full '
                    "response when you need bindings and object UUIDs."
                ),
                "affected_terms": [],
                "diagnostic": rtg_diagnostic(
                    code="query.return_properties_empty",
                    category="query_contract",
                    path="query_spec.return_spec.properties",
                    problem="No returned property paths were requested for a compact response.",
                    remedy=(
                        'Add return_spec.properties entries such as [["facts", ["title"]]], '
                        "or omit response_options.format=properties_only."
                    ),
                    minimal_example={
                        "return_spec": {"properties": [["facts", ["title"]]]},
                        "response_options": {"format": "properties_only"},
                    },
                    guide_topics=("workflow_patterns", "query_examples", "tool_call_shapes"),
                ),
            }
        )
    return {
        "status": "query_executed",
        "format": "properties_only",
        "row_count": len(rows),
        "rows": rows,
        "diagnostics": diagnostics,
    }


def _anchor_fact_lookup_query(
    *,
    anchor_type: str,
    data_type: str,
    property_path: list[str],
    value: Any,
    case_sensitive: bool,
) -> dict[str, Any]:
    path = _property_path(property_path, "property_path")
    if not isinstance(case_sensitive, bool):
        raise RtgMcpInputInvalid("case_sensitive must be a boolean")
    predicate: dict[str, Any] = {
        "path": path,
        "operator": "equals",
        "value": copy.deepcopy(value),
    }
    if case_sensitive:
        predicate["case_sensitive"] = True
    return {
        "query_spec": {
            "anchor_buckets": [
                {
                    "name": "anchor",
                    "anchor_type_keys": [
                        _non_empty_text(anchor_type, "anchor_type"),
                    ],
                }
            ],
            "data_requirements": [
                {
                    "name": "facts",
                    "anchor_bucket": "anchor",
                    "data_type_key": _non_empty_text(data_type, "data_type"),
                    "predicates": [predicate],
                }
            ],
            "return_spec": {
                "anchor_buckets": ["anchor"],
                "data_requirements": ["facts"],
                "properties": [["facts", path]],
            },
        },
        "query_options": {"live_filter": "live"},
    }


def _anchor_fact_lookup_matches(encoded_query_result: dict[str, Any]) -> list[dict[str, Any]]:
    returns = _json_list(encoded_query_result.get("returns"))
    rows_by_index = {row.get("row_index"): row for row in returns if isinstance(row, dict)}
    matches: list[dict[str, Any]] = []
    for index, binding in enumerate(_json_list(encoded_query_result.get("bindings"))):
        if not isinstance(binding, dict):
            continue
        anchors = _json_dict(binding.get("anchors"))
        resource_id = anchors.get("anchor")
        if not isinstance(resource_id, str):
            continue
        row = _json_dict(rows_by_index.get(index))
        matches.append(
            {
                "row_index": index,
                "resource_id": resource_id,
                "properties": _json_dict(row.get("properties")),
            }
        )
    return matches


def _anchor_resolution_guidance(match_count: int) -> str:
    if match_count == 0:
        return "No live anchor matched; refine the type, fact type, property_path, or value."
    if match_count == 1:
        return "Use matches[0].resource_id as the existing anchor resource_id."
    return "Multiple live anchors matched; refine the predicate before writing links."


def _property_path(value: object, label: str) -> list[str]:
    path = _list_value(value, label)
    if not path:
        raise RtgMcpInputInvalid(f"{label} must contain at least one property name")
    result: list[str] = []
    for index, item in enumerate(path):
        if not isinstance(item, str) or not item:
            raise RtgMcpInputInvalid(f"{label}[{index}] must be a non-empty string")
        result.append(item)
    return result


def _non_empty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RtgMcpInputInvalid(f"{label} must be a non-empty string")
    return value


def _response_options(value: dict[str, Any] | None) -> dict[str, str]:
    if value is None:
        return {"format": "full"}
    if not isinstance(value, dict):
        raise RtgMcpInputInvalid("response_options must be an object")
    unknown = sorted(set(value) - {"format"})
    if unknown:
        raise RtgMcpInputInvalid(
            "response_options has unsupported field(s): "
            f"{', '.join(map(repr, unknown))}. Accepted field(s): 'format'. "
            'Example: {"format": "properties_only"}. If this was nested inside query_spec, '
            "move response_options to the top-level rtg_execute_query arguments.",
            diagnostic=rtg_diagnostic(
                code="mcp.input.unsupported_field",
                category="input_shape",
                path=f"response_options.{unknown[0]}",
                problem="response_options contains unsupported fields.",
                remedy=(
                    "Use only response_options.format, and pass response_options as a top-level "
                    "rtg_execute_query argument."
                ),
                accepted_fields=("format",),
                minimal_example={"response_options": {"format": "properties_only"}},
                guide_topics=("tool_call_shapes", "query_examples"),
            ),
        )
    format_value = value.get("format", "full")
    if format_value not in {"full", "properties_only"}:
        raise RtgMcpInputInvalid("response_options.format must be full or properties_only")
    return {"format": str(format_value)}


def _shape_loaded_snapshot_result(
    document: object,
    *,
    return_snapshot: bool,
) -> dict[str, Any]:
    encoded = encode_json(document)
    if not isinstance(encoded, dict):
        return {"result": encoded}
    snapshot = encoded.get("snapshot")
    if isinstance(snapshot, dict):
        encoded["summary"] = _snapshot_summary_from_json(snapshot)
    if not return_snapshot:
        encoded.pop("snapshot", None)
    return encoded


def _shape_persisted_snapshot_result(
    result: object,
    *,
    relative_path: str,
    return_snapshot: bool,
) -> dict[str, Any]:
    encoded = encode_json(result)
    if not isinstance(encoded, dict):
        return {"result": encoded}
    snapshot = encoded.get("snapshot")
    if isinstance(snapshot, dict):
        encoded["summary"] = _snapshot_summary_from_json(snapshot)
    else:
        encoded["summary"] = {"relative_path": relative_path}
    encoded["relative_path"] = relative_path
    if not return_snapshot:
        encoded.pop("snapshot", None)
    return encoded


def _snapshot_summary(snapshot: object) -> dict[str, Any]:
    encoded = encode_json(snapshot)
    if not isinstance(encoded, dict):
        return {}
    return _snapshot_summary_from_json(encoded)


def _snapshot_summary_from_json(snapshot: dict[str, Any]) -> dict[str, Any]:
    graph = _json_dict(snapshot.get("graph"))
    schema = _json_dict(snapshot.get("schema"))
    migration = _json_dict(snapshot.get("migration"))
    constraints = _json_dict(snapshot.get("constraints"))
    return {
        "graph_counts": {
            "anchor": _type_counts(graph.get("anchors")),
            "data_object": _type_counts(graph.get("data_objects")),
            "link": _type_counts(graph.get("links")),
        },
        "schema_type_counts": _schema_type_counts(schema.get("definitions")),
        "migration_counts_by_status": _migration_counts(migration.get("migrations")),
        "constraint_count": len(_json_list(constraints.get("constraints"))),
        "last_ledger_position": snapshot.get("last_ledger_position"),
        "last_transaction_id": snapshot.get("last_transaction_id"),
        "last_transaction_timestamp": snapshot.get("last_transaction_timestamp"),
    }


def _json_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _type_counts(value: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in _json_list(value):
        if not isinstance(item, dict):
            continue
        type_key = item.get("type")
        if isinstance(type_key, str):
            counts[type_key] = counts.get(type_key, 0) + 1
    return counts


def _schema_type_counts(value: object) -> dict[str, int]:
    counts: dict[str, int] = {"anchor": 0, "data_object": 0, "link": 0}
    for item in _json_list(value):
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if isinstance(kind, str):
            counts[kind] = counts.get(kind, 0) + 1
    return counts


def _migration_counts(value: object) -> dict[str, int]:
    counts: dict[str, int] = {
        "draft": 0,
        "ready": 0,
        "failed": 0,
        "applied": 0,
        "abandoned": 0,
    }
    for item in _json_list(value):
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        if isinstance(status, str):
            counts[status] = counts.get(status, 0) + 1
    return counts


def _required_text(data: dict[str, Any], key: str, label: str) -> str:
    try:
        value = data[key]
    except KeyError as error:
        raise RtgMcpInputInvalid(f"{label} is required") from error
    if not isinstance(value, str) or not value:
        raise RtgMcpInputInvalid(f"{label} must be a non-empty string")
    return value


def _usage_guide(topic: str) -> dict[str, Any]:
    guides: dict[str, Callable[[], dict[str, Any]]] = {
        "mcp_bootstrap_checklist": _mcp_bootstrap_checklist_guide,
        "operator_card": _operator_card_guide,
        "workflow_patterns": _workflow_patterns_guide,
        "request_patterns": _request_patterns_guide,
        "schema_staging_minimal": _schema_staging_minimal_guide,
        "tool_call_shapes": _tool_call_shapes_guide,
        "live_write": _live_write_guide,
        "lookup_examples": _lookup_examples_guide,
        "query_examples": _query_examples_guide,
        "recovery_and_replay": _recovery_and_replay_guide,
        "migration_history": _migration_history_guide,
        "migration_abandonment": _migration_abandonment_guide,
    }
    try:
        return guides[topic]()
    except KeyError as error:
        raise RtgMcpInputInvalid("topic must be one of: " + ", ".join(sorted(guides))) from error


def _mcp_bootstrap_checklist_guide() -> dict[str, Any]:
    return {
        "topic": "mcp_bootstrap_checklist",
        "purpose": "Canonical MCP-only sequence for a repo-blind agent.",
        "steps": [
            {
                "tool": "rtg_validate_graph",
                "arguments": {},
                "expected": {"ok": True, "result.accepted": True},
                "why": "Connection smoke check before making stateful assumptions.",
            },
            {
                "tool": "rtg_get_system_state",
                "arguments": {},
                "why": "Classify empty/schema/populated/staged/replay state and follow hints.",
            },
            {
                "tool": "rtg_get_usage_guide",
                "arguments": {"topic": "schema_staging_minimal"},
                "when": (
                    "Use for schema payload shape. Translate the user's domain model into "
                    "schema_definitions; do not treat examples as the application schema."
                ),
            },
            {
                "tool": "rtg_stage_schema_migration",
                "argument_source": (
                    "Build migration_id, description, and schema_definitions from the user's "
                    "domain prompt. schema_staging_minimal shows only the JSON shape."
                ),
            },
            {
                "tool": "rtg_apply_migration_cutover",
                "argument_source": "Use the migration_id submitted to rtg_stage_schema_migration.",
            },
            {
                "tool": "rtg_get_usage_guide",
                "arguments": {"topic": "tool_call_shapes"},
                "when": (
                    "Use before the first large write or query. It shows complete MCP envelopes "
                    "and the ref object shape used by anchor, data, and link writes."
                ),
            },
            {
                "tool": "rtg_apply_live_anchor_records",
                "why": "Use for repeated anchor-with-required-facts ingestion.",
            },
            {
                "tool": "rtg_resolve_anchor_by_fact",
                "why": "Resolve existing anchor resource IDs before writing links.",
            },
            {
                "tool": "rtg_execute_query",
                "why": "Answer graph questions; use properties_only for compact rows.",
            },
            {
                "tool": "rtg_validate_live_anchor_records",
                "why": "Dry-run bad-write probes or risky anchor-record imports.",
            },
            {
                "tool": "rtg_persist_system_snapshot",
                "arguments": {"relative_path": "snapshots/run.json", "return_snapshot": False},
            },
            {
                "tool": "rtg_load_persisted_snapshot",
                "arguments": {"relative_path": "snapshots/run.json", "return_snapshot": False},
            },
            {
                "tool": "rtg_verify_replay_from_ledger",
                "arguments": {"replay_options": {"start_snapshot_path": "snapshots/run.json"}},
                "why": "Report replay_window, records seen, count diffs, and validation.",
            },
            {
                "tool": "rtg_list_migration_history",
                "why": "Use for ledger-backed migration audit, even when current counts are zero.",
            },
        ],
        "notes": [
            (
                "rtg_get_system_state.migration_counts_by_status reports the current migration "
                "store. Applied and abandoned migrations may be pruned from current state while "
                "remaining visible through rtg_list_migration_history."
            ),
            (
                "Dry-run validation evidence can be reported in the final brief without writing "
                "a live graph evidence record."
            ),
            (
                "Tool options are sibling tool arguments. For rtg_execute_query, pass "
                "query_spec, query_options, and response_options at the top level."
            ),
            (
                "Every ref-like field is an object, not a string: use "
                '{"local_ref": "request-local-name"} inside one request or '
                '{"resource_id": "<uuid>"} for objects returned by earlier calls.'
            ),
            (
                "Dry-run tools use validation_options; mutation tools use validation_mode."
            ),
            "Examples teach RTG payload shapes; build the actual schema from the user task.",
        ],
    }


def _operator_card_guide() -> dict[str, Any]:
    return {
        "topic": "operator_card",
        "steps": [
            "Call rtg_validate_graph({})",
            "Call rtg_get_system_state({})",
            "If empty, bootstrap schema with rtg_stage_schema_migration",
            "If schema exists, inspect it with rtg_discover_anchor_types and rtg_get_schema_pack",
            (
                "Resolve existing object UUIDs with rtg_resolve_anchor_by_fact or "
                "rtg_execute_query lookup examples before writing links"
            ),
            (
                "Dry-run risky graph_changes with rtg_validate_live_graph_changes or repeated "
                "anchor+facts payloads with rtg_validate_live_anchor_records"
            ),
            (
                "Write live data with rtg_apply_live_graph_changes, or use "
                "rtg_apply_live_anchor_records for anchor+required-facts records"
            ),
            "Query with rtg_execute_query; use response_options.format=properties_only for briefs",
            "Persist and load snapshots with compact return options for recovery checks",
            "Use rtg_list_migration_history for ledger-backed migration audit",
        ],
        "validation_options": {
            "valid_keys": ["tracks", "finding_limit"],
            "note": (
                "Dry-run validation tools do not accept validation_options.mode. Mutation tools "
                "use validation_mode instead."
            ),
        },
    }


def _workflow_patterns_guide() -> dict[str, Any]:
    return {
        "topic": "workflow_patterns",
        "purpose": "Generic RTG operating workflows for cold MCP agents.",
        "workflows": [
            _workflow_pattern(
                "connection_state_check",
                "Use first, or whenever the current RTG state is unknown.",
                ("rtg_validate_graph", "rtg_get_system_state"),
                ("rtg_validate_graph", "rtg_get_system_state"),
                "Do not assume the app is empty or populated before reading state.",
                "State response includes state_classification and recommended_workflows.",
                ("Smoke check fails", "State says needs_replay"),
            ),
            _workflow_pattern(
                "schema_bootstrap",
                "Use when the app is empty and the user wants a new durable model.",
                (
                    "rtg_get_usage_guide(schema_staging_minimal)",
                    "rtg_stage_schema_migration",
                    "rtg_apply_migration_cutover",
                    "rtg_validate_graph",
                ),
                ("rtg_stage_schema_migration", "rtg_apply_migration_cutover"),
                "Do not use beta-specific schemas or store schema as live graph facts.",
                "Live schema exists and validation is accepted.",
                ("unknown type", "migration cutover validation failure"),
            ),
            _workflow_pattern(
                "schema_discovery",
                "Use before writing data into an existing schema.",
                ("rtg_discover_anchor_types", "rtg_get_schema_pack"),
                ("rtg_discover_anchor_types", "rtg_get_schema_pack"),
                "Do not invent type keys or required fields.",
                "Schema pack identifies allowed anchor, data, and link types.",
                ("unknown type", "missing required associated data"),
            ),
            _workflow_pattern(
                "data_ingest",
                "Use when schema exists and the user provides facts to remember.",
                (
                    "rtg_validate_live_anchor_records",
                    "rtg_apply_live_anchor_records",
                    "rtg_validate_graph",
                ),
                ("rtg_apply_live_anchor_records", "rtg_apply_live_graph_changes"),
                "Do not write schema, constraints, or migrations through live graph tools.",
                "Graph counts increase and validation is accepted.",
                ("missing required property", "property kind mismatch"),
            ),
            _workflow_pattern(
                "query_answer",
                "Use when the user asks a question about live graph content.",
                (
                    "rtg_get_usage_guide(query_examples)",
                    "rtg_execute_query",
                ),
                ("rtg_execute_query",),
                "Do not answer by manually scanning every object when a query can express it.",
                "Query returns bindings or compact properties for the requested answer.",
                ("unknown bucket", "properties_only has no returned properties"),
            ),
            _workflow_pattern(
                "safe_update",
                "Use when adding or changing graph data could fail validation.",
                (
                    "rtg_validate_live_graph_changes",
                    "rtg_apply_live_graph_changes",
                    "rtg_validate_graph",
                ),
                ("rtg_validate_live_graph_changes", "rtg_apply_live_graph_changes"),
                "Do not commit recovery probes or risky imports before a dry-run when avoidable.",
                "Dry-run returns mutation_state not_mutated, then apply succeeds.",
                ("validation findings", "unresolved references"),
            ),
            _workflow_pattern(
                "link_writing",
                "Use when connecting existing anchors with typed links.",
                (
                    "rtg_resolve_anchor_by_fact",
                    "rtg_validate_live_graph_changes",
                    "rtg_apply_live_graph_changes",
                ),
                ("rtg_resolve_anchor_by_fact", "rtg_execute_query", "rtg_apply_live_graph_changes"),
                "Do not guess UUIDs or reuse local_ref values from earlier requests.",
                "Link endpoints resolve and the link schema allows the endpoint types.",
                ("reference_missing", "link endpoint type invalid"),
            ),
            _workflow_pattern(
                "validation_error_recovery",
                "Use when a write or dry-run returns validation findings.",
                (
                    "inspect validation_report.findings",
                    "inspect error.diagnostic when present",
                    "repair smallest payload issue",
                    "retry dry-run or strict mutation",
                ),
                ("rtg_validate_live_graph_changes", "rtg_validate_graph"),
                "Do not weaken schema or constraints just to make bad data pass.",
                "Corrected payload validates without adding throwaway graph content.",
                ("missing required data", "kind mismatch", "invalid link endpoint"),
            ),
            _workflow_pattern(
                "schema_evolution",
                "Use when new facts do not fit the current live schema.",
                (
                    "rtg_stage_schema_migration",
                    "rtg_apply_migration_cutover",
                    "rtg_validate_graph",
                    "rtg_list_migration_history",
                ),
                ("rtg_stage_schema_migration", "rtg_apply_migration_cutover"),
                "Do not mutate live schema directly; evolve through staged candidates.",
                "Cutover applies or fails while preserving live state.",
                ("failed cutover", "unbackfilled required property"),
            ),
            _workflow_pattern(
                "snapshot_replay_check",
                "Use to prove durability or prepare recovery evidence.",
                (
                    "rtg_persist_system_snapshot",
                    "rtg_list_persisted_snapshots",
                    "rtg_load_persisted_snapshot",
                    "rtg_verify_replay_from_ledger",
                ),
                (
                    "rtg_persist_system_snapshot",
                    "rtg_load_persisted_snapshot",
                    "rtg_verify_replay_from_ledger",
                ),
                "Do not require filesystem reads for MCP-only snapshot readback.",
                "Snapshot loads through MCP and replay verification validates.",
                ("snapshot path not found", "replay starts after snapshot ledger position"),
            ),
            _workflow_pattern(
                "staged_work_review",
                "Use when system state reports staged work.",
                ("rtg_list_migrations", "rtg_get_migration", "rtg_list_migration_history"),
                ("rtg_list_migrations", "rtg_get_migration"),
                "Do not assume staged candidates are live.",
                "The intended migration or failed experiment is identified.",
                ("current migration counts differ from migration history",),
            ),
            _workflow_pattern(
                "cutover_or_abandon",
                "Use after staged work is identified.",
                ("rtg_apply_migration_cutover", "rtg_abandon_migration", "rtg_validate_graph"),
                ("rtg_apply_migration_cutover", "rtg_abandon_migration"),
                "Do not leave accidental failed/draft work active when it should be retired.",
                "Intended work is live, or accidental work is abandoned and pruned safely.",
                ("failed cutover", "shared candidate not pruned"),
            ),
            _workflow_pattern(
                "replay_recovery",
                "Use when ledger records exist but in-memory state is empty.",
                ("rtg_replay_ledger", "rtg_validate_graph", "rtg_get_system_state"),
                ("rtg_replay_ledger", "rtg_verify_replay_from_ledger"),
                "Do not replay into active non-empty state without a start snapshot.",
                "Replay reconstructs state and validation is accepted.",
                ("replay non-empty state", "ambiguous replay start"),
            ),
        ],
    }


def _request_patterns_guide() -> dict[str, Any]:
    return {
        "topic": "request_patterns",
        "purpose": "Map ordinary user requests to generic RTG workflow IDs.",
        "patterns": [
            _request_pattern(
                "remember/model this domain",
                ("connection_state_check", "schema_bootstrap", "data_ingest", "query_answer"),
                "Use when the user describes new durable concepts and facts.",
            ),
            _request_pattern(
                "add these facts",
                ("connection_state_check", "schema_discovery", "data_ingest"),
                "Use when the schema likely already exists and the user supplies new records.",
            ),
            _request_pattern(
                "answer this question",
                ("connection_state_check", "query_answer"),
                "Use when the user asks for a graph-derived answer or summary.",
            ),
            _request_pattern(
                "connect these things",
                ("schema_discovery", "link_writing", "safe_update"),
                "Use when the user asks to relate existing records.",
            ),
            _request_pattern(
                "this new data does not fit",
                ("schema_discovery", "schema_evolution", "validation_error_recovery"),
                "Use when required facts or relationships are missing from the current schema.",
            ),
            _request_pattern(
                "check/recover durability",
                ("snapshot_replay_check", "replay_recovery"),
                "Use when the user asks for snapshot, restore, replay, or audit confidence.",
            ),
            _request_pattern(
                "clean up failed experiments",
                ("staged_work_review", "cutover_or_abandon"),
                "Use when staged migrations or failed candidates should be inspected or retired.",
            ),
        ],
    }


def _workflow_pattern(
    workflow_id: str,
    when_to_use: str,
    sequence: tuple[str, ...],
    preferred_tools: tuple[str, ...],
    avoid: str,
    success_check: str,
    common_failures: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "workflow_id": workflow_id,
        "when_to_use": when_to_use,
        "sequence": list(sequence),
        "preferred_tools": list(preferred_tools),
        "avoid": avoid,
        "success_check": success_check,
        "common_failures": list(common_failures),
    }


def _request_pattern(
    user_request: str,
    workflow_ids: tuple[str, ...],
    when_to_use: str,
) -> dict[str, Any]:
    return {
        "user_request": user_request,
        "workflow_ids": list(workflow_ids),
        "when_to_use": when_to_use,
    }


def _schema_staging_minimal_guide() -> dict[str, Any]:
    return {
        "topic": "schema_staging_minimal",
        "notes": [
            "Schema payload references use type keys, such as ItemFacts.",
            "Migration membership uses candidate UUIDs; rtg_stage_schema_migration generates them.",
        ],
        "tool": "rtg_stage_schema_migration",
        "arguments": {
            "migration_id": "minimal-item-schema",
            "description": "Introduce Item anchors, ItemFacts data, and collection links.",
            "schema_definitions": [
                {
                    "kind": "data_object",
                    "type_key": "ItemFacts",
                    "description": "Structured facts for an item.",
                    "payload": {
                        "properties": {
                            "title": {"required": True, "value_kinds": ["string"]},
                            "category": {"required": False, "value_kinds": ["string"]},
                            "status": {"required": True, "value_kinds": ["string"]},
                        }
                    },
                },
                {
                    "kind": "anchor",
                    "type_key": "Item",
                    "description": "A durable item.",
                    "payload": {"required_data_types": ["ItemFacts"]},
                },
                {
                    "kind": "data_object",
                    "type_key": "CollectionFacts",
                    "description": "Structured facts for a collection.",
                    "payload": {
                        "properties": {
                            "title": {"required": True, "value_kinds": ["string"]},
                            "status": {"required": True, "value_kinds": ["string"]},
                        }
                    },
                },
                {
                    "kind": "anchor",
                    "type_key": "Collection",
                    "description": "A durable grouping of items.",
                    "payload": {"required_data_types": ["CollectionFacts"]},
                },
                {
                    "kind": "link",
                    "type_key": "contains",
                    "description": "Items can belong to collections.",
                    "payload": {
                        "allowed_source_types": ["Item"],
                        "allowed_target_types": ["Collection"],
                    },
                },
                {
                    "kind": "link",
                    "type_key": "related_to",
                    "description": "Items can be related to other items.",
                    "payload": {
                        "allowed_source_types": ["Item"],
                        "allowed_target_types": ["Item"],
                    },
                },
            ],
        },
    }


def _tool_call_shapes_guide() -> dict[str, Any]:
    return {
        "topic": "tool_call_shapes",
        "notes": [
            (
                "These are complete MCP tool argument envelopes. Do not nest sibling arguments "
                "inside query_spec or graph_changes."
            ),
            (
                "Every ref-like field is a JSON object, never a plain string. Use "
                '{"local_ref": "request-local-name"} inside one request or '
                '{"resource_id": "<uuid>"} for objects returned by earlier calls.'
            ),
            (
                "Dry-run tools use validation_options. Mutation tools use validation_mode."
            ),
        ],
        "rtg_stage_schema_migration": {
            "tool": "rtg_stage_schema_migration",
            "arguments": {
                "migration_id": "minimal-item-schema",
                "description": "Introduce a minimal item schema.",
                "schema_definitions": [
                    {
                        "kind": "data_object",
                        "type_key": "ItemFacts",
                        "description": "Structured facts for an item.",
                        "payload": {
                            "properties": {
                                "title": {"required": True, "value_kinds": ["string"]},
                                "status": {"required": True, "value_kinds": ["string"]},
                            }
                        },
                    },
                    {
                        "kind": "anchor",
                        "type_key": "Item",
                        "description": "A durable item.",
                        "payload": {"required_data_types": ["ItemFacts"]},
                    },
                    {
                        "kind": "link",
                        "type_key": "related_to",
                        "description": "Items can be related to other items.",
                        "payload": {
                            "allowed_source_types": ["Item"],
                            "allowed_target_types": ["Item"],
                        },
                    },
                ],
                "validation_mode": "strict",
            },
        },
        "rtg_validate_live_anchor_records": {
            "tool": "rtg_validate_live_anchor_records",
            "arguments": {
                "anchor_records": [
                    {
                        "ref": {"local_ref": "item-alpha"},
                        "type": "Item",
                        "display_name": "Item alpha",
                        "facts": [
                            {
                                "type": "ItemFacts",
                                "properties": {"title": "Item alpha", "status": "active"},
                            }
                        ],
                    }
                ],
                "link_writes": [],
                "validation_options": {"tracks": "all", "finding_limit": 20},
            },
        },
        "rtg_apply_live_anchor_records": {
            "tool": "rtg_apply_live_anchor_records",
            "arguments": {
                "anchor_records": [
                    {
                        "ref": {"local_ref": "item-alpha"},
                        "type": "Item",
                        "display_name": "Item alpha",
                        "facts": [
                            {
                                "type": "ItemFacts",
                                "properties": {"title": "Item alpha", "status": "active"},
                            }
                        ],
                    },
                    {
                        "ref": {"local_ref": "item-beta"},
                        "type": "Item",
                        "display_name": "Item beta",
                        "facts": [
                            {
                                "type": "ItemFacts",
                                "properties": {"title": "Item beta", "status": "active"},
                            }
                        ],
                    },
                ],
                "link_writes": [
                    {
                        "ref": {"local_ref": "item-alpha-related-to-item-beta"},
                        "type": "related_to",
                        "source_ref": {"local_ref": "item-alpha"},
                        "target_ref": {"local_ref": "item-beta"},
                    }
                ],
                "validation_mode": "strict",
            },
        },
        "rtg_validate_live_graph_changes": {
            "tool": "rtg_validate_live_graph_changes",
            "arguments": {
                "graph_changes": {
                    "anchor_writes": [
                        {
                            "ref": {"local_ref": "item-alpha"},
                            "type": "Item",
                            "display_name": "Item alpha",
                        }
                    ],
                    "data_object_writes": [
                        {
                            "ref": {"local_ref": "item-alpha-facts"},
                            "type": "ItemFacts",
                            "properties": {"title": "Item alpha", "status": "active"},
                            "anchor_refs": [{"local_ref": "item-alpha"}],
                        }
                    ],
                },
                "validation_options": {"tracks": "all", "finding_limit": 20},
            },
        },
        "rtg_execute_query": {
            "tool": "rtg_execute_query",
            "arguments": {
                "query_spec": {
                    "anchor_buckets": [{"name": "item", "anchor_type_keys": ["Item"]}],
                    "data_requirements": [
                        {
                            "name": "facts",
                            "anchor_bucket": "item",
                            "data_type_key": "ItemFacts",
                            "predicates": [
                                {"path": ["status"], "operator": "equals", "value": "active"}
                            ],
                        }
                    ],
                    "return_spec": {
                        "anchor_buckets": ["item"],
                        "data_requirements": ["facts"],
                        "properties": [["facts", ["title"]]],
                    },
                },
                "query_options": {"live_filter": "live"},
                "response_options": {"format": "properties_only"},
            },
        },
        "rtg_persist_system_snapshot": {
            "tool": "rtg_persist_system_snapshot",
            "arguments": {"relative_path": "snapshots/run.json", "return_snapshot": False},
        },
        "rtg_load_persisted_snapshot": {
            "tool": "rtg_load_persisted_snapshot",
            "arguments": {"relative_path": "snapshots/run.json", "return_snapshot": False},
        },
        "rtg_verify_replay_from_ledger": {
            "tool": "rtg_verify_replay_from_ledger",
            "arguments": {"replay_options": {"start_snapshot_path": "snapshots/run.json"}},
        },
    }


def _live_write_guide() -> dict[str, Any]:
    return {
        "topic": "live_write",
        "notes": [
            (
                "For repeated anchor plus required-facts ingestion, prefer the anchor-record "
                "facade and keep rtg_apply_live_graph_changes for low-level CRUD."
            ),
            (
                "Dry-run validation tools accept validation_options.tracks and "
                "validation_options.finding_limit. Do not pass validation_options.mode."
            ),
        ],
        "anchor_record_tool": "rtg_apply_live_anchor_records",
        "anchor_record_arguments": {
            "anchor_records": [
                {
                    "ref": {"local_ref": "item-alpha"},
                    "type": "Item",
                    "display_name": "Item alpha",
                    "facts": [
                        {
                            "type": "ItemFacts",
                            "properties": {
                                "title": "Item alpha",
                                "category": "example",
                                "status": "active",
                            },
                        }
                    ],
                }
            ],
            "validation_mode": "strict",
        },
        "tool": "rtg_apply_live_graph_changes",
        "arguments": {
            "graph_changes": {
                "anchor_writes": [
                    {
                        "ref": {"local_ref": "item-alpha"},
                        "type": "Item",
                        "display_name": "Item alpha",
                    }
                ],
                "data_object_writes": [
                    {
                        "ref": {"local_ref": "item-alpha-facts"},
                        "type": "ItemFacts",
                        "properties": {
                            "title": "Item alpha",
                            "category": "example",
                            "status": "active",
                        },
                        "anchor_refs": [{"local_ref": "item-alpha"}],
                    }
                ],
            },
            "validation_mode": "strict",
        },
    }


def _lookup_query(
    anchor_type: str, data_type: str, property_name: str, value: str
) -> dict[str, Any]:
    return {
        "tool": "rtg_execute_query",
        "arguments": {
            "query_spec": {
                "anchor_buckets": [{"name": "anchor", "anchor_type_keys": [anchor_type]}],
                "data_requirements": [
                    {
                        "name": "facts",
                        "anchor_bucket": "anchor",
                        "data_type_key": data_type,
                        "predicates": [
                            {"path": [property_name], "operator": "equals", "value": value}
                        ],
                    }
                ],
                "return_spec": {
                    "anchor_buckets": ["anchor"],
                    "data_requirements": ["facts"],
                    "properties": [["facts", [property_name]]],
                },
            },
            "query_options": {"live_filter": "live"},
        },
    }


def _lookup_examples_guide() -> dict[str, Any]:
    return {
        "topic": "lookup_examples",
        "notes": [
            "Prefer rtg_resolve_anchor_by_fact for common exact fact lookups.",
            "Use these queries when you need the full canonical query payload.",
            (
                "Use result.bindings[0].anchors.anchor as the resource_id when exactly one row "
                "matches."
            ),
            "Do not guess UUIDs; if a lookup returns zero or multiple rows, refine the predicate.",
        ],
        "resolve_anchor_by_fact_example": {
            "tool": "rtg_resolve_anchor_by_fact",
            "arguments": {
                "anchor_type": "Item",
                "data_type": "ItemFacts",
                "property_path": ["title"],
                "value": "Item alpha",
            },
        },
        "item_by_title": _lookup_query(
            "Item",
            "ItemFacts",
            "title",
            "Item alpha",
        ),
        "collection_by_title": _lookup_query(
            "Collection",
            "CollectionFacts",
            "title",
            "Example collection",
        ),
    }


def _query_examples_guide() -> dict[str, Any]:
    return {
        "topic": "query_examples",
        "active_items": {
            "tool": "rtg_execute_query",
            "arguments": {
                "query_spec": {
                    "anchor_buckets": [{"name": "item", "anchor_type_keys": ["Item"]}],
                    "data_requirements": [
                        {
                            "name": "facts",
                            "anchor_bucket": "item",
                            "data_type_key": "ItemFacts",
                            "predicates": [
                                {"path": ["status"], "operator": "equals", "value": "active"}
                            ],
                        }
                    ],
                    "return_spec": {
                        "anchor_buckets": ["item"],
                        "data_requirements": ["facts"],
                        "properties": [["facts", ["title"]]],
                    },
                },
                "query_options": {"live_filter": "live"},
                "response_options": {"format": "properties_only"},
            },
        },
        "counting_guidance": {
            "properties_only": "Use result.row_count for compact query responses.",
            "full_response": "Use len(result.bindings) for full query responses.",
            "note": (
                "Expected counts should come from the user's task or evaluator, not from "
                "generic usage examples."
            ),
        },
        "relationship_query_guidance": {
            "belongs_to": "Bind source and target anchor buckets, then require a belongs_to link.",
            "supports": (
                "Bind supporting objects and supported objects, then require a supports link. "
                "Use optional data requirements when multiple supporter anchor types may appear."
            ),
            "owns": (
                "Bind owner and owned object buckets, then require an owns link."
            ),
            "related_to": "Bind two item buckets, then require a related_to link.",
        },
        "ordered_active_items": {
            "tool": "rtg_execute_query",
            "arguments": {
                "query_spec": {
                    "anchor_buckets": [{"name": "item", "anchor_type_keys": ["Item"]}],
                    "data_requirements": [
                        {
                            "name": "facts",
                            "anchor_bucket": "item",
                            "data_type_key": "ItemFacts",
                            "predicates": [
                                {"path": ["status"], "operator": "equals", "value": "active"}
                            ],
                        }
                    ],
                    "return_spec": {
                        "anchor_buckets": ["item"],
                        "data_requirements": ["facts"],
                        "properties": [
                            ["facts", ["title"]],
                            ["facts", ["rank"]],
                        ],
                    },
                },
                "query_options": {
                    "live_filter": "live",
                    "order_by": [
                        {
                            "data_requirement": "facts",
                            "path": ["rank"],
                            "direction": "ascending",
                        }
                    ],
                },
                "response_options": {"format": "properties_only"},
            },
            "note": (
                "Count rows with row_count when using properties_only, or len(result.bindings) "
                "when using the full response."
            ),
        },
        "items_by_category": {
            "note": "Change the category predicate to match your schema.",
            "tool": "rtg_execute_query",
            "arguments": {
                "query_spec": {
                    "anchor_buckets": [{"name": "item", "anchor_type_keys": ["Item"]}],
                    "data_requirements": [
                        {
                            "name": "facts",
                            "anchor_bucket": "item",
                            "data_type_key": "ItemFacts",
                            "predicates": [
                                {"path": ["status"], "operator": "equals", "value": "active"},
                                {
                                    "path": ["category"],
                                    "operator": "equals",
                                    "value": "example",
                                },
                            ],
                        }
                    ],
                    "return_spec": {
                        "anchor_buckets": ["item"],
                        "data_requirements": ["facts"],
                        "properties": [
                            ["facts", ["title"]],
                            ["facts", ["category"]],
                            ["facts", ["status"]],
                        ],
                    },
                },
                "query_options": {
                    "live_filter": "live",
                },
                "response_options": {"format": "properties_only"},
            },
        },
        "collections_by_title": {
            "tool": "rtg_execute_query",
            "arguments": {
                "query_spec": {
                    "anchor_buckets": [
                        {"name": "collection", "anchor_type_keys": ["Collection"]}
                    ],
                    "data_requirements": [
                        {
                            "name": "facts",
                            "anchor_bucket": "collection",
                            "data_type_key": "CollectionFacts",
                            "predicates": [
                                {"path": ["status"], "operator": "equals", "value": "active"}
                            ],
                        }
                    ],
                    "return_spec": {
                        "anchor_buckets": ["collection"],
                        "data_requirements": ["facts"],
                        "properties": [
                            ["facts", ["title"]],
                            ["facts", ["status"]],
                        ],
                    },
                },
                "query_options": {
                    "live_filter": "live",
                    "order_by": [
                        {
                            "data_requirement": "facts",
                            "path": ["title"],
                            "direction": "ascending",
                        }
                    ],
                },
                "response_options": {"format": "properties_only"},
            },
        },
        "related_items": {
            "tool": "rtg_execute_query",
            "arguments": {
                "query_spec": {
                    "anchor_buckets": [
                        {"name": "source", "anchor_type_keys": ["Item"]},
                        {"name": "target", "anchor_type_keys": ["Item"]},
                    ],
                    "link_requirements": [
                        {
                            "name": "relationship",
                            "source_bucket": "source",
                            "target_bucket": "target",
                            "link_type_keys": ["related_to"],
                        }
                    ],
                    "data_requirements": [
                        {
                            "name": "source_facts",
                            "anchor_bucket": "source",
                            "data_type_key": "ItemFacts",
                        },
                        {
                            "name": "target_facts",
                            "anchor_bucket": "target",
                            "data_type_key": "ItemFacts",
                        },
                    ],
                    "return_spec": {
                        "anchor_buckets": ["source", "target"],
                        "link_requirements": ["relationship"],
                        "properties": [
                            ["source_facts", ["title"]],
                            ["target_facts", ["title"]],
                        ],
                    },
                },
                "query_options": {"live_filter": "live"},
                "response_options": {"format": "properties_only"},
            },
        },
        "items_in_collections": {
            "note": (
                "Use a link requirement plus data requirements on both endpoint buckets to "
                "answer relationship questions."
            ),
            "tool": "rtg_execute_query",
            "arguments": {
                "query_spec": {
                    "anchor_buckets": [
                        {"name": "item", "anchor_type_keys": ["Item"]},
                        {"name": "collection", "anchor_type_keys": ["Collection"]},
                    ],
                    "link_requirements": [
                        {
                            "name": "membership",
                            "source_bucket": "item",
                            "target_bucket": "collection",
                            "link_type_keys": ["contains"],
                        }
                    ],
                    "data_requirements": [
                        {
                            "name": "item_facts",
                            "anchor_bucket": "item",
                            "data_type_key": "ItemFacts",
                        },
                        {
                            "name": "collection_facts",
                            "anchor_bucket": "collection",
                            "data_type_key": "CollectionFacts",
                        },
                    ],
                    "return_spec": {
                        "anchor_buckets": ["item", "collection"],
                        "data_requirements": [
                            "item_facts",
                            "collection_facts",
                        ],
                        "properties": [
                            ["item_facts", ["title"]],
                            ["collection_facts", ["title"]],
                        ],
                    },
                },
                "query_options": {"live_filter": "live"},
                "response_options": {"format": "properties_only"},
            },
        },
    }


def _recovery_and_replay_guide() -> dict[str, Any]:
    return {
        "topic": "recovery_and_replay",
        "replay_from_empty": {
            "tool": "rtg_replay_ledger",
            "arguments": {"replay_options": {}},
        },
        "steps": [
            {
                "tool": "rtg_persist_system_snapshot",
                "arguments": {
                    "relative_path": "snapshots/run.json",
                    "return_snapshot": False,
                },
            },
            {"tool": "rtg_list_persisted_snapshots", "arguments": {}},
            {
                "tool": "rtg_load_persisted_snapshot",
                "arguments": {"relative_path": "snapshots/run.json", "return_snapshot": False},
            },
            {
                "tool": "rtg_replay_ledger",
                "argument_source": {
                    "replay_options.start_snapshot_path": "Use snapshots/run.json."
                },
            },
            {
                "tool": "rtg_verify_replay_from_ledger",
                "arguments": {"replay_options": {"start_snapshot_path": "snapshots/run.json"}},
            },
        ],
        "notes": [
            (
                "Replay results include replay_window metadata. With start_snapshot_path, replay "
                "starts after the snapshot ledger position, so a snapshot taken at the end of a "
                "run may replay zero mutating requests."
            ),
            (
                "Dry-run validation evidence can be reported in the final brief without writing "
                "a live graph evidence record. Only create durable graph evidence when it is "
                "explicitly desired."
            ),
        ],
        "controlled_failed_migration_example": {
            "stage": {
                "tool": "rtg_stage_schema_migration",
                "arguments": {
                    "migration_id": "invalid-itemfacts-owner-required",
                    "description": (
                        "Controlled failure: require ItemFacts.owner without backfilling "
                        "existing ItemFacts."
                    ),
                    "schema_definitions": [
                        {
                            "kind": "data_object",
                            "type_key": "ItemFacts",
                            "description": "Item facts with an explicit owner.",
                            "payload": {
                                "properties": {
                                    "title": {"required": True, "value_kinds": ["string"]},
                                    "category": {"required": True, "value_kinds": ["string"]},
                                    "status": {"required": True, "value_kinds": ["string"]},
                                    "owner": {"required": True, "value_kinds": ["string"]},
                                }
                            },
                        }
                    ],
                    "retire_live_schema": [{"kind": "data_object", "type_key": "ItemFacts"}],
                    "validation_mode": "skip",
                },
            },
            "strict_cutover": {
                "tool": "rtg_apply_migration_cutover",
                "arguments": {"migration_id": "invalid-itemfacts-owner-required"},
                "expected": (
                    "ok:false with missing ItemFacts.owner findings; live schema preserved."
                ),
            },
            "audit_and_cleanup": [
                {"tool": "rtg_list_migration_history", "arguments": {}},
                {
                    "tool": "rtg_abandon_migration",
                    "arguments": {
                        "migration_id": "invalid-itemfacts-owner-required",
                        "reason": "Controlled failed migration exercise complete.",
                    },
                },
            ],
        },
    }


def _migration_history_guide() -> dict[str, Any]:
    return {
        "topic": "migration_history",
        "tool": "rtg_list_migration_history",
        "notes": [
            "Use this for durable migration audit after applied migrations are pruned from "
            "the live migration store.",
            "Expected event_type values include staged, cutover_applied, cutover_failed, and "
            "abandoned.",
        ],
        "arguments": {},
    }


def _migration_abandonment_guide() -> dict[str, Any]:
    return {
        "topic": "migration_abandonment",
        "tool": "rtg_abandon_migration",
        "arguments": {
            "migration_id": "experimental-schema-change",
            "reason": "Exploratory schema candidate should not proceed.",
        },
        "notes": [
            "Only draft, ready, and failed migrations can be abandoned.",
            (
                "The controller prunes non-live make-live candidates only when no other "
                "migration references them."
            ),
        ],
    }


def _schema_definition_matches(value: dict[str, Any], kind: str, type_key: str) -> bool:
    system = value.get("system")
    return (
        value.get("kind") == kind
        and value.get("type_key") == type_key
        and isinstance(system, dict)
        and system.get("live", True) is True
    )
