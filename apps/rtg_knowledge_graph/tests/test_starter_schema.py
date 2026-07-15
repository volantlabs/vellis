from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
from io import StringIO
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from apps.rtg_knowledge_graph.composition import build_app
from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from apps.rtg_knowledge_graph.mcp_codec import decode_change_batch, decode_schema_definition
from apps.rtg_knowledge_graph.mcp_toolset import RtgMcpToolset
from apps.rtg_knowledge_graph.onboarding import (
    config_for_data_dir,
    doctor_report,
    setup_vellis,
)
from apps.rtg_knowledge_graph.starter_schema import (
    VellisStartupFailed,
    install_everyday_life_ontology,
    load_starter_schema_bundle,
    prepare_controller,
)
from components.rtg.change_validation import DeterministicRtgChangeValidator
from components.rtg.constraints import InMemoryRtgConstraints
from components.rtg.controller import InProcessRtgController
from components.rtg.graph import InMemoryRtgGraph
from components.rtg.migration import InMemoryRtgMigration
from components.rtg.query import SimpleRtgQueryEngine
from components.rtg.schema import (
    InMemoryRtgSchema,
    RtgAnchorSchemaPayload,
    RtgSchemaDefinition,
)
from components.storage.json_file.implementation import LocalJsonFileStorage
from components.storage.sql import SqliteStorage

MODEL_EVIDENCE = {
    "EverydayLifeOntologyVerification": (
        "test_everyday_life_bundle_is_exact_schema_only_and_deterministic",
        "test_modeled_ontology_installer_reports_installation_and_reuse",
        "test_everyday_life_ontology_install_is_idempotent_and_replayable",
        "test_custom_schema_is_preserved_and_not_overlaid",
        "test_replayed_beta_shaped_custom_graph_with_overlapping_keys_starts",
        "test_installed_ontology_can_be_extended_without_bootstrap_overwrite",
        "test_starter_identity_collision_fails_without_partial_effects",
        "test_partial_starter_installation_fails_without_partial_effects",
        "test_startup_completes_an_exact_interrupted_starter_staging",
        "test_empty_mode_abandons_an_exact_interrupted_starter_staging",
        "test_manual_recovery_does_not_overlay_durable_history",
        "test_failed_starter_cutover_removes_staged_state_and_replays_cleanly",
    ),
}


def test_everyday_life_bundle_is_exact_schema_only_and_deterministic() -> None:
    first = load_starter_schema_bundle()
    second = load_starter_schema_bundle()
    assert first == second
    assert first["ontology_id"] == "ontology.vellis.everyday_life"
    assert first["graph_objects"] == []
    UUID(first["bootstrap_migration_id"])

    writes = first["knowledge_changes"]["schema_changes"]["definition_writes"]
    definitions = [write["definition"] for write in writes]
    assert len(definitions) == 33
    assert {item["type_key"] for item in definitions if item["kind"] == "anchor"} == {
        "Person",
        "Group",
        "Area",
        "Goal",
        "Project",
        "Task",
        "Event",
        "Routine",
        "Decision",
        "Note",
        "Resource",
        "Place",
    }
    assert {item["type_key"] for item in definitions if item["kind"] == "link"} == {
        "belongs_to",
        "supports",
        "responsible_for",
        "member_of",
        "involves",
        "located_at",
        "documents",
        "mentions",
        "depends_on",
    }
    facts = {
        item["type_key"]: item["payload"]["properties"]
        for item in definitions
        if item["kind"] == "data_object"
    }
    expected_fields = {
        "PersonFacts": ("name", "relationship", "preferred_contact", "notes"),
        "GroupFacts": ("name", "kind", "description"),
        "AreaFacts": ("title", "domain", "focus", "active"),
        "GoalFacts": (
            "title",
            "domain",
            "status",
            "priority",
            "target_date",
            "desired_outcome",
        ),
        "ProjectFacts": (
            "title",
            "domain",
            "status",
            "priority",
            "desired_outcome",
            "next_review",
        ),
        "TaskFacts": ("title", "domain", "status", "priority", "due", "context"),
        "EventFacts": ("title", "domain", "status", "start", "end", "summary"),
        "RoutineFacts": ("title", "domain", "cadence", "active", "next_due", "context"),
        "DecisionFacts": ("title", "domain", "status", "decided_on", "rationale"),
        "NoteFacts": ("title", "domain", "topic", "summary", "captured_at"),
        "ResourceFacts": ("title", "domain", "kind", "locator", "summary"),
        "PlaceFacts": ("name", "kind", "address", "notes"),
    }
    assert {key: set(properties) for key, properties in facts.items()} == {
        key: set(properties) for key, properties in expected_fields.items()
    }
    all_anchors = [
        "Person",
        "Group",
        "Area",
        "Goal",
        "Project",
        "Task",
        "Event",
        "Routine",
        "Decision",
        "Note",
        "Resource",
        "Place",
    ]
    links = {
        item["type_key"]: (
            item["payload"]["allowed_source_types"],
            item["payload"]["allowed_target_types"],
        )
        for item in definitions
        if item["kind"] == "link"
    }
    assert links == {
        "belongs_to": (
            ["Goal", "Project", "Task", "Event", "Routine", "Decision", "Note", "Resource"],
            ["Area"],
        ),
        "supports": (
            ["Project", "Task", "Event", "Routine", "Decision", "Note", "Resource"],
            ["Goal", "Project"],
        ),
        "responsible_for": (
            ["Person", "Group"],
            ["Area", "Goal", "Project", "Task", "Event", "Routine"],
        ),
        "member_of": (["Person"], ["Group"]),
        "involves": (
            ["Goal", "Project", "Task", "Event", "Routine", "Decision"],
            ["Person", "Group"],
        ),
        "located_at": (["Task", "Event", "Routine", "Group"], ["Place"]),
        "documents": (["Note", "Resource"], all_anchors),
        "mentions": (["Note"], all_anchors),
        "depends_on": (["Goal", "Project", "Task"], ["Goal", "Project", "Task"]),
    }
    for definition in definitions:
        UUID(definition["uuid"])
        assert definition["system"] == {"live": False}
        if definition["kind"] == "data_object":
            required = [
                key for key, rule in definition["payload"]["properties"].items() if rule["required"]
            ]
            assert required in (["name"], ["title"])


