from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from apps.rtg_knowledge_graph import main as app_main
from apps.rtg_knowledge_graph.composition import build_app
from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from apps.rtg_knowledge_graph.gateway_registration import (
    model_application_manifest,
    model_mcp_gateway_registrations,
    model_runtime_topology_manifest,
)
from apps.rtg_knowledge_graph.mcp_toolset import TOOL_NAMES
from components.interface.mcp_gateway import McpGatewayInvocation, RuntimeMcpGateway
from components.runtime.message_runtime import RuntimeHealth, RuntimeHistoryQuery

pytestmark = pytest.mark.integration

MODEL_EVIDENCE = {
    "RunRtgKnowledgeGraphContractVerification": (
        "test_composed_app_runs_and_writes_manifest",
        "test_manual_recovery_startup_defers_runner_component_calls",
    ),
    "VellisCompositionVerification": (
        "test_composed_app_runs_and_writes_manifest",
        "test_cli_runs_full_app",
        "test_manual_recovery_startup_defers_runner_component_calls",
        "test_effect_free_indeterminate_read_still_gates_restart_recovery",
    ),
    "VellisRuntimeCompositionVerification": (
        "test_runtime_composition_manifest_and_curated_gateway",
        "test_snapshot_transfer_starts_a_fresh_runtime_chronology",
        "test_restart_reconstructs_message_native_component_state",
    ),
}


def test_runtime_composition_manifest_and_curated_gateway(tmp_path: Path) -> None:
    async def exercise() -> None:
        config = RtgKnowledgeGraphConfig(
            storage_root=tmp_path / "documents",
            runtime_database_path=tmp_path / "runtime.sqlite",
            install_starter_schema=False,
        )
        async with await build_app(config) as app:
            outcome = await app.gateway.invoke_tool(
                McpGatewayInvocation("rtg_get_system_state", {})
            )
            assert outcome.result["ok"] is True
            trace = await app.runtime.get_trace(outcome.trace_id, include_payload=True)
            delivered = {
                fact.instance_key for fact in trace.facts if fact.fact_type == "delivery_started"
            }
            assert {"vellis.facade.primary", "vellis.controller.primary"} <= delivered
            roots = [
                fact.envelope
                for fact in trace.facts
                if fact.fact_type == "message_accepted"
                and fact.envelope is not None
                and fact.envelope.causation_id is None
            ]
            assert len(roots) == 1
            assert roots[0].source == app.runtime.address_for("vellis.interface.mcp")
            internal = next(
                fact.message_id
                for fact in trace.facts
                if fact.fact_type == "message_accepted"
                and fact.message_id is not None
                and fact.envelope is not None
                and fact.envelope.kind.value == "request"
                and fact.message_id != roots[0].message_id
            )
            denied = await app.gateway.invoke_tool(
                McpGatewayInvocation(
                    "rtg_get_operation_outcome",
                    {"message_id": str(internal)},
                )
            )
            assert denied.result["ok"] is False

            await app.gateway.invoke_tool(
                McpGatewayInvocation(
                    "rtg_export_system_snapshot",
                    {"runtime_options": {"request_key": "state-transfer-observation"}},
                )
            )
            withheld = await app.gateway.invoke_tool(
                McpGatewayInvocation(
                    "rtg_get_operation_outcome",
                    {"request_key": "state-transfer-observation"},
                )
            )
            assert withheld.result["result"]["payload_withheld"] is True
            assert "outcome" not in withheld.result["result"]
            included = await app.gateway.invoke_tool(
                McpGatewayInvocation(
                    "rtg_get_operation_outcome",
                    {
                        "request_key": "state-transfer-observation",
                        "include_state_transfer": True,
                    },
                )
            )
            assert "outcome" in included.result["result"]

        manifest = model_application_manifest()
        assert manifest["schema_version"] == 4
        assert len(manifest["occurrences"]) == 12
        assert len(manifest["tools"]) == len(TOOL_NAMES) == 27
        assert all(item["lanes"] for item in manifest["occurrences"])
        assert not any("component_kind" in item for item in manifest["occurrences"])
        gateway = RuntimeMcpGateway(model_mcp_gateway_registrations())
        assert gateway.seal() == model_runtime_topology_manifest().curated_registration_digest

    asyncio.run(exercise())


def test_composed_app_runs_and_writes_manifest(tmp_path: Path) -> None:
    async def exercise() -> None:
        config = RtgKnowledgeGraphConfig(
            storage_root=tmp_path / "documents",
            runtime_database_path=tmp_path / "runtime.sqlite",
            install_starter_schema=False,
        )
        async with await build_app(config) as app:
            status = await app.run()
            assert status.rtg_controller_ready
            document = json.loads(
                (config.storage_root / status.manifest_path).read_text(encoding="utf-8")
            )
            assert document["schema_version"] == 4
            assert document["runtime"]["runtime_key"] == "vellis.rtg_knowledge_graph"

    asyncio.run(exercise())


