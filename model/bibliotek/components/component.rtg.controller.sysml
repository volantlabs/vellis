library package BibliotekRtgController {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;
    private import BibliotekStorageJsonFile::*;
    private import BibliotekRtgGraph::*;
    private import BibliotekRtgSchema::*;
    private import BibliotekRtgConstraints::*;
    private import BibliotekRtgMigration::*;
    private import BibliotekRtgQuery::*;
    private import BibliotekRtgChangeValidation::*;
    private import BibliotekRtgDiagnostics::*;

    enum def RtgControllerValidationMode { enum strict; enum skip; }
    enum def RtgControllerFailureRestore {
        enum restore_pre_cutover_snapshot;
    }
    enum def RtgControllerOperationStatus {
        enum applied;
        enum cutover_applied;
        enum cutover_failed;
        enum migration_abandoned;
        enum snapshot_persisted;
        enum restore_applied;
    }
    enum def RtgControllerValidationStatus { enum validated; }
    enum def RtgControllerMutationState {
        enum not_mutated;
    }
    enum def RtgControllerStateClassification {
        enum empty; enum schemaOnly; enum populated; enum hasStagedWork;
    }
    enum def RtgControllerWorkflow {
        enum schemaBootstrap; enum dataIngest; enum queryAnswer; enum safeUpdate;
        enum stagedWorkReview;
    }
    enum def RtgControllerMigrationCountScope {
        enum current_migration_store;
    }
    attribute def RtgControllerValidationOptions :> RtgValidationOptions {
        doc /* Controller validation uses the same canonical track-selection and finding-limit semantics as change validation. */
    }
    attribute def RtgControllerCutoverOptions { attribute validationMode : RtgControllerValidationMode = RtgControllerValidationMode::strict; attribute pruneRetired : Boolean = true; attribute failureRestore : RtgControllerFailureRestore = RtgControllerFailureRestore::restore_pre_cutover_snapshot; }
    attribute def RtgControllerDiscoveryOptions { attribute includeNonLive : Boolean = false; attribute limit[0..1] : Integer; }
    attribute def RtgControllerSchemaPackOptions { attribute live[0..1] : Boolean = true; attribute includeLiveCounts : Boolean = true; }
    attribute def RtgControllerAppliedChanges {
        attribute graphWrites : Integer;
        attribute schemaWrites : Integer;
        attribute constraintWrites : Integer;
        attribute migrationWrites : Integer;
        attribute deletes : Integer;
        attribute liveStatusChanges : Integer;
    }
    attribute def RtgControllerOperationResult {
        attribute status : RtgControllerOperationStatus;
        attribute appliedChanges : RtgControllerAppliedChanges;
        attribute validationReport[0..1] : RtgValidationReport;
        attribute 'snapshot'[0..1] : RtgSystemSnapshot;
        attribute details : JsonObject;
        attribute generatedIds : JsonObject;
    }
    attribute def RtgControllerLiveGraphValidationResult { attribute status : RtgControllerValidationStatus; attribute mutationState : RtgControllerMutationState; attribute accepted : Boolean; attribute generatedIds : JsonObject; attribute resolvedGraphChanges : RtgGraphChangeSet; attribute validationReport : RtgValidationReport; doc /* generatedIds maps each request-local reference to its resolved UUID exactly as apply would. */ }
    attribute def RtgSystemSnapshot { attribute graph : RtgGraphSnapshot; attribute schema : RtgSchemaSnapshot; attribute constraints : RtgConstraintSnapshot; attribute migration : RtgMigrationSnapshot; }
    attribute def RtgAnchorTypeDiscoveryEntry { attribute typeKey : String; attribute description : String; attribute liveCount : Integer; }
    attribute def RtgAnchorTypeDiscoveryResult { attribute anchorTypes[0..*] : RtgAnchorTypeDiscoveryEntry; }
    attribute def RtgControllerSchemaPack { attribute schemaPack : RtgSchemaPack; attribute liveCounts : JsonObject; }
    attribute def RtgPersistedSnapshotMetadata { attribute relativePath : JsonRelativePath; attribute sizeBytes : Integer; attribute modifiedAt : Timestamp; }
    attribute def RtgControllerSchemaCounts {
        attribute anchor : Integer;
        attribute dataObject : Integer;
        attribute link : Integer;
        attribute total : Integer;
    }
    attribute def RtgControllerCandidateCounts {
        attribute schema : Integer;
        attribute constraints : Integer;
        attribute graph : Integer;
        attribute total : Integer;
    }
    attribute def RtgControllerMigrationCounts {
        attribute draft : Integer;
        attribute ready : Integer;
        attribute failed : Integer;
        attribute applied : Integer;
        attribute abandoned : Integer;
        attribute total : Integer;
    }
    attribute def RtgControllerSystemState {
        attribute stateClassification : RtgControllerStateClassification;
        attribute liveSchemaCounts : RtgControllerSchemaCounts;
        attribute liveObjectCounts : RtgTypeCountList;
        attribute nonLiveCandidateCounts : RtgControllerCandidateCounts;
        attribute migrationCountsByStatus : RtgControllerMigrationCounts;
        attribute migrationCountsScope : RtgControllerMigrationCountScope default = RtgControllerMigrationCountScope::current_migration_store;
        attribute persistedSnapshotPaths[0..*] ordered : JsonRelativePath;
        attribute recommendedWorkflows[0..*] : RtgControllerWorkflow;
        attribute recommendedNextSteps[0..*] : String;
    }
    attribute def RtgPersistedSnapshotList { attribute snapshots[0..*] : RtgPersistedSnapshotMetadata; }
    attribute def RtgPersistedSnapshotDocument { attribute relativePath : JsonRelativePath; attribute 'snapshot' : RtgSystemSnapshot; }

    attribute def RtgControllerConfigurationInvalid { attribute 'message' : String; attribute diagnostic[0..1] : RtgDiagnostic; }
    attribute def RtgControllerValidationFailed { attribute 'message' : String; attribute validationReport[0..1] : RtgValidationReport; attribute diagnostic[0..1] : RtgDiagnostic; }
    attribute def RtgControllerPreconditionFailed { attribute 'message' : String; attribute diagnostic[0..1] : RtgDiagnostic; }
    attribute def RtgControllerApplyFailed { attribute 'message' : String; attribute diagnostic[0..1] : RtgDiagnostic; }
    attribute def RtgControllerObjectNotFound { attribute 'message' : String; attribute diagnostic[0..1] : RtgDiagnostic; }
    attribute def RtgControllerDiscoveryFailed { attribute 'message' : String; attribute diagnostic[0..1] : RtgDiagnostic; }
    attribute def RtgControllerSnapshotFailed { attribute 'message' : String; attribute diagnostic[0..1] : RtgDiagnostic; }
    attribute def RtgControllerRecoveryIndeterminate { attribute 'message' : String; attribute diagnostic[0..1] : RtgDiagnostic; }

    action def ApplyLiveGraphChanges { in graphChanges : RtgGraphChangeSet; in validationMode : RtgControllerValidationMode default = RtgControllerValidationMode::strict; out result : RtgControllerOperationResult; doc /* Validate and apply normal live graph CRUD in the serialized mutation lane. */ @FailureContract { errorIds = ("RtgControllerValidationFailed", "RtgControllerApplyFailed"); } }
    action def ValidateLiveGraphChanges { in graphChanges : RtgGraphChangeSet; in validationOptions[0..1] : RtgControllerValidationOptions; out result : RtgControllerLiveGraphValidationResult; doc /* Normalize exactly as apply would and return generated identities, resolved changes, and validation without component mutation. */ @FailureContract { errorIds = ("RtgControllerPreconditionFailed", "RtgValidationInputInvalid"); } }
    action def StageKnowledgeChanges { in knowledgeChanges : RtgChangeBatch; in validationMode : RtgControllerValidationMode default = RtgControllerValidationMode::strict; out result : RtgControllerOperationResult; doc /* Validate and stage migration-scoped non-live graph, schema, constraint, and migration records. */ @FailureContract { errorIds = ("RtgControllerValidationFailed", "RtgControllerPreconditionFailed", "RtgControllerApplyFailed"); } }
    action def ApplyMigrationCutover { in migrationId : String; in cutoverOptions[0..1] : RtgControllerCutoverOptions; out result : RtgControllerOperationResult; doc /* Apply exactly one migration membership in reference-safe order, validate the result, and either commit or restore. */ @FailureContract { errorIds = ("RtgControllerPreconditionFailed", "RtgControllerValidationFailed", "RtgControllerApplyFailed", "RtgControllerRecoveryIndeterminate"); } }
    action def ExecuteControllerQuery { in querySpec : RtgQuerySpec; in queryOptions[0..1] : RtgQueryOptions; out result : RtgQueryResult; doc /* Execute against one coherent graph view while controller mutations are excluded. */ @FailureContract { errorIds = ("RtgQuerySpecInvalid", "RtgQueryUnsupported"); } }
    action def ControllerGetObject { in objectUuid : String; out ref object : RtgObject; doc /* Normalize UUID text and return the public graph record without lifecycle filtering; invalid and absent UUIDs are reported through the controller-owned not-found contract. */ @FailureContract { errorIds = ("RtgControllerObjectNotFound"); } }
    action def ControllerListMigrations { in status[0..1] : RtgMigrationStatus; out result : RtgMigrationRecordList; doc /* Return all migration records or one status in deterministic migration-ID order. */ @FailureContract { errorIds = ("RtgMigrationStatusInvalid"); } }
    action def ControllerGetMigration { in migrationId : String; out result : RtgMigrationRecord; doc /* Return one migration tracking record by stable migration ID. */ @FailureContract { errorIds = ("RtgMigrationNotFound"); } }
    action def ValidateGraph { in migrationIds[0..*] : String; in validationOptions[0..1] : RtgControllerValidationOptions; out report : RtgValidationReport; doc /* Validate current state or named migration projections without mutation. */ @FailureContract { errorIds = ("RtgControllerValidationFailed"); } }
    action def DiscoverAnchorTypes { in discoveryOptions[0..1] : RtgControllerDiscoveryOptions; out result : RtgAnchorTypeDiscoveryResult; doc /* Compose schema summaries and graph counts; absent options exclude non-live types and impose no limit. */ @FailureContract { errorIds = ("RtgControllerDiscoveryFailed"); } }
    action def GetControllerSchemaPack { in anchorTypeKeys[1..*] : String; in schemaPackOptions[0..1] : RtgControllerSchemaPackOptions; out result : RtgControllerSchemaPack; doc /* Return the schema closure for named anchors and, by default, current live counts. */ @FailureContract { errorIds = ("RtgControllerDiscoveryFailed"); } }
    action def GetSystemState { out result : RtgControllerSystemState; doc /* Return a read-only classified domain summary, persisted snapshot paths, and recommended workflows. */ @FailureContract { errorIds = ("RtgControllerDiscoveryFailed"); } }
    action def ExportSystemSnapshot { out 'snapshot' : RtgSystemSnapshot; doc /* Export all four component snapshots from one coordinated visible state. */ @FailureContract { errorIds = ("RtgControllerSnapshotFailed"); } }
    action def PersistSystemSnapshot { in relativePath : JsonRelativePath; out result : RtgControllerOperationResult; doc /* Export and atomically store one coordinated snapshot under JSON storage authority. */ @FailureContract { errorIds = ("RtgControllerSnapshotFailed"); } }
    action def ListPersistedSnapshots { out result : RtgPersistedSnapshotList; doc /* List only valid persisted system snapshots visible through the bound JSON storage root. */ @FailureContract { errorIds = ("RtgControllerSnapshotFailed"); } }
    action def LoadPersistedSnapshot { in relativePath : JsonRelativePath; out result : RtgPersistedSnapshotDocument; doc /* Read and validate a persisted snapshot document without applying it. */ @FailureContract { errorIds = ("RtgControllerSnapshotFailed"); } }
    action def AbandonMigration { in migrationId : String; in reason[0..1] : String; out result : RtgControllerOperationResult; doc /* Mark migration work abandoned and prune only safe non-live candidates owned by that migration. */ @FailureContract { errorIds = ("RtgControllerPreconditionFailed", "RtgControllerApplyFailed"); } }
    action def RestoreFromSnapshot { in 'snapshot' : RtgSystemSnapshot; out result : RtgControllerOperationResult; doc /* Validate then atomically replace coordinated graph, schema, constraint, and migration state. */ @FailureContract { errorIds = ("RtgControllerSnapshotFailed", "RtgControllerRecoveryIndeterminate"); } }

    part def <'component.rtg.controller'> RtgController {
        doc /* Coordinate RTG mutation and validation lanes, saga compensation, cross-component invariants, query consistency, and coordinated snapshot export, persistence, and restoration. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }

        ref part graph[1] : RtgGraph {
            perform restoreFromSnapshot.replaceGraph;
            perform restoreFromSnapshot.compensateGraph;
        }
        ref part schema[1] : RtgSchema {
            perform restoreFromSnapshot.replaceSchema;
            perform restoreFromSnapshot.compensateSchema;
        }
        ref part constraints[1] : RtgConstraints {
            perform restoreFromSnapshot.replaceConstraints;
            perform restoreFromSnapshot.compensateConstraints;
        }
        ref part migration[1] : RtgMigration {
            perform restoreFromSnapshot.replaceMigration;
            perform restoreFromSnapshot.compensateMigration;
        }
        ref part changeValidator[1] : RtgChangeValidator {
            perform applyLiveGraphChanges.validateProjection;
            perform applyMigrationCutover.validateProjection;
            perform applyMigrationCutover.validateActualState;
            perform restoreFromSnapshot.validateSnapshot;
        }
        ref part queryEngine[1] : RtgQueryEngine {
            perform executeQuery.evaluate;
        }
        ref part jsonStorage[1] : JsonFileStorage;
        perform action applyLiveGraphChanges[0..*] : ApplyLiveGraphChanges {
            doc /* Serialized validation, component mutation, restoration on failure, and domain result. */
            action normalize {
                in attribute graphChanges = applyLiveGraphChanges.graphChanges;
                in attribute validationMode = applyLiveGraphChanges.validationMode;
                out attribute projectedBatch : RtgChangeBatch;
                out attribute validationOptions : RtgValidationOptions;
                doc /* Resolve request-local identities into one canonical projected change and validation selection. */
            }
            action validateProjection : ValidateRtgChangeBatch {
                in graph redefines ValidateRtgChangeBatch::graph = RtgController::graph;
                in schema redefines ValidateRtgChangeBatch::schema = RtgController::schema;
                in constraints redefines ValidateRtgChangeBatch::constraints = RtgController::constraints;
                in migration redefines ValidateRtgChangeBatch::migration = RtgController::migration;
                in query redefines ValidateRtgChangeBatch::query = RtgController::queryEngine;
                in changeBatch redefines ValidateRtgChangeBatch::changeBatch = normalize.projectedBatch;
                in validationOptions redefines ValidateRtgChangeBatch::validationOptions = normalize.validationOptions;
            }
            action applyProjection {
                in attribute projectedBatch = normalize.projectedBatch;
                out applied : Boolean;
                doc /* Apply the accepted projected graph change through public graph actions. */
            }
            action reject { doc /* Return the blocking validation report without mutation. */ }
            action restorePreimage { doc /* Restore every touched component after an apply failure. */ }
            action returnOutcome {
                out attribute result = applyLiveGraphChanges.result;
                doc /* Return the applied, rejected, or restored domain outcome. */
            }
            first normalize then validateProjection;
            succession acceptedProjection first validateProjection
                if validateProjection.report.accepted then applyProjection;
            succession rejectedProjection first validateProjection
                if not validateProjection.report.accepted then reject;
            succession failedApply first applyProjection
                if not applyProjection.applied then restorePreimage;
            succession successfulApply first applyProjection
                if applyProjection.applied then returnOutcome;
            first restorePreimage then returnOutcome;
            first reject then returnOutcome;
        }
        perform action validateLiveGraphChanges[0..*] : ValidateLiveGraphChanges { doc /* read and project dependencies with no component mutation. */ }
        perform action stageKnowledgeChanges[0..*] : StageKnowledgeChanges { doc /* serialized migration-scoped staging with rollback and a domain result. */ }
        perform action applyMigrationCutover[0..*] : ApplyMigrationCutover {
            doc /* Serialized coordinated cutover with validation, restoration, and a legible outcome. */
            action derivePlan {
                in attribute migrationId = applyMigrationCutover.migrationId;
                in attribute cutoverOptions = applyMigrationCutover.cutoverOptions;
                out attribute projectedBatch : RtgChangeBatch;
                out attribute validationOptions : RtgValidationOptions;
                doc /* Derive the exact transition set and validation selection from migration membership. */
            }
            action validateProjection : ValidateRtgChangeBatch {
                in graph redefines ValidateRtgChangeBatch::graph = RtgController::graph;
                in schema redefines ValidateRtgChangeBatch::schema = RtgController::schema;
                in constraints redefines ValidateRtgChangeBatch::constraints = RtgController::constraints;
                in migration redefines ValidateRtgChangeBatch::migration = RtgController::migration;
                in query redefines ValidateRtgChangeBatch::query = RtgController::queryEngine;
                in changeBatch redefines ValidateRtgChangeBatch::changeBatch = derivePlan.projectedBatch;
                in validationOptions redefines ValidateRtgChangeBatch::validationOptions = derivePlan.validationOptions;
            }
            action capturePreimage { doc /* Capture the complete coordinated pre-cutover state. */ }
            action applyCutover {
                out applied : Boolean;
                doc /* Apply reference-safe schema, constraint, graph, and lifecycle changes. */
            }
            action validateActualState : ValidateRtgChangeBatch {
                in graph redefines ValidateRtgChangeBatch::graph = RtgController::graph;
                in schema redefines ValidateRtgChangeBatch::schema = RtgController::schema;
                in constraints redefines ValidateRtgChangeBatch::constraints = RtgController::constraints;
                in migration redefines ValidateRtgChangeBatch::migration = RtgController::migration;
                in query redefines ValidateRtgChangeBatch::query = RtgController::queryEngine;
                in changeBatch redefines ValidateRtgChangeBatch::changeBatch = derivePlan.projectedBatch;
                in validationOptions redefines ValidateRtgChangeBatch::validationOptions = derivePlan.validationOptions;
            }
            action commitApplied {
                out attribute result = applyMigrationCutover.result;
                doc /* Commit applied lifecycle status and optional pruning, then return the applied outcome. */
            }
            action restorePreimage { doc /* Restore the coordinated preimage after any failed apply or validation. */ }
            action recordFailed {
                out attribute result = applyMigrationCutover.result;
                doc /* Return cutover_failed with actionable diagnostics after restoration and the documented migration failure-state effect. */
            }
            first derivePlan then validateProjection;
            succession acceptedCutoverProjection first validateProjection
                if validateProjection.report.accepted then capturePreimage;
            first capturePreimage then applyCutover;
            succession appliedCutover first applyCutover
                if applyCutover.applied then validateActualState;
            succession validCutoverState first validateActualState
                if validateActualState.report.accepted then commitApplied;
            succession failedCutoverApply first applyCutover
                if not applyCutover.applied then restorePreimage;
            succession invalidCutoverState first validateActualState
                if not validateActualState.report.accepted then restorePreimage;
            first restorePreimage then recordFailed;
        }
        perform action executeQuery[0..*] : ExecuteControllerQuery {
            doc /* Evaluate once against a coherent graph view while component writes are excluded. */
            action evaluate : ExecuteRtgQuery {
                in graph redefines ExecuteRtgQuery::graph = RtgController::graph;
                in querySpec redefines ExecuteRtgQuery::querySpec = executeQuery.querySpec;
                in queryOptions redefines ExecuteRtgQuery::queryOptions = executeQuery.queryOptions;
                out result redefines ExecuteRtgQuery::result = executeQuery.result;
            }
        }
        perform action getObject[0..*] : ControllerGetObject { doc /* read graph without mutation. */ }
        perform action listMigrations[0..*] : ControllerListMigrations { doc /* read migration store without mutation. */ }
        perform action getMigration[0..*] : ControllerGetMigration { doc /* read migration store without mutation. */ }
        perform action validateGraph[0..*] : ValidateGraph { doc /* read and project dependencies without mutation. */ }
        perform action discoverAnchorTypes[0..*] : DiscoverAnchorTypes { doc /* compose schema and count reads without mutation. */ }
        perform action getSchemaPack[0..*] : GetControllerSchemaPack { doc /* compose schema and count reads without mutation. */ }
        perform action getSystemState[0..*] : GetSystemState { doc /* summarize domain components and persisted snapshots without mutation. */ }
        perform action exportSystemSnapshot[0..*] : ExportSystemSnapshot { doc /* coordinated read of all four state-owning RTG components. */ }
        perform action persistSystemSnapshot[0..*] : PersistSystemSnapshot { doc /* write one atomic JSON snapshot document and return its domain outcome. */ }
        perform action listPersistedSnapshots[0..*] : ListPersistedSnapshots { doc /* read storage-scoped snapshot metadata without mutation. */ }
        perform action loadPersistedSnapshot[0..*] : LoadPersistedSnapshot { doc /* read and decode one snapshot document without restoring it. */ }
        perform action abandonMigration[0..*] : AbandonMigration { doc /* serialized safe candidate pruning, migration transition, rollback, and domain result. */ }
        perform action restoreFromSnapshot[0..*] : RestoreFromSnapshot {
            doc /* Validate then atomically replace coordinated domain state. Runtime chronology records the surrounding request and canonical effect outside this component. */
            action projectSnapshot {
                in attribute 'snapshot' = restoreFromSnapshot.'snapshot';
                out ref graph : RtgGraphReadView;
                out ref schema : RtgSchema;
                out ref constraints : RtgConstraints;
                out ref migration : RtgMigration;
                out ref query : RtgQueryEngine;
                out attribute validationOptions : RtgValidationOptions;
                doc /* Construct an isolated candidate state and the complete validation projection without changing current state. */
            }
            action validateSnapshot : ValidateRtgGraphState {
                in graph redefines ValidateRtgGraphState::graph = projectSnapshot.graph;
                in schema redefines ValidateRtgGraphState::schema = projectSnapshot.schema;
                in constraints redefines ValidateRtgGraphState::constraints = projectSnapshot.constraints;
                in migration redefines ValidateRtgGraphState::migration = projectSnapshot.migration;
                in query redefines ValidateRtgGraphState::query = projectSnapshot.query;
                in validationOptions redefines ValidateRtgGraphState::validationOptions = projectSnapshot.validationOptions;
            }
            action capturePreimage {
                out attribute graph : RtgGraphSnapshot;
                out attribute schema : RtgSchemaSnapshot;
                out attribute constraints : RtgConstraintSnapshot;
                out attribute migration : RtgMigrationSnapshot;
                doc /* Capture the complete prior state before any component replacement. */
            }
            action replaceGraph : ReplaceGraphSnapshot { in 'snapshot' redefines ReplaceGraphSnapshot::'snapshot' = restoreFromSnapshot.'snapshot'.graph; }
            action replaceSchema : ReplaceSchemaSnapshot { in 'snapshot' redefines ReplaceSchemaSnapshot::'snapshot' = restoreFromSnapshot.'snapshot'.schema; }
            action replaceConstraints : ReplaceConstraintSnapshot { in 'snapshot' redefines ReplaceConstraintSnapshot::'snapshot' = restoreFromSnapshot.'snapshot'.constraints; }
            action replaceMigration : ReplaceMigrationSnapshot { in 'snapshot' redefines ReplaceMigrationSnapshot::'snapshot' = restoreFromSnapshot.'snapshot'.migration; }
            action compensateGraph : ReplaceGraphSnapshot { in 'snapshot' redefines ReplaceGraphSnapshot::'snapshot' = capturePreimage.graph; }
            action compensateSchema : ReplaceSchemaSnapshot { in 'snapshot' redefines ReplaceSchemaSnapshot::'snapshot' = capturePreimage.schema; }
            action compensateConstraints : ReplaceConstraintSnapshot { in 'snapshot' redefines ReplaceConstraintSnapshot::'snapshot' = capturePreimage.constraints; }
            action compensateMigration : ReplaceMigrationSnapshot { in 'snapshot' redefines ReplaceMigrationSnapshot::'snapshot' = capturePreimage.migration; }
            action returnRestore {
                out attribute result = restoreFromSnapshot.result;
                doc /* Return the restoration outcome after the coordinated replacement. */
            }
            first projectSnapshot then validateSnapshot;
            succession acceptedSnapshot first validateSnapshot
                if validateSnapshot.report.accepted then capturePreimage;
            first capturePreimage then replaceGraph;
            first replaceGraph then replaceSchema;
            first replaceSchema then replaceConstraints;
            first replaceConstraints then replaceMigration;
            first replaceMigration then returnRestore;
        }

        dependency liveApplyGraph from applyLiveGraphChanges to graph { doc /* apply the accepted resolved graph change set. */ }
        dependency liveApplyValidation from applyLiveGraphChanges to changeValidator { doc /* validate the projected graph state before mutation. */ }
        dependency liveApplySchema from applyLiveGraphChanges to schema { doc /* supply schema state to projection validation. */ }
        dependency liveApplyConstraints from applyLiveGraphChanges to constraints { doc /* supply constraint state to projection validation. */ }
        dependency liveApplyMigration from applyLiveGraphChanges to migration { doc /* supply migration overlays to projection validation. */ }
        dependency liveApplyQuery from applyLiveGraphChanges to queryEngine { doc /* supply declarative query evaluation to validation tracks. */ }

        dependency liveValidateGraph from validateLiveGraphChanges to graph { doc /* read canonical graph state and build a projection without mutation. */ }
        dependency liveValidateSchema from validateLiveGraphChanges to schema { doc /* read schema state required by selected validation tracks. */ }
        dependency liveValidateConstraints from validateLiveGraphChanges to constraints { doc /* read constraint definitions required by selected tracks. */ }
        dependency liveValidateMigration from validateLiveGraphChanges to migration { doc /* read migration state required by selected tracks. */ }
        dependency liveValidateQuery from validateLiveGraphChanges to queryEngine { doc /* evaluate validation patterns without mutation. */ }
        dependency liveValidateEngine from validateLiveGraphChanges to changeValidator { doc /* validate the resolved projected state. */ }

        dependency stageGraph from stageKnowledgeChanges to graph { doc /* create or replace migration-scoped non-live graph candidates. */ }
        dependency stageSchema from stageKnowledgeChanges to schema { doc /* create or replace migration-scoped non-live schema candidates. */ }
        dependency stageConstraints from stageKnowledgeChanges to constraints { doc /* create or replace migration-scoped non-live constraint candidates. */ }
        dependency stageMigration from stageKnowledgeChanges to migration { doc /* maintain migration records, membership, evidence, and status. */ }
        dependency stageValidation from stageKnowledgeChanges to changeValidator { doc /* validate projected cutover state before staged writes. */ }
        dependency stageQuery from stageKnowledgeChanges to queryEngine { doc /* evaluate declarative validation patterns. */ }

        dependency cutoverGraph from applyMigrationCutover to graph { doc /* apply graph live-status changes and restore graph state on failure. */ }
        dependency cutoverSchema from applyMigrationCutover to schema { doc /* apply schema live-status changes and restore schema state on failure. */ }
        dependency cutoverConstraints from applyMigrationCutover to constraints { doc /* apply constraint live-status changes and restore constraint state on failure. */ }
        dependency cutoverMigration from applyMigrationCutover to migration { doc /* derive the plan and commit applied or failed lifecycle status. */ }
        dependency cutoverValidation from applyMigrationCutover to changeValidator { doc /* validate projected and actual cutover states. */ }
        dependency cutoverQuery from applyMigrationCutover to queryEngine { doc /* evaluate declarative validation patterns. */ }

        dependency queryGraph from executeQuery to graph { doc /* supply one coherent graph read view while writes are excluded. */ }
        dependency queryEngineUse from executeQuery to queryEngine { doc /* evaluate the caller query specification. */ }
        dependency objectGraph from getObject to graph { doc /* retrieve one graph object without mutation. */ }
        dependency listMigrationStore from listMigrations to migration { doc /* read deterministic current migration records. */ }
        dependency getMigrationStore from getMigration to migration { doc /* read one current migration record. */ }

        dependency graphValidationGraph from validateGraph to graph { doc /* read canonical graph state for validation. */ }
        dependency graphValidationSchema from validateGraph to schema { doc /* read schema state for validation. */ }
        dependency graphValidationConstraints from validateGraph to constraints { doc /* read constraints for validation. */ }
        dependency graphValidationMigration from validateGraph to migration { doc /* read migrations and requested overlays for validation. */ }
        dependency graphValidationQuery from validateGraph to queryEngine { doc /* evaluate declarative validation patterns. */ }
        dependency graphValidationEngine from validateGraph to changeValidator { doc /* execute selected validation tracks. */ }

        dependency discoveryGraph from discoverAnchorTypes to graph { doc /* count current objects by type and lifecycle. */ }
        dependency discoverySchema from discoverAnchorTypes to schema { doc /* read anchor type keys and descriptions. */ }
        dependency schemaPackGraph from getSchemaPack to graph { doc /* read requested live counts. */ }
        dependency schemaPackSchema from getSchemaPack to schema { doc /* read the selected schema closure. */ }

        dependency systemStateGraph from getSystemState to graph { doc /* summarize graph population and staged candidates. */ }
        dependency systemStateSchema from getSystemState to schema { doc /* summarize live and non-live schema state. */ }
        dependency systemStateConstraints from getSystemState to constraints { doc /* summarize constraint candidates. */ }
        dependency systemStateMigration from getSystemState to migration { doc /* summarize current migration lifecycle state. */ }
        dependency systemStateDocuments from getSystemState to jsonStorage { doc /* list storage-scoped persisted snapshots. */ }

        dependency exportGraph from exportSystemSnapshot to graph { doc /* export the graph snapshot. */ }
        dependency exportSchema from exportSystemSnapshot to schema { doc /* export the schema snapshot. */ }
        dependency exportConstraints from exportSystemSnapshot to constraints { doc /* export the constraint snapshot. */ }
        dependency exportMigration from exportSystemSnapshot to migration { doc /* export the migration snapshot. */ }
        dependency persistGraph from persistSystemSnapshot to graph { doc /* export graph state for the coordinated snapshot. */ }
        dependency persistSchema from persistSystemSnapshot to schema { doc /* export schema state for the coordinated snapshot. */ }
        dependency persistConstraints from persistSystemSnapshot to constraints { doc /* export constraint state for the coordinated snapshot. */ }
        dependency persistMigration from persistSystemSnapshot to migration { doc /* export migration state for the coordinated snapshot. */ }
        dependency persistDocuments from persistSystemSnapshot to jsonStorage { doc /* atomically write the coordinated snapshot document. */ }
        dependency listSnapshotDocuments from listPersistedSnapshots to jsonStorage { doc /* list persisted snapshot metadata. */ }
        dependency loadSnapshotDocument from loadPersistedSnapshot to jsonStorage { doc /* read and validate one persisted snapshot document. */ }

        dependency abandonGraph from abandonMigration to graph { doc /* prune only safe non-live graph candidates. */ }
        dependency abandonSchema from abandonMigration to schema { doc /* prune only safe non-live schema candidates. */ }
        dependency abandonConstraints from abandonMigration to constraints { doc /* prune only safe non-live constraint candidates. */ }
        dependency abandonMigrationStore from abandonMigration to migration { doc /* transition the selected migration to abandoned. */ }

        dependency restoreGraph from restoreFromSnapshot to graph { doc /* replace graph state from the validated snapshot. */ }
        dependency restoreSchema from restoreFromSnapshot to schema { doc /* replace schema state from the validated snapshot. */ }
        dependency restoreConstraints from restoreFromSnapshot to constraints { doc /* replace constraint state from the validated snapshot. */ }
        dependency restoreMigration from restoreFromSnapshot to migration { doc /* replace migration state from the validated snapshot. */ }
    }

    action def OpenRtgController {
        in ref graph : RtgGraph;
        in ref schema : RtgSchema;
        in ref constraints : RtgConstraints;
        in ref migration : RtgMigration;
        in ref changeValidator : RtgChangeValidator;
        in ref queryEngine : RtgQueryEngine;
        in ref jsonStorage : JsonFileStorage;
        out part controller : RtgController;
        doc /* Bind exactly one implementation of each of the seven required Bibliotek roles without taking traffic-ledger or runtime-history ownership. */
        @FailureContract { errorIds = ("RtgControllerConfigurationInvalid"); }
        bind controller.graph = graph;
        bind controller.schema = schema;
        bind controller.constraints = constraints;
        bind controller.migration = migration;
        bind controller.changeValidator = changeValidator;
        bind controller.queryEngine = queryEngine;
        bind controller.jsonStorage = jsonStorage;
    }


    requirement <'contract.rtg.controller.live_mutation_flow'> liveMutationFlow {
        subject operation : ApplyLiveGraphChanges;
        require constraint {
            doc /* Normalize references, construct a projected state, validate it in strict mode, apply only an accepted projection, restore all touched component state on apply failure, then return the domain outcome. */
        }
    }

    requirement <'contract.rtg.controller.live_mutation_lane'> liveMutationLane {
        subject operation : ApplyLiveGraphChanges;
        require constraint {
            doc /* The live lane accepts live anchor, data-object, and link writes, associations, dissociations, deletes, and live replacements. It rejects schema, constraint, migration, non-live candidate creation, and requests that make graph objects non-live. strict is the default; skip bypasses change validation only and never lower-store invariants. */
        }
    }

    requirement <'contract.rtg.controller.staging_flow'> stagingFlow {
        subject operation : StageKnowledgeChanges;
        require constraint {
            doc /* Staging accepts migration-scoped non-live graph, schema, and constraint candidates plus migration records, evidence, and permitted status changes. It rejects direct live schema/constraint writes, unscoped candidates, and live-status flips reserved for cutover. Strict mode validates the projected cutover before any write. A successful result has status applied and details keys operation_effect=staged_candidates_written, requires_cutover, staged_migration_ids, and candidate_counts with schema, constraints, and graph counts. */
        }
    }

    requirement <'contract.rtg.controller.validation_flow'> validationFlow {
        subject operation : ValidateLiveGraphChanges;
        require constraint {
            doc /* Resolve the request exactly as a write would, validate the projected state, return generated identities and resolved changes, and leave component state unchanged. */
        }
    }

    requirement <'contract.rtg.controller.cutover_flow'> cutoverFlow {
        subject operation : ApplyMigrationCutover;
        require constraint {
            doc /* Read the selected migration membership, snapshot coordinated state, apply make-live and make-non-live changes in reference-safe order, validate the result, and either commit an applied status or restore the snapshot and record failed status. A failed compensation never claims restoration or an ordinary failed outcome; it reports RtgControllerRecoveryIndeterminate. */
        }
    }

    requirement <'contract.rtg.controller.cutover_sequence'> cutoverSequence {
        subject operation : ApplyMigrationCutover;
        require constraint {
            doc /* Under the write lock: derive the plan from the selected migration; validate the projected state; capture a coordinated preimage; make schema and constraint changes, with make-non-live before make-live for a type key; make graph live changes; validate actual state; optionally prune retired records; then remove the completed migration. An ordinary failure restores the preimage, marks the migration failed when safe, and records cutover_failed. Failed compensation reports recovery-indeterminate state and does not assert either restoration or a safe failed-migration status. */
        }
    }

    requirement <'contract.rtg.controller.abandonment_flow'> abandonmentFlow {
        subject operation : AbandonMigration;
        require constraint {
            doc /* Applied migrations cannot be abandoned. Draft, ready, or failed work becomes abandoned; only non-live make-live candidates unshared by another migration may be pruned. Live records and make-non-live targets are never deleted. details.pruned_candidates groups removed IDs under schema, constraints, and graph; details.skipped_candidates groups retained IDs under the same keys and gives each a reason of shared, missing, or live. */
        }
    }

    requirement <'contract.rtg.controller.stable_query_flow'> stableQueryFlow {
        subject operation : ExecuteControllerQuery;
        require constraint {
            doc /* Execute each query while writes are excluded so the query engine receives one coherent graph read view. */
        }
    }

    requirement <'contract.rtg.controller.read_semantics'> controllerReadSemantics {
        subject controller : RtgController;
        require constraint {
            doc /* Query defaults to live-only at the controller boundary unless explicit query options override it. Direct object reads do not lifecycle-filter. Migration reads are deterministically ordered. All reads queue behind cutover and restore mutations. */
        }
    }

    requirement <'contract.rtg.controller.discovery_semantics'> discoverySemantics {
        subject controller : RtgController;
        require constraint {
            doc /* Discovery composes schema-owned descriptions with graph counts, excludes non-live definitions by default, and applies a positive optional limit. Schema packs contain selected anchors, associated-data schemas, participating links, and live counts when requested. */
        }
    }

    requirement <'contract.rtg.controller.system_state_semantics'> systemStateSemantics {
        subject operation : GetSystemState;
        require constraint {
            doc /* State classification is exactly empty, schema_only, populated, or has_staged_work. liveSchemaCounts has anchor, data-object, link, and total definition counts; liveObjectCounts is the graph-owned ordered type-count list; nonLiveCandidateCounts has schema, constraints, graph, and total counts; migrationCountsByStatus has draft, ready, failed, applied, abandoned, and total counts. The result also reports storage-scoped snapshot paths, stable workflow identifiers, and advisory next steps without mutation. Type names and snapshot metadata remain available through their dedicated discovery and snapshot-list actions. */
        }
    }

    requirement <'contract.rtg.controller.snapshot_flow'> coordinatedSnapshotFlow {
        subject operation : ExportSystemSnapshot;
        require constraint {
            doc /* Export graph, schema, constraint, and migration snapshots from one visible controller state. */
        }
    }

    requirement <'contract.rtg.controller.persisted_snapshot_semantics'> persistedSnapshotSemantics {
        subject controller : RtgController;
        require constraint {
            doc /* Persist writes the coordinated snapshot atomically through JSON storage. List and load expose only valid snapshot-like JSON documents below that storage root; load validates but does not apply the snapshot. */
        }
    }

    requirement <'contract.rtg.controller.restore_flow'> restoreFlow {
        subject operation : RestoreFromSnapshot;
        require constraint {
            doc /* Construct and semantically validate all four candidate component states before replacing any current component. Invoke each state owner's public full-snapshot replacement action while controller reads and writes are excluded. Success exposes the coordinated domain state as one serialized visible change; a component failure invokes the same public replacement actions with the captured preimage before returning ordinary failure. Completed compensation preserves the complete prior domain state; failed compensation reports RtgControllerRecoveryIndeterminate and makes no coordinated-state claim. */
        }
    }

    requirement <'contract.rtg.controller.operation_results'> operationResultSemantics {
        subject controller : RtgController;
        require constraint {
            doc /* State-changing results use only applied, cutover_applied, cutover_failed, migration_abandoned, snapshot_persisted, or restore_applied. generatedIds maps every request-local reference resolved by that operation and is empty when none are generated. Zero visible state change reports zero applied counts; validationReport is absent when skipped; details carries operation-specific JSON-safe domain evidence. Runtime traces and cursors are supplied outside this result. */
        }
    }

    requirement <'invariant.rtg.controller.public_contracts_only'> publicContractsOnly {
        subject controller : RtgController;
        require constraint {
            doc /* Lower components are used only through public contracts, including snapshot replacement and compensation; no private host-swapping callback may replace a runtime-managed occurrence. */
        }
    }

    requirement <'invariant.rtg.controller.no_transport_ownership'> noTransportOwnership {
        subject controller : RtgController;
        require constraint {
            doc /* Controller owns no MCP, REST, CLI, SDK, or UI transport. */
        }
    }

    requirement <'contract.rtg.controller.intentional_boundary'> intentionalBoundary {
        subject controller : RtgController;
        require constraint {
            doc /* The controller owns RTG saga sequencing, compensation, coordinated snapshot export/restore, and snapshot persistence through its JSON collaborator, not lower-store records or algorithms. It owns no traffic ledger, generic history/replay, runtime trace/cursor, authentication/authorization, UI or transport, storage-engine mechanics, replication/deployment topology, distributed lock, or distributed transaction guarantee. Curated discovery-view state remains outside v1. */
        }
    }

    requirement <'invariant.rtg.controller.validates_before_required_mutation'> validatesBeforeRequiredMutation {
        subject controller : RtgController;
        require constraint {
            doc /* Strict mutation validates the projected state before apply. */
        }
    }

    requirement <'invariant.rtg.controller.strict_validation_default'> strictValidationDefault {
        subject controller : RtgController;
        require constraint {
            doc /* Normal mutation defaults to strict validation. */
        }
    }

    requirement <'invariant.rtg.controller.live_graph_lane_excludes_knowledge_engineering'> liveGraphLaneExcludesKnowledgeEngineering {
        subject controller : RtgController;
        require constraint {
            doc /* Live CRUD excludes schema, constraint, migration, and non-live work. */
        }
    }

    requirement <'invariant.rtg.controller.knowledge_changes_are_migration_scoped'> knowledgeChangesMigrationScoped {
        subject controller : RtgController;
        require constraint {
            doc /* Non-live knowledge changes belong to active migration work. */
        }
    }

    requirement <'invariant.rtg.controller.cutover_is_only_live_flip_authority_for_staged_schema_constraints'> cutoverOnlyLiveFlipAuthority {
        subject controller : RtgController;
        require constraint {
            doc /* Cutover is the only authority for staged schema and constraint live flips. */
        }
    }

    requirement <'invariant.rtg.controller.normalized_batches_are_internal_controller_plans'> normalizedBatchesInternalPlans {
        subject controller : RtgController;
        require constraint {
            doc /* Normalized batches are internal plans, not a generic public mutation backdoor. */
        }
    }

    requirement <'invariant.rtg.controller.schema_constraint_changes_use_migrations'> schemaConstraintChangesUseMigrations {
        subject controller : RtgController;
        require constraint {
            doc /* Schema and constraint writes use migration workflows. */
        }
    }

    requirement <'invariant.rtg.controller.schema_constraint_deletion_uses_migrations'> schemaConstraintDeletionUsesMigrations {
        subject controller : RtgController;
        require constraint {
            doc /* Schema and constraint retirement/deletion uses migration workflows. */
        }
    }

    requirement <'invariant.rtg.controller.non_live_candidates_are_migration_scoped'> nonLiveCandidatesMigrationScoped {
        subject controller : RtgController;
        require constraint {
            doc /* Non-live candidates are referenced by active migration membership. */
        }
    }

    requirement <'invariant.rtg.controller.system_invariants_owned'> systemInvariantsOwned {
        subject controller : RtgController;
        require constraint {
            doc /* Cross-component invariants are enforced by the controller. */
        }
    }

    requirement <'invariant.rtg.controller.validation_report_authoritative'> validationReportAuthoritative {
        subject controller : RtgController;
        require constraint {
            doc /* Blocking validation findings control strict acceptance. */
        }
    }

    requirement <'invariant.rtg.controller.snapshot_uses_component_snapshots'> snapshotUsesComponentSnapshots {
        subject controller : RtgController;
        require constraint {
            doc /* Coordinated snapshots are assembled through component snapshot contracts. */
        }
    }

    requirement <'invariant.rtg.controller.snapshot_json_serializable'> snapshotJsonSerializable {
        subject controller : RtgController;
        require constraint {
            doc /* Exported system snapshots are JSON-serializable. */
        }
    }

    requirement <'invariant.rtg.controller.persisted_snapshot_readback_is_storage_scoped'> persistedSnapshotStorageScoped {
        subject controller : RtgController;
        require constraint {
            doc /* Snapshot readback is limited to JSON storage documents. */
        }
    }

    requirement <'invariant.rtg.controller.cutover_uses_migration_membership'> cutoverUsesMigrationMembership {
        subject controller : RtgController;
        require constraint {
            doc /* Cutover applies exactly the selected migration membership. */
        }
    }

    requirement <'invariant.rtg.controller.reads_do_not_observe_transient_cutover'> readsHideTransientState {
        subject controller : RtgController;
        require constraint {
            doc /* Reads do not observe transient cutover or restore state. */
        }
    }

    requirement <'invariant.rtg.controller.projected_queries_use_live_overlay'> projectedQueriesUseLiveOverlay {
        subject controller : RtgController;
        require constraint {
            doc /* Projected validation uses explicit live-status overlays. */
        }
    }

    requirement <'invariant.rtg.controller.cutover_restores_on_failure'> cutoverRestoresOnFailure {
        subject controller : RtgController;
        require constraint {
            doc /* Failed cutover restores the pre-cutover visible state when compensation completes; compensation failure is explicitly recovery-indeterminate and never reported as an ordinary restored cutover failure. */
        }
    }

    requirement <'invariant.rtg.controller.failed_cutover_is_legible'> failedCutoverLegible {
        subject controller : RtgController;
        require constraint {
            doc /* Failed cutover records actionable diagnostic status. */
        }
    }

    requirement <'invariant.rtg.controller.cutover_order'> cutoverOrder {
        subject controller : RtgController;
        require constraint {
            doc /* Cutover ordering preserves referenced state and validation. */
        }
    }

    requirement <'invariant.rtg.controller.abandonment_never_deletes_live_records'> abandonmentNeverDeletesLive {
        subject controller : RtgController;
        require constraint {
            doc /* Abandonment never deletes live records. */
        }
    }

    requirement <'invariant.rtg.controller.one_write_at_a_time'> oneWriteAtATime {
        subject controller : RtgController;
        require constraint {
            doc /* Only one controller write mutates coordinated RTG domain state at a time. */
        }
    }

    requirement <'invariant.rtg.controller.resolved_uuids_before_mutation'> resolvedUuidsBeforeMutation {
        subject controller : RtgController;
        require constraint {
            doc /* Batch-local references are resolved before validation and mutation so generated identities are stable in the domain result and runtime canonical effect. */
        }
    }

    requirement <'invariant.rtg.controller.write_atomicity_scoped'> writeAtomicityScoped {
        subject controller : RtgController;
        require constraint {
            doc /* Failed normalized apply restores touched component state within the controller scope. */
        }
    }

    requirement <'invariant.rtg.controller.reads_mediated'> readsMediated {
        subject controller : RtgController;
        require constraint {
            doc /* Application reads pass through controller public contracts. */
        }
    }

    requirement <'invariant.rtg.controller.live_flips_via_full_record_write'> liveFlipsViaFullRecordWrite {
        subject controller : RtgController;
        require constraint {
            doc /* Live-status changes preserve complete public records. */
        }
    }

    requirement <'invariant.rtg.controller.graph_type_is_schema_type_key'> graphTypeIsSchemaTypeKey {
        subject controller : RtgController;
        require constraint {
            doc /* Graph object type values correspond to schema type keys. */
        }
    }

    requirement <'contract.rtg.controller.apply_live_graph_changes.failures'> applyLiveGraphChangesFailureSemantics {
        subject operation : ApplyLiveGraphChanges;
        require constraint {
            doc /* Strict rejection has no graph effect; apply failure restores touched component state and remains visible in the domain outcome. */
        }
    }

    requirement <'contract.rtg.controller.validate_live_graph_changes.failures'> validateLiveGraphChangesFailureSemantics {
        subject operation : ValidateLiveGraphChanges;
        require constraint {
            doc /* Every rejected validation attempt leaves component state unchanged. */
        }
    }

    requirement <'contract.rtg.controller.stage_knowledge_changes.failures'> stageKnowledgeChangesFailureSemantics {
        subject operation : StageKnowledgeChanges;
        require constraint {
            doc /* Rejected staging has no effect; failed apply restores touched state and returns the visible domain outcome. */
        }
    }

    requirement <'contract.rtg.controller.apply_migration_cutover.failures'> applyMigrationCutoverFailureSemantics {
        subject operation : ApplyMigrationCutover;
        require constraint {
            doc /* A failed cutover with completed compensation restores the pre-cutover visible state, preserves the documented failed-migration status when safe, and returns a legible failed outcome. If compensation fails, RtgControllerRecoveryIndeterminate identifies unconfirmed coordinated state; a runtime binding assigns an indeterminate trace disposition so reconstruction excludes the trace. */
        }
    }

    requirement <'contract.rtg.controller.execute_controller_query.failures'> executeControllerQueryFailureSemantics {
        subject operation : ExecuteControllerQuery;
        require constraint {
            doc /* Query failures have no component state effect. */
        }
    }

    requirement <'contract.rtg.controller.controller_get_object.failures'> controllerGetObjectFailureSemantics {
        subject operation : ControllerGetObject;
        require constraint {
            doc /* Invalid UUID text or an absent graph object produces RtgControllerObjectNotFound with corrective diagnostics and has no state effect. */
        }
    }

    requirement <'contract.rtg.controller.controller_list_migrations.failures'> controllerListMigrationsFailureSemantics {
        subject operation : ControllerListMigrations;
        require constraint {
            doc /* Listing has no state effect. */
        }
    }

    requirement <'contract.rtg.controller.controller_get_migration.failures'> controllerGetMigrationFailureSemantics {
        subject operation : ControllerGetMigration;
        require constraint {
            doc /* Read failure has no state effect. */
        }
    }

    requirement <'contract.rtg.controller.validate_graph.failures'> validateGraphFailureSemantics {
        subject operation : ValidateGraph;
        require constraint {
            doc /* Validation has no component state effect. */
        }
    }

    requirement <'contract.rtg.controller.discover_anchor_types.failures'> discoverAnchorTypesFailureSemantics {
        subject operation : DiscoverAnchorTypes;
        require constraint {
            doc /* Discovery has no state effect. */
        }
    }

    requirement <'contract.rtg.controller.get_controller_schema_pack.failures'> getControllerSchemaPackFailureSemantics {
        subject operation : GetControllerSchemaPack;
        require constraint {
            doc /* Schema-pack reads have no state effect. */
        }
    }

    requirement <'contract.rtg.controller.get_system_state.failures'> getSystemStateFailureSemantics {
        subject operation : GetSystemState;
        require constraint {
            doc /* System-state inspection has no state effect. */
        }
    }

    requirement <'contract.rtg.controller.export_system_snapshot.failures'> exportSystemSnapshotFailureSemantics {
        subject operation : ExportSystemSnapshot;
        require constraint {
            doc /* Export returns one coordinated state and does not mutate components. */
        }
    }

    requirement <'contract.rtg.controller.persist_system_snapshot.failures'> persistSystemSnapshotFailureSemantics {
        subject operation : PersistSystemSnapshot;
        require constraint {
            doc /* Failure leaves no partial JSON document and remains visible as the operation outcome. */
        }
    }

    requirement <'contract.rtg.controller.list_persisted_snapshots.failures'> listPersistedSnapshotsFailureSemantics {
        subject operation : ListPersistedSnapshots;
        require constraint {
            doc /* Listing is storage-scoped and has no state effect. */
        }
    }

    requirement <'contract.rtg.controller.load_persisted_snapshot.failures'> loadPersistedSnapshotFailureSemantics {
        subject operation : LoadPersistedSnapshot;
        require constraint {
            doc /* Loading does not restore or otherwise mutate current system state. */
        }
    }

    requirement <'contract.rtg.controller.abandon_migration.failures'> abandonMigrationFailureSemantics {
        subject operation : AbandonMigration;
        require constraint {
            doc /* Abandonment never deletes live records; failure restores touched state and returns the outcome. */
        }
    }

    requirement <'contract.rtg.controller.restore_from_snapshot.failures'> restoreFromSnapshotFailureSemantics {
        subject operation : RestoreFromSnapshot;
        require constraint {
            doc /* Invalid restoration and replacement failure with completed compensation leave the prior coordinated state visible. If compensation fails, RtgControllerRecoveryIndeterminate identifies unconfirmed coordinated state; a runtime binding assigns an indeterminate trace disposition so reconstruction excludes the trace rather than claiming rollback. */
        }
    }

    requirement <'contract.rtg.controller.open_rtg_controller.failures'> openRtgControllerFailureSemantics {
        subject operation : OpenRtgController;
        require constraint {
            doc /* Invalid or incompatible dependencies do not return a partially usable controller. */
        }
    }

    part contractContext {
        part controller : RtgController;
        satisfy liveMutationFlow by controller.applyLiveGraphChanges;
        satisfy liveMutationLane by controller.applyLiveGraphChanges;
        satisfy stagingFlow by controller.stageKnowledgeChanges;
        satisfy validationFlow by controller.validateLiveGraphChanges;
        satisfy cutoverFlow by controller.applyMigrationCutover;
        satisfy cutoverSequence by controller.applyMigrationCutover;
        satisfy abandonmentFlow by controller.abandonMigration;
        satisfy stableQueryFlow by controller.executeQuery;
        satisfy controllerReadSemantics by controller;
        satisfy discoverySemantics by controller;
        satisfy persistedSnapshotSemantics by controller;
        satisfy operationResultSemantics by controller;
        satisfy publicContractsOnly by controller;
        satisfy noTransportOwnership by controller;
        satisfy intentionalBoundary by controller;
        satisfy validatesBeforeRequiredMutation by controller;
        satisfy strictValidationDefault by controller;
        satisfy liveGraphLaneExcludesKnowledgeEngineering by controller;
        satisfy knowledgeChangesMigrationScoped by controller;
        satisfy cutoverOnlyLiveFlipAuthority by controller;
        satisfy normalizedBatchesInternalPlans by controller;
        satisfy schemaConstraintChangesUseMigrations by controller;
        satisfy schemaConstraintDeletionUsesMigrations by controller;
        satisfy nonLiveCandidatesMigrationScoped by controller;
        satisfy systemInvariantsOwned by controller;
        satisfy validationReportAuthoritative by controller;
        satisfy snapshotUsesComponentSnapshots by controller;
        satisfy snapshotJsonSerializable by controller;
        satisfy persistedSnapshotStorageScoped by controller;
        satisfy cutoverUsesMigrationMembership by controller;
        satisfy readsHideTransientState by controller;
        satisfy projectedQueriesUseLiveOverlay by controller;
        satisfy cutoverRestoresOnFailure by controller;
        satisfy failedCutoverLegible by controller;
        satisfy cutoverOrder by controller;
        satisfy abandonmentNeverDeletesLive by controller;
        satisfy oneWriteAtATime by controller;
        satisfy resolvedUuidsBeforeMutation by controller;
        satisfy writeAtomicityScoped by controller;
        satisfy readsMediated by controller;
        satisfy liveFlipsViaFullRecordWrite by controller;
        satisfy graphTypeIsSchemaTypeKey by controller;
        satisfy systemStateSemantics by controller.getSystemState;
        satisfy coordinatedSnapshotFlow by controller.exportSystemSnapshot;
        satisfy restoreFlow by controller.restoreFromSnapshot;

        satisfy applyLiveGraphChangesFailureSemantics by controller.applyLiveGraphChanges;
        satisfy validateLiveGraphChangesFailureSemantics by controller.validateLiveGraphChanges;
        satisfy stageKnowledgeChangesFailureSemantics by controller.stageKnowledgeChanges;
        satisfy applyMigrationCutoverFailureSemantics by controller.applyMigrationCutover;
        satisfy executeControllerQueryFailureSemantics by controller.executeQuery;
        satisfy controllerGetObjectFailureSemantics by controller.getObject;
        satisfy controllerListMigrationsFailureSemantics by controller.listMigrations;
        satisfy controllerGetMigrationFailureSemantics by controller.getMigration;
        satisfy validateGraphFailureSemantics by controller.validateGraph;
        satisfy discoverAnchorTypesFailureSemantics by controller.discoverAnchorTypes;
        satisfy getControllerSchemaPackFailureSemantics by controller.getSchemaPack;
        satisfy getSystemStateFailureSemantics by controller.getSystemState;
        satisfy exportSystemSnapshotFailureSemantics by controller.exportSystemSnapshot;
        satisfy persistSystemSnapshotFailureSemantics by controller.persistSystemSnapshot;
        satisfy listPersistedSnapshotsFailureSemantics by controller.listPersistedSnapshots;
        satisfy loadPersistedSnapshotFailureSemantics by controller.loadPersistedSnapshot;
        satisfy abandonMigrationFailureSemantics by controller.abandonMigration;
        satisfy restoreFromSnapshotFailureSemantics by controller.restoreFromSnapshot;
        action openRtgControllerSubject : OpenRtgController;
        satisfy openRtgControllerFailureSemantics by openRtgControllerSubject;
    }

    verification def ApplyLiveGraphChangesContractVerification {
        subject operation : ApplyLiveGraphChanges;
        objective {
            verify liveMutationFlow;
            verify liveMutationLane;

            verify applyLiveGraphChangesFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py#ApplyLiveGraphChangesContractVerification";
            implementationScope = "InProcessRtgController";
        }
    }

    verification def StageKnowledgeChangesContractVerification {
        subject operation : StageKnowledgeChanges;
        objective {
            verify stagingFlow;

            verify stageKnowledgeChangesFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py#StageKnowledgeChangesContractVerification";
            implementationScope = "InProcessRtgController";
        }
    }

    verification def ValidateLiveGraphChangesContractVerification {
        subject operation : ValidateLiveGraphChanges;
        objective {
            verify validationFlow;

            verify validateLiveGraphChangesFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py#ValidateLiveGraphChangesContractVerification";
            implementationScope = "InProcessRtgController";
        }
    }

    verification def ApplyMigrationCutoverContractVerification {
        subject operation : ApplyMigrationCutover;
        objective {
            verify cutoverFlow;
            verify cutoverSequence;

            verify applyMigrationCutoverFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py#ApplyMigrationCutoverContractVerification";
            implementationScope = "InProcessRtgController";
        }
    }

    verification def AbandonMigrationContractVerification {
        subject operation : AbandonMigration;
        objective {
            verify abandonmentFlow;

            verify abandonMigrationFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py#AbandonMigrationContractVerification";
            implementationScope = "InProcessRtgController";
        }
    }

    verification def ExecuteControllerQueryContractVerification {
        subject operation : ExecuteControllerQuery;
        objective {
            verify stableQueryFlow;

            verify executeControllerQueryFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py#ExecuteControllerQueryContractVerification";
            implementationScope = "InProcessRtgController";
        }
    }

    verification def GetSystemStateContractVerification {
        subject operation : GetSystemState;
        objective {
            verify systemStateSemantics;

            verify getSystemStateFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py#GetSystemStateContractVerification";
            implementationScope = "InProcessRtgController";
        }
    }

    verification def ExportSystemSnapshotContractVerification {
        subject operation : ExportSystemSnapshot;
        objective {
            verify coordinatedSnapshotFlow;

            verify exportSystemSnapshotFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py#ExportSystemSnapshotContractVerification";
            implementationScope = "InProcessRtgController";
        }
    }

    verification def RestoreFromSnapshotContractVerification {
        subject operation : RestoreFromSnapshot;
        objective {
            verify restoreFlow;

            verify restoreFromSnapshotFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py#RestoreFromSnapshotContractVerification";
            implementationScope = "InProcessRtgController";
        }
    }

    verification def ControllerGetObjectContractVerification {
        subject operation : ControllerGetObject;
        objective { verify controllerGetObjectFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py#ControllerGetObjectContractVerification"; implementationScope = "InProcessRtgController"; }
    }

    verification def ControllerListMigrationsContractVerification {
        subject operation : ControllerListMigrations;
        objective { verify controllerListMigrationsFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py#ControllerListMigrationsContractVerification"; implementationScope = "InProcessRtgController"; }
    }

    verification def ControllerGetMigrationContractVerification {
        subject operation : ControllerGetMigration;
        objective { verify controllerGetMigrationFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py#ControllerGetMigrationContractVerification"; implementationScope = "InProcessRtgController"; }
    }

    verification def ValidateGraphContractVerification {
        subject operation : ValidateGraph;
        objective { verify validateGraphFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py#ValidateGraphContractVerification"; implementationScope = "InProcessRtgController"; }
    }

    verification def DiscoverAnchorTypesContractVerification {
        subject operation : DiscoverAnchorTypes;
        objective { verify discoverAnchorTypesFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py#DiscoverAnchorTypesContractVerification"; implementationScope = "InProcessRtgController"; }
    }

    verification def GetControllerSchemaPackContractVerification {
        subject operation : GetControllerSchemaPack;
        objective { verify getControllerSchemaPackFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py#GetControllerSchemaPackContractVerification"; implementationScope = "InProcessRtgController"; }
    }

    verification def PersistSystemSnapshotContractVerification {
        subject operation : PersistSystemSnapshot;
        objective { verify persistSystemSnapshotFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py#PersistSystemSnapshotContractVerification"; implementationScope = "InProcessRtgController"; }
    }

    verification def ListPersistedSnapshotsContractVerification {
        subject operation : ListPersistedSnapshots;
        objective { verify listPersistedSnapshotsFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py#ListPersistedSnapshotsContractVerification"; implementationScope = "InProcessRtgController"; }
    }

    verification def LoadPersistedSnapshotContractVerification {
        subject operation : LoadPersistedSnapshot;
        objective { verify loadPersistedSnapshotFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py#LoadPersistedSnapshotContractVerification"; implementationScope = "InProcessRtgController"; }
    }

    verification def OpenRtgControllerContractVerification {
        subject operation : OpenRtgController;
        objective { verify openRtgControllerFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py#OpenRtgControllerContractVerification"; implementationScope = "InProcessRtgController"; }
    }



    verification def RtgControllerBoundaryVerification {
        subject controller : RtgController;
        objective {
            verify controllerReadSemantics;
            verify discoverySemantics;
            verify persistedSnapshotSemantics;
            verify operationResultSemantics;
            verify publicContractsOnly;
            verify noTransportOwnership;
            verify intentionalBoundary;
            verify validatesBeforeRequiredMutation;
            verify strictValidationDefault;
            verify liveGraphLaneExcludesKnowledgeEngineering;
            verify knowledgeChangesMigrationScoped;
            verify cutoverOnlyLiveFlipAuthority;
            verify normalizedBatchesInternalPlans;
            verify schemaConstraintChangesUseMigrations;
            verify schemaConstraintDeletionUsesMigrations;
            verify nonLiveCandidatesMigrationScoped;
            verify systemInvariantsOwned;
            verify validationReportAuthoritative;
            verify snapshotUsesComponentSnapshots;
            verify snapshotJsonSerializable;
            verify persistedSnapshotStorageScoped;
            verify cutoverUsesMigrationMembership;
            verify readsHideTransientState;
            verify projectedQueriesUseLiveOverlay;
            verify cutoverRestoresOnFailure;
            verify failedCutoverLegible;
            verify cutoverOrder;
            verify abandonmentNeverDeletesLive;
            verify oneWriteAtATime;
            verify resolvedUuidsBeforeMutation;
            verify writeAtomicityScoped;
            verify readsMediated;
            verify liveFlipsViaFullRecordWrite;
            verify graphTypeIsSchemaTypeKey;
        }
        @EvidenceBinding { evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py#RtgControllerBoundaryVerification"; implementationScope = "InProcessRtgController"; }
    }
}
