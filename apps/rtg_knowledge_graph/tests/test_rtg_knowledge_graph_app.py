from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

from apps.rtg_knowledge_graph import composition as app_composition
from apps.rtg_knowledge_graph import main as app_main
from apps.rtg_knowledge_graph import mcp_launch
from apps.rtg_knowledge_graph.composition import build_app
from apps.rtg_knowledge_graph.config import (
    DEFAULT_RUNTIME_DATABASE_PATH,
    DEFAULT_STORAGE_ROOT,
    RUNTIME_DATABASE_PATH_ENV_VAR,
    STORAGE_ROOT_ENV_VAR,
    RtgKnowledgeGraphConfig,
)
from apps.rtg_knowledge_graph.mcp_toolset import TOOL_NAMES, VellisRequestInvalid
from apps.rtg_knowledge_graph.runtime_binding import create_vellis_facade_adapter
from components.interface.mcp_gateway import McpGatewayInvocation
from components.rtg.change_validation import (
    DeterministicRtgChangeValidator,
    RtgValidationFinding,
    RtgValidationOptions,
    RtgValidationReport,
)
from components.rtg.controller import (
    RtgControllerPreconditionFailed,
    RtgControllerRecoveryIndeterminate,
    RtgControllerValidationFailed,
)
from components.rtg.migration import RtgMigrationNotFound
from components.runtime.component_adapter.implementation import encode_json
from components.runtime.message_runtime import (
    JsonObject,
    RuntimeHistoryQuery,
    RuntimeMessageKind,
    RuntimeTraceDisposition,
)

MODEL_EVIDENCE = {
    "VellisCompositionVerification": (
        "test_config_uses_default_storage_root_relative_to_cwd",
        "test_config_uses_env_storage_root",
        "test_composed_app_runs_and_writes_manifest",
        "test_persisted_manifest_preserves_configured_startup_modes",
        "test_cli_runs_full_app",
        "test_cli_reports_mcp_dry_run_metadata",
        "test_cli_prints_focused_stdio_client_config_without_initializing_app",
        "test_cli_prints_focused_http_client_config",
        "test_cli_prints_exact_codex_stdio_registration_command",
        "test_cli_prints_exact_codex_http_registration_command",
        "test_cli_help_explains_both_first_run_client_paths",
        "test_cli_treats_mcp_keyboard_interrupt_as_clean_shutdown",
        "test_powershell_quoting_preserves_paths_and_embedded_quotes",
        "test_cli_reports_custom_http_mcp_dry_run_metadata",
        "test_mcp_launch_metadata_has_installed_package_fallback",
    ),
    "VellisRuntimeCompositionVerification": (
        "test_runtime_composition_manifest_and_curated_gateway",
        "test_vellis_facade_binding_failures_match_accepted_model",
        "test_runtime_facade_preserves_modeled_controller_and_collaborator_faults",
        "test_snapshot_transfer_starts_a_fresh_runtime_chronology",
        "test_failed_cutover_status_is_committed_and_reconstructed",
    ),
}


class _TogglePostCutoverValidator(DeterministicRtgChangeValidator):
    def __init__(self) -> None:
        self.reject_actual_state = False

    def validate_graph_state(
        self,
        graph: object,
        schema: object,
        constraints: object,
        migration: object | None,
        query: object,
        migration_ids: tuple[str, ...] | None = None,
        validation_options: RtgValidationOptions | None = None,
    ) -> RtgValidationReport:
        if not self.reject_actual_state:
            return super().validate_graph_state(
                graph,
                schema,
                constraints,
                migration,
                query,
                migration_ids,
                validation_options,
            )
        return RtgValidationReport(
            accepted=False,
            findings=(
                RtgValidationFinding(
                    track="schema_object",
                    severity="blocking",
                    code="test.post_cutover_rejected",
                    message="post-cutover state rejected",
                ),
            ),
        )


