package VellisLocalPythonRealization {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import BibliotekStorageJsonFile::*;
    private import BibliotekRuntimeMessageRuntime::*;
    private import BibliotekRtgGraph::*;
    private import BibliotekRtgSchema::*;
    private import BibliotekRtgConstraints::*;
    private import BibliotekRtgMigration::*;
    private import BibliotekRtgQuery::*;
    private import BibliotekRtgChangeValidation::*;
    private import BibliotekRtgController::*;
    private import VellisOperations::*;
    private import VellisEverydayLifeOntology::*;
    private import Vellis::*;

    part def LocalJsonFileStorage :> JsonFileStorage {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/storage/json_file"; symbol = "components.storage.json_file.LocalJsonFileStorage"; realization = "VellisLocalPython"; }
    }
    part def InMemoryRtgGraph :> RtgGraph {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/rtg/graph"; symbol = "components.rtg.graph.InMemoryRtgGraph"; realization = "VellisLocalPython"; }
    }
    part def InMemoryRtgSchema :> RtgSchema {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/rtg/schema"; symbol = "components.rtg.schema.InMemoryRtgSchema"; realization = "VellisLocalPython"; }
    }
    part def InMemoryRtgConstraints :> RtgConstraints {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/rtg/constraints"; symbol = "components.rtg.constraints.InMemoryRtgConstraints"; realization = "VellisLocalPython"; }
    }
    part def InMemoryRtgMigration :> RtgMigration {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/rtg/migration"; symbol = "components.rtg.migration.InMemoryRtgMigration"; realization = "VellisLocalPython"; }
    }
    part def SimpleRtgQueryEngine :> RtgQueryEngine {
        @ImplementationCodec { logicalType = "RtgQueryReturnProperty"; implementationType = "tuple[str, tuple[str, ...]]"; normalization = "The pair preserves dataRequirement and ordered path losslessly."; }
        @ImplementationCodec { logicalType = "RtgQuerySpec::returnSpec"; implementationType = "RtgQueryReturnSpec"; normalization = "An absent logical returnSpec decodes to the empty default record and encodes equivalently."; }
        @ImplementationCodec { logicalType = "RtgQuerySpec::diagnosticOptions"; implementationType = "RtgQueryDiagnosticOptions"; normalization = "Absent logical options decode to includeNonFatal=true and suggest_discovery and encode equivalently."; }
        @ImplementationCodec { logicalType = "RtgQueryNamedObjectBinding[0..*]"; implementationType = "dict[str, UUID]"; normalization = "Unique binding names become dictionary keys and preserve every name-to-object identity pair losslessly."; }
        @ImplementationCodec { logicalType = "RtgQueryLiveStatusOverride[0..*]"; implementationType = "dict[UUID, bool]"; normalization = "The unique object-UUID override map preserves every modeled override losslessly."; }
        @ImplementationCodec { logicalType = "RtgQueryPropertyPredicate::value[0..1]"; implementationType = "JsonValue | RtgQueryValueAbsent"; normalization = "The Python absence sentinel is omitted from JSON while an explicit None encodes as JSON null, preserving optional-field presence losslessly."; }
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/rtg/query"; symbol = "components.rtg.query.SimpleRtgQueryEngine"; realization = "VellisLocalPython"; }
    }
    part def DeterministicRtgChangeValidator :> RtgChangeValidator {
        @ImplementationCodec { logicalType = "RtgValidationOptions::selection"; implementationType = "tracks='all' | tuple[RtgValidationTrack, ...]"; normalization = "The compact tracks encoding preserves the modeled all-tracks selection or an explicit non-empty ordered track collection losslessly."; }
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/rtg/change_validation"; symbol = "components.rtg.change_validation.DeterministicRtgChangeValidator"; realization = "VellisLocalPython"; }
    }
    part def PythonRtgControllerCoordinator :> RtgController {
        doc /* Python controller validation options use the same tracks="all" or non-empty tuple encoding and map losslessly to RtgControllerValidationOptions. */
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/rtg/controller"; symbol = "components.rtg.controller.RtgControllerCoordinator"; realization = "VellisLocalPython"; }
    }
    part def PythonVellisFacade :> VellisApplicationFacade {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "apps/rtg_knowledge_graph"; symbol = "apps.rtg_knowledge_graph.facade.VellisFacadeComponent"; realization = "VellisLocalPython"; }
    }
    part def PythonRtgKnowledgeGraphRunner :> RtgKnowledgeGraphRunner {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "apps/rtg_knowledge_graph"; symbol = "apps.rtg_knowledge_graph.runner.RtgKnowledgeGraphRunner"; realization = "VellisLocalPython"; }
        perform action :>> run : RunRtgKnowledgeGraph;
    }
    part def PythonEverydayLifeOntologyInstaller :> EverydayLifeOntologyInstaller {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "apps/rtg_knowledge_graph"; symbol = "apps.rtg_knowledge_graph.starter_schema.EverydayLifeOntologyInstaller"; realization = "message-native installation and targeted status actions"; }
        perform action :>> install : InstallEverydayLifeOntology;
        perform action :>> getStatus : GetEverydayLifeOntologyStatus;
    }

    part def VellisLocalPython :> VellisApplication {
        doc /* Python realizations of the logical Vellis component occurrences. Runtime participation and address-only application composition are defined by VellisRuntimePython. */
        part :>> runtime : MessageRuntime;
        part :>> documentStorage : LocalJsonFileStorage;
        part :>> graphStore : InMemoryRtgGraph;
        part :>> schemaRegistry : InMemoryRtgSchema;
        part :>> constraintRegistry : InMemoryRtgConstraints;
        part :>> migrationStore : InMemoryRtgMigration;
        part :>> queryEngine : SimpleRtgQueryEngine;
        part :>> changeValidator : DeterministicRtgChangeValidator;
        part :>> controller : PythonRtgControllerCoordinator;
        part :>> facade : PythonVellisFacade;
        part :>> runner : PythonRtgKnowledgeGraphRunner;
        part :>> starterOntologyInstaller : PythonEverydayLifeOntologyInstaller;
    }

    part logicalVellis : VellisApplication;
    part pythonVellis : VellisLocalPython;
    allocate logicalVellis to pythonVellis {
        allocate logicalVellis.documentStorage to pythonVellis.documentStorage;
        allocate logicalVellis.runtime to pythonVellis.runtime;
        allocate logicalVellis.graphStore to pythonVellis.graphStore;
        allocate logicalVellis.schemaRegistry to pythonVellis.schemaRegistry;
        allocate logicalVellis.constraintRegistry to pythonVellis.constraintRegistry;
        allocate logicalVellis.migrationStore to pythonVellis.migrationStore;
        allocate logicalVellis.queryEngine to pythonVellis.queryEngine;
        allocate logicalVellis.changeValidator to pythonVellis.changeValidator;
        allocate logicalVellis.controller to pythonVellis.controller;
        allocate logicalVellis.facade to pythonVellis.facade {
            allocate logicalVellis.facade.rtgGetSystemState to pythonVellis.facade.rtgGetSystemState;
            allocate logicalVellis.facade.rtgGetUsageGuide to pythonVellis.facade.rtgGetUsageGuide;
            allocate logicalVellis.facade.rtgStageSchemaMigration to pythonVellis.facade.rtgStageSchemaMigration;
            allocate logicalVellis.facade.rtgValidateLiveAnchorRecords to pythonVellis.facade.rtgValidateLiveAnchorRecords;
            allocate logicalVellis.facade.rtgApplyLiveAnchorRecords to pythonVellis.facade.rtgApplyLiveAnchorRecords;
            allocate logicalVellis.facade.rtgValidateLiveGraphChanges to pythonVellis.facade.rtgValidateLiveGraphChanges;
            allocate logicalVellis.facade.rtgApplyLiveGraphChanges to pythonVellis.facade.rtgApplyLiveGraphChanges;
            allocate logicalVellis.facade.rtgStageKnowledgeChanges to pythonVellis.facade.rtgStageKnowledgeChanges;
            allocate logicalVellis.facade.rtgApplyMigrationCutover to pythonVellis.facade.rtgApplyMigrationCutover;
            allocate logicalVellis.facade.rtgAbandonMigration to pythonVellis.facade.rtgAbandonMigration;
            allocate logicalVellis.facade.rtgExecuteQuery to pythonVellis.facade.rtgExecuteQuery;
            allocate logicalVellis.facade.rtgResolveAnchorByFact to pythonVellis.facade.rtgResolveAnchorByFact;
            allocate logicalVellis.facade.rtgGetObject to pythonVellis.facade.rtgGetObject;
            allocate logicalVellis.facade.rtgListMigrations to pythonVellis.facade.rtgListMigrations;
            allocate logicalVellis.facade.rtgGetMigration to pythonVellis.facade.rtgGetMigration;
            allocate logicalVellis.facade.rtgValidateGraph to pythonVellis.facade.rtgValidateGraph;
            allocate logicalVellis.facade.rtgDiscoverAnchorTypes to pythonVellis.facade.rtgDiscoverAnchorTypes;
            allocate logicalVellis.facade.rtgGetSchemaPack to pythonVellis.facade.rtgGetSchemaPack;
            allocate logicalVellis.facade.rtgExportSystemSnapshot to pythonVellis.facade.rtgExportSystemSnapshot;
            allocate logicalVellis.facade.rtgPersistSystemSnapshot to pythonVellis.facade.rtgPersistSystemSnapshot;
            allocate logicalVellis.facade.rtgListPersistedSnapshots to pythonVellis.facade.rtgListPersistedSnapshots;
            allocate logicalVellis.facade.rtgLoadPersistedSnapshot to pythonVellis.facade.rtgLoadPersistedSnapshot;
            allocate logicalVellis.facade.rtgReplayLedger to pythonVellis.facade.rtgReplayLedger;
            allocate logicalVellis.facade.rtgVerifyReplayFromLedger to pythonVellis.facade.rtgVerifyReplayFromLedger;
            allocate logicalVellis.facade.rtgListMigrationHistory to pythonVellis.facade.rtgListMigrationHistory;
            allocate logicalVellis.facade.rtgGetOperationOutcome to pythonVellis.facade.rtgGetOperationOutcome;
            allocate logicalVellis.facade.rtgRestoreFromSnapshot to pythonVellis.facade.rtgRestoreFromSnapshot;
        }
        allocate logicalVellis.starterOntologyInstaller to pythonVellis.starterOntologyInstaller;
    }
}
