package Vellis {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import Bibliotek::*;
    private import VellisOperations::*;
    private import VellisEverydayLifeOntology::*;

    part def <'application.vellis'> VellisApplication {
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }

        part documentStorage : JsonFileStorage;
        part ledgerStorage : SqlStorage;
        part graphStore : RtgGraph;
        part schemaRegistry : RtgSchema;
        part constraintRegistry : RtgConstraints;
        part migrationStore : RtgMigration;
        part queryEngine : RtgQueryEngine;
        part changeValidator : RtgChangeValidator;
        part controller : RtgController;
        part facade : VellisApplicationFacade;
        part starterOntologyInstaller : EverydayLifeOntologyInstaller;

        bind controller.graph = graphStore;
        bind controller.schema = schemaRegistry;
        bind controller.constraints = constraintRegistry;
        bind controller.migration = migrationStore;
        bind controller.changeValidator = changeValidator;
        bind controller.queryEngine = queryEngine;
        bind controller.jsonStorage = documentStorage;
        bind controller.sqlStorage = ledgerStorage;
        bind facade.controller = controller;
    }


    requirement <'invariant.vellis.bibliotek_public_contracts_only'> bibliotekOnlyThroughContracts {
        subject application : VellisApplication;
        require constraint {
            doc /* Vellis consumes Bibliotek roles only through modeled public contracts. */
        }
    }

    requirement <'invariant.vellis.discovery_draft_unbound'> discoveryDraftUnbound {
        subject application : VellisApplication;
        require constraint {
            doc /* The draft curated discovery component is not part of the current application. */
        }
    }

    requirement <'invariant.vellis.transport_outside_controller'> transportOutsideController {
        subject application : VellisApplication;
        require constraint {
            doc /* MCP transport and app shaping remain outside the RTG controller. */
        }
    }

    part contractContext {
        part application : VellisApplication;
        satisfy bibliotekOnlyThroughContracts by application;
        satisfy discoveryDraftUnbound by application;
        satisfy transportOutsideController by application;
    }


    verification def VellisCompositionVerification {
        subject application : VellisApplication;
        objective { verify bibliotekOnlyThroughContracts; verify discoveryDraftUnbound; verify transportOutsideController; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_app.py#VellisCompositionVerification"; implementationScope = "VellisLocalPython"; }
    }
}