def test_runtime_composition_manifest_and_curated_gateway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mcp_launch, "_uv_command", lambda: "uv")
    opened_collaborators: list[tuple[object, ...]] = []
    original_open = app_composition.InProcessRtgController.open

    def audited_open(cls: type[object], *collaborators: object, **options: object) -> object:
        del cls
        assert len(collaborators) == 7
        assert all(_is_runtime_proxy(item) for item in collaborators)
        assert options == {}
        opened_collaborators.append(collaborators)
        return cast(Any, original_open)(*collaborators, **options)

    monkeypatch.setattr(
        app_composition.InProcessRtgController,
        "open",
        classmethod(audited_open),
    )
    config = RtgKnowledgeGraphConfig(
        storage_root=tmp_path / "storage",
        runtime_database_path=tmp_path / "runtime.sqlite",
        install_starter_schema=False,
    )
    with build_app(config) as composition:
        starter = composition.prepare()
        composition.controller.get_system_state()
        starter_source = composition.runtime.address_for(
            "vellis.starter_ontology.installer"
        )
        setup_calls = composition.runtime.query_history_sync(
            RuntimeHistoryQuery(
                action_id="component.rtg.controller.get_system_state",
                fact_type="message_accepted",
                limit=100,
            )
        ).facts
        assert setup_calls
        assert all(
            fact.envelope is not None and fact.envelope.source == starter_source
            for fact in setup_calls
        )
        status = composition.runner.run()
        gateway = composition.build_mcp_gateway(starter)
        outcome = gateway.invoke_tool_sync(
            McpGatewayInvocation(tool_name="rtg_get_system_state", arguments={})
        )
        validation = gateway.invoke_tool_sync(
            McpGatewayInvocation(
                tool_name="rtg_validate_graph",
                arguments={"migration_ids": None, "validation_options": None},
            )
        )

        assert outcome.result["ok"] is True
        assert validation.result["ok"] is True
        assert len(opened_collaborators) == 1
        assert _is_runtime_proxy(composition.controller)
        assert _is_runtime_proxy(composition._starter_controller)
        assert _is_runtime_proxy(composition.runner._controller)
        assert _is_runtime_proxy(composition.runner._document_storage)
        facts = composition.runtime.query_history_sync(
            RuntimeHistoryQuery(
                trace_id=outcome.trace_id,
                action_id="application.vellis.facade.rtg_get_system_state",
            )
        ).facts
        assert facts[0].fact_type == "message_accepted"
        assert facts[-1].fact_type == "trace_committed"

        manifest = json.loads(
            (config.storage_root / status.manifest_path).read_text(encoding="utf-8")
        )

    occurrence_keys = {item["instance_key"] for item in manifest["occurrences"]}
    assert occurrence_keys == {
        "vellis.graph.primary",
        "vellis.schema.primary",
        "vellis.constraints.primary",
        "vellis.migration.primary",
        "vellis.storage.json.primary",
        "vellis.query.primary",
        "vellis.validation.primary",
        "vellis.controller.primary",
        "vellis.facade.primary",
        "vellis.interface.mcp",
        "vellis.starter_ontology.installer",
        "vellis.runner.local",
    }
    assert manifest["runtime"]["runtime_key"] == "vellis.rtg_knowledge_graph"
    canonical = dict(manifest)
    digest = canonical.pop("manifest_hash")
    canonical.pop("interfaces")
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    assert digest == hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    assert config.runtime_database_path.exists()

    gateway_source = Path("components/interface/mcp_gateway/implementation.py").read_text(
        encoding="utf-8"
    )
    assert "components.rtg" not in gateway_source
    transport_source = Path("apps/rtg_knowledge_graph/mcp_server.py").read_text(
        encoding="utf-8"
    )
    assert "RtgMcpToolset" not in transport_source
    assert "def rtg_" not in transport_source
    assert "components.rtg" not in transport_source
    controller_replay_source = inspect.getsource(
        app_composition._controller_replay_binding
    )
    assert ".resolve()" not in controller_replay_source
    assert all(
        f"{name}_proxy.export_snapshot()" in controller_replay_source
        for name in ("graph", "schema", "constraints", "migration")
    )


def test_vellis_facade_binding_failures_match_accepted_model(tmp_path: Path) -> None:
    config = RtgKnowledgeGraphConfig(
        storage_root=tmp_path / "storage",
        runtime_database_path=tmp_path / "runtime.sqlite",
        install_starter_schema=False,
    )
    with build_app(config) as composition:
        actions = create_vellis_facade_adapter(
            composition._facade_host
        ).describe().actions

    model = (
        Path(__file__).resolve().parents[3] / "model/vellis/VellisOperations.sysml"
    ).read_text(encoding="utf-8")
    assert tuple(action.action_id.rsplit(".", 1)[-1] for action in actions) == TOOL_NAMES
    for action in actions:
        tool_name = action.action_id.rsplit(".", 1)[-1]
        definition = re.search(
            rf"\baction def\s+<'operation\.vellis\.{re.escape(tool_name)}'>\s+\w+\s*\{{"
            r"(?P<body>.*?)@FailureContract\s*\{(?P<contract>.*?)\}",
            model,
            flags=re.DOTALL,
        )
        assert definition is not None, tool_name
        error_ids = re.search(
            r"\berrorIds\s*=\s*\((?P<values>.*?)\)",
            definition.group("contract"),
            flags=re.DOTALL,
        )
        assert error_ids is not None, tool_name
        modeled = tuple(re.findall(r'"([^"]+)"', error_ids.group("values")))
        assert action.supported_failure_names == modeled


