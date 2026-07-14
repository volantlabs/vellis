# Vellis application model reference

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

## Application composition

| Application role | Bibliotek component |
|---|---|
| `documentStorage` | `component.storage.json_file` |
| `ledgerStorage` | `component.storage.sql` |
| `graphStore` | `component.rtg.graph` |
| `schemaRegistry` | `component.rtg.schema` |
| `constraintRegistry` | `component.rtg.constraints` |
| `migrationStore` | `component.rtg.migration` |
| `queryEngine` | `component.rtg.query` |
| `changeValidator` | `component.rtg.change_validation` |
| `controller` | `component.rtg.controller` |

## Personal Launcher composition

| Personal Launcher role | Logical type | Provider |
|---|---|---|
| `catalog` | `AppCatalog` | `component.app.catalog` |
| `runtimeAdapter` | `RuntimeAdapter` | `external runtime capability` |
| `launcher` | `AppLauncher` | `component.app.launcher` |
| `shell` | `AppShell` | `component.app.shell` |

## Everyday Life starter ontology

Ontology `ontology.vellis.everyday_life` version `1` is generated as schema-only bootstrap material. It contains no people, tasks, or other graph facts.

| Anchor | Required facts | Fields |
|---|---|---|
| `Person` | `PersonFacts` | `name` (required), `relationship`, `preferred_contact`, `notes` |
| `Group` | `GroupFacts` | `name` (required), `kind`, `description` |
| `Area` | `AreaFacts` | `title` (required), `domain`, `focus`, `active` |
| `Goal` | `GoalFacts` | `title` (required), `domain`, `status`, `priority`, `target_date`, `desired_outcome` |
| `Project` | `ProjectFacts` | `title` (required), `domain`, `status`, `priority`, `desired_outcome`, `next_review` |
| `Task` | `TaskFacts` | `title` (required), `domain`, `status`, `priority`, `due`, `context` |
| `Event` | `EventFacts` | `title` (required), `domain`, `status`, `start`, `end`, `summary` |
| `Routine` | `RoutineFacts` | `title` (required), `domain`, `cadence`, `active`, `next_due`, `context` |
| `Decision` | `DecisionFacts` | `title` (required), `domain`, `status`, `decided_on`, `rationale` |
| `Note` | `NoteFacts` | `title` (required), `domain`, `topic`, `summary`, `captured_at` |
| `Resource` | `ResourceFacts` | `title` (required), `domain`, `kind`, `locator`, `summary` |
| `Place` | `PlaceFacts` | `name` (required), `kind`, `address`, `notes` |

| Link | Allowed sources | Allowed targets |
|---|---|---|
| `belongs_to` | `Goal`, `Project`, `Task`, `Event`, `Routine`, `Decision`, `Note`, `Resource` | `Area` |
| `supports` | `Project`, `Task`, `Event`, `Routine`, `Decision`, `Note`, `Resource` | `Goal`, `Project` |
| `responsible_for` | `Person`, `Group` | `Area`, `Goal`, `Project`, `Task`, `Event`, `Routine` |
| `member_of` | `Person` | `Group` |
| `involves` | `Goal`, `Project`, `Task`, `Event`, `Routine`, `Decision` | `Person`, `Group` |
| `located_at` | `Task`, `Event`, `Routine`, `Group` | `Place` |
| `documents` | `Note`, `Resource` | `Person`, `Group`, `Area`, `Goal`, `Project`, `Task`, `Event`, `Routine`, `Decision`, `Note`, `Resource`, `Place` |
| `mentions` | `Note` | `Person`, `Group`, `Area`, `Goal`, `Project`, `Task`, `Event`, `Routine`, `Decision`, `Note`, `Resource`, `Place` |
| `depends_on` | `Goal`, `Project`, `Task` | `Goal`, `Project`, `Task` |

## Actor-visible use cases

| Actor-visible use case | Objective | Realized application actions |
|---|---|---|
| `BootstrapAndEvolveSchema` | Establish or evolve a validated live schema for subsequent knowledge work. | `inspectState: RtgGetSystemState`, `stageSchema: RtgStageSchemaMigration`, `cutover: RtgApplyMigrationCutover` |
| `ValidateAndApplyLiveKnowledge` | Validate and apply ordinary live knowledge without weakening schema or constraints. | `validate: RtgValidateLiveGraphChanges`, `apply: RtgApplyLiveGraphChanges` |
| `StageAndCutoverKnowledge` | Stage migration-scoped knowledge work and make it live through an explicit cutover. | `stage: RtgStageKnowledgeChanges`, `cutover: RtgApplyMigrationCutover` |
| `QueryAndDiscoverKnowledge` | Discover relevant schema and answer a graph question without mutation. | `discover: RtgDiscoverAnchorTypes`, `inspectSchema: RtgGetSchemaPack`, `query: RtgExecuteQuery` |
| `SnapshotAndRestoreSystem` | Persist, inspect, and restore a coordinated system snapshot. | `persist: RtgPersistSystemSnapshot`, `load: RtgLoadPersistedSnapshot`, `restore: RtgRestoreFromSnapshot` |
| `AuditAndReplayActivity` | Inspect durable activity and prove that replay reconstructs the expected state. | `history: RtgListMigrationHistory`, `verifyReplay: RtgVerifyReplayFromLedger` |
| `InspectStateAndGuidance` | Determine current system posture and the appropriate next workflow. | `state: RtgGetSystemState`, `guide: RtgGetUsageGuide` |
| `AbandonStagedWork` | Remove safe non-live staged work while preserving all live state. | `abandon: RtgAbandonMigration` |