def test_modeled_ontology_installer_reports_installation_and_reuse(tmp_path: Path) -> None:
    controller = _controller(tmp_path, InMemoryRtgSchema.empty())

    installed = install_everyday_life_ontology(controller)
    reused = install_everyday_life_ontology(controller)

    assert installed.status == "installed"
    assert installed.schema_definition_count == 33
    assert installed.ontology.ontology_id == "ontology.vellis.everyday_life"
    assert installed.ontology.version == "1"
    assert installed.ontology.bootstrap_migration_id == "migration.vellis.everyday_life.v1"
    assert reused.status == "alreadyInstalled"
    assert reused.ontology == installed.ontology
    assert reused.schema_definition_count == 33


def test_everyday_life_ontology_install_is_idempotent_and_replayable(tmp_path: Path) -> None:
    config = config_for_data_dir(tmp_path / "data")
    first = build_app(config)
    installed = first.prepare()
    assert installed.status == "installed"
    assert first.controller.get_system_state().live_schema_counts.total == 33

    toolset = RtgMcpToolset(first.controller, installed)
    created = toolset.rtg_apply_live_anchor_records(
        [
            {
                "ref": {"local_ref": "person-alex"},
                "type": "Person",
                "display_name": "Alex",
                "facts": [{"type": "PersonFacts", "properties": {"name": "Alex"}}],
            }
        ]
    )
    assert created["ok"] is True
    assert first.controller.get_system_state().state_classification == "populated"

    restarted = build_app(config)
    replayed = restarted.prepare()
    assert replayed.status == "installed"
    assert replayed.recovery == "ledger_replayed"
    state = restarted.controller.get_system_state()
    assert state.live_schema_counts.total == 33
    assert state.state_classification == "populated"

    repeated = restarted.prepare()
    assert repeated.status == "installed"
    assert restarted.controller.get_system_state().live_schema_counts.total == 33


@pytest.mark.parametrize("type_key", ["CustomThing", "Person"])
def test_custom_schema_is_preserved_and_not_overlaid(tmp_path: Path, type_key: str) -> None:
    schema = InMemoryRtgSchema.empty()
    custom_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=custom_id,
            kind="anchor",
                type_key=type_key,
                description="Existing custom schema.",
                payload=RtgAnchorSchemaPayload(),
                time_shape="state_now",
                system={"live": True},
        )
    )
    controller = _controller(tmp_path, schema)
    status = prepare_controller(controller)
    assert status.status == "custom"
    snapshot = controller.export_system_snapshot()
    assert len(snapshot.schema.definitions) == 1
    assert snapshot.schema.definitions[0]["type_key"] == type_key

    installed = install_everyday_life_ontology(controller)
    assert installed.status == "customPreserved"
    assert installed.schema_definition_count == 0
    assert controller.export_system_snapshot() == snapshot


