from __future__ import annotations

import copy
from typing import Any, cast
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
)
from apps.rtg_knowledge_graph.mcp_toolset import (
    TOOL_NAMES,
    VellisRequestInvalid,
    _anchor_fact_lookup_matches,
    _anchor_fact_lookup_query,
    _anchor_resolution_guidance,
    _compile_live_anchor_records,
    _mutation_response_format,
    _required_text,
    _shape_loaded_snapshot_result,
    _shape_persisted_snapshot_result,
    _shape_query_response,
    _snapshot_summary,
    _usage_guide,
)
from apps.rtg_knowledge_graph.runtime_binding import create_vellis_facade_adapter
from apps.rtg_knowledge_graph.runtime_services import VellisRuntimeServices
from apps.rtg_knowledge_graph.starter_schema import (
    STARTER_INSTALLER_ACTIONS,
    StarterSchemaStatus,
)
from components.rtg.controller import RTG_CONTROLLER_ACTIONS
from components.rtg.query import RtgQueryResult
from components.runtime.component_adapter import (
    ComponentAdapter,
    ComponentExecution,
    RuntimeRemoteFault,
    decode_typed,
    encode_json,
)
from components.runtime.message_runtime import JsonObject, JsonValue, RuntimeTraceDisposition


class VellisFacadeComponent:
    """Vellis request compilation and response shaping as ordinary message handlers."""

    def __init__(
        self,
        runtime_services: VellisRuntimeServices,
        *,
        controller_key: str = "vellis.controller.primary",
        starter_schema_key: str = "vellis.starter_ontology.installer",
    ) -> None:
        self._runtime_services = runtime_services
        self._controller_key = controller_key
        self._starter_schema_key = starter_schema_key

    def create_adapter(self) -> ComponentAdapter:
        return create_vellis_facade_adapter({name: self._handler(name) for name in TOOL_NAMES})

    def _handler(self, name: str):
        async def handle(arguments: JsonObject, execution: ComponentExecution) -> None:
            try:
                result = await self._execute(name, arguments, execution)
            except RuntimeRemoteFault as error:
                await execution.forward_fault(
                    error.payload,
                    disposition=_remote_fault_disposition(name, error.payload),
                )
                return
            except RtgMcpInputInvalid as error:
                raise VellisRequestInvalid(str(error), diagnostic=error.diagnostic) from error
            except (KeyError, TypeError, ValueError) as error:
                raise VellisRequestInvalid(str(error)) from error
            await execution.complete({"ok": True, "result": encode_json(result)})

        return handle

    async def _execute(
        self,
        name: str,
        arguments: JsonObject,
        execution: ComponentExecution,
    ) -> object:
        if name == "rtg_get_usage_guide":
            return _usage_guide(_text(arguments, "topic"))
        if name == "rtg_get_system_state":
            state = _object(await self._controller(name, {}, execution))
            starter_schema = decode_typed(
                await execution.call(
                    "starter-ontology-status",
                    STARTER_INSTALLER_ACTIONS["get_status"],
                    {"recovery": "not_checked"},
                    target=execution.address_for(self._starter_schema_key),
                ),
                StarterSchemaStatus,
            )
            if starter_schema is not None:
                state["starter_schema"] = starter_schema.to_json_value()
                if (
                    starter_schema.status == "installed"
                    and state.get("state_classification") == "schema_only"
                ):
                    workflows = state.get("recommended_workflows")
                    if (
                        isinstance(workflows, list)
                        and "everyday_memory_onboarding" not in workflows
                    ):
                        workflows.append("everyday_memory_onboarding")
                    steps = state.get("recommended_next_steps")
                    if isinstance(steps, list):
                        steps.insert(
                            0,
                            "The Everyday Life ontology is installed; ask what the user wants "
                            "Vellis to remember before proposing initial records.",
                        )
            state["runtime"] = await self._runtime_services.status()
            return state
        if name == "rtg_stage_schema_migration":
            return await self._stage_schema_migration(arguments, execution)
        if name in {"rtg_validate_live_anchor_records", "rtg_apply_live_anchor_records"}:
            return await self._anchor_records(name, arguments, execution)
        if name == "rtg_resolve_anchor_by_fact":
            return await self._resolve_anchor(arguments, execution)
        if name == "rtg_execute_query":
            query_spec = decode_query_spec(arguments["query_spec"])
            result = await self._controller(
                name,
                {
                    "query_spec": query_spec,
                    "query_options": decode_query_options(arguments.get("query_options")),
                },
                execution,
            )
            return _shape_query_response(
                decode_typed(result, RtgQueryResult),
                cast(dict[str, Any] | None, arguments.get("response_options")),
                query_spec,
            )
        if name == "rtg_export_system_snapshot":
            snapshot = await self._controller(name, {}, execution)
            if bool(arguments.get("summary", False)):
                return {
                    "kind": "summary",
                    "status": "snapshot_exported",
                    "summary": _snapshot_summary(snapshot),
                }
            return {"kind": "full", **_object(snapshot)}
        if name == "rtg_persist_system_snapshot":
            relative_path = _text(arguments, "relative_path")
            result = await self._controller(name, {"relative_path": relative_path}, execution)
            if bool(arguments.get("return_snapshot", False)):
                encoded = _object(result)
                encoded["snapshot"] = await self._controller(
                    "rtg_export_system_snapshot", {}, execution
                )
                result = encoded
            return _shape_persisted_snapshot_result(
                result,
                relative_path=relative_path,
                return_snapshot=bool(arguments.get("return_snapshot", False)),
            )
        if name == "rtg_load_persisted_snapshot":
            result = await self._controller(
                name,
                {"relative_path": _text(arguments, "relative_path")},
                execution,
            )
            return _shape_loaded_snapshot_result(
                result,
                return_snapshot=bool(arguments.get("return_snapshot", False)),
            )
        if name == "rtg_replay_ledger":
            return await self._runtime_services.reconstruct(
                decode_replay_options(arguments.get("replay_options"))
            )
        if name == "rtg_verify_replay_from_ledger":
            return await self._runtime_services.verify_reconstruction(
                decode_replay_options(arguments.get("replay_options"))
            )
        if name == "rtg_list_persisted_snapshots":
            return await self._controller(
                name,
                {
                    "offset": _optional_nonnegative_int(arguments, "offset") or 0,
                    "limit": _bounded_page_limit(arguments.get("limit")),
                },
                execution,
            )
        if name == "rtg_list_migration_history":
            return await self._runtime_services.migration_history(
                after_runtime_position=_optional_nonnegative_int(
                    arguments, "after_runtime_position"
                ),
                limit=_bounded_page_limit(arguments.get("limit")),
            )
        if name == "rtg_get_operation_outcome":
            include_state_transfer = arguments.get("include_state_transfer", False)
            if not isinstance(include_state_transfer, bool):
                raise VellisRequestInvalid("include_state_transfer must be a boolean")
            return await self._runtime_services.operation_outcome(
                message_id=_optional_text(arguments, "message_id"),
                request_key=_optional_text(arguments, "request_key"),
                include_state_transfer=include_state_transfer,
            )

        controller_arguments = _controller_arguments(name, arguments)
        return await self._controller(name, controller_arguments, execution)

    async def _controller(
        self,
        facade_action: str,
        arguments: dict[str, object],
        execution: ComponentExecution,
    ) -> JsonValue:
        controller_name = _CONTROLLER_ACTION_FOR_FACADE.get(facade_action, facade_action[4:])
        return await execution.call(
            f"controller:{facade_action}",
            RTG_CONTROLLER_ACTIONS[controller_name],
            arguments,
            target=execution.address_for(self._controller_key),
        )

    async def _stage_schema_migration(
        self,
        arguments: JsonObject,
        execution: ComponentExecution,
    ) -> JsonObject:
        migration_id = _text(arguments, "migration_id")
        description = _text(arguments, "description")
        definitions = _object_list(arguments, "schema_definitions")
        if not definitions:
            raise VellisRequestInvalid("schema_definitions must contain at least one definition")
        response_format = _mutation_response_format(
            cast(dict[str, Any] | None, arguments.get("response_options"))
        )
        writes: list[dict[str, Any]] = []
        generated_ids: dict[str, str] = {}
        make_live: list[str] = []
        seen: set[str] = set()
        for index, source in enumerate(definitions):
            definition = copy.deepcopy(source)
            kind = _required_text(definition, "kind", f"schema_definitions[{index}].kind")
            type_key = _required_text(
                definition, "type_key", f"schema_definitions[{index}].type_key"
            )
            schema_key = f"{kind}:{type_key}"
            if schema_key in seen:
                raise VellisRequestInvalid(
                    "schema_definitions must contain unique kind and type_key pairs"
                )
            seen.add(schema_key)
            definition_id = str(uuid4())
            definition["uuid"] = definition_id
            system = definition.get("system", {})
            if not isinstance(system, dict):
                raise VellisRequestInvalid(f"schema_definitions[{index}].system must be an object")
            definition["system"] = {**system, "live": False}
            generated_ids[schema_key] = definition_id
            make_live.append(definition_id)
            writes.append({"ref": {"resource_id": definition_id}, "definition": definition})
        make_non_live = await self._schema_retirements(
            cast(list[dict[str, Any]], arguments.get("retire_live_schema") or []),
            execution,
        )
        changes: dict[str, Any] = {
            "schema_changes": {"definition_writes": writes},
            "migration_changes": {
                "migration_writes": [
                    {
                        "ref": {"resource_id": migration_id},
                        "migration": {
                            "migration_id": migration_id,
                            "description": description,
                            "status": "ready",
                            "schema_make_live": make_live,
                            "schema_make_non_live": make_non_live,
                        },
                    }
                ]
            },
        }
        operation = await self._controller(
            "rtg_stage_knowledge_changes",
            {
                "knowledge_changes": decode_change_batch(changes),
                "validation_mode": str(arguments.get("validation_mode", "strict")),
            },
            execution,
        )
        result: JsonObject = {
            "format": response_format,
            "generated_schema_ids": generated_ids,
            "operation": operation,
        }
        if response_format == "full":
            result["submitted_knowledge_changes"] = changes
        return result

    async def _schema_retirements(
        self,
        selectors: list[dict[str, Any]],
        execution: ComponentExecution,
    ) -> list[str]:
        if not selectors:
            return []
        resolved: list[str] = []
        for index, selector in enumerate(selectors):
            kind = _required_text(selector, "kind", f"retire_live_schema[{index}].kind")
            type_key = _required_text(selector, "type_key", f"retire_live_schema[{index}].type_key")
            page = _object(
                await self._controller(
                    "rtg_list_schema_definitions_by_type_key",
                    {
                        "type_key": type_key,
                        "kind": kind,
                        "live": True,
                        "offset": 0,
                        "limit": 2,
                    },
                    execution,
                )
            )
            matches = [str(item["uuid"]) for item in _object_list(page, "definitions")]
            if len(matches) != 1:
                raise VellisRequestInvalid(
                    f"retire_live_schema[{index}] expected exactly one live schema definition "
                    f"for kind={kind!r}, type_key={type_key!r}; found {len(matches)}"
                )
            resolved.append(matches[0])
        return resolved

    async def _anchor_records(
        self,
        name: str,
        arguments: JsonObject,
        execution: ComponentExecution,
    ) -> JsonObject:
        compiled = _compile_live_anchor_records(
            _object_list(arguments, "anchor_records"),
            cast(list[dict[str, Any]], arguments.get("link_writes") or []),
        )
        graph_changes = decode_graph_changes(compiled["submitted_graph_changes"])
        if name == "rtg_validate_live_anchor_records":
            response_format = _mutation_response_format(
                cast(dict[str, Any] | None, arguments.get("response_options"))
            )
            validation = _object(await self._controller(
                "rtg_validate_live_graph_changes",
                {
                    "graph_changes": graph_changes,
                    "validation_options": decode_validation_options(
                        arguments.get("validation_options")
                    ),
                },
                execution,
            ))
            validation_result: JsonObject = {
                "format": response_format,
                "status": cast(JsonValue, validation.get("status")),
                "mutation_state": cast(JsonValue, validation.get("mutation_state")),
                "accepted": bool(validation.get("accepted", False)),
                "identity_resolutions": _identity_resolutions(compiled, validation),
                "validation_report": cast(
                    JsonValue, validation.get("validation_report", {})
                ),
            }
            if response_format == "full":
                validation_result["submitted_graph_changes"] = compiled[
                    "submitted_graph_changes"
                ]
            return validation_result
        response_format = _mutation_response_format(
            cast(dict[str, Any] | None, arguments.get("response_options"))
        )
        operation = _object(
            await self._controller(
                "rtg_apply_live_graph_changes",
                {
                    "graph_changes": graph_changes,
                    "validation_mode": str(arguments.get("validation_mode", "strict")),
                },
                execution,
            )
        )
        result: JsonObject = {
            "format": response_format,
            "identity_resolutions": _identity_resolutions(compiled, operation),
            "operation": _public_mutation_operation(operation),
        }
        if response_format == "full":
            result["submitted_graph_changes"] = compiled["submitted_graph_changes"]
        return result

    async def _resolve_anchor(
        self,
        arguments: JsonObject,
        execution: ComponentExecution,
    ) -> JsonObject:
        submitted = _anchor_fact_lookup_query(
            anchor_type=_text(arguments, "anchor_type"),
            data_type=_text(arguments, "data_type"),
            property_path=cast(list[str], arguments["property_path"]),
            value=arguments.get("value"),
            case_sensitive=bool(arguments.get("case_sensitive", False)),
        )
        encoded = _object(
            await self._controller(
                "rtg_execute_query",
                {
                    "query_spec": decode_query_spec(submitted["query_spec"]),
                    "query_options": decode_query_options(submitted["query_options"]),
                },
                execution,
            )
        )
        matches = _anchor_fact_lookup_matches(encoded)
        return {
            "status": "resolved",
            "match_count": len(matches),
            "matches": matches,
            "submitted_query": submitted,
            "diagnostics": cast(JsonValue, encoded.get("diagnostics", [])),
            "guidance": _anchor_resolution_guidance(len(matches)),
        }


