package VellisRuntimePythonRealization {
    private import SoftwareComponentModeling::*;
    private import ScalarValues::*;
    private import BibliotekRuntimeMessageRuntime::*;
    private import BibliotekRuntimeComponentAdapter::*;
    private import BibliotekInterfaceMcpGateway::*;
    private import VellisLocalPythonRealization::*;

    metadata def RuntimeOccurrenceBinding {
        :>> annotatedElement : SysML::PartUsage;
        attribute instanceKey : String;
        attribute componentContractId : String;
        attribute implementationBinding : String;
        attribute runtimeBindingId : String;
        attribute bindingVersion : Integer default = 1;
        attribute queueCapacity : Integer default = 128;
        attribute maxInFlight : Integer default = 1;
        attribute configurationReferences[0..*] : String;
        attribute replayAuthority : RuntimeReplayMode;
        doc /* Vellis-runtime realization metadata projected into the generated static occurrence manifest. The annotated usage remains the authoritative application occurrence. */
    }

    part def SqliteMessageRuntime :> MessageRuntime {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/runtime/message_runtime"; symbol = "components.runtime.message_runtime.SqliteMessageRuntime"; realization = "VellisRuntimePython"; }
    }
    part def ExplicitPythonComponentAdapter :> ComponentRuntimeAdapter {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/runtime/component_adapter"; symbol = "components.runtime.component_adapter.ExplicitComponentAdapter"; realization = "VellisRuntimePython"; }
    }
    part def PythonMcpGateway :> McpGateway {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/interface/mcp_gateway"; symbol = "components.interface.mcp_gateway.RuntimeMcpGateway"; realization = "VellisRuntimePython"; }
    }

    part def VellisRuntimePython :> VellisLocalPython {
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "apps/rtg_knowledge_graph"; symbol = "apps.rtg_knowledge_graph.composition.build_app"; realization = "local manifest-composed message runtime"; }
        doc /* Runtime-native Vellis realization. Every black-box component boundary is mediated by an explicit binding and the runtime; the controller retains RTG saga and coordinated snapshot authority while runtime history and reconstruction remain outside it. */

        part :>> runtime : SqliteMessageRuntime;
        part :>> graphStore : InMemoryRtgGraph {
            @RuntimeOccurrenceBinding { instanceKey = "vellis.graph.primary"; componentContractId = "component.rtg.graph"; implementationBinding = "VellisLocalPythonRealization::InMemoryRtgGraph"; runtimeBindingId = "binding.python.rtg.graph.v1"; replayAuthority = RuntimeReplayMode::canonical_effect; }
        }
        part :>> schemaRegistry : InMemoryRtgSchema {
            @RuntimeOccurrenceBinding { instanceKey = "vellis.schema.primary"; componentContractId = "component.rtg.schema"; implementationBinding = "VellisLocalPythonRealization::InMemoryRtgSchema"; runtimeBindingId = "binding.python.rtg.schema.v1"; replayAuthority = RuntimeReplayMode::canonical_effect; }
        }
        part :>> constraintRegistry : InMemoryRtgConstraints {
            @RuntimeOccurrenceBinding { instanceKey = "vellis.constraints.primary"; componentContractId = "component.rtg.constraints"; implementationBinding = "VellisLocalPythonRealization::InMemoryRtgConstraints"; runtimeBindingId = "binding.python.rtg.constraints.v1"; replayAuthority = RuntimeReplayMode::canonical_effect; }
        }
        part :>> migrationStore : InMemoryRtgMigration {
            @RuntimeOccurrenceBinding { instanceKey = "vellis.migration.primary"; componentContractId = "component.rtg.migration"; implementationBinding = "VellisLocalPythonRealization::InMemoryRtgMigration"; runtimeBindingId = "binding.python.rtg.migration.v1"; replayAuthority = RuntimeReplayMode::canonical_effect; }
        }
        part :>> documentStorage : LocalJsonFileStorage {
            @RuntimeOccurrenceBinding { instanceKey = "vellis.storage.json.primary"; componentContractId = "component.storage.json_file"; implementationBinding = "VellisLocalPythonRealization::LocalJsonFileStorage"; runtimeBindingId = "binding.python.storage.json_file.v1"; configurationReferences = ("config.storage_root"); replayAuthority = RuntimeReplayMode::external_exchange; }
        }
        part :>> queryEngine : SimpleRtgQueryEngine {
            @RuntimeOccurrenceBinding { instanceKey = "vellis.query.primary"; componentContractId = "component.rtg.query"; implementationBinding = "VellisLocalPythonRealization::SimpleRtgQueryEngine"; runtimeBindingId = "binding.python.rtg.query.v1"; replayAuthority = RuntimeReplayMode::no_state_effect; }
        }
        part :>> changeValidator : DeterministicRtgChangeValidator {
            @RuntimeOccurrenceBinding { instanceKey = "vellis.validation.primary"; componentContractId = "component.rtg.change_validation"; implementationBinding = "VellisLocalPythonRealization::DeterministicRtgChangeValidator"; runtimeBindingId = "binding.python.rtg.change_validation.v1"; replayAuthority = RuntimeReplayMode::no_state_effect; }
        }
        part :>> controller : InProcessRtgController {
            @RuntimeOccurrenceBinding { instanceKey = "vellis.controller.primary"; componentContractId = "component.rtg.controller"; implementationBinding = "VellisLocalPythonRealization::InProcessRtgController"; runtimeBindingId = "binding.python.rtg.controller.v1"; replayAuthority = RuntimeReplayMode::canonical_effect; }
        }
        part :>> facade : PythonVellisFacade {
            @RuntimeOccurrenceBinding { instanceKey = "vellis.facade.primary"; componentContractId = "application.vellis.facade"; implementationBinding = "VellisLocalPythonRealization::PythonVellisFacade"; runtimeBindingId = "binding.python.vellis.facade.v1"; replayAuthority = RuntimeReplayMode::coordinator_trace; }
        }
        part gateway : PythonMcpGateway {
            @RuntimeOccurrenceBinding { instanceKey = "vellis.interface.mcp"; componentContractId = "component.interface.mcp_gateway"; implementationBinding = "VellisRuntimePythonRealization::PythonMcpGateway"; runtimeBindingId = "binding.python.interface.mcp_gateway.source.v1"; queueCapacity = 1; replayAuthority = RuntimeReplayMode::external_exchange; }
        }
        part :>> starterOntologyInstaller : PythonEverydayLifeOntologyInstaller {
            @RuntimeOccurrenceBinding { instanceKey = "vellis.starter_ontology.installer"; componentContractId = "application.vellis.starter_ontology_installer"; implementationBinding = "VellisLocalPythonRealization::PythonEverydayLifeOntologyInstaller"; runtimeBindingId = "binding.python.vellis.starter_ontology_installer.source.v1"; queueCapacity = 1; replayAuthority = RuntimeReplayMode::external_exchange; }
        }
        part :>> runner : RtgKnowledgeGraphRunner {
            @RuntimeOccurrenceBinding { instanceKey = "vellis.runner.local"; componentContractId = "application.vellis.runner"; implementationBinding = "VellisLocalPythonRealization::RtgKnowledgeGraphRunner"; runtimeBindingId = "binding.python.vellis.runner.source.v1"; queueCapacity = 1; replayAuthority = RuntimeReplayMode::external_exchange; }
        }
        part graphAdapter : ExplicitPythonComponentAdapter;
        part schemaAdapter : ExplicitPythonComponentAdapter;
        part constraintsAdapter : ExplicitPythonComponentAdapter;
        part migrationAdapter : ExplicitPythonComponentAdapter;
        part queryAdapter : ExplicitPythonComponentAdapter;
        part validationAdapter : ExplicitPythonComponentAdapter;
        part jsonStorageAdapter : ExplicitPythonComponentAdapter;
        part controllerAdapter : ExplicitPythonComponentAdapter;
        part facadeAdapter : ExplicitPythonComponentAdapter;

        interface graphRuntime : RuntimeMessageExchange connect graphAdapter.messages to runtime.messages;
        interface schemaRuntime : RuntimeMessageExchange connect schemaAdapter.messages to runtime.messages;
        interface constraintsRuntime : RuntimeMessageExchange connect constraintsAdapter.messages to runtime.messages;
        interface migrationRuntime : RuntimeMessageExchange connect migrationAdapter.messages to runtime.messages;
        interface queryRuntime : RuntimeMessageExchange connect queryAdapter.messages to runtime.messages;
        interface validationRuntime : RuntimeMessageExchange connect validationAdapter.messages to runtime.messages;
        interface jsonStorageRuntime : RuntimeMessageExchange connect jsonStorageAdapter.messages to runtime.messages;
        interface controllerRuntime : RuntimeMessageExchange connect controllerAdapter.messages to runtime.messages;
        interface facadeRuntime : RuntimeMessageExchange connect facadeAdapter.messages to runtime.messages;
        interface gatewayRuntime : RuntimeMessageExchange connect gateway.messages to runtime.messages;

        bind graphAdapter.runtime = runtime;
        bind schemaAdapter.runtime = runtime;
        bind constraintsAdapter.runtime = runtime;
        bind migrationAdapter.runtime = runtime;
        bind queryAdapter.runtime = runtime;
        bind validationAdapter.runtime = runtime;
        bind jsonStorageAdapter.runtime = runtime;
        bind controllerAdapter.runtime = runtime;
        bind facadeAdapter.runtime = runtime;
        bind gateway.runtime = runtime;

        action routeGatewayRequest {
            in item requestEnvelope : RuntimeMessageEnvelope;
            action emitRequest send requestEnvelope via gateway.messages;
            action acceptRequest accept receivedRequest : RuntimeMessageEnvelope via runtime.messages;
            message gatewayRequestTransfer of RuntimeMessageEnvelope from emitRequest to acceptRequest;
        }
        action routeFacadeRequest {
            in item requestEnvelope : RuntimeMessageEnvelope;
            action emitRequest send requestEnvelope via runtime.messages;
            action acceptRequest accept receivedRequest : RuntimeMessageEnvelope via facadeAdapter.messages;
            message facadeRequestTransfer of RuntimeMessageEnvelope from emitRequest to acceptRequest;
        }
        action routeControllerRequest {
            in item requestEnvelope : RuntimeMessageEnvelope;
            action emitRequest send requestEnvelope via runtime.messages;
            action acceptRequest accept receivedRequest : RuntimeMessageEnvelope via controllerAdapter.messages;
            message controllerRequestTransfer of RuntimeMessageEnvelope from emitRequest to acceptRequest;
        }
        action routeGraphRequest {
            in item requestEnvelope : RuntimeMessageEnvelope;
            action emitRequest send requestEnvelope via runtime.messages;
            action acceptRequest accept receivedRequest : RuntimeMessageEnvelope via graphAdapter.messages;
            message graphRequestTransfer of RuntimeMessageEnvelope from emitRequest to acceptRequest;
        }
    }

    part runtimeVellis : VellisRuntimePython;
    allocate runtimeVellis.facade to runtimeVellis.facadeAdapter {
        allocate runtimeVellis.facade.rtgGetObject to runtimeVellis.facadeAdapter.dispatch;
        allocate runtimeVellis.facade.rtgReplayLedger to runtimeVellis.facadeAdapter.dispatch;
        allocate runtimeVellis.facade.rtgListMigrationHistory to runtimeVellis.facadeAdapter.dispatch;
        allocate runtimeVellis.facade.rtgRestoreFromSnapshot to runtimeVellis.facadeAdapter.dispatch;
    }
    allocate runtimeVellis.controller to runtimeVellis.controllerAdapter {
        allocate runtimeVellis.controller.getObject to runtimeVellis.controllerAdapter.dispatch;
        allocate runtimeVellis.controller.restoreFromSnapshot to runtimeVellis.controllerAdapter.dispatch;
    }
    allocate runtimeVellis.graphStore to runtimeVellis.graphAdapter {
        allocate runtimeVellis.graphStore.getObject to runtimeVellis.graphAdapter.dispatch;
    }
    allocate runtimeVellis.schemaRegistry to runtimeVellis.schemaAdapter;
    allocate runtimeVellis.constraintRegistry to runtimeVellis.constraintsAdapter;
    allocate runtimeVellis.migrationStore to runtimeVellis.migrationAdapter;
    allocate runtimeVellis.queryEngine to runtimeVellis.queryAdapter;
    allocate runtimeVellis.changeValidator to runtimeVellis.validationAdapter;
    allocate runtimeVellis.documentStorage to runtimeVellis.jsonStorageAdapter;

    requirement <'invariant.vellis.runtime.curated_gateway'> curatedRuntimeGateway {
        subject application : VellisRuntimePython;
        require constraint { doc /* External MCP traffic reaches only manifest-registered façade actions; no arbitrary component invocation operation is exposed. */ }
    }
    requirement <'invariant.vellis.runtime.message_mediated_boundaries'> messageMediatedBoundaries {
        subject application : VellisRuntimePython;
        require constraint { doc /* MCP, façade, controller, and lower component black-box interactions use registered message bindings; concrete business occurrences are constructed only at the composition root and never injected directly across managed boundaries. */ }
    }
    requirement <'invariant.vellis.runtime.snapshot_transfer'> snapshotTransferStartsNewChronology {
        subject application : VellisRuntimePython;
        require constraint { doc /* Data from an earlier Vellis installation enters through a validated coordinated snapshot restoration request recorded as new runtime traffic; no earlier controller ledger is imported or projected. */ }
    }
    part runtimeContractContext {
        part application : VellisRuntimePython;
        satisfy curatedRuntimeGateway by application;
        satisfy messageMediatedBoundaries by application;
        satisfy snapshotTransferStartsNewChronology by application;
    }
    verification def VellisRuntimeCompositionVerification {
        subject application : VellisRuntimePython;
        objective { verify curatedRuntimeGateway; verify messageMediatedBoundaries; verify snapshotTransferStartsNewChronology; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_app.py#VellisRuntimeCompositionVerification"; implementationScope = "VellisRuntimePython"; }
    }
}