def test_snapshot_transfer_starts_a_fresh_runtime_chronology(tmp_path: Path) -> None:
    source_config = RtgKnowledgeGraphConfig(
        storage_root=tmp_path / "source" / "storage",
        runtime_database_path=tmp_path / "source" / "runtime.sqlite",
    )
    with build_app(source_config) as source:
        source.prepare()
        expected_snapshot = source.controller.export_system_snapshot()
        encoded_snapshot = encode_json(expected_snapshot)
    assert isinstance(encoded_snapshot, dict)
    transfer_snapshot = {
        **encoded_snapshot,
        "transaction_id": "discarded-source-trace",
        "ledger_position": 1234,
        "legacy_controller_metadata": {"source": "pre-runtime"},
    }

    destination_config = RtgKnowledgeGraphConfig(
        storage_root=tmp_path / "destination" / "storage",
        runtime_database_path=tmp_path / "destination" / "runtime.sqlite",
        install_starter_schema=False,
    )
    with build_app(destination_config) as destination:
        empty = destination.prepare()
        assert not destination.runtime.query_history_sync(
            RuntimeHistoryQuery(fact_type="canonical_effect")
        ).facts

        result = destination.build_facade(empty).rtg_restore_from_snapshot(transfer_snapshot)

        assert result["ok"] is True
        roots = destination.runtime.query_history_sync(
            RuntimeHistoryQuery(
                fact_type="message_accepted",
                action_id="application.vellis.facade.rtg_restore_from_snapshot",
            )
        ).facts
        trace_id = roots[-1].trace_id
        assert trace_id is not None
        trace = destination.runtime.get_trace_sync(trace_id)
        accepted_actions = {
            fact.action_id for fact in trace.facts if fact.fact_type == "message_accepted"
        }
        assert {
            "component.rtg.graph.replace_snapshot",
            "component.rtg.schema.replace_snapshot",
            "component.rtg.constraints.replace_snapshot",
            "component.rtg.migration.replace_snapshot",
            "component.rtg.change_validation.validate_graph_state",
        }.issubset(accepted_actions)
        effects = destination.runtime.query_history_sync(
            RuntimeHistoryQuery(trace_id=trace_id, fact_type="canonical_effect")
        ).facts
        assert {item.instance_key for item in effects} == {
            "vellis.graph.primary",
            "vellis.schema.primary",
            "vellis.constraints.primary",
            "vellis.migration.primary",
            "vellis.controller.primary",
        }
        controller_effect = next(
            item for item in effects if item.instance_key == "vellis.controller.primary"
        )
        assert controller_effect.runtime_position == max(
            item.runtime_position for item in effects
        )
        effect = controller_effect.details["effect"]
        assert isinstance(effect, dict)
        payload = effect["payload"]
        assert isinstance(payload, dict)
        assert payload["supersedes_trace_effects"] is True
        arguments = payload["arguments"]
        assert isinstance(arguments, dict)
        restored_snapshot = arguments["snapshot"]
        assert isinstance(restored_snapshot, dict)
        assert "transaction_id" not in restored_snapshot
        assert "ledger_position" not in restored_snapshot
        assert "legacy_controller_metadata" not in restored_snapshot
        accepted_before_restart = len(
            destination.runtime.query_history_sync(
                RuntimeHistoryQuery(fact_type="message_accepted", limit=1000)
            ).facts
        )

    with build_app(destination_config) as restarted:
        reconstruction = restarted.runtime_services.startup_reconstruction
        assert reconstruction is not None
        assert reconstruction.verified
        assert reconstruction.skipped_effects >= 4
        assert len(
            restarted.runtime.query_history_sync(
                RuntimeHistoryQuery(fact_type="message_accepted", limit=1000)
            ).facts
        ) == accepted_before_restart
        assert restarted.controller.export_system_snapshot() == expected_snapshot