_CONTROLLER_ACTION_FOR_FACADE = {
    "rtg_validate_live_anchor_records": "validate_live_graph_changes",
    "rtg_apply_live_anchor_records": "apply_live_graph_changes",
    "rtg_resolve_anchor_by_fact": "execute_query",
}


def _identity_resolutions(compiled: JsonObject, operation: JsonObject) -> list[JsonObject]:
    generated = operation.get("generated_ids", {})
    if not isinstance(generated, dict):
        return []
    positions: dict[str, tuple[str, int | None, int | None]] = {}
    changes = compiled.get("submitted_graph_changes", {})
    if isinstance(changes, dict):
        for kind, key in (
            ("anchor", "anchor_writes"),
            ("data_object", "data_object_writes"),
            ("link", "link_writes"),
        ):
            values = changes.get(key, [])
            if not isinstance(values, list):
                continue
            for index, value in enumerate(values):
                if not isinstance(value, dict) or not isinstance(value.get("ref"), dict):
                    continue
                local_ref = value["ref"].get("local_ref")
                if isinstance(local_ref, str):
                    positions[local_ref] = (kind, index, None)
    facts = compiled.get("generated_refs", {})
    if isinstance(facts, dict) and isinstance(facts.get("facts"), list):
        for value in facts["facts"]:
            if not isinstance(value, dict) or not isinstance(value.get("local_ref"), str):
                continue
            positions[value["local_ref"]] = (
                "data_object",
                int(value["anchor_index"]),
                int(value["fact_index"]),
            )
    result: list[JsonObject] = []
    for local_ref, resource_id in sorted(generated.items()):
        kind, parent_index, child_index = positions.get(
            str(local_ref), ("graph_object", None, None)
        )
        item: JsonObject = {
            "local_ref": str(local_ref),
            "resource_id": str(resource_id),
            "resource_kind": kind,
        }
        if parent_index is not None:
            item["anchor_index" if child_index is not None else "write_index"] = parent_index
        if child_index is not None:
            item["fact_index"] = child_index
        result.append(item)
    return result


