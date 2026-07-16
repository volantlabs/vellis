from __future__ import annotations

import asyncio
import inspect
from dataclasses import replace
from pathlib import Path
from uuid import UUID

from components.rtg.change_validation import (
    DeterministicRtgChangeValidator,
    RtgChangeBatch,
    RtgGraphChangeSet,
    create_rtg_change_validator_adapter,
)
from components.rtg.constraints import InMemoryRtgConstraints, create_rtg_constraints_adapter
from components.rtg.controller import (
    RTG_CONTROLLER_ACTIONS,
    RtgControllerCoordinator,
    RtgControllerCutoverOptions,
    RtgSystemSnapshot,
    create_rtg_controller_adapter,
)
from components.rtg.graph import InMemoryRtgGraph, RtgAnchor, create_rtg_graph_adapter
from components.rtg.migration import (
    InMemoryRtgMigration,
    RtgMigrationRecord,
    create_rtg_migration_adapter,
)
from components.rtg.query import (
    RtgQueryAnchorBucket,
    RtgQuerySpec,
    SimpleRtgQueryEngine,
    create_rtg_query_adapter,
)
from components.rtg.schema import (
    InMemoryRtgSchema,
    RtgAnchorSchemaPayload,
    RtgSchemaDefinition,
    create_rtg_schema_adapter,
)
from components.runtime.component_adapter import ComponentAdapter, ComponentEndpoint, decode_typed
from components.runtime.message_runtime import SqliteMessageRuntime
from components.runtime.messaging import (
    ComponentOccurrenceDeclaration,
    RuntimeLaneDeclaration,
    RuntimeMessageKind,
    RuntimeReplayMode,
    RuntimeTopologyManifest,
    topology_manifest_hash,
)
from components.storage.json_file import LocalJsonFileStorage, create_json_file_storage_adapter

MODEL_EVIDENCE = {
    "ApplyLiveGraphChangesContractVerification": (
        "test_apply_live_graph_changes_contract_through_runtime",
    ),
    "ValidateLiveGraphChangesContractVerification": (
        "test_validate_live_graph_changes_contract_through_runtime",
    ),
    "StageKnowledgeChangesContractVerification": (
        "test_stage_knowledge_changes_contract_through_runtime",
    ),
    "ApplyMigrationCutoverContractVerification": (
        "test_apply_migration_cutover_contract_through_runtime",
    ),
    "AbandonMigrationContractVerification": ("test_abandon_migration_contract_through_runtime",),
    "ExecuteControllerQueryContractVerification": ("test_execute_query_contract_through_runtime",),
    "GetSystemStateContractVerification": ("test_get_system_state_contract_through_runtime",),
    "ExportSystemSnapshotContractVerification": (
        "test_export_system_snapshot_contract_through_runtime",
    ),
    "RestoreFromSnapshotContractVerification": (
        "test_restore_from_snapshot_contract_through_runtime",
    ),
    "ControllerGetObjectContractVerification": ("test_get_object_contract_through_runtime",),
    "ControllerListMigrationsContractVerification": (
        "test_list_migrations_contract_through_runtime",
    ),
    "ControllerGetMigrationContractVerification": ("test_get_migration_contract_through_runtime",),
    "ValidateGraphContractVerification": ("test_validate_graph_contract_through_runtime",),
    "DiscoverAnchorTypesContractVerification": (
        "test_discover_anchor_types_contract_through_runtime",
    ),
    "GetControllerSchemaPackContractVerification": (
        "test_get_schema_pack_contract_through_runtime",
    ),
    "PersistSystemSnapshotContractVerification": (
        "test_persist_system_snapshot_contract_through_runtime",
    ),
    "ListPersistedSnapshotsContractVerification": (
        "test_list_persisted_snapshots_contract_through_runtime",
    ),
    "ListSchemaDefinitionsByTypeKeyContractVerification": (
        "test_list_schema_definitions_by_type_key_contract_through_runtime",
    ),
    "LoadPersistedSnapshotContractVerification": (
        "test_load_persisted_snapshot_contract_through_runtime",
    ),
    "OpenRtgControllerContractVerification": (
        "test_controller_coordinator_receives_only_addresses_and_catalog_configuration",
    ),
    "RtgControllerBoundaryVerification": (
        "test_apply_live_graph_changes_contract_through_runtime",
        "test_validate_live_graph_changes_contract_through_runtime",
        "test_stage_knowledge_changes_contract_through_runtime",
        "test_apply_migration_cutover_contract_through_runtime",
        "test_abandon_migration_contract_through_runtime",
        "test_execute_query_contract_through_runtime",
        "test_get_system_state_contract_through_runtime",
        "test_export_system_snapshot_contract_through_runtime",
        "test_restore_from_snapshot_contract_through_runtime",
        "test_get_object_contract_through_runtime",
        "test_list_migrations_contract_through_runtime",
        "test_get_migration_contract_through_runtime",
        "test_validate_graph_contract_through_runtime",
        "test_discover_anchor_types_contract_through_runtime",
        "test_get_schema_pack_contract_through_runtime",
        "test_persist_system_snapshot_contract_through_runtime",
        "test_list_persisted_snapshots_contract_through_runtime",
        "test_list_schema_definitions_by_type_key_contract_through_runtime",
        "test_load_persisted_snapshot_contract_through_runtime",
        "test_controller_coordinator_receives_only_addresses_and_catalog_configuration",
    ),
}