def test_runtime_facade_preserves_modeled_controller_and_collaborator_faults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = RtgKnowledgeGraphConfig(
        storage_root=tmp_path / "storage",
        runtime_database_path=tmp_path / "runtime.sqlite",
        install_starter_schema=False,
    )
    with build_app(config) as composition:
        starter = composition.prepare()
        facade = composition.build_facade(starter)

        with pytest.raises(RtgMigrationNotFound):
            facade.rtg_get_migration("missing")
        with pytest.raises(RtgControllerPreconditionFailed):
            facade.rtg_apply_migration_cutover("missing")
        with pytest.raises(RtgControllerPreconditionFailed):
            facade.rtg_apply_migration_cutover(
                "missing",
                {"validation_mode": "invalid"},
            )
        with pytest.raises(VellisRequestInvalid):
            facade.rtg_get_usage_guide("not-a-topic")

        for action_id in (
            "application.vellis.facade.rtg_get_migration",
            "application.vellis.facade.rtg_apply_migration_cutover",
            "application.vellis.facade.rtg_get_usage_guide",
        ):
            accepted = composition.runtime.query_history_sync(
                RuntimeHistoryQuery(
                    action_id=action_id,
                    fact_type="message_accepted",
                    limit=100,
                )
            ).facts
            assert accepted
            for root in accepted:
                assert root.trace_id is not None
                trace = composition.runtime.get_trace_sync(root.trace_id)
                assert trace.disposition is RuntimeTraceDisposition.ABORTED
                facade_faults = [
                    fact
                    for fact in trace.facts
                    if fact.fact_type == "fault_recorded" and fact.action_id == action_id
                ]
                assert len(facade_faults) == 1
                assert facade_faults[0].envelope is not None
                assert facade_faults[0].envelope.kind is RuntimeMessageKind.FAULT

        gateway = composition.build_mcp_gateway(starter)
        external = gateway.invoke_tool_sync(
            McpGatewayInvocation(
                tool_name="rtg_get_migration",
                arguments={"migration_id": "missing"},
            )
        )
        external_error = cast(dict[str, object], external.result["error"])
        assert external.result["ok"] is False
        assert external_error["type"] == "RtgMigrationNotFound"
        assert (
            composition.runtime.get_trace_sync(external.trace_id).disposition
            is RuntimeTraceDisposition.ABORTED
        )
        assert not composition.runtime.query_history_sync(
            RuntimeHistoryQuery(fact_type="trace_indeterminate", limit=100)
        ).facts

        snapshot = composition.controller.export_system_snapshot()

        def indeterminate_restore(*_args: object, **_kwargs: object) -> object:
            raise RtgControllerRecoveryIndeterminate("compensation could not be confirmed")

        monkeypatch.setattr(
            app_composition.InProcessRtgController,
            "restore_from_snapshot",
            indeterminate_restore,
        )
        uncertain = gateway.invoke_tool_sync(
            McpGatewayInvocation(
                tool_name="rtg_restore_from_snapshot",
                arguments=cast(JsonObject, {"snapshot": encode_json(snapshot)}),
            )
        )
        uncertain_error = cast(dict[str, object], uncertain.result["error"])
        assert uncertain.result["ok"] is False
        assert uncertain_error["type"] == "RtgControllerRecoveryIndeterminate"
        assert (
            composition.runtime.get_trace_sync(uncertain.trace_id).disposition
            is RuntimeTraceDisposition.INDETERMINATE
        )
        assert composition.runtime.health == "recovery_required"


def test_failed_cutover_status_is_committed_and_reconstructed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validator = _TogglePostCutoverValidator()
    monkeypatch.setattr(
        app_composition,
        "DeterministicRtgChangeValidator",
        lambda: validator,
    )
    config = RtgKnowledgeGraphConfig(
        storage_root=tmp_path / "storage",
        runtime_database_path=tmp_path / "runtime.sqlite",
    )
    migration_id = "runtime-failed-cutover"

    with build_app(config) as original:
        facade = original.build_facade(original.prepare())
        staged = facade.rtg_stage_schema_migration(
            migration_id,
            "Exercise intentional failed-cutover reconstruction.",
            [
                {
                    "kind": "anchor",
                    "type_key": "RuntimeFailureProbe",
                    "description": "A non-live candidate used only by this regression test.",
                    "payload": {"required_data_types": []},
                }
            ],
            validation_mode="skip",
        )
        assert staged["ok"] is True

        validator.reject_actual_state = True
        with pytest.raises(RtgControllerValidationFailed):
            facade.rtg_apply_migration_cutover(migration_id)

        accepted = original.runtime.query_history_sync(
            RuntimeHistoryQuery(
                action_id="component.rtg.controller.apply_migration_cutover",
                fact_type="message_accepted",
            )
        ).facts
        failed_trace_id = accepted[-1].trace_id
        assert failed_trace_id is not None
        assert (
            original.runtime.get_trace_sync(failed_trace_id).disposition
            is RuntimeTraceDisposition.COMMITTED
        )
        failure_effects = original.runtime.query_history_sync(
            RuntimeHistoryQuery(
                trace_id=failed_trace_id,
                action_id="component.rtg.controller.apply_migration_cutover",
                fact_type="canonical_effect",
            )
        ).facts
        assert len(failure_effects) == 1
        failure_effect = failure_effects[0].details["effect"]
        assert isinstance(failure_effect, dict)
        failure_payload = failure_effect["payload"]
        assert isinstance(failure_payload, dict)
        assert failure_payload["supersedes_trace_effects"] is True
        assert original.controller.get_migration(migration_id).status == "failed"
        expected_state = original.controller.export_system_snapshot()

    validator.reject_actual_state = False
    with build_app(config) as restarted:
        reconstruction = restarted.runtime_services.startup_reconstruction
        assert reconstruction is not None
        assert reconstruction.verified
        assert reconstruction.skipped_effects > 0
        assert restarted.controller.get_migration(migration_id).status == "failed"
        assert restarted.controller.export_system_snapshot() == expected_state


