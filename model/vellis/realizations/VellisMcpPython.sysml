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

    metadata def McpToolBinding {
        :>> annotatedElement : SysML::ActionUsage;
        attribute toolName : String;
        attribute implementationSymbol : String;
        attribute transport[1..*] : McpTransportKind;
        doc /* Vellis MCP realization traceability. The annotated action usage documents the exact transport-facing description; shared typed contracts define result and failure encoding. */
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

        perform action getSystemState[0..*] : RtgGetSystemState { @McpToolBinding { toolName = "rtg_get_system_state"; implementationSymbol = "RtgMcpToolset.rtg_get_system_state"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Read controller state for MCP-only agents. Returns state_classification (empty|schema_only|populated|has_staged_work|needs_replay), typed starter_schema status and available type keys, live schema summary, live/non-live counts, current migration-store status counts, persisted snapshot paths, ledger count, last ledger/transaction pointers, migration history hints, and recommended_workflows plus recommended_next_steps. Use everyday_life_schema, workflow_patterns, or request_patterns when entering cold. */
            action invokeFacade : RtgGetSystemState {
                out result redefines RtgGetSystemState::result = getSystemState.result;
            }
        }
        perform action getUsageGuide[0..*] : RtgGetUsageGuide { @McpToolBinding { toolName = "rtg_get_usage_guide"; implementationSymbol = "RtgMcpToolset.rtg_get_usage_guide"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Return MCP-accessible usage guidance and complete examples. topic values: everyday_life_schema, schema_design, mcp_bootstrap_checklist, operator_card, workflow_patterns, request_patterns, schema_staging_minimal, tool_call_shapes, live_write, lookup_examples, query_examples, recovery_and_replay, migration_history, migration_abandonment. Everyday Life guidance describes the installed Vellis ontology; generic examples teach RTG operation shapes without silently replacing application schema. */
            action invokeFacade : RtgGetUsageGuide {
                in topic redefines RtgGetUsageGuide::topic = getUsageGuide.topic;
                out result redefines RtgGetUsageGuide::result = getUsageGuide.result;
            }
        }
        perform action stageSchemaMigration[0..*] : RtgStageSchemaMigration { @McpToolBinding { toolName = "rtg_stage_schema_migration"; implementationSymbol = "RtgMcpToolset.rtg_stage_schema_migration"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Ergonomic schema staging for agents. Inputs: migration_id, description, schema_definitions[{kind:anchor|data_object|link,type_key,description,payload}], optional retire_live_schema[{kind,type_key}], validation_mode. Generates candidate UUIDs, sets system.live=false, fills schema_make_live/schema_make_non_live, submits the canonical rtg_stage_knowledge_changes payload, and returns that payload. Use after schema_bootstrap or schema_evolution workflow planning; next call is usually rtg_apply_migration_cutover. */
            action invokeFacade : RtgStageSchemaMigration {
                in migration_id redefines RtgStageSchemaMigration::migration_id = stageSchemaMigration.migration_id;
                in description redefines RtgStageSchemaMigration::description = stageSchemaMigration.description;
                in schema_definitions redefines RtgStageSchemaMigration::schema_definitions = stageSchemaMigration.schema_definitions;
                in retire_live_schema redefines RtgStageSchemaMigration::retire_live_schema = stageSchemaMigration.retire_live_schema;
                in validation_mode redefines RtgStageSchemaMigration::validation_mode = stageSchemaMigration.validation_mode;
                out result redefines RtgStageSchemaMigration::result = stageSchemaMigration.result;
            }
        }
        perform action validateLiveAnchorRecords[0..*] : RtgValidateLiveAnchorRecords { @McpToolBinding { toolName = "rtg_validate_live_anchor_records"; implementationSymbol = "RtgMcpToolset.rtg_validate_live_anchor_records"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Validate ergonomic live anchor records without mutating or ledgering. Inputs: anchor_records[{ref,type,display_name?,system?,facts:[{ref?,type,properties,system?}]}], optional link_writes, optional validation_options{tracks,finding_limit}. Compiles to canonical graph_changes and returns submitted_graph_changes plus validation result. */
            action invokeFacade : RtgValidateLiveAnchorRecords {
                in anchor_records redefines RtgValidateLiveAnchorRecords::anchor_records = validateLiveAnchorRecords.anchor_records;
                in link_writes redefines RtgValidateLiveAnchorRecords::link_writes = validateLiveAnchorRecords.link_writes;
                in validation_options redefines RtgValidateLiveAnchorRecords::validation_options = validateLiveAnchorRecords.validation_options;
                out result redefines RtgValidateLiveAnchorRecords::result = validateLiveAnchorRecords.result;
            }
        }
        perform action applyLiveAnchorRecords[0..*] : RtgApplyLiveAnchorRecords { @McpToolBinding { toolName = "rtg_apply_live_anchor_records"; implementationSymbol = "RtgMcpToolset.rtg_apply_live_anchor_records"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Apply ergonomic live anchor records after schema exists. Inputs: anchor_records[{ref,type,display_name?,system?,facts:[{ref?,type,properties,system?}]}], optional link_writes, validation_mode(strict|skip). Compiles to canonical graph_changes and returns submitted_graph_changes plus the underlying operation result. */
            action invokeFacade : RtgApplyLiveAnchorRecords {
                in anchor_records redefines RtgApplyLiveAnchorRecords::anchor_records = applyLiveAnchorRecords.anchor_records;
                in link_writes redefines RtgApplyLiveAnchorRecords::link_writes = applyLiveAnchorRecords.link_writes;
                in validation_mode redefines RtgApplyLiveAnchorRecords::validation_mode = applyLiveAnchorRecords.validation_mode;
                out result redefines RtgApplyLiveAnchorRecords::result = applyLiveAnchorRecords.result;
            }
        }
        perform action validateLiveGraphChanges[0..*] : RtgValidateLiveGraphChanges { @McpToolBinding { toolName = "rtg_validate_live_graph_changes"; implementationSymbol = "RtgMcpToolset.rtg_validate_live_graph_changes"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Validate normal live graph CRUD without mutating or ledgering it. Inputs: graph_changes with the same shape as rtg_apply_live_graph_changes and optional validation_options{tracks,finding_limit}. Do not pass validation_options.mode; mutation tools use validation_mode. Resolves local_ref values exactly like a real write, returns generated_ids, resolved_graph_changes, and validation_report, and leaves graph state and the controller ledger unchanged. Use before risky imports, safe_update, or validation_error_recovery probes. */
            action invokeFacade : RtgValidateLiveGraphChanges {
                in graph_changes redefines RtgValidateLiveGraphChanges::graph_changes = validateLiveGraphChanges.graph_changes;
                in validation_options redefines RtgValidateLiveGraphChanges::validation_options = validateLiveGraphChanges.validation_options;
                out result redefines RtgValidateLiveGraphChanges::result = validateLiveGraphChanges.result;
            }
        }
        perform action applyLiveGraphChanges[0..*] : RtgApplyLiveGraphChanges { @McpToolBinding { toolName = "rtg_apply_live_graph_changes"; implementationSymbol = "RtgMcpToolset.rtg_apply_live_graph_changes"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Apply normal live graph CRUD only. Use this after the live schema exists. graph_changes keys: anchor_writes[{ref:{local_ref|resource_id}, type, display_name?, system?}], data_object_writes[{ref, type, properties, anchor_refs:[ref], system?}], link_writes[{ref, type, source_ref, target_ref, system?}], associate_data[{anchor_ref,data_ref}], dissociate_data, delete_anchors, delete_data_objects, delete_links, set_live[{object_ref,live}]. Link writes require existing or same-request endpoint anchors and a live link schema allowing their types. local_ref is request-local only; use resource_id values returned by earlier calls for existing objects. Strict invalid writes return validation_report findings. Rejects schema, constraint, migration, and non-live candidate work. */
            action invokeFacade : RtgApplyLiveGraphChanges {
                in graph_changes redefines RtgApplyLiveGraphChanges::graph_changes = applyLiveGraphChanges.graph_changes;
                in validation_mode redefines RtgApplyLiveGraphChanges::validation_mode = applyLiveGraphChanges.validation_mode;
                out result redefines RtgApplyLiveGraphChanges::result = applyLiveGraphChanges.result;
            }
        }
        perform action stageKnowledgeChanges[0..*] : RtgStageKnowledgeChanges { @McpToolBinding { toolName = "rtg_stage_knowledge_changes"; implementationSymbol = "RtgMcpToolset.rtg_stage_knowledge_changes"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Advanced normalized-batch staging for migration-scoped knowledge-engineering changes. For ordinary schema bootstrap/evolution, prefer rtg_stage_schema_migration because it generates candidate UUIDs and migration membership. knowledge_changes is a change batch with schema_changes, constraint_changes, migration_changes, and optional non-live graph_changes. Schema writes use schema_changes.definition_writes[{ref, definition:{uuid?, kind: anchor|data_object|link, type_key, description, payload, system:{live:false}}}], where anchor payload uses required_data_types/optional_data_types, data_object payload uses properties:{field:{required,value_kinds,properties?,items?}}, and link payload uses allowed_source_types/allowed_target_types. Constraint writes use constraint_changes.constraint_writes[{ref,constraint:{uuid?, kind: query_pattern|cardinality, target_type_keys, display_name, description, payload, system:{live:false}}}], where query_pattern payload uses query_spec+expectation and cardinality payload uses query_spec+counted_binding+minimum/maximum. Migration writes use migration_changes.migration_writes[{ref, migration:{migration_id, description, status:ready, schema_make_live?, schema_make_non_live?, graph_make_live?, constraint_make_live?}}]. New candidates must be referenced by a migration record in the same request. For non-live graph_changes, graph_make_live must include every candidate anchor, data object, and link UUID. Strict staging validates the projected migration cutover; use validation_mode:skip only for controlled recovery or intentionally invalid cutover tests. */
            action invokeFacade : RtgStageKnowledgeChanges {
                in knowledge_changes redefines RtgStageKnowledgeChanges::knowledge_changes = stageKnowledgeChanges.knowledge_changes;
                in validation_mode redefines RtgStageKnowledgeChanges::validation_mode = stageKnowledgeChanges.validation_mode;
                out result redefines RtgStageKnowledgeChanges::result = stageKnowledgeChanges.result;
            }
        }
        perform action applyMigrationCutover[0..*] : RtgApplyMigrationCutover { @McpToolBinding { toolName = "rtg_apply_migration_cutover"; implementationSymbol = "RtgMcpToolset.rtg_apply_migration_cutover"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Apply an explicit migration cutover. The migration record decides which staged schema, constraint, or graph candidates become live and which records retire. Use after rtg_stage_knowledge_changes returns ok:true. cutover_options keys: validation_mode (strict|skip, default strict), prune_retired (default true), failure_restore (only restore_pre_cutover_snapshot in v1). Strict cutover returns validation_report findings, restores or preserves the previous live state on blocking failures, and marks the migration failed so replay can reproduce that status. */
            action invokeFacade : RtgApplyMigrationCutover {
                in migration_id redefines RtgApplyMigrationCutover::migration_id = applyMigrationCutover.migration_id;
                in cutover_options redefines RtgApplyMigrationCutover::cutover_options = applyMigrationCutover.cutover_options;
                out result redefines RtgApplyMigrationCutover::result = applyMigrationCutover.result;
            }
        }
        perform action abandonMigration[0..*] : RtgAbandonMigration { @McpToolBinding { toolName = "rtg_abandon_migration"; implementationSymbol = "RtgMcpToolset.rtg_abandon_migration"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Abandon draft/ready/failed staged work and prune safe non-live make-live candidates. Never deletes live records or make-non-live targets. Use when exploratory schema, constraint, or non-live graph candidates should not proceed. */
            action invokeFacade : RtgAbandonMigration {
                in migration_id redefines RtgAbandonMigration::migration_id = abandonMigration.migration_id;
                in reason redefines RtgAbandonMigration::reason = abandonMigration.reason;
                out result redefines RtgAbandonMigration::result = abandonMigration.result;
            }
        }
        perform action executeQuery[0..*] : RtgExecuteQuery { @McpToolBinding { toolName = "rtg_execute_query"; implementationSymbol = "RtgMcpToolset.rtg_execute_query"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Execute a read-only RTG query. query_spec keys: anchor_buckets[{name, anchor_type_keys}], link_requirements[{name, source_bucket, target_bucket, link_type_keys}], data_requirements[{name, anchor_bucket, data_type_key, required?, predicates:[{path:[property,...], operator, value?, values?, case_sensitive?, regex_flags?}]}], return_spec:{anchor_buckets?, link_requirements?, data_requirements?, properties:[[data_requirement_name,[property,...]]]}. Operators: exists, equals, not_equals, lt, lte, gt, gte, contains, in, substring, regex. query_options keys: live_filter(all|live|non_live), live_status_overlay, order_by[{data_requirement,path,direction:ascending|descending}]. order_by may only reference paths listed in return_spec.properties. Optional response_options supports format:full or properties_only. */
            action invokeFacade : RtgExecuteQuery {
                in query_spec redefines RtgExecuteQuery::query_spec = executeQuery.query_spec;
                in query_options redefines RtgExecuteQuery::query_options = executeQuery.query_options;
                in response_options redefines RtgExecuteQuery::response_options = executeQuery.response_options;
                out result redefines RtgExecuteQuery::result = executeQuery.result;
            }
        }
        perform action resolveAnchorByFact[0..*] : RtgResolveAnchorByFact { @McpToolBinding { toolName = "rtg_resolve_anchor_by_fact"; implementationSymbol = "RtgMcpToolset.rtg_resolve_anchor_by_fact"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Resolve live anchor UUIDs through the canonical query contract. Inputs: anchor_type, data_type, property_path, value, optional case_sensitive. Compiles to rtg_execute_query and returns match_count, matches[{resource_id, properties}], submitted_query, and guidance for zero or multiple matches. */
            action invokeFacade : RtgResolveAnchorByFact {
                in anchor_type redefines RtgResolveAnchorByFact::anchor_type = resolveAnchorByFact.anchor_type;
                in data_type redefines RtgResolveAnchorByFact::data_type = resolveAnchorByFact.data_type;
                in property_path redefines RtgResolveAnchorByFact::property_path = resolveAnchorByFact.property_path;
                in value redefines RtgResolveAnchorByFact::value = resolveAnchorByFact.value;
                in case_sensitive redefines RtgResolveAnchorByFact::case_sensitive = resolveAnchorByFact.case_sensitive;
                out result redefines RtgResolveAnchorByFact::result = resolveAnchorByFact.result;
            }
        }
        perform action getObject[0..*] : RtgGetObject { @McpToolBinding { toolName = "rtg_get_object"; implementationSymbol = "RtgMcpToolset.rtg_get_object"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Read one RTG graph object by UUID. */
            action invokeFacade : RtgGetObject {
                in object_uuid redefines RtgGetObject::object_uuid = getObject.object_uuid;
                out result redefines RtgGetObject::result = getObject.result;
            }
        }
        perform action listMigrations[0..*] : RtgListMigrations { @McpToolBinding { toolName = "rtg_list_migrations"; implementationSymbol = "RtgMcpToolset.rtg_list_migrations"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* List RTG migration records, optionally filtered by status. */
            action invokeFacade : RtgListMigrations {
                in status redefines RtgListMigrations::status = listMigrations.status;
                out result redefines RtgListMigrations::result = listMigrations.result;
            }
        }
        perform action getMigration[0..*] : RtgGetMigration { @McpToolBinding { toolName = "rtg_get_migration"; implementationSymbol = "RtgMcpToolset.rtg_get_migration"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Read one RTG migration record by ID. */
            action invokeFacade : RtgGetMigration {
                in migration_id redefines RtgGetMigration::migration_id = getMigration.migration_id;
                out result redefines RtgGetMigration::result = getMigration.result;
            }
        }
        perform action validateGraph[0..*] : RtgValidateGraph { @McpToolBinding { toolName = "rtg_validate_graph"; implementationSymbol = "RtgMcpToolset.rtg_validate_graph"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Validate current or migration-projected RTG state without mutation. Use rtg_validate_graph({}) as the first MCP smoke check. Pass migration_ids to validate a staged cutover projection. validation_options keys: tracks (all or list), finding_limit (positive integer). */
            action invokeFacade : RtgValidateGraph {
                in migration_ids redefines RtgValidateGraph::migration_ids = validateGraph.migration_ids;
                in validation_options redefines RtgValidateGraph::validation_options = validateGraph.validation_options;
                out result redefines RtgValidateGraph::result = validateGraph.result;
            }
        }
        perform action discoverAnchorTypes[0..*] : RtgDiscoverAnchorTypes { @McpToolBinding { toolName = "rtg_discover_anchor_types"; implementationSymbol = "RtgMcpToolset.rtg_discover_anchor_types"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Return live anchor type keys and descriptions for discovery. discovery_options keys: include_non_live, limit (positive integer). Use before guessing anchor_type_keys. */
            action invokeFacade : RtgDiscoverAnchorTypes {
                in discovery_options redefines RtgDiscoverAnchorTypes::discovery_options = discoverAnchorTypes.discovery_options;
                out result redefines RtgDiscoverAnchorTypes::result = discoverAnchorTypes.result;
            }
        }
        perform action getSchemaPack[0..*] : RtgGetSchemaPack { @McpToolBinding { toolName = "rtg_get_schema_pack"; implementationSymbol = "RtgMcpToolset.rtg_get_schema_pack"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Return schema details and optional live counts for anchor types. Provide anchor_type_keys. schema_pack_options keys: live (true, false, or null), include_live_counts. Use this before writing data_object_writes or query data_requirements so required data types and property names are known. */
            action invokeFacade : RtgGetSchemaPack {
                in anchor_type_keys redefines RtgGetSchemaPack::anchor_type_keys = getSchemaPack.anchor_type_keys;
                in schema_pack_options redefines RtgGetSchemaPack::schema_pack_options = getSchemaPack.schema_pack_options;
                out result redefines RtgGetSchemaPack::result = getSchemaPack.result;
            }
        }
        perform action exportSystemSnapshot[0..*] : RtgExportSystemSnapshot { @McpToolBinding { toolName = "rtg_export_system_snapshot"; implementationSymbol = "RtgMcpToolset.rtg_export_system_snapshot"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Export a coordinated JSON-safe RTG system snapshot for graph, schema, constraints, migration state, and ledger position. Pass summary:true for compact counts and ledger pointers instead of the full graph payload. */
            action invokeFacade : RtgExportSystemSnapshot {
                in summary redefines RtgExportSystemSnapshot::summary = exportSystemSnapshot.summary;
                out result redefines RtgExportSystemSnapshot::result = exportSystemSnapshot.result;
            }
        }
        perform action persistSystemSnapshot[0..*] : RtgPersistSystemSnapshot { @McpToolBinding { toolName = "rtg_persist_system_snapshot"; implementationSymbol = "RtgMcpToolset.rtg_persist_system_snapshot"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Persist a coordinated system snapshot through JSON File Storage at relative_path. Pass return_snapshot:false to omit the full snapshot payload and return compact summary metadata. */
            action invokeFacade : RtgPersistSystemSnapshot {
                in relative_path redefines RtgPersistSystemSnapshot::relative_path = persistSystemSnapshot.relative_path;
                in return_snapshot redefines RtgPersistSystemSnapshot::return_snapshot = persistSystemSnapshot.return_snapshot;
                out result redefines RtgPersistSystemSnapshot::result = persistSystemSnapshot.result;
            }
        }
        perform action listPersistedSnapshots[0..*] : RtgListPersistedSnapshots { @McpToolBinding { toolName = "rtg_list_persisted_snapshots"; implementationSymbol = "RtgMcpToolset.rtg_list_persisted_snapshots"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* List persisted system snapshots visible through JSON File Storage. Does not expose arbitrary filesystem access. */
            action invokeFacade : RtgListPersistedSnapshots {
                out result redefines RtgListPersistedSnapshots::result = listPersistedSnapshots.result;
            }
        }
        perform action loadPersistedSnapshot[0..*] : RtgLoadPersistedSnapshot { @McpToolBinding { toolName = "rtg_load_persisted_snapshot"; implementationSymbol = "RtgMcpToolset.rtg_load_persisted_snapshot"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Load one persisted system snapshot by relative JSON File Storage path. Use the returned snapshot with rtg_restore_from_snapshot or rtg_replay_ledger start_snapshot. Pass return_snapshot:false to return only relative_path and compact summary. */
            action invokeFacade : RtgLoadPersistedSnapshot {
                in relative_path redefines RtgLoadPersistedSnapshot::relative_path = loadPersistedSnapshot.relative_path;
                in return_snapshot redefines RtgLoadPersistedSnapshot::return_snapshot = loadPersistedSnapshot.return_snapshot;
                out result redefines RtgLoadPersistedSnapshot::result = loadPersistedSnapshot.result;
            }
        }
        perform action replayLedger[0..*] : RtgReplayLedger { @McpToolBinding { toolName = "rtg_replay_ledger"; implementationSymbol = "RtgMcpToolset.rtg_replay_ledger"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Replay mutating controller ledger requests into an empty or snapshot-seeded controller. replay_options keys: start_snapshot, start_snapshot_path, after_ledger_position, through_ledger_position. Ordinary startup replays automatically; this explicit surface supports controlled recovery, audits, and manual-recovery evaluation. */
            action invokeFacade : RtgReplayLedger {
                in replay_options redefines RtgReplayLedger::replay_options = replayLedger.replay_options;
                out result redefines RtgReplayLedger::result = replayLedger.result;
            }
        }
        perform action verifyReplay[0..*] : RtgVerifyReplayFromLedger { @McpToolBinding { toolName = "rtg_verify_replay_from_ledger"; implementationSymbol = "RtgMcpToolset.rtg_verify_replay_from_ledger"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Replay mutating controller ledger requests into isolated scratch state and restore the current state before returning. Accepts the same replay_options as rtg_replay_ledger, including start_snapshot_path. Returns pre/post summaries, count diffs, replay counts, and validation result without appending ledger entries. */
            action invokeFacade : RtgVerifyReplayFromLedger {
                in replay_options redefines RtgVerifyReplayFromLedger::replay_options = verifyReplay.replay_options;
                out result redefines RtgVerifyReplayFromLedger::result = verifyReplay.result;
            }
        }
        perform action listMigrationHistory[0..*] : RtgListMigrationHistory { @McpToolBinding { toolName = "rtg_list_migration_history"; implementationSymbol = "RtgMcpToolset.rtg_list_migration_history"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Return ledger-backed migration audit events, including staged, cutover_applied, cutover_failed, and abandoned events. Applied migrations may be absent from the live migration store but remain visible here. */
            action invokeFacade : RtgListMigrationHistory {
                out result redefines RtgListMigrationHistory::result = listMigrationHistory.result;
            }
        }
        perform action flushLedgerFailures[0..*] : RtgFlushLedgerFailures { @McpToolBinding { toolName = "rtg_flush_ledger_failures"; implementationSymbol = "RtgMcpToolset.rtg_flush_ledger_failures"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Flush queued controller ledger failures to SQL storage. */
            action invokeFacade : RtgFlushLedgerFailures {
                out result redefines RtgFlushLedgerFailures::result = flushLedgerFailures.result;
            }
        }
        perform action restoreFromSnapshot[0..*] : RtgRestoreFromSnapshot { @McpToolBinding { toolName = "rtg_restore_from_snapshot"; implementationSymbol = "RtgMcpToolset.rtg_restore_from_snapshot"; transport = (McpTransportKind::stdio, McpTransportKind::http); }
            doc /* Restore RTG state from a supplied system snapshot. restore_options keys: ledger_mode(record|skip). Use with rtg_export_system_snapshot or a persisted snapshot payload. */
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
            doc /* Each MCP-bound adapter action documents its exact transport-facing tool description. Logical Vellis action documentation remains the concise semantic contract; generated runtime metadata carries the realization description without a second Python authority. */
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
            doc /* Every successful action returns exactly {ok:true,result:<lower_snake_case JSON encoding of the modeled action result>}. Result shaping defined by the Vellis action occurs before this envelope and the adapter adds no domain behavior. For current Python result records, an absent optional RtgDiagnostic encodes as an empty JSON object; failure envelopes instead omit an absent diagnostic. */
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
