from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal, cast

from fastmcp import FastMCP
from fastmcp.tools import Tool, ToolResult
from mcp.types import ToolAnnotations
from pydantic import PrivateAttr

from apps.rtg_knowledge_graph.composition import build_app
from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from apps.rtg_knowledge_graph.mcp_launch import (
    DEFAULT_LOCALHOST_HOST,
    DEFAULT_LOCALHOST_PATH,
    DEFAULT_LOCALHOST_PORT,
    MCP_SERVER_NAME,
    mcp_launch_metadata,
)
from apps.rtg_knowledge_graph.mcp_toolset import mcp_tool_metadata
from components.interface.mcp_gateway import (
    McpGateway,
    McpGatewayInvocation,
    McpGatewayToolRegistration,
)
from components.runtime.message_runtime import JsonObject


class _RuntimeGatewayTool(Tool):
    """FastMCP transport projection of one curated gateway registration."""

    _gateway: McpGateway = PrivateAttr()
    _registration: McpGatewayToolRegistration = PrivateAttr()

    def __init__(
        self,
        gateway: McpGateway,
        registration: McpGatewayToolRegistration,
    ) -> None:
        super().__init__(
            name=registration.tool_name,
            description=registration.description,
            parameters=cast(dict[str, Any], deepcopy(registration.parameter_schema)),
            output_schema=None,
            annotations=ToolAnnotations(**cast(dict[str, Any], registration.annotations)),
        )
        self._gateway = gateway
        self._registration = registration

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        outcome = await self._gateway.invoke_tool(
            McpGatewayInvocation(
                tool_name=self._registration.tool_name,
                arguments=cast(JsonObject, arguments),
            )
        )
        return self.convert_result(cast(dict[str, Any], outcome.result))


def build_mcp_server(gateway: McpGateway) -> FastMCP:
    """Project a curated gateway inventory into an MCP transport server."""

    server = FastMCP(
        MCP_SERVER_NAME,
        instructions=(
            "Read system state first. Use installed schema when present and discover schema "
            "before writing. Dry-run risky changes, use the correct mutation lane, and fetch "
            "usage-guide topics for detailed request shapes."
        ),
    )
    for registration in gateway.registrations:
        server.add_tool(_RuntimeGatewayTool(gateway, registration))
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
    with build_app(config) as composition:
        starter_schema = composition.prepare()
        status = composition.run()
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
    with build_app(config) as composition:
        starter_schema = composition.prepare()
        composition.run()
        server = build_mcp_server(composition.build_mcp_gateway(starter_schema))
        if transport == "stdio":
            server.run(transport=transport)
            return
        server.run(
            transport=transport,
            host=host,
            port=port,
            path=path,
        )