## Python realization

| Application role | Logical type | Python realization | Implementation symbol |
|---|---|---|---|
| `documentStorage` | `JsonFileStorage` | `LocalJsonFileStorage` | `components.storage.json_file.LocalJsonFileStorage` |
| `ledgerStorage` | `SqlStorage` | `SqliteStorage` | `components.storage.sql.SqliteStorage` |
| `graphStore` | `RtgGraph` | `InMemoryRtgGraph` | `components.rtg.graph.InMemoryRtgGraph` |
| `schemaRegistry` | `RtgSchema` | `InMemoryRtgSchema` | `components.rtg.schema.InMemoryRtgSchema` |
| `constraintRegistry` | `RtgConstraints` | `InMemoryRtgConstraints` | `components.rtg.constraints.InMemoryRtgConstraints` |
| `migrationStore` | `RtgMigration` | `InMemoryRtgMigration` | `components.rtg.migration.InMemoryRtgMigration` |
| `queryEngine` | `RtgQueryEngine` | `SimpleRtgQueryEngine` | `components.rtg.query.SimpleRtgQueryEngine` |
| `changeValidator` | `RtgChangeValidator` | `DeterministicRtgChangeValidator` | `components.rtg.change_validation.DeterministicRtgChangeValidator` |
| `controller` | `RtgController` | `InProcessRtgController` | `components.rtg.controller.InProcessRtgController` |
| `facade` | `VellisApplicationFacade` | `PythonVellisFacade` | `apps.rtg_knowledge_graph.mcp_toolset.RtgMcpToolset` |
| `starterOntologyInstaller` | `EverydayLifeOntologyInstaller` | `PythonEverydayLifeOntologyInstaller` | `apps.rtg_knowledge_graph.starter_schema.install_everyday_life_ontology` |

## Personal Launcher Python realization

| Personal Launcher role | Logical type | Python realization | Implementation symbol |
|---|---|---|---|
| `catalog` | `Bibliotek component realization` | `InMemoryAppCatalog` | `See Bibliotek Python realization` |
| `runtimeAdapter` | `RuntimeAdapter` | `PythonDesktopRuntimeAdapter` | `apps.personal_launcher.runtime.DesktopRuntimeAdapter` |
| `launcher` | `Bibliotek component realization` | `InMemoryAppLauncher` | `See Bibliotek Python realization` |
| `shell` | `Bibliotek component realization` | `InMemoryAppShell` | `See Bibliotek Python realization` |