def _public_mutation_operation(operation: JsonObject) -> JsonObject:
    """Expose one compact operation result without state or repeated identity maps."""

    return {
        key: cast(JsonValue, operation[key])
        for key in ("status", "applied_changes", "validation_report")
        if key in operation and operation[key] is not None
    }


def _controller_arguments(name: str, arguments: JsonObject) -> dict[str, object]:
    if name == "rtg_validate_live_graph_changes":
        return {
            "graph_changes": decode_graph_changes(arguments["graph_changes"]),
            "validation_options": decode_validation_options(arguments.get("validation_options")),
        }
    if name == "rtg_apply_live_graph_changes":
        return {
            "graph_changes": decode_graph_changes(arguments["graph_changes"]),
            "validation_mode": str(arguments.get("validation_mode", "strict")),
        }
    if name == "rtg_stage_knowledge_changes":
        return {
            "knowledge_changes": decode_change_batch(arguments["knowledge_changes"]),
            "validation_mode": str(arguments.get("validation_mode", "strict")),
        }
    if name == "rtg_apply_migration_cutover":
        return {
            "migration_id": _text(arguments, "migration_id"),
            "cutover_options": decode_cutover_options(arguments.get("cutover_options")),
        }
    if name == "rtg_abandon_migration":
        return {
            "migration_id": _text(arguments, "migration_id"),
            "reason": arguments.get("reason"),
        }
    if name == "rtg_get_object":
        return {"object_uuid": _text(arguments, "object_uuid")}
    if name == "rtg_list_migrations":
        return {
            "status": arguments.get("status"),
            "offset": int(arguments.get("offset", 0)),
            "limit": _bounded_page_limit(arguments.get("limit")),
        }
    if name == "rtg_get_migration":
        return {"migration_id": _text(arguments, "migration_id")}
    if name == "rtg_validate_graph":
        ids = arguments.get("migration_ids")
        return {
            "migration_ids": tuple(cast(list[str], ids)) if ids is not None else None,
            "validation_options": decode_validation_options(arguments.get("validation_options")),
        }
    if name == "rtg_discover_anchor_types":
        return {"discovery_options": decode_discovery_options(arguments.get("discovery_options"))}
    if name == "rtg_get_schema_pack":
        return {
            "anchor_type_keys": tuple(cast(list[str], arguments["anchor_type_keys"])),
            "schema_pack_options": decode_schema_pack_options(arguments.get("schema_pack_options")),
        }
    if name == "rtg_restore_from_snapshot":
        decode_restore_options(arguments.get("restore_options"))
        return {"snapshot": decode_system_snapshot(arguments["snapshot"])}
    if name in {"rtg_list_persisted_snapshots", "rtg_export_system_snapshot"}:
        return {}
    raise VellisRequestInvalid(f"unsupported facade operation: {name}")


