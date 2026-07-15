from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from apps.rtg_knowledge_graph.gateway_registration import (
    model_mcp_gateway_registrations,
    model_runtime_topology_manifest,
)
from apps.rtg_knowledge_graph.mcp_toolset import RtgMcpToolset
from apps.rtg_knowledge_graph.runner import RtgKnowledgeGraphRunner
from apps.rtg_knowledge_graph.runtime_binding import (
    create_vellis_facade_adapter,
    create_vellis_facade_proxy,
)
from apps.rtg_knowledge_graph.runtime_services import VellisRuntimeServices
from apps.rtg_knowledge_graph.starter_schema import (
    StarterSchemaStatus,
    prepare_controller,
    unreconstructed_starter_schema_status,
)
from components.interface.mcp_gateway import RuntimeMcpGateway
from components.rtg.change_validation import DeterministicRtgChangeValidator
from components.rtg.change_validation.runtime_binding import (
    create_rtg_change_validator_adapter,
    create_rtg_change_validator_proxy,
)
from components.rtg.constraints import InMemoryRtgConstraints
from components.rtg.constraints.runtime_binding import (
    create_rtg_constraints_adapter,
    create_rtg_constraints_proxy,
)
from components.rtg.controller import (
    InProcessRtgController,
    RtgController,
    RtgSystemSnapshot,
)
from components.rtg.controller.runtime_binding import (
    create_rtg_controller_adapter,
    create_rtg_controller_proxy,
)
from components.rtg.graph import InMemoryRtgGraph
from components.rtg.graph.runtime_binding import (
    create_rtg_graph_adapter,
    create_rtg_graph_proxy,
)
from components.rtg.migration import InMemoryRtgMigration
from components.rtg.migration.runtime_binding import (
    create_rtg_migration_adapter,
    create_rtg_migration_proxy,
)
from components.rtg.query import SimpleRtgQueryEngine
from components.rtg.query.runtime_binding import create_rtg_query_adapter, create_rtg_query_proxy
from components.rtg.schema import InMemoryRtgSchema
from components.rtg.schema.runtime_binding import (
    create_rtg_schema_adapter,
    create_rtg_schema_proxy,
)
from components.runtime.component_adapter import (
    MutableAdapterHost,
    ReplayStateBinding,
    RuntimeBindingInvalid,
)
from components.runtime.component_adapter.implementation import encode_json
from components.runtime.message_runtime import (
    ComponentOccurrenceRegistration,
    RuntimeHistoryQuery,
    RuntimeTopologyManifest,
)
from components.runtime.message_runtime.implementation import SqliteMessageRuntime
from components.storage.json_file.implementation import LocalJsonFileStorage
from components.storage.json_file.runtime_binding import (
    create_json_file_storage_adapter,
    create_json_file_storage_proxy,
)

_SOURCE_OCCURRENCES = {
    "vellis.interface.mcp",
    "vellis.starter_ontology.installer",
    "vellis.runner.local",
}


@dataclass(slots=True)
class RtgKnowledgeGraphComposition:
    config: RtgKnowledgeGraphConfig
    runtime: SqliteMessageRuntime
    controller: RtgController
    runner: RtgKnowledgeGraphRunner
    runtime_services: VellisRuntimeServices
    _starter_controller: RtgController
    _facade_host: MutableAdapterHost[RtgMcpToolset]
    _facade_proxy: RtgMcpToolset
    _gateway_registration: ComponentOccurrenceRegistration
    _manual_recovery_required: bool = False
    _starter_schema: StarterSchemaStatus | None = None
    _mcp_gateway: RuntimeMcpGateway | None = None

    def prepare(self) -> StarterSchemaStatus:
        if self._starter_schema is not None:
            return self._starter_schema
        recovery = (
            "manual_recovery_required"
            if self._manual_recovery_required
            else (
                "runtime_reconstructed"
                if self.runtime_services.startup_reconstruction is not None
                and self.runtime_services.startup_reconstruction.applied_effects > 0
                else "not_needed"
            )
        )
        status = (
            unreconstructed_starter_schema_status()
            if self._manual_recovery_required and self.runtime.health == "recovery_required"
            else prepare_controller(
                self._starter_controller,
                install_starter_schema=self.config.install_starter_schema,
                automatic_recovery=self.config.automatic_recovery,
                recovery=recovery,
            )
        )
        self._facade_host.replace(
            RtgMcpToolset(self._controller_for_facade(), status, self.runtime_services)
        )
        self._starter_schema = status
        return status

    def build_facade(self, starter_schema: StarterSchemaStatus) -> RtgMcpToolset:
        if self._starter_schema != starter_schema:
            self._facade_host.replace(
                RtgMcpToolset(
                    self._controller_for_facade(),
                    starter_schema,
                    self.runtime_services,
                )
            )
            self._starter_schema = starter_schema
        return self._facade_proxy

    def build_mcp_gateway(self, starter_schema: StarterSchemaStatus) -> RuntimeMcpGateway:
        if self._mcp_gateway is not None:
            return self._mcp_gateway
        self.build_facade(starter_schema)
        gateway = RuntimeMcpGateway(
            self.runtime,
            source_instance_key=self._gateway_registration.instance_key,
        )
        gateway.register_tools(model_mcp_gateway_registrations())
        self._mcp_gateway = gateway
        return gateway

    def close(self) -> None:
        self.runtime.close()

    def __enter__(self) -> RtgKnowledgeGraphComposition:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _controller_for_facade(self) -> RtgController:
        facade_address = self.runtime.address_for("vellis.facade.primary")
        controller_address = self.runtime.address_for("vellis.controller.primary")
        return create_rtg_controller_proxy(self.runtime, facade_address, controller_address)


