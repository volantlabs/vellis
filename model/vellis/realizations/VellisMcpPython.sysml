package VellisMcpPythonRealization {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;
    private import BibliotekRtgChangeValidation::*;
    private import BibliotekRtgDiagnostics::*;
    private import VellisOperations::*;
    private import VellisLocalPythonRealization::*;

    enum def McpTransportKind {
        enum stdio;
        enum http;
    }

    enum def McpOperationalLane {
        enum state_and_discovery;
        enum live_graph;
        enum query;
        enum knowledge_engineering;
        enum migration;
        enum recovery_and_audit;
    }

    enum def McpAudienceKind { enum everyday; enum advanced; enum operator; }

    metadata def McpToolBinding {
        :>> annotatedElement : SysML::ActionUsage;
        attribute toolName : String;
        attribute implementationSymbol : String;
        attribute transport[1..*] : McpTransportKind;
        attribute lane : McpOperationalLane;
        attribute audience : McpAudienceKind;
        attribute ledgers : Boolean;
        attribute recommendedPredecessors[0..*] : String;
        attribute dryRunTool[0..1] : String;
        attribute readOnlyHint : Boolean;
        attribute destructiveHint : Boolean;
        attribute idempotentHint : Boolean;
        attribute openWorldHint : Boolean;
        doc /* Vellis MCP realization traceability, optional dry-run predecessor, and standard MCP behavioral hints. The annotated action usage documents a concise transport-facing description; detailed grammar lives in usage guides and shared typed contracts define result and failure encoding. */
    }

    attribute def VellisMcpError {
        attribute type : String;
        attribute 'message' : String;
        attribute diagnostic[0..1] : RtgDiagnostic;
        doc /* type is the concrete modeled failure name; diagnostic is present only when the source failure supplies structured corrective guidance. */
    }
    attribute def VellisMcpSuccess { attribute ok : Boolean = true; attribute result : JsonValue; }
    attribute def VellisMcpFailure {
        attribute ok : Boolean = false;
        attribute error : VellisMcpError;
        attribute transactionId[0..1] : Uuid;
        attribute validationReport[0..1] : RtgValidationReport;
    }

    attribute def VellisMcpOutcome {
        attribute success[0..1] : VellisMcpSuccess;
        attribute failure[0..1] : VellisMcpFailure;
        doc /* Exactly one of success or failure is present for each completed tool invocation. */
    }

    constraint def VellisMcpOutcomeExclusive {
        in outcome : VellisMcpOutcome;
        (outcome.success != null and outcome.failure == null) or
        (outcome.success == null and outcome.failure != null)
    }

    item def McpToolInvocation {
        attribute toolName : String;
        attribute arguments : JsonObject;
    }

    item def McpToolResponse {
        attribute toolName : String;
        attribute outcome : VellisMcpOutcome;
    }

    port def McpEndpoint {
        in item invocation[0..*] : McpToolInvocation;
        out item response[0..*] : McpToolResponse;
    }

    interface def McpToolExchange {
        end clientEndpoint : ~McpEndpoint;
        end adapterEndpoint : McpEndpoint;
        flow clientEndpoint.invocation to adapterEndpoint.invocation;
        flow adapterEndpoint.response to clientEndpoint.response;
    }

    part def McpClient {
        port endpoint : ~McpEndpoint;
    }

    part def <'adapter.vellis.mcp'> VellisMcpAdapter {
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "apps/rtg_knowledge_graph"; symbol = "apps.rtg_knowledge_graph.mcp_server.build_mcp_server"; realization = "FastMCP"; }
        ref part facade[1] : VellisApplicationFacade {
            perform getSystemState.invokeFacade;
            perform getUsageGuide.invokeFacade;
            perform stageSchemaMigration.invokeFacade;
            perform validateLiveAnchorRecords.invokeFacade;
            perform applyLiveAnchorRecords.invokeFacade;
            perform validateLiveGraphChanges.invokeFacade;
            perform applyLiveGraphChanges.invokeFacade;
            perform stageKnowledgeChanges.invokeFacade;
            perform applyMigrationCutover.invokeFacade;
            perform abandonMigration.invokeFacade;
            perform executeQuery.invokeFacade;
            perform resolveAnchorByFact.invokeFacade;
            perform getObject.invokeFacade;
            perform listMigrations.invokeFacade;
            perform getMigration.invokeFacade;
            perform validateGraph.invokeFacade;
            perform discoverAnchorTypes.invokeFacade;
            perform getSchemaPack.invokeFacade;
            perform exportSystemSnapshot.invokeFacade;
            perform persistSystemSnapshot.invokeFacade;
            perform listPersistedSnapshots.invokeFacade;
            perform loadPersistedSnapshot.invokeFacade;
            perform replayLedger.invokeFacade;
            perform verifyReplay.invokeFacade;
            perform listMigrationHistory.invokeFacade;
            perform flushLedgerFailures.invokeFacade;
            perform restoreFromSnapshot.invokeFacade;
        }
        port endpoint : McpEndpoint;

        perform action getSystemState[0..*] : RtgGetSystemState { @McpToolBinding { toolName = "rtg_get_system_state"; implementationSymbol = "RtgMcpToolset.rtg_get_system_state"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::state_and_discovery; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Inspect RTG state and workflow guidance; Lane: state_and_discovery; call this before schema-dependent work. */
            action invokeFacade : RtgGetSystemState {
                out result redefines RtgGetSystemState::result = getSystemState.result;
            }
        }
        perform action getUsageGuide[0..*] : RtgGetUsageGuide { @McpToolBinding { toolName = "rtg_get_usage_guide"; implementationSymbol = "RtgMcpToolset.rtg_get_usage_guide"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::state_and_discovery; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Read detailed RTG request shapes and workflows; Lane: state_and_discovery; use topic capabilities for the tool map. */
            action invokeFacade : RtgGetUsageGuide {
                in topic redefines RtgGetUsageGuide::topic = getUsageGuide.topic;
                out result redefines RtgGetUsageGuide::result = getUsageGuide.result;
            }
        }
        perform action stageSchemaMigration[0..*] : RtgStageSchemaMigration { @McpToolBinding { toolName = "rtg_stage_schema_migration"; implementationSymbol = "RtgMcpToolset.rtg_stage_schema_migration"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::knowledge_engineering; audience = McpAudienceKind::advanced; ledgers = true; recommendedPredecessors = ("rtg_get_system_state", "rtg_get_schema_pack"); readOnlyHint = false; destructiveHint = true; idempotentHint = false; openWorldHint = false; }
            doc /* Stage an ergonomic schema migration; Lane: knowledge_engineering; inspect current schema and obtain approval first. */
            action invokeFacade : RtgStageSchemaMigration {
                in migration_id redefines RtgStageSchemaMigration::migration_id = stageSchemaMigration.migration_id;
                in description redefines RtgStageSchemaMigration::description = stageSchemaMigration.description;
                in schema_definitions redefines RtgStageSchemaMigration::schema_definitions = stageSchemaMigration.schema_definitions;
                in retire_live_schema redefines RtgStageSchemaMigration::retire_live_schema = stageSchemaMigration.retire_live_schema;
                in validation_mode redefines RtgStageSchemaMigration::validation_mode = stageSchemaMigration.validation_mode;
                in response_options redefines RtgStageSchemaMigration::response_options = stageSchemaMigration.response_options;
                out result redefines RtgStageSchemaMigration::result = stageSchemaMigration.result;
            }
        }
        perform action validateLiveAnchorRecords[0..*] : RtgValidateLiveAnchorRecords { @McpToolBinding { toolName = "rtg_validate_live_anchor_records"; implementationSymbol = "RtgMcpToolset.rtg_validate_live_anchor_records"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::live_graph; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Dry-run ergonomic anchor records without mutation or ledgering; Lane: live_graph. */
            action invokeFacade : RtgValidateLiveAnchorRecords {
                in anchor_records redefines RtgValidateLiveAnchorRecords::anchor_records = validateLiveAnchorRecords.anchor_records;
                in link_writes redefines RtgValidateLiveAnchorRecords::link_writes = validateLiveAnchorRecords.link_writes;
                in validation_options redefines RtgValidateLiveAnchorRecords::validation_options = validateLiveAnchorRecords.validation_options;
                out result redefines RtgValidateLiveAnchorRecords::result = validateLiveAnchorRecords.result;
            }
        }
        perform action applyLiveAnchorRecords[0..*] : RtgApplyLiveAnchorRecords { @McpToolBinding { toolName = "rtg_apply_live_anchor_records"; implementationSymbol = "RtgMcpToolset.rtg_apply_live_anchor_records"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::live_graph; audience = McpAudienceKind::everyday; ledgers = true; recommendedPredecessors = ("rtg_validate_live_anchor_records"); dryRunTool = "rtg_validate_live_anchor_records"; readOnlyHint = false; destructiveHint = true; idempotentHint = false; openWorldHint = false; }
            doc /* Apply ergonomic anchor records to live state; Lane: live_graph; discover schema first. */
            action invokeFacade : RtgApplyLiveAnchorRecords {
                in anchor_records redefines RtgApplyLiveAnchorRecords::anchor_records = applyLiveAnchorRecords.anchor_records;
                in link_writes redefines RtgApplyLiveAnchorRecords::link_writes = applyLiveAnchorRecords.link_writes;
                in validation_mode redefines RtgApplyLiveAnchorRecords::validation_mode = applyLiveAnchorRecords.validation_mode;
                in response_options redefines RtgApplyLiveAnchorRecords::response_options = applyLiveAnchorRecords.response_options;
                out result redefines RtgApplyLiveAnchorRecords::result = applyLiveAnchorRecords.result;
            }
        }
        perform action validateLiveGraphChanges[0..*] : RtgValidateLiveGraphChanges { @McpToolBinding { toolName = "rtg_validate_live_graph_changes"; implementationSymbol = "RtgMcpToolset.rtg_validate_live_graph_changes"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::live_graph; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Dry-run normalized live graph changes without mutation or ledgering; Lane: live_graph. */
            action invokeFacade : RtgValidateLiveGraphChanges {
                in graph_changes redefines RtgValidateLiveGraphChanges::graph_changes = validateLiveGraphChanges.graph_changes;
                in validation_options redefines RtgValidateLiveGraphChanges::validation_options = validateLiveGraphChanges.validation_options;
                out result redefines RtgValidateLiveGraphChanges::result = validateLiveGraphChanges.result;
            }
        }
        perform action applyLiveGraphChanges[0..*] : RtgApplyLiveGraphChanges { @McpToolBinding { toolName = "rtg_apply_live_graph_changes"; implementationSymbol = "RtgMcpToolset.rtg_apply_live_graph_changes"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::live_graph; audience = McpAudienceKind::everyday; ledgers = true; recommendedPredecessors = ("rtg_validate_live_graph_changes"); dryRunTool = "rtg_validate_live_graph_changes"; readOnlyHint = false; destructiveHint = true; idempotentHint = false; openWorldHint = false; }
            doc /* Apply normalized live graph changes; Lane: live_graph; use the validation predecessor for risky writes. */
            action invokeFacade : RtgApplyLiveGraphChanges {
                in graph_changes redefines RtgApplyLiveGraphChanges::graph_changes = applyLiveGraphChanges.graph_changes;
                in validation_mode redefines RtgApplyLiveGraphChanges::validation_mode = applyLiveGraphChanges.validation_mode;
                out result redefines RtgApplyLiveGraphChanges::result = applyLiveGraphChanges.result;
            }
        }
        perform action stageKnowledgeChanges[0..*] : RtgStageKnowledgeChanges { @McpToolBinding { toolName = "rtg_stage_knowledge_changes"; implementationSymbol = "RtgMcpToolset.rtg_stage_knowledge_changes"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::knowledge_engineering; audience = McpAudienceKind::advanced; ledgers = true; recommendedPredecessors = ("rtg_get_system_state", "rtg_validate_graph"); readOnlyHint = false; destructiveHint = true; idempotentHint = false; openWorldHint = false; }
            doc /* Stage an advanced normalized knowledge batch; Lane: knowledge_engineering; prefer ergonomic staging for ordinary schema work. */
            action invokeFacade : RtgStageKnowledgeChanges {
                in knowledge_changes redefines RtgStageKnowledgeChanges::knowledge_changes = stageKnowledgeChanges.knowledge_changes;
                in validation_mode redefines RtgStageKnowledgeChanges::validation_mode = stageKnowledgeChanges.validation_mode;
                out result redefines RtgStageKnowledgeChanges::result = stageKnowledgeChanges.result;
            }
        }
        perform action applyMigrationCutover[0..*] : RtgApplyMigrationCutover { @McpToolBinding { toolName = "rtg_apply_migration_cutover"; implementationSymbol = "RtgMcpToolset.rtg_apply_migration_cutover"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::migration; audience = McpAudienceKind::advanced; ledgers = true; recommendedPredecessors = ("rtg_get_migration", "rtg_validate_graph"); readOnlyHint = false; destructiveHint = true; idempotentHint = false; openWorldHint = false; }
            doc /* Apply a staged migration atomically; Lane: migration; validate the projected state first. */
            action invokeFacade : RtgApplyMigrationCutover {
                in migration_id redefines RtgApplyMigrationCutover::migration_id = applyMigrationCutover.migration_id;
                in cutover_options redefines RtgApplyMigrationCutover::cutover_options = applyMigrationCutover.cutover_options;
                out result redefines RtgApplyMigrationCutover::result = applyMigrationCutover.result;
            }
        }
        perform action abandonMigration[0..*] : RtgAbandonMigration { @McpToolBinding { toolName = "rtg_abandon_migration"; implementationSymbol = "RtgMcpToolset.rtg_abandon_migration"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::migration; audience = McpAudienceKind::advanced; ledgers = true; recommendedPredecessors = ("rtg_get_migration"); readOnlyHint = false; destructiveHint = true; idempotentHint = false; openWorldHint = false; }
            doc /* Abandon staged migration work and prune safe non-live candidates; Lane: migration. */
            action invokeFacade : RtgAbandonMigration {
                in migration_id redefines RtgAbandonMigration::migration_id = abandonMigration.migration_id;
                in reason redefines RtgAbandonMigration::reason = abandonMigration.reason;
                out result redefines RtgAbandonMigration::result = abandonMigration.result;
            }
        }
        perform action executeQuery[0..*] : RtgExecuteQuery { @McpToolBinding { toolName = "rtg_execute_query"; implementationSymbol = "RtgMcpToolset.rtg_execute_query"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::query; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Execute a read-only RTG query; Lane: query; detailed grammar and examples are in usage guides. */
            action invokeFacade : RtgExecuteQuery {
                in query_spec redefines RtgExecuteQuery::query_spec = executeQuery.query_spec;
                in query_options redefines RtgExecuteQuery::query_options = executeQuery.query_options;
                in response_options redefines RtgExecuteQuery::response_options = executeQuery.response_options;
                out result redefines RtgExecuteQuery::result = executeQuery.result;
            }
        }
        perform action resolveAnchorByFact[0..*] : RtgResolveAnchorByFact { @McpToolBinding { toolName = "rtg_resolve_anchor_by_fact"; implementationSymbol = "RtgMcpToolset.rtg_resolve_anchor_by_fact"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::query; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Resolve zero, one, or multiple live anchors by typed fact; Lane: query; never guess among multiple matches. */
            action invokeFacade : RtgResolveAnchorByFact {
                in anchor_type redefines RtgResolveAnchorByFact::anchor_type = resolveAnchorByFact.anchor_type;
                in data_type redefines RtgResolveAnchorByFact::data_type = resolveAnchorByFact.data_type;
                in property_path redefines RtgResolveAnchorByFact::property_path = resolveAnchorByFact.property_path;
                in value redefines RtgResolveAnchorByFact::value = resolveAnchorByFact.value;
                in case_sensitive redefines RtgResolveAnchorByFact::case_sensitive = resolveAnchorByFact.case_sensitive;
                out result redefines RtgResolveAnchorByFact::result = resolveAnchorByFact.result;
            }
        }
        perform action getObject[0..*] : RtgGetObject { @McpToolBinding { toolName = "rtg_get_object"; implementationSymbol = "RtgMcpToolset.rtg_get_object"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::state_and_discovery; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Read one RTG graph object by UUID; Lane: state_and_discovery. */
            action invokeFacade : RtgGetObject {
                in object_uuid redefines RtgGetObject::object_uuid = getObject.object_uuid;
                out result redefines RtgGetObject::result = getObject.result;
            }
        }
        perform action listMigrations[0..*] : RtgListMigrations { @McpToolBinding { toolName = "rtg_list_migrations"; implementationSymbol = "RtgMcpToolset.rtg_list_migrations"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::migration; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* List current migration-store records; Lane: migration; use history for pruned or rejected work. */
            action invokeFacade : RtgListMigrations {
                in status redefines RtgListMigrations::status = listMigrations.status;
                out result redefines RtgListMigrations::result = listMigrations.result;
            }
        }
        perform action getMigration[0..*] : RtgGetMigration { @McpToolBinding { toolName = "rtg_get_migration"; implementationSymbol = "RtgMcpToolset.rtg_get_migration"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::migration; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Read one current migration-store record by ID; Lane: migration. */
            action invokeFacade : RtgGetMigration {
                in migration_id redefines RtgGetMigration::migration_id = getMigration.migration_id;
                out result redefines RtgGetMigration::result = getMigration.result;
            }
        }
        perform action validateGraph[0..*] : RtgValidateGraph { @McpToolBinding { toolName = "rtg_validate_graph"; implementationSymbol = "RtgMcpToolset.rtg_validate_graph"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::live_graph; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Validate current or migration-projected RTG state without mutation; Lane: live_graph. */
            action invokeFacade : RtgValidateGraph {
                in migration_ids redefines RtgValidateGraph::migration_ids = validateGraph.migration_ids;
                in validation_options redefines RtgValidateGraph::validation_options = validateGraph.validation_options;
                out result redefines RtgValidateGraph::result = validateGraph.result;
            }
        }
        perform action discoverAnchorTypes[0..*] : RtgDiscoverAnchorTypes { @McpToolBinding { toolName = "rtg_discover_anchor_types"; implementationSymbol = "RtgMcpToolset.rtg_discover_anchor_types"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::state_and_discovery; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Discover anchor types and live counts; Lane: state_and_discovery; use before guessing type keys. */
            action invokeFacade : RtgDiscoverAnchorTypes {
                in discovery_options redefines RtgDiscoverAnchorTypes::discovery_options = discoverAnchorTypes.discovery_options;
                out result redefines RtgDiscoverAnchorTypes::result = discoverAnchorTypes.result;
            }
        }
        perform action getSchemaPack[0..*] : RtgGetSchemaPack { @McpToolBinding { toolName = "rtg_get_schema_pack"; implementationSymbol = "RtgMcpToolset.rtg_get_schema_pack"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::state_and_discovery; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Read schema details for selected anchor types; Lane: state_and_discovery; use before writes. */
            action invokeFacade : RtgGetSchemaPack {
                in anchor_type_keys redefines RtgGetSchemaPack::anchor_type_keys = getSchemaPack.anchor_type_keys;
                in schema_pack_options redefines RtgGetSchemaPack::schema_pack_options = getSchemaPack.schema_pack_options;
                out result redefines RtgGetSchemaPack::result = getSchemaPack.result;
            }
        }
        perform action exportSystemSnapshot[0..*] : RtgExportSystemSnapshot { @McpToolBinding { toolName = "rtg_export_system_snapshot"; implementationSymbol = "RtgMcpToolset.rtg_export_system_snapshot"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::recovery_and_audit; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Export current coordinated RTG state or a compact summary; Lane: recovery_and_audit. */
            action invokeFacade : RtgExportSystemSnapshot {
                in summary redefines RtgExportSystemSnapshot::summary = exportSystemSnapshot.summary;
                out result redefines RtgExportSystemSnapshot::result = exportSystemSnapshot.result;
            }
        }
        perform action persistSystemSnapshot[0..*] : RtgPersistSystemSnapshot { @McpToolBinding { toolName = "rtg_persist_system_snapshot"; implementationSymbol = "RtgMcpToolset.rtg_persist_system_snapshot"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::recovery_and_audit; audience = McpAudienceKind::everyday; ledgers = true; readOnlyHint = false; destructiveHint = true; idempotentHint = false; openWorldHint = false; }
            doc /* Persist a coordinated RTG snapshot; Lane: recovery_and_audit; this records an administrative ledger event. */
            action invokeFacade : RtgPersistSystemSnapshot {
                in relative_path redefines RtgPersistSystemSnapshot::relative_path = persistSystemSnapshot.relative_path;
                in return_snapshot redefines RtgPersistSystemSnapshot::return_snapshot = persistSystemSnapshot.return_snapshot;
                out result redefines RtgPersistSystemSnapshot::result = persistSystemSnapshot.result;
            }
        }
        perform action listPersistedSnapshots[0..*] : RtgListPersistedSnapshots { @McpToolBinding { toolName = "rtg_list_persisted_snapshots"; implementationSymbol = "RtgMcpToolset.rtg_list_persisted_snapshots"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::recovery_and_audit; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* List RTG snapshots visible through configured storage; Lane: recovery_and_audit. */
            action invokeFacade : RtgListPersistedSnapshots {
                out result redefines RtgListPersistedSnapshots::result = listPersistedSnapshots.result;
            }
        }
        perform action loadPersistedSnapshot[0..*] : RtgLoadPersistedSnapshot { @McpToolBinding { toolName = "rtg_load_persisted_snapshot"; implementationSymbol = "RtgMcpToolset.rtg_load_persisted_snapshot"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::recovery_and_audit; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Load one persisted RTG snapshot without restoring it; Lane: recovery_and_audit. */
            action invokeFacade : RtgLoadPersistedSnapshot {
                in relative_path redefines RtgLoadPersistedSnapshot::relative_path = loadPersistedSnapshot.relative_path;
                in return_snapshot redefines RtgLoadPersistedSnapshot::return_snapshot = loadPersistedSnapshot.return_snapshot;
                out result redefines RtgLoadPersistedSnapshot::result = loadPersistedSnapshot.result;
            }
        }
        perform action replayLedger[0..*] : RtgReplayLedger { @McpToolBinding { toolName = "rtg_replay_ledger"; implementationSymbol = "RtgMcpToolset.rtg_replay_ledger"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::recovery_and_audit; audience = McpAudienceKind::operator; ledgers = false; recommendedPredecessors = ("rtg_get_system_state"); readOnlyHint = false; destructiveHint = true; idempotentHint = false; openWorldHint = false; }
            doc /* Replay eligible mutations into empty or snapshot-seeded state; Lane: recovery_and_audit; operator use. */
            action invokeFacade : RtgReplayLedger {
                in replay_options redefines RtgReplayLedger::replay_options = replayLedger.replay_options;
                out result redefines RtgReplayLedger::result = replayLedger.result;
            }
        }
        perform action verifyReplay[0..*] : RtgVerifyReplayFromLedger { @McpToolBinding { toolName = "rtg_verify_replay_from_ledger"; implementationSymbol = "RtgMcpToolset.rtg_verify_replay_from_ledger"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::recovery_and_audit; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Verify replay in isolated scratch state and restore live state exactly; Lane: recovery_and_audit. */
            action invokeFacade : RtgVerifyReplayFromLedger {
                in replay_options redefines RtgVerifyReplayFromLedger::replay_options = verifyReplay.replay_options;
                out result redefines RtgVerifyReplayFromLedger::result = verifyReplay.result;
            }
        }
        perform action listMigrationHistory[0..*] : RtgListMigrationHistory { @McpToolBinding { toolName = "rtg_list_migration_history"; implementationSymbol = "RtgMcpToolset.rtg_list_migration_history"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::migration; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Read ledger-projected migration events, including rejected proposals; Lane: migration. */
            action invokeFacade : RtgListMigrationHistory {
                out result redefines RtgListMigrationHistory::result = listMigrationHistory.result;
            }
        }
        perform action flushLedgerFailures[0..*] : RtgFlushLedgerFailures { @McpToolBinding { toolName = "rtg_flush_ledger_failures"; implementationSymbol = "RtgMcpToolset.rtg_flush_ledger_failures"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::recovery_and_audit; audience = McpAudienceKind::operator; ledgers = false; recommendedPredecessors = ("rtg_get_system_state"); readOnlyHint = false; destructiveHint = true; idempotentHint = false; openWorldHint = false; }
            doc /* Retry queued controller ledger writes; Lane: recovery_and_audit; operator use. */
            action invokeFacade : RtgFlushLedgerFailures {
                out result redefines RtgFlushLedgerFailures::result = flushLedgerFailures.result;
            }
        }
        perform action restoreFromSnapshot[0..*] : RtgRestoreFromSnapshot { @McpToolBinding { toolName = "rtg_restore_from_snapshot"; implementationSymbol = "RtgMcpToolset.rtg_restore_from_snapshot"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::recovery_and_audit; audience = McpAudienceKind::operator; ledgers = true; recommendedPredecessors = ("rtg_load_persisted_snapshot"); readOnlyHint = false; destructiveHint = true; idempotentHint = false; openWorldHint = false; }
            doc /* Restore coordinated RTG state from a supplied snapshot; Lane: recovery_and_audit; operator use. */
            action invokeFacade : RtgRestoreFromSnapshot {
                in 'snapshot' redefines RtgRestoreFromSnapshot::'snapshot' = restoreFromSnapshot.'snapshot';
                in restore_options redefines RtgRestoreFromSnapshot::restore_options = restoreFromSnapshot.restore_options;
                out result redefines RtgRestoreFromSnapshot::result = restoreFromSnapshot.result;
            }
        }
    }

    part def VellisMcpPython {
        part application : VellisLocalPython;
        part adapter : VellisMcpAdapter;
        part client : McpClient;
        interface clientToAdapter : McpToolExchange
            connect client.endpoint to adapter.endpoint;
            bind adapter.facade = application.facade;
        allocate application.facade.rtgGetSystemState to adapter.getSystemState;
        allocate application.facade.rtgGetUsageGuide to adapter.getUsageGuide;
        allocate application.facade.rtgStageSchemaMigration to adapter.stageSchemaMigration;
        allocate application.facade.rtgValidateLiveAnchorRecords to adapter.validateLiveAnchorRecords;
        allocate application.facade.rtgApplyLiveAnchorRecords to adapter.applyLiveAnchorRecords;
        allocate application.facade.rtgValidateLiveGraphChanges to adapter.validateLiveGraphChanges;
        allocate application.facade.rtgApplyLiveGraphChanges to adapter.applyLiveGraphChanges;
        allocate application.facade.rtgStageKnowledgeChanges to adapter.stageKnowledgeChanges;
        allocate application.facade.rtgApplyMigrationCutover to adapter.applyMigrationCutover;
        allocate application.facade.rtgAbandonMigration to adapter.abandonMigration;
        allocate application.facade.rtgExecuteQuery to adapter.executeQuery;
        allocate application.facade.rtgResolveAnchorByFact to adapter.resolveAnchorByFact;
        allocate application.facade.rtgGetObject to adapter.getObject;
        allocate application.facade.rtgListMigrations to adapter.listMigrations;
        allocate application.facade.rtgGetMigration to adapter.getMigration;
        allocate application.facade.rtgValidateGraph to adapter.validateGraph;
        allocate application.facade.rtgDiscoverAnchorTypes to adapter.discoverAnchorTypes;
        allocate application.facade.rtgGetSchemaPack to adapter.getSchemaPack;
        allocate application.facade.rtgExportSystemSnapshot to adapter.exportSystemSnapshot;
        allocate application.facade.rtgPersistSystemSnapshot to adapter.persistSystemSnapshot;
        allocate application.facade.rtgListPersistedSnapshots to adapter.listPersistedSnapshots;
        allocate application.facade.rtgLoadPersistedSnapshot to adapter.loadPersistedSnapshot;
        allocate application.facade.rtgReplayLedger to adapter.replayLedger;
        allocate application.facade.rtgVerifyReplayFromLedger to adapter.verifyReplay;
        allocate application.facade.rtgListMigrationHistory to adapter.listMigrationHistory;
        allocate application.facade.rtgFlushLedgerFailures to adapter.flushLedgerFailures;
        allocate application.facade.rtgRestoreFromSnapshot to adapter.restoreFromSnapshot;
    }


    requirement <'contract.vellis.mcp.outcome_exclusive'> mcpOutcomeExclusive {
        subject outcome : VellisMcpOutcome;
        require constraint exclusive : VellisMcpOutcomeExclusive {
            in outcome = mcpOutcomeExclusive.outcome;
        }
    }

    requirement <'contract.vellis.mcp.description_authority'> mcpDescriptionAuthority {
        subject adapter : VellisMcpAdapter;
        require constraint {
            doc /* Each MCP-bound adapter action documents one concise purpose/lane/safety description and standard read-only, destructive, idempotent, and closed-world hints. Detailed request grammar and examples are available through usage guides. Logical Vellis action documentation remains the semantic contract; generated runtime metadata carries the realization description without a second Python authority. */
        }
    }

    requirement <'contract.vellis.mcp.input_encoding'> mcpInputEncoding {
        subject adapter : VellisMcpAdapter;
        require constraint {
            doc /* MCP arguments use the exact lower_snake_case action input names. Required inputs must be present; omitted optional inputs use modeled defaults. JSON arrays that realize typed list values encode directly as arrays. Decoding rejects unknown fields, wrong kinds, unsupported enum literals, empty required strings/lists, and contradictory option shapes before invoking the action. */
        }
    }

    requirement <'contract.vellis.mcp.result_encoding'> mcpResultEncoding {
        subject adapter : VellisMcpAdapter;
        require constraint {
            doc /* Every successful action returns exactly {ok:true,result:<lower_snake_case JSON encoding of the modeled action result>}. The usage-guide codec preserves its typed topic and flattens its content fields beside topic for established-wire compatibility. Result shaping defined by the Vellis action occurs before this envelope and the adapter adds no other domain behavior. For current Python result records, an absent optional RtgDiagnostic encodes as an empty JSON object; failure envelopes instead omit an absent diagnostic. */
        }
    }

    requirement <'contract.vellis.mcp.failure_encoding'> mcpFailureEncoding {
        subject adapter : VellisMcpAdapter;
        require constraint {
            doc /* Every expected or unexpected action failure returns {ok:false,error:{type,message,diagnostic?}} rather than a transport failure. type preserves the concrete failure name. Controller validation failures additionally expose top-level transaction_id and validation_report when present on the source failure. Failure encoding adds no state effect. */
        }
    }

    requirement <'contract.vellis.mcp.transport_equivalence'> mcpTransportEquivalence {
        subject adapter : VellisMcpAdapter;
        require constraint {
            doc /* The exact same 27 tool contracts, descriptions, argument schemas, results, and failure envelopes are exposed over stdio and localhost HTTP; transport selection does not alter application semantics. */
        }
    }

    part contractContext {
        part adapter : VellisMcpAdapter;
        attribute outcome : VellisMcpOutcome;
        satisfy mcpOutcomeExclusive by outcome;
        satisfy mcpDescriptionAuthority by adapter;
        satisfy mcpInputEncoding by adapter;
        satisfy mcpResultEncoding by adapter;
        satisfy mcpFailureEncoding by adapter;
        satisfy mcpTransportEquivalence by adapter;
    }

    verification def VellisMcpOutcomeContractVerification {
        subject outcome : VellisMcpOutcome;
        objective {
            verify mcpOutcomeExclusive;
        }
        @EvidenceBinding {
            evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp.py#VellisMcpOutcomeContractVerification";
            implementationScope = "VellisMcpPython";
        }
    }


    verification def VellisMcpBoundaryVerification {
        subject adapter : VellisMcpAdapter;
        objective { verify mcpDescriptionAuthority; verify mcpInputEncoding; verify mcpResultEncoding; verify mcpFailureEncoding; verify mcpTransportEquivalence; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp.py#VellisMcpBoundaryVerification"; implementationScope = "VellisMcpPython"; }
    }
}