async def _controller_runtime(
    root: Path,
    action_name: str,
) -> tuple[SqliteMessageRuntime, ComponentEndpoint, UUID]:
    anchor_id = UUID("00000000-0000-0000-0000-000000000001")
    graph = InMemoryRtgGraph.empty()
    if action_name in {"execute_query", "get_object"}:
        graph.put_anchor(RtgAnchor(anchor_id, "Person"))
    migration = InMemoryRtgMigration.empty()
    if action_name in {
        "apply_migration_cutover",
        "abandon_migration",
        "get_migration",
        "list_migrations",
    }:
        migration.put_migration(RtgMigrationRecord("migration-1", "evidence migration"))
    schema = InMemoryRtgSchema.empty()
    if action_name == "get_schema_pack":
        schema.put_definition(
            RtgSchemaDefinition(
                UUID("00000000-0000-0000-0000-000000000002"),
                "anchor",
                "Person",
                "A person",
                RtgAnchorSchemaPayload(),
                {"live": True},
            )
        )

    participants = {
        "vellis.graph.primary": create_rtg_graph_adapter(graph),
        "vellis.schema.primary": create_rtg_schema_adapter(schema),
        "vellis.constraints.primary": create_rtg_constraints_adapter(
            InMemoryRtgConstraints.empty()
        ),
        "vellis.migration.primary": create_rtg_migration_adapter(migration),
        "vellis.query.primary": create_rtg_query_adapter(SimpleRtgQueryEngine()),
        "vellis.validation.primary": create_rtg_change_validator_adapter(
            DeterministicRtgChangeValidator()
        ),
        "vellis.storage.json.primary": create_json_file_storage_adapter(
            LocalJsonFileStorage.open(root / "documents")
        ),
        "vellis.controller.primary": create_rtg_controller_adapter(RtgControllerCoordinator()),
        "ingress": ComponentAdapter(
            binding_id="binding.test.ingress",
            component_contract_id="component.test.ingress",
        ),
    }
    declarations = tuple(
        ComponentOccurrenceDeclaration(
            instance_key=key,
            component_contract_id=adapter.describe().component_contract_id,
            binding_id=adapter.describe().binding_id,
            binding_version=adapter.describe().binding_version,
            lanes=(
                (
                    RuntimeLaneDeclaration("read", worker_limit=4),
                    RuntimeLaneDeclaration("mutation"),
                )
                if key == "vellis.controller.primary"
                else (RuntimeLaneDeclaration("serialized"),)
            ),
            replay_authority=(
                RuntimeReplayMode.CANONICAL_EFFECT
                if key
                in {
                    "vellis.graph.primary",
                    "vellis.schema.primary",
                    "vellis.constraints.primary",
                    "vellis.migration.primary",
                }
                else RuntimeReplayMode.NO_STATE_EFFECT
            ),
        )
        for key, adapter in participants.items()
    )
    manifest = RuntimeTopologyManifest("test.controller.evidence", 4, declarations, (), "")
    manifest = replace(manifest, manifest_hash=topology_manifest_hash(manifest))
    runtime = SqliteMessageRuntime(root / "runtime.sqlite", runtime_key=manifest.runtime_key)
    await runtime.prepare_static_topology(manifest)
    for declaration in declarations:
        registration = await runtime.register_occurrence(declaration)
        participant = participants[declaration.instance_key]
        await runtime.attach_participant(
            registration,
            participant,
            participant.describe().actions,
        )
    await runtime.confirm_static_topology(manifest)
    ingress = participants["ingress"]
    return (
        runtime,
        ComponentEndpoint(runtime, ingress, source=runtime.address_for("ingress")),
        anchor_id,
    )


