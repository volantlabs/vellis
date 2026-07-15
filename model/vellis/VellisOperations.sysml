package VellisOperations {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import BibliotekStorageJsonFile::*;
    private import ScalarValues::*;
    private import BibliotekRtgGraph::*;
    private import BibliotekRtgSchema::*;
    private import BibliotekRtgMigration::*;
    private import BibliotekRtgQuery::*;
    private import BibliotekRtgChangeValidation::*;
    private import BibliotekRtgController::*;
    private import BibliotekRtgDiagnostics::*;
    private import BibliotekRuntimeMessageRuntime::*;

    enum def VellisUsageGuideTopic {
        enum mcpBootstrapChecklist; enum operatorCard; enum workflowPatterns;
        enum requestPatterns; enum schemaStagingMinimal; enum toolCallShapes;
        enum liveWrite; enum lookupExamples; enum queryExamples;
        enum recoveryAndReplay; enum migrationHistory; enum migrationAbandonment;
        enum everydayLifeSchema; enum schemaDesign; enum capabilities;
    }
    enum def VellisQueryResponseFormat {
        enum full;
        enum properties_only;
    }
    enum def VellisMutationResponseFormat { enum compact; enum full; }
    enum def VellisQueryResponseKind { enum full; enum properties_only; }
    enum def VellisResolutionStatus { enum resolved; }
    enum def VellisSnapshotSummaryStatus {
        enum snapshot_exported;
    }
    enum def VellisStarterSchemaState { enum installed; enum custom; enum empty; }
    enum def VellisReconstructionVerificationStatus {
        enum reconstruction_verified;
        enum isolated_reconstruction_required;
    }
    enum def VellisRuntimeHistorySource { enum runtime_ledger; }
    enum def VellisRestoreLedgerMode { enum record; }

    attribute def JsonObjectList { attribute values[0..*] : JsonObject; doc /* Encodes directly as a JSON array, not an object containing values. */ }
    attribute def StringList { attribute values[0..*] : String; doc /* Encodes directly as a JSON array, not an object containing values. */ }
    attribute def RtgGraphLinkWriteList { attribute values[0..*] : RtgGraphLinkWrite; doc /* Encodes directly as a JSON array of canonical link-write objects. */ }
    attribute def VellisUsageGuide { attribute topic : VellisUsageGuideTopic; attribute content : JsonObject; doc /* The logical guide has one typed topic and topic-specific JSON content. The MCP realization uses an explicit flattened codec that emits topic alongside the content fields for compatibility with the established guide wire format. */ }
    attribute def VellisStarterSchemaSummary {
        attribute ontologyId : String;
        attribute version : String;
        attribute status : VellisStarterSchemaState;
        attribute anchorTypeKeys[0..*] : String;
        attribute linkTypeKeys[0..*] : String;
        attribute recovery : String;
    }
    attribute def VellisRuntimeState {
        attribute runtimeId : Uuid;
        attribute runtimeKey : String;
        attribute health : String;
        attribute currentPosition : Integer;
        attribute messageCount : Integer;
        attribute lastTraceId[0..1] : Uuid;
        attribute lastTracePosition[0..1] : Integer;
        attribute lastTraceDisposition[0..1] : RuntimeTraceDisposition;
        doc /* Read-only application projection of runtime identity, health, chronology, and the most recent terminal trace. */
    }
    attribute def VellisSystemState :> RtgControllerSystemState {
        attribute starterSchema : VellisStarterSchemaSummary;
        attribute runtime : VellisRuntimeState;
    }
    attribute def VellisSchemaDefinitionRequest { attribute kind : RtgSchemaDefinitionKind; attribute typeKey : String; attribute description : String; attribute payload : RtgSchemaPayload; doc /* Description and typeKey are non-empty; payload family must match kind. */ }
    attribute def VellisSchemaDefinitionRequestList { attribute definitions[1..*] : VellisSchemaDefinitionRequest; doc /* Encodes directly as the schema_definitions JSON array. Each kind-and-typeKey pair is unique within one request so generated-schema identity correlation is lossless. */ }
    attribute def VellisSchemaRetirement { attribute kind : RtgSchemaDefinitionKind; attribute typeKey : String; }
    attribute def VellisSchemaRetirementList { attribute definitions[0..*] : VellisSchemaRetirement; doc /* Encodes directly as the retire_live_schema JSON array. */ }
    attribute def VellisAnchorFact { attribute 'ref'[0..1] : RtgChangeReference; attribute type : String; attribute properties : JsonObject; attribute system : JsonObject; }
    attribute def VellisAnchorRecord { attribute 'ref' : RtgChangeReference; attribute type : String; attribute displayName[0..1] : String; attribute system : JsonObject; attribute facts[0..*] : VellisAnchorFact; }
    attribute def VellisAnchorRecordList { attribute records[1..*] : VellisAnchorRecord; doc /* Encodes directly as the anchor_records JSON array. */ }
    attribute def VellisGeneratedFactReference { attribute anchorIndex : Integer; attribute factIndex : Integer; attribute localRef : String; }
    attribute def VellisGeneratedReferences { attribute facts[0..*] : VellisGeneratedFactReference; }
    attribute def VellisMutationResponseOptions { attribute format : VellisMutationResponseFormat = VellisMutationResponseFormat::compact; }
    attribute def VellisSchemaMigrationResult { attribute format : VellisMutationResponseFormat; attribute generatedSchemaIds : JsonObject; attribute submittedKnowledgeChanges[0..1] : RtgChangeBatch; attribute operation : RtgControllerOperationResult; doc /* generatedSchemaIds maps each unique kind:type_key request key to the generated durable UUID. */ }
    attribute def VellisAnchorValidationResult { attribute submittedGraphChanges : RtgGraphChangeSet; attribute generatedRefs : VellisGeneratedReferences; attribute validation : RtgControllerLiveGraphValidationResult; }
    attribute def VellisAnchorApplyResult { attribute format : VellisMutationResponseFormat; attribute generatedIds : JsonObject; attribute submittedGraphChanges[0..1] : RtgGraphChangeSet; attribute generatedRefs : VellisGeneratedReferences; attribute operation : RtgControllerOperationResult; }
    attribute def VellisQueryResponseOptions { attribute format : VellisQueryResponseFormat = VellisQueryResponseFormat::full; }
    attribute def VellisQueryPropertiesRow { attribute rowIndex : Integer; attribute properties : JsonObject; }
    abstract attribute def VellisQueryResponse {
        attribute kind : VellisQueryResponseKind;
        doc /* Discriminated response base. Every concrete response fixes exactly one kind, making full and properties-only results distinguishable at the logical boundary. */
    }
    attribute def VellisFullQueryResponse :> VellisQueryResponse, RtgQueryResult {
        :>> kind = VellisQueryResponseKind::full;
        doc /* Full response retaining the complete canonical query result shape. */
    }
    attribute def VellisQueryPropertiesResponse :> VellisQueryResponse { :>> kind = VellisQueryResponseKind::properties_only; attribute status : String; attribute format : VellisQueryResponseFormat = VellisQueryResponseFormat::properties_only; attribute rowCount : Integer; attribute rows[0..*] : JsonObject; attribute totalRowCount : Integer; attribute returnedRowCount : Integer; attribute nextOffset[0..1] : Integer; attribute diagnostics[0..*] : RtgQueryDiagnostic; doc /* Compact response retaining final row order, pagination metadata, and diagnostics; kind and format are properties_only and status is query_executed. Non-aggregate rows encode VellisQueryPropertiesRow. Aggregate rows preserve the canonical aggregation row object: row_index, group_by, and each caller-named aggregation value. */ }
    attribute def VellisResolvedAnchor { attribute resourceId : Uuid; attribute properties : JsonObject; }
    attribute def VellisAnchorResolutionResult { attribute status : VellisResolutionStatus; attribute matchCount : Integer; attribute matches[0..*] : VellisResolvedAnchor; attribute submittedQuery : JsonObject; attribute diagnostics[0..*] : RtgQueryDiagnostic; attribute guidance[0..*] : String; }
    enum def VellisSnapshotExportKind { enum full; enum summary; }
    abstract attribute def VellisSnapshotExport { attribute kind : VellisSnapshotExportKind; doc /* Discriminated base for full and summary snapshot exports. */ }
    attribute def VellisFullSnapshotExport :> VellisSnapshotExport, RtgSystemSnapshot {
        :>> kind = VellisSnapshotExportKind::full;
        doc /* Full coordinated system snapshot. */
    }
    attribute def VellisSnapshotSummaryExport :> VellisSnapshotExport { :>> kind = VellisSnapshotExportKind::summary; attribute status : VellisSnapshotSummaryStatus; attribute summary : JsonObject; }
    attribute def VellisPersistedSnapshotResult { attribute status : RtgControllerOperationStatus; attribute generatedIds : JsonObject; attribute appliedChanges : RtgControllerAppliedChanges; attribute validationReport[0..1] : RtgValidationReport; attribute 'snapshot'[0..1] : RtgSystemSnapshot; attribute details : JsonObject; attribute relativePath : JsonRelativePath; attribute summary : JsonObject; doc /* Mirrors the domain controller result, adds relativePath and summary, and omits snapshot when return_snapshot is false; runtime trace identity and position remain envelope/history metadata rather than domain fields. */ }
    attribute def VellisLoadedSnapshotResult { attribute relativePath : JsonRelativePath; attribute 'snapshot'[0..1] : RtgSystemSnapshot; attribute summary : JsonObject; doc /* snapshot is omitted when return_snapshot is false. */ }
    attribute def VellisReplayVerificationResult {
        attribute status : VellisReconstructionVerificationStatus;
        attribute verified : Boolean;
        attribute throughRuntimePosition[0..1] : Integer;
        attribute requestedThroughRuntimePosition[0..1] : Integer;
        attribute report[0..1] : RuntimeReconstructionReport;
        attribute details : JsonObject;
        doc /* Reports whether the requested cursor has verified reconstruction evidence; arbitrary historical verification requires an isolated data-root copy. */
    }
    attribute def VellisMigrationHistoryEvent {
        attribute eventType : String;
        attribute runtimePosition : Integer;
        attribute traceId[0..1] : Uuid;
        attribute disposition[0..1] : RuntimeTraceDisposition;
        attribute migrationId[0..1] : String;
        attribute arguments : JsonObject;
        doc /* One migration-related controller request projected from its complete runtime trace. */
    }
    attribute def VellisMigrationHistory {
        attribute events[0..*] ordered : VellisMigrationHistoryEvent;
        attribute source : VellisRuntimeHistorySource = VellisRuntimeHistorySource::runtime_ledger;
        attribute throughRuntimePosition : Integer;
        doc /* Runtime-position-ordered migration trace projection; the controller owns no separate history store. */
    }
    attribute def VellisDeprecatedLedgerFlushResult {
        attribute status : String;
        attribute details : JsonObject;
        doc /* Deprecated compatibility response reporting runtime fail-stop health and zero queued degraded records; it performs no flush and changes no state. */
    }
    attribute def VellisRestoreOptions {
        attribute ledgerMode : VellisRestoreLedgerMode default = VellisRestoreLedgerMode::record;
        doc /* Optional compatibility shape. Snapshot restoration is always recorded as authoritative runtime traffic; record is the only valid value. */
    }
    attribute def VellisRequestInvalid { attribute 'message' : String; attribute diagnostic[0..1] : RtgDiagnostic; }

    action def <'operation.vellis.rtg_get_system_state'> RtgGetSystemState {
        out result : VellisSystemState[1];
        doc /* Return RTG domain classification and counts, starter-schema posture, runtime identity and health, current runtime position, and recommended next steps. */
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerDiscoveryFailed"); }
    }
    action def <'operation.vellis.rtg_get_usage_guide'> RtgGetUsageGuide {
        in topic : VellisUsageGuideTopic[1];
        out result : VellisUsageGuide[1];
        doc /* Return MCP-accessible workflow guidance and complete generic request examples for exactly one declared topic; it does not invent domain schema. */
        @FailureContract { errorIds = ("VellisRequestInvalid"); }
    }
    action def <'operation.vellis.rtg_stage_schema_migration'> RtgStageSchemaMigration {
        in migration_id : String[1]; in description : String[1];
        in schema_definitions : VellisSchemaDefinitionRequestList[1];
        in retire_live_schema : VellisSchemaRetirementList[0..1];
        in validation_mode : RtgControllerValidationMode[0..1] default = RtgControllerValidationMode::strict; in response_options : VellisMutationResponseOptions[0..1]; out result : VellisSchemaMigrationResult[1];
        doc /* Generate a UUID for each schema candidate, force each candidate non-live, resolve each retirement to exactly one live definition, create a ready migration whose membership covers those candidates, and submit canonical staged knowledge changes. Compact is the default and omits submittedKnowledgeChanges; full adds exactly the submitted batch without changing the operation. */
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerValidationFailed", "RtgControllerPreconditionFailed", "RtgControllerApplyFailed"); }
    }
    action def <'operation.vellis.rtg_validate_live_anchor_records'> RtgValidateLiveAnchorRecords {
        in anchor_records : VellisAnchorRecordList[1]; in link_writes : RtgGraphLinkWriteList[0..1];
        in validation_options : RtgControllerValidationOptions[0..1]; out result : VellisAnchorValidationResult[1];
        doc /* Compile each anchor and nested fact into canonical writes, generate deterministic request-local fact references where omitted, pass through canonical link writes, and return compiled changes plus validation without component mutation; the runtime still records the request and outcome. */
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerPreconditionFailed", "RtgValidationInputInvalid"); }
    }
    action def <'operation.vellis.rtg_apply_live_anchor_records'> RtgApplyLiveAnchorRecords {
        in anchor_records : VellisAnchorRecordList[1]; in link_writes : RtgGraphLinkWriteList[0..1];
        in validation_mode : RtgControllerValidationMode[0..1] default = RtgControllerValidationMode::strict; in response_options : VellisMutationResponseOptions[0..1]; out result : VellisAnchorApplyResult[1];
        doc /* Compile anchor-with-facts input identically to validation and apply it once through the controller. Compact is the default and returns all generated local-reference UUIDs plus generated fact references while omitting submittedGraphChanges; full adds exactly the submitted graph changes without changing the operation. */
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerValidationFailed", "RtgControllerApplyFailed"); }
    }
    action def <'operation.vellis.rtg_validate_live_graph_changes'> RtgValidateLiveGraphChanges {
        in graph_changes : RtgGraphChangeSet[1]; in validation_options : RtgControllerValidationOptions[0..1];
        out result : RtgControllerLiveGraphValidationResult[1];
        doc /* Validate normal live graph CRUD without component mutation; the runtime still records the request and outcome. */
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerPreconditionFailed", "RtgValidationInputInvalid"); }
    }
    action def <'operation.vellis.rtg_apply_live_graph_changes'> RtgApplyLiveGraphChanges {
        in graph_changes : RtgGraphChangeSet[1]; in validation_mode : RtgControllerValidationMode[0..1] default = RtgControllerValidationMode::strict;
        out result : RtgControllerOperationResult[1];
        doc /* Apply normal live graph CRUD through strict controller policy by default. */
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerValidationFailed", "RtgControllerApplyFailed"); }
    }
    action def <'operation.vellis.rtg_stage_knowledge_changes'> RtgStageKnowledgeChanges {
        in knowledge_changes : RtgChangeBatch[1]; in validation_mode : RtgControllerValidationMode[0..1] default = RtgControllerValidationMode::strict;
        out result : RtgControllerOperationResult[1];
        doc /* Stage advanced normalized migration-scoped knowledge changes. */
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerValidationFailed", "RtgControllerPreconditionFailed", "RtgControllerApplyFailed"); }
    }
    action def <'operation.vellis.rtg_apply_migration_cutover'> RtgApplyMigrationCutover {
        in migration_id : String[1]; in cutover_options : RtgControllerCutoverOptions[0..1];
        out result : RtgControllerOperationResult[1];
        doc /* Apply the selected migration cutover with validation and failure restoration. */
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerValidationFailed", "RtgControllerPreconditionFailed", "RtgControllerApplyFailed", "RtgControllerRecoveryIndeterminate"); }
    }
    action def <'operation.vellis.rtg_abandon_migration'> RtgAbandonMigration {
        in migration_id : String[1]; in reason : String[0..1]; out result : RtgControllerOperationResult[1];
        doc /* Abandon safe non-live staged work without deleting live records. */
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerPreconditionFailed", "RtgControllerApplyFailed"); }
    }
    action def <'operation.vellis.rtg_execute_query'> RtgExecuteQuery {
        in query_spec : RtgQuerySpec[1]; in query_options : RtgQueryOptions[0..1];
        in response_options : VellisQueryResponseOptions[0..1]; out result : VellisQueryResponse[1];
        doc /* Execute the canonical read-only query. full returns RtgQueryResult unchanged. properties_only returns pagination metadata and diagnostics plus either row_index with requested properties for non-aggregate queries or canonical aggregation rows for aggregate queries, adding empty-return-property guidance when appropriate. */
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgQuerySpecInvalid", "RtgQueryUnsupported"); }
    }
    action def <'operation.vellis.rtg_resolve_anchor_by_fact'> RtgResolveAnchorByFact {
        in anchor_type : String[1]; in data_type : String[1]; in property_path : StringList[1];
        in value : JsonValue[1]; in case_sensitive : Boolean[0..1] default = false; out result : VellisAnchorResolutionResult[1];
        doc /* Build one live-only anchor-plus-associated-data equality query, return resolved status, deterministic matches with resource IDs and selected properties, the submitted query/options, query diagnostics, and guidance that distinguishes zero, one, and multiple matches. */
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgQuerySpecInvalid", "RtgQueryUnsupported"); }
    }
    action def <'operation.vellis.rtg_get_object'> RtgGetObject { in object_uuid : String[1]; out result : RtgObject[1]; doc /* Return one graph object by UUID without lifecycle filtering or mutation. */ @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerObjectNotFound"); } }
    action def <'operation.vellis.rtg_list_migrations'> RtgListMigrations { in status : RtgMigrationStatus[0..1]; out result : RtgMigrationRecordList[1]; doc /* Return every current migration, or one status, in deterministic migration-ID order. */ @FailureContract { errorIds = ("VellisRequestInvalid", "RtgMigrationStatusInvalid"); } }
    action def <'operation.vellis.rtg_get_migration'> RtgGetMigration { in migration_id : String[1]; out result : RtgMigrationRecord[1]; doc /* Return one current migration record by stable migration ID. */ @FailureContract { errorIds = ("VellisRequestInvalid", "RtgMigrationNotFound"); } }
    action def <'operation.vellis.rtg_validate_graph'> RtgValidateGraph {
        in migration_ids : StringList[0..1]; in validation_options : RtgControllerValidationOptions[0..1];
        out result : RtgValidationReport[1];
        doc /* Validate current or migration-projected state without mutation. */
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerValidationFailed"); }
    }
    action def <'operation.vellis.rtg_discover_anchor_types'> RtgDiscoverAnchorTypes { in discovery_options : RtgControllerDiscoveryOptions[0..1]; out result : RtgAnchorTypeDiscoveryResult[1]; doc /* Return schema type keys, descriptions, and live counts; exclude non-live types by default and honor a positive optional limit. */ @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerDiscoveryFailed"); } }
    action def <'operation.vellis.rtg_get_schema_pack'> RtgGetSchemaPack { in anchor_type_keys : StringList[1]; in schema_pack_options : RtgControllerSchemaPackOptions[0..1]; out result : RtgControllerSchemaPack[1]; doc /* Return selected anchor schemas, associated-data schemas, participating link schemas, and requested live counts. */ @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerDiscoveryFailed"); } }
    action def <'operation.vellis.rtg_export_system_snapshot'> RtgExportSystemSnapshot { in summary : Boolean[0..1] default = false; out result : VellisSnapshotExport[1]; doc /* Return the full coordinated snapshot when summary is false; otherwise return snapshot_exported plus compact component counts. Runtime chronology remains outside the snapshot payload. */ @FailureContract { errorIds = ("RtgControllerSnapshotFailed"); } }
    action def <'operation.vellis.rtg_persist_system_snapshot'> RtgPersistSystemSnapshot { in relative_path : JsonRelativePath[1]; in return_snapshot : Boolean[0..1] default = true; out result : VellisPersistedSnapshotResult[1]; doc /* Persist a coordinated snapshot, add relative path and compact summary to the domain controller result, and omit the full snapshot only when requested. */ @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerSnapshotFailed"); } }
    action def <'operation.vellis.rtg_list_persisted_snapshots'> RtgListPersistedSnapshots { out result : RtgPersistedSnapshotList[1]; doc /* List only persisted snapshot-like documents visible through the configured JSON storage root. */ @FailureContract { errorIds = ("RtgControllerSnapshotFailed"); } }
    action def <'operation.vellis.rtg_load_persisted_snapshot'> RtgLoadPersistedSnapshot { in relative_path : JsonRelativePath[1]; in return_snapshot : Boolean[0..1] default = true; out result : VellisLoadedSnapshotResult[1]; doc /* Load and validate one persisted snapshot, always return path and compact summary, and omit the full snapshot only when requested; do not apply it. */ @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerSnapshotFailed"); } }
    action def <'operation.vellis.rtg_replay_ledger'> RtgReplayLedger { in replay_options : RuntimeReconstructionRequest[0..1]; out result : RuntimeReconstructionReport[1]; doc /* Reconstruct managed component state through an optional runtime cursor, preparing targets by explicit reset or compatible checkpoints and applying committed canonical effects only. */ @FailureContract { errorIds = ("VellisRequestInvalid", "RuntimeReplayIncompatible", "RuntimeLedgerUnavailable", "RuntimeFailStopped"); } }
    action def <'operation.vellis.rtg_verify_replay_from_ledger'> RtgVerifyReplayFromLedger { in replay_options : RuntimeReconstructionRequest[0..1]; out result : VellisReplayVerificationResult[1]; doc /* Return available reconstruction verification for the requested runtime cursor without replacing current state; historical verification that lacks exact startup evidence requires an isolated data-root copy. */ @FailureContract { errorIds = ("VellisRequestInvalid", "RuntimeReplayIncompatible", "RuntimeLedgerUnavailable", "RuntimeFailStopped"); } }
    action def <'operation.vellis.rtg_list_migration_history'> RtgListMigrationHistory { out result : VellisMigrationHistory[1]; doc /* Query runtime facts and causal traces for migration staging, cutover, and abandonment requests and return them in terminal runtime-position order. */ @FailureContract { errorIds = ("RuntimeLedgerUnavailable", "RuntimeFailStopped"); } }
    action def <'operation.vellis.rtg_flush_ledger_failures'> RtgFlushLedgerFailures { out result : VellisDeprecatedLedgerFlushResult[1]; doc /* Deprecated health-only compatibility operation: report runtime health and zero queued degraded records without retrying, flushing, or mutating anything. */ @FailureContract { errorIds = ("RuntimeLedgerUnavailable"); } }
    action def <'operation.vellis.rtg_restore_from_snapshot'> RtgRestoreFromSnapshot { in 'snapshot' : RtgSystemSnapshot[1]; in restore_options : VellisRestoreOptions[0..1]; out result : RtgControllerOperationResult[1]; doc /* Validate and atomically restore coordinated RTG state. The restore request is always recorded as authoritative runtime traffic; optional restore_options can only affirm record mode. */ @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerSnapshotFailed", "RtgControllerRecoveryIndeterminate"); } }


    requirement <'contract.vellis.facade.failures'> facadeFailureSemantics {
        subject facade : VellisApplicationFacade;
        require constraint {
            doc /* Input decoding rejects unknown fields, wrong JSON kinds, invalid enum literals, missing required values, and contradictory option shapes as VellisRequestInvalid before controller or runtime invocation. Modeled Bibliotek failures propagate without changing their concrete type, message, diagnostic, or validation evidence. */
        }
    }

    requirement <'contract.vellis.facade.implementation_freedom'> facadeFreedom {
        subject facade : VellisApplicationFacade;
        require constraint {
            doc /* The facade may choose any implementation language or helper decomposition but must preserve the modeled request compilation, controller and runtime invocation, response shaping, defaults, ordering, and no-effect guarantees. */
        }
    }

    requirement <'contract.vellis.facade.usage_guides'> usageGuideSemantics {
        subject operation : RtgGetUsageGuide;
        require constraint {
            doc /* The fifteen guide topics cover: the installed Everyday Life schema; safe RTG schema design and evolution; compact machine-readable tool capabilities; MCP bootstrap sequence; concise operator rules; state-driven workflows; ordinary-request-to-workflow mapping; minimal schema staging; exact top-level tool shapes; live writes; identity lookup before links; query construction; snapshot transfer and runtime reconstruction; runtime trace history; and safe abandonment. Generic examples do not silently replace or specialize an application's modeled schema. */
        }
    }

    requirement <'contract.vellis.facade.schema_migration_compilation'> schemaMigrationCompilation {
        subject operation : RtgStageSchemaMigration;
        require constraint {
            doc /* Each unique kind-and-typeKey request becomes one newly identified non-live schema write and one schema_make_live member; duplicate request keys are rejected before controller invocation. generatedSchemaIds maps kind:type_key to that UUID. Each retirement selector must resolve to exactly one live definition and becomes schema_make_non_live. One ready migration with the supplied ID and description owns the membership. Compact response is default and full response adds the exact submitted batch; shaping has no mutation effect. */
        }
    }

    requirement <'contract.vellis.facade.anchor_record_compilation'> anchorRecordCompilation {
        subject facade : VellisApplicationFacade;
        require constraint {
            doc /* Each anchor record becomes one canonical anchor write. Each nested fact becomes one data-object write associated to that anchor; an omitted fact reference receives a unique request-local reference reported in generatedRefs. Link writes pass through unchanged. Validation and apply use identical compilation. Apply returns every resolved local-reference UUID; compact is default and full additionally returns the exact submitted graph changes. */
        }
    }

    requirement <'contract.vellis.facade.query_semantics'> queryFacadeSemantics {
        subject facade : VellisApplicationFacade;
        require constraint {
            doc /* Full query responses preserve the canonical query result. properties_only retains final row order, pagination metadata, and diagnostics while omitting bindings and unrequested records; non-aggregate rows contain row_index plus selected properties, while aggregate rows preserve row_index, group_by, and caller-named aggregation values. Anchor resolution compiles one live-only equality query and returns every deterministic match without guessing uniqueness. */
        }
    }

    requirement <'contract.vellis.facade.snapshot_semantics'> snapshotFacadeSemantics {
        subject facade : VellisApplicationFacade;
        require constraint {
            doc /* Full export returns the canonical coordinated RTG snapshot; summary export returns snapshot_exported and compact component counts. Persist and load always add compact summary and relative path, and return_snapshot=false removes only the full snapshot payload. Snapshot payloads contain no controller-ledger cursor or transaction identity, and response shaping changes no stored or current state. */
        }
    }

    requirement <'contract.vellis.facade.controller_forwarding'> controllerForwardingSemantics {
        subject facade : VellisApplicationFacade;
        require constraint {
            doc /* Controller-owned actions not identified as compilation or shaping workflows decode their modeled inputs, invoke exactly the satisfied controller capability once, and encode the modeled result without adding state, filtering, retries, ordering, or lifecycle policy. Runtime history, reconstruction, and health projections never route through the controller. */
        }
    }
    requirement <'contract.vellis.facade.runtime_projection'> runtimeProjectionSemantics {
        subject facade : VellisApplicationFacade;
        require constraint {
            doc /* System state augments the controller's domain summary with runtime identity, health, message count, cursor, and latest terminal trace. Replay delegates to runtime reconstruction with explicit cursor/reset/checkpoint semantics. Verification reports exact available evidence without in-place historical rewind. Migration history is a deterministic projection of runtime facts and causal traces. The deprecated flush operation reports health and zero queued degraded records without mutation. */
        }
    }
    part def <'application.vellis.facade'> VellisApplicationFacade {
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        ref part controller[1] : RtgController {
            perform rtgGetSystemState.invokeController;
            perform rtgStageSchemaMigration.invokeExportSystemSnapshot;
            perform rtgStageSchemaMigration.invokeStageKnowledgeChanges;
            perform rtgValidateLiveAnchorRecords.invokeController;
            perform rtgApplyLiveAnchorRecords.invokeController;
            perform rtgValidateLiveGraphChanges.invokeController;
            perform rtgApplyLiveGraphChanges.invokeController;
            perform rtgStageKnowledgeChanges.invokeController;
            perform rtgApplyMigrationCutover.invokeController;
            perform rtgAbandonMigration.invokeController;
            perform rtgExecuteQuery.invokeController;
            perform rtgResolveAnchorByFact.invokeController;
            perform rtgGetObject.invokeController;
            perform rtgListMigrations.invokeController;
            perform rtgGetMigration.invokeController;
            perform rtgValidateGraph.invokeController;
            perform rtgDiscoverAnchorTypes.invokeController;
            perform rtgGetSchemaPack.invokeController;
            perform rtgExportSystemSnapshot.invokeController;
            perform rtgPersistSystemSnapshot.invokeController;
            perform rtgListPersistedSnapshots.invokeController;
            perform rtgLoadPersistedSnapshot.invokeController;
            perform rtgRestoreFromSnapshot.invokeController;
        }
        ref part runtime[1] : MessageRuntime {
            perform rtgReplayLedger.invokeRuntime;
            perform rtgListMigrationHistory.queryRuntimeHistory;
        }
        perform action rtgGetSystemState[0..*] : RtgGetSystemState {
            action invokeController : GetSystemState {
                out result redefines GetSystemState::result;
            }
            action shapeSystemState {
                in attribute domainState = invokeController.result;
                in attribute runtimeId = runtime.runtimeId;
                in attribute runtimeKey = runtime.runtimeKey;
                in attribute runtimeHealth = runtime.health;
                in attribute runtimePosition = runtime.currentPosition;
                out attribute result = rtgGetSystemState.result;
                doc /* Add starter-schema posture and the trusted runtime status projection to the controller's domain state. */
            }
            first invokeController then shapeSystemState;
        }
        perform action rtgGetUsageGuide[0..*] : RtgGetUsageGuide { doc /* select one modeled guide topic and return static application guidance. */ }
        perform action rtgStageSchemaMigration[0..*] : RtgStageSchemaMigration {
            action invokeExportSystemSnapshot : ExportSystemSnapshot {
                out 'snapshot' redefines ExportSystemSnapshot::'snapshot';
            }
            action compileMigration {
                in attribute migrationId = rtgStageSchemaMigration.migration_id;
                in attribute description = rtgStageSchemaMigration.description;
                in attribute definitions = rtgStageSchemaMigration.schema_definitions;
                in attribute retirements = rtgStageSchemaMigration.retire_live_schema;
                in attribute currentState = invokeExportSystemSnapshot.'snapshot';
                out attribute knowledgeChanges : RtgChangeBatch;
                doc /* Resolve retirements and construct the modeled non-live candidates plus ready migration. */
            }
            action invokeStageKnowledgeChanges : StageKnowledgeChanges {
                in knowledgeChanges redefines StageKnowledgeChanges::knowledgeChanges = compileMigration.knowledgeChanges;
                in validationMode redefines StageKnowledgeChanges::validationMode = rtgStageSchemaMigration.validation_mode;
                out result redefines StageKnowledgeChanges::result;
            }
            action shapeResult {
                in attribute submittedChanges = compileMigration.knowledgeChanges;
                in attribute operation = invokeStageKnowledgeChanges.result;
                in attribute responseOptions = rtgStageSchemaMigration.response_options;
                out attribute result = rtgStageSchemaMigration.result;
                doc /* Return compact generated identities and controller evidence by default; include submitted canonical changes only when full response detail is requested. */
            }
            first invokeExportSystemSnapshot then compileMigration;
            first compileMigration then invokeStageKnowledgeChanges;
            first invokeStageKnowledgeChanges then shapeResult;
        }
        perform action rtgValidateLiveAnchorRecords[0..*] : RtgValidateLiveAnchorRecords {
            action compileRecords {
                in attribute records = rtgValidateLiveAnchorRecords.anchor_records;
                in attribute links = rtgValidateLiveAnchorRecords.link_writes;
                out attribute graphChanges : RtgGraphChangeSet;
                out attribute generatedRefs : VellisGeneratedReferences;
            }
            action invokeController : ValidateLiveGraphChanges {
                in graphChanges redefines ValidateLiveGraphChanges::graphChanges = compileRecords.graphChanges;
                in validationOptions redefines ValidateLiveGraphChanges::validationOptions = rtgValidateLiveAnchorRecords.validation_options;
                out result redefines ValidateLiveGraphChanges::result;
            }
            action shapeResult {
                in attribute graphChanges = compileRecords.graphChanges;
                in attribute generatedRefs = compileRecords.generatedRefs;
                in attribute validation = invokeController.result;
                out attribute result = rtgValidateLiveAnchorRecords.result;
            }
            first compileRecords then invokeController;
            first invokeController then shapeResult;
        }
        perform action rtgApplyLiveAnchorRecords[0..*] : RtgApplyLiveAnchorRecords {
            action compileRecords {
                in attribute records = rtgApplyLiveAnchorRecords.anchor_records;
                in attribute links = rtgApplyLiveAnchorRecords.link_writes;
                out attribute graphChanges : RtgGraphChangeSet;
                out attribute generatedRefs : VellisGeneratedReferences;
            }
            action invokeController : ApplyLiveGraphChanges {
                in graphChanges redefines ApplyLiveGraphChanges::graphChanges = compileRecords.graphChanges;
                in validationMode redefines ApplyLiveGraphChanges::validationMode = rtgApplyLiveAnchorRecords.validation_mode;
                out result redefines ApplyLiveGraphChanges::result;
            }
            action shapeResult {
                in attribute graphChanges = compileRecords.graphChanges;
                in attribute generatedRefs = compileRecords.generatedRefs;
                in attribute operation = invokeController.result;
                in attribute responseOptions = rtgApplyLiveAnchorRecords.response_options;
                out attribute result = rtgApplyLiveAnchorRecords.result;
            }
            first compileRecords then invokeController;
            first invokeController then shapeResult;
        }
        perform action rtgValidateLiveGraphChanges[0..*] : RtgValidateLiveGraphChanges {
            action invokeController : ValidateLiveGraphChanges {
                in graphChanges redefines ValidateLiveGraphChanges::graphChanges = rtgValidateLiveGraphChanges.graph_changes;
                in validationOptions redefines ValidateLiveGraphChanges::validationOptions = rtgValidateLiveGraphChanges.validation_options;
                out result redefines ValidateLiveGraphChanges::result = rtgValidateLiveGraphChanges.result;
            }
        }
        perform action rtgApplyLiveGraphChanges[0..*] : RtgApplyLiveGraphChanges {
            action invokeController : ApplyLiveGraphChanges {
                in graphChanges redefines ApplyLiveGraphChanges::graphChanges = rtgApplyLiveGraphChanges.graph_changes;
                in validationMode redefines ApplyLiveGraphChanges::validationMode = rtgApplyLiveGraphChanges.validation_mode;
                out result redefines ApplyLiveGraphChanges::result = rtgApplyLiveGraphChanges.result;
            }
        }
        perform action rtgStageKnowledgeChanges[0..*] : RtgStageKnowledgeChanges {
            action invokeController : StageKnowledgeChanges {
                in knowledgeChanges redefines StageKnowledgeChanges::knowledgeChanges = rtgStageKnowledgeChanges.knowledge_changes;
                in validationMode redefines StageKnowledgeChanges::validationMode = rtgStageKnowledgeChanges.validation_mode;
                out result redefines StageKnowledgeChanges::result = rtgStageKnowledgeChanges.result;
            }
        }
        perform action rtgApplyMigrationCutover[0..*] : RtgApplyMigrationCutover {
            action invokeController : ApplyMigrationCutover {
                in migrationId redefines ApplyMigrationCutover::migrationId = rtgApplyMigrationCutover.migration_id;
                in cutoverOptions redefines ApplyMigrationCutover::cutoverOptions = rtgApplyMigrationCutover.cutover_options;
                out result redefines ApplyMigrationCutover::result = rtgApplyMigrationCutover.result;
            }
        }
        perform action rtgAbandonMigration[0..*] : RtgAbandonMigration {
            action invokeController : AbandonMigration {
                in migrationId redefines AbandonMigration::migrationId = rtgAbandonMigration.migration_id;
                in reason redefines AbandonMigration::reason = rtgAbandonMigration.reason;
                out result redefines AbandonMigration::result = rtgAbandonMigration.result;
            }
        }
        perform action rtgExecuteQuery[0..*] : RtgExecuteQuery {
            action invokeController : ExecuteControllerQuery {
                in querySpec redefines ExecuteControllerQuery::querySpec = rtgExecuteQuery.query_spec;
                in queryOptions redefines ExecuteControllerQuery::queryOptions = rtgExecuteQuery.query_options;
                out result redefines ExecuteControllerQuery::result;
            }
            action shapeResponse {
                in attribute canonicalResult = invokeController.result;
                in attribute responseOptions = rtgExecuteQuery.response_options;
                out attribute result = rtgExecuteQuery.result;
            }
            first invokeController then shapeResponse;
        }
        perform action rtgResolveAnchorByFact[0..*] : RtgResolveAnchorByFact {
            action compileQuery {
                in attribute anchorType = rtgResolveAnchorByFact.anchor_type;
                in attribute dataType = rtgResolveAnchorByFact.data_type;
                in attribute propertyPath = rtgResolveAnchorByFact.property_path;
                in attribute value = rtgResolveAnchorByFact.value;
                in attribute caseSensitive = rtgResolveAnchorByFact.case_sensitive;
                out attribute querySpec : RtgQuerySpec;
                out attribute queryOptions : RtgQueryOptions;
            }
            action invokeController : ExecuteControllerQuery {
                in querySpec redefines ExecuteControllerQuery::querySpec = compileQuery.querySpec;
                in queryOptions redefines ExecuteControllerQuery::queryOptions = compileQuery.queryOptions;
                out result redefines ExecuteControllerQuery::result;
            }
            action shapeResolution {
                in attribute submittedQuery = compileQuery.querySpec;
                in attribute canonicalResult = invokeController.result;
                out attribute result = rtgResolveAnchorByFact.result;
            }
            first compileQuery then invokeController;
            first invokeController then shapeResolution;
        }
        perform action rtgGetObject[0..*] : RtgGetObject {
            action invokeController : ControllerGetObject {
                in objectUuid redefines ControllerGetObject::objectUuid = rtgGetObject.object_uuid;
                out object redefines ControllerGetObject::object = rtgGetObject.result;
            }
        }
        perform action rtgListMigrations[0..*] : RtgListMigrations {
            action invokeController : ControllerListMigrations {
                in status redefines ControllerListMigrations::status = rtgListMigrations.status;
                out result redefines ControllerListMigrations::result = rtgListMigrations.result;
            }
        }
        perform action rtgGetMigration[0..*] : RtgGetMigration {
            action invokeController : ControllerGetMigration {
                in migrationId redefines ControllerGetMigration::migrationId = rtgGetMigration.migration_id;
                out result redefines ControllerGetMigration::result = rtgGetMigration.result;
            }
        }
        perform action rtgValidateGraph[0..*] : RtgValidateGraph {
            action invokeController : ValidateGraph {
                in migrationIds redefines ValidateGraph::migrationIds = rtgValidateGraph.migration_ids.values;
                in validationOptions redefines ValidateGraph::validationOptions = rtgValidateGraph.validation_options;
                out report redefines ValidateGraph::report = rtgValidateGraph.result;
            }
        }
        perform action rtgDiscoverAnchorTypes[0..*] : RtgDiscoverAnchorTypes {
            action invokeController : DiscoverAnchorTypes {
                in discoveryOptions redefines DiscoverAnchorTypes::discoveryOptions = rtgDiscoverAnchorTypes.discovery_options;
                out result redefines DiscoverAnchorTypes::result = rtgDiscoverAnchorTypes.result;
            }
        }
        perform action rtgGetSchemaPack[0..*] : RtgGetSchemaPack {
            action invokeController : GetControllerSchemaPack {
                in anchorTypeKeys redefines GetControllerSchemaPack::anchorTypeKeys = rtgGetSchemaPack.anchor_type_keys.values;
                in schemaPackOptions redefines GetControllerSchemaPack::schemaPackOptions = rtgGetSchemaPack.schema_pack_options;
                out result redefines GetControllerSchemaPack::result = rtgGetSchemaPack.result;
            }
        }
        perform action rtgExportSystemSnapshot[0..*] : RtgExportSystemSnapshot {
            action invokeController : ExportSystemSnapshot {
                out 'snapshot' redefines ExportSystemSnapshot::'snapshot';
            }
            action shapeExport {
                in attribute 'snapshot' = invokeController.'snapshot';
                in attribute summaryOnly = rtgExportSystemSnapshot.summary;
                out attribute result = rtgExportSystemSnapshot.result;
            }
            first invokeController then shapeExport;
        }
        perform action rtgPersistSystemSnapshot[0..*] : RtgPersistSystemSnapshot {
            action invokeController : PersistSystemSnapshot {
                in relativePath redefines PersistSystemSnapshot::relativePath = rtgPersistSystemSnapshot.relative_path;
                out result redefines PersistSystemSnapshot::result;
            }
            action shapeResult {
                in attribute operation = invokeController.result;
                in attribute relativePath = rtgPersistSystemSnapshot.relative_path;
                in attribute returnSnapshot = rtgPersistSystemSnapshot.return_snapshot;
                out attribute result = rtgPersistSystemSnapshot.result;
            }
            first invokeController then shapeResult;
        }
        perform action rtgListPersistedSnapshots[0..*] : RtgListPersistedSnapshots {
            action invokeController : ListPersistedSnapshots {
                out result redefines ListPersistedSnapshots::result = rtgListPersistedSnapshots.result;
            }
        }
        perform action rtgLoadPersistedSnapshot[0..*] : RtgLoadPersistedSnapshot {
            action invokeController : LoadPersistedSnapshot {
                in relativePath redefines LoadPersistedSnapshot::relativePath = rtgLoadPersistedSnapshot.relative_path;
                out result redefines LoadPersistedSnapshot::result;
            }
            action shapeResult {
                in attribute document = invokeController.result;
                in attribute returnSnapshot = rtgLoadPersistedSnapshot.return_snapshot;
                out attribute result = rtgLoadPersistedSnapshot.result;
            }
            first invokeController then shapeResult;
        }
        perform action rtgReplayLedger[0..*] : RtgReplayLedger {
            action normalizeReconstructionRequest {
                in attribute options = rtgReplayLedger.replay_options;
                out attribute request : RuntimeReconstructionRequest;
                doc /* Omitted options become the default request with no cursor, no checkpoints, and resetTargets=false. */
            }
            action invokeRuntime : ReconstructRuntimeState {
                in request redefines ReconstructRuntimeState::request = normalizeReconstructionRequest.request;
                out report redefines ReconstructRuntimeState::report = rtgReplayLedger.result;
            }
            first normalizeReconstructionRequest then invokeRuntime;
        }
        perform action rtgVerifyReplayFromLedger[0..*] : RtgVerifyReplayFromLedger {
            action inspectReconstructionEvidence {
                in attribute request = rtgVerifyReplayFromLedger.replay_options;
                in attribute runtimeId = runtime.runtimeId;
                in attribute currentPosition = runtime.currentPosition;
                out attribute result = rtgVerifyReplayFromLedger.result;
                doc /* Compare the requested cursor with verified startup reconstruction evidence; require an isolated copy for any other historical cursor. */
            }
        }
        perform action rtgListMigrationHistory[0..*] : RtgListMigrationHistory {
            action buildRuntimeHistoryQuery {
                out attribute query : RuntimeHistoryQuery;
                doc /* Select controller request facts and traces for migration staging, cutover, and abandonment. */
            }
            action queryRuntimeHistory : QueryRuntimeHistory {
                in query redefines QueryRuntimeHistory::query = buildRuntimeHistoryQuery.query;
                out page redefines QueryRuntimeHistory::page;
            }
            action shapeMigrationHistory {
                in attribute historyPage = queryRuntimeHistory.page;
                out attribute result = rtgListMigrationHistory.result;
                doc /* Resolve complete causal traces, retain migration identifiers and arguments, and order events by terminal runtime position. */
            }
            first buildRuntimeHistoryQuery then queryRuntimeHistory;
            first queryRuntimeHistory then shapeMigrationHistory;
        }
        perform action rtgFlushLedgerFailures[0..*] : RtgFlushLedgerFailures {
            action shapeDeprecatedStatus {
                in attribute runtimeHealth = runtime.health;
                out attribute result = rtgFlushLedgerFailures.result;
                doc /* Report current runtime health, queued_degraded_records=0, deprecation, and the replacement runtime recovery surface. */
            }
        }
        perform action rtgRestoreFromSnapshot[0..*] : RtgRestoreFromSnapshot {
            action validateRestoreOptions {
                in attribute options = rtgRestoreFromSnapshot.restore_options;
                doc /* Accept omitted options or ledgerMode=record only. */
            }
            action invokeController : RestoreFromSnapshot {
                in 'snapshot' redefines RestoreFromSnapshot::'snapshot' = rtgRestoreFromSnapshot.'snapshot';
                out result redefines RestoreFromSnapshot::result = rtgRestoreFromSnapshot.result;
            }
            first validateRestoreOptions then invokeController;
        }

        dependency stateRuntimeMetadata from rtgGetSystemState to runtime { doc /* Read runtime identity, health, current position, message count, and latest terminal trace without changing history. */ }
        dependency verifyRuntimeEvidence from rtgVerifyReplayFromLedger to runtime { doc /* Read trusted reconstruction evidence without changing live component state or canonical history. */ }
        dependency flushRuntimeHealth from rtgFlushLedgerFailures to runtime { doc /* Read fail-stop health only; no queued controller-ledger records exist. */ }




























    }

    requirement <'contract.vellis.facade.rtg_get_system_state.failures'> rtgGetSystemStateFailureSemantics {
        subject operation : RtgGetSystemState;
        require constraint {
            doc /* Failure is encoded without changing controller or application state. */
        }
    }

    requirement <'contract.vellis.facade.rtg_get_usage_guide.failures'> rtgGetUsageGuideFailureSemantics {
        subject operation : RtgGetUsageGuide;
        require constraint {
            doc /* Unknown topics return a typed input failure and have no effect. */
        }
    }

    requirement <'contract.vellis.facade.rtg_stage_schema_migration.failures'> rtgStageSchemaMigrationFailureSemantics {
        subject operation : RtgStageSchemaMigration;
        require constraint {
            doc /* Invalid shaping or retirement selection has no staging effect; downstream controller atomicity applies after submission. */
        }
    }

    requirement <'contract.vellis.facade.rtg_validate_live_anchor_records.failures'> rtgValidateLiveAnchorRecordsFailureSemantics {
        subject operation : RtgValidateLiveAnchorRecords;
        require constraint {
            doc /* Compilation or validation failure has no domain-component effect; the runtime may retain the rejected or faulted trace. */
        }
    }

    requirement <'contract.vellis.facade.rtg_apply_live_anchor_records.failures'> rtgApplyLiveAnchorRecordsFailureSemantics {
        subject operation : RtgApplyLiveAnchorRecords;
        require constraint {
            doc /* Compilation failure has no effect; controller atomicity governs submitted mutations. */
        }
    }

    requirement <'contract.vellis.facade.rtg_validate_live_graph_changes.failures'> rtgValidateLiveGraphChangesFailureSemantics {
        subject operation : RtgValidateLiveGraphChanges;
        require constraint {
            doc /* The dry-run never mutates domain-component state; runtime traffic recording remains authoritative. */
        }
    }

    requirement <'contract.vellis.facade.rtg_apply_live_graph_changes.failures'> rtgApplyLiveGraphChangesFailureSemantics {
        subject operation : RtgApplyLiveGraphChanges;
        require constraint {
            doc /* The facade adds no mutation outside the controller lane. */
        }
    }

    requirement <'contract.vellis.facade.rtg_stage_knowledge_changes.failures'> rtgStageKnowledgeChangesFailureSemantics {
        subject operation : RtgStageKnowledgeChanges;
        require constraint {
            doc /* The facade preserves controller validation and rollback behavior. */
        }
    }

    requirement <'contract.vellis.facade.rtg_apply_migration_cutover.failures'> rtgApplyMigrationCutoverFailureSemantics {
        subject operation : RtgApplyMigrationCutover;
        require constraint {
            doc /* The facade does not weaken cutover restoration, rollback, or runtime trace-disposition semantics. If restoration cannot be confirmed, RtgControllerRecoveryIndeterminate propagates and the runtime records an indeterminate trace before gating further traffic. */
        }
    }

    requirement <'contract.vellis.facade.rtg_abandon_migration.failures'> rtgAbandonMigrationFailureSemantics {
        subject operation : RtgAbandonMigration;
        require constraint {
            doc /* Failure preserves controller abandonment guarantees. */
        }
    }

    requirement <'contract.vellis.facade.rtg_execute_query.failures'> rtgExecuteQueryFailureSemantics {
        subject operation : RtgExecuteQuery;
        require constraint {
            doc /* Query and shaping failures have no domain-component effect; the runtime records the resulting fault trace. */
        }
    }

    requirement <'contract.vellis.facade.rtg_resolve_anchor_by_fact.failures'> rtgResolveAnchorByFactFailureSemantics {
        subject operation : RtgResolveAnchorByFact;
        require constraint {
            doc /* Resolution is read-only and never guesses an identity. */
        }
    }

    requirement <'contract.vellis.facade.rtg_get_object.failures'> rtgGetObjectFailureSemantics {
        subject operation : RtgGetObject;
        require constraint {
            doc /* Failure has no domain-component effect; the runtime records the resulting fault trace. */
        }
    }

    requirement <'contract.vellis.facade.rtg_list_migrations.failures'> rtgListMigrationsFailureSemantics {
        subject operation : RtgListMigrations;
        require constraint {
            doc /* Failure has no domain-component effect; the runtime records the resulting fault trace. */
        }
    }

    requirement <'contract.vellis.facade.rtg_get_migration.failures'> rtgGetMigrationFailureSemantics {
        subject operation : RtgGetMigration;
        require constraint {
            doc /* Failure has no domain-component effect; the runtime records the resulting fault trace. */
        }
    }

    requirement <'contract.vellis.facade.rtg_validate_graph.failures'> rtgValidateGraphFailureSemantics {
        subject operation : RtgValidateGraph;
        require constraint {
            doc /* Blocking findings are returned in a report; only unusable input or execution raises, and no state changes. */
        }
    }

    requirement <'contract.vellis.facade.rtg_discover_anchor_types.failures'> rtgDiscoverAnchorTypesFailureSemantics {
        subject operation : RtgDiscoverAnchorTypes;
        require constraint {
            doc /* Discovery is read-only. */
        }
    }

    requirement <'contract.vellis.facade.rtg_get_schema_pack.failures'> rtgGetSchemaPackFailureSemantics {
        subject operation : RtgGetSchemaPack;
        require constraint {
            doc /* Schema-pack reads have no effect. */
        }
    }

    requirement <'contract.vellis.facade.rtg_export_system_snapshot.failures'> rtgExportSystemSnapshotFailureSemantics {
        subject operation : RtgExportSystemSnapshot;
        require constraint {
            doc /* Export has no domain-component effect; normal runtime request and response facts remain recorded. */
        }
    }

    requirement <'contract.vellis.facade.rtg_persist_system_snapshot.failures'> rtgPersistSystemSnapshotFailureSemantics {
        subject operation : RtgPersistSystemSnapshot;
        require constraint {
            doc /* Failure exposes no partial JSON document. */
        }
    }

    requirement <'contract.vellis.facade.rtg_list_persisted_snapshots.failures'> rtgListPersistedSnapshotsFailureSemantics {
        subject operation : RtgListPersistedSnapshots;
        require constraint {
            doc /* Listing is read-only. */
        }
    }

    requirement <'contract.vellis.facade.rtg_load_persisted_snapshot.failures'> rtgLoadPersistedSnapshotFailureSemantics {
        subject operation : RtgLoadPersistedSnapshot;
        require constraint {
            doc /* Loading has no current-state effect. */
        }
    }

    requirement <'contract.vellis.facade.rtg_replay_ledger.failures'> rtgReplayLedgerFailureSemantics {
        subject operation : RtgReplayLedger;
        require constraint {
            doc /* Rejected replay inputs expose no partial reconstructed state. */
        }
    }

    requirement <'contract.vellis.facade.rtg_verify_replay_from_ledger.failures'> rtgVerifyReplayFromLedgerFailureSemantics {
        subject operation : RtgVerifyReplayFromLedger;
        require constraint {
            doc /* Verification leaves current component state and canonical runtime history unchanged. */
        }
    }

    requirement <'contract.vellis.facade.rtg_list_migration_history.failures'> rtgListMigrationHistoryFailureSemantics {
        subject operation : RtgListMigrationHistory;
        require constraint {
            doc /* History inspection is read-only. */
        }
    }

    requirement <'contract.vellis.facade.rtg_flush_ledger_failures.failures'> rtgFlushLedgerFailuresFailureSemantics {
        subject operation : RtgFlushLedgerFailures;
        require constraint {
            doc /* The deprecated operation never mutates runtime or component state and always reports zero queued degraded controller-ledger records. */
        }
    }

    requirement <'contract.vellis.facade.rtg_restore_from_snapshot.failures'> rtgRestoreFromSnapshotFailureSemantics {
        subject operation : RtgRestoreFromSnapshot;
        require constraint {
            doc /* Ordinary failure restores the prior coordinated state. If restoration cannot be confirmed, RtgControllerRecoveryIndeterminate explicitly reports the uncertainty and the runtime records an indeterminate trace before gating further traffic. */
        }
    }

    part contractContext {
        part facade : VellisApplicationFacade;
        satisfy facadeFailureSemantics by facade;
        satisfy facadeFreedom by facade;
        satisfy anchorRecordCompilation by facade;
        satisfy queryFacadeSemantics by facade;
        satisfy snapshotFacadeSemantics by facade;
        satisfy controllerForwardingSemantics by facade;
        satisfy runtimeProjectionSemantics by facade;
        satisfy usageGuideSemantics by facade.rtgGetUsageGuide;
        satisfy schemaMigrationCompilation by facade.rtgStageSchemaMigration;

        satisfy rtgGetSystemStateFailureSemantics by facade.rtgGetSystemState;
        satisfy rtgGetUsageGuideFailureSemantics by facade.rtgGetUsageGuide;
        satisfy rtgStageSchemaMigrationFailureSemantics by facade.rtgStageSchemaMigration;
        satisfy rtgValidateLiveAnchorRecordsFailureSemantics by facade.rtgValidateLiveAnchorRecords;
        satisfy rtgApplyLiveAnchorRecordsFailureSemantics by facade.rtgApplyLiveAnchorRecords;
        satisfy rtgValidateLiveGraphChangesFailureSemantics by facade.rtgValidateLiveGraphChanges;
        satisfy rtgApplyLiveGraphChangesFailureSemantics by facade.rtgApplyLiveGraphChanges;
        satisfy rtgStageKnowledgeChangesFailureSemantics by facade.rtgStageKnowledgeChanges;
        satisfy rtgApplyMigrationCutoverFailureSemantics by facade.rtgApplyMigrationCutover;
        satisfy rtgAbandonMigrationFailureSemantics by facade.rtgAbandonMigration;
        satisfy rtgExecuteQueryFailureSemantics by facade.rtgExecuteQuery;
        satisfy rtgResolveAnchorByFactFailureSemantics by facade.rtgResolveAnchorByFact;
        satisfy rtgGetObjectFailureSemantics by facade.rtgGetObject;
        satisfy rtgListMigrationsFailureSemantics by facade.rtgListMigrations;
        satisfy rtgGetMigrationFailureSemantics by facade.rtgGetMigration;
        satisfy rtgValidateGraphFailureSemantics by facade.rtgValidateGraph;
        satisfy rtgDiscoverAnchorTypesFailureSemantics by facade.rtgDiscoverAnchorTypes;
        satisfy rtgGetSchemaPackFailureSemantics by facade.rtgGetSchemaPack;
        satisfy rtgExportSystemSnapshotFailureSemantics by facade.rtgExportSystemSnapshot;
        satisfy rtgPersistSystemSnapshotFailureSemantics by facade.rtgPersistSystemSnapshot;
        satisfy rtgListPersistedSnapshotsFailureSemantics by facade.rtgListPersistedSnapshots;
        satisfy rtgLoadPersistedSnapshotFailureSemantics by facade.rtgLoadPersistedSnapshot;
        satisfy rtgReplayLedgerFailureSemantics by facade.rtgReplayLedger;
        satisfy rtgVerifyReplayFromLedgerFailureSemantics by facade.rtgVerifyReplayFromLedger;
        satisfy rtgListMigrationHistoryFailureSemantics by facade.rtgListMigrationHistory;
        satisfy rtgFlushLedgerFailuresFailureSemantics by facade.rtgFlushLedgerFailures;
        satisfy rtgRestoreFromSnapshotFailureSemantics by facade.rtgRestoreFromSnapshot;
    }

    verification def RtgGetUsageGuideContractVerification {
        subject operation : RtgGetUsageGuide;
        objective {
            verify usageGuideSemantics;

            verify rtgGetUsageGuideFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgGetUsageGuideContractVerification";
            implementationScope = "VellisApplicationFacade";
        }
    }

    verification def RtgStageSchemaMigrationContractVerification {
        subject operation : RtgStageSchemaMigration;
        objective {
            verify schemaMigrationCompilation;

            verify rtgStageSchemaMigrationFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgStageSchemaMigrationContractVerification";
            implementationScope = "VellisApplicationFacade";
        }
    }
    verification def RtgGetSystemStateContractVerification {
        subject operation : RtgGetSystemState;
        objective { verify rtgGetSystemStateFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgGetSystemStateContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgValidateLiveAnchorRecordsContractVerification {
        subject operation : RtgValidateLiveAnchorRecords;
        objective { verify rtgValidateLiveAnchorRecordsFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgValidateLiveAnchorRecordsContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgApplyLiveAnchorRecordsContractVerification {
        subject operation : RtgApplyLiveAnchorRecords;
        objective { verify rtgApplyLiveAnchorRecordsFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgApplyLiveAnchorRecordsContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgValidateLiveGraphChangesContractVerification {
        subject operation : RtgValidateLiveGraphChanges;
        objective { verify rtgValidateLiveGraphChangesFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgValidateLiveGraphChangesContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgApplyLiveGraphChangesContractVerification {
        subject operation : RtgApplyLiveGraphChanges;
        objective { verify rtgApplyLiveGraphChangesFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgApplyLiveGraphChangesContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgStageKnowledgeChangesContractVerification {
        subject operation : RtgStageKnowledgeChanges;
        objective { verify rtgStageKnowledgeChangesFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgStageKnowledgeChangesContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgApplyMigrationCutoverContractVerification {
        subject operation : RtgApplyMigrationCutover;
        objective { verify rtgApplyMigrationCutoverFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgApplyMigrationCutoverContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgAbandonMigrationContractVerification {
        subject operation : RtgAbandonMigration;
        objective { verify rtgAbandonMigrationFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgAbandonMigrationContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgExecuteQueryContractVerification {
        subject operation : RtgExecuteQuery;
        objective { verify rtgExecuteQueryFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgExecuteQueryContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgResolveAnchorByFactContractVerification {
        subject operation : RtgResolveAnchorByFact;
        objective { verify rtgResolveAnchorByFactFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgResolveAnchorByFactContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgGetObjectContractVerification {
        subject operation : RtgGetObject;
        objective { verify rtgGetObjectFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgGetObjectContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgListMigrationsContractVerification {
        subject operation : RtgListMigrations;
        objective { verify rtgListMigrationsFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgListMigrationsContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgGetMigrationContractVerification {
        subject operation : RtgGetMigration;
        objective { verify rtgGetMigrationFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgGetMigrationContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgValidateGraphContractVerification {
        subject operation : RtgValidateGraph;
        objective { verify rtgValidateGraphFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgValidateGraphContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgDiscoverAnchorTypesContractVerification {
        subject operation : RtgDiscoverAnchorTypes;
        objective { verify rtgDiscoverAnchorTypesFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgDiscoverAnchorTypesContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgGetSchemaPackContractVerification {
        subject operation : RtgGetSchemaPack;
        objective { verify rtgGetSchemaPackFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgGetSchemaPackContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgExportSystemSnapshotContractVerification {
        subject operation : RtgExportSystemSnapshot;
        objective { verify rtgExportSystemSnapshotFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgExportSystemSnapshotContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgPersistSystemSnapshotContractVerification {
        subject operation : RtgPersistSystemSnapshot;
        objective { verify rtgPersistSystemSnapshotFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgPersistSystemSnapshotContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgListPersistedSnapshotsContractVerification {
        subject operation : RtgListPersistedSnapshots;
        objective { verify rtgListPersistedSnapshotsFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgListPersistedSnapshotsContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgLoadPersistedSnapshotContractVerification {
        subject operation : RtgLoadPersistedSnapshot;
        objective { verify rtgLoadPersistedSnapshotFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgLoadPersistedSnapshotContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgReplayLedgerContractVerification {
        subject operation : RtgReplayLedger;
        objective { verify rtgReplayLedgerFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgReplayLedgerContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgVerifyReplayFromLedgerContractVerification {
        subject operation : RtgVerifyReplayFromLedger;
        objective { verify rtgVerifyReplayFromLedgerFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgVerifyReplayFromLedgerContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgListMigrationHistoryContractVerification {
        subject operation : RtgListMigrationHistory;
        objective { verify rtgListMigrationHistoryFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgListMigrationHistoryContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgFlushLedgerFailuresContractVerification {
        subject operation : RtgFlushLedgerFailures;
        objective { verify rtgFlushLedgerFailuresFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgFlushLedgerFailuresContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }

    verification def RtgRestoreFromSnapshotContractVerification {
        subject operation : RtgRestoreFromSnapshot;
        objective { verify rtgRestoreFromSnapshotFailureSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgRestoreFromSnapshotContractVerification"; implementationScope = "VellisApplicationFacade"; }
    }



    verification def VellisFacadeBoundaryVerification {
        subject facade : VellisApplicationFacade;
        objective { verify facadeFailureSemantics; verify facadeFreedom; verify anchorRecordCompilation; verify queryFacadeSemantics; verify snapshotFacadeSemantics; verify controllerForwardingSemantics; verify runtimeProjectionSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#VellisFacadeBoundaryVerification"; implementationScope = "VellisApplicationFacade"; }
    }
}
