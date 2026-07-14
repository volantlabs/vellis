from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastmcp import FastMCP

from apps.rtg_federation.registry_io import (
    DEFAULT_REGISTRY_PATH,
    default_bridge_path_for_registry,
    load_optional_bridge_store,
    load_registry,
)
from apps.rtg_federation.semantic_openai import (
    openai_semantic_generator_from_environment,
)
from apps.rtg_federation.toolset import (
    TOOL_DESCRIPTIONS,
    RtgFederationToolset,
    mcp_tool_metadata,
)

MCP_SERVER_NAME = "rtg_federation"
DEFAULT_LOCALHOST_HOST = "127.0.0.1"
DEFAULT_LOCALHOST_PORT = 8775
DEFAULT_LOCALHOST_PATH = "/mcp"

McpTransport = Literal["stdio", "http"]


def build_mcp_server(toolset: RtgFederationToolset) -> FastMCP:
    server = FastMCP(
        MCP_SERVER_NAME,
        instructions=(
            "Use this server as the Vellis RTG graph control plane. Start with "
            "vellis_list_graphs and vellis_federated_capabilities to inspect registered graph "
            "monographs, then use vellis_federated_preflight to confirm declared reads can load "
            "and validate before broad execution. Use vellis_route_pack_preview to assemble the "
            "selected skill, scoped tools, docs, checks, route records, and hazards before acting. "
            "Use vellis_route_pack_gate to decide whether to invoke, clarify, or block before "
            "execution. "
            "Use vellis_intent_compile before invoking graph-specific MCP tools. "
            "Reads may proceed when a route is selected and does not require confirmation. Writes "
            "must name a target_graph_id explicitly. Use vellis_graph_mcp_info to obtain launch "
            "and client configuration for the selected graph. Use vellis_federated_plan when a "
            "question may need graph-local reads from more than one monograph; bridge_hints and "
            "their follow_up_checklist items are planning facts, not executed joins. "
            "candidate_hints require review and promotion before traversal. "
            "Use vellis_bridge_candidates and vellis_bridge_candidate to inspect proposals, and "
            "promote or reject them explicitly. "
            "Use vellis_federated_answer for read-only structured synthesis across supported "
            "graph-local canned reads. Use vellis_federated_semantic_answer only when semantic "
            "synthesis was explicitly enabled at server launch; it runs the deterministic "
            "answer first and validates generated claims against that evidence. "
            "Resolve one returned graph-qualified citation with vellis_resolve_citation; it uses "
            "only the owning graph's descriptor-declared "
            "projection. Use vellis_traverse_bridge only with one explicit active confirmed "
            "bridge id; it resolves the two endpoints independently and does not join them. Use "
            "vellis_route_query only for read-only single-graph queries after route compilation. "
            "This server does not proxy graph writes or perform cross-graph joins."
        ),
    )

    @server.tool(
        name="vellis_list_graphs",
        description=TOOL_DESCRIPTIONS["vellis_list_graphs"],
    )
    def vellis_list_graphs() -> dict[str, Any]:
        return toolset.vellis_list_graphs()

    @server.tool(
        name="vellis_federated_capabilities",
        description=TOOL_DESCRIPTIONS["vellis_federated_capabilities"],
    )
    def vellis_federated_capabilities() -> dict[str, Any]:
        return toolset.vellis_federated_capabilities()

    @server.tool(
        name="vellis_federated_preflight",
        description=TOOL_DESCRIPTIONS["vellis_federated_preflight"],
    )
    def vellis_federated_preflight() -> dict[str, Any]:
        return toolset.vellis_federated_preflight()

    @server.tool(
        name="vellis_intent_compile",
        description=TOOL_DESCRIPTIONS["vellis_intent_compile"],
    )
    def vellis_intent_compile(
        text: str,
        operation: str = "read",
        target_graph_id: str | None = None,
        domain_hints: list[str] | None = None,
        tag_hints: list[str] | None = None,
    ) -> dict[str, Any]:
        return toolset.vellis_intent_compile(
            text=text,
            operation=operation,
            target_graph_id=target_graph_id,
            domain_hints=domain_hints,
            tag_hints=tag_hints,
        )

    @server.tool(
        name="vellis_route_pack_preview",
        description=TOOL_DESCRIPTIONS["vellis_route_pack_preview"],
    )
    def vellis_route_pack_preview(
        text: str,
        operation: str = "read",
        target_graph_ids: list[str] | None = None,
        domain_hints: list[str] | None = None,
        tag_hints: list[str] | None = None,
    ) -> dict[str, Any]:
        return toolset.vellis_route_pack_preview(
            text=text,
            operation=operation,
            target_graph_ids=target_graph_ids,
            domain_hints=domain_hints,
            tag_hints=tag_hints,
        )

    @server.tool(
        name="vellis_route_pack_gate",
        description=TOOL_DESCRIPTIONS["vellis_route_pack_gate"],
    )
    def vellis_route_pack_gate(
        text: str,
        operation: str = "read",
        target_graph_ids: list[str] | None = None,
        domain_hints: list[str] | None = None,
        tag_hints: list[str] | None = None,
    ) -> dict[str, Any]:
        return toolset.vellis_route_pack_gate(
            text=text,
            operation=operation,
            target_graph_ids=target_graph_ids,
            domain_hints=domain_hints,
            tag_hints=tag_hints,
        )

    @server.tool(
        name="vellis_federated_plan",
        description=TOOL_DESCRIPTIONS["vellis_federated_plan"],
    )
    def vellis_federated_plan(
        text: str,
        operation: str = "read",
        target_graph_ids: list[str] | None = None,
        domain_hints: list[str] | None = None,
        tag_hints: list[str] | None = None,
    ) -> dict[str, Any]:
        return toolset.vellis_federated_plan(
            text=text,
            operation=operation,
            target_graph_ids=target_graph_ids,
            domain_hints=domain_hints,
            tag_hints=tag_hints,
        )

    @server.tool(
        name="vellis_federated_answer",
        description=TOOL_DESCRIPTIONS["vellis_federated_answer"],
    )
    def vellis_federated_answer(
        text: str,
        operation: str = "read",
        target_graph_ids: list[str] | None = None,
        domain_hints: list[str] | None = None,
        tag_hints: list[str] | None = None,
        canned_queries: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return toolset.vellis_federated_answer(
            text=text,
            operation=operation,
            target_graph_ids=target_graph_ids,
            domain_hints=domain_hints,
            tag_hints=tag_hints,
            canned_queries=canned_queries,
        )

    @server.tool(
        name="vellis_federated_semantic_answer",
        description=TOOL_DESCRIPTIONS["vellis_federated_semantic_answer"],
    )
    def vellis_federated_semantic_answer(
        text: str,
        operation: str = "read",
        target_graph_ids: list[str] | None = None,
        domain_hints: list[str] | None = None,
        tag_hints: list[str] | None = None,
        canned_queries: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return toolset.vellis_federated_semantic_answer(
            text=text,
            operation=operation,
            target_graph_ids=target_graph_ids,
            domain_hints=domain_hints,
            tag_hints=tag_hints,
            canned_queries=canned_queries,
        )

    @server.tool(
        name="vellis_resolve_citation",
        description=TOOL_DESCRIPTIONS["vellis_resolve_citation"],
    )
    def vellis_resolve_citation(
        graph_id: str,
        local_uuid: str,
    ) -> dict[str, Any]:
        return toolset.vellis_resolve_citation(
            graph_id=graph_id,
            local_uuid=local_uuid,
        )

    @server.tool(
        name="vellis_traverse_bridge",
        description=TOOL_DESCRIPTIONS["vellis_traverse_bridge"],
    )
    def vellis_traverse_bridge(bridge_id: str) -> dict[str, Any]:
        return toolset.vellis_traverse_bridge(bridge_id=bridge_id)

    @server.tool(
        name="vellis_graph_mcp_info",
        description=TOOL_DESCRIPTIONS["vellis_graph_mcp_info"],
    )
    def vellis_graph_mcp_info(graph_id: str) -> dict[str, Any]:
        return toolset.vellis_graph_mcp_info(graph_id)

    @server.tool(
        name="vellis_route_query",
        description=TOOL_DESCRIPTIONS["vellis_route_query"],
    )
    def vellis_route_query(
        text: str,
        query_spec: dict[str, Any] | None = None,
        query_options: dict[str, Any] | None = None,
        response_options: dict[str, Any] | None = None,
        target_graph_id: str | None = None,
        domain_hints: list[str] | None = None,
        tag_hints: list[str] | None = None,
        canned_query: str | None = None,
    ) -> dict[str, Any]:
        return toolset.vellis_route_query(
            text=text,
            query_spec=query_spec,
            query_options=query_options,
            response_options=response_options,
            target_graph_id=target_graph_id,
            domain_hints=domain_hints,
            tag_hints=tag_hints,
            canned_query=canned_query,
        )

    @server.tool(
        name="vellis_bridge_candidates",
        description=TOOL_DESCRIPTIONS["vellis_bridge_candidates"],
    )
    def vellis_bridge_candidates(status: str = "candidate_only") -> dict[str, Any]:
        return toolset.vellis_bridge_candidates(status=status)

    @server.tool(
        name="vellis_bridge_candidate",
        description=TOOL_DESCRIPTIONS["vellis_bridge_candidate"],
    )
    def vellis_bridge_candidate(candidate_id: str) -> dict[str, Any]:
        return toolset.vellis_bridge_candidate(candidate_id)

    @server.tool(
        name="vellis_promote_bridge_candidate",
        description=TOOL_DESCRIPTIONS["vellis_promote_bridge_candidate"],
    )
    def vellis_promote_bridge_candidate(
        candidate_id: str,
        asserted_at: str,
        asserted_by: str,
    ) -> dict[str, Any]:
        return toolset.vellis_promote_bridge_candidate(
            candidate_id=candidate_id,
            asserted_at=asserted_at,
            asserted_by=asserted_by,
        )

    @server.tool(
        name="vellis_reject_bridge_candidate",
        description=TOOL_DESCRIPTIONS["vellis_reject_bridge_candidate"],
    )
    def vellis_reject_bridge_candidate(
        candidate_id: str,
        rejected_at: str,
        rejected_by: str,
        reason: str,
    ) -> dict[str, Any]:
        return toolset.vellis_reject_bridge_candidate(
            candidate_id=candidate_id,
            rejected_at=rejected_at,
            rejected_by=rejected_by,
            reason=reason,
        )

    return server


def mcp_dry_run_status(
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    *,
    bridge_path: Path | None = None,
    transport: McpTransport = "stdio",
    host: str = DEFAULT_LOCALHOST_HOST,
    port: int = DEFAULT_LOCALHOST_PORT,
    path: str = DEFAULT_LOCALHOST_PATH,
    semantic_model: str | None = None,
    semantic_api_key_env: str = "OPENAI_API_KEY",
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    resolved_bridge_path = bridge_path or default_bridge_path_for_registry(registry_path)
    bridge_store = load_optional_bridge_store(resolved_bridge_path)
    launch = _launch_metadata(
        registry_path=registry_path,
        bridge_path=bridge_path,
        transport=transport,
        host=host,
        port=port,
        path=path,
        semantic_model=semantic_model,
        semantic_api_key_env=semantic_api_key_env,
    )
    return {
        "app": {
            "app_name": "rtg_federation",
            "registry_path": str(registry_path.resolve()),
            "graph_count": len(registry.list_graphs().graphs),
            "bridge_catalog_path": str(resolved_bridge_path.resolve()),
            "bridge_catalog_status": "loaded" if bridge_store is not None else "not_configured",
            "bridge_count": (
                0 if bridge_store is None else len(bridge_store.list_bridges(status=None).bridges)
            ),
            "bridge_candidate_count": (
                0
                if bridge_store is None
                else len(bridge_store.list_candidates(status=None).candidates)
            ),
            "semantic_synthesis": {
                "status": "enabled_requested" if semantic_model else "not_configured",
                "model": semantic_model,
                "api_key_env": semantic_api_key_env if semantic_model else None,
            },
        },
        "mcp": {
            "server_name": MCP_SERVER_NAME,
            "transport": transport,
            "tools": mcp_tool_metadata(),
            **launch,
        },
    }


def run_mcp_server(
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    *,
    bridge_path: Path | None = None,
    transport: McpTransport = "stdio",
    host: str = DEFAULT_LOCALHOST_HOST,
    port: int = DEFAULT_LOCALHOST_PORT,
    path: str = DEFAULT_LOCALHOST_PATH,
    semantic_model: str | None = None,
    semantic_api_key_env: str = "OPENAI_API_KEY",
) -> None:
    registry = load_registry(registry_path)
    resolved_bridge_path = bridge_path or default_bridge_path_for_registry(registry_path)
    server = build_mcp_server(
        RtgFederationToolset(
            registry=registry,
            bridge_store=load_optional_bridge_store(resolved_bridge_path),
            bridge_catalog_path=resolved_bridge_path,
            semantic_generator=(
                None
                if semantic_model is None
                else openai_semantic_generator_from_environment(
                    model=semantic_model,
                    api_key_env=semantic_api_key_env,
                )
            ),
        )
    )
    if transport == "stdio":
        server.run(transport=transport)
        return
    server.run(transport=transport, host=host, port=port, path=path)


def _launch_metadata(
    *,
    registry_path: Path,
    bridge_path: Path | None,
    transport: McpTransport,
    host: str,
    port: int,
    path: str,
    semantic_model: str | None,
    semantic_api_key_env: str,
) -> dict[str, Any]:
    registry_path = registry_path.resolve()
    launch_args = [
        "run",
        "python",
        "-m",
        "apps.rtg_federation",
        "serve-mcp",
        "--transport",
        transport,
        "--registry",
        str(registry_path),
    ]
    if bridge_path is not None:
        launch_args.extend(["--bridges", str(bridge_path.resolve())])
    if semantic_model is not None:
        launch_args.extend(
            [
                "--semantic-model",
                semantic_model,
                "--semantic-api-key-env",
                semantic_api_key_env,
            ]
        )
    if transport == "http":
        launch_args.extend(["--host", host, "--port", str(port), "--path", path])
    launch = {"command": "uv", "args": launch_args}
    if transport == "http":
        client_config = {
            "mcpServers": {
                MCP_SERVER_NAME: {
                    "transport": "http",
                    "url": f"http://{host}:{port}{path}",
                }
            }
        }
    else:
        client_config = {"mcpServers": {MCP_SERVER_NAME: launch}}
    return {"launch": launch, "client_config": client_config}
