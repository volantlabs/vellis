package VellisOperations {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;
    private import BibliotekRtgGraph::*;
    private import BibliotekRtgSchema::*;
    private import BibliotekRtgMigration::*;
    private import BibliotekRtgQuery::*;
    private import BibliotekRtgChangeValidation::*;
    private import BibliotekRtgController::*;

    @ExternalEncodingProfile {
        memberNames = ExternalNamingConvention::lowerSnakeCase;
        enumLiterals = ExternalNamingConvention::lowerSnakeCase;
    }

    enum def VellisUsageGuideTopic {
        enum mcpBootstrapChecklist; enum operatorCard; enum workflowPatterns;
        enum requestPatterns; enum schemaStagingMinimal; enum toolCallShapes;
        enum liveWrite; enum lookupExamples; enum queryExamples;
        enum recoveryAndReplay; enum migrationHistory; enum migrationAbandonment;
    }
    enum def VellisQueryResponseFormat {
        enum full;
        enum propertiesOnly { @ExternalName { name = "properties_only"; } }
    }
    enum def VellisResolutionStatus { enum resolved; }
    enum def VellisSnapshotSummaryStatus {
        enum snapshotExported { @ExternalName { name = "snapshot_exported"; } }
    }

    attribute def JsonObjectList { attribute values[0..*] : JsonObject; doc /* Encodes directly as a JSON array, not an object containing values. */ }
    attribute def StringList { attribute values[0..*] : String; doc /* Encodes directly as a JSON array, not an object containing values. */ }
    attribute def RtgGraphLinkWriteList { attribute values[0..*] : RtgGraphLinkWrite; doc /* Encodes directly as a JSON array of canonical link-write objects. */ }
    attribute def VellisUsageGuide { attribute topic : VellisUsageGuideTopic; attribute content : JsonObject; }
    attribute def VellisSchemaDefinitionRequest { attribute kind : RtgSchemaDefinitionKind; attribute typeKey : String; attribute description : String; attribute payload : RtgSchemaPayload; doc /* Description and typeKey are non-empty; payload family must match kind. */ }
    attribute def VellisSchemaDefinitionRequestList { attribute definitions[1..*] : VellisSchemaDefinitionRequest; doc /* Encodes directly as the schema_definitions JSON array. */ }
    attribute def VellisSchemaRetirement { attribute kind : RtgSchemaDefinitionKind; attribute typeKey : String; }
    attribute def VellisSchemaRetirementList { attribute definitions[0..*] : VellisSchemaRetirement; doc /* Encodes directly as the retire_live_schema JSON array. */ }
    attribute def VellisAnchorFact { attribute ref[0..1] : RtgChangeReference; attribute type : String; attribute properties : JsonObject; attribute system : JsonObject; }
    attribute def VellisAnchorRecord { attribute ref : RtgChangeReference; attribute type : String; attribute displayName[0..1] : String; attribute system : JsonObject; attribute facts[0..*] : VellisAnchorFact; }
    attribute def VellisAnchorRecordList { attribute records[1..*] : VellisAnchorRecord; doc /* Encodes directly as the anchor_records JSON array. */ }
    attribute def VellisGeneratedFactReference { attribute anchorIndex : Integer; attribute factIndex : Integer; attribute localRef : String; }
    attribute def VellisGeneratedReferences { attribute facts[0..*] : VellisGeneratedFactReference; }
    attribute def VellisSchemaMigrationResult { attribute generatedSchemaIds : JsonObject; attribute submittedKnowledgeChanges : RtgChangeBatch; attribute operation : RtgControllerOperationResult; }
    attribute def VellisAnchorValidationResult { attribute submittedGraphChanges : RtgGraphChangeSet; attribute generatedRefs : VellisGeneratedReferences; attribute validation : RtgControllerLiveGraphValidationResult; }
    attribute def VellisAnchorApplyResult { attribute submittedGraphChanges : RtgGraphChangeSet; attribute generatedRefs : VellisGeneratedReferences; attribute operation : RtgControllerOperationResult; }
    attribute def VellisQueryResponseOptions { attribute format : VellisQueryResponseFormat = VellisQueryResponseFormat::full; }
    attribute def VellisQueryPropertiesRow { attribute rowIndex : Integer; attribute properties : JsonObject; }
    attribute def VellisQueryPropertiesResponse { attribute status : String; attribute format : VellisQueryResponseFormat; attribute rowCount : Integer; attribute rows[0..*] : VellisQueryPropertiesRow; attribute diagnostics[0..*] : RtgQueryDiagnostic; doc /* status is query_executed and format is properties_only. */ }
    attribute def VellisQueryResponse { doc /* Discriminated response: full returns the canonical RtgQueryResult directly; properties_only returns VellisQueryPropertiesResponse and may add query.return_properties_empty guidance without changing matching. */ }
    attribute def VellisResolvedAnchor { attribute resourceId : Uuid; attribute properties : JsonObject; }
    attribute def VellisAnchorResolutionResult { attribute status : VellisResolutionStatus; attribute matchCount : Integer; attribute matches[0..*] : VellisResolvedAnchor; attribute submittedQuery : JsonObject; attribute diagnostics[0..*] : RtgQueryDiagnostic; attribute guidance[0..*] : String; }
    attribute def VellisSnapshotExport { doc /* Discriminated response: summary=false returns RtgSystemSnapshot directly; summary=true returns status=snapshot_exported plus a compact summary. */ }
    attribute def VellisSnapshotSummaryExport :> VellisSnapshotExport { attribute status : VellisSnapshotSummaryStatus; attribute summary : JsonObject; }
    attribute def VellisPersistedSnapshotResult { attribute status : RtgControllerOperationStatus; attribute transactionId : Uuid; attribute ledgerPosition[0..1] : Integer; attribute appliedChanges : RtgControllerAppliedChanges; attribute validationReport[0..1] : RtgValidationReport; attribute snapshot[0..1] : RtgSystemSnapshot; attribute details : JsonObject; attribute relativePath : JsonRelativePath; attribute summary : JsonObject; doc /* Mirrors the controller result, adds relativePath and summary, and omits snapshot when return_snapshot is false. */ }
    attribute def VellisLoadedSnapshotResult { attribute relativePath : JsonRelativePath; attribute snapshot[0..1] : RtgSystemSnapshot; attribute summary : JsonObject; doc /* snapshot is omitted when return_snapshot is false. */ }
    attribute def VellisRequestInvalid { attribute message : String; attribute diagnostic : JsonObject; }

    action def RtgGetSystemState {
        out result : RtgControllerSystemState[1];
        doc /* Return state classification, counts, ledger pointers, and recommended next steps. */
        @StableId { id = "operation.vellis.rtg_get_system_state"; }
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerDiscoveryFailed"); obligation = "Failure is encoded without changing controller or application state."; }
    }
    action def RtgGetUsageGuide {
        in topic : VellisUsageGuideTopic[1];
        out result : VellisUsageGuide[1];
        doc /* Return MCP-accessible workflow guidance and complete generic request examples for exactly one declared topic; it does not invent domain schema. */
        @StableId { id = "operation.vellis.rtg_get_usage_guide"; }
        @FailureContract { errorIds = ("VellisRequestInvalid"); obligation = "Unknown topics return a typed input failure and have no effect."; }
    }
    action def RtgStageSchemaMigration {
        in migration_id : String[1]; in description : String[1];
        in schema_definitions : VellisSchemaDefinitionRequestList[1];
        in retire_live_schema : VellisSchemaRetirementList[0..1];
        in validation_mode : RtgControllerValidationMode[0..1] = RtgControllerValidationMode::strict; out result : VellisSchemaMigrationResult[1];
        doc /* Generate a UUID for each schema candidate, force each candidate non-live, resolve each retirement to exactly one live definition, create a ready migration whose membership covers those candidates, submit canonical staged knowledge changes, and return generated IDs, submitted changes, and the controller outcome. */
        @StableId { id = "operation.vellis.rtg_stage_schema_migration"; }
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerValidationFailed", "RtgControllerPreconditionFailed", "RtgControllerApplyFailed"); obligation = "Invalid shaping or retirement selection has no staging effect; downstream controller atomicity applies after submission."; }
    }
    action def RtgValidateLiveAnchorRecords {
        in anchor_records : VellisAnchorRecordList[1]; in link_writes : RtgGraphLinkWriteList[0..1];
        in validation_options : RtgControllerValidationOptions[0..1]; out result : VellisAnchorValidationResult[1];
        doc /* Compile each anchor and nested fact into canonical writes, generate deterministic request-local fact references where omitted, pass through canonical link writes, and return compiled changes plus validation without mutation or ledger writes. */
        @StableId { id = "operation.vellis.rtg_validate_live_anchor_records"; }
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerPreconditionFailed", "RtgValidationInputInvalid"); obligation = "Compilation or validation failure has no component or ledger effect."; }
    }
    action def RtgApplyLiveAnchorRecords {
        in anchor_records : VellisAnchorRecordList[1]; in link_writes : RtgGraphLinkWriteList[0..1];
        in validation_mode : RtgControllerValidationMode[0..1] = RtgControllerValidationMode::strict; out result : VellisAnchorApplyResult[1];
        doc /* Compile anchor-with-facts input identically to the validation action, apply the canonical graph changes through the controller, and return compiled changes, generated fact references, and operation outcome. */
        @StableId { id = "operation.vellis.rtg_apply_live_anchor_records"; }
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerValidationFailed", "RtgControllerApplyFailed"); obligation = "Compilation failure has no effect; controller atomicity governs submitted mutations."; }
    }
    action def RtgValidateLiveGraphChanges {
        in graph_changes : RtgGraphChangeSet[1]; in validation_options : RtgControllerValidationOptions[0..1];
        out result : RtgControllerLiveGraphValidationResult[1];
        doc /* Validate normal live graph CRUD without mutation or ledger writes. */
        @StableId { id = "operation.vellis.rtg_validate_live_graph_changes"; }
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerPreconditionFailed", "RtgValidationInputInvalid"); obligation = "The dry-run never mutates component or ledger state."; }
    }
    action def RtgApplyLiveGraphChanges {
        in graph_changes : RtgGraphChangeSet[1]; in validation_mode : RtgControllerValidationMode[0..1] = RtgControllerValidationMode::strict;
        out result : RtgControllerOperationResult[1];
        doc /* Apply normal live graph CRUD through strict controller policy by default. */
        @StableId { id = "operation.vellis.rtg_apply_live_graph_changes"; }
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerValidationFailed", "RtgControllerApplyFailed"); obligation = "The facade adds no mutation outside the controller lane."; }
    }
    action def RtgStageKnowledgeChanges {
        in knowledge_changes : RtgChangeBatch[1]; in validation_mode : RtgControllerValidationMode[0..1] = RtgControllerValidationMode::strict;
        out result : RtgControllerOperationResult[1];
        doc /* Stage advanced normalized migration-scoped knowledge changes. */
        @StableId { id = "operation.vellis.rtg_stage_knowledge_changes"; }
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerValidationFailed", "RtgControllerPreconditionFailed", "RtgControllerApplyFailed"); obligation = "The facade preserves controller validation and rollback behavior."; }
    }
    action def RtgApplyMigrationCutover {
        in migration_id : String[1]; in cutover_options : RtgControllerCutoverOptions[0..1];
        out result : RtgControllerOperationResult[1];
        doc /* Apply the selected migration cutover with validation and failure restoration. */
        @StableId { id = "operation.vellis.rtg_apply_migration_cutover"; }
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerValidationFailed", "RtgControllerPreconditionFailed", "RtgControllerApplyFailed"); obligation = "The facade does not weaken cutover restoration or ledger semantics."; }
    }
    action def RtgAbandonMigration {
        in migration_id : String[1]; in reason : String[0..1]; out result : RtgControllerOperationResult[1];
        doc /* Abandon safe non-live staged work without deleting live records. */
        @StableId { id = "operation.vellis.rtg_abandon_migration"; }
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerPreconditionFailed", "RtgControllerApplyFailed"); obligation = "Failure preserves controller abandonment guarantees."; }
    }
    action def RtgExecuteQuery {
        in query_spec : RtgQuerySpec[1]; in query_options : RtgQueryOptions[0..1];
        in response_options : VellisQueryResponseOptions[0..1]; out result : VellisQueryResponse[1];
        doc /* Execute the canonical read-only query. full returns RtgQueryResult unchanged; properties_only returns row_index plus requested properties, row count, and diagnostics, adding empty-return-property guidance when appropriate. */
        @StableId { id = "operation.vellis.rtg_execute_query"; }
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgQuerySpecInvalid", "RtgQueryUnsupported"); obligation = "Query and shaping failures have no state or ledger effect."; }
    }
    action def RtgResolveAnchorByFact {
        in anchor_type : String[1]; in data_type : String[1]; in property_path : StringList[1];
        in value : JsonValue[1]; in case_sensitive : Boolean[0..1] = false; out result : VellisAnchorResolutionResult[1];
        doc /* Build one live-only anchor-plus-associated-data equality query, return resolved status, deterministic matches with resource IDs and selected properties, the submitted query/options, query diagnostics, and guidance that distinguishes zero, one, and multiple matches. */
        @StableId { id = "operation.vellis.rtg_resolve_anchor_by_fact"; }
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgQuerySpecInvalid", "RtgQueryUnsupported"); obligation = "Resolution is read-only and never guesses an identity."; }
    }
    action def RtgGetObject { in object_uuid : String[1]; out result : RtgObject[1]; doc /* Return one graph object by UUID without lifecycle filtering or mutation. */ @StableId { id = "operation.vellis.rtg_get_object"; } @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerObjectNotFound"); obligation = "Failure has no state or ledger effect."; } }
    action def RtgListMigrations { in status : RtgMigrationStatus[0..1]; out result : RtgMigrationRecordList[1]; doc /* Return every current migration, or one status, in deterministic migration-ID order. */ @StableId { id = "operation.vellis.rtg_list_migrations"; } @FailureContract { errorIds = ("VellisRequestInvalid", "RtgMigrationStatusInvalid"); obligation = "Failure has no state or ledger effect."; } }
    action def RtgGetMigration { in migration_id : String[1]; out result : RtgMigrationRecord[1]; doc /* Return one current migration record by stable migration ID. */ @StableId { id = "operation.vellis.rtg_get_migration"; } @FailureContract { errorIds = ("VellisRequestInvalid", "RtgMigrationNotFound"); obligation = "Failure has no state or ledger effect."; } }
    action def RtgValidateGraph {
        in migration_ids : StringList[0..1]; in validation_options : RtgControllerValidationOptions[0..1];
        out result : RtgValidationReport[1];
        doc /* Validate current or migration-projected state without mutation. */
        @StableId { id = "operation.vellis.rtg_validate_graph"; }
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerValidationFailed"); obligation = "Blocking findings are returned in a report; only unusable input or execution raises, and no state changes."; }
    }
    action def RtgDiscoverAnchorTypes { in discovery_options : RtgControllerDiscoveryOptions[0..1]; out result : RtgAnchorTypeDiscoveryResult[1]; doc /* Return schema type keys, descriptions, and live counts; exclude non-live types by default and honor a positive optional limit. */ @StableId { id = "operation.vellis.rtg_discover_anchor_types"; } @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerDiscoveryFailed"); obligation = "Discovery is read-only."; } }
    action def RtgGetSchemaPack { in anchor_type_keys : StringList[1]; in schema_pack_options : RtgControllerSchemaPackOptions[0..1]; out result : RtgControllerSchemaPack[1]; doc /* Return selected anchor schemas, associated-data schemas, participating link schemas, and requested live counts. */ @StableId { id = "operation.vellis.rtg_get_schema_pack"; } @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerDiscoveryFailed"); obligation = "Schema-pack reads have no effect."; } }
    action def RtgExportSystemSnapshot { in summary : Boolean[0..1] = false; out result : VellisSnapshotExport[1]; doc /* Return the full coordinated snapshot when summary is false; otherwise return snapshot_exported plus compact component counts and ledger pointers. */ @StableId { id = "operation.vellis.rtg_export_system_snapshot"; } @FailureContract { errorIds = ("RtgControllerSnapshotFailed"); obligation = "Export has no state or ledger effect."; } }
    action def RtgPersistSystemSnapshot { in relative_path : JsonRelativePath[1]; in return_snapshot : Boolean[0..1] = true; out result : VellisPersistedSnapshotResult[1]; doc /* Persist a coordinated snapshot, add relative path and compact summary to the controller result, and omit the full snapshot only when requested. */ @StableId { id = "operation.vellis.rtg_persist_system_snapshot"; } @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerSnapshotFailed", "RtgControllerApplyFailed"); obligation = "Failure exposes no partial JSON document."; } }
    action def RtgListPersistedSnapshots { out result : RtgPersistedSnapshotList[1]; doc /* List only persisted snapshot-like documents visible through the configured JSON storage root. */ @StableId { id = "operation.vellis.rtg_list_persisted_snapshots"; } @FailureContract { errorIds = ("RtgControllerSnapshotFailed"); obligation = "Listing is read-only."; } }
    action def RtgLoadPersistedSnapshot { in relative_path : JsonRelativePath[1]; in return_snapshot : Boolean[0..1] = true; out result : VellisLoadedSnapshotResult[1]; doc /* Load and validate one persisted snapshot, always return path and compact summary, and omit the full snapshot only when requested; do not apply it. */ @StableId { id = "operation.vellis.rtg_load_persisted_snapshot"; } @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerSnapshotFailed"); obligation = "Loading has no current-state effect."; } }
    action def RtgReplayLedger { in replay_options : RtgControllerReplayOptions[0..1]; out result : RtgControllerOperationResult[1]; doc /* Reconstruct state from an empty or explicit snapshot seed using the selected ascending ledger window. */ @StableId { id = "operation.vellis.rtg_replay_ledger"; } @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerReplayFailed"); obligation = "Rejected replay inputs expose no partial reconstructed state."; } }
    action def RtgVerifyReplayFromLedger { in replay_options : RtgControllerReplayOptions[0..1]; out result : RtgControllerReplayVerificationResult[1]; doc /* Replay into isolated state and return summaries, count differences, replay window, and validation without replacing current state. */ @StableId { id = "operation.vellis.rtg_verify_replay_from_ledger"; } @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerReplayFailed"); obligation = "Verification leaves current state and source ledger unchanged."; } }
    action def RtgListMigrationHistory { out result : RtgControllerMigrationHistory[1]; doc /* Return ledger-backed staged, cutover-applied, cutover-failed, and abandoned events in ledger order. */ @StableId { id = "operation.vellis.rtg_list_migration_history"; } @FailureContract { errorIds = ("RtgControllerReplayFailed"); obligation = "History inspection is read-only."; } }
    action def RtgFlushLedgerFailures { out result : RtgControllerOperationResult[1]; doc /* Retry queued audit records in original order and report remaining degraded-audit state. */ @StableId { id = "operation.vellis.rtg_flush_ledger_failures"; } @FailureContract { errorIds = ("RtgControllerApplyFailed"); obligation = "Unflushed records remain queued and legible."; } }
    action def RtgRestoreFromSnapshot { in snapshot : RtgSystemSnapshot[1]; in restore_options : RtgControllerRestoreOptions[0..1]; out result : RtgControllerOperationResult[1]; doc /* Validate and atomically restore coordinated state; record the operation by default and reserve skip for internal recovery. */ @StableId { id = "operation.vellis.rtg_restore_from_snapshot"; } @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerSnapshotFailed"); obligation = "Failure exposes no partially restored state."; } }

    requirement facadeFailureSemantics { subject facade : VellisApplicationFacade; doc /* Input decoding rejects unknown fields, wrong JSON kinds, invalid enum literals, missing required values, and contradictory option shapes as VellisRequestInvalid before controller invocation. Modeled Bibliotek failures propagate without changing their concrete type, message, diagnostic, transaction identity, or validation evidence. */ @StableId { id = "contract.vellis.facade.failures"; } }
    requirement facadeFreedom { subject facade : VellisApplicationFacade; doc /* The facade may choose any implementation language or helper decomposition but must preserve the modeled request compilation, controller invocation, response shaping, defaults, ordering, and no-effect guarantees. */ @StableId { id = "contract.vellis.facade.implementation_freedom"; } }
    requirement usageGuideSemantics { subject operation : RtgGetUsageGuide; doc /* The twelve guide topics cover: MCP bootstrap sequence; concise operator rules; state-driven workflows; ordinary-request-to-workflow mapping; minimal schema staging; exact top-level tool shapes; live writes; identity lookup before links; query construction; snapshot/restore/replay recovery; durable migration history; and safe abandonment. Examples use complete generic envelopes and never invent application-domain schema. */ @StableId { id = "contract.vellis.facade.usage_guides"; } }
    requirement schemaMigrationCompilation { subject operation : RtgStageSchemaMigration; doc /* Each requested definition becomes one newly identified non-live schema write and one schema_make_live member. Each retirement selector must resolve to exactly one live definition and becomes schema_make_non_live. One ready migration with the supplied ID and description owns the membership; the returned submitted batch is exactly the batch passed to staging. */ @StableId { id = "contract.vellis.facade.schema_migration_compilation"; } }
    requirement anchorRecordCompilation { subject facade : VellisApplicationFacade; doc /* Each anchor record becomes one canonical anchor write. Each nested fact becomes one data-object write associated to that anchor; an omitted fact reference receives a unique request-local reference reported in generatedRefs. Link writes pass through unchanged. Validation and apply use the identical compilation. */ @StableId { id = "contract.vellis.facade.anchor_record_compilation"; } }
    requirement queryFacadeSemantics { subject facade : VellisApplicationFacade; doc /* Full query responses preserve the canonical query result. properties_only retains final row order, row_index, selected properties, and diagnostics while omitting bindings and unrequested records. Anchor resolution compiles one live-only equality query and returns every deterministic match without guessing uniqueness. */ @StableId { id = "contract.vellis.facade.query_semantics"; } }
    requirement snapshotFacadeSemantics { subject facade : VellisApplicationFacade; doc /* Full export returns the canonical snapshot; summary export returns snapshot_exported and compact counts/pointers. Persist and load always add compact summary and relative path, and return_snapshot=false removes only the full snapshot payload. No response shaping changes stored or current state. */ @StableId { id = "contract.vellis.facade.snapshot_semantics"; } }
    requirement controllerForwardingSemantics { subject facade : VellisApplicationFacade; doc /* Actions not identified as compilation or shaping workflows decode their modeled inputs, invoke exactly the satisfied controller capability once, and encode the modeled result without adding state, filtering, retries, ordering, or lifecycle policy. */ @StableId { id = "contract.vellis.facade.controller_forwarding"; } }

    part def VellisApplicationFacade {
        @SpecIdentity { id = "application.vellis.facade"; lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        @DependencyPolicy { allowedComponentIds = ("component.rtg.controller"); forbiddenComponentIds = ("component.rtg.graph", "component.rtg.schema", "component.rtg.constraints", "component.rtg.migration"); }
        ref action requiredApplyLiveGraphChanges[0..*] : ApplyLiveGraphChanges { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredValidateLiveGraphChanges[0..*] : ValidateLiveGraphChanges { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredStageKnowledgeChanges[0..*] : StageKnowledgeChanges { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredApplyMigrationCutover[0..*] : ApplyMigrationCutover { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredExecuteQuery[0..*] : ExecuteControllerQuery { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredGetObject[0..*] : ControllerGetObject { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredListMigrations[0..*] : ControllerListMigrations { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredGetMigration[0..*] : ControllerGetMigration { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredValidateGraph[0..*] : ValidateGraph { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredDiscoverAnchorTypes[0..*] : DiscoverAnchorTypes { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredGetSchemaPack[0..*] : GetControllerSchemaPack { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredGetSystemState[0..*] : GetSystemState { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredExportSystemSnapshot[0..*] : ExportSystemSnapshot { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredPersistSystemSnapshot[0..*] : PersistSystemSnapshot { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredListPersistedSnapshots[0..*] : ListPersistedSnapshots { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredLoadPersistedSnapshot[0..*] : LoadPersistedSnapshot { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredAbandonMigration[0..*] : AbandonMigration { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredReplayLedger[0..*] : ReplayLedger { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredVerifyReplayFromLedger[0..*] : VerifyReplayFromLedger { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredListMigrationHistory[0..*] : ListMigrationHistory { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredFlushLedgerFailures[0..*] : FlushLedgerFailures { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        ref action requiredRestoreFromSnapshot[0..*] : RestoreFromSnapshot { @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; } }
        perform action rtgGetSystemState[0..*] : RtgGetSystemState;
        perform action rtgGetUsageGuide[0..*] : RtgGetUsageGuide { @StateAccess { kind = StateAccessKind::none; effect = "select one modeled guide topic and return static application guidance"; } }
        perform action rtgStageSchemaMigration[0..*] : RtgStageSchemaMigration;
        perform action rtgValidateLiveAnchorRecords[0..*] : RtgValidateLiveAnchorRecords;
        perform action rtgApplyLiveAnchorRecords[0..*] : RtgApplyLiveAnchorRecords;
        perform action rtgValidateLiveGraphChanges[0..*] : RtgValidateLiveGraphChanges;
        perform action rtgApplyLiveGraphChanges[0..*] : RtgApplyLiveGraphChanges;
        perform action rtgStageKnowledgeChanges[0..*] : RtgStageKnowledgeChanges;
        perform action rtgApplyMigrationCutover[0..*] : RtgApplyMigrationCutover;
        perform action rtgAbandonMigration[0..*] : RtgAbandonMigration;
        perform action rtgExecuteQuery[0..*] : RtgExecuteQuery;
        perform action rtgResolveAnchorByFact[0..*] : RtgResolveAnchorByFact;
        perform action rtgGetObject[0..*] : RtgGetObject;
        perform action rtgListMigrations[0..*] : RtgListMigrations;
        perform action rtgGetMigration[0..*] : RtgGetMigration;
        perform action rtgValidateGraph[0..*] : RtgValidateGraph;
        perform action rtgDiscoverAnchorTypes[0..*] : RtgDiscoverAnchorTypes;
        perform action rtgGetSchemaPack[0..*] : RtgGetSchemaPack;
        perform action rtgExportSystemSnapshot[0..*] : RtgExportSystemSnapshot;
        perform action rtgPersistSystemSnapshot[0..*] : RtgPersistSystemSnapshot;
        perform action rtgListPersistedSnapshots[0..*] : RtgListPersistedSnapshots;
        perform action rtgLoadPersistedSnapshot[0..*] : RtgLoadPersistedSnapshot;
        perform action rtgReplayLedger[0..*] : RtgReplayLedger;
        perform action rtgVerifyReplayFromLedger[0..*] : RtgVerifyReplayFromLedger;
        perform action rtgListMigrationHistory[0..*] : RtgListMigrationHistory;
        perform action rtgFlushLedgerFailures[0..*] : RtgFlushLedgerFailures;
        perform action rtgRestoreFromSnapshot[0..*] : RtgRestoreFromSnapshot;

        dependency getStateFlow from rtgGetSystemState to requiredGetSystemState { @CapabilityUse { effect = "return the controller state summary unchanged"; } }
        dependency schemaStageReadFlow from rtgStageSchemaMigration to requiredExportSystemSnapshot { @CapabilityUse { effect = "resolve each retirement selector to exactly one current live schema definition"; } }
        dependency schemaStageWriteFlow from rtgStageSchemaMigration to requiredStageKnowledgeChanges { @CapabilityUse { effect = "submit the compiled non-live candidates and ready migration as one canonical staged batch"; } }
        dependency validateAnchorFlow from rtgValidateLiveAnchorRecords to requiredValidateLiveGraphChanges { @CapabilityUse { effect = "compile ergonomic records and invoke the no-mutation canonical validation lane"; } }
        dependency applyAnchorFlow from rtgApplyLiveAnchorRecords to requiredApplyLiveGraphChanges { @CapabilityUse { effect = "compile ergonomic records and invoke the canonical live mutation lane"; } }
        dependency validateGraphChangesFlow from rtgValidateLiveGraphChanges to requiredValidateLiveGraphChanges { @CapabilityUse { effect = "decode and forward canonical graph changes without mutation"; } }
        dependency applyGraphChangesFlow from rtgApplyLiveGraphChanges to requiredApplyLiveGraphChanges { @CapabilityUse { effect = "decode and forward canonical live graph changes"; } }
        dependency stageKnowledgeFlow from rtgStageKnowledgeChanges to requiredStageKnowledgeChanges { @CapabilityUse { effect = "decode and forward the advanced canonical staging batch"; } }
        dependency cutoverFlow from rtgApplyMigrationCutover to requiredApplyMigrationCutover { @CapabilityUse { effect = "decode options and invoke the controller cutover contract"; } }
        dependency abandonFlow from rtgAbandonMigration to requiredAbandonMigration { @CapabilityUse { effect = "invoke safe abandonment and candidate pruning"; } }
        dependency executeQueryFlow from rtgExecuteQuery to requiredExecuteQuery { @CapabilityUse { effect = "execute the canonical query, then shape only the returned representation"; } }
        dependency resolveAnchorFlow from rtgResolveAnchorByFact to requiredExecuteQuery { @CapabilityUse { effect = "compile one live anchor/fact equality query and shape its matches and guidance"; } }
        dependency getObjectFlow from rtgGetObject to requiredGetObject { @CapabilityUse { effect = "forward identity read without lifecycle filtering"; } }
        dependency listMigrationsFlow from rtgListMigrations to requiredListMigrations { @CapabilityUse { effect = "forward the optional status filter"; } }
        dependency getMigrationFlow from rtgGetMigration to requiredGetMigration { @CapabilityUse { effect = "forward the stable migration identity"; } }
        dependency validateStateFlow from rtgValidateGraph to requiredValidateGraph { @CapabilityUse { effect = "validate current or projected state without mutation"; } }
        dependency discoveryFlow from rtgDiscoverAnchorTypes to requiredDiscoverAnchorTypes { @CapabilityUse { effect = "forward discovery options and return composed schema/count results"; } }
        dependency schemaPackFlow from rtgGetSchemaPack to requiredGetSchemaPack { @CapabilityUse { effect = "forward selected anchor types and pack options"; } }
        dependency exportSnapshotFlow from rtgExportSystemSnapshot to requiredExportSystemSnapshot { @CapabilityUse { effect = "return the full snapshot or derive a compact summary without mutation"; } }
        dependency persistSnapshotFlow from rtgPersistSystemSnapshot to requiredPersistSystemSnapshot { @CapabilityUse { effect = "persist the snapshot, then add path/summary shaping and optional payload omission"; } }
        dependency listSnapshotsFlow from rtgListPersistedSnapshots to requiredListPersistedSnapshots { @CapabilityUse { effect = "return storage-scoped snapshot listings"; } }
        dependency loadSnapshotFlow from rtgLoadPersistedSnapshot to requiredLoadPersistedSnapshot { @CapabilityUse { effect = "load without applying, add summary, and optionally omit the full snapshot"; } }
        dependency replayFlow from rtgReplayLedger to requiredReplayLedger { @CapabilityUse { effect = "decode replay options and invoke state reconstruction"; } }
        dependency verifyReplayFlow from rtgVerifyReplayFromLedger to requiredVerifyReplayFromLedger { @CapabilityUse { effect = "invoke isolated replay verification without current-state mutation"; } }
        dependency historyFlow from rtgListMigrationHistory to requiredListMigrationHistory { @CapabilityUse { effect = "return ordered ledger-backed migration history"; } }
        dependency flushAuditFlow from rtgFlushLedgerFailures to requiredFlushLedgerFailures { @CapabilityUse { effect = "retry queued audit records and return remaining degraded-audit detail"; } }
        dependency restoreFlow from rtgRestoreFromSnapshot to requiredRestoreFromSnapshot { @CapabilityUse { effect = "decode and invoke atomic coordinated restoration"; } }
    }

    verification def VellisFacadeBoundaryVerification {
        subject facade : VellisApplicationFacade;
        objective { verify facadeFailureSemantics; verify facadeFreedom; verify usageGuideSemantics; verify schemaMigrationCompilation; verify anchorRecordCompilation; verify queryFacadeSemantics; verify snapshotFacadeSemantics; verify controllerForwardingSemantics; }
        @EvidenceBinding { verificationId = "verification.vellis.facade.boundary"; evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py"; implementationScope = "VellisApplicationFacade"; }
    }
}