def test_replayed_beta_shaped_custom_graph_with_overlapping_keys_starts(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path, InMemoryRtgSchema.empty())
    toolset = RtgMcpToolset(controller)
    anchor_types = ("Person", "Area", "Project", "Task", "Event", "Note", "Resource")
    definitions: list[dict[str, Any]] = []
    for type_key in anchor_types:
        facts_type = f"{type_key}Facts"
        definitions.extend(
            (
                {
                    "kind": "anchor",
                        "type_key": type_key,
                        "description": f"Custom beta {type_key}.",
                        "time_shape": "state_now",
                        "payload": {"required_data_types": [facts_type]},
                },
                {
                    "kind": "data_object",
                        "type_key": facts_type,
                        "description": f"Custom beta {type_key} facts.",
                        "time_shape": "state_now",
                    "payload": {
                        "properties": {"title": {"required": True, "value_kinds": ["string"]}}
                    },
                },
            )
        )
    definitions.append(
        {
            "kind": "link",
            "type_key": "belongs_to",
            "description": "Custom beta primary-area relation.",
                "payload": {
                    "allowed_source_types": ["Project"],
                    "allowed_target_types": ["Area"],
                    "link_kind": "semantic",
                },
        }
    )
    assert (
        toolset.rtg_stage_schema_migration(
            "custom-beta-bootstrap", "Install synthetic custom beta schema.", definitions
        )["ok"]
        is True
    )
    assert toolset.rtg_apply_migration_cutover("custom-beta-bootstrap")["ok"] is True
    records = [
        {
            "ref": {"local_ref": type_key.lower()},
            "type": type_key,
            "facts": [{"type": f"{type_key}Facts", "properties": {"title": type_key}}],
        }
        for type_key in anchor_types
    ]
    assert (
        toolset.rtg_apply_live_anchor_records(
            records,
            link_writes=[
                {
                    "ref": {"local_ref": "project-area"},
                    "type": "belongs_to",
                    "source_ref": {"local_ref": "project"},
                    "target_ref": {"local_ref": "area"},
                }
            ],
        )["ok"]
        is True
    )
    before = controller.export_system_snapshot()

    restarted = build_app(
        RtgKnowledgeGraphConfig(
            storage_root=tmp_path / "json",
            sql_database_path=tmp_path / "ledger.sqlite",
            install_starter_schema=True,
            automatic_recovery=True,
        )
    )
    status = restarted.prepare()
    after = restarted.controller.export_system_snapshot()
    assert status.status == "custom"
    assert status.recovery == "ledger_replayed"
    _assert_same_domain_state(after, before)
    assert len(after.graph.anchors) == 7
    assert len(after.graph.data_objects) == 7
    assert len(after.graph.links) == 1
    assert len(after.schema.definitions) == 15

    legacy_config = RtgKnowledgeGraphConfig(
        storage_root=tmp_path / "json",
        sql_database_path=tmp_path / "ledger.sqlite",
        install_starter_schema=True,
        automatic_recovery=True,
    )
    ledger_count = restarted.controller.get_system_state().ledger_record_count
    setup = setup_vellis(
        legacy_config,
        client="generic-json",
        yes=True,
        output_stream=StringIO(),
    )
    assert setup.starter_schema.status == "custom"
    assert setup.starter_schema.recovery == "ledger_replayed"
    doctor = doctor_report(legacy_config, client="generic-json")
    assert doctor["ok"] is True
    replay_check = next(check for check in doctor["checks"] if check["id"] == "replay_feasibility")
    assert replay_check["detail"] == {
        "status": "custom",
        "recovery": "ledger_replayed",
    }
    asyncio.run(_assert_custom_graph_mcp_reconnects(legacy_config, tmp_path))
    final = build_app(legacy_config)
    assert final.prepare().status == "custom"
    assert final.controller.get_system_state().ledger_record_count == ledger_count
    _assert_same_domain_state(final.controller.export_system_snapshot(), before)

    empty_mode = build_app(
        RtgKnowledgeGraphConfig(
            storage_root=tmp_path / "json-empty-mode",
            sql_database_path=tmp_path / "ledger.sqlite",
            install_starter_schema=False,
            automatic_recovery=True,
        )
    )
    assert empty_mode.prepare().status == "custom"
    manual = build_app(
        RtgKnowledgeGraphConfig(
            storage_root=tmp_path / "json-manual",
            sql_database_path=tmp_path / "ledger.sqlite",
            install_starter_schema=False,
            automatic_recovery=False,
        )
    )
    manual_status = manual.prepare()
    assert manual_status.status == "empty"
    assert manual_status.recovery == "manual_recovery_required"