async def _action_arguments(
    action_name: str,
    endpoint: ComponentEndpoint,
    runtime: SqliteMessageRuntime,
    anchor_id: UUID,
) -> dict[str, object]:
    target = runtime.address_for("vellis.controller.primary")
    if action_name == "apply_live_graph_changes":
        return {"graph_changes": RtgGraphChangeSet(), "validation_mode": "skip"}
    if action_name == "validate_live_graph_changes":
        return {"graph_changes": RtgGraphChangeSet(), "validation_options": None}
    if action_name == "stage_knowledge_changes":
        return {"knowledge_changes": RtgChangeBatch(), "validation_mode": "skip"}
    if action_name == "apply_migration_cutover":
        return {
            "migration_id": "migration-1",
            "cutover_options": RtgControllerCutoverOptions(
                validation_mode="skip",
                prune_retired=False,
            ),
        }
    if action_name == "execute_query":
        return {
            "query_spec": RtgQuerySpec((RtgQueryAnchorBucket("people", ("Person",)),)),
            "query_options": None,
        }
    if action_name == "get_object":
        return {"object_uuid": anchor_id}
    if action_name == "list_migrations":
        return {"status": None}
    if action_name == "get_migration":
        return {"migration_id": "migration-1"}
    if action_name == "validate_graph":
        return {"migration_ids": None, "validation_options": None}
    if action_name == "discover_anchor_types":
        return {"discovery_options": None}
    if action_name == "get_schema_pack":
        return {"anchor_type_keys": ("Person",), "schema_pack_options": None}
    if action_name == "list_schema_definitions_by_type_key":
        return {"type_key": "Person", "kind": "anchor", "live": True, "offset": 0, "limit": 2}
    if action_name in {"get_system_state", "export_system_snapshot"}:
        return {}
    if action_name == "persist_system_snapshot":
        return {"relative_path": "snapshots/evidence.json"}
    if action_name == "list_persisted_snapshots":
        return {}
    if action_name == "load_persisted_snapshot":
        await endpoint.request(
            RTG_CONTROLLER_ACTIONS["persist_system_snapshot"],
            {"relative_path": "snapshots/evidence.json"},
            target=target,
        )
        return {"relative_path": "snapshots/evidence.json"}
    if action_name == "abandon_migration":
        return {"migration_id": "migration-1", "reason": "evidence"}
    if action_name == "restore_from_snapshot":
        exported = await endpoint.request(
            RTG_CONTROLLER_ACTIONS["export_system_snapshot"],
            {},
            target=target,
        )
        payload = exported.response.payload.value
        assert isinstance(payload, dict)
        return {"snapshot": decode_typed(payload["result"], RtgSystemSnapshot)}
    raise AssertionError(f"missing evidence arguments for {action_name}")


