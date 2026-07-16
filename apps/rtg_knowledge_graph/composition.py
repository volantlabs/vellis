from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from apps.rtg_knowledge_graph.facade import VellisFacadeComponent
from apps.rtg_knowledge_graph.gateway_registration import (
    model_mcp_gateway_registrations,
    model_runtime_topology_manifest,
)
from apps.rtg_knowledge_graph.runner import (
    RUNNER_ACTIONS,
    RtgKnowledgeGraphRunner,
    RtgKnowledgeGraphRunStatus,
)
from apps.rtg_knowledge_graph.runtime_services import VellisRuntimeServices
from apps.rtg_knowledge_graph.starter_schema import (
    STARTER_INSTALLER_ACTIONS,
    EverydayLifeOntologyInstaller,
    StarterSchemaStatus,
    VellisStartupFailed,
    unreconstructed_starter_schema_status,
)
from components.interface.mcp_gateway import McpGatewayEndpoint, RuntimeMcpGateway
from components.rtg.change_validation import (
    DeterministicRtgChangeValidator,
    create_rtg_change_validator_adapter,
)
from components.rtg.constraints import InMemoryRtgConstraints, create_rtg_constraints_adapter
from components.rtg.controller import RtgControllerCoordinator, create_rtg_controller_adapter
from components.rtg.graph import InMemoryRtgGraph, create_rtg_graph_adapter
from components.rtg.migration import InMemoryRtgMigration, create_rtg_migration_adapter
from components.rtg.query import SimpleRtgQueryEngine, create_rtg_query_adapter
from components.rtg.schema import InMemoryRtgSchema, create_rtg_schema_adapter
from components.runtime.component_adapter import (
    ComponentAdapter,
    ComponentEndpoint,
    ReplayStateBinding,
    RuntimeBindingInvalid,
    decode_typed,
    encode_json,
)
from components.runtime.message_runtime import (
    ComponentOccurrenceRegistration,
    RuntimeHealth,
    RuntimeMessageKind,
    RuntimeReconstructionRequest,
    RuntimeTopologyManifest,
    SqliteMessageRuntime,
)
from components.storage.json_file import LocalJsonFileStorage, create_json_file_storage_adapter


@dataclass(slots=True)
class RtgKnowledgeGraphComposition:
    """The Vellis app: one runtime, ordinary attached occurrences, and curated ingress."""

    config: RtgKnowledgeGraphConfig
    runtime: SqliteMessageRuntime
    runtime_services: VellisRuntimeServices
    gateway: McpGatewayEndpoint
    _runner_endpoint: ComponentEndpoint
    _installer_endpoint: ComponentEndpoint
    _manual_recovery_required: bool = False
    _starter_schema: StarterSchemaStatus | None = None

    async def prepare(self) -> StarterSchemaStatus:
        if self._starter_schema is not None:
            return self._starter_schema
        if self._manual_recovery_required:
            self._starter_schema = unreconstructed_starter_schema_status()
            return self._starter_schema
        recovery = (
            "runtime_reconstructed"
            if self.runtime_services.startup_reconstruction is not None
            and self.runtime_services.startup_reconstruction.applied_effects > 0
            else "not_needed"
        )
        outcome = await self._installer_endpoint.request(
            STARTER_INSTALLER_ACTIONS["install"],
            {"recovery": recovery},
            target=self.runtime.address_for("vellis.starter_ontology.installer"),
        )
        if outcome.response.kind is RuntimeMessageKind.FAULT:
            raise VellisStartupFailed(str(outcome.response.payload.value))
        status_outcome = await self._installer_endpoint.request(
            STARTER_INSTALLER_ACTIONS["get_status"],
            {"recovery": recovery},
            target=self.runtime.address_for("vellis.starter_ontology.installer"),
        )
        if status_outcome.response.kind is RuntimeMessageKind.FAULT:
            raise VellisStartupFailed(str(status_outcome.response.payload.value))
        payload = status_outcome.response.payload.value
        if not isinstance(payload, dict):
            raise VellisStartupFailed("starter status returned a non-object response")
        self._starter_schema = decode_typed(payload.get("result"), StarterSchemaStatus)
        return self._starter_schema

    async def run(self) -> RtgKnowledgeGraphRunStatus:
        if (
            self._manual_recovery_required
            or self.runtime.health is RuntimeHealth.RECOVERY_REQUIRED
        ):
            return _recovery_pending_status(self.config)
        await self.prepare()
        outcome = await self._runner_endpoint.request(
            RUNNER_ACTIONS["run"],
            {},
            target=self.runtime.address_for("vellis.runner.local"),
        )
        if outcome.response.kind is RuntimeMessageKind.FAULT:
            raise RuntimeError(str(outcome.response.payload.value))
        payload = outcome.response.payload.value
        if not isinstance(payload, dict):
            raise RuntimeError("runner returned a non-object response")
        return decode_typed(payload.get("result"), RtgKnowledgeGraphRunStatus)

    async def build_mcp_gateway(self) -> McpGatewayEndpoint:
        await self.prepare()
        return self.gateway

    async def close(self) -> None:
        await self.runtime.aclose()

    async def __aenter__(self) -> RtgKnowledgeGraphComposition:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()


