package VellisMcpPythonRealization {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import BibliotekRtgChangeValidation::*;
    private import VellisOperations::*;
    private import VellisLocalPythonRealization::*;

    enum def McpTransportKind {
        enum stdio;
        enum http;
    }

    metadata def McpToolBinding {
        attribute toolName : String;
        attribute descriptionSymbol : String;
        attribute implementationSymbol : String;
        attribute transport[1..*] : McpTransportKind;
        attribute resultMapping : String;
        attribute errorMapping : String;
        doc /* Vellis MCP realization traceability; this vocabulary is intentionally not part of the generic component-modeling foundation. */
    }

    attribute def VellisMcpError {
        attribute type : String;
        attribute message : String;
        attribute diagnostic[0..1] : JsonObject;
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
        @ImplementationBinding { language = ImplementationLanguage::python; codeRoot = "apps/rtg_knowledge_graph"; symbol = "apps.rtg_knowledge_graph.mcp_server.build_mcp_server"; realization = "FastMCP"; }
        port endpoint : McpEndpoint;

        perform action getSystemState[0..*] : RtgGetSystemState { @McpToolBinding { toolName = "rtg_get_system_state"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_get_system_state"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_get_system_state"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action getUsageGuide[0..*] : RtgGetUsageGuide { @McpToolBinding { toolName = "rtg_get_usage_guide"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_get_usage_guide"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_get_usage_guide"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action stageSchemaMigration[0..*] : RtgStageSchemaMigration { @McpToolBinding { toolName = "rtg_stage_schema_migration"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_stage_schema_migration"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_stage_schema_migration"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action validateLiveAnchorRecords[0..*] : RtgValidateLiveAnchorRecords { @McpToolBinding { toolName = "rtg_validate_live_anchor_records"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_validate_live_anchor_records"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_validate_live_anchor_records"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action applyLiveAnchorRecords[0..*] : RtgApplyLiveAnchorRecords { @McpToolBinding { toolName = "rtg_apply_live_anchor_records"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_apply_live_anchor_records"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_apply_live_anchor_records"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action validateLiveGraphChanges[0..*] : RtgValidateLiveGraphChanges { @McpToolBinding { toolName = "rtg_validate_live_graph_changes"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_validate_live_graph_changes"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_validate_live_graph_changes"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action applyLiveGraphChanges[0..*] : RtgApplyLiveGraphChanges { @McpToolBinding { toolName = "rtg_apply_live_graph_changes"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_apply_live_graph_changes"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_apply_live_graph_changes"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action stageKnowledgeChanges[0..*] : RtgStageKnowledgeChanges { @McpToolBinding { toolName = "rtg_stage_knowledge_changes"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_stage_knowledge_changes"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_stage_knowledge_changes"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action applyMigrationCutover[0..*] : RtgApplyMigrationCutover { @McpToolBinding { toolName = "rtg_apply_migration_cutover"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_apply_migration_cutover"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_apply_migration_cutover"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action abandonMigration[0..*] : RtgAbandonMigration { @McpToolBinding { toolName = "rtg_abandon_migration"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_abandon_migration"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_abandon_migration"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action executeQuery[0..*] : RtgExecuteQuery { @McpToolBinding { toolName = "rtg_execute_query"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_execute_query"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_execute_query"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action resolveAnchorByFact[0..*] : RtgResolveAnchorByFact { @McpToolBinding { toolName = "rtg_resolve_anchor_by_fact"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_resolve_anchor_by_fact"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_resolve_anchor_by_fact"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action getObject[0..*] : RtgGetObject { @McpToolBinding { toolName = "rtg_get_object"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_get_object"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_get_object"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action listMigrations[0..*] : RtgListMigrations { @McpToolBinding { toolName = "rtg_list_migrations"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_list_migrations"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_list_migrations"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action getMigration[0..*] : RtgGetMigration { @McpToolBinding { toolName = "rtg_get_migration"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_get_migration"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_get_migration"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action validateGraph[0..*] : RtgValidateGraph { @McpToolBinding { toolName = "rtg_validate_graph"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_validate_graph"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_validate_graph"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action discoverAnchorTypes[0..*] : RtgDiscoverAnchorTypes { @McpToolBinding { toolName = "rtg_discover_anchor_types"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_discover_anchor_types"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_discover_anchor_types"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action getSchemaPack[0..*] : RtgGetSchemaPack { @McpToolBinding { toolName = "rtg_get_schema_pack"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_get_schema_pack"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_get_schema_pack"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action exportSystemSnapshot[0..*] : RtgExportSystemSnapshot { @McpToolBinding { toolName = "rtg_export_system_snapshot"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_export_system_snapshot"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_export_system_snapshot"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action persistSystemSnapshot[0..*] : RtgPersistSystemSnapshot { @McpToolBinding { toolName = "rtg_persist_system_snapshot"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_persist_system_snapshot"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_persist_system_snapshot"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action listPersistedSnapshots[0..*] : RtgListPersistedSnapshots { @McpToolBinding { toolName = "rtg_list_persisted_snapshots"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_list_persisted_snapshots"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_list_persisted_snapshots"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action loadPersistedSnapshot[0..*] : RtgLoadPersistedSnapshot { @McpToolBinding { toolName = "rtg_load_persisted_snapshot"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_load_persisted_snapshot"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_load_persisted_snapshot"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action replayLedger[0..*] : RtgReplayLedger { @McpToolBinding { toolName = "rtg_replay_ledger"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_replay_ledger"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_replay_ledger"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action verifyReplay[0..*] : RtgVerifyReplayFromLedger { @McpToolBinding { toolName = "rtg_verify_replay_from_ledger"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_verify_replay_from_ledger"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_verify_replay_from_ledger"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action listMigrationHistory[0..*] : RtgListMigrationHistory { @McpToolBinding { toolName = "rtg_list_migration_history"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_list_migration_history"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_list_migration_history"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action flushLedgerFailures[0..*] : RtgFlushLedgerFailures { @McpToolBinding { toolName = "rtg_flush_ledger_failures"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_flush_ledger_failures"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_flush_ledger_failures"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
        perform action restoreFromSnapshot[0..*] : RtgRestoreFromSnapshot { @McpToolBinding { toolName = "rtg_restore_from_snapshot"; descriptionSymbol = "TOOL_DESCRIPTIONS.rtg_restore_from_snapshot"; resultMapping = "JSON object returned by RtgMcpToolset"; errorMapping = "guarded MCP error envelope"; implementationSymbol = "RtgMcpToolset.rtg_restore_from_snapshot"; transport = (McpTransportKind::stdio, McpTransportKind::http); } }
    }

    part def VellisMcpPython {
        part application : VellisLocalPython;
        part adapter : VellisMcpAdapter;
        part client : McpClient;
        interface clientToAdapter : McpToolExchange
            connect client.endpoint to adapter.endpoint;
    }

    requirement <'contract.vellis.mcp.outcome_exclusive'> mcpOutcomeExclusive {
        subject outcome : VellisMcpOutcome;
        doc /* Every completed tool invocation has exactly one success value or one failure value, never both and never neither. */
    }
    requirement <'contract.vellis.mcp.description_authority'> mcpDescriptionAuthority {
        subject adapter : VellisMcpAdapter;
        doc /* Each tool description is generated from the documentation of its typed Vellis action contract. descriptionSymbol is a Python realization trace only and never the semantic source. */
    }
    requirement <'contract.vellis.mcp.input_encoding'> mcpInputEncoding {
        subject adapter : VellisMcpAdapter;
        doc /* MCP arguments use the exact lower_snake_case action input names. Required inputs must be present; omitted optional inputs use modeled defaults. JSON arrays that realize typed list values encode directly as arrays. Decoding rejects unknown fields, wrong kinds, unsupported enum literals, empty required strings/lists, and contradictory option shapes before invoking the action. */
    }
    requirement <'contract.vellis.mcp.result_encoding'> mcpResultEncoding {
        subject adapter : VellisMcpAdapter;
        doc /* Every successful action returns exactly {ok:true,result:<lower_snake_case JSON encoding of the modeled action result>}. Result shaping defined by the Vellis action occurs before this envelope and the adapter adds no domain behavior. */
    }
    requirement <'contract.vellis.mcp.failure_encoding'> mcpFailureEncoding {
        subject adapter : VellisMcpAdapter;
        doc /* Every expected or unexpected action failure returns {ok:false,error:{type,message,diagnostic?}} rather than a transport failure. type preserves the concrete failure name. Controller validation failures additionally expose top-level transaction_id and validation_report when present on the source failure. Failure encoding adds no state effect. */
    }
    requirement <'contract.vellis.mcp.transport_equivalence'> mcpTransportEquivalence {
        subject adapter : VellisMcpAdapter;
        doc /* The exact same 27 tool contracts, descriptions, argument schemas, results, and failure envelopes are exposed over stdio and localhost HTTP; transport selection does not alter application semantics. */
    }

    verification def VellisMcpBoundaryVerification {
        subject adapter : VellisMcpAdapter;
        objective { verify mcpOutcomeExclusive; verify mcpDescriptionAuthority; verify mcpInputEncoding; verify mcpResultEncoding; verify mcpFailureEncoding; verify mcpTransportEquivalence; }
        @EvidenceBinding { verificationId = "verification.vellis.mcp.boundary"; evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp.py"; implementationScope = "VellisMcpPython"; }
    }
}
