package VellisLocalPythonRealization {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import Vellis::*;

    part def LocalJsonFileStorage :> JsonFileStorage {
        @ImplementationBinding { language = ImplementationLanguage::python; codeRoot = "components/storage/json_file"; symbol = "components.storage.json_file.LocalJsonFileStorage"; realization = "VellisLocalPython"; }
    }
    part def SqliteStorage :> SqlStorage {
        @ImplementationBinding { language = ImplementationLanguage::python; codeRoot = "components/storage/sql"; symbol = "components.storage.sql.SqliteStorage"; realization = "VellisLocalPython"; }
    }
    part def InMemoryRtgGraph :> RtgGraph {
        @ImplementationBinding { language = ImplementationLanguage::python; codeRoot = "components/rtg/graph"; symbol = "components.rtg.graph.InMemoryRtgGraph"; realization = "VellisLocalPython"; }
    }
    part def InMemoryRtgSchema :> RtgSchema {
        @ImplementationBinding { language = ImplementationLanguage::python; codeRoot = "components/rtg/schema"; symbol = "components.rtg.schema.InMemoryRtgSchema"; realization = "VellisLocalPython"; }
    }
    part def InMemoryRtgConstraints :> RtgConstraints {
        @ImplementationBinding { language = ImplementationLanguage::python; codeRoot = "components/rtg/constraints"; symbol = "components.rtg.constraints.InMemoryRtgConstraints"; realization = "VellisLocalPython"; }
    }
    part def InMemoryRtgMigration :> RtgMigration {
        @ImplementationBinding { language = ImplementationLanguage::python; codeRoot = "components/rtg/migration"; symbol = "components.rtg.migration.InMemoryRtgMigration"; realization = "VellisLocalPython"; }
    }
    part def SimpleRtgQueryEngine :> RtgQueryEngine {
        @ImplementationBinding { language = ImplementationLanguage::python; codeRoot = "components/rtg/query"; symbol = "components.rtg.query.SimpleRtgQueryEngine"; realization = "VellisLocalPython"; }
    }
    part def DeterministicRtgChangeValidator :> RtgChangeValidator {
        @ImplementationBinding { language = ImplementationLanguage::python; codeRoot = "components/rtg/change_validation"; symbol = "components.rtg.change_validation.DeterministicRtgChangeValidator"; realization = "VellisLocalPython"; }
    }
    part def InProcessRtgController :> RtgController {
        @ImplementationBinding { language = ImplementationLanguage::python; codeRoot = "components/rtg/controller"; symbol = "components.rtg.controller.InProcessRtgController"; realization = "VellisLocalPython"; }
    }
    part def RtgKnowledgeGraphRunner {
        @ImplementationBinding { language = ImplementationLanguage::python; codeRoot = "apps/rtg_knowledge_graph"; symbol = "apps.rtg_knowledge_graph.runner.RtgKnowledgeGraphRunner"; realization = "VellisLocalPython"; }
    }

    part def VellisLocalPython :> VellisApplication {
        @ImplementationBinding { language = ImplementationLanguage::python; codeRoot = "apps/rtg_knowledge_graph"; symbol = "apps.rtg_knowledge_graph.composition.build_app"; realization = "dependency-injected-in-process"; }
        part :>> documentStorage : LocalJsonFileStorage;
        part :>> ledgerStorage : SqliteStorage;
        part :>> graphStore : InMemoryRtgGraph;
        part :>> schemaRegistry : InMemoryRtgSchema;
        part :>> constraintRegistry : InMemoryRtgConstraints;
        part :>> migrationStore : InMemoryRtgMigration;
        part :>> queryEngine : SimpleRtgQueryEngine;
        part :>> changeValidator : DeterministicRtgChangeValidator;
        part :>> controller : InProcessRtgController;
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
    }
}
