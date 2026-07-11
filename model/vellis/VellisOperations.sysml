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

    enum def VellisUsageGuideTopic {
        enum mcpBootstrapChecklist; enum operatorCard; enum workflowPatterns;
        enum requestPatterns; enum schemaStagingMinimal; enum toolCallShapes;
        enum liveWrite; enum lookupExamples; enum queryExamples;
        enum recoveryAndReplay; enum migrationHistory; enum migrationAbandonment;
    }
    enum def VellisQueryResponseFormat {
        enum full;
        enum properties_only;
    }
    enum def VellisQueryResponseKind {
        enum full;
        enum propertiesOnly;
    }
    enum def VellisResolutionStatus { enum resolved; }
    enum def VellisSnapshotSummaryStatus {
        enum snapshot_exported;
    }

    attribute def JsonObjectList { attribute values[0..*] : JsonObject; doc /* Encodes directly as a JSON array, not an object containing values. */ }
    attribute def StringList { attribute values[0..*] : String; doc /* Encodes directly as a JSON array, not an object containing values. */ }
    attribute def RtgGraphLinkWriteList { attribute values[0..*] : RtgGraphLinkWrite; doc /* Encodes directly as a JSON array of canonical link-write objects. */ }
    attribute def VellisUsageGuide { attribute topic : VellisUsageGuideTopic; attribute content : JsonObject; }
    attribute def VellisSchemaDefinitionRequest { attribute kind : RtgSchemaDefinitionKind; attribute typeKey : String; attribute description : String; attribute payload : RtgSchemaPayload; doc /* Description and typeKey are non-empty; payload family must match kind. */ }
    attribute def VellisSchemaDefinitionRequestList { attribute definitions[1..*] : VellisSchemaDefinitionRequest; doc /* Encodes directly as the schema_definitions JSON array. */ }
    attribute def VellisSchemaRetirement { attribute kind : RtgSchemaDefinitionKind; attribute typeKey : String; }
    attribute def VellisSchemaRetirementList { attribute definitions[0..*] : VellisSchemaRetirement; doc /* Encodes directly as the retire_live_schema JSON array. */ }
    attribute def VellisAnchorFact { attribute 'ref'[0..1] : RtgChangeReference; attribute type : String; attribute properties : JsonObject; attribute system : JsonObject; }
    attribute def VellisAnchorRecord { attribute 'ref' : RtgChangeReference; attribute type : String; attribute displayName[0..1] : String; attribute system : JsonObject; attribute facts[0..*] : VellisAnchorFact; }
    attribute def VellisAnchorRecordList { attribute records[1..*] : VellisAnchorRecord; doc /* Encodes directly as the anchor_records JSON array. */ }
    attribute def VellisGeneratedFactReference { attribute anchorIndex : Integer; attribute factIndex : Integer; attribute localRef : String; }
    attribute def VellisGeneratedReferences { attribute facts[0..*] : VellisGeneratedFactReference; }
    attribute def VellisSchemaMigrationResult { attribute generatedSchemaIds : JsonObject; attribute submittedKnowledgeChanges : RtgChangeBatch; attribute operation : RtgControllerOperationResult; }
    attribute def VellisAnchorValidationResult { attribute submittedGraphChanges : RtgGraphChangeSet; attribute generatedRefs : VellisGeneratedReferences; attribute validation : RtgControllerLiveGraphValidationResult; }
    attribute def VellisAnchorApplyResult { attribute submittedGraphChanges : RtgGraphChangeSet; attribute generatedRefs : VellisGeneratedReferences; attribute operation : RtgControllerOperationResult; }
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
    attribute def VellisQueryPropertiesResponse :> VellisQueryResponse { :>> kind = VellisQueryResponseKind::propertiesOnly; attribute status : String; attribute format : VellisQueryResponseFormat = VellisQueryResponseFormat::properties_only; attribute rowCount : Integer; attribute rows[0..*] : VellisQueryPropertiesRow; attribute diagnostics[0..*] : RtgQueryDiagnostic; doc /* Compact response retaining final row order, selected properties, and diagnostics; status is query_executed and format is properties_only. */ }
    attribute def VellisResolvedAnchor { attribute resourceId : Uuid; attribute properties : JsonObject; }
    attribute def VellisAnchorResolutionResult { attribute status : VellisResolutionStatus; attribute matchCount : Integer; attribute matches[0..*] : VellisResolvedAnchor; attribute submittedQuery : JsonObject; attribute diagnostics[0..*] : RtgQueryDiagnostic; attribute guidance[0..*] : String; }
    enum def VellisSnapshotExportKind { enum full; enum summary; }
    abstract attribute def VellisSnapshotExport { attribute kind : VellisSnapshotExportKind; doc /* Discriminated base for full and summary snapshot exports. */ }
    attribute def VellisFullSnapshotExport :> VellisSnapshotExport, RtgSystemSnapshot {
        :>> kind = VellisSnapshotExportKind::full;
        doc /* Full coordinated system snapshot. */
    }
    attribute def VellisSnapshotSummaryExport :> VellisSnapshotExport { :>> kind = VellisSnapshotExportKind::summary; attribute status : VellisSnapshotSummaryStatus; attribute summary : JsonObject; }
    attribute def VellisPersistedSnapshotResult { attribute status : RtgControllerOperationStatus; attribute transactionId : Uuid; attribute ledgerPosition[0..1] : Integer; attribute appliedChanges : RtgControllerAppliedChanges; attribute validationReport[0..1] : RtgValidationReport; attribute 'snapshot'[0..1] : RtgSystemSnapshot; attribute details : JsonObject; attribute relativePath : JsonRelativePath; attribute summary : JsonObject; doc /* Mirrors the controller result, adds relativePath and summary, and omits snapshot when return_snapshot is false. */ }
    attribute def VellisLoadedSnapshotResult { attribute relativePath : JsonRelativePath; attribute 'snapshot'[0..1] : RtgSystemSnapshot; attribute summary : JsonObject; doc /* snapshot is omitted when return_snapshot is false. */ }
    attribute def VellisRequestInvalid { attribute 'message' : String; attribute diagnostic : JsonObject; }

    action def <'operation.vellis.rtg_get_system_state'> RtgGetSystemState {
        out result : RtgControllerSystemState[1];
        doc /* Return state classification, counts, ledger pointers, and recommended next steps. */
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
        in validation_mode : RtgControllerValidationMode[0..1] default = RtgControllerValidationMode::strict; out result : VellisSchemaMigrationResult[1];
        doc /* Generate a UUID for each schema candidate, force each candidate non-live, resolve each retirement to exactly one live definition, create a ready migration whose membership covers those candidates, submit canonical staged knowledge changes, and return generated IDs, submitted changes, and the controller outcome. */
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerValidationFailed", "RtgControllerPreconditionFailed", "RtgControllerApplyFailed"); }
    }
    action def <'operation.vellis.rtg_validate_live_anchor_records'> RtgValidateLiveAnchorRecords {
        in anchor_records : VellisAnchorRecordList[1]; in link_writes : RtgGraphLinkWriteList[0..1];
        in validation_options : RtgControllerValidationOptions[0..1]; out result : VellisAnchorValidationResult[1];
        doc /* Compile each anchor and nested fact into canonical writes, generate deterministic request-local fact references where omitted, pass through canonical link writes, and return compiled changes plus validation without mutation or ledger writes. */
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerPreconditionFailed", "RtgValidationInputInvalid"); }
    }
    action def <'operation.vellis.rtg_apply_live_anchor_records'> RtgApplyLiveAnchorRecords {
        in anchor_records : VellisAnchorRecordList[1]; in link_writes : RtgGraphLinkWriteList[0..1];
        in validation_mode : RtgControllerValidationMode[0..1] default = RtgControllerValidationMode::strict; out result : VellisAnchorApplyResult[1];
        doc /* Compile anchor-with-facts input identically to the validation action, apply the canonical graph changes through the controller, and return compiled changes, generated fact references, and operation outcome. */
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerValidationFailed", "RtgControllerApplyFailed"); }
    }
    action def <'operation.vellis.rtg_validate_live_graph_changes'> RtgValidateLiveGraphChanges {
        in graph_changes : RtgGraphChangeSet[1]; in validation_options : RtgControllerValidationOptions[0..1];
        out result : RtgControllerLiveGraphValidationResult[1];
        doc /* Validate normal live graph CRUD without mutation or ledger writes. */
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
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerValidationFailed", "RtgControllerPreconditionFailed", "RtgControllerApplyFailed"); }
    }
    action def <'operation.vellis.rtg_abandon_migration'> RtgAbandonMigration {
        in migration_id : String[1]; in reason : String[0..1]; out result : RtgControllerOperationResult[1];
        doc /* Abandon safe non-live staged work without deleting live records. */
        @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerPreconditionFailed", "RtgControllerApplyFailed"); }
    }
    action def <'operation.vellis.rtg_execute_query'> RtgExecuteQuery {
        in query_spec : RtgQuerySpec[1]; in query_options : RtgQueryOptions[0..1];
        in response_options : VellisQueryResponseOptions[0..1]; out result : VellisQueryResponse[1];
        doc /* Execute the canonical read-only query. full returns RtgQueryResult unchanged; properties_only returns row_index plus requested properties, row count, and diagnostics, adding empty-return-property guidance when appropriate. */
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
    action def <'operation.vellis.rtg_export_system_snapshot'> RtgExportSystemSnapshot { in summary : Boolean[0..1] default = false; out result : VellisSnapshotExport[1]; doc /* Return the full coordinated snapshot when summary is false; otherwise return snapshot_exported plus compact component counts and ledger pointers. */ @FailureContract { errorIds = ("RtgControllerSnapshotFailed"); } }
    action def <'operation.vellis.rtg_persist_system_snapshot'> RtgPersistSystemSnapshot { in relative_path : JsonRelativePath[1]; in return_snapshot : Boolean[0..1] default = true; out result : VellisPersistedSnapshotResult[1]; doc /* Persist a coordinated snapshot, add relative path and compact summary to the controller result, and omit the full snapshot only when requested. */ @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerSnapshotFailed", "RtgControllerApplyFailed"); } }
    action def <'operation.vellis.rtg_list_persisted_snapshots'> RtgListPersistedSnapshots { out result : RtgPersistedSnapshotList[1]; doc /* List only persisted snapshot-like documents visible through the configured JSON storage root. */ @FailureContract { errorIds = ("RtgControllerSnapshotFailed"); } }
    action def <'operation.vellis.rtg_load_persisted_snapshot'> RtgLoadPersistedSnapshot { in relative_path : JsonRelativePath[1]; in return_snapshot : Boolean[0..1] default = true; out result : VellisLoadedSnapshotResult[1]; doc /* Load and validate one persisted snapshot, always return path and compact summary, and omit the full snapshot only when requested; do not apply it. */ @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerSnapshotFailed"); } }
    action def <'operation.vellis.rtg_replay_ledger'> RtgReplayLedger { in replay_options : RtgControllerReplayOptions[0..1]; out result : RtgControllerOperationResult[1]; doc /* Reconstruct state from an empty or explicit snapshot seed using the selected ascending ledger window. */ @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerReplayFailed"); } }
    action def <'operation.vellis.rtg_verify_replay_from_ledger'> RtgVerifyReplayFromLedger { in replay_options : RtgControllerReplayOptions[0..1]; out result : RtgControllerReplayVerificationResult[1]; doc /* Replay into isolated state and return summaries, count differences, replay window, and validation without replacing current state. */ @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerReplayFailed"); } }
    action def <'operation.vellis.rtg_list_migration_history'> RtgListMigrationHistory { out result : RtgControllerMigrationHistory[1]; doc /* Return ledger-backed staged, cutover-applied, cutover-failed, and abandoned events in ledger order. */ @FailureContract { errorIds = ("RtgControllerReplayFailed"); } }
    action def <'operation.vellis.rtg_flush_ledger_failures'> RtgFlushLedgerFailures { out result : RtgControllerOperationResult[1]; doc /* Retry queued audit records in original order and report remaining degraded-audit state. */ @FailureContract { errorIds = ("RtgControllerApplyFailed"); } }
    action def <'operation.vellis.rtg_restore_from_snapshot'> RtgRestoreFromSnapshot { in 'snapshot' : RtgSystemSnapshot[1]; in restore_options : RtgControllerRestoreOptions[0..1]; out result : RtgControllerOperationResult[1]; doc /* Validate and atomically restore coordinated state; record the operation by default and reserve skip for internal recovery. */ @FailureContract { errorIds = ("VellisRequestInvalid", "RtgControllerSnapshotFailed"); } }


    requirement <'contract.vellis.facade.failures'> facadeFailureSemantics {
        subject facade : VellisApplicationFacade;
        require constraint {
            doc /* Input decoding rejects unknown fields, wrong JSON kinds, invalid enum literals, missing required values, and contradictory option shapes as VellisRequestInvalid before controller invocation. Modeled Bibliotek failures propagate without changing their concrete type, message, diagnostic, transaction identity, or validation evidence. */
        }
    }

    requirement <'contract.vellis.facade.implementation_freedom'> facadeFreedom {
        subject facade : VellisApplicationFacade;
        require constraint {
            doc /* The facade may choose any implementation language or helper decomposition but must preserve the modeled request compilation, controller invocation, response shaping, defaults, ordering, and no-effect guarantees. */
        }
    }

    requirement <'contract.vellis.facade.usage_guides'> usageGuideSemantics {
        subject operation : RtgGetUsageGuide;
        require constraint {
            doc /* The twelve guide topics cover: MCP bootstrap sequence; concise operator rules; state-driven workflows; ordinary-request-to-workflow mapping; minimal schema staging; exact top-level tool shapes; live writes; identity lookup before links; query construction; snapshot/restore/replay recovery; durable migration history; and safe abandonment. Examples use complete generic envelopes and never invent application-domain schema. */
        }
    }

    requirement <'contract.vellis.facade.schema_migration_compilation'> schemaMigrationCompilation {
        subject operation : RtgStageSchemaMigration;
        require constraint {
            doc /* Each requested definition becomes one newly identified non-live schema write and one schema_make_live member. Each retirement selector must resolve to exactly one live definition and becomes schema_make_non_live. One ready migration with the supplied ID and description owns the membership; the returned submitted batch is exactly the batch passed to staging. */
        }
    }

    requirement <'contract.vellis.facade.anchor_record_compilation'> anchorRecordCompilation {
        subject facade : VellisApplicationFacade;
        require constraint {
            doc /* Each anchor record becomes one canonical anchor write. Each nested fact becomes one data-object write associated to that anchor; an omitted fact reference receives a unique request-local reference reported in generatedRefs. Link writes pass through unchanged. Validation and apply use the identical compilation. */
        }
    }

    requirement <'contract.vellis.facade.query_semantics'> queryFacadeSemantics {
        subject facade : VellisApplicationFacade;
        require constraint {
            doc /* Full query responses preserve the canonical query result. properties_only retains final row order, row_index, selected properties, and diagnostics while omitting bindings and unrequested records. Anchor resolution compiles one live-only equality query and returns every deterministic match without guessing uniqueness. */
        }
    }

    requirement <'contract.vellis.facade.snapshot_semantics'> snapshotFacadeSemantics {
        subject facade : VellisApplicationFacade;
        require constraint {
            doc /* Full export returns the canonical snapshot; summary export returns snapshot_exported and compact counts/pointers. Persist and load always add compact summary and relative path, and return_snapshot=false removes only the full snapshot payload. No response shaping changes stored or current state. */
        }
    }

    requirement <'contract.vellis.facade.controller_forwarding'> controllerForwardingSemantics {
        subject facade : VellisApplicationFacade;
        require constraint {
            doc /* Actions not identified as compilation or shaping workflows decode their modeled inputs, invoke exactly the satisfied controller capability once, and encode the modeled result without adding state, filtering, retries, ordering, or lifecycle policy. */
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
            perform rtgReplayLedger.invokeController;
            perform rtgVerifyReplayFromLedger.invokeController;
            perform rtgListMigrationHistory.invokeController;
            perform rtgFlushLedgerFailures.invokeController;
            perform rtgRestoreFromSnapshot.invokeController;
        }
        perform action rtgGetSystemState[0..*] : RtgGetSystemState {
            action invokeController : GetSystemState {
                out result redefines GetSystemState::result = rtgGetSystemState.result;
            }
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
                out attribute result = rtgStageSchemaMigration.result;
                doc /* Return generated identities, the submitted canonical changes, and the controller outcome. */
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
            action invokeController : ReplayLedger {
                in replayOptions redefines ReplayLedger::replayOptions = rtgReplayLedger.replay_options;
                out result redefines ReplayLedger::result = rtgReplayLedger.result;
            }
        }
        perform action rtgVerifyReplayFromLedger[0..*] : RtgVerifyReplayFromLedger {
            action invokeController : VerifyReplayFromLedger {
                in replayOptions redefines VerifyReplayFromLedger::replayOptions = rtgVerifyReplayFromLedger.replay_options;
                out result redefines VerifyReplayFromLedger::result = rtgVerifyReplayFromLedger.result;
            }
        }
        perform action rtgListMigrationHistory[0..*] : RtgListMigrationHistory {
            action invokeController : ListMigrationHistory {
                out result redefines ListMigrationHistory::result = rtgListMigrationHistory.result;
            }
        }
        perform action rtgFlushLedgerFailures[0..*] : RtgFlushLedgerFailures {
            action invokeController : FlushLedgerFailures {
                out result redefines FlushLedgerFailures::result = rtgFlushLedgerFailures.result;
            }
        }
        perform action rtgRestoreFromSnapshot[0..*] : RtgRestoreFromSnapshot {
            action invokeController : RestoreFromSnapshot {
                in 'snapshot' redefines RestoreFromSnapshot::'snapshot' = rtgRestoreFromSnapshot.'snapshot';
                in restoreOptions redefines RestoreFromSnapshot::restoreOptions = rtgRestoreFromSnapshot.restore_options;
                out result redefines RestoreFromSnapshot::result = rtgRestoreFromSnapshot.result;
            }
        }




























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
            doc /* Compilation or validation failure has no component or ledger effect. */
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
            doc /* The dry-run never mutates component or ledger state. */
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
            doc /* The facade does not weaken cutover restoration or ledger semantics. */
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
            doc /* Query and shaping failures have no state or ledger effect. */
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
            doc /* Failure has no state or ledger effect. */
        }
    }

    requirement <'contract.vellis.facade.rtg_list_migrations.failures'> rtgListMigrationsFailureSemantics {
        subject operation : RtgListMigrations;
        require constraint {
            doc /* Failure has no state or ledger effect. */
        }
    }

    requirement <'contract.vellis.facade.rtg_get_migration.failures'> rtgGetMigrationFailureSemantics {
        subject operation : RtgGetMigration;
        require constraint {
            doc /* Failure has no state or ledger effect. */
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
            doc /* Export has no state or ledger effect. */
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
            doc /* Verification leaves current state and source ledger unchanged. */
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
            doc /* Unflushed records remain queued and legible. */
        }
    }

    requirement <'contract.vellis.facade.rtg_restore_from_snapshot.failures'> rtgRestoreFromSnapshotFailureSemantics {
        subject operation : RtgRestoreFromSnapshot;
        require constraint {
            doc /* Failure exposes no partially restored state. */
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
        objective { verify facadeFailureSemantics; verify facadeFreedom; verify anchorRecordCompilation; verify queryFacadeSemantics; verify snapshotFacadeSemantics; verify controllerForwardingSemantics; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#VellisFacadeBoundaryVerification"; implementationScope = "VellisApplicationFacade"; }
    }
}