def _is_runtime_proxy(value: object) -> bool:
    return bool(getattr(value, "_bibliotek_runtime_proxy", False)) or type(
        value
    ).__module__.endswith(".runtime_binding")


def test_config_uses_default_storage_root_relative_to_cwd(tmp_path: Path) -> None:
    config = RtgKnowledgeGraphConfig.from_env(env={}, cwd=tmp_path)

    assert config.storage_root == tmp_path / DEFAULT_STORAGE_ROOT
    assert config.runtime_database_path == tmp_path / DEFAULT_RUNTIME_DATABASE_PATH


def test_config_uses_env_storage_root(tmp_path: Path) -> None:
    configured = tmp_path / "configured-storage"
    config = RtgKnowledgeGraphConfig.from_env(
        env={
            STORAGE_ROOT_ENV_VAR: str(configured),
            RUNTIME_DATABASE_PATH_ENV_VAR: str(tmp_path / "configured.sqlite"),
        },
        cwd=tmp_path / "ignored",
    )

    assert config.storage_root == configured
    assert config.runtime_database_path == tmp_path / "configured.sqlite"


def test_composed_app_runs_and_writes_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mcp_launch, "_uv_command", lambda: "uv")
    config = RtgKnowledgeGraphConfig(
        storage_root=tmp_path / "storage",
        runtime_database_path=tmp_path / "runtime.sqlite",
    )
    composition = build_app(config)

    status = composition.runner.run()

    assert status.app_name == "rtg_knowledge_graph"
    assert status.manifest_path == "system/app_manifest.json"
    assert status.json_document_count == 1
    assert status.rtg_controller_ready is True

    manifest_path = config.storage_root / status.manifest_path
    with manifest_path.open("r", encoding="utf-8") as file:
        manifest = json.load(file)

    dependency_ids = {item["id"] for item in manifest["component_dependencies"]}
    assert dependency_ids == {
        "component.storage.json_file",
        "component.rtg.controller",
        "component.rtg.graph",
        "component.rtg.schema",
        "component.rtg.constraints",
        "component.rtg.migration",
        "component.rtg.change_validation",
        "component.rtg.query",
    }
    assert manifest["interfaces"] == [
        {
            "kind": "mcp",
            "server_name": "rtg_knowledge_graph",
            "transport": "stdio",
            "launch_mode": "repository_checkout",
            "state_mode": "durable_local_auto_replay",
            "eval_prompt_path": str(
                Path("docs/guides/vellis/evals/rtg-individual-life-graph-beta-prompt.md").resolve()
            ),
            "recommended_eval_prompt": "individual_life_graph",
            "eval_prompts": {
                "individual_life_graph": {
                    "title": "RTG Individual Life Graph Beta Prompt",
                    "path": str(
                        Path(
                            "docs/guides/vellis/evals/rtg-individual-life-graph-beta-prompt.md"
                        ).resolve()
                    ),
                    "description": (
                        "Initial single-user personal and professional life-graph beta scenario."
                    ),
                    "available": True,
                    "recommended": True,
                },
                "component_repo_affordance": {
                    "title": "RTG Agent Affordance Eval Prompt",
                    "path": str(
                        Path(
                            "docs/guides/vellis/evals/rtg-agent-affordance-eval-prompt.md"
                        ).resolve()
                    ),
                    "description": "Software-component repository modeling scenario.",
                    "available": True,
                    "recommended": False,
                },
            },
            "guides": {
                "known_good_walkthrough": {
                    "title": "RTG Beta Known-Good Walkthrough",
                    "path": str(
                        Path(
                            "docs/guides/vellis/evals/rtg-beta-known-good-walkthrough.md"
                        ).resolve()
                    ),
                    "description": "Expected shape of a successful first life-graph beta run.",
                    "available": True,
                },
            },
            "first_call": {
                "tool": "rtg_validate_graph",
                "arguments": {},
                "expected": {
                    "ok": True,
                    "result.accepted": True,
                    "result.findings": [],
                },
                "purpose": (
                    "Confirm the MCP client is connected to a valid recovered RTG controller."
                ),
            },
            "transports": {
                "stdio": {
                    "launch": {
                        "command": "uv",
                        "args": [
                            "--directory",
                            str(Path(".").resolve()),
                            "run",
                            "python",
                            "-m",
                            "apps.rtg_knowledge_graph",
                            "serve-mcp",
                            "--transport",
                            "stdio",
                            "--storage-root",
                            str((tmp_path / "storage").resolve()),
                            "--runtime-database-path",
                            str((tmp_path / "runtime.sqlite").resolve()),
                        ],
                        "cwd": str(Path(".").resolve()),
                    },
                    "client_config": {
                        "mcpServers": {
                            "rtg_knowledge_graph": {
                                "command": "uv",
                                "args": [
                                    "--directory",
                                    str(Path(".").resolve()),
                                    "run",
                                    "python",
                                    "-m",
                                    "apps.rtg_knowledge_graph",
                                    "serve-mcp",
                                    "--transport",
                                    "stdio",
                                    "--storage-root",
                                    str((tmp_path / "storage").resolve()),
                                    "--runtime-database-path",
                                    str((tmp_path / "runtime.sqlite").resolve()),
                                ],
                                "cwd": str(Path(".").resolve()),
                            }
                        }
                    },
                },
                "localhost_http": {
                    "url": "http://127.0.0.1:8765/mcp",
                    "transport": "http",
                    "host": "127.0.0.1",
                    "port": 8765,
                    "path": "/mcp",
                    "auth": "none",
                    "network_scope": "localhost",
                    "launch": {
                        "command": "uv",
                        "args": [
                            "--directory",
                            str(Path(".").resolve()),
                            "run",
                            "python",
                            "-m",
                            "apps.rtg_knowledge_graph",
                            "serve-mcp",
                            "--transport",
                            "http",
                            "--host",
                            "127.0.0.1",
                            "--port",
                            "8765",
                            "--path",
                            "/mcp",
                            "--storage-root",
                            str((tmp_path / "storage").resolve()),
                            "--runtime-database-path",
                            str((tmp_path / "runtime.sqlite").resolve()),
                        ],
                        "cwd": str(Path(".").resolve()),
                    },
                    "client_config": {
                        "mcpServers": {
                            "rtg_knowledge_graph": {
                                "url": "http://127.0.0.1:8765/mcp",
                                "transport": "http",
                            }
                        }
                    },
                },
            },
            "launch": {
                "command": "uv",
                "args": [
                    "--directory",
                    str(Path(".").resolve()),
                    "run",
                    "python",
                    "-m",
                    "apps.rtg_knowledge_graph",
                    "serve-mcp",
                    "--transport",
                    "stdio",
                    "--storage-root",
                    str((tmp_path / "storage").resolve()),
                    "--runtime-database-path",
                    str((tmp_path / "runtime.sqlite").resolve()),
                ],
                "cwd": str(Path(".").resolve()),
            },
            "client_config": {
                "mcpServers": {
                    "rtg_knowledge_graph": {
                        "command": "uv",
                        "args": [
                            "--directory",
                            str(Path(".").resolve()),
                            "run",
                            "python",
                            "-m",
                            "apps.rtg_knowledge_graph",
                            "serve-mcp",
                            "--transport",
                            "stdio",
                            "--storage-root",
                            str((tmp_path / "storage").resolve()),
                            "--runtime-database-path",
                            str((tmp_path / "runtime.sqlite").resolve()),
                        ],
                        "cwd": str(Path(".").resolve()),
                    }
                }
            },
        }
    ]


