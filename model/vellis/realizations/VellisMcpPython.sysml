package VellisMcpPythonRealization {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;
    private import BibliotekRtgChangeValidation::*;
    private import BibliotekRtgDiagnostics::*;
    private import BibliotekInterfaceMcpGateway::*;
    private import VellisOperations::*;
    private import VellisRuntimePythonRealization::*;

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
        doc /* Vellis MCP registration traceability, optional dry-run predecessor, and standard MCP behavioral hints. Each annotated transport action is projected dynamically through the generic gateway; detailed grammar lives in usage guides and shared typed contracts define result and failure encoding. */
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
        doc /* Project the curated Vellis MCP registrations over a generic gateway without retaining the application facade, controller, or domain implementations. */
        ref part gateway[1] : McpGateway;
        port endpoint : McpEndpoint;

        perform action getSystemState[0..*] : RtgGetSystemState { @McpToolBinding { toolName = "rtg_get_system_state"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::state_and_discovery; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Inspect RTG state and workflow guidance; Lane: state_and_discovery; call this before schema-dependent work. */
        }
        perform action getUsageGuide[0..*] : RtgGetUsageGuide { @McpToolBinding { toolName = "rtg_get_usage_guide"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::state_and_discovery; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Read detailed RTG request shapes and workflows; Lane: state_and_discovery; use topic capabilities for the tool map. */
        }
        perform action stageSchemaMigration[0..*] : RtgStageSchemaMigration { @McpToolBinding { toolName = "rtg_stage_schema_migration"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::knowledge_engineering; audience = McpAudienceKind::advanced; ledgers = true; recommendedPredecessors = ("rtg_get_system_state", "rtg_get_schema_pack"); readOnlyHint = false; destructiveHint = true; idempotentHint = false; openWorldHint = false; }
            doc /* Stage an ergonomic schema migration; Lane: knowledge_engineering; inspect current schema and obtain approval first. */
        }
        perform action validateLiveAnchorRecords[0..*] : RtgValidateLiveAnchorRecords { @McpToolBinding { toolName = "rtg_validate_live_anchor_records"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::live_graph; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Dry-run ergonomic anchor records without mutation or ledgering; Lane: live_graph. */
        }
        perform action applyLiveAnchorRecords[0..*] : RtgApplyLiveAnchorRecords { @McpToolBinding { toolName = "rtg_apply_live_anchor_records"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::live_graph; audience = McpAudienceKind::everyday; ledgers = true; recommendedPredecessors = ("rtg_validate_live_anchor_records"); dryRunTool = "rtg_validate_live_anchor_records"; readOnlyHint = false; destructiveHint = true; idempotentHint = false; openWorldHint = false; }
            doc /* Apply ergonomic anchor records to live state; Lane: live_graph; discover schema first. */
        }
        perform action validateLiveGraphChanges[0..*] : RtgValidateLiveGraphChanges { @McpToolBinding { toolName = "rtg_validate_live_graph_changes"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::live_graph; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Dry-run normalized live graph changes without mutation or ledgering; Lane: live_graph. */
        }
        perform action applyLiveGraphChanges[0..*] : RtgApplyLiveGraphChanges { @McpToolBinding { toolName = "rtg_apply_live_graph_changes"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::live_graph; audience = McpAudienceKind::everyday; ledgers = true; recommendedPredecessors = ("rtg_validate_live_graph_changes"); dryRunTool = "rtg_validate_live_graph_changes"; readOnlyHint = false; destructiveHint = true; idempotentHint = false; openWorldHint = false; }
            doc /* Apply normalized live graph changes; Lane: live_graph; use the validation predecessor for risky writes. */
        }
        perform action stageKnowledgeChanges[0..*] : RtgStageKnowledgeChanges { @McpToolBinding { toolName = "rtg_stage_knowledge_changes"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::knowledge_engineering; audience = McpAudienceKind::advanced; ledgers = true; recommendedPredecessors = ("rtg_get_system_state", "rtg_validate_graph"); readOnlyHint = false; destructiveHint = true; idempotentHint = false; openWorldHint = false; }
            doc /* Stage an advanced normalized knowledge batch; Lane: knowledge_engineering; prefer ergonomic staging for ordinary schema work. */
        }
        perform action applyMigrationCutover[0..*] : RtgApplyMigrationCutover { @McpToolBinding { toolName = "rtg_apply_migration_cutover"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::migration; audience = McpAudienceKind::advanced; ledgers = true; recommendedPredecessors = ("rtg_get_migration", "rtg_validate_graph"); readOnlyHint = false; destructiveHint = true; idempotentHint = false; openWorldHint = false; }
            doc /* Apply a staged migration atomically; Lane: migration; validate the projected state first. */
        }
        perform action abandonMigration[0..*] : RtgAbandonMigration { @McpToolBinding { toolName = "rtg_abandon_migration"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::migration; audience = McpAudienceKind::advanced; ledgers = true; recommendedPredecessors = ("rtg_get_migration"); readOnlyHint = false; destructiveHint = true; idempotentHint = false; openWorldHint = false; }
            doc /* Abandon staged migration work and prune safe non-live candidates; Lane: migration. */
        }
        perform action executeQuery[0..*] : RtgExecuteQuery { @McpToolBinding { toolName = "rtg_execute_query"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::query; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Execute a read-only RTG query; Lane: query; detailed grammar and examples are in usage guides. */
        }
        perform action resolveAnchorByFact[0..*] : RtgResolveAnchorByFact { @McpToolBinding { toolName = "rtg_resolve_anchor_by_fact"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::query; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Resolve zero, one, or multiple live anchors by typed fact; Lane: query; never guess among multiple matches. */
        }
        perform action getObject[0..*] : RtgGetObject { @McpToolBinding { toolName = "rtg_get_object"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::state_and_discovery; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Read one RTG graph object by UUID; Lane: state_and_discovery. */
        }
        perform action listMigrations[0..*] : RtgListMigrations { @McpToolBinding { toolName = "rtg_list_migrations"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::migration; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* List current migration-store records; Lane: migration; use history for pruned or rejected work. */
        }
        perform action getMigration[0..*] : RtgGetMigration { @McpToolBinding { toolName = "rtg_get_migration"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::migration; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Read one current migration-store record by ID; Lane: migration. */
        }
        perform action validateGraph[0..*] : RtgValidateGraph { @McpToolBinding { toolName = "rtg_validate_graph"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::live_graph; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Validate current or migration-projected RTG state without mutation; Lane: live_graph. */
        }
        perform action discoverAnchorTypes[0..*] : RtgDiscoverAnchorTypes { @McpToolBinding { toolName = "rtg_discover_anchor_types"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::state_and_discovery; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Discover anchor types and live counts; Lane: state_and_discovery; use before guessing type keys. */
        }
        perform action getSchemaPack[0..*] : RtgGetSchemaPack { @McpToolBinding { toolName = "rtg_get_schema_pack"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::state_and_discovery; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Read schema details for selected anchor types; Lane: state_and_discovery; use before writes. */
        }
        perform action exportSystemSnapshot[0..*] : RtgExportSystemSnapshot { @McpToolBinding { toolName = "rtg_export_system_snapshot"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::recovery_and_audit; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Export current coordinated RTG state or a compact summary; Lane: recovery_and_audit. */
        }
        perform action persistSystemSnapshot[0..*] : RtgPersistSystemSnapshot { @McpToolBinding { toolName = "rtg_persist_system_snapshot"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::recovery_and_audit; audience = McpAudienceKind::everyday; ledgers = true; readOnlyHint = false; destructiveHint = true; idempotentHint = false; openWorldHint = false; }
            doc /* Persist a coordinated RTG snapshot; Lane: recovery_and_audit; the runtime records the request, component calls, and terminal trace. */
        }
        perform action listPersistedSnapshots[0..*] : RtgListPersistedSnapshots { @McpToolBinding { toolName = "rtg_list_persisted_snapshots"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::recovery_and_audit; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* List RTG snapshots visible through configured storage; Lane: recovery_and_audit. */
        }
        perform action loadPersistedSnapshot[0..*] : RtgLoadPersistedSnapshot { @McpToolBinding { toolName = "rtg_load_persisted_snapshot"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::recovery_and_audit; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Load one persisted RTG snapshot without restoring it; Lane: recovery_and_audit. */
        }
        perform action replayLedger[0..*] : RtgReplayLedger { @McpToolBinding { toolName = "rtg_replay_ledger"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::recovery_and_audit; audience = McpAudienceKind::operator; ledgers = false; recommendedPredecessors = ("rtg_get_system_state"); readOnlyHint = false; destructiveHint = true; idempotentHint = false; openWorldHint = false; }
            doc /* Reconstruct committed canonical effects through an optional runtime cursor after explicit reset or compatible checkpoints; Lane: recovery_and_audit; operator use. */
        }
        perform action verifyReplay[0..*] : RtgVerifyReplayFromLedger { @McpToolBinding { toolName = "rtg_verify_replay_from_ledger"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::recovery_and_audit; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Report exact available reconstruction evidence and direct historical requests to an isolated data-root copy; Lane: recovery_and_audit. */
        }
        perform action listMigrationHistory[0..*] : RtgListMigrationHistory { @McpToolBinding { toolName = "rtg_list_migration_history"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::migration; audience = McpAudienceKind::everyday; ledgers = false; readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Read migration-related runtime traces in terminal-position order; Lane: migration. */
        }
        perform action flushLedgerFailures[0..*] : RtgFlushLedgerFailures { @McpToolBinding { toolName = "rtg_flush_ledger_failures"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::recovery_and_audit; audience = McpAudienceKind::operator; ledgers = false; recommendedPredecessors = ("rtg_get_system_state"); readOnlyHint = true; destructiveHint = false; idempotentHint = true; openWorldHint = false; }
            doc /* Deprecated health-only status for callers that still know the old tool name; Lane: recovery_and_audit; operator use. */
        }
        perform action restoreFromSnapshot[0..*] : RtgRestoreFromSnapshot { @McpToolBinding { toolName = "rtg_restore_from_snapshot"; implementationSymbol = "apps.rtg_knowledge_graph.mcp_server._RuntimeGatewayTool.run"; transport = (McpTransportKind::stdio, McpTransportKind::http); lane = McpOperationalLane::recovery_and_audit; audience = McpAudienceKind::operator; ledgers = true; recommendedPredecessors = ("rtg_load_persisted_snapshot"); readOnlyHint = false; destructiveHint = true; idempotentHint = false; openWorldHint = false; }
            doc /* Restore coordinated RTG state from a supplied snapshot; Lane: recovery_and_audit; operator use. */
        }
    }

    part def VellisMcpPython {
        part application : VellisRuntimePython;
        part adapter : VellisMcpAdapter;
        part client : McpClient;
        interface clientToAdapter : McpToolExchange
            connect client.endpoint to adapter.endpoint;
        bind adapter.gateway = application.gateway;
        allocate adapter.getSystemState to application.gateway.invokeTool;
        allocate adapter.getUsageGuide to application.gateway.invokeTool;
        allocate adapter.stageSchemaMigration to application.gateway.invokeTool;
        allocate adapter.validateLiveAnchorRecords to application.gateway.invokeTool;
        allocate adapter.applyLiveAnchorRecords to application.gateway.invokeTool;
        allocate adapter.validateLiveGraphChanges to application.gateway.invokeTool;
        allocate adapter.applyLiveGraphChanges to application.gateway.invokeTool;
        allocate adapter.stageKnowledgeChanges to application.gateway.invokeTool;
        allocate adapter.applyMigrationCutover to application.gateway.invokeTool;
        allocate adapter.abandonMigration to application.gateway.invokeTool;
        allocate adapter.executeQuery to application.gateway.invokeTool;
        allocate adapter.resolveAnchorByFact to application.gateway.invokeTool;
        allocate adapter.getObject to application.gateway.invokeTool;
        allocate adapter.listMigrations to application.gateway.invokeTool;
        allocate adapter.getMigration to application.gateway.invokeTool;
        allocate adapter.validateGraph to application.gateway.invokeTool;
        allocate adapter.discoverAnchorTypes to application.gateway.invokeTool;
        allocate adapter.getSchemaPack to application.gateway.invokeTool;
        allocate adapter.exportSystemSnapshot to application.gateway.invokeTool;
        allocate adapter.persistSystemSnapshot to application.gateway.invokeTool;
        allocate adapter.listPersistedSnapshots to application.gateway.invokeTool;
        allocate adapter.loadPersistedSnapshot to application.gateway.invokeTool;
        allocate adapter.replayLedger to application.gateway.invokeTool;
        allocate adapter.verifyReplay to application.gateway.invokeTool;
        allocate adapter.listMigrationHistory to application.gateway.invokeTool;
        allocate adapter.flushLedgerFailures to application.gateway.invokeTool;
        allocate adapter.restoreFromSnapshot to application.gateway.invokeTool;
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

    requirement <'contract.vellis.mcp.gateway_projection'> mcpGatewayProjection {
        subject adapter : VellisMcpAdapter;
        require constraint {
            doc /* The transport adapter obtains its curated registrations from and dispatches every tool through the retained generic MCP gateway; it retains no Vellis facade, RTG controller, or domain implementation role. */
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
            doc /* Every expected or unexpected action failure returns {ok:false,error:{type,message,diagnostic?}} rather than a transport failure. type preserves the concrete failure name. Controller validation failures additionally expose top-level validation_report when present on the source failure. Runtime message and trace identity remain runtime envelope/history metadata. Failure encoding adds no domain state effect. */
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
        satisfy mcpGatewayProjection by adapter;
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
        objective { verify mcpDescriptionAuthority; verify mcpGatewayProjection; verify mcpInputEncoding; verify mcpResultEncoding; verify mcpFailureEncoding; verify mcpTransportEquivalence; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp.py#VellisMcpBoundaryVerification"; implementationScope = "VellisMcpPython"; }
    }
}
