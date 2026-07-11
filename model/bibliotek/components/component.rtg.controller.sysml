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
        enum restorePreCutoverSnapshot { @ExternalName { name = "restore_pre_cutover_snapshot"; } }
    }
    enum def RtgControllerLedgerMode { enum record; enum skip; }
    enum def RtgControllerOperationStatus {
        enum applied;
        enum cutoverApplied { @ExternalName { name = "cutover_applied"; } }
        enum cutoverFailed { @ExternalName { name = "cutover_failed"; } }
        enum migrationAbandoned { @ExternalName { name = "migration_abandoned"; } }
        enum snapshotPersisted { @ExternalName { name = "snapshot_persisted"; } }
        enum restoreApplied { @ExternalName { name = "restore_applied"; } }
        enum replayApplied { @ExternalName { name = "replay_applied"; } }
        enum ledgerFailuresFlushed { @ExternalName { name = "ledger_failures_flushed"; } }
    }
    enum def RtgControllerValidationStatus { enum validated; }
    enum def RtgControllerReplayVerificationStatus {
        enum replayVerified { @ExternalName { name = "replay_verified"; } }
    }
    enum def RtgControllerMutationState {
        enum notMutated { @ExternalName { name = "not_mutated"; } }
    }
    enum def RtgControllerStateClassification {
        enum empty; enum schemaOnly; enum populated; enum hasStagedWork; enum needsReplay;
    }
    enum def RtgControllerWorkflow {
        enum schemaBootstrap; enum dataIngest; enum queryAnswer; enum safeUpdate;
        enum snapshotReplayCheck; enum stagedWorkReview; enum replayRecovery;
    }
    enum def RtgControllerMigrationCountScope {
        enum currentMigrationStore { @ExternalName { name = "current_migration_store"; } }
    }
    enum def RtgControllerLedgerRecordKind { enum request; enum response; enum error; }
    enum def RtgControllerMigrationEventType {
        enum staged;
        enum cutoverApplied { @ExternalName { name = "cutover_applied"; } }
        enum cutoverFailed { @ExternalName { name = "cutover_failed"; } }
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

    part def RtgController {
        doc /* Coordinate cross-component RTG invariants, mutation lanes, cutover, recovery, replay, and audit outcomes. */
        @SpecIdentity { id = "component.rtg.controller"; lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        @DependencyPolicy {
            allowedComponentIds = ("component.rtg.graph", "component.rtg.schema",
                "component.rtg.constraints", "component.rtg.migration",
                "component.rtg.change_validation", "component.rtg.query",
                "component.storage.json_file", "component.storage.sql");
            forbiddenComponentIds = ("application.vellis", "adapter.mcp", "adapter.rest");
        }

        ref action requiredGraphSnapshot[0..*] : ExportGraphSnapshot { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredGraphPutAnchor[0..*] : PutAnchor { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredGraphPutDataObject[0..*] : PutDataObject { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredGraphPutLink[0..*] : PutLink { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredGraphDelete[0..*] : DeleteAnchor { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredGraphPreview[0..*] : PreviewDeleteAnchor { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredGraphRead[0..*] : GetGraphObject { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredSchemaSnapshot[0..*] : ExportSchemaSnapshot { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredSchemaWrite[0..*] : PutSchemaDefinition { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredSchemaRead[0..*] : GetSchemaPack { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredConstraintSnapshot[0..*] : ExportConstraintSnapshot { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredConstraintWrite[0..*] : PutConstraint { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredMigrationSnapshot[0..*] : ExportMigrationSnapshot { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredMigrationWrite[0..*] : PutMigration { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredMigrationRead[0..*] : GetMigration { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredValidation[0..*] : ValidateRtgChangeBatch { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredQuery[0..*] : ExecuteRtgQuery { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredJsonWrite[0..*] : WriteJsonDocument { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredJsonRead[0..*] : ReadJsonDocument { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredSqlExecute[0..*] : ExecuteSql { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredSqlQuery[0..*] : QuerySql { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredSqlTransaction[0..*] : ExecuteSqlTransaction { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }

        ref item ledger : RtgControllerLedger {
            @StateAuthority {
                authority = StateAuthorityKind::canonicalOwner;
                lifetime = StateLifetime::independent;
                persistence = StatePersistence::durable;
            }
        }

        perform action applyLiveGraphChanges[0..*] : ApplyLiveGraphChanges { @StateAccess { kind = StateAccessKind::write; effect = "serialized component mutation plus durable or queued ledger outcome"; } }
        perform action validateLiveGraphChanges[0..*] : ValidateLiveGraphChanges { @StateAccess { kind = StateAccessKind::none; effect = "read and project dependencies; no component or ledger mutation"; } }
        perform action stageKnowledgeChanges[0..*] : StageKnowledgeChanges { @StateAccess { kind = StateAccessKind::write; effect = "serialized migration-scoped staging plus ledger outcome"; } }
        perform action applyMigrationCutover[0..*] : ApplyMigrationCutover { @StateAccess { kind = StateAccessKind::write; effect = "serialized coordinated cutover or restoration plus ledger outcome"; } }
        perform action executeQuery[0..*] : ExecuteControllerQuery { @StateAccess { kind = StateAccessKind::none; effect = "coherent dependency read; no component or ledger mutation"; } }
        perform action getObject[0..*] : ControllerGetObject { @StateAccess { kind = StateAccessKind::none; effect = "read graph without mutation or ledger write"; } }
        perform action listMigrations[0..*] : ControllerListMigrations { @StateAccess { kind = StateAccessKind::none; effect = "read migration store without mutation or ledger write"; } }
        perform action getMigration[0..*] : ControllerGetMigration { @StateAccess { kind = StateAccessKind::none; effect = "read migration store without mutation or ledger write"; } }
        perform action validateGraph[0..*] : ValidateGraph { @StateAccess { kind = StateAccessKind::none; effect = "read/project dependencies without mutation or ledger write"; } }
        perform action discoverAnchorTypes[0..*] : DiscoverAnchorTypes { @StateAccess { kind = StateAccessKind::none; effect = "compose schema and count reads without mutation"; } }
        perform action getSchemaPack[0..*] : GetControllerSchemaPack { @StateAccess { kind = StateAccessKind::none; effect = "compose schema and count reads without mutation"; } }
        perform action getSystemState[0..*] : GetSystemState { @StateAccess { kind = StateAccessKind::none; effect = "summarize components, snapshots, and ledger without mutation"; } }
        perform action exportSystemSnapshot[0..*] : ExportSystemSnapshot { @StateAccess { kind = StateAccessKind::none; effect = "coordinated read of components and ledger cursor"; } }
        perform action persistSystemSnapshot[0..*] : PersistSystemSnapshot { @StateAccess { kind = StateAccessKind::write; effect = "write one atomic JSON snapshot document and record outcome"; } }
        perform action listPersistedSnapshots[0..*] : ListPersistedSnapshots { @StateAccess { kind = StateAccessKind::none; effect = "read storage-scoped snapshot metadata without mutation"; } }
        perform action loadPersistedSnapshot[0..*] : LoadPersistedSnapshot { @StateAccess { kind = StateAccessKind::none; effect = "read and decode one snapshot document without restoring it"; } }
        perform action abandonMigration[0..*] : AbandonMigration { @StateAccess { kind = StateAccessKind::write; effect = "serialized safe candidate pruning, migration transition, and ledger outcome"; } }
        perform action replayLedger[0..*] : ReplayLedger { @StateAccess { kind = StateAccessKind::write; effect = "replace component state with selected replay result without duplicating source ledger records"; } }
        perform action verifyReplayFromLedger[0..*] : VerifyReplayFromLedger { @StateAccess { kind = StateAccessKind::none; effect = "replay into isolated scratch state and compare without current-state mutation"; } }
        perform action listMigrationHistory[0..*] : ListMigrationHistory { @StateAccess { kind = StateAccessKind::none; effect = "read ordered migration-related ledger events"; } }
        perform action flushLedgerFailures[0..*] : FlushLedgerFailures { @StateAccess { kind = StateAccessKind::write; effect = "retry queued durable records and retain only failures"; } }
        perform action restoreFromSnapshot[0..*] : RestoreFromSnapshot { @StateAccess { kind = StateAccessKind::write; effect = "atomically replace coordinated state and honor ledger mode"; } }

        dependency liveMutationLedger from applyLiveGraphChanges to ledger {
            @StateAccess { kind = StateAccessKind::write; effect = "record the resolved request and its applied, rejected, failed, or degraded outcome"; }
        }
        dependency stagingLedger from stageKnowledgeChanges to ledger {
            @StateAccess { kind = StateAccessKind::write; effect = "record the migration-scoped staging outcome"; }
        }
        dependency cutoverLedger from applyMigrationCutover to ledger {
            @StateAccess { kind = StateAccessKind::write; effect = "record applied or failed cutover status after restoration handling"; }
        }
        dependency replayLedgerAccess from replayLedger to ledger {
            @StateAccess { kind = StateAccessKind::read; effect = "reconstruct from the selected monotonic ledger window without recording replayed requests again"; }
        }
        dependency restoreLedgerAccess from restoreFromSnapshot to ledger {
            @StateAccess { kind = StateAccessKind::write; effect = "restore the represented cursor and record restoration only when requested"; }
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
    }

    requirement liveMutationFlow {
        subject operation : ApplyLiveGraphChanges;
        doc /* Normalize references, construct a projected state, validate it in strict mode, apply only an accepted projection, restore all touched component state on apply failure, then expose the ledger outcome. */
        @StableId { id = "contract.rtg.controller.live_mutation_flow"; }
    }
    requirement liveMutationLane { subject operation : ApplyLiveGraphChanges; doc /* The live lane accepts live anchor, data-object, and link writes, associations, dissociations, deletes, and live replacements. It rejects schema, constraint, migration, non-live candidate creation, and requests that make graph objects non-live. strict is the default; skip bypasses change validation only and never lower-store invariants. */ @StableId { id = "contract.rtg.controller.live_mutation_lane"; } }
    requirement stagingFlow { subject operation : StageKnowledgeChanges; doc /* Staging accepts migration-scoped non-live graph, schema, and constraint candidates plus migration records, evidence, and permitted status changes. It rejects direct live schema/constraint writes, unscoped candidates, and live-status flips reserved for cutover. Strict mode validates the projected cutover before any write. A successful result has status applied and details keys operation_effect=staged_candidates_written, requires_cutover, staged_migration_ids, and candidate_counts with schema, constraints, and graph counts. */ @StableId { id = "contract.rtg.controller.staging_flow"; } }
    requirement validationFlow {
        subject operation : ValidateLiveGraphChanges;
        doc /* Resolve the request exactly as a write would, validate the projected state, return generated identities and resolved changes, and mutate neither component state nor the controller ledger. */
        @StableId { id = "contract.rtg.controller.validation_flow"; }
    }
    requirement cutoverFlow {
        subject operation : ApplyMigrationCutover;
        doc /* Read the selected migration membership, snapshot coordinated state, apply make-live and make-non-live changes in reference-safe order, validate the result, and either commit an applied status or restore the snapshot and record failed status. */
        @StableId { id = "contract.rtg.controller.cutover_flow"; }
    }
    requirement cutoverSequence { subject operation : ApplyMigrationCutover; doc /* Under the write lock: derive the plan from the selected migration; validate the projected state; capture a coordinated preimage; make schema and constraint changes, with make-non-live before make-live for a type key; make graph live changes; validate actual state; optionally prune retired records; then remove the completed migration. Any failure restores the preimage, marks the migration failed when safe, and records cutover_failed. */ @StableId { id = "contract.rtg.controller.cutover_sequence"; } }
    requirement abandonmentFlow { subject operation : AbandonMigration; doc /* Applied migrations cannot be abandoned. Draft, ready, or failed work becomes abandoned; only non-live make-live candidates unshared by another migration may be pruned. Live records and make-non-live targets are never deleted. details.pruned_candidates groups removed IDs under schema, constraints, and graph; details.skipped_candidates groups retained IDs under the same keys and gives each a reason of shared, missing, or live. */ @StableId { id = "contract.rtg.controller.abandonment_flow"; } }
    requirement stableQueryFlow {
        subject operation : ExecuteControllerQuery;
        doc /* Execute each query while writes are excluded so the query engine receives one coherent graph read view; query execution does not append a mutation record. */
        @StableId { id = "contract.rtg.controller.stable_query_flow"; }
    }
    requirement controllerReadSemantics { subject controller : RtgController; doc /* Query defaults to live-only at the controller boundary unless explicit query options override it. Direct object reads do not lifecycle-filter. Migration reads are deterministically ordered. All reads queue behind cutover, restore, and replay mutation and never append mutation ledger records. */ @StableId { id = "contract.rtg.controller.read_semantics"; } }
    requirement discoverySemantics { subject controller : RtgController; doc /* Discovery composes schema-owned descriptions with graph counts, excludes non-live definitions by default, and applies a positive optional limit. Schema packs contain selected anchors, associated-data schemas, participating links, and live counts when requested. */ @StableId { id = "contract.rtg.controller.discovery_semantics"; } }
    requirement systemStateSemantics { subject operation : GetSystemState; doc /* State classification is exactly empty, schema_only, populated, has_staged_work, or needs_replay. liveSchemaCounts has anchor, data_object, and link counts; liveObjectCounts groups counts by object kind and type key; nonLiveCandidateCounts has schema, constraints, and graph totals; migrationCountsByStatus has draft, ready, failed, applied, and abandoned totals. The result also reports storage-scoped snapshot paths, ledger pointers/count, stable workflow identifiers, and advisory next steps without mutation. */ @StableId { id = "contract.rtg.controller.system_state_semantics"; } }
    requirement coordinatedSnapshotFlow {
        subject operation : ExportSystemSnapshot;
        doc /* Export graph, schema, constraint, and migration snapshots together with the represented ledger cursor and transaction identity from one visible controller state. */
        @StableId { id = "contract.rtg.controller.snapshot_flow"; }
    }
    requirement persistedSnapshotSemantics { subject controller : RtgController; doc /* Persist writes the coordinated snapshot atomically through JSON storage. List and load expose only valid snapshot-like JSON documents below that storage root; load validates but does not apply the snapshot. */ @StableId { id = "contract.rtg.controller.persisted_snapshot_semantics"; } }
    requirement restoreFlow {
        subject operation : RestoreFromSnapshot;
        doc /* Validate all supplied component snapshots before replacement, expose no partially restored state, and honor the requested ledger recording mode. */
        @StableId { id = "contract.rtg.controller.restore_flow"; }
    }
    requirement replayFlow {
        subject operation : ReplayLedger;
        doc /* Start from empty or explicitly supplied snapshot state, replay resolved mutating requests after the selected cursor through the optional stop cursor in ledger order, and keep replay itself ledger-silent. The replay_applied result details contain ledger_records_seen, mutating_requests_replayed, and replay_window. */
        @StableId { id = "contract.rtg.controller.replay_flow"; }
    }
    requirement replaySelection { subject operation : ReplayLedger; doc /* Exactly zero or one start snapshot source is supplied. Replay starts after the explicit cursor or the snapshot cursor, stops at an optional inclusive through cursor, processes ascending ledger positions, reuses recorded resolved identities, and replays only accepted mutating outcomes; rejected and rolled-back requests and read-only calls have no reconstruction effect. */ @StableId { id = "contract.rtg.controller.replay_selection"; } }
    requirement replayVerification { subject operation : VerifyReplayFromLedger; doc /* Replay verification uses isolated scratch state, returns replay_verified with seed/result summaries, count differences, replay-window details, records seen, requests replayed, and post-replay validation, then leaves current state and source ledger unchanged. */ @StableId { id = "contract.rtg.controller.replay_verification"; } }
    requirement migrationHistorySemantics { subject operation : ListMigrationHistory; doc /* Migration history reconstructs staged, cutover_applied, cutover_failed, and abandoned events in ledger order even when terminal migration records are absent from the current migration store. */ @StableId { id = "contract.rtg.controller.migration_history"; } }
    requirement ledgerFailureSemantics { subject operation : FlushLedgerFailures; doc /* Failed audit records retain request/response/error kind, original JSON payload, failure text, retry count, timestamps, transaction identity, and any reserved position. Flush retries in original order, removes only durable successes, and reports ledger_failures_flushed with integer details.flushed and details.remaining counts rather than raising for records that remain unavailable. */ @StableId { id = "contract.rtg.controller.ledger_failure_semantics"; } }
    requirement operationResultSemantics { subject controller : RtgController; doc /* State-changing results use only applied, cutover_applied, cutover_failed, migration_abandoned, snapshot_persisted, restore_applied, replay_applied, or ledger_failures_flushed. Zero visible state change reports zero applied counts; validationReport is absent when skipped; details carries operation-specific JSON-safe evidence. */ @StableId { id = "contract.rtg.controller.operation_results"; } }
    requirement ledgerOutcomeFlow {
        subject controller : RtgController;
        doc /* Every controller call has a UUID transaction identity. Durable ledger success advances the monotonic cursor; a ledger failure after a state effect is returned as degraded audit state and queued for explicit flush. */
        @StableId { id = "contract.rtg.controller.ledger_outcomes"; }
    }

    requirement publicContractsOnly { subject controller : RtgController; doc /* Lower components are used only through public contracts. */ @StableId { id = "invariant.rtg.controller.public_contracts_only"; } }
    requirement noTransportOwnership { subject controller : RtgController; doc /* Controller owns no MCP, REST, CLI, SDK, or UI transport. */ @StableId { id = "invariant.rtg.controller.no_transport_ownership"; } }
    requirement validatesBeforeRequiredMutation { subject controller : RtgController; doc /* Strict mutation validates the projected state before apply. */ @StableId { id = "invariant.rtg.controller.validates_before_required_mutation"; } }
    requirement strictValidationDefault { subject controller : RtgController; doc /* Normal mutation defaults to strict validation. */ @StableId { id = "invariant.rtg.controller.strict_validation_default"; } }
    requirement liveGraphLaneExcludesKnowledgeEngineering { subject controller : RtgController; doc /* Live CRUD excludes schema, constraint, migration, and non-live work. */ @StableId { id = "invariant.rtg.controller.live_graph_lane_excludes_knowledge_engineering"; } }
    requirement knowledgeChangesMigrationScoped { subject controller : RtgController; doc /* Non-live knowledge changes belong to active migration work. */ @StableId { id = "invariant.rtg.controller.knowledge_changes_are_migration_scoped"; } }
    requirement cutoverOnlyLiveFlipAuthority { subject controller : RtgController; doc /* Cutover is the only authority for staged schema and constraint live flips. */ @StableId { id = "invariant.rtg.controller.cutover_is_only_live_flip_authority_for_staged_schema_constraints"; } }
    requirement normalizedBatchesInternalPlans { subject controller : RtgController; doc /* Normalized batches are internal plans, not a generic public mutation backdoor. */ @StableId { id = "invariant.rtg.controller.normalized_batches_are_internal_controller_plans"; } }
    requirement schemaConstraintChangesUseMigrations { subject controller : RtgController; doc /* Schema and constraint writes use migration workflows. */ @StableId { id = "invariant.rtg.controller.schema_constraint_changes_use_migrations"; } }
    requirement schemaConstraintDeletionUsesMigrations { subject controller : RtgController; doc /* Schema and constraint retirement/deletion uses migration workflows. */ @StableId { id = "invariant.rtg.controller.schema_constraint_deletion_uses_migrations"; } }
    requirement nonLiveCandidatesMigrationScoped { subject controller : RtgController; doc /* Non-live candidates are referenced by active migration membership. */ @StableId { id = "invariant.rtg.controller.non_live_candidates_are_migration_scoped"; } }
    requirement systemInvariantsOwned { subject controller : RtgController; doc /* Cross-component invariants are enforced by the controller. */ @StableId { id = "invariant.rtg.controller.system_invariants_owned"; } }
    requirement validationReportAuthoritative { subject controller : RtgController; doc /* Blocking validation findings control strict acceptance. */ @StableId { id = "invariant.rtg.controller.validation_report_authoritative"; } }
    requirement snapshotUsesComponentSnapshots { subject controller : RtgController; doc /* Coordinated snapshots are assembled through component snapshot contracts. */ @StableId { id = "invariant.rtg.controller.snapshot_uses_component_snapshots"; } }
    requirement snapshotJsonSerializable { subject controller : RtgController; doc /* Exported system snapshots are JSON-serializable. */ @StableId { id = "invariant.rtg.controller.snapshot_json_serializable"; } }
    requirement snapshotRecordsLedgerPosition { subject controller : RtgController; doc /* Snapshots identify the represented ledger position and transaction. */ @StableId { id = "invariant.rtg.controller.snapshot_records_ledger_position"; } }
    requirement persistedSnapshotStorageScoped { subject controller : RtgController; doc /* Snapshot readback is limited to JSON storage documents. */ @StableId { id = "invariant.rtg.controller.persisted_snapshot_readback_is_storage_scoped"; } }
    requirement cutoverUsesMigrationMembership { subject controller : RtgController; doc /* Cutover applies exactly the selected migration membership. */ @StableId { id = "invariant.rtg.controller.cutover_uses_migration_membership"; } }
    requirement readsHideTransientState { subject controller : RtgController; doc /* Reads do not observe transient cutover, restore, or replay state. */ @StableId { id = "invariant.rtg.controller.reads_do_not_observe_transient_cutover"; } }
    requirement projectedQueriesUseLiveOverlay { subject controller : RtgController; doc /* Projected validation uses explicit live-status overlays. */ @StableId { id = "invariant.rtg.controller.projected_queries_use_live_overlay"; } }
    requirement cutoverRestoresOnFailure { subject controller : RtgController; doc /* Failed cutover restores the pre-cutover visible state. */ @StableId { id = "invariant.rtg.controller.cutover_restores_on_failure"; } }
    requirement failedCutoverLegible { subject controller : RtgController; doc /* Failed cutover records actionable diagnostic status. */ @StableId { id = "invariant.rtg.controller.failed_cutover_is_legible"; } }
    requirement failedCutoverReplayPreservesStatus { subject controller : RtgController; doc /* Replay reproduces recorded failed-cutover status. */ @StableId { id = "invariant.rtg.controller.failed_cutover_replay_preserves_status"; } }
    requirement cutoverOrder { subject controller : RtgController; doc /* Cutover ordering preserves referenced state and validation. */ @StableId { id = "invariant.rtg.controller.cutover_order"; } }
    requirement abandonmentNeverDeletesLive { subject controller : RtgController; doc /* Abandonment never deletes live records. */ @StableId { id = "invariant.rtg.controller.abandonment_never_deletes_live_records"; } }
    requirement oneWriteAtATime { subject controller : RtgController; doc /* Only one controller write mutates system or ledger state at a time. */ @StableId { id = "invariant.rtg.controller.one_write_at_a_time"; } }
    requirement ledgerRecordsBlackBoxActivity { subject controller : RtgController; doc /* Ledger records controller requests, results, and visible failures. */ @StableId { id = "invariant.rtg.controller.ledger_records_black_box_activity"; } }
    requirement ledgerPayloadsJsonText { subject controller : RtgController; doc /* Ledger request, response, and error payloads are JSON text. */ @StableId { id = "invariant.rtg.controller.ledger_payloads_are_json_text"; } }
    requirement transactionIdAlwaysAssigned { subject controller : RtgController; doc /* Every controller operation receives a transaction identifier. */ @StableId { id = "invariant.rtg.controller.transaction_id_always_assigned"; } }
    requirement transactionIdsUuids { subject controller : RtgController; doc /* Transaction identifiers are UUIDs. */ @StableId { id = "invariant.rtg.controller.transaction_ids_are_uuids"; } }
    requirement ledgerPositionReplayCursor { subject controller : RtgController; doc /* Ledger position is monotonic and is the replay cursor. */ @StableId { id = "invariant.rtg.controller.ledger_position_is_replay_cursor"; } }
    requirement resolvedUuidsBeforeLedger { subject controller : RtgController; doc /* Batch-local references are resolved before durable ledger recording. */ @StableId { id = "invariant.rtg.controller.resolved_uuids_before_ledger"; } }
    requirement writeAtomicityScoped { subject controller : RtgController; doc /* Failed normalized apply restores touched component state within the controller scope. */ @StableId { id = "invariant.rtg.controller.write_atomicity_scoped"; } }
    requirement readsMediated { subject controller : RtgController; doc /* Application reads pass through controller public contracts. */ @StableId { id = "invariant.rtg.controller.reads_mediated"; } }
    requirement liveFlipsViaFullRecordWrite { subject controller : RtgController; doc /* Live-status changes preserve complete public records. */ @StableId { id = "invariant.rtg.controller.live_flips_via_full_record_write"; } }
    requirement graphTypeIsSchemaTypeKey { subject controller : RtgController; doc /* Graph object type values correspond to schema type keys. */ @StableId { id = "invariant.rtg.controller.graph_type_is_schema_type_key"; } }

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