def _assert_controller_action_contract(tmp_path: Path, action_name: str) -> None:
    async def exercise() -> None:
        root = tmp_path / action_name
        runtime, endpoint, anchor_id = await _controller_runtime(root, action_name)
        target = runtime.address_for("vellis.controller.primary")
        arguments = await _action_arguments(action_name, endpoint, runtime, anchor_id)

        outcome = await endpoint.request(
            RTG_CONTROLLER_ACTIONS[action_name],
            arguments,
            target=target,
        )

        assert outcome.response.kind is RuntimeMessageKind.RESPONSE, outcome.response.payload.value
        payload = outcome.response.payload.value
        assert isinstance(payload, dict)
        assert "result" in payload
        trace = await runtime.get_trace(outcome.request.trace_id)
        assert any(
            fact.fact_type == "delivery_started"
            and fact.instance_key == "vellis.controller.primary"
            and fact.action_id == RTG_CONTROLLER_ACTIONS[action_name].action_id
            for fact in trace.facts
        )
        await runtime.aclose()

    asyncio.run(exercise())


def test_apply_live_graph_changes_contract_through_runtime(tmp_path: Path) -> None:
    _assert_controller_action_contract(tmp_path, "apply_live_graph_changes")


def test_validate_live_graph_changes_contract_through_runtime(tmp_path: Path) -> None:
    _assert_controller_action_contract(tmp_path, "validate_live_graph_changes")


def test_stage_knowledge_changes_contract_through_runtime(tmp_path: Path) -> None:
    _assert_controller_action_contract(tmp_path, "stage_knowledge_changes")


def test_apply_migration_cutover_contract_through_runtime(tmp_path: Path) -> None:
    _assert_controller_action_contract(tmp_path, "apply_migration_cutover")


def test_abandon_migration_contract_through_runtime(tmp_path: Path) -> None:
    _assert_controller_action_contract(tmp_path, "abandon_migration")


def test_execute_query_contract_through_runtime(tmp_path: Path) -> None:
    _assert_controller_action_contract(tmp_path, "execute_query")


def test_get_system_state_contract_through_runtime(tmp_path: Path) -> None:
    _assert_controller_action_contract(tmp_path, "get_system_state")


def test_export_system_snapshot_contract_through_runtime(tmp_path: Path) -> None:
    _assert_controller_action_contract(tmp_path, "export_system_snapshot")


def test_restore_from_snapshot_contract_through_runtime(tmp_path: Path) -> None:
    _assert_controller_action_contract(tmp_path, "restore_from_snapshot")


def test_get_object_contract_through_runtime(tmp_path: Path) -> None:
    _assert_controller_action_contract(tmp_path, "get_object")


def test_list_migrations_contract_through_runtime(tmp_path: Path) -> None:
    _assert_controller_action_contract(tmp_path, "list_migrations")


def test_get_migration_contract_through_runtime(tmp_path: Path) -> None:
    _assert_controller_action_contract(tmp_path, "get_migration")


def test_validate_graph_contract_through_runtime(tmp_path: Path) -> None:
    _assert_controller_action_contract(tmp_path, "validate_graph")


def test_discover_anchor_types_contract_through_runtime(tmp_path: Path) -> None:
    _assert_controller_action_contract(tmp_path, "discover_anchor_types")


def test_get_schema_pack_contract_through_runtime(tmp_path: Path) -> None:
    _assert_controller_action_contract(tmp_path, "get_schema_pack")


def test_persist_system_snapshot_contract_through_runtime(tmp_path: Path) -> None:
    _assert_controller_action_contract(tmp_path, "persist_system_snapshot")


def test_list_persisted_snapshots_contract_through_runtime(tmp_path: Path) -> None:
    _assert_controller_action_contract(tmp_path, "list_persisted_snapshots")


def test_list_schema_definitions_by_type_key_contract_through_runtime(tmp_path: Path) -> None:
    _assert_controller_action_contract(tmp_path, "list_schema_definitions_by_type_key")


def test_load_persisted_snapshot_contract_through_runtime(tmp_path: Path) -> None:
    _assert_controller_action_contract(tmp_path, "load_persisted_snapshot")


def test_controller_coordinator_receives_only_addresses_and_catalog_configuration() -> None:
    signature = inspect.signature(RtgControllerCoordinator)
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in signature.parameters.values()
    )
    assert all(parameter.name.endswith("_key") for parameter in signature.parameters.values())
    exports = __import__("components.rtg.controller", fromlist=["*"]).__dict__
    assert not any(name.startswith("InProcess") for name in exports)
