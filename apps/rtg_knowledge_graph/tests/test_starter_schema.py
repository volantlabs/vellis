from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

import pytest

from apps.rtg_knowledge_graph.composition import build_app
from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from apps.rtg_knowledge_graph.starter_schema import load_starter_schema_bundle
from components.interface.mcp_gateway import McpGatewayInvocation

MODEL_EVIDENCE = {
    "EverydayLifeOntologyVerification": (
        "test_everyday_life_bundle_is_exact_schema_only_and_deterministic",
        "test_starter_ontology_installs_idempotently_and_reconstructs",
        "test_empty_mode_does_not_install_starter_ontology",
    ),
}


def test_everyday_life_bundle_is_exact_schema_only_and_deterministic() -> None:
    first = load_starter_schema_bundle()
    assert first == load_starter_schema_bundle()
    assert first["ontology_id"] == "ontology.vellis.everyday_life"
    assert first["graph_objects"] == []
    UUID(str(first["bootstrap_migration_id"]))
    writes = first["knowledge_changes"]["schema_changes"]["definition_writes"]
    assert len(writes) == 33
    assert {item["definition"]["kind"] for item in writes} == {
        "anchor",
        "data_object",
        "link",
    }


@pytest.mark.integration
def test_starter_ontology_installs_idempotently_and_reconstructs(tmp_path: Path) -> None:
    async def exercise() -> None:
        config = RtgKnowledgeGraphConfig(
            storage_root=tmp_path / "documents",
            runtime_database_path=tmp_path / "runtime.sqlite",
        )
        first = await build_app(config)
        try:
            assert (await first.prepare()).status == "installed"
            snapshot = await first.gateway.invoke_tool(
                McpGatewayInvocation("rtg_export_system_snapshot", {"summary": True})
            )
            assert snapshot.result["ok"] is True
        finally:
            await first.close()

        restarted = await build_app(config)
        try:
            assert restarted.runtime_services.startup_reconstruction is not None
            assert restarted.runtime_services.startup_reconstruction.applied_effects > 0
            assert (await restarted.prepare()).status == "installed"
            validation = await restarted.gateway.invoke_tool(
                McpGatewayInvocation("rtg_validate_graph", {})
            )
            assert validation.result["result"]["accepted"] is True
        finally:
            await restarted.close()

    asyncio.run(exercise())


@pytest.mark.integration
def test_empty_mode_does_not_install_starter_ontology(tmp_path: Path) -> None:
    async def exercise() -> None:
        async with await build_app(
            RtgKnowledgeGraphConfig(
                storage_root=tmp_path / "documents",
                runtime_database_path=tmp_path / "runtime.sqlite",
                install_starter_schema=False,
            )
        ) as app:
            assert (await app.prepare()).status == "empty"

    asyncio.run(exercise())
