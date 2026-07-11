package Vellis {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import Bibliotek::*;
    private import VellisOperations::*;

    part def VellisApplication {
        @SpecIdentity { id = "application.vellis"; lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }

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

        dependency queryGraphRead
            from queryEngine.requiredGraphReadView to graphStore {
            @ContractSatisfaction;
        }

        dependency validationGraphRead
            from changeValidator.requiredGraphSnapshot to graphStore.exportSnapshot {
            @ContractSatisfaction;
        }
        dependency validationSchemaRead
            from changeValidator.requiredSchemaSnapshot to schemaRegistry.exportSnapshot {
            @ContractSatisfaction;
        }
        dependency validationConstraintRead
            from changeValidator.requiredConstraintSnapshot to constraintRegistry.exportSnapshot {
            @ContractSatisfaction;
        }
        dependency validationMigrationRead
            from changeValidator.requiredMigrationSnapshot to migrationStore.exportSnapshot {
            @ContractSatisfaction;
        }
        dependency validationQuery
            from changeValidator.requiredQueryExecution to queryEngine.execute {
            @ContractSatisfaction;
        }

        dependency controllerGraphSnapshot from controller.requiredGraphSnapshot to graphStore.exportSnapshot { @ContractSatisfaction; }
        dependency controllerGraphPutAnchor from controller.requiredGraphPutAnchor to graphStore.putAnchor { @ContractSatisfaction; }
        dependency controllerGraphPutData from controller.requiredGraphPutDataObject to graphStore.putDataObject { @ContractSatisfaction; }
        dependency controllerGraphPutLink from controller.requiredGraphPutLink to graphStore.putLink { @ContractSatisfaction; }
        dependency controllerGraphDelete from controller.requiredGraphDelete to graphStore.deleteAnchor { @ContractSatisfaction; }
        dependency controllerGraphPreview from controller.requiredGraphPreview to graphStore.previewDeleteAnchor { @ContractSatisfaction; }
        dependency controllerGraphRead from controller.requiredGraphRead to graphStore.getObject { @ContractSatisfaction; }
        dependency controllerSchemaSnapshot from controller.requiredSchemaSnapshot to schemaRegistry.exportSnapshot { @ContractSatisfaction; }
        dependency controllerSchemaWrite from controller.requiredSchemaWrite to schemaRegistry.putDefinition { @ContractSatisfaction; }
        dependency controllerSchemaRead from controller.requiredSchemaRead to schemaRegistry.getSchemaPack { @ContractSatisfaction; }
        dependency controllerConstraintSnapshot from controller.requiredConstraintSnapshot to constraintRegistry.exportSnapshot { @ContractSatisfaction; }
        dependency controllerConstraintWrite from controller.requiredConstraintWrite to constraintRegistry.putConstraint { @ContractSatisfaction; }
        dependency controllerMigrationSnapshot from controller.requiredMigrationSnapshot to migrationStore.exportSnapshot { @ContractSatisfaction; }
        dependency controllerMigrationWrite from controller.requiredMigrationWrite to migrationStore.putMigration { @ContractSatisfaction; }
        dependency controllerMigrationRead from controller.requiredMigrationRead to migrationStore.getMigration { @ContractSatisfaction; }
        dependency controllerValidation from controller.requiredValidation to changeValidator.validateBatch { @ContractSatisfaction; }
        dependency controllerQuery from controller.requiredQuery to queryEngine.execute { @ContractSatisfaction; }
        dependency controllerJsonWrite from controller.requiredJsonWrite to documentStorage.write { @ContractSatisfaction; }
        dependency controllerJsonRead from controller.requiredJsonRead to documentStorage.read { @ContractSatisfaction; }
        dependency controllerSqlExecute from controller.requiredSqlExecute to ledgerStorage.execute { @ContractSatisfaction; }
        dependency controllerSqlQuery from controller.requiredSqlQuery to ledgerStorage.query { @ContractSatisfaction; }
        dependency controllerSqlTransaction from controller.requiredSqlTransaction to ledgerStorage.transaction { @ContractSatisfaction; }

        dependency facadeApplyLiveGraphChanges from facade.requiredApplyLiveGraphChanges to controller.applyLiveGraphChanges { @ContractSatisfaction; }
        dependency facadeValidateLiveGraphChanges from facade.requiredValidateLiveGraphChanges to controller.validateLiveGraphChanges { @ContractSatisfaction; }
        dependency facadeStageKnowledgeChanges from facade.requiredStageKnowledgeChanges to controller.stageKnowledgeChanges { @ContractSatisfaction; }
        dependency facadeApplyMigrationCutover from facade.requiredApplyMigrationCutover to controller.applyMigrationCutover { @ContractSatisfaction; }
        dependency facadeExecuteQuery from facade.requiredExecuteQuery to controller.executeQuery { @ContractSatisfaction; }
        dependency facadeGetObject from facade.requiredGetObject to controller.getObject { @ContractSatisfaction; }
        dependency facadeListMigrations from facade.requiredListMigrations to controller.listMigrations { @ContractSatisfaction; }
        dependency facadeGetMigration from facade.requiredGetMigration to controller.getMigration { @ContractSatisfaction; }
        dependency facadeValidateGraph from facade.requiredValidateGraph to controller.validateGraph { @ContractSatisfaction; }
        dependency facadeDiscoverAnchorTypes from facade.requiredDiscoverAnchorTypes to controller.discoverAnchorTypes { @ContractSatisfaction; }
        dependency facadeGetSchemaPack from facade.requiredGetSchemaPack to controller.getSchemaPack { @ContractSatisfaction; }
        dependency facadeGetSystemState from facade.requiredGetSystemState to controller.getSystemState { @ContractSatisfaction; }
        dependency facadeExportSystemSnapshot from facade.requiredExportSystemSnapshot to controller.exportSystemSnapshot { @ContractSatisfaction; }
        dependency facadePersistSystemSnapshot from facade.requiredPersistSystemSnapshot to controller.persistSystemSnapshot { @ContractSatisfaction; }
        dependency facadeListPersistedSnapshots from facade.requiredListPersistedSnapshots to controller.listPersistedSnapshots { @ContractSatisfaction; }
        dependency facadeLoadPersistedSnapshot from facade.requiredLoadPersistedSnapshot to controller.loadPersistedSnapshot { @ContractSatisfaction; }
        dependency facadeAbandonMigration from facade.requiredAbandonMigration to controller.abandonMigration { @ContractSatisfaction; }
        dependency facadeReplayLedger from facade.requiredReplayLedger to controller.replayLedger { @ContractSatisfaction; }
        dependency facadeVerifyReplayFromLedger from facade.requiredVerifyReplayFromLedger to controller.verifyReplayFromLedger { @ContractSatisfaction; }
        dependency facadeListMigrationHistory from facade.requiredListMigrationHistory to controller.listMigrationHistory { @ContractSatisfaction; }
        dependency facadeFlushLedgerFailures from facade.requiredFlushLedgerFailures to controller.flushLedgerFailures { @ContractSatisfaction; }
        dependency facadeRestoreFromSnapshot from facade.requiredRestoreFromSnapshot to controller.restoreFromSnapshot { @ContractSatisfaction; }
    }

    requirement bibliotekOnlyThroughContracts {
        subject application : VellisApplication;
        doc /* Vellis consumes Bibliotek roles only through modeled public contracts. */
        @StableId { id = "invariant.vellis.bibliotek_public_contracts_only"; }
    }
    requirement discoveryDraftUnbound {
        subject application : VellisApplication;
        doc /* The draft curated discovery component is not part of the current application. */
        @StableId { id = "invariant.vellis.discovery_draft_unbound"; }
    }
    requirement transportOutsideController {
        subject application : VellisApplication;
        doc /* MCP transport and app shaping remain outside the RTG controller. */
        @StableId { id = "invariant.vellis.transport_outside_controller"; }
    }

    verification def VellisCompositionVerification {
        subject application : VellisApplication;
        objective { verify bibliotekOnlyThroughContracts; verify discoveryDraftUnbound; verify transportOutsideController; }
        @EvidenceBinding { verificationId = "verification.vellis.composition"; evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_app.py"; implementationScope = "VellisLocalPython"; }
    }
}