def build_app(config: RtgKnowledgeGraphConfig) -> RtgKnowledgeGraphComposition:
    topology = model_runtime_topology_manifest()
    runtime = SqliteMessageRuntime.open(
        config.runtime_database_path,
        runtime_key=topology.runtime_key,
    )
    runtime.prepare_static_topology_sync(topology)
    registrations = _register_topology(runtime, topology)

    graph_host = MutableAdapterHost(InMemoryRtgGraph.empty())
    schema_host = MutableAdapterHost(InMemoryRtgSchema.empty())
    constraints_host = MutableAdapterHost(InMemoryRtgConstraints.empty())
    migration_host = MutableAdapterHost(InMemoryRtgMigration.empty())
    document_storage = LocalJsonFileStorage.open(config.storage_root)
    query = SimpleRtgQueryEngine()
    validator = DeterministicRtgChangeValidator()

    _attach(
        runtime,
        registrations,
        "vellis.graph.primary",
        create_rtg_graph_adapter(
            graph_host,
            replay_state=_state_replay_binding(graph_host, InMemoryRtgGraph.empty),
        ),
    )
    _attach(
        runtime,
        registrations,
        "vellis.schema.primary",
        create_rtg_schema_adapter(
            schema_host,
            replay_state=_state_replay_binding(schema_host, InMemoryRtgSchema.empty),
        ),
    )
    _attach(
        runtime,
        registrations,
        "vellis.constraints.primary",
        create_rtg_constraints_adapter(
            constraints_host,
            replay_state=_state_replay_binding(constraints_host, InMemoryRtgConstraints.empty),
        ),
    )
    _attach(
        runtime,
        registrations,
        "vellis.migration.primary",
        create_rtg_migration_adapter(
            migration_host,
            replay_state=_state_replay_binding(migration_host, InMemoryRtgMigration.empty),
        ),
    )
    _attach(
        runtime,
        registrations,
        "vellis.storage.json.primary",
        create_json_file_storage_adapter(document_storage),
    )
    _attach(
        runtime,
        registrations,
        "vellis.query.primary",
        create_rtg_query_adapter(query),
    )

    validator_address = runtime.address_for("vellis.validation.primary")
    query_address = runtime.address_for("vellis.query.primary")
    validation_query = create_rtg_query_proxy(runtime, validator_address, query_address)
    _attach(
        runtime,
        registrations,
        "vellis.validation.primary",
        create_rtg_change_validator_adapter(validator, query=validation_query),
    )

    controller_address = runtime.address_for("vellis.controller.primary")
    graph_proxy = create_rtg_graph_proxy(
        runtime, controller_address, runtime.address_for("vellis.graph.primary")
    )
    schema_proxy = create_rtg_schema_proxy(
        runtime, controller_address, runtime.address_for("vellis.schema.primary")
    )
    constraints_proxy = create_rtg_constraints_proxy(
        runtime, controller_address, runtime.address_for("vellis.constraints.primary")
    )
    migration_proxy = create_rtg_migration_proxy(
        runtime, controller_address, runtime.address_for("vellis.migration.primary")
    )
    validator_proxy = create_rtg_change_validator_proxy(
        runtime, controller_address, validator_address
    )
    query_proxy = create_rtg_query_proxy(runtime, controller_address, query_address)
    json_proxy = create_json_file_storage_proxy(
        runtime,
        controller_address,
        runtime.address_for("vellis.storage.json.primary"),
    )

    direct_controller = InProcessRtgController.open(
        graph_proxy,
        schema_proxy,
        constraints_proxy,
        migration_proxy,
        validator_proxy,
        query_proxy,
        json_proxy,
    )
    _attach(
        runtime,
        registrations,
        "vellis.controller.primary",
        create_rtg_controller_adapter(
            direct_controller,
            replay_state=_controller_replay_binding(
                graph_proxy,
                schema_proxy,
                constraints_proxy,
                migration_proxy,
                validator_proxy,
                query_proxy,
            ),
        ),
    )

    runtime_services = VellisRuntimeServices(runtime)
    facade_address = runtime.address_for("vellis.facade.primary")
    facade_controller = create_rtg_controller_proxy(runtime, facade_address, controller_address)
    facade_host = MutableAdapterHost(
        RtgMcpToolset(facade_controller, runtime_services=runtime_services)
    )
    _attach(
        runtime,
        registrations,
        "vellis.facade.primary",
        create_vellis_facade_adapter(facade_host),
    )

    runtime.confirm_static_topology_sync(topology)
    has_effects = bool(
        runtime.query_history_sync(RuntimeHistoryQuery(fact_type="canonical_effect", limit=1)).facts
    )
    manual_recovery_required = has_effects and not config.automatic_recovery
    if config.automatic_recovery:
        runtime_services.startup_reconstruction = runtime.reconstruct_sync(
            _latest_reconstruction_request()
        )

    gateway_registration = registrations["vellis.interface.mcp"]
    starter_registration = registrations["vellis.starter_ontology.installer"]
    starter_controller = create_rtg_controller_proxy(
        runtime,
        runtime.address_for(starter_registration.instance_key),
        controller_address,
    )
    runner_source = runtime.address_for("vellis.runner.local")
    runner = RtgKnowledgeGraphRunner(
        document_storage=create_json_file_storage_proxy(
            runtime,
            runner_source,
            runtime.address_for("vellis.storage.json.primary"),
        ),
        controller=create_rtg_controller_proxy(runtime, runner_source, controller_address),
        storage_root=config.storage_root,
        runtime_database_path=config.runtime_database_path,
        install_starter_schema=config.install_starter_schema,
        automatic_recovery=config.automatic_recovery,
    )
    return RtgKnowledgeGraphComposition(
        config=config,
        runtime=runtime,
        controller=starter_controller,
        runner=runner,
        runtime_services=runtime_services,
        _starter_controller=starter_controller,
        _facade_host=facade_host,
        _facade_proxy=create_vellis_facade_proxy(
            runtime,
            runtime.address_for(gateway_registration.instance_key),
            facade_address,
        ),
        _gateway_registration=gateway_registration,
        _manual_recovery_required=manual_recovery_required,
    )