## Requirements and satisfaction

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `invariant.vellis.bibliotek_public_contracts_only` | `VellisApplication` | `application` | Vellis consumes Bibliotek roles only through modeled public contracts. |
| `invariant.vellis.discovery_draft_unbound` | `VellisApplication` | `application` | The draft curated discovery component is not part of the current application. |
| `invariant.vellis.transport_outside_controller` | `VellisApplication` | `application` | MCP transport and app shaping remain outside the RTG controller. |
| `invariant.vellis.personal_launcher.public_contracts_only` | `PersonalLauncherApplication` | `application` | The launcher composes catalog, launcher, shell, and runtime roles only through their modeled public contracts. |
| `invariant.vellis.personal_launcher.truthful_activity` | `PersonalLauncherApplication` | `application` | Managed runtime surfaces produce launcher-owned sessions; handed-off or already completed surfaces produce bounded recent activity without false runtime ownership. |
| `invariant.vellis.personal_launcher.current_defaults` | `PersonalLauncherApplication` | `application` | Built-in repository-local catalog entries name only surfaces available in the current Vellis distribution; optional applications enter through explicit catalog records when installed. |
| `invariant.vellis.personal_launcher.transport_outside_components` | `PersonalLauncherApplication` | `application` | HTTP serving, browser opening, and desktop-wrapper installation remain application adapters and do not enter reusable component contracts. |
| `contract.vellis.facade.failures` | `VellisApplicationFacade` | `facade` | Input decoding rejects unknown fields, wrong JSON kinds, invalid enum literals, missing required values, and contradictory option shapes as VellisRequestInvalid before controller invocation. Modeled Bibliotek failures propagate without changing their concrete type, message, diagnostic, transaction identity, or validation evidence. |
| `contract.vellis.facade.implementation_freedom` | `VellisApplicationFacade` | `facade` | The facade may choose any implementation language or helper decomposition but must preserve the modeled request compilation, controller invocation, response shaping, defaults, ordering, and no-effect guarantees. |
| `contract.vellis.facade.usage_guides` | `RtgGetUsageGuide` | `facade.rtgGetUsageGuide` | The fifteen guide topics cover: the installed Everyday Life schema; safe RTG schema design and evolution; compact machine-readable tool capabilities; MCP bootstrap sequence; concise operator rules; state-driven workflows; ordinary-request-to-workflow mapping; minimal schema staging; exact top-level tool shapes; live writes; identity lookup before links; query construction; snapshot/restore/replay recovery; durable migration history; and safe abandonment. Generic examples do not silently replace or specialize an application's modeled schema. |
| `contract.vellis.facade.schema_migration_compilation` | `RtgStageSchemaMigration` | `facade.rtgStageSchemaMigration` | Each unique kind-and-typeKey request becomes one newly identified non-live schema write and one schema_make_live member; duplicate request keys are rejected before controller invocation. generatedSchemaIds maps kind:type_key to that UUID. Each retirement selector must resolve to exactly one live definition and becomes schema_make_non_live. One ready migration with the supplied ID and description owns the membership. Compact response is default and full response adds the exact submitted batch; shaping has no mutation effect. |
| `contract.vellis.facade.anchor_record_compilation` | `VellisApplicationFacade` | `facade` | Each anchor record becomes one canonical anchor write. Each nested fact becomes one data-object write associated to that anchor; an omitted fact reference receives a unique request-local reference reported in generatedRefs. Link writes pass through unchanged. Validation and apply use identical compilation. Apply returns every resolved local-reference UUID; compact is default and full additionally returns the exact submitted graph changes. |
| `contract.vellis.facade.query_semantics` | `VellisApplicationFacade` | `facade` | Full query responses preserve the canonical query result. properties_only retains final row order, pagination metadata, and diagnostics while omitting bindings and unrequested records; non-aggregate rows contain row_index plus selected properties, while aggregate rows preserve row_index, group_by, and caller-named aggregation values. Anchor resolution compiles one live-only equality query and returns every deterministic match without guessing uniqueness. |
| `contract.vellis.facade.snapshot_semantics` | `VellisApplicationFacade` | `facade` | Full export returns the canonical snapshot; summary export returns snapshot_exported and compact counts/pointers. Persist and load always add compact summary and relative path, and return_snapshot=false removes only the full snapshot payload. No response shaping changes stored or current state. |
| `contract.vellis.facade.controller_forwarding` | `VellisApplicationFacade` | `facade` | Actions not identified as compilation or shaping workflows decode their modeled inputs, invoke exactly the satisfied controller capability once, and encode the modeled result without adding state, filtering, retries, ordering, or lifecycle policy. |
| `contract.vellis.facade.rtg_get_system_state.failures` | `RtgGetSystemState` | `facade.rtgGetSystemState` | Failure is encoded without changing controller or application state. |
| `contract.vellis.facade.rtg_get_usage_guide.failures` | `RtgGetUsageGuide` | `facade.rtgGetUsageGuide` | Unknown topics return a typed input failure and have no effect. |
| `contract.vellis.facade.rtg_stage_schema_migration.failures` | `RtgStageSchemaMigration` | `facade.rtgStageSchemaMigration` | Invalid shaping or retirement selection has no staging effect; downstream controller atomicity applies after submission. |
| `contract.vellis.facade.rtg_validate_live_anchor_records.failures` | `RtgValidateLiveAnchorRecords` | `facade.rtgValidateLiveAnchorRecords` | Compilation or validation failure has no component or ledger effect. |
| `contract.vellis.facade.rtg_apply_live_anchor_records.failures` | `RtgApplyLiveAnchorRecords` | `facade.rtgApplyLiveAnchorRecords` | Compilation failure has no effect; controller atomicity governs submitted mutations. |
| `contract.vellis.facade.rtg_validate_live_graph_changes.failures` | `RtgValidateLiveGraphChanges` | `facade.rtgValidateLiveGraphChanges` | The dry-run never mutates component or ledger state. |
| `contract.vellis.facade.rtg_apply_live_graph_changes.failures` | `RtgApplyLiveGraphChanges` | `facade.rtgApplyLiveGraphChanges` | The facade adds no mutation outside the controller lane. |
| `contract.vellis.facade.rtg_stage_knowledge_changes.failures` | `RtgStageKnowledgeChanges` | `facade.rtgStageKnowledgeChanges` | The facade preserves controller validation and rollback behavior. |
| `contract.vellis.facade.rtg_apply_migration_cutover.failures` | `RtgApplyMigrationCutover` | `facade.rtgApplyMigrationCutover` | The facade does not weaken cutover restoration or ledger semantics. |
| `contract.vellis.facade.rtg_abandon_migration.failures` | `RtgAbandonMigration` | `facade.rtgAbandonMigration` | Failure preserves controller abandonment guarantees. |
| `contract.vellis.facade.rtg_execute_query.failures` | `RtgExecuteQuery` | `facade.rtgExecuteQuery` | Query and shaping failures have no state or ledger effect. |
| `contract.vellis.facade.rtg_resolve_anchor_by_fact.failures` | `RtgResolveAnchorByFact` | `facade.rtgResolveAnchorByFact` | Resolution is read-only and never guesses an identity. |
| `contract.vellis.facade.rtg_get_object.failures` | `RtgGetObject` | `facade.rtgGetObject` | Failure has no state or ledger effect. |
| `contract.vellis.facade.rtg_list_migrations.failures` | `RtgListMigrations` | `facade.rtgListMigrations` | Failure has no state or ledger effect. |
| `contract.vellis.facade.rtg_get_migration.failures` | `RtgGetMigration` | `facade.rtgGetMigration` | Failure has no state or ledger effect. |
| `contract.vellis.facade.rtg_validate_graph.failures` | `RtgValidateGraph` | `facade.rtgValidateGraph` | Blocking findings are returned in a report; only unusable input or execution raises, and no state changes. |
| `contract.vellis.facade.rtg_discover_anchor_types.failures` | `RtgDiscoverAnchorTypes` | `facade.rtgDiscoverAnchorTypes` | Discovery is read-only. |
| `contract.vellis.facade.rtg_get_schema_pack.failures` | `RtgGetSchemaPack` | `facade.rtgGetSchemaPack` | Schema-pack reads have no effect. |
| `contract.vellis.facade.rtg_export_system_snapshot.failures` | `RtgExportSystemSnapshot` | `facade.rtgExportSystemSnapshot` | Export has no state or ledger effect. |
| `contract.vellis.facade.rtg_persist_system_snapshot.failures` | `RtgPersistSystemSnapshot` | `facade.rtgPersistSystemSnapshot` | Failure exposes no partial JSON document. |
| `contract.vellis.facade.rtg_list_persisted_snapshots.failures` | `RtgListPersistedSnapshots` | `facade.rtgListPersistedSnapshots` | Listing is read-only. |
| `contract.vellis.facade.rtg_load_persisted_snapshot.failures` | `RtgLoadPersistedSnapshot` | `facade.rtgLoadPersistedSnapshot` | Loading has no current-state effect. |
| `contract.vellis.facade.rtg_replay_ledger.failures` | `RtgReplayLedger` | `facade.rtgReplayLedger` | Rejected replay inputs expose no partial reconstructed state. |
| `contract.vellis.facade.rtg_verify_replay_from_ledger.failures` | `RtgVerifyReplayFromLedger` | `facade.rtgVerifyReplayFromLedger` | Verification leaves current state and source ledger unchanged. |
| `contract.vellis.facade.rtg_list_migration_history.failures` | `RtgListMigrationHistory` | `facade.rtgListMigrationHistory` | History inspection is read-only. |
| `contract.vellis.facade.rtg_flush_ledger_failures.failures` | `RtgFlushLedgerFailures` | `facade.rtgFlushLedgerFailures` | Unflushed records remain queued and legible. |
| `contract.vellis.facade.rtg_restore_from_snapshot.failures` | `RtgRestoreFromSnapshot` | `facade.rtgRestoreFromSnapshot` | Failure exposes no partially restored state. |
| `contract.vellis.mcp.outcome_exclusive` | `VellisMcpOutcome` | `outcome` | Formal modeled predicate. |
| `contract.vellis.mcp.description_authority` | `VellisMcpAdapter` | `adapter` | Each MCP-bound adapter action documents one concise purpose/lane/safety description and standard read-only, destructive, idempotent, and closed-world hints. Detailed request grammar and examples are available through usage guides. Logical Vellis action documentation remains the semantic contract; generated runtime metadata carries the realization description without a second Python authority. |
| `contract.vellis.mcp.input_encoding` | `VellisMcpAdapter` | `adapter` | MCP arguments use the exact lower_snake_case action input names. Required inputs must be present; omitted optional inputs use modeled defaults. JSON arrays that realize typed list values encode directly as arrays. Decoding rejects unknown fields, wrong kinds, unsupported enum literals, empty required strings/lists, and contradictory option shapes before invoking the action. |
| `contract.vellis.mcp.result_encoding` | `VellisMcpAdapter` | `adapter` | Every successful action returns exactly {ok:true,result:<lower_snake_case JSON encoding of the modeled action result>}. The usage-guide codec preserves its typed topic and flattens its content fields beside topic for established-wire compatibility. Result shaping defined by the Vellis action occurs before this envelope and the adapter adds no other domain behavior. For current Python result records, an absent optional RtgDiagnostic encodes as an empty JSON object; failure envelopes instead omit an absent diagnostic. |
| `contract.vellis.mcp.failure_encoding` | `VellisMcpAdapter` | `adapter` | Every expected or unexpected action failure returns {ok:false,error:{type,message,diagnostic?}} rather than a transport failure. type preserves the concrete failure name. Controller validation failures additionally expose top-level transaction_id and validation_report when present on the source failure. Failure encoding adds no state effect. |
| `contract.vellis.mcp.transport_equivalence` | `VellisMcpAdapter` | `adapter` | The exact same 27 tool contracts, descriptions, argument schemas, results, and failure envelopes are exposed over stdio and localhost HTTP; transport selection does not alter application semantics. |

