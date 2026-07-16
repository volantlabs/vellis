from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from apps.rtg_knowledge_graph.composition import build_app
from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from apps.rtg_knowledge_graph.gateway_registration import model_mcp_gateway_registrations
from apps.rtg_knowledge_graph.mcp_codec import RtgMcpInputInvalid, decode_graph_changes
from apps.rtg_knowledge_graph.mcp_server import build_mcp_server, mcp_dry_run_status
from apps.rtg_knowledge_graph.mcp_toolset import TOOL_NAMES, mcp_tool_metadata
from components.interface.mcp_gateway import McpGatewayInvocation

MODEL_EVIDENCE = {
    "VellisMcpOutcomeContractVerification": (
        "test_mcp_gateway_preserves_success_and_fault_shapes",
    ),
    "VellisMcpBoundaryVerification": (
        "test_mcp_inventory_is_model_generated_and_transport_neutral",
        "test_mcp_gateway_preserves_success_and_fault_shapes",
        "test_mcp_codec_rejects_unknown_mutation_fields",
    ),
}


def test_mcp_inventory_is_model_generated_and_transport_neutral(tmp_path: Path) -> None:
    async def inspect_server() -> None:
        async with await build_app(
            RtgKnowledgeGraphConfig(
                storage_root=tmp_path / "documents",
                runtime_database_path=tmp_path / "runtime.sqlite",
                install_starter_schema=False,
            )
            ) as app:
                tools = await build_mcp_server(app.gateway).list_tools()
                assert {tool.name for tool in tools} == set(TOOL_NAMES)

    asyncio.run(inspect_server())
    registrations = model_mcp_gateway_registrations()
    assert len(registrations) == len(TOOL_NAMES) == 27
    assert {item.tool_name for item in registrations} == set(TOOL_NAMES)
    assert {item["name"] for item in mcp_tool_metadata()} == set(TOOL_NAMES)

    for transport in ("stdio", "http"):
        status = mcp_dry_run_status(
            RtgKnowledgeGraphConfig(
                storage_root=tmp_path / f"{transport}-documents",
                runtime_database_path=tmp_path / f"{transport}.sqlite",
                install_starter_schema=False,
            ),
            transport=transport,
        )
        assert status["mcp"]["transport"] == transport
        assert len(status["mcp"]["tools"]) == 27


def test_mcp_gateway_preserves_success_and_fault_shapes(tmp_path: Path) -> None:
    async def exercise() -> None:
        async with await build_app(
            RtgKnowledgeGraphConfig(
                storage_root=tmp_path / "documents",
                runtime_database_path=tmp_path / "runtime.sqlite",
                install_starter_schema=False,
            )
        ) as app:
            success = await app.gateway.invoke_tool(
                McpGatewayInvocation("rtg_get_system_state", {})
            )
            assert success.result["ok"] is True
            fault = await app.gateway.invoke_tool(
                McpGatewayInvocation("rtg_get_object", {"object_uuid": "not-a-uuid"})
            )
            assert fault.result["ok"] is False
            assert set(fault.result["error"]) >= {"type", "message"}

    asyncio.run(exercise())


def test_mcp_codec_rejects_unknown_mutation_fields() -> None:
    with pytest.raises(RtgMcpInputInvalid):
        decode_graph_changes({"anchors": []})