def _remote_fault_disposition(name: str, payload: JsonObject) -> RuntimeTraceDisposition:
    fault_type = payload.get("type")
    if fault_type == "RtgControllerRecoveryIndeterminate":
        return RuntimeTraceDisposition.INDETERMINATE
    if name == "rtg_apply_migration_cutover" and fault_type in {
        "RtgControllerValidationFailed",
        "RtgControllerApplyFailed",
    }:
        return RuntimeTraceDisposition.COMMITTED
    return RuntimeTraceDisposition.ABORTED


def _text(value: JsonObject, key: str) -> str:
    item = value[key]
    if not isinstance(item, str) or not item:
        raise VellisRequestInvalid(f"{key} must be a non-empty string")
    return item


def _optional_text(value: JsonObject, key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str) or not item:
        raise VellisRequestInvalid(f"{key} must be a non-empty string when supplied")
    return item


def _optional_nonnegative_int(value: JsonObject, key: str) -> int | None:
    item = value.get(key)
    if item is None:
        return None
    if isinstance(item, bool) or not isinstance(item, int) or item < 0:
        raise VellisRequestInvalid(f"{key} must be a non-negative integer when supplied")
    return item


def _bounded_page_limit(value: object) -> int:
    if value is None:
        return 100
    if isinstance(value, bool) or not isinstance(value, int):
        raise VellisRequestInvalid("limit must be an integer")
    limit = value
    if not 1 <= limit <= 500:
        raise VellisRequestInvalid("limit must be between 1 and 500")
    return limit


def _object(value: object) -> JsonObject:
    if not isinstance(value, dict):
        raise VellisRequestInvalid("expected an object result")
    return cast(JsonObject, value)


def _object_list(value: JsonObject, key: str) -> list[dict[str, Any]]:
    items = value.get(key, [])
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise VellisRequestInvalid(f"{key} must be a list of objects")
    return cast(list[dict[str, Any]], items)


__all__ = ["VellisFacadeComponent"]