## Verification closure

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `VellisCompositionVerification` | `VellisApplication` | `bibliotekOnlyThroughContracts`, `discoveryDraftUnbound`, `transportOutsideController` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_app.py#VellisCompositionVerification` |
| `PersonalLauncherCompositionVerification` | `PersonalLauncherApplication` | `publicContractsOnly`, `truthfulActivity`, `currentDefaults`, `transportOutsideComponents` | `apps/personal_launcher/tests/test_personal_launcher_app.py#PersonalLauncherCompositionVerification` |
| `RtgGetUsageGuideContractVerification` | `RtgGetUsageGuide` | `usageGuideSemantics`, `rtgGetUsageGuideFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgGetUsageGuideContractVerification` |
| `RtgStageSchemaMigrationContractVerification` | `RtgStageSchemaMigration` | `schemaMigrationCompilation`, `rtgStageSchemaMigrationFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgStageSchemaMigrationContractVerification` |
| `RtgGetSystemStateContractVerification` | `RtgGetSystemState` | `rtgGetSystemStateFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgGetSystemStateContractVerification` |
| `RtgValidateLiveAnchorRecordsContractVerification` | `RtgValidateLiveAnchorRecords` | `rtgValidateLiveAnchorRecordsFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgValidateLiveAnchorRecordsContractVerification` |
| `RtgApplyLiveAnchorRecordsContractVerification` | `RtgApplyLiveAnchorRecords` | `rtgApplyLiveAnchorRecordsFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgApplyLiveAnchorRecordsContractVerification` |
| `RtgValidateLiveGraphChangesContractVerification` | `RtgValidateLiveGraphChanges` | `rtgValidateLiveGraphChangesFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgValidateLiveGraphChangesContractVerification` |
| `RtgApplyLiveGraphChangesContractVerification` | `RtgApplyLiveGraphChanges` | `rtgApplyLiveGraphChangesFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgApplyLiveGraphChangesContractVerification` |
| `RtgStageKnowledgeChangesContractVerification` | `RtgStageKnowledgeChanges` | `rtgStageKnowledgeChangesFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgStageKnowledgeChangesContractVerification` |
| `RtgApplyMigrationCutoverContractVerification` | `RtgApplyMigrationCutover` | `rtgApplyMigrationCutoverFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgApplyMigrationCutoverContractVerification` |
| `RtgAbandonMigrationContractVerification` | `RtgAbandonMigration` | `rtgAbandonMigrationFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgAbandonMigrationContractVerification` |
| `RtgExecuteQueryContractVerification` | `RtgExecuteQuery` | `rtgExecuteQueryFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgExecuteQueryContractVerification` |
| `RtgResolveAnchorByFactContractVerification` | `RtgResolveAnchorByFact` | `rtgResolveAnchorByFactFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgResolveAnchorByFactContractVerification` |
| `RtgGetObjectContractVerification` | `RtgGetObject` | `rtgGetObjectFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgGetObjectContractVerification` |
| `RtgListMigrationsContractVerification` | `RtgListMigrations` | `rtgListMigrationsFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgListMigrationsContractVerification` |
| `RtgGetMigrationContractVerification` | `RtgGetMigration` | `rtgGetMigrationFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgGetMigrationContractVerification` |
| `RtgValidateGraphContractVerification` | `RtgValidateGraph` | `rtgValidateGraphFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgValidateGraphContractVerification` |
| `RtgDiscoverAnchorTypesContractVerification` | `RtgDiscoverAnchorTypes` | `rtgDiscoverAnchorTypesFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgDiscoverAnchorTypesContractVerification` |
| `RtgGetSchemaPackContractVerification` | `RtgGetSchemaPack` | `rtgGetSchemaPackFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgGetSchemaPackContractVerification` |
| `RtgExportSystemSnapshotContractVerification` | `RtgExportSystemSnapshot` | `rtgExportSystemSnapshotFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgExportSystemSnapshotContractVerification` |
| `RtgPersistSystemSnapshotContractVerification` | `RtgPersistSystemSnapshot` | `rtgPersistSystemSnapshotFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgPersistSystemSnapshotContractVerification` |
| `RtgListPersistedSnapshotsContractVerification` | `RtgListPersistedSnapshots` | `rtgListPersistedSnapshotsFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgListPersistedSnapshotsContractVerification` |
| `RtgLoadPersistedSnapshotContractVerification` | `RtgLoadPersistedSnapshot` | `rtgLoadPersistedSnapshotFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgLoadPersistedSnapshotContractVerification` |
| `RtgReplayLedgerContractVerification` | `RtgReplayLedger` | `rtgReplayLedgerFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgReplayLedgerContractVerification` |
| `RtgVerifyReplayFromLedgerContractVerification` | `RtgVerifyReplayFromLedger` | `rtgVerifyReplayFromLedgerFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgVerifyReplayFromLedgerContractVerification` |
| `RtgListMigrationHistoryContractVerification` | `RtgListMigrationHistory` | `rtgListMigrationHistoryFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgListMigrationHistoryContractVerification` |
| `RtgFlushLedgerFailuresContractVerification` | `RtgFlushLedgerFailures` | `rtgFlushLedgerFailuresFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgFlushLedgerFailuresContractVerification` |
| `RtgRestoreFromSnapshotContractVerification` | `RtgRestoreFromSnapshot` | `rtgRestoreFromSnapshotFailureSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#RtgRestoreFromSnapshotContractVerification` |
| `VellisFacadeBoundaryVerification` | `VellisApplicationFacade` | `facadeFailureSemantics`, `facadeFreedom`, `anchorRecordCompilation`, `queryFacadeSemantics`, `snapshotFacadeSemantics`, `controllerForwardingSemantics` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp_user_flows.py#VellisFacadeBoundaryVerification` |
| `VellisMcpOutcomeContractVerification` | `VellisMcpOutcome` | `mcpOutcomeExclusive` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp.py#VellisMcpOutcomeContractVerification` |
| `VellisMcpBoundaryVerification` | `VellisMcpAdapter` | `mcpDescriptionAuthority`, `mcpInputEncoding`, `mcpResultEncoding`, `mcpFailureEncoding`, `mcpTransportEquivalence` | `apps/rtg_knowledge_graph/tests/test_rtg_knowledge_graph_mcp.py#VellisMcpBoundaryVerification` |