def test_installed_ontology_can_be_extended_without_bootstrap_overwrite(tmp_path: Path) -> None:
    composition = build_app(config_for_data_dir(tmp_path / "data"))
    installed = composition.prepare()
    toolset = RtgMcpToolset(composition.controller, installed)
    staged = toolset.rtg_stage_schema_migration(
        migration_id="everyday-life-extension",
        description="Add a user-approved extension type.",
        schema_definitions=[
            {
                "kind": "anchor",
                    "type_key": "UserExtension",
                    "description": "An approved application extension.",
                    "time_shape": "state_now",
                    "payload": {"required_data_types": []},
            }
        ],
    )
    assert staged["ok"] is True
    assert toolset.rtg_apply_migration_cutover("everyday-life-extension")["ok"] is True

    repeated = composition.prepare()
    assert repeated.status == "installed"
    assert composition.controller.get_system_state().live_schema_counts.total == 34


def test_starter_identity_collision_fails_without_partial_effects(tmp_path: Path) -> None:
    bundle = load_starter_schema_bundle()
    first_definition = bundle["knowledge_changes"]["schema_changes"]["definition_writes"][0][
        "definition"
    ]
    schema = InMemoryRtgSchema.empty()
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=UUID(first_definition["uuid"]),
            kind="anchor",
                type_key="ConflictingPerson",
                description="Conflicts with a reserved starter identity.",
                payload=decode_schema_definition(first_definition).payload,
                time_shape=str(first_definition["time_shape"]),
                system={"live": True},
        )
    )
    controller = _controller(tmp_path, schema)
    before = controller.export_system_snapshot()
    with pytest.raises(VellisStartupFailed, match="deterministic definition UUID"):
        prepare_controller(controller)
    assert controller.export_system_snapshot() == before


def test_partial_starter_installation_fails_without_partial_effects(tmp_path: Path) -> None:
    bundle = load_starter_schema_bundle()
    first_definition = bundle["knowledge_changes"]["schema_changes"]["definition_writes"][0][
        "definition"
    ]
    schema = InMemoryRtgSchema.empty()
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=UUID(first_definition["uuid"]),
            kind=first_definition["kind"],
                type_key=first_definition["type_key"],
                description=first_definition["description"],
                payload=decode_schema_definition(first_definition).payload,
                time_shape=str(first_definition["time_shape"]),
                system={"live": True},
        )
    )
    controller = _controller(tmp_path, schema)
    before = controller.export_system_snapshot()
    with pytest.raises(VellisStartupFailed, match="partial Everyday Life"):
        prepare_controller(controller)
    assert controller.export_system_snapshot() == before


def test_startup_completes_an_exact_interrupted_starter_staging(tmp_path: Path) -> None:
    controller = _controller(tmp_path, InMemoryRtgSchema.empty())
    bundle = load_starter_schema_bundle()
    controller.stage_knowledge_changes(
        decode_change_batch(bundle["knowledge_changes"]), validation_mode="strict"
    )

    status = prepare_controller(controller)

    assert status.status == "installed"
    assert status.recovery == "starter_install_completed"
    assert controller.validate_graph().accepted is True


def test_empty_mode_abandons_an_exact_interrupted_starter_staging(tmp_path: Path) -> None:
    controller = _controller(tmp_path, InMemoryRtgSchema.empty())
    bundle = load_starter_schema_bundle()
    controller.stage_knowledge_changes(
        decode_change_batch(bundle["knowledge_changes"]), validation_mode="strict"
    )

    status = prepare_controller(controller, install_starter_schema=False)

    assert status.status == "empty"
    assert status.recovery == "starter_install_abandoned"
    assert controller.export_system_snapshot().schema.definitions == ()