async def build_app(config: RtgKnowledgeGraphConfig) -> RtgKnowledgeGraphComposition:
    topology = model_runtime_topology_manifest()
    runtime = SqliteMessageRuntime.open(
        config.runtime_database_path,
        runtime_key=topology.runtime_key,
    )
    try:
        await runtime.prepare_static_topology(topology)
        registrations = await _register_topology(runtime, topology)

        graph = InMemoryRtgGraph.empty()
        schema = InMemoryRtgSchema.empty()
        constraints = InMemoryRtgConstraints.empty()
        migration = InMemoryRtgMigration.empty()
        document_storage = LocalJsonFileStorage.open(config.storage_root)

        participants: dict[str, ComponentAdapter] = {
            "vellis.graph.primary": create_rtg_graph_adapter(
                graph,
                replay_state=_state_replay_binding(graph, InMemoryRtgGraph.empty),
            ),
            "vellis.schema.primary": create_rtg_schema_adapter(
                schema,
                replay_state=_state_replay_binding(schema, InMemoryRtgSchema.empty),
            ),
            "vellis.constraints.primary": create_rtg_constraints_adapter(
                constraints,
                replay_state=_state_replay_binding(
                    constraints,
                    InMemoryRtgConstraints.empty,
                ),
            ),
            "vellis.migration.primary": create_rtg_migration_adapter(
                migration,
                replay_state=_state_replay_binding(migration, InMemoryRtgMigration.empty),
            ),
            "vellis.storage.json.primary": create_json_file_storage_adapter(document_storage),
            "vellis.query.primary": create_rtg_query_adapter(SimpleRtgQueryEngine()),
            "vellis.validation.primary": create_rtg_change_validator_adapter(
                DeterministicRtgChangeValidator()
            ),
            "vellis.controller.primary": create_rtg_controller_adapter(RtgControllerCoordinator()),
        }

        runtime_services = VellisRuntimeServices(runtime)
        facade = VellisFacadeComponent(runtime_services)
        participants["vellis.facade.primary"] = facade.create_adapter()

        gateway_component = RuntimeMcpGateway(model_mcp_gateway_registrations())
        gateway_digest = gateway_component.seal()
        if topology.curated_registration_digest != gateway_digest:
            raise RuntimeBindingInvalid(
                "sealed MCP registration digest differs from the projected topology"
            )
        participants["vellis.interface.mcp"] = gateway_component.create_adapter()

        installer = EverydayLifeOntologyInstaller(
            install_starter_schema=config.install_starter_schema,
            automatic_recovery=config.automatic_recovery,
        )
        participants["vellis.starter_ontology.installer"] = installer.create_adapter()

        runner = RtgKnowledgeGraphRunner(
            storage_root=config.storage_root,
            runtime_database_path=config.runtime_database_path,
            install_starter_schema=config.install_starter_schema,
            automatic_recovery=config.automatic_recovery,
        )
        participants["vellis.runner.local"] = runner.create_adapter()

        for instance_key, participant in participants.items():
            registration = registrations[instance_key]
            await runtime.attach_participant(
                registration,
                participant,
                participant.describe().actions,
            )
        await runtime.confirm_static_topology(topology)

        recovery_required = runtime.health is RuntimeHealth.RECOVERY_REQUIRED
        manual_recovery_required = recovery_required and not config.automatic_recovery
        if config.automatic_recovery and recovery_required:
            runtime_services.startup_reconstruction = await runtime.reconstruct(
                RuntimeReconstructionRequest()
            )

        gateway_adapter = participants["vellis.interface.mcp"]
        gateway_endpoint = ComponentEndpoint(
            runtime,
            gateway_adapter,
            source=runtime.address_for("vellis.interface.mcp"),
        )
        return RtgKnowledgeGraphComposition(
            config=config,
            runtime=runtime,
            runtime_services=runtime_services,
            gateway=McpGatewayEndpoint(
                gateway_endpoint,
                runtime.address_for,
                gateway_component,
                timeout_seconds=gateway_component.timeout_seconds,
            ),
            _runner_endpoint=ComponentEndpoint(
                runtime,
                participants["vellis.runner.local"],
                source=runtime.address_for("vellis.runner.local"),
            ),
            _installer_endpoint=ComponentEndpoint(
                runtime,
                participants["vellis.starter_ontology.installer"],
                source=runtime.address_for("vellis.starter_ontology.installer"),
            ),
            _manual_recovery_required=manual_recovery_required,
        )
    except Exception:
        await runtime.aclose()
        raise


async def _register_topology(
    runtime: SqliteMessageRuntime,
    topology: RuntimeTopologyManifest,
) -> dict[str, ComponentOccurrenceRegistration]:
    return {
        declaration.instance_key: await runtime.register_occurrence(declaration)
        for declaration in topology.occurrences
    }


def _state_replay_binding(
    component: Any,
    empty_factory: Callable[[], Any],
) -> ReplayStateBinding:
    empty_snapshot = empty_factory().export_snapshot()
    empty_state = encode_json(empty_snapshot)

    def export_state() -> Any:
        return encode_json(component.export_snapshot())

    return ReplayStateBinding(
        is_empty=lambda: export_state() == empty_state,
        reset=lambda: component.replace_snapshot(empty_snapshot),
        import_checkpoint=_unsupported_checkpoint,
        export_state=export_state,
    )


def _unsupported_checkpoint(_reference: str) -> int:
    raise RuntimeBindingInvalid(
        "this binding has no component checkpoint importer; replay from canonical effects"
    )


def _recovery_pending_status(config: RtgKnowledgeGraphConfig) -> RtgKnowledgeGraphRunStatus:
    return RtgKnowledgeGraphRunStatus(
        app_name="rtg_knowledge_graph",
        storage_root=str(config.storage_root),
        runtime_database_path=str(config.runtime_database_path),
        manifest_path="system/app_manifest.json",
        manifest_size_bytes=None,
        json_document_count=None,
        rtg_controller_ready=False,
    )


__all__ = ["RtgKnowledgeGraphComposition", "build_app"]
