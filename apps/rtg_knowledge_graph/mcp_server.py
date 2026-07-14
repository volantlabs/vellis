from __future__ import annotations

from typing import Any, Literal, cast

from fastmcp import FastMCP

from apps.rtg_knowledge_graph.composition import build_app
from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from apps.rtg_knowledge_graph.mcp_launch import (
    DEFAULT_LOCALHOST_HOST,
    DEFAULT_LOCALHOST_PATH,
    DEFAULT_LOCALHOST_PORT,
    MCP_SERVER_NAME,
    mcp_launch_metadata,
)
from apps.rtg_knowledge_graph.mcp_toolset import (
    TOOL_ANNOTATIONS,
    TOOL_DESCRIPTIONS,
    RtgMcpToolset,
    mcp_tool_metadata,
)
from components.rtg.graph import JsonObject


def build_mcp_server(toolset: RtgMcpToolset) -> FastMCP:
    server = FastMCP(
        MCP_SERVER_NAME,
        instructions=(
            "Read system state first. Use installed schema when present and discover schema "
            "before writing. Dry-run risky changes, use the correct mutation lane, and fetch "
            "usage-guide topics for detailed request shapes."
        ),
    )

    def _tool(*, name: str, description: str):
        return server.tool(
            name=name,
            description=description,
            annotations=TOOL_ANNOTATIONS[name],
        )

    @_tool(name="rtg_get_system_state", description=TOOL_DESCRIPTIONS["rtg_get_system_state"])
    def rtg_get_system_state() -> dict[str, Any]:
        return _as_tool_result(toolset.rtg_get_system_state())

    @_tool(name="rtg_get_usage_guide", description=TOOL_DESCRIPTIONS["rtg_get_usage_guide"])
    def rtg_get_usage_guide(topic: str) -> dict[str, Any]:
        return _as_tool_result(toolset.rtg_get_usage_guide(topic))

    @_tool(
        name="rtg_stage_schema_migration",
        description=TOOL_DESCRIPTIONS["rtg_stage_schema_migration"],
    )
    def rtg_stage_schema_migration(
        migration_id: str,
        description: str,
        schema_definitions: list[dict[str, Any]],
        retire_live_schema: list[dict[str, Any]] | None = None,
        validation_mode: str = "strict",
        response_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _as_tool_result(
            toolset.rtg_stage_schema_migration(
                migration_id,
                description,
                schema_definitions,
                retire_live_schema,
                validation_mode,
                _optional_json_object(response_options),
            )
        )

    @_tool(
        name="rtg_validate_live_anchor_records",
        description=TOOL_DESCRIPTIONS["rtg_validate_live_anchor_records"],
    )
    def rtg_validate_live_anchor_records(
        anchor_records: list[dict[str, Any]],
        link_writes: list[dict[str, Any]] | None = None,
        validation_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _as_tool_result(
            toolset.rtg_validate_live_anchor_records(
                anchor_records,
                link_writes,
                _optional_json_object(validation_options),
            )
        )

    @_tool(
        name="rtg_apply_live_anchor_records",
        description=TOOL_DESCRIPTIONS["rtg_apply_live_anchor_records"],
    )
    def rtg_apply_live_anchor_records(
        anchor_records: list[dict[str, Any]],
        link_writes: list[dict[str, Any]] | None = None,
        validation_mode: str = "strict",
        response_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _as_tool_result(
            toolset.rtg_apply_live_anchor_records(
                anchor_records,
                link_writes,
                validation_mode,
                _optional_json_object(response_options),
            )
        )

    @_tool(
        name="rtg_apply_live_graph_changes",
        description=TOOL_DESCRIPTIONS["rtg_apply_live_graph_changes"],
    )
    def rtg_apply_live_graph_changes(
        graph_changes: dict[str, Any],
        validation_mode: str = "strict",
    ) -> dict[str, Any]:
        return _as_tool_result(
            toolset.rtg_apply_live_graph_changes(
                _json_object(graph_changes),
                validation_mode=validation_mode,
            )
        )

    @_tool(
        name="rtg_validate_live_graph_changes",
        description=TOOL_DESCRIPTIONS["rtg_validate_live_graph_changes"],
    )
    def rtg_validate_live_graph_changes(
        graph_changes: dict[str, Any],
        validation_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _as_tool_result(
            toolset.rtg_validate_live_graph_changes(
                _json_object(graph_changes),
                validation_options=_optional_json_object(validation_options),
            )
        )

    @_tool(
        name="rtg_stage_knowledge_changes",
        description=TOOL_DESCRIPTIONS["rtg_stage_knowledge_changes"],
    )
    def rtg_stage_knowledge_changes(
        knowledge_changes: dict[str, Any],
        validation_mode: str = "strict",
    ) -> dict[str, Any]:
        return _as_tool_result(
            toolset.rtg_stage_knowledge_changes(
                _json_object(knowledge_changes),
                validation_mode=validation_mode,
            )
        )

    @_tool(
        name="rtg_apply_migration_cutover",
        description=TOOL_DESCRIPTIONS["rtg_apply_migration_cutover"],
    )
    def rtg_apply_migration_cutover(
        migration_id: str,
        cutover_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _as_tool_result(
            toolset.rtg_apply_migration_cutover(
                migration_id,
                _optional_json_object(cutover_options),
            )
        )

    @_tool(name="rtg_abandon_migration", description=TOOL_DESCRIPTIONS["rtg_abandon_migration"])
    def rtg_abandon_migration(
        migration_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return _as_tool_result(toolset.rtg_abandon_migration(migration_id, reason))

    @_tool(name="rtg_execute_query", description=TOOL_DESCRIPTIONS["rtg_execute_query"])
    def rtg_execute_query(
        query_spec: dict[str, Any],
        query_options: dict[str, Any] | None = None,
        response_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _as_tool_result(
            toolset.rtg_execute_query(
                _json_object(query_spec),
                _optional_json_object(query_options),
                _optional_json_object(response_options),
            )
        )

    @_tool(
        name="rtg_resolve_anchor_by_fact",
        description=TOOL_DESCRIPTIONS["rtg_resolve_anchor_by_fact"],
    )
    def rtg_resolve_anchor_by_fact(
        anchor_type: str,
        data_type: str,
        property_path: list[str],
        value: Any,
        case_sensitive: bool = False,
    ) -> dict[str, Any]:
        return _as_tool_result(
            toolset.rtg_resolve_anchor_by_fact(
                anchor_type,
                data_type,
                property_path,
                value,
                case_sensitive,
            )
        )

    @_tool(name="rtg_get_object", description=TOOL_DESCRIPTIONS["rtg_get_object"])
    def rtg_get_object(object_uuid: str) -> dict[str, Any]:
        return _as_tool_result(toolset.rtg_get_object(object_uuid))

    @_tool(
        name="rtg_list_migrations",
        description=TOOL_DESCRIPTIONS["rtg_list_migrations"],
    )
    def rtg_list_migrations(status: str | None = None) -> dict[str, Any]:
        return _as_tool_result(toolset.rtg_list_migrations(status=status))

    @_tool(name="rtg_get_migration", description=TOOL_DESCRIPTIONS["rtg_get_migration"])
    def rtg_get_migration(migration_id: str) -> dict[str, Any]:
        return _as_tool_result(toolset.rtg_get_migration(migration_id))

    @_tool(
        name="rtg_validate_graph",
        description=TOOL_DESCRIPTIONS["rtg_validate_graph"],
    )
    def rtg_validate_graph(
        migration_ids: list[str] | None = None,
        validation_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _as_tool_result(
            toolset.rtg_validate_graph(
                migration_ids=migration_ids,
                validation_options=_optional_json_object(validation_options),
            )
        )

    @_tool(
        name="rtg_discover_anchor_types",
        description=TOOL_DESCRIPTIONS["rtg_discover_anchor_types"],
    )
    def rtg_discover_anchor_types(
        discovery_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _as_tool_result(
            toolset.rtg_discover_anchor_types(
                _optional_json_object(discovery_options),
            )
        )

    @_tool(
        name="rtg_get_schema_pack",
        description=TOOL_DESCRIPTIONS["rtg_get_schema_pack"],
    )
    def rtg_get_schema_pack(
        anchor_type_keys: list[str],
        schema_pack_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _as_tool_result(
            toolset.rtg_get_schema_pack(
                anchor_type_keys,
                _optional_json_object(schema_pack_options),
            )
        )

    @_tool(
        name="rtg_export_system_snapshot",
        description=TOOL_DESCRIPTIONS["rtg_export_system_snapshot"],
    )
    def rtg_export_system_snapshot(summary: bool = False) -> dict[str, Any]:
        return _as_tool_result(toolset.rtg_export_system_snapshot(summary=summary))

    @_tool(
        name="rtg_persist_system_snapshot",
        description=TOOL_DESCRIPTIONS["rtg_persist_system_snapshot"],
    )
    def rtg_persist_system_snapshot(
        relative_path: str,
        return_snapshot: bool = True,
    ) -> dict[str, Any]:
        return _as_tool_result(
            toolset.rtg_persist_system_snapshot(relative_path, return_snapshot=return_snapshot)
        )

    @_tool(
        name="rtg_list_persisted_snapshots",
        description=TOOL_DESCRIPTIONS["rtg_list_persisted_snapshots"],
    )
    def rtg_list_persisted_snapshots() -> dict[str, Any]:
        return _as_tool_result(toolset.rtg_list_persisted_snapshots())

    @_tool(
        name="rtg_load_persisted_snapshot",
        description=TOOL_DESCRIPTIONS["rtg_load_persisted_snapshot"],
    )
    def rtg_load_persisted_snapshot(
        relative_path: str,
        return_snapshot: bool = True,
    ) -> dict[str, Any]:
        return _as_tool_result(
            toolset.rtg_load_persisted_snapshot(
                relative_path,
                return_snapshot=return_snapshot,
            )
        )

    @_tool(
        name="rtg_replay_ledger",
        description=TOOL_DESCRIPTIONS["rtg_replay_ledger"],
    )
    def rtg_replay_ledger(replay_options: dict[str, Any] | None = None) -> dict[str, Any]:
        return _as_tool_result(toolset.rtg_replay_ledger(_optional_json_object(replay_options)))

    @_tool(
        name="rtg_verify_replay_from_ledger",
        description=TOOL_DESCRIPTIONS["rtg_verify_replay_from_ledger"],
    )
    def rtg_verify_replay_from_ledger(
        replay_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _as_tool_result(
            toolset.rtg_verify_replay_from_ledger(_optional_json_object(replay_options))
        )

    @_tool(
        name="rtg_list_migration_history",
        description=TOOL_DESCRIPTIONS["rtg_list_migration_history"],
    )
    def rtg_list_migration_history() -> dict[str, Any]:
        return _as_tool_result(toolset.rtg_list_migration_history())

    @_tool(
        name="rtg_flush_ledger_failures",
        description=TOOL_DESCRIPTIONS["rtg_flush_ledger_failures"],
    )
    def rtg_flush_ledger_failures() -> dict[str, Any]:
        return _as_tool_result(toolset.rtg_flush_ledger_failures())

    @_tool(
        name="rtg_restore_from_snapshot",
        description=TOOL_DESCRIPTIONS["rtg_restore_from_snapshot"],
    )
    def rtg_restore_from_snapshot(
        snapshot: dict[str, Any],
        restore_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _as_tool_result(
            toolset.rtg_restore_from_snapshot(
                _json_object(snapshot),
                _optional_json_object(restore_options),
            )
        )

    return server


McpTransport = Literal["stdio", "http"]


def mcp_dry_run_status(
    config: RtgKnowledgeGraphConfig,
    *,
    transport: McpTransport = "stdio",
    host: str = DEFAULT_LOCALHOST_HOST,
    port: int = DEFAULT_LOCALHOST_PORT,
    path: str = DEFAULT_LOCALHOST_PATH,
) -> dict[str, Any]:
    composition = build_app(config)
    starter_schema = composition.prepare()
    status = composition.runner.run()
    launch_metadata = mcp_launch_metadata(
        config,
        localhost_host=host,
        localhost_port=port,
        localhost_path=path,
        preferred_transport=transport,
    )
    return {
        "app": status.to_json_value(),
        "mcp": {
            "server_name": MCP_SERVER_NAME,
            "transport": transport,
            **launch_metadata,
            "starter_schema": starter_schema.to_json_value(),
            "tools": mcp_tool_metadata(),
        },
    }


def run_mcp_server(
    config: RtgKnowledgeGraphConfig,
    transport: McpTransport = "stdio",
    *,
    host: str = DEFAULT_LOCALHOST_HOST,
    port: int = DEFAULT_LOCALHOST_PORT,
    path: str = DEFAULT_LOCALHOST_PATH,
) -> None:
    composition = build_app(config)
    starter_schema = composition.prepare()
    composition.runner.run()
    server = build_mcp_server(RtgMcpToolset(composition.controller, starter_schema))
    if transport == "stdio":
        server.run(transport=transport)
        return
    server.run(
        transport=transport,
        host=host,
        port=port,
        path=path,
    )


def _json_object(value: dict[str, Any]) -> JsonObject:
    return cast(JsonObject, value)


def _optional_json_object(value: dict[str, Any] | None) -> JsonObject | None:
    return None if value is None else _json_object(value)


def _as_tool_result(value: JsonObject) -> dict[str, Any]:
    return cast(dict[str, Any], value)