def test_manual_recovery_does_not_overlay_durable_history(tmp_path: Path) -> None:
    config = config_for_data_dir(tmp_path / "data")
    build_app(config).prepare()
    manual = build_app(
        RtgKnowledgeGraphConfig(
            storage_root=config.storage_root,
            sql_database_path=config.sql_database_path,
            install_starter_schema=False,
            automatic_recovery=False,
        )
    )
    status = manual.prepare()
    assert status.status == "empty"
    assert status.recovery == "manual_recovery_required"
    assert manual.controller.get_system_state().state_classification == "needs_replay"


def test_failed_starter_cutover_removes_staged_state_and_replays_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = config_for_data_dir(tmp_path / "data")
    composition = build_app(config)
    before = composition.controller.export_system_snapshot()

    def fail_cutover(_self: InProcessRtgController, _migration_id: str) -> object:
        raise RuntimeError("simulated cutover failure")

    monkeypatch.setattr(InProcessRtgController, "apply_migration_cutover", fail_cutover)
    with pytest.raises(VellisStartupFailed, match="installation failed"):
        composition.prepare()
    _assert_same_domain_state(composition.controller.export_system_snapshot(), before)

    monkeypatch.undo()
    restarted = build_app(
        RtgKnowledgeGraphConfig(
            storage_root=config.storage_root,
            sql_database_path=config.sql_database_path,
            install_starter_schema=False,
            automatic_recovery=True,
        )
    )
    status = restarted.prepare()
    assert status.status == "empty"
    _assert_same_domain_state(restarted.controller.export_system_snapshot(), before)


def _controller(tmp_path: Path, schema: InMemoryRtgSchema) -> InProcessRtgController:
    return InProcessRtgController.open(
        InMemoryRtgGraph.empty(),
        schema,
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        DeterministicRtgChangeValidator(),
        SimpleRtgQueryEngine(),
        LocalJsonFileStorage.open(tmp_path / "json"),
        SqliteStorage.open(tmp_path / "ledger.sqlite"),
    )


def _assert_same_domain_state(left: object, right: object) -> None:
    for feature in ("graph", "schema", "constraints", "migration"):
        assert getattr(left, feature) == getattr(right, feature)


async def _assert_custom_graph_mcp_reconnects(
    config: RtgKnowledgeGraphConfig, working_directory: Path
) -> None:
    base_args = [
        sys.executable,
        "-m",
        "apps.rtg_knowledge_graph",
        "serve-mcp",
        "--storage-root",
        str(config.storage_root),
        "--sql-database-path",
        str(config.sql_database_path),
    ]
    stdio = StdioServerParameters(
        command=base_args[0],
        args=[*base_args[1:], "--transport", "stdio"],
        cwd=working_directory,
    )
    async with stdio_client(stdio) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await _assert_custom_graph_session(session)

    port = _free_tcp_port()
    process = subprocess.Popen(
        [
            *base_args,
            "--transport",
            "http",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--path",
            "/mcp",
        ],
        cwd=working_directory,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_for_tcp_port("127.0.0.1", port, process)
        async with streamable_http_client(f"http://127.0.0.1:{port}/mcp") as (
            read,
            write,
            _session_id,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await _assert_custom_graph_session(session)
    finally:
        _terminate_process(process)


async def _assert_custom_graph_session(session: ClientSession) -> None:
    state = _tool_result_payload(await session.call_tool("rtg_get_system_state", {}))
    validation = _tool_result_payload(await session.call_tool("rtg_validate_graph", {}))
    query = _tool_result_payload(
        await session.call_tool(
            "rtg_execute_query",
            {"query_spec": {"anchor_buckets": [{"name": "task", "anchor_type_keys": ["Task"]}]}},
        )
    )
    assert state["ok"] is True
    assert state["result"]["starter_schema"]["status"] == "custom"
    assert state["result"]["live_schema_counts"]["total"] == 15
    assert validation["result"]["accepted"] is True
    assert len(query["result"]["bindings"]) == 1


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_tcp_port(host: str, port: int, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            _stdout, stderr = process.communicate(timeout=1)
            raise AssertionError(f"MCP HTTP server exited early: {stderr}")
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    _terminate_process(process)
    raise AssertionError(f"MCP HTTP server did not listen on {host}:{port}")


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _tool_result_payload(result: object) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return cast(dict[str, Any], structured)
    content = cast(Any, result).content
    return cast(dict[str, Any], json.loads(content[0].text))