def test_persisted_manifest_preserves_configured_startup_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mcp_launch, "_uv_command", lambda: "uv")
    config = RtgKnowledgeGraphConfig(
        storage_root=tmp_path / "storage",
        runtime_database_path=tmp_path / "runtime.sqlite",
        install_starter_schema=False,
        automatic_recovery=False,
    )

    status = build_app(config).runner.run()
    manifest = json.loads((config.storage_root / status.manifest_path).read_text(encoding="utf-8"))
    interface = manifest["interfaces"][0]

    assert interface["state_mode"] == "manual_recovery"
    assert "--empty" in interface["launch"]["args"]
    assert "--manual-recovery" in interface["launch"]["args"]


def test_cli_runs_full_app(tmp_path: Path) -> None:
    storage_root = tmp_path / "cli-storage"

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "apps.rtg_knowledge_graph",
            "--storage-root",
            str(storage_root),
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    status = json.loads(result.stdout)
    assert status["app_name"] == "rtg_knowledge_graph"
    assert status["manifest_path"] == "system/app_manifest.json"
    assert status["json_document_count"] == 1
    assert status["rtg_controller_ready"] is True
    assert (storage_root / "system" / "app_manifest.json").exists()
    assert (storage_root / "runtime.sqlite").exists()


def test_cli_reports_mcp_dry_run_metadata(tmp_path: Path) -> None:
    storage_root = tmp_path / "mcp-storage"
    runtime_database_path = tmp_path / "runtime.sqlite"

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "apps.rtg_knowledge_graph",
            "serve-mcp",
            "--storage-root",
            str(storage_root),
            "--runtime-database-path",
            str(runtime_database_path),
            "--dry-run",
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    status = json.loads(result.stdout)
    tool_names = {item["name"] for item in status["mcp"]["tools"]}
    launch = status["mcp"]["launch"]
    client_config = status["mcp"]["client_config"]["mcpServers"]["rtg_knowledge_graph"]
    localhost_http = status["mcp"]["transports"]["localhost_http"]

    assert status["mcp"]["transport"] == "stdio"
    assert status["mcp"]["launch_mode"] == "repository_checkout"
    assert status["mcp"]["state_mode"] == "durable_local_auto_replay"
    assert (
        Path(status["mcp"]["eval_prompt_path"])
        == Path("docs/guides/vellis/evals/rtg-individual-life-graph-beta-prompt.md").resolve()
    )
    assert status["mcp"]["recommended_eval_prompt"] == "individual_life_graph"
    assert set(status["mcp"]["eval_prompts"]) == {
        "individual_life_graph",
        "component_repo_affordance",
    }
    assert status["mcp"]["eval_prompts"]["individual_life_graph"]["recommended"] is True
    assert status["mcp"]["eval_prompts"]["individual_life_graph"]["available"] is True
    assert status["mcp"]["eval_prompts"]["component_repo_affordance"]["recommended"] is False
    assert status["mcp"]["guides"]["known_good_walkthrough"]["available"] is True
    assert (
        Path(status["mcp"]["guides"]["known_good_walkthrough"]["path"])
        == Path("docs/guides/vellis/evals/rtg-beta-known-good-walkthrough.md").resolve()
    )
    assert set(status["mcp"]["guides"]) == {"known_good_walkthrough"}
    assert status["mcp"]["first_call"] == {
        "tool": "rtg_validate_graph",
        "arguments": {},
        "expected": {
            "ok": True,
            "result.accepted": True,
            "result.findings": [],
        },
        "purpose": "Confirm the MCP client is connected to a valid recovered RTG controller.",
    }
    assert len(tool_names) == 27
    assert "rtg_apply_live_graph_changes" in tool_names
    assert "rtg_validate_live_graph_changes" in tool_names
    assert "rtg_apply_live_anchor_records" in tool_names
    assert "rtg_validate_live_anchor_records" in tool_names
    assert "rtg_resolve_anchor_by_fact" in tool_names
    assert "rtg_get_agent_affordance_eval_prompt" not in tool_names
    assert launch["command"] == (shutil.which("uv") or "uv")
    assert launch["args"][:2] == ["--directory", str(Path(".").resolve())]
    assert "--storage-root" in launch["args"]
    assert "--runtime-database-path" in launch["args"]
    assert str(runtime_database_path.resolve()) in launch["args"]
    assert client_config == launch
    assert localhost_http["url"] == "http://127.0.0.1:8765/mcp"
    assert localhost_http["client_config"]["mcpServers"]["rtg_knowledge_graph"] == {
        "url": "http://127.0.0.1:8765/mcp",
        "transport": "http",
    }
    assert "--transport" in localhost_http["launch"]["args"]
    assert "http" in localhost_http["launch"]["args"]
    assert (storage_root / "system" / "app_manifest.json").exists()
    assert runtime_database_path.exists()


