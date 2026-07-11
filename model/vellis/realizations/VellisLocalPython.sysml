package VellisLocalPythonRealization {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import BibliotekStorageJsonFile::*;
    private import BibliotekStorageSql::*;
    private import BibliotekRtgGraph::*;
    private import BibliotekRtgSchema::*;
    private import BibliotekRtgConstraints::*;
    private import BibliotekRtgMigration::*;
    private import BibliotekRtgQuery::*;
    private import BibliotekRtgChangeValidation::*;
    private import BibliotekRtgController::*;
    private import VellisOperations::*;
    private import Vellis::*;

    part def LocalJsonFileStorage :> JsonFileStorage {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/storage/json_file"; symbol = "components.storage.json_file.LocalJsonFileStorage"; realization = "VellisLocalPython"; }
    }
    part def SqliteStorage :> SqlStorage {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/storage/sql"; symbol = "components.storage.sql.SqliteStorage"; realization = "VellisLocalPython"; }
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
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/rtg/query"; symbol = "components.rtg.query.SimpleRtgQueryEngine"; realization = "VellisLocalPython"; }
    }
    part def DeterministicRtgChangeValidator :> RtgChangeValidator {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/rtg/change_validation"; symbol = "components.rtg.change_validation.DeterministicRtgChangeValidator"; realization = "VellisLocalPython"; }
    }
    part def InProcessRtgController :> RtgController {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/rtg/controller"; symbol = "components.rtg.controller.InProcessRtgController"; realization = "VellisLocalPython"; }
    }
    part def PythonVellisFacade :> VellisApplicationFacade {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "apps/rtg_knowledge_graph"; symbol = "apps.rtg_knowledge_graph.mcp_toolset.RtgMcpToolset"; realization = "VellisLocalPython"; }
    }
    part def RtgKnowledgeGraphRunner {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "apps/rtg_knowledge_graph"; symbol = "apps.rtg_knowledge_graph.runner.RtgKnowledgeGraphRunner"; realization = "VellisLocalPython"; }
    }

    part def VellisLocalPython :> VellisApplication {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "apps/rtg_knowledge_graph"; symbol = "apps.rtg_knowledge_graph.composition.build_app"; realization = "dependency-injected-in-process"; }
        part :>> documentStorage : LocalJsonFileStorage;
        part :>> ledgerStorage : SqliteStorage;
        part :>> graphStore : InMemoryRtgGraph;
        part :>> schemaRegistry : InMemoryRtgSchema;
        part :>> constraintRegistry : InMemoryRtgConstraints;
        part :>> migrationStore : InMemoryRtgMigration;
        part :>> queryEngine : SimpleRtgQueryEngine;
        part :>> changeValidator : DeterministicRtgChangeValidator;
        part :>> controller : InProcessRtgController;
        part :>> facade : PythonVellisFacade;
        part runner : RtgKnowledgeGraphRunner;
    }

    part logicalVellis : VellisApplication;
    part pythonVellis : VellisLocalPython;
    allocate logicalVellis to pythonVellis {
        allocate logicalVellis.documentStorage to pythonVellis.documentStorage;
        allocate logicalVellis.ledgerStorage to pythonVellis.ledgerStorage;
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
            allocate logicalVellis.facade.rtgFlushLedgerFailures to pythonVellis.facade.rtgFlushLedgerFailures;
            allocate logicalVellis.facade.rtgRestoreFromSnapshot to pythonVellis.facade.rtgRestoreFromSnapshot;
        }
    }
}
