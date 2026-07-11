library package BibliotekRtgController {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;
    private import BibliotekStorageJsonFile::*;
    private import BibliotekStorageSql::*;
    private import BibliotekRtgGraph::*;
    private import BibliotekRtgSchema::*;
    private import BibliotekRtgConstraints::*;
    private import BibliotekRtgMigration::*;
    private import BibliotekRtgQuery::*;
    private import BibliotekRtgChangeValidation::*;

    enum def RtgControllerValidationMode { enum strict; enum skip; }
    enum def RtgControllerFailureRestore {
        enum <'restore_pre_cutover_snapshot'> restorePreCutoverSnapshot;
    }
    enum def RtgControllerLedgerMode { enum record; enum skip; }
    enum def RtgControllerOperationStatus {
        enum applied;
        enum <'cutover_applied'> cutoverApplied;
        enum <'cutover_failed'> cutoverFailed;
        enum <'migration_abandoned'> migrationAbandoned;
        enum <'snapshot_persisted'> snapshotPersisted;
        enum <'restore_applied'> restoreApplied;
        enum <'replay_applied'> replayApplied;
        enum <'ledger_failures_flushed'> ledgerFailuresFlushed;
    }
    enum def RtgControllerValidationStatus { enum validated; }
    enum def RtgControllerReplayVerificationStatus {
        enum <'replay_verified'> replayVerified;
    }
    enum def RtgControllerMutationState {
        enum <'not_mutated'> notMutated;
    }
    enum def RtgControllerStateClassification {
        enum empty; enum schemaOnly; enum populated; enum hasStagedWork; enum needsReplay;
    }
    enum def RtgControllerWorkflow {
        enum schemaBootstrap; enum dataIngest; enum queryAnswer; enum safeUpdate;
        enum snapshotReplayCheck; enum stagedWorkReview; enum replayRecovery;
    }
    enum def RtgControllerMigrationCountScope {
        enum <'current_migration_store'> currentMigrationStore;
    }
    enum def RtgControllerLedgerRecordKind { enum request; enum response; enum error; }
    enum def RtgControllerMigrationEventType {
        enum staged;
        enum <'cutover_applied'> cutoverApplied;
        enum <'cutover_failed'> cutoverFailed;
        enum abandoned;
    }
    attribute def RtgControllerValidationTrackChoice {
        doc /* Externally encoded as either the literal "all" or a non-empty unique ordered list of RtgValidationTrack literals. */
    }
    attribute def RtgControllerValidationOptions { attribute tracks[0..1] : RtgControllerValidationTrackChoice; attribute findingLimit[0..1] : Integer; doc /* Omitted tracks means "all" and an absent finding limit means unlimited; a present limit is positive and limits returned findings without changing acceptance. */ }
    attribute def RtgControllerCutoverOptions { attribute validationMode : RtgControllerValidationMode = RtgControllerValidationMode::strict; attribute pruneRetired : Boolean = true; attribute failureRestore : RtgControllerFailureRestore = RtgControllerFailureRestore::restorePreCutoverSnapshot; }
    attribute def RtgControllerDiscoveryOptions { attribute includeNonLive : Boolean = false; attribute limit[0..1] : Integer; }
    attribute def RtgControllerSchemaPackOptions { attribute live[0..1] : Boolean = true; attribute includeLiveCounts : Boolean = true; }
    attribute def RtgControllerReplayOptions {
        attribute startSnapshot[0..1] : RtgSystemSnapshot;
        attribute startSnapshotPath[0..1] : JsonRelativePath;
        attribute afterLedgerPosition[0..1] : Integer;
        attribute throughLedgerPosition[0..1] : Integer;
    }
    attribute def RtgControllerRestoreOptions { attribute ledgerMode : RtgControllerLedgerMode = RtgControllerLedgerMode::record; }
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
        attribute transactionId : Uuid;
        attribute ledgerPosition[0..1] : Integer;
        attribute appliedChanges : RtgControllerAppliedChanges;
        attribute validationReport[0..1] : RtgValidationReport;
        attribute snapshot[0..1] : RtgSystemSnapshot;
        attribute details : JsonObject;
    }
    attribute def RtgControllerLiveGraphValidationResult { attribute status : RtgControllerValidationStatus; attribute mutationState : RtgControllerMutationState; attribute accepted : Boolean; attribute generatedIds : JsonObject; attribute resolvedGraphChanges : RtgGraphChangeSet; attribute validationReport : RtgValidationReport; doc /* generatedIds maps each request-local reference to its resolved UUID exactly as apply would. */ }
    attribute def RtgControllerReplayVerificationResult {
        attribute status : RtgControllerReplayVerificationStatus;
        attribute ledgerRecordsSeen : Integer;
        attribute mutatingRequestsReplayed : Integer;
        attribute replayWindow : JsonObject;
        attribute preSummary : JsonObject;
        attribute postSummary : JsonObject;
        attribute countDiffs : JsonObject;
        attribute validationReport : RtgValidationReport;
    }
    attribute def RtgControllerMigrationHistoryEvent { attribute eventType : RtgControllerMigrationEventType; attribute migrationId : String; attribute description[0..1] : String; attribute transactionId : Uuid; attribute ledgerPosition : Integer; attribute status : String; attribute recordedAt : Timestamp; attribute summary : String; }
    attribute def RtgControllerMigrationHistory { attribute events[0..*] : RtgControllerMigrationHistoryEvent; }
    attribute def RtgControllerLedgerFailureRecord {
        attribute transactionId : Uuid;
        attribute ledgerPosition[0..1] : Integer;
        attribute operationName : String;
        attribute recordKind : RtgControllerLedgerRecordKind;
        attribute payloadJson : String;
        attribute failureMessage : String;
        attribute retryCount : Integer;
        attribute firstFailedTimestamp : Timestamp;
        attribute lastFailedTimestamp : Timestamp;
    }
    item def RtgControllerLedger {
        attribute position : Integer;
        attribute queuedFailures[0..*] : RtgControllerLedgerFailureRecord;
    }
    attribute def RtgSystemSnapshot { attribute graph : RtgGraphSnapshot; attribute schema : RtgSchemaSnapshot; attribute constraints : RtgConstraintSnapshot; attribute migration : RtgMigrationSnapshot; attribute lastLedgerPosition[0..1] : Integer; attribute lastTransactionId[0..1] : Uuid; attribute lastTransactionTimestamp[0..1] : Timestamp; }
    attribute def RtgAnchorTypeDiscoveryEntry { attribute typeKey : String; attribute description : String; attribute liveCount : Integer; }
    attribute def RtgAnchorTypeDiscoveryResult { attribute anchorTypes[0..*] : RtgAnchorTypeDiscoveryEntry; }
    attribute def RtgControllerSchemaPack { attribute schemaPack : RtgSchemaPack; attribute liveCounts : JsonObject; }
    attribute def RtgPersistedSnapshotMetadata { attribute relativePath : JsonRelativePath; attribute sizeBytes : Integer; attribute modifiedAt : Timestamp; }
    attribute def RtgControllerSystemState {
        attribute stateClassification : RtgControllerStateClassification;
        attribute liveSchemaCounts : JsonObject;
        attribute liveObjectCounts : JsonObject;
        attribute nonLiveCandidateCounts : JsonObject;
        attribute migrationCountsByStatus : JsonObject;
        attribute migrationCountsScope : RtgControllerMigrationCountScope = RtgControllerMigrationCountScope::currentMigrationStore;
        attribute migrationHistoryHint[0..1] : String;
        attribute persistedSnapshotPaths[0..*] : JsonRelativePath;
        attribute ledgerRecordCount : Integer;
        attribute lastLedgerPosition[0..1] : Integer;
        attribute lastTransactionId[0..1] : Uuid;
        attribute recommendedWorkflows[0..*] : RtgControllerWorkflow;
        attribute recommendedNextSteps[0..*] : String;
    }
    attribute def RtgPersistedSnapshotList { attribute snapshots[0..*] : RtgPersistedSnapshotMetadata; }
    attribute def RtgPersistedSnapshotDocument { attribute relativePath : JsonRelativePath; attribute snapshot : RtgSystemSnapshot; }

    attribute def RtgControllerConfigurationInvalid { attribute message : String; attribute diagnostic : JsonObject; }
    attribute def RtgControllerValidationFailed { attribute message : String; attribute transactionId[0..1] : Uuid; attribute validationReport[0..1] : RtgValidationReport; attribute diagnostic : JsonObject; }
    attribute def RtgControllerPreconditionFailed { attribute message : String; attribute diagnostic : JsonObject; }
    attribute def RtgControllerApplyFailed { attribute message : String; attribute diagnostic : JsonObject; }
    attribute def RtgControllerObjectNotFound { attribute message : String; attribute diagnostic : JsonObject; }
    attribute def RtgControllerDiscoveryFailed { attribute message : String; attribute diagnostic : JsonObject; }
    attribute def RtgControllerSnapshotFailed { attribute message : String; attribute diagnostic : JsonObject; }
    attribute def RtgControllerReplayFailed { attribute message : String; attribute diagnostic : JsonObject; }

    action def ApplyLiveGraphChanges { in graphChanges : RtgGraphChangeSet; in validationMode : RtgControllerValidationMode = RtgControllerValidationMode::strict; out result : RtgControllerOperationResult; doc /* Validate and apply normal live graph CRUD in the serialized mutation lane. */ @FailureContract { errorIds = ("RtgControllerValidationFailed", "RtgControllerApplyFailed"); obligation = "Strict rejection has no graph effect; apply failure restores touched component state and remains visible in the ledger outcome."; } }
    action def ValidateLiveGraphChanges { in graphChanges : RtgGraphChangeSet; in validationOptions[0..1] : RtgControllerValidationOptions; out result : RtgControllerLiveGraphValidationResult; doc /* Normalize exactly as apply would and return generated identities, resolved changes, and validation without component or ledger mutation. */ @FailureContract { errorIds = ("RtgControllerPreconditionFailed", "RtgValidationInputInvalid"); obligation = "Every rejected validation attempt leaves component state and ledger unchanged and receives no controller transaction identifier."; } }
    action def StageKnowledgeChanges { in knowledgeChanges : RtgChangeBatch; in validationMode : RtgControllerValidationMode = RtgControllerValidationMode::strict; out result : RtgControllerOperationResult; doc /* Validate and stage migration-scoped non-live graph, schema, constraint, and migration records. */ @FailureContract { errorIds = ("RtgControllerValidationFailed", "RtgControllerPreconditionFailed", "RtgControllerApplyFailed"); obligation = "Rejected staging has no effect; failed apply restores touched state and records the visible outcome."; } }
    action def ApplyMigrationCutover { in migrationId : String; in cutoverOptions[0..1] : RtgControllerCutoverOptions; out result : RtgControllerOperationResult; doc /* Apply exactly one migration membership in reference-safe order, validate the result, and either commit or restore. */ @FailureContract { errorIds = ("RtgControllerPreconditionFailed", "RtgControllerValidationFailed", "RtgControllerApplyFailed"); obligation = "A failed cutover restores the pre-cutover visible state and records a legible failed outcome."; } }
    action def ExecuteControllerQuery { in querySpec : RtgQuerySpec; in queryOptions[0..1] : RtgQueryOptions; out result : RtgQueryResult; doc /* Execute against one coherent graph view while controller mutations are excluded; do not append a mutation ledger record. */ @FailureContract { errorIds = ("RtgQuerySpecInvalid", "RtgQueryUnsupported"); obligation = "Query failures have no component or ledger effect."; } }
    action def ControllerGetObject { in objectUuid : String; out ref object : RtgObject; doc /* Normalize UUID text and return the public graph record without lifecycle filtering. */ @FailureContract { errorIds = ("RtgControllerObjectNotFound"); obligation = "Read failure has no state or ledger effect."; } }
    action def ControllerListMigrations { in status[0..1] : RtgMigrationStatus; out result : RtgMigrationRecordList; doc /* Return all migration records or one status in deterministic migration-ID order. */ @FailureContract { errorIds = ("RtgMigrationStatusInvalid"); obligation = "Listing has no state or ledger effect."; } }
    action def ControllerGetMigration { in migrationId : String; out result : RtgMigrationRecord; doc /* Return one migration tracking record by stable migration ID. */ @FailureContract { errorIds = ("RtgMigrationNotFound"); obligation = "Read failure has no state or ledger effect."; } }
    action def ValidateGraph { in migrationIds[0..*] : String; in validationOptions[0..1] : RtgControllerValidationOptions; out report : RtgValidationReport; doc /* Validate current state or named migration projections without mutation. */ @FailureContract { errorIds = ("RtgControllerValidationFailed"); obligation = "Validation has no component or ledger effect."; } }
    action def DiscoverAnchorTypes { in discoveryOptions[0..1] : RtgControllerDiscoveryOptions; out result : RtgAnchorTypeDiscoveryResult; doc /* Compose schema summaries and graph counts; absent options exclude non-live types and impose no limit. */ @FailureContract { errorIds = ("RtgControllerDiscoveryFailed"); obligation = "Discovery has no state or ledger effect."; } }
    action def GetControllerSchemaPack { in anchorTypeKeys[1..*] : String; in schemaPackOptions[0..1] : RtgControllerSchemaPackOptions; out result : RtgControllerSchemaPack; doc /* Return the schema closure for named anchors and, by default, current live counts. */ @FailureContract { errorIds = ("RtgControllerDiscoveryFailed"); obligation = "Schema-pack reads have no state or ledger effect."; } }
    action def GetSystemState { out result : RtgControllerSystemState; doc /* Return a read-only classified summary, bounded history pointers, and recommended workflows. */ @FailureContract { errorIds = ("RtgControllerDiscoveryFailed"); obligation = "System-state inspection has no state or ledger effect."; } }
    action def ExportSystemSnapshot { out snapshot : RtgSystemSnapshot; doc /* Export all four component snapshots with the represented ledger cursor and transaction identity from one coordinated state. */ @FailureContract { errorIds = ("RtgControllerSnapshotFailed"); obligation = "Export returns one coordinated state and does not mutate components or ledger."; } }
    action def PersistSystemSnapshot { in relativePath : JsonRelativePath; out result : RtgControllerOperationResult; doc /* Export and atomically store one coordinated snapshot under JSON storage authority. */ @FailureContract { errorIds = ("RtgControllerSnapshotFailed"); obligation = "Failure leaves no partial JSON document and remains visible as the operation outcome."; } }
    action def ListPersistedSnapshots { out result : RtgPersistedSnapshotList; doc /* List only valid persisted system snapshots visible through the bound JSON storage root. */ @FailureContract { errorIds = ("RtgControllerSnapshotFailed"); obligation = "Listing is storage-scoped and has no state or ledger effect."; } }
    action def LoadPersistedSnapshot { in relativePath : JsonRelativePath; out result : RtgPersistedSnapshotDocument; doc /* Read and validate a persisted snapshot document without applying it. */ @FailureContract { errorIds = ("RtgControllerSnapshotFailed"); obligation = "Loading does not restore or otherwise mutate current system state."; } }
    action def AbandonMigration { in migrationId : String; in reason[0..1] : String; out result : RtgControllerOperationResult; doc /* Mark migration work abandoned and prune only safe non-live candidates owned by that migration. */ @FailureContract { errorIds = ("RtgControllerPreconditionFailed", "RtgControllerApplyFailed"); obligation = "Abandonment never deletes live records; failure restores touched state and records the outcome."; } }
    action def ReplayLedger { in replayOptions[0..1] : RtgControllerReplayOptions; out result : RtgControllerOperationResult; doc /* Reconstruct component state from an empty or explicit snapshot base and a monotonic ledger window. */ @FailureContract { errorIds = ("RtgControllerReplayFailed"); obligation = "Ambiguous replay inputs are rejected and replay does not append replayed activity to the source ledger."; } }
    action def VerifyReplayFromLedger { in replayOptions[0..1] : RtgControllerReplayOptions; out result : RtgControllerReplayVerificationResult; doc /* Replay into isolated state and compare pre/post summaries and validation without replacing current state. */ @FailureContract { errorIds = ("RtgControllerReplayFailed", "RtgControllerSnapshotFailed"); obligation = "Verification runs against isolated scratch state and has no current-state or source-ledger effect."; } }
    action def ListMigrationHistory { out result : RtgControllerMigrationHistory; doc /* Return migration-related controller events in ledger order, including durable failure outcomes. */ @FailureContract { errorIds = ("RtgControllerReplayFailed"); obligation = "History inspection has no component or ledger effect."; } }
    action def FlushLedgerFailures { out result : RtgControllerOperationResult; doc /* Retry queued audit records in original order and report the remaining degraded-audit state. */ @FailureContract { errorIds = (); obligation = "Successfully durable queued outcomes are removed; remaining failures stay queued and legible in the result rather than raising."; } }
    action def RestoreFromSnapshot { in snapshot : RtgSystemSnapshot; in restoreOptions[0..1] : RtgControllerRestoreOptions; out result : RtgControllerOperationResult; doc /* Validate then atomically replace coordinated component state, preserving or recording the ledger cursor as requested. */ @FailureContract { errorIds = ("RtgControllerSnapshotFailed"); obligation = "Invalid or failed restoration does not expose a partially restored coordinated state."; } }

    part def <'component.rtg.controller'> RtgController {
        doc /* Coordinate cross-component RTG invariants, mutation lanes, cutover, recovery, replay, and audit outcomes. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }

        ref part graph[1] : RtgGraph;
        ref part schema[1] : RtgSchema;
        ref part constraints[1] : RtgConstraints;
        ref part migration[1] : RtgMigration;
        ref part changeValidator[1] : RtgChangeValidator;
        ref part queryEngine[1] : RtgQueryEngine;
        ref part jsonStorage[1] : JsonFileStorage;
        ref part sqlStorage[1] : SqlStorage;

        ref item ledger : RtgControllerLedger {
            doc /* Independently durable canonical controller ledger and degraded-audit queue. */
        }

        perform action applyLiveGraphChanges[0..*] : ApplyLiveGraphChanges { doc /* serialized component mutation plus durable or queued ledger outcome. */ }
        perform action validateLiveGraphChanges[0..*] : ValidateLiveGraphChanges { doc /* read and project dependencies; no component or ledger mutation. */ }
        perform action stageKnowledgeChanges[0..*] : StageKnowledgeChanges { doc /* serialized migration-scoped staging plus ledger outcome. */ }
        perform action applyMigrationCutover[0..*] : ApplyMigrationCutover { doc /* serialized coordinated cutover or restoration plus ledger outcome. */ }
        perform action executeQuery[0..*] : ExecuteControllerQuery { doc /* coherent dependency read; no component or ledger mutation. */ }
        perform action getObject[0..*] : ControllerGetObject { doc /* read graph without mutation or ledger write. */ }
        perform action listMigrations[0..*] : ControllerListMigrations { doc /* read migration store without mutation or ledger write. */ }
        perform action getMigration[0..*] : ControllerGetMigration { doc /* read migration store without mutation or ledger write. */ }
        perform action validateGraph[0..*] : ValidateGraph { doc /* read/project dependencies without mutation or ledger write. */ }
        perform action discoverAnchorTypes[0..*] : DiscoverAnchorTypes { doc /* compose schema and count reads without mutation. */ }
        perform action getSchemaPack[0..*] : GetControllerSchemaPack { doc /* compose schema and count reads without mutation. */ }
        perform action getSystemState[0..*] : GetSystemState { doc /* summarize components, snapshots, and ledger without mutation. */ }
        perform action exportSystemSnapshot[0..*] : ExportSystemSnapshot { doc /* coordinated read of components and ledger cursor. */ }
        perform action persistSystemSnapshot[0..*] : PersistSystemSnapshot { doc /* write one atomic JSON snapshot document and record outcome. */ }
        perform action listPersistedSnapshots[0..*] : ListPersistedSnapshots { doc /* read storage-scoped snapshot metadata without mutation. */ }
        perform action loadPersistedSnapshot[0..*] : LoadPersistedSnapshot { doc /* read and decode one snapshot document without restoring it. */ }
        perform action abandonMigration[0..*] : AbandonMigration { doc /* serialized safe candidate pruning, migration transition, and ledger outcome. */ }
        perform action replayLedger[0..*] : ReplayLedger { doc /* replace component state with selected replay result without duplicating source ledger records. */ }
        perform action verifyReplayFromLedger[0..*] : VerifyReplayFromLedger { doc /* replay into isolated scratch state and compare without current-state mutation. */ }
        perform action listMigrationHistory[0..*] : ListMigrationHistory { doc /* read ordered migration-related ledger events. */ }
        perform action flushLedgerFailures[0..*] : FlushLedgerFailures { doc /* retry queued durable records and retain only failures. */ }
        perform action restoreFromSnapshot[0..*] : RestoreFromSnapshot { doc /* atomically replace coordinated state and honor ledger mode. */ }

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
        dependency systemStateLedgerStorage from getSystemState to sqlStorage { doc /* read durable ledger counts and pointers. */ }

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

        dependency replayGraph from replayLedger to graph { doc /* replace graph state with the reconstructed result. */ }
        dependency replaySchema from replayLedger to schema { doc /* replace schema state with the reconstructed result. */ }
        dependency replayConstraints from replayLedger to constraints { doc /* replace constraint state with the reconstructed result. */ }
        dependency replayMigration from replayLedger to migration { doc /* replace migration state with the reconstructed result. */ }
        dependency replaySql from replayLedger to sqlStorage { doc /* read the selected ascending durable ledger window. */ }
        dependency verifyReplayGraph from verifyReplayFromLedger to graph { doc /* compare current graph summary with isolated replay output without mutation. */ }
        dependency verifyReplaySchema from verifyReplayFromLedger to schema { doc /* compare current schema summary with isolated replay output without mutation. */ }
        dependency verifyReplayConstraints from verifyReplayFromLedger to constraints { doc /* compare current constraint summary with isolated replay output without mutation. */ }
        dependency verifyReplayMigration from verifyReplayFromLedger to migration { doc /* compare current migration summary with isolated replay output without mutation. */ }
        dependency verifyReplayValidation from verifyReplayFromLedger to changeValidator { doc /* validate isolated reconstructed state. */ }
        dependency verifyReplayQuery from verifyReplayFromLedger to queryEngine { doc /* evaluate validation patterns against isolated state. */ }
        dependency verifyReplaySql from verifyReplayFromLedger to sqlStorage { doc /* read the selected ledger window without changing it. */ }
        dependency historySql from listMigrationHistory to sqlStorage { doc /* read migration-related ledger records in ledger order. */ }
        dependency flushSql from flushLedgerFailures to sqlStorage { doc /* retry queued records against durable ledger storage. */ }

        dependency restoreGraph from restoreFromSnapshot to graph { doc /* replace graph state from the validated snapshot. */ }
        dependency restoreSchema from restoreFromSnapshot to schema { doc /* replace schema state from the validated snapshot. */ }
        dependency restoreConstraints from restoreFromSnapshot to constraints { doc /* replace constraint state from the validated snapshot. */ }
        dependency restoreMigration from restoreFromSnapshot to migration { doc /* replace migration state from the validated snapshot. */ }
        dependency restoreSql from restoreFromSnapshot to sqlStorage { doc /* preserve or record the ledger cursor as requested. */ }

        dependency liveMutationLedger from applyLiveGraphChanges to ledger {
            doc /* record the resolved request and its applied, rejected, failed, or degraded outcome. */
        }
        dependency stagingLedger from stageKnowledgeChanges to ledger {
            doc /* record the migration-scoped staging outcome. */
        }
        dependency cutoverLedger from applyMigrationCutover to ledger {
            doc /* record applied or failed cutover status after restoration handling. */
        }
        dependency stateLedger from getSystemState to ledger {
            doc /* report durable and queued ledger state without mutation. */
        }
        dependency exportLedger from exportSystemSnapshot to ledger {
            doc /* capture the represented ledger cursor and transaction identity. */
        }
        dependency persistLedger from persistSystemSnapshot to ledger {
            doc /* capture the represented cursor and record the persistence outcome. */
        }
        dependency abandonLedger from abandonMigration to ledger {
            doc /* record the abandonment outcome after candidate handling. */
        }
        dependency replayLedgerAccess from replayLedger to ledger {
            doc /* reconstruct from the selected monotonic ledger window without recording replayed requests again. */
        }
        dependency verifyReplayLedger from verifyReplayFromLedger to ledger {
            doc /* read the source replay window without replacing current state or appending replayed activity. */
        }
        dependency historyLedger from listMigrationHistory to ledger {
            doc /* return migration events in ledger order without mutation. */
        }
        dependency flushLedger from flushLedgerFailures to ledger {
            doc /* remove only queued outcomes that become durable and retain remaining failures. */
        }
        dependency restoreLedgerAccess from restoreFromSnapshot to ledger {
            doc /* restore the represented cursor and record restoration only when requested. */
        }
    }

    action def OpenRtgController {
        in ref graph : RtgGraph;
        in ref schema : RtgSchema;
        in ref constraints : RtgConstraints;
        in ref migration : RtgMigration;
        in ref changeValidator : RtgChangeValidator;
        in ref queryEngine : RtgQueryEngine;
        in ref jsonStorage : JsonFileStorage;
        in ref sqlStorage : SqlStorage;
        out part controller : RtgController;
        doc /* Bind exactly one implementation of each of the eight required Bibliotek roles and initialize or validate the durable ledger schema. */
        @FailureContract { errorIds = ("RtgControllerConfigurationInvalid"); obligation = "Invalid or incompatible dependencies do not return a partially usable controller."; }
        bind controller.graph = graph;
        bind controller.schema = schema;
        bind controller.constraints = constraints;
        bind controller.migration = migration;
        bind controller.changeValidator = changeValidator;
        bind controller.queryEngine = queryEngine;
        bind controller.jsonStorage = jsonStorage;
        bind controller.sqlStorage = sqlStorage;
    }

    requirement <'contract.rtg.controller.live_mutation_flow'> liveMutationFlow {
        subject operation : ApplyLiveGraphChanges;
        doc /* Normalize references, construct a projected state, validate it in strict mode, apply only an accepted projection, restore all touched component state on apply failure, then expose the ledger outcome. */
    }
    requirement <'contract.rtg.controller.live_mutation_lane'> liveMutationLane { subject operation : ApplyLiveGraphChanges; doc /* The live lane accepts live anchor, data-object, and link writes, associations, dissociations, deletes, and live replacements. It rejects schema, constraint, migration, non-live candidate creation, and requests that make graph objects non-live. strict is the default; skip bypasses change validation only and never lower-store invariants. */ }
    requirement <'contract.rtg.controller.staging_flow'> stagingFlow { subject operation : StageKnowledgeChanges; doc /* Staging accepts migration-scoped non-live graph, schema, and constraint candidates plus migration records, evidence, and permitted status changes. It rejects direct live schema/constraint writes, unscoped candidates, and live-status flips reserved for cutover. Strict mode validates the projected cutover before any write. A successful result has status applied and details keys operation_effect=staged_candidates_written, requires_cutover, staged_migration_ids, and candidate_counts with schema, constraints, and graph counts. */ }
    requirement <'contract.rtg.controller.validation_flow'> validationFlow {
        subject operation : ValidateLiveGraphChanges;
        doc /* Resolve the request exactly as a write would, validate the projected state, return generated identities and resolved changes, and mutate neither component state nor the controller ledger. */
    }
    requirement <'contract.rtg.controller.cutover_flow'> cutoverFlow {
        subject operation : ApplyMigrationCutover;
        doc /* Read the selected migration membership, snapshot coordinated state, apply make-live and make-non-live changes in reference-safe order, validate the result, and either commit an applied status or restore the snapshot and record failed status. */
    }
    requirement <'contract.rtg.controller.cutover_sequence'> cutoverSequence { subject operation : ApplyMigrationCutover; doc /* Under the write lock: derive the plan from the selected migration; validate the projected state; capture a coordinated preimage; make schema and constraint changes, with make-non-live before make-live for a type key; make graph live changes; validate actual state; optionally prune retired records; then remove the completed migration. Any failure restores the preimage, marks the migration failed when safe, and records cutover_failed. */ }
    requirement <'contract.rtg.controller.abandonment_flow'> abandonmentFlow { subject operation : AbandonMigration; doc /* Applied migrations cannot be abandoned. Draft, ready, or failed work becomes abandoned; only non-live make-live candidates unshared by another migration may be pruned. Live records and make-non-live targets are never deleted. details.pruned_candidates groups removed IDs under schema, constraints, and graph; details.skipped_candidates groups retained IDs under the same keys and gives each a reason of shared, missing, or live. */ }
    requirement <'contract.rtg.controller.stable_query_flow'> stableQueryFlow {
        subject operation : ExecuteControllerQuery;
        doc /* Execute each query while writes are excluded so the query engine receives one coherent graph read view; query execution does not append a mutation record. */
    }
    requirement <'contract.rtg.controller.read_semantics'> controllerReadSemantics { subject controller : RtgController; doc /* Query defaults to live-only at the controller boundary unless explicit query options override it. Direct object reads do not lifecycle-filter. Migration reads are deterministically ordered. All reads queue behind cutover, restore, and replay mutation and never append mutation ledger records. */ }
    requirement <'contract.rtg.controller.discovery_semantics'> discoverySemantics { subject controller : RtgController; doc /* Discovery composes schema-owned descriptions with graph counts, excludes non-live definitions by default, and applies a positive optional limit. Schema packs contain selected anchors, associated-data schemas, participating links, and live counts when requested. */ }
    requirement <'contract.rtg.controller.system_state_semantics'> systemStateSemantics { subject operation : GetSystemState; doc /* State classification is exactly empty, schema_only, populated, has_staged_work, or needs_replay. liveSchemaCounts has anchor, data_object, and link counts; liveObjectCounts groups counts by object kind and type key; nonLiveCandidateCounts has schema, constraints, and graph totals; migrationCountsByStatus has draft, ready, failed, applied, and abandoned totals. The result also reports storage-scoped snapshot paths, ledger pointers/count, stable workflow identifiers, and advisory next steps without mutation. */ }
    requirement <'contract.rtg.controller.snapshot_flow'> coordinatedSnapshotFlow {
        subject operation : ExportSystemSnapshot;
        doc /* Export graph, schema, constraint, and migration snapshots together with the represented ledger cursor and transaction identity from one visible controller state. */
    }
    requirement <'contract.rtg.controller.persisted_snapshot_semantics'> persistedSnapshotSemantics { subject controller : RtgController; doc /* Persist writes the coordinated snapshot atomically through JSON storage. List and load expose only valid snapshot-like JSON documents below that storage root; load validates but does not apply the snapshot. */ }
    requirement <'contract.rtg.controller.restore_flow'> restoreFlow {
        subject operation : RestoreFromSnapshot;
        doc /* Validate all supplied component snapshots before replacement, expose no partially restored state, and honor the requested ledger recording mode. */
    }
    requirement <'contract.rtg.controller.replay_flow'> replayFlow {
        subject operation : ReplayLedger;
        doc /* Start from empty or explicitly supplied snapshot state, replay resolved mutating requests after the selected cursor through the optional stop cursor in ledger order, and keep replay itself ledger-silent. The replay_applied result details contain ledger_records_seen, mutating_requests_replayed, and replay_window. */
    }
    requirement <'contract.rtg.controller.replay_selection'> replaySelection { subject operation : ReplayLedger; doc /* Exactly zero or one start snapshot source is supplied. Replay starts after the explicit cursor or the snapshot cursor, stops at an optional inclusive through cursor, processes ascending ledger positions, reuses recorded resolved identities, and replays only accepted mutating outcomes; rejected and rolled-back requests and read-only calls have no reconstruction effect. */ }
    requirement <'contract.rtg.controller.replay_verification'> replayVerification { subject operation : VerifyReplayFromLedger; doc /* Replay verification uses isolated scratch state, returns replay_verified with seed/result summaries, count differences, replay-window details, records seen, requests replayed, and post-replay validation, then leaves current state and source ledger unchanged. */ }
    requirement <'contract.rtg.controller.migration_history'> migrationHistorySemantics { subject operation : ListMigrationHistory; doc /* Migration history reconstructs staged, cutover_applied, cutover_failed, and abandoned events in ledger order even when terminal migration records are absent from the current migration store. */ }
    requirement <'contract.rtg.controller.ledger_failure_semantics'> ledgerFailureSemantics { subject operation : FlushLedgerFailures; doc /* Failed audit records retain request/response/error kind, original JSON payload, failure text, retry count, timestamps, transaction identity, and any reserved position. Flush retries in original order, removes only durable successes, and reports ledger_failures_flushed with integer details.flushed and details.remaining counts rather than raising for records that remain unavailable. */ }
    requirement <'contract.rtg.controller.operation_results'> operationResultSemantics { subject controller : RtgController; doc /* State-changing results use only applied, cutover_applied, cutover_failed, migration_abandoned, snapshot_persisted, restore_applied, replay_applied, or ledger_failures_flushed. Zero visible state change reports zero applied counts; validationReport is absent when skipped; details carries operation-specific JSON-safe evidence. */ }
    requirement <'contract.rtg.controller.ledger_outcomes'> ledgerOutcomeFlow {
        subject controller : RtgController;
        doc /* Every controller call has a UUID transaction identity. Durable ledger success advances the monotonic cursor; a ledger failure after a state effect is returned as degraded audit state and queued for explicit flush. */
    }

    requirement <'invariant.rtg.controller.public_contracts_only'> publicContractsOnly { subject controller : RtgController; doc /* Lower components are used only through public contracts. */ }
    requirement <'invariant.rtg.controller.no_transport_ownership'> noTransportOwnership { subject controller : RtgController; doc /* Controller owns no MCP, REST, CLI, SDK, or UI transport. */ }
    requirement <'invariant.rtg.controller.validates_before_required_mutation'> validatesBeforeRequiredMutation { subject controller : RtgController; doc /* Strict mutation validates the projected state before apply. */ }
    requirement <'invariant.rtg.controller.strict_validation_default'> strictValidationDefault { subject controller : RtgController; doc /* Normal mutation defaults to strict validation. */ }
    requirement <'invariant.rtg.controller.live_graph_lane_excludes_knowledge_engineering'> liveGraphLaneExcludesKnowledgeEngineering { subject controller : RtgController; doc /* Live CRUD excludes schema, constraint, migration, and non-live work. */ }
    requirement <'invariant.rtg.controller.knowledge_changes_are_migration_scoped'> knowledgeChangesMigrationScoped { subject controller : RtgController; doc /* Non-live knowledge changes belong to active migration work. */ }
    requirement <'invariant.rtg.controller.cutover_is_only_live_flip_authority_for_staged_schema_constraints'> cutoverOnlyLiveFlipAuthority { subject controller : RtgController; doc /* Cutover is the only authority for staged schema and constraint live flips. */ }
    requirement <'invariant.rtg.controller.normalized_batches_are_internal_controller_plans'> normalizedBatchesInternalPlans { subject controller : RtgController; doc /* Normalized batches are internal plans, not a generic public mutation backdoor. */ }
    requirement <'invariant.rtg.controller.schema_constraint_changes_use_migrations'> schemaConstraintChangesUseMigrations { subject controller : RtgController; doc /* Schema and constraint writes use migration workflows. */ }
    requirement <'invariant.rtg.controller.schema_constraint_deletion_uses_migrations'> schemaConstraintDeletionUsesMigrations { subject controller : RtgController; doc /* Schema and constraint retirement/deletion uses migration workflows. */ }
    requirement <'invariant.rtg.controller.non_live_candidates_are_migration_scoped'> nonLiveCandidatesMigrationScoped { subject controller : RtgController; doc /* Non-live candidates are referenced by active migration membership. */ }
    requirement <'invariant.rtg.controller.system_invariants_owned'> systemInvariantsOwned { subject controller : RtgController; doc /* Cross-component invariants are enforced by the controller. */ }
    requirement <'invariant.rtg.controller.validation_report_authoritative'> validationReportAuthoritative { subject controller : RtgController; doc /* Blocking validation findings control strict acceptance. */ }
    requirement <'invariant.rtg.controller.snapshot_uses_component_snapshots'> snapshotUsesComponentSnapshots { subject controller : RtgController; doc /* Coordinated snapshots are assembled through component snapshot contracts. */ }
    requirement <'invariant.rtg.controller.snapshot_json_serializable'> snapshotJsonSerializable { subject controller : RtgController; doc /* Exported system snapshots are JSON-serializable. */ }
    requirement <'invariant.rtg.controller.snapshot_records_ledger_position'> snapshotRecordsLedgerPosition { subject controller : RtgController; doc /* Snapshots identify the represented ledger position and transaction. */ }
    requirement <'invariant.rtg.controller.persisted_snapshot_readback_is_storage_scoped'> persistedSnapshotStorageScoped { subject controller : RtgController; doc /* Snapshot readback is limited to JSON storage documents. */ }
    requirement <'invariant.rtg.controller.cutover_uses_migration_membership'> cutoverUsesMigrationMembership { subject controller : RtgController; doc /* Cutover applies exactly the selected migration membership. */ }
    requirement <'invariant.rtg.controller.reads_do_not_observe_transient_cutover'> readsHideTransientState { subject controller : RtgController; doc /* Reads do not observe transient cutover, restore, or replay state. */ }
    requirement <'invariant.rtg.controller.projected_queries_use_live_overlay'> projectedQueriesUseLiveOverlay { subject controller : RtgController; doc /* Projected validation uses explicit live-status overlays. */ }
    requirement <'invariant.rtg.controller.cutover_restores_on_failure'> cutoverRestoresOnFailure { subject controller : RtgController; doc /* Failed cutover restores the pre-cutover visible state. */ }
    requirement <'invariant.rtg.controller.failed_cutover_is_legible'> failedCutoverLegible { subject controller : RtgController; doc /* Failed cutover records actionable diagnostic status. */ }
    requirement <'invariant.rtg.controller.failed_cutover_replay_preserves_status'> failedCutoverReplayPreservesStatus { subject controller : RtgController; doc /* Replay reproduces recorded failed-cutover status. */ }
    requirement <'invariant.rtg.controller.cutover_order'> cutoverOrder { subject controller : RtgController; doc /* Cutover ordering preserves referenced state and validation. */ }
    requirement <'invariant.rtg.controller.abandonment_never_deletes_live_records'> abandonmentNeverDeletesLive { subject controller : RtgController; doc /* Abandonment never deletes live records. */ }
    requirement <'invariant.rtg.controller.one_write_at_a_time'> oneWriteAtATime { subject controller : RtgController; doc /* Only one controller write mutates system or ledger state at a time. */ }
    requirement <'invariant.rtg.controller.ledger_records_black_box_activity'> ledgerRecordsBlackBoxActivity { subject controller : RtgController; doc /* Ledger records controller requests, results, and visible failures. */ }
    requirement <'invariant.rtg.controller.ledger_payloads_are_json_text'> ledgerPayloadsJsonText { subject controller : RtgController; doc /* Ledger request, response, and error payloads are JSON text. */ }
    requirement <'invariant.rtg.controller.transaction_id_always_assigned'> transactionIdAlwaysAssigned { subject controller : RtgController; doc /* Every controller operation receives a transaction identifier. */ }
    requirement <'invariant.rtg.controller.transaction_ids_are_uuids'> transactionIdsUuids { subject controller : RtgController; doc /* Transaction identifiers are UUIDs. */ }
    requirement <'invariant.rtg.controller.ledger_position_is_replay_cursor'> ledgerPositionReplayCursor { subject controller : RtgController; doc /* Ledger position is monotonic and is the replay cursor. */ }
    requirement <'invariant.rtg.controller.resolved_uuids_before_ledger'> resolvedUuidsBeforeLedger { subject controller : RtgController; doc /* Batch-local references are resolved before durable ledger recording. */ }
    requirement <'invariant.rtg.controller.write_atomicity_scoped'> writeAtomicityScoped { subject controller : RtgController; doc /* Failed normalized apply restores touched component state within the controller scope. */ }
    requirement <'invariant.rtg.controller.reads_mediated'> readsMediated { subject controller : RtgController; doc /* Application reads pass through controller public contracts. */ }
    requirement <'invariant.rtg.controller.live_flips_via_full_record_write'> liveFlipsViaFullRecordWrite { subject controller : RtgController; doc /* Live-status changes preserve complete public records. */ }
    requirement <'invariant.rtg.controller.graph_type_is_schema_type_key'> graphTypeIsSchemaTypeKey { subject controller : RtgController; doc /* Graph object type values correspond to schema type keys. */ }

    verification def RtgControllerBoundaryVerification {
        subject controller : RtgController;
        objective {
            verify liveMutationFlow;
            verify liveMutationLane;
            verify stagingFlow;
            verify validationFlow;
            verify cutoverFlow;
            verify cutoverSequence;
            verify abandonmentFlow;
            verify stableQueryFlow;
            verify controllerReadSemantics;
            verify discoverySemantics;
            verify systemStateSemantics;
            verify coordinatedSnapshotFlow;
            verify persistedSnapshotSemantics;
            verify restoreFlow;
            verify replayFlow;
            verify replaySelection;
            verify replayVerification;
            verify migrationHistorySemantics;
            verify ledgerFailureSemantics;
            verify operationResultSemantics;
            verify ledgerOutcomeFlow;
            verify publicContractsOnly;
            verify noTransportOwnership;
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
            verify snapshotRecordsLedgerPosition;
            verify persistedSnapshotStorageScoped;
            verify cutoverUsesMigrationMembership;
            verify readsHideTransientState;
            verify projectedQueriesUseLiveOverlay;
            verify cutoverRestoresOnFailure;
            verify failedCutoverLegible;
            verify failedCutoverReplayPreservesStatus;
            verify cutoverOrder;
            verify abandonmentNeverDeletesLive;
            verify oneWriteAtATime;
            verify ledgerRecordsBlackBoxActivity;
            verify ledgerPayloadsJsonText;
            verify transactionIdAlwaysAssigned;
            verify transactionIdsUuids;
            verify ledgerPositionReplayCursor;
            verify resolvedUuidsBeforeLedger;
            verify writeAtomicityScoped;
            verify readsMediated;
            verify liveFlipsViaFullRecordWrite;
            verify graphTypeIsSchemaTypeKey;
        }
        @EvidenceBinding { verificationId = "verification.rtg.controller.boundary"; evidenceId = "components/rtg/controller/tests/test_rtg_controller_contract.py"; implementationScope = "InProcessRtgController"; }
    }
}