def test_snapshot_transfer_starts_a_fresh_runtime_chronology(tmp_path: Path) -> None:
    async def exercise() -> None:
        source_config = RtgKnowledgeGraphConfig(
            storage_root=tmp_path / "source-documents",
            runtime_database_path=tmp_path / "source.sqlite",
        )
        async with await build_app(source_config) as source:
            await source.prepare()
            exported = await source.gateway.invoke_tool(
                McpGatewayInvocation("rtg_export_system_snapshot", {})
            )
            snapshot = dict(exported.result["result"])
            snapshot.pop("kind")
            source_runtime_id = source.runtime.runtime_id

        destination_config = RtgKnowledgeGraphConfig(
            storage_root=tmp_path / "destination-documents",
            runtime_database_path=tmp_path / "destination.sqlite",
            install_starter_schema=False,
        )
        async with await build_app(destination_config) as destination:
            assert destination.runtime.runtime_id != source_runtime_id
            restored = await destination.gateway.invoke_tool(
                McpGatewayInvocation("rtg_restore_from_snapshot", {"snapshot": snapshot})
            )
            assert restored.result["ok"] is True
            validation = await destination.gateway.invoke_tool(
                McpGatewayInvocation("rtg_validate_graph", {})
            )
            assert validation.result["result"]["accepted"] is True
            legacy = await destination.runtime.query_history(
                RuntimeHistoryQuery(fact_type="legacy_import", limit=1)
            )
            assert not legacy.facts

        async with await build_app(destination_config) as restarted:
            report = restarted.runtime_services.startup_reconstruction
            assert report is not None and report.verified and report.applied_effects > 0
            validation = await restarted.gateway.invoke_tool(
                McpGatewayInvocation("rtg_validate_graph", {})
            )
            assert validation.result["result"]["accepted"] is True

    asyncio.run(exercise())


def test_restart_reconstructs_message_native_component_state(tmp_path: Path) -> None:
    async def exercise() -> None:
        config = RtgKnowledgeGraphConfig(
            storage_root=tmp_path / "documents",
            runtime_database_path=tmp_path / "runtime.sqlite",
        )
        first = await build_app(config)
        try:
            assert (await first.prepare()).status == "installed"
        finally:
            await first.close()
        restarted = await build_app(config)
        try:
            report = restarted.runtime_services.startup_reconstruction
            assert report is not None and report.verified and report.applied_effects > 0
            assert (await restarted.prepare()).status == "installed"
        finally:
            await restarted.close()

    asyncio.run(exercise())


def test_manual_recovery_startup_defers_runner_component_calls(tmp_path: Path) -> None:
    async def exercise() -> None:
        ready_config = RtgKnowledgeGraphConfig(
            storage_root=tmp_path / "documents",
            runtime_database_path=tmp_path / "runtime.sqlite",
        )
        first = await build_app(ready_config)
        await first.prepare()
        await first.close()

        manual = await build_app(
            RtgKnowledgeGraphConfig(
                storage_root=ready_config.storage_root,
                runtime_database_path=ready_config.runtime_database_path,
                automatic_recovery=False,
            )
        )
        try:
            before = await manual.runtime.query_history(
                RuntimeHistoryQuery(
                    instance_key="vellis.runner.local", fact_type="message_accepted"
                )
            )
            status = await manual.run()
            after = await manual.runtime.query_history(
                RuntimeHistoryQuery(
                    instance_key="vellis.runner.local", fact_type="message_accepted"
                )
            )
            assert not status.rtg_controller_ready
            assert after.facts == before.facts
        finally:
            await manual.close()

    asyncio.run(exercise())


def test_effect_free_indeterminate_read_still_gates_restart_recovery(tmp_path: Path) -> None:
    async def exercise() -> None:
        config = RtgKnowledgeGraphConfig(
            storage_root=tmp_path / "documents",
            runtime_database_path=tmp_path / "runtime.sqlite",
            install_starter_schema=False,
        )
        first = await build_app(config)
        outcome = await first.gateway.invoke_tool(McpGatewayInvocation("rtg_get_system_state", {}))
        trace = await first.runtime.get_trace(outcome.trace_id, include_payload=True)
        root = next(
            fact.envelope
            for fact in trace.facts
            if fact.fact_type == "message_accepted"
            and fact.envelope is not None
            and fact.envelope.causation_id is None
        )
        await first.close()

        connection = sqlite3.connect(config.runtime_database_path)
        with connection:
            connection.execute(
                "UPDATE runtime_messages SET status = 'delivering', terminal_position = NULL, "
                "trace_disposition = NULL WHERE message_id = ?",
                (str(root.message_id),),
            )
        connection.close()

        manual = await build_app(replace(config, automatic_recovery=False))
        try:
            assert manual.runtime.health is RuntimeHealth.RECOVERY_REQUIRED
            status = await manual.run()
            assert status.rtg_controller_ready is False
        finally:
            await manual.close()

    asyncio.run(exercise())


def test_cli_runs_full_app(tmp_path: Path, capsys) -> None:
    result = app_main.main(
        [
            "--storage-root",
            str(tmp_path / "documents"),
            "--runtime-database-path",
            str(tmp_path / "runtime.sqlite"),
            "--empty",
            "--json",
        ]
    )
    assert result == 0
    assert json.loads(capsys.readouterr().out)["rtg_controller_ready"] is True