def test_cli_prints_focused_stdio_client_config_without_initializing_app(tmp_path: Path) -> None:
    storage_root = tmp_path / "mcp-storage"

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "apps.rtg_knowledge_graph",
            "mcp-config",
            "--storage-root",
            str(storage_root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    client_config = json.loads(result.stdout)
    launch = client_config["mcpServers"]["rtg_knowledge_graph"]

    assert launch["command"] == (shutil.which("uv") or "uv")
    assert launch["args"][:2] == ["--directory", str(Path(".").resolve())]
    assert str(storage_root.resolve()) in launch["args"]
    assert not storage_root.exists()


def test_cli_prints_focused_http_client_config(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "apps.rtg_knowledge_graph",
            "mcp-config",
            "--transport",
            "http",
            "--host",
            "127.0.0.1",
            "--port",
            "9876",
            "--path",
            "/custom-mcp",
            "--storage-root",
            str(tmp_path / "mcp-storage"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == {
        "mcpServers": {
            "rtg_knowledge_graph": {
                "transport": "http",
                "url": "http://127.0.0.1:9876/custom-mcp",
            }
        }
    }


def test_cli_prints_exact_codex_stdio_registration_command(tmp_path: Path) -> None:
    storage_root = tmp_path / "mcp storage"

    result = subprocess.run(
        [
            "uv",
            "run",
            "vellis-rtg-knowledge-graph",
            "mcp-config",
            "--client",
            "codex",
            "--storage-root",
            str(storage_root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    if os.name == "nt":
        assert result.stdout.startswith("codex mcp add rtg_knowledge_graph -- ")
        assert app_main._powershell_quote(shutil.which("uv") or "uv") in result.stdout
        assert app_main._powershell_quote(str(storage_root.resolve())) in result.stdout
    else:
        command = shlex.split(result.stdout)
        assert command[:5] == ["codex", "mcp", "add", "rtg_knowledge_graph", "--"]
        assert command[5] == (shutil.which("uv") or "uv")
        assert "--directory" in command
        assert str(storage_root.resolve()) in command
    assert not storage_root.exists()


def test_cli_prints_exact_codex_http_registration_command(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            "uv",
            "run",
            "vellis-rtg-knowledge-graph",
            "mcp-config",
            "--client",
            "codex",
            "--transport",
            "http",
            "--port",
            "9876",
            "--storage-root",
            str(tmp_path / "mcp-storage"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert shlex.split(result.stdout) == [
        "codex",
        "mcp",
        "add",
        "rtg_knowledge_graph",
        "--url",
        "http://127.0.0.1:9876/mcp",
    ]


def test_cli_help_explains_both_first_run_client_paths() -> None:
    result = subprocess.run(
        ["uv", "run", "vellis-rtg-knowledge-graph", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "vellis setup" in result.stdout
    assert "--client {auto,codex,claude-code,claude-desktop,generic-json}" in result.stdout
    assert "MCP client owns the configured stdio process" in result.stdout


def test_cli_treats_mcp_keyboard_interrupt_as_clean_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupt(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(app_main, "run_mcp_server", interrupt)

    assert app_main.main(["serve-mcp", "--transport", "http"]) == 0


def test_powershell_quoting_preserves_paths_and_embedded_quotes() -> None:
    assert app_main._powershell_quote(r"C:\Program Files\uv.exe") == (r"'C:\Program Files\uv.exe'")
    assert app_main._powershell_quote("person's-path") == "'person''s-path'"


def test_cli_reports_custom_http_mcp_dry_run_metadata(tmp_path: Path) -> None:
    storage_root = tmp_path / "mcp-storage"

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "apps.rtg_knowledge_graph",
            "serve-mcp",
            "--transport",
            "http",
            "--host",
            "127.0.0.1",
            "--port",
            "9876",
            "--path",
            "/custom-mcp",
            "--storage-root",
            str(storage_root),
            "--dry-run",
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    status = json.loads(result.stdout)

    assert status["mcp"]["transport"] == "http"
    assert status["mcp"]["client_config"] == {
        "mcpServers": {
            "rtg_knowledge_graph": {
                "url": "http://127.0.0.1:9876/custom-mcp",
                "transport": "http",
            }
        }
    }
    assert status["mcp"]["transports"]["localhost_http"]["url"] == (
        "http://127.0.0.1:9876/custom-mcp"
    )
    assert status["mcp"]["transports"]["localhost_http"]["client_config"] == {
        "mcpServers": {
            "rtg_knowledge_graph": {
                "url": "http://127.0.0.1:9876/custom-mcp",
                "transport": "http",
            }
        }
    }


def test_mcp_launch_metadata_has_installed_package_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_launch, "repository_root", lambda: None)
    config = RtgKnowledgeGraphConfig(
        storage_root=tmp_path / "storage",
        runtime_database_path=tmp_path / "runtime.sqlite",
    )

    metadata = mcp_launch.mcp_launch_metadata(config)
    launch = metadata["launch"]

    assert metadata["launch_mode"] == "installed_package"
    assert metadata["eval_prompt_path"] is None
    assert all(not prompt["available"] for prompt in metadata["eval_prompts"].values())
    assert all(not guide["available"] for guide in metadata["guides"].values())
    assert launch["command"]
    assert launch["args"][:3] == ["-m", "apps.rtg_knowledge_graph", "serve-mcp"]
    assert "cwd" not in launch
    assert metadata["client_config"]["mcpServers"]["rtg_knowledge_graph"] == launch
    assert metadata["transports"]["localhost_http"]["launch"]["args"][:3] == [
        "-m",
        "apps.rtg_knowledge_graph",
        "serve-mcp",
    ]
    assert metadata["transports"]["localhost_http"]["url"] == "http://127.0.0.1:8765/mcp"