def _register_topology(
    runtime: SqliteMessageRuntime, topology: RuntimeTopologyManifest
) -> dict[str, ComponentOccurrenceRegistration]:
    registrations: dict[str, ComponentOccurrenceRegistration] = {}
    for declaration in topology.occurrences:
        if declaration.instance_key in _SOURCE_OCCURRENCES:
            registration = runtime.register_source_occurrence(
                instance_key=declaration.instance_key,
                component_contract_id=declaration.component_contract_id,
                binding_id=declaration.binding_id,
                binding_version=declaration.binding_version,
                replay_authority=declaration.replay_authority,
                configuration_references=declaration.configuration_references,
            )
        else:
            registration = runtime.register_occurrence_sync(declaration)
        registrations[declaration.instance_key] = registration
    return registrations


def _attach(
    runtime: SqliteMessageRuntime,
    registrations: dict[str, ComponentOccurrenceRegistration],
    instance_key: str,
    adapter: Any,
) -> None:
    runtime.attach_adapter(registrations[instance_key], adapter)


def _state_replay_binding(
    host: MutableAdapterHost[Any],
    empty_factory: Callable[[], Any],
) -> ReplayStateBinding:
    empty_state = cast(Any, encode_json(empty_factory().export_snapshot()))

    def export_state() -> Any:
        return encode_json(host.resolve().export_snapshot())

    return ReplayStateBinding(
        is_empty=lambda: export_state() == empty_state,
        reset=lambda: host.replace(empty_factory()),
        import_checkpoint=_unsupported_checkpoint,
        export_state=export_state,
    )


def _controller_replay_binding(
    graph_proxy: Any,
    schema_proxy: Any,
    constraints_proxy: Any,
    migration_proxy: Any,
    validator_proxy: Any,
    query_proxy: Any,
) -> ReplayStateBinding:
    def export_state() -> Any:
        return encode_json(
            RtgSystemSnapshot(
                graph=graph_proxy.export_snapshot(),
                schema=schema_proxy.export_snapshot(),
                constraints=constraints_proxy.export_snapshot(),
                migration=migration_proxy.export_snapshot(),
            )
        )

    def verify() -> tuple[str, ...]:
        report = validator_proxy.validate_graph_state(
            graph_proxy,
            schema_proxy,
            constraints_proxy,
            migration_proxy,
            query_proxy,
        )
        return tuple(
            sorted(
                {
                    f"{finding.track}:{finding.code}"
                    for finding in report.findings
                    if finding.severity == "blocking"
                }
            )
        )

    return ReplayStateBinding(
        is_empty=lambda: True,
        reset=lambda: None,
        import_checkpoint=_unsupported_checkpoint,
        export_state=export_state,
        verify=verify,
    )


def _unsupported_checkpoint(_reference: str) -> int:
    raise RuntimeBindingInvalid(
        "this binding has no component checkpoint importer; replay from canonical effects"
    )


def _latest_reconstruction_request():
    from components.runtime.message_runtime import RuntimeReconstructionRequest

    return RuntimeReconstructionRequest()