## Façade and transport mappings

Successful MCP calls encode as `{ok: true, result: <encoded action result>}`. Failures encode as `{ok: false, error: {type, message, diagnostic?}}`; controller validation failures also expose `transaction_id` and `validation_report` when present.

| # | Tool | Façade / controller realization | Signature | Principal failures | Outcome |
|---:|---|---|---|---|---|
| 1 | `rtg_get_system_state` | `rtgGetSystemState` → `GetSystemState` → `getSystemState` | out `result: VellisSystemState[1]` | `VellisRequestInvalid`, `RtgControllerDiscoveryFailed` | Return state classification, counts, ledger pointers, and recommended next steps. |
| 2 | `rtg_get_usage_guide` | `rtgGetUsageGuide` → `application-local` → `getUsageGuide` | in `topic: VellisUsageGuideTopic[1]`; out `result: VellisUsageGuide[1]` | `VellisRequestInvalid` | Return MCP-accessible workflow guidance and complete generic request examples for exactly one declared topic; it does not invent domain schema. |
| 3 | `rtg_stage_schema_migration` | `rtgStageSchemaMigration` → `ExportSystemSnapshot`, `StageKnowledgeChanges` → `stageSchemaMigration` | in `migration_id: String[1]`; in `description: String[1]`; in `schema_definitions: VellisSchemaDefinitionRequestList[1]`; in `retire_live_schema: VellisSchemaRetirementList[0..1]`; in `validation_mode: RtgControllerValidationMode[0..1]` = `RtgControllerValidationMode::strict`; in `response_options: VellisMutationResponseOptions[0..1]`; out `result: VellisSchemaMigrationResult[1]` | `VellisRequestInvalid`, `RtgControllerValidationFailed`, `RtgControllerPreconditionFailed`, `RtgControllerApplyFailed` | Generate a UUID for each schema candidate, force each candidate non-live, resolve each retirement to exactly one live definition, create a ready migration whose membership covers those candidates, and submit canonical staged knowledge changes. Compact is the default and omits submittedKnowledgeChanges; full adds exactly the submitted batch without changing the operation. |
| 4 | `rtg_validate_live_anchor_records` | `rtgValidateLiveAnchorRecords` → `ValidateLiveGraphChanges` → `validateLiveAnchorRecords` | in `anchor_records: VellisAnchorRecordList[1]`; in `link_writes: RtgGraphLinkWriteList[0..1]`; in `validation_options: RtgControllerValidationOptions[0..1]`; out `result: VellisAnchorValidationResult[1]` | `VellisRequestInvalid`, `RtgControllerPreconditionFailed`, `RtgValidationInputInvalid` | Compile each anchor and nested fact into canonical writes, generate deterministic request-local fact references where omitted, pass through canonical link writes, and return compiled changes plus validation without mutation or ledger writes. |
| 5 | `rtg_apply_live_anchor_records` | `rtgApplyLiveAnchorRecords` → `ApplyLiveGraphChanges` → `applyLiveAnchorRecords` | in `anchor_records: VellisAnchorRecordList[1]`; in `link_writes: RtgGraphLinkWriteList[0..1]`; in `validation_mode: RtgControllerValidationMode[0..1]` = `RtgControllerValidationMode::strict`; in `response_options: VellisMutationResponseOptions[0..1]`; out `result: VellisAnchorApplyResult[1]` | `VellisRequestInvalid`, `RtgControllerValidationFailed`, `RtgControllerApplyFailed` | Compile anchor-with-facts input identically to validation and apply it once through the controller. Compact is the default and returns all generated local-reference UUIDs plus generated fact references while omitting submittedGraphChanges; full adds exactly the submitted graph changes without changing the operation. |
| 6 | `rtg_validate_live_graph_changes` | `rtgValidateLiveGraphChanges` → `ValidateLiveGraphChanges` → `validateLiveGraphChanges` | in `graph_changes: RtgGraphChangeSet[1]`; in `validation_options: RtgControllerValidationOptions[0..1]`; out `result: RtgControllerLiveGraphValidationResult[1]` | `VellisRequestInvalid`, `RtgControllerPreconditionFailed`, `RtgValidationInputInvalid` | Validate normal live graph CRUD without mutation or ledger writes. |
| 7 | `rtg_apply_live_graph_changes` | `rtgApplyLiveGraphChanges` → `ApplyLiveGraphChanges` → `applyLiveGraphChanges` | in `graph_changes: RtgGraphChangeSet[1]`; in `validation_mode: RtgControllerValidationMode[0..1]` = `RtgControllerValidationMode::strict`; out `result: RtgControllerOperationResult[1]` | `VellisRequestInvalid`, `RtgControllerValidationFailed`, `RtgControllerApplyFailed` | Apply normal live graph CRUD through strict controller policy by default. |
| 8 | `rtg_stage_knowledge_changes` | `rtgStageKnowledgeChanges` → `StageKnowledgeChanges` → `stageKnowledgeChanges` | in `knowledge_changes: RtgChangeBatch[1]`; in `validation_mode: RtgControllerValidationMode[0..1]` = `RtgControllerValidationMode::strict`; out `result: RtgControllerOperationResult[1]` | `VellisRequestInvalid`, `RtgControllerValidationFailed`, `RtgControllerPreconditionFailed`, `RtgControllerApplyFailed` | Stage advanced normalized migration-scoped knowledge changes. |
| 9 | `rtg_apply_migration_cutover` | `rtgApplyMigrationCutover` → `ApplyMigrationCutover` → `applyMigrationCutover` | in `migration_id: String[1]`; in `cutover_options: RtgControllerCutoverOptions[0..1]`; out `result: RtgControllerOperationResult[1]` | `VellisRequestInvalid`, `RtgControllerValidationFailed`, `RtgControllerPreconditionFailed`, `RtgControllerApplyFailed` | Apply the selected migration cutover with validation and failure restoration. |
| 10 | `rtg_abandon_migration` | `rtgAbandonMigration` → `AbandonMigration` → `abandonMigration` | in `migration_id: String[1]`; in `reason: String[0..1]`; out `result: RtgControllerOperationResult[1]` | `VellisRequestInvalid`, `RtgControllerPreconditionFailed`, `RtgControllerApplyFailed` | Abandon safe non-live staged work without deleting live records. |
| 11 | `rtg_execute_query` | `rtgExecuteQuery` → `ExecuteControllerQuery` → `executeQuery` | in `query_spec: RtgQuerySpec[1]`; in `query_options: RtgQueryOptions[0..1]`; in `response_options: VellisQueryResponseOptions[0..1]`; out `result: VellisQueryResponse[1]` | `VellisRequestInvalid`, `RtgQuerySpecInvalid`, `RtgQueryUnsupported` | Execute the canonical read-only query. full returns RtgQueryResult unchanged. properties_only returns pagination metadata and diagnostics plus either row_index with requested properties for non-aggregate queries or canonical aggregation rows for aggregate queries, adding empty-return-property guidance when appropriate. |
| 12 | `rtg_resolve_anchor_by_fact` | `rtgResolveAnchorByFact` → `ExecuteControllerQuery` → `resolveAnchorByFact` | in `anchor_type: String[1]`; in `data_type: String[1]`; in `property_path: StringList[1]`; in `value: JsonValue[1]`; in `case_sensitive: Boolean[0..1]` = `false`; out `result: VellisAnchorResolutionResult[1]` | `VellisRequestInvalid`, `RtgQuerySpecInvalid`, `RtgQueryUnsupported` | Build one live-only anchor-plus-associated-data equality query, return resolved status, deterministic matches with resource IDs and selected properties, the submitted query/options, query diagnostics, and guidance that distinguishes zero, one, and multiple matches. |
| 13 | `rtg_get_object` | `rtgGetObject` → `ControllerGetObject` → `getObject` | in `object_uuid: String[1]`; out `result: RtgObject[1]` | `VellisRequestInvalid`, `RtgControllerObjectNotFound` | Return one graph object by UUID without lifecycle filtering or mutation. |
| 14 | `rtg_list_migrations` | `rtgListMigrations` → `ControllerListMigrations` → `listMigrations` | in `status: RtgMigrationStatus[0..1]`; out `result: RtgMigrationRecordList[1]` | `VellisRequestInvalid`, `RtgMigrationStatusInvalid` | Return every current migration, or one status, in deterministic migration-ID order. |
| 15 | `rtg_get_migration` | `rtgGetMigration` → `ControllerGetMigration` → `getMigration` | in `migration_id: String[1]`; out `result: RtgMigrationRecord[1]` | `VellisRequestInvalid`, `RtgMigrationNotFound` | Return one current migration record by stable migration ID. |
| 16 | `rtg_validate_graph` | `rtgValidateGraph` → `ValidateGraph` → `validateGraph` | in `migration_ids: StringList[0..1]`; in `validation_options: RtgControllerValidationOptions[0..1]`; out `result: RtgValidationReport[1]` | `VellisRequestInvalid`, `RtgControllerValidationFailed` | Validate current or migration-projected state without mutation. |
| 17 | `rtg_discover_anchor_types` | `rtgDiscoverAnchorTypes` → `DiscoverAnchorTypes` → `discoverAnchorTypes` | in `discovery_options: RtgControllerDiscoveryOptions[0..1]`; out `result: RtgAnchorTypeDiscoveryResult[1]` | `VellisRequestInvalid`, `RtgControllerDiscoveryFailed` | Return schema type keys, descriptions, and live counts; exclude non-live types by default and honor a positive optional limit. |
| 18 | `rtg_get_schema_pack` | `rtgGetSchemaPack` → `GetControllerSchemaPack` → `getSchemaPack` | in `anchor_type_keys: StringList[1]`; in `schema_pack_options: RtgControllerSchemaPackOptions[0..1]`; out `result: RtgControllerSchemaPack[1]` | `VellisRequestInvalid`, `RtgControllerDiscoveryFailed` | Return selected anchor schemas, associated-data schemas, participating link schemas, and requested live counts. |
| 19 | `rtg_export_system_snapshot` | `rtgExportSystemSnapshot` → `ExportSystemSnapshot` → `exportSystemSnapshot` | in `summary: Boolean[0..1]` = `false`; out `result: VellisSnapshotExport[1]` | `RtgControllerSnapshotFailed` | Return the full coordinated snapshot when summary is false; otherwise return snapshot_exported plus compact component counts and ledger pointers. |
| 20 | `rtg_persist_system_snapshot` | `rtgPersistSystemSnapshot` → `PersistSystemSnapshot` → `persistSystemSnapshot` | in `relative_path: JsonRelativePath[1]`; in `return_snapshot: Boolean[0..1]` = `true`; out `result: VellisPersistedSnapshotResult[1]` | `VellisRequestInvalid`, `RtgControllerSnapshotFailed`, `RtgControllerApplyFailed` | Persist a coordinated snapshot, add relative path and compact summary to the controller result, and omit the full snapshot only when requested. |
| 21 | `rtg_list_persisted_snapshots` | `rtgListPersistedSnapshots` → `ListPersistedSnapshots` → `listPersistedSnapshots` | out `result: RtgPersistedSnapshotList[1]` | `RtgControllerSnapshotFailed` | List only persisted snapshot-like documents visible through the configured JSON storage root. |
| 22 | `rtg_load_persisted_snapshot` | `rtgLoadPersistedSnapshot` → `LoadPersistedSnapshot` → `loadPersistedSnapshot` | in `relative_path: JsonRelativePath[1]`; in `return_snapshot: Boolean[0..1]` = `true`; out `result: VellisLoadedSnapshotResult[1]` | `VellisRequestInvalid`, `RtgControllerSnapshotFailed` | Load and validate one persisted snapshot, always return path and compact summary, and omit the full snapshot only when requested; do not apply it. |
| 23 | `rtg_replay_ledger` | `rtgReplayLedger` → `ReplayLedger` → `replayLedger` | in `replay_options: RtgControllerReplayOptions[0..1]`; out `result: RtgControllerOperationResult[1]` | `VellisRequestInvalid`, `RtgControllerReplayFailed` | Reconstruct state from an empty or explicit snapshot seed using the selected ascending ledger window. |
| 24 | `rtg_verify_replay_from_ledger` | `rtgVerifyReplayFromLedger` → `VerifyReplayFromLedger` → `verifyReplay` | in `replay_options: RtgControllerReplayOptions[0..1]`; out `result: RtgControllerReplayVerificationResult[1]` | `VellisRequestInvalid`, `RtgControllerReplayFailed` | Replay into isolated state and return summaries, count differences, replay window, and validation without replacing current state. |
| 25 | `rtg_list_migration_history` | `rtgListMigrationHistory` → `ListMigrationHistory` → `listMigrationHistory` | out `result: RtgControllerMigrationHistory[1]` | `RtgControllerReplayFailed` | Return ledger-backed staged, staging-rejected, staging-failed, cutover-applied, cutover-failed, and abandoned events in ledger order. |
| 26 | `rtg_flush_ledger_failures` | `rtgFlushLedgerFailures` → `FlushLedgerFailures` → `flushLedgerFailures` | out `result: RtgControllerOperationResult[1]` | `RtgControllerApplyFailed` | Retry queued audit records in original order and report remaining degraded-audit state. |
| 27 | `rtg_restore_from_snapshot` | `rtgRestoreFromSnapshot` → `RestoreFromSnapshot` → `restoreFromSnapshot` | in `snapshot: RtgSystemSnapshot[1]`; in `restore_options: RtgControllerRestoreOptions[0..1]`; out `result: RtgControllerOperationResult[1]` | `VellisRequestInvalid`, `RtgControllerSnapshotFailed` | Validate and atomically restore coordinated state; record the operation by default and reserve skip for internal recovery. |
