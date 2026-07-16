# component.rtg.controller

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

- Model definition: `RtgController`
- Lifecycle: `accepted`
- Purpose: Coordinate RTG mutation and validation lanes, component-local atomic batches, cross-component recovery classification, query consistency, and explicit snapshot export, persistence, and restoration.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `applyLiveGraphChanges` | `ApplyLiveGraphChanges` | in `graphChanges: RtgGraphChangeSet`; in `validationMode: RtgControllerValidationMode` = `RtgControllerValidationMode::strict`; out `result: RtgControllerOperationResult` | `RtgControllerValidationFailed`, `RtgControllerApplyFailed`, `RtgControllerRecoveryIndeterminate` | Validate and apply normal live graph CRUD in the serialized mutation lane. |
| `validateLiveGraphChanges` | `ValidateLiveGraphChanges` | in `graphChanges: RtgGraphChangeSet`; in `validationOptions: RtgControllerValidationOptions[0..1]`; out `result: RtgControllerLiveGraphValidationResult` | `RtgControllerPreconditionFailed`, `RtgValidationInputInvalid` | Normalize exactly as apply would and return generated identities plus bounded validation without component mutation or repeating the resolved batch. |
| `stageKnowledgeChanges` | `StageKnowledgeChanges` | in `knowledgeChanges: RtgChangeBatch`; in `validationMode: RtgControllerValidationMode` = `RtgControllerValidationMode::strict`; out `result: RtgControllerOperationResult` | `RtgControllerValidationFailed`, `RtgControllerPreconditionFailed`, `RtgControllerApplyFailed`, `RtgControllerRecoveryIndeterminate` | Validate and stage migration-scoped non-live graph, schema, constraint, and migration records. |
| `applyMigrationCutover` | `ApplyMigrationCutover` | in `migrationId: String`; in `cutoverOptions: RtgControllerCutoverOptions[0..1]`; out `result: RtgControllerOperationResult` | `RtgControllerPreconditionFailed`, `RtgControllerValidationFailed`, `RtgControllerApplyFailed`, `RtgControllerRecoveryIndeterminate` | Apply exactly one migration membership in reference-safe order, validate the result, and either commit or restore. |
| `executeQuery` | `ExecuteControllerQuery` | in `querySpec: RtgQuerySpec`; in `queryOptions: RtgQueryOptions[0..1]`; out `result: RtgQueryResult` | `RtgQuerySpecInvalid`, `RtgQueryUnsupported` | Execute against one coherent graph view while controller mutations are excluded. |
| `getObject` | `ControllerGetObject` | in `objectUuid: String`; out `object: RtgObject` | `RtgControllerObjectNotFound` | Normalize UUID text and return the public graph record without lifecycle filtering; invalid and absent UUIDs are reported through the controller-owned not-found contract. |
| `listMigrations` | `ControllerListMigrations` | in `status: RtgMigrationStatus[0..1]`; in `offset: Integer` = `0`; in `limit: Integer` = `100`; out `result: RtgMigrationRecordList` | `RtgMigrationStatusInvalid` | Return a stable bounded page of migration records in migration-ID order. |
| `getMigration` | `ControllerGetMigration` | in `migrationId: String`; out `result: RtgMigrationRecord` | `RtgMigrationNotFound` | Return one migration tracking record by stable migration ID. |
| `validateGraph` | `ValidateGraph` | in `migrationIds: String[0..*]`; in `validationOptions: RtgControllerValidationOptions[0..1]`; out `report: RtgValidationReport` | `RtgControllerValidationFailed` | Validate current state or named migration projections without mutation. |
| `discoverAnchorTypes` | `DiscoverAnchorTypes` | in `discoveryOptions: RtgControllerDiscoveryOptions[0..1]`; out `result: RtgAnchorTypeDiscoveryResult` | `RtgControllerDiscoveryFailed` | Compose schema summaries and graph counts; absent options exclude non-live types and impose no limit. |
| `getSchemaPack` | `GetControllerSchemaPack` | in `anchorTypeKeys: String[1..*]`; in `schemaPackOptions: RtgControllerSchemaPackOptions[0..1]`; out `result: RtgControllerSchemaPack` | `RtgControllerDiscoveryFailed` | Return the schema closure for named anchors and, by default, current live counts. |
| `listSchemaDefinitionsByTypeKey` | `ListSchemaDefinitionsByTypeKey` | in `typeKey: String`; in `kind: RtgSchemaDefinitionKind[0..1]`; in `live: Boolean[0..1]`; in `offset: Integer` = `0`; in `limit: Integer[0..1]`; out `result: RtgSchemaDefinitionList` | `RtgControllerPreconditionFailed` | Return a deterministic bounded page for one type key without exporting coordinated system state. |
| `getSystemState` | `GetSystemState` | out `result: RtgControllerSystemState` | `RtgControllerDiscoveryFailed` | Return a read-only classified domain summary, persisted snapshot paths, and recommended workflows. |
| `exportSystemSnapshot` | `ExportSystemSnapshot` | out `snapshot: RtgSystemSnapshot` | `RtgControllerSnapshotFailed` | Export all four component snapshots from one coordinated visible state. |
| `persistSystemSnapshot` | `PersistSystemSnapshot` | in `relativePath: JsonRelativePath`; out `result: RtgSnapshotPersistenceResult` | `RtgControllerSnapshotFailed` | Export and atomically store one coordinated snapshot under JSON storage authority, returning only path, byte size, digest, and state counts. |
| `listPersistedSnapshots` | `ListPersistedSnapshots` | in `offset: Integer` = `0`; in `limit: Integer` = `100`; out `result: RtgPersistedSnapshotList` | `RtgControllerSnapshotFailed` | Return a stable bounded page of valid persisted system snapshots visible through the bound JSON storage root. |
| `loadPersistedSnapshot` | `LoadPersistedSnapshot` | in `relativePath: JsonRelativePath`; out `result: RtgPersistedSnapshotDocument` | `RtgControllerSnapshotFailed` | Read and validate a persisted snapshot document without applying it. |
| `abandonMigration` | `AbandonMigration` | in `migrationId: String`; in `reason: String[0..1]`; out `result: RtgControllerOperationResult` | `RtgControllerPreconditionFailed`, `RtgControllerApplyFailed`, `RtgControllerRecoveryIndeterminate` | Mark migration work abandoned and prune only safe non-live candidates owned by that migration. |
| `restoreFromSnapshot` | `RestoreFromSnapshot` | in `snapshot: RtgSystemSnapshot`; out `result: RtgControllerOperationResult` | `RtgControllerSnapshotFailed`, `RtgControllerRecoveryIndeterminate` | Validate an explicitly supplied whole-system state-transfer document, replace each state owner while writes are excluded, and require runtime reconstruction before reopening if a partial replacement cannot be resolved. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `OpenRtgController` | in `graph: RtgGraph`; in `schema: RtgSchema`; in `constraints: RtgConstraints`; in `migration: RtgMigration`; in `changeValidator: RtgChangeValidator`; in `queryEngine: RtgQueryEngine`; in `jsonStorage: JsonFileStorage`; out `controller: RtgController` | `RtgControllerConfigurationInvalid` | Bind exactly one implementation of each of the seven required Bibliotek roles without taking traffic-ledger or runtime-history ownership. |

## Retained collaborator roles

| Role | Kind | Referenced type | Multiplicity |
|---|---|---|---|
| `graph` | `part` | `RtgGraph` | `[1]` |
| `schema` | `part` | `RtgSchema` | `[1]` |
| `constraints` | `part` | `RtgConstraints` | `[1]` |
| `migration` | `part` | `RtgMigration` | `[1]` |
| `changeValidator` | `part` | `RtgChangeValidator` | `[1]` |
| `queryEngine` | `part` | `RtgQueryEngine` | `[1]` |
| `jsonStorage` | `part` | `JsonFileStorage` | `[1]` |

## Owned state

| State feature | Type | Ownership | Meaning |
|---|---|---|---|
| — | — | — | This component owns no abstract state. |

## Action and state effects

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `applyLiveGraphChanges` | `graph` | `dependency` | apply the accepted resolved graph change set. |
| `applyLiveGraphChanges` | `changeValidator` | `dependency` | validate the projected graph state before mutation. |
| `applyLiveGraphChanges` | `schema` | `dependency` | supply schema state to projection validation. |
| `applyLiveGraphChanges` | `constraints` | `dependency` | supply constraint state to projection validation. |
| `applyLiveGraphChanges` | `migration` | `dependency` | supply migration overlays to projection validation. |
| `applyLiveGraphChanges` | `queryEngine` | `dependency` | supply declarative query evaluation to validation tracks. |
| `validateLiveGraphChanges` | `graph` | `dependency` | read canonical graph state and build a projection without mutation. |
| `validateLiveGraphChanges` | `schema` | `dependency` | read schema state required by selected validation tracks. |
| `validateLiveGraphChanges` | `constraints` | `dependency` | read constraint definitions required by selected tracks. |
| `validateLiveGraphChanges` | `migration` | `dependency` | read migration state required by selected tracks. |
| `validateLiveGraphChanges` | `queryEngine` | `dependency` | evaluate validation patterns without mutation. |
| `validateLiveGraphChanges` | `changeValidator` | `dependency` | validate the resolved projected state. |
| `stageKnowledgeChanges` | `graph` | `dependency` | create or replace migration-scoped non-live graph candidates. |
| `stageKnowledgeChanges` | `schema` | `dependency` | create or replace migration-scoped non-live schema candidates. |
| `stageKnowledgeChanges` | `constraints` | `dependency` | create or replace migration-scoped non-live constraint candidates. |
| `stageKnowledgeChanges` | `migration` | `dependency` | maintain migration records, membership, evidence, and status. |
| `stageKnowledgeChanges` | `changeValidator` | `dependency` | validate projected cutover state before staged writes. |
| `stageKnowledgeChanges` | `queryEngine` | `dependency` | evaluate declarative validation patterns. |
| `applyMigrationCutover` | `graph` | `dependency` | apply graph live-status changes and restore graph state on failure. |
| `applyMigrationCutover` | `schema` | `dependency` | apply schema live-status changes and restore schema state on failure. |
| `applyMigrationCutover` | `constraints` | `dependency` | apply constraint live-status changes and restore constraint state on failure. |
| `applyMigrationCutover` | `migration` | `dependency` | derive the plan and commit applied or failed lifecycle status. |
| `applyMigrationCutover` | `changeValidator` | `dependency` | validate projected and actual cutover states. |
| `applyMigrationCutover` | `queryEngine` | `dependency` | evaluate declarative validation patterns. |
| `executeQuery` | `graph` | `dependency` | supply one coherent graph read view while writes are excluded. |
| `executeQuery` | `queryEngine` | `dependency` | evaluate the caller query specification. |
| `getObject` | `graph` | `dependency` | retrieve one graph object without mutation. |
| `listMigrations` | `migration` | `dependency` | read deterministic current migration records. |
| `getMigration` | `migration` | `dependency` | read one current migration record. |
| `validateGraph` | `graph` | `dependency` | read canonical graph state for validation. |
| `validateGraph` | `schema` | `dependency` | read schema state for validation. |
| `validateGraph` | `constraints` | `dependency` | read constraints for validation. |
| `validateGraph` | `migration` | `dependency` | read migrations and requested overlays for validation. |
| `validateGraph` | `queryEngine` | `dependency` | evaluate declarative validation patterns. |
| `validateGraph` | `changeValidator` | `dependency` | execute selected validation tracks. |
| `discoverAnchorTypes` | `graph` | `dependency` | count current objects by type and lifecycle. |
| `discoverAnchorTypes` | `schema` | `dependency` | read anchor type keys and descriptions. |
| `getSchemaPack` | `graph` | `dependency` | read requested live counts. |
| `getSchemaPack` | `schema` | `dependency` | read the selected schema closure. |
| `getSystemState` | `graph` | `dependency` | summarize graph population and staged candidates. |
| `getSystemState` | `schema` | `dependency` | summarize live and non-live schema state. |
| `getSystemState` | `constraints` | `dependency` | summarize constraint candidates. |
| `getSystemState` | `migration` | `dependency` | summarize current migration lifecycle state. |
| `getSystemState` | `jsonStorage` | `dependency` | list storage-scoped persisted snapshots. |
| `exportSystemSnapshot` | `graph` | `dependency` | export the graph snapshot. |
| `exportSystemSnapshot` | `schema` | `dependency` | export the schema snapshot. |
| `exportSystemSnapshot` | `constraints` | `dependency` | export the constraint snapshot. |
| `exportSystemSnapshot` | `migration` | `dependency` | export the migration snapshot. |
| `persistSystemSnapshot` | `graph` | `dependency` | export graph state for the coordinated snapshot. |
| `persistSystemSnapshot` | `schema` | `dependency` | export schema state for the coordinated snapshot. |
| `persistSystemSnapshot` | `constraints` | `dependency` | export constraint state for the coordinated snapshot. |
| `persistSystemSnapshot` | `migration` | `dependency` | export migration state for the coordinated snapshot. |
| `persistSystemSnapshot` | `jsonStorage` | `dependency` | atomically write the coordinated snapshot document. |
| `listPersistedSnapshots` | `jsonStorage` | `dependency` | list persisted snapshot metadata. |
| `loadPersistedSnapshot` | `jsonStorage` | `dependency` | read and validate one persisted snapshot document. |
| `abandonMigration` | `graph` | `dependency` | prune only safe non-live graph candidates. |
| `abandonMigration` | `schema` | `dependency` | prune only safe non-live schema candidates. |
| `abandonMigration` | `constraints` | `dependency` | prune only safe non-live constraint candidates. |
| `abandonMigration` | `migration` | `dependency` | transition the selected migration to abandoned. |
| `restoreFromSnapshot` | `graph` | `dependency` | replace graph state from the validated snapshot. |
| `restoreFromSnapshot` | `schema` | `dependency` | replace schema state from the validated snapshot. |
| `restoreFromSnapshot` | `constraints` | `dependency` | replace constraint state from the validated snapshot. |
| `restoreFromSnapshot` | `migration` | `dependency` | replace migration state from the validated snapshot. |
| `listSchemaDefinitionsByTypeKey` | — | `declared` | delegate one targeted schema read without mutation. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| `applyLiveGraphChanges` | `normalize: local`, `validateProjection: ValidateRtgChangeBatch`, `applyProjection: local`, `reject: local`, `returnOutcome: local` | `first normalize then validateProjection;`; `first reject then returnOutcome;` |
| `applyMigrationCutover` | `derivePlan: local`, `validateProjection: ValidateRtgChangeBatch`, `applyCutover: local`, `validateActualState: ValidateRtgChangeBatch`, `commitApplied: local`, `recordFailed: local` | `first derivePlan then validateProjection;` |
| `executeQuery` | `evaluate: ExecuteRtgQuery` | — |
| `restoreFromSnapshot` | `projectSnapshot: local`, `validateSnapshot: ValidateRtgGraphState`, `replaceGraph: ReplaceGraphSnapshot`, `replaceSchema: ReplaceSchemaSnapshot`, `replaceConstraints: ReplaceConstraintSnapshot`, `replaceMigration: ReplaceMigrationSnapshot`, `returnRestore: local` | `first projectSnapshot then validateSnapshot;`; `first replaceGraph then replaceSchema;`; `first replaceSchema then replaceConstraints;`; `first replaceConstraints then replaceMigration;`; `first replaceMigration then returnRestore;` |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.rtg.controller.live_mutation_flow` | `ApplyLiveGraphChanges` | `controller.applyLiveGraphChanges` | Normalize references, construct a projected state, validate it in strict mode, and submit one graph-local atomic batch only for an accepted projection. Rejection and local batch failure expose unchanged graph state. |
| `contract.rtg.controller.live_mutation_lane` | `ApplyLiveGraphChanges` | `controller.applyLiveGraphChanges` | The live lane accepts live anchor, data-object, and link writes, associations, dissociations, deletes, and live replacements. It rejects schema, constraint, migration, non-live candidate creation, and requests that make graph objects non-live. strict is the default; skip bypasses change validation only and never lower-store invariants. |
| `contract.rtg.controller.staging_flow` | `StageKnowledgeChanges` | `controller.stageKnowledgeChanges` | Staging accepts migration-scoped non-live graph, schema, and constraint candidates plus migration records, evidence, and permitted status changes. It rejects direct live schema/constraint writes, unscoped candidates, and live-status flips reserved for cutover. Strict mode validates the projected cutover before any write. A successful result has status applied and details keys operation_effect=staged_candidates_written, requires_cutover, staged_migration_ids, and candidate_counts with schema, constraints, and graph counts. |
| `contract.rtg.controller.validation_flow` | `ValidateLiveGraphChanges` | `controller.validateLiveGraphChanges` | Resolve the request exactly as a write would, validate the projected state, return generated identities and resolved changes, and leave component state unchanged. |
| `contract.rtg.controller.cutover_flow` | `ApplyMigrationCutover` | `controller.applyMigrationCutover` | Read selected migration membership, validate the projection, apply non-empty component-local batches in reference-safe order, validate the result, and commit applied status. Before any owner commits, rejection is an ordinary no-effect failure. After an owner commits, unresolved delivery or a later-owner failure is recovery-indeterminate and ordinary traffic remains closed until reconstruction verifies a coherent outcome. |
| `contract.rtg.controller.cutover_sequence` | `ApplyMigrationCutover` | `controller.applyMigrationCutover` | Under the write lock: derive and validate the plan; submit one non-empty atomic batch per state owner in reference-safe order; validate actual state; optionally prune retired records; then remove the completed migration. A known pre-commit rejection records cutover_failed. An unresolved fault after any owner commits reports recovery-indeterminate and does not assert restoration or a safe migration status. |
| `contract.rtg.controller.abandonment_flow` | `AbandonMigration` | `controller.abandonMigration` | Applied migrations cannot be abandoned. Draft, ready, or failed work becomes abandoned; only non-live make-live candidates unshared by another migration may be pruned. Live records and make-non-live targets are never deleted. details.pruned_candidates groups removed IDs under schema, constraints, and graph; details.skipped_candidates groups retained IDs under the same keys and gives each a reason of shared, missing, or live. |
| `contract.rtg.controller.stable_query_flow` | `ExecuteControllerQuery` | `controller.executeQuery` | Execute each query while writes are excluded so the query engine receives one coherent graph read view. |
| `contract.rtg.controller.read_semantics` | `RtgController` | `controller` | Query defaults to live-only at the controller boundary unless explicit query options override it. Direct object reads do not lifecycle-filter. Migration reads are deterministically ordered. All reads queue behind cutover and restore mutations. |
| `contract.rtg.controller.discovery_semantics` | `RtgController` | `controller` | Discovery composes schema-owned descriptions with graph counts, excludes non-live definitions by default, and applies a positive optional limit. Schema packs contain selected anchors, associated-data schemas, participating links, and live counts when requested. |
| `contract.rtg.controller.system_state_semantics` | `GetSystemState` | `controller.getSystemState` | State classification is exactly empty, schema_only, populated, or has_staged_work. liveSchemaCounts has anchor, data-object, link, and total definition counts; liveObjectCounts is the graph-owned ordered type-count list; nonLiveCandidateCounts has schema, constraints, graph, and total counts; migrationCountsByStatus has draft, ready, failed, applied, abandoned, and total counts. The result also reports storage-scoped snapshot paths, stable workflow identifiers, and advisory next steps without mutation. Type names and snapshot metadata remain available through their dedicated discovery and snapshot-list actions. |
| `contract.rtg.controller.snapshot_flow` | `ExportSystemSnapshot` | `controller.exportSystemSnapshot` | Export graph, schema, constraint, and migration snapshots from one visible controller state. |
| `contract.rtg.controller.persisted_snapshot_semantics` | `RtgController` | `controller` | Persist writes the coordinated snapshot atomically through JSON storage. List and load expose only valid snapshot-like JSON documents below that storage root; load validates but does not apply the snapshot. |
| `contract.rtg.controller.restore_flow` | `RestoreFromSnapshot` | `controller.restoreFromSnapshot` | Construct and semantically validate all four candidate component states before replacing current components. Invoke each state owner's public full-snapshot replacement action while controller reads and writes are excluded. The controller does not capture another full preimage. Success exposes the requested logical restoration. Any unresolved partial replacement reports RtgControllerRecoveryIndeterminate, keeps ordinary traffic closed, and relies on the explicit restore target plus runtime reconstruction before reopening. |
| `contract.rtg.controller.operation_results` | `RtgController` | `controller` | State-changing results use only applied, cutover_applied, cutover_failed, migration_abandoned, snapshot_persisted, or restore_applied. generatedIds maps every request-local reference resolved by that operation and is empty when none are generated. Zero visible state change reports zero applied counts; validationReport is absent when skipped; details carries operation-specific JSON-safe domain evidence. Runtime traces and cursors are supplied outside this result. |
| `invariant.rtg.controller.public_contracts_only` | `RtgController` | `controller` | Lower components are used only through public contracts, including atomic batches and explicit snapshot replacement; no private host-swapping callback may replace a runtime-managed occurrence. |
| `invariant.rtg.controller.no_transport_ownership` | `RtgController` | `controller` | Controller owns no MCP, REST, CLI, SDK, or UI transport. |
| `contract.rtg.controller.intentional_boundary` | `RtgController` | `controller` | The controller owns RTG operation sequencing, cross-component invariant checks, recovery-required classification, coordinated snapshot export/restore, and snapshot persistence through its JSON collaborator, not lower-store records or algorithms. It owns no traffic ledger, generic history/replay, runtime trace/cursor, authentication/authorization, UI or transport, storage-engine mechanics, replication/deployment topology, distributed lock, online distributed rollback, or distributed transaction guarantee. Curated discovery-view state remains outside v1. |
| `invariant.rtg.controller.validates_before_required_mutation` | `RtgController` | `controller` | Strict mutation validates the projected state before apply. |
| `invariant.rtg.controller.strict_validation_default` | `RtgController` | `controller` | Normal mutation defaults to strict validation. |
| `invariant.rtg.controller.live_graph_lane_excludes_knowledge_engineering` | `RtgController` | `controller` | Live CRUD excludes schema, constraint, migration, and non-live work. |
| `invariant.rtg.controller.knowledge_changes_are_migration_scoped` | `RtgController` | `controller` | Non-live knowledge changes belong to active migration work. |
| `invariant.rtg.controller.cutover_is_only_live_flip_authority_for_staged_schema_constraints` | `RtgController` | `controller` | Cutover is the only authority for staged schema and constraint live flips. |
| `invariant.rtg.controller.normalized_batches_are_internal_controller_plans` | `RtgController` | `controller` | Normalized batches are internal plans, not a generic public mutation backdoor. |
| `invariant.rtg.controller.schema_constraint_changes_use_migrations` | `RtgController` | `controller` | Schema and constraint writes use migration workflows. |
| `invariant.rtg.controller.schema_constraint_deletion_uses_migrations` | `RtgController` | `controller` | Schema and constraint retirement/deletion uses migration workflows. |
| `invariant.rtg.controller.non_live_candidates_are_migration_scoped` | `RtgController` | `controller` | Non-live candidates are referenced by active migration membership. |
| `invariant.rtg.controller.system_invariants_owned` | `RtgController` | `controller` | Cross-component invariants are enforced by the controller. |
| `invariant.rtg.controller.validation_report_authoritative` | `RtgController` | `controller` | Blocking validation findings control strict acceptance. |
| `invariant.rtg.controller.snapshot_uses_component_snapshots` | `RtgController` | `controller` | Coordinated snapshots are assembled through component snapshot contracts. |
| `invariant.rtg.controller.snapshot_json_serializable` | `RtgController` | `controller` | Exported system snapshots are JSON-serializable. |
| `invariant.rtg.controller.persisted_snapshot_readback_is_storage_scoped` | `RtgController` | `controller` | Snapshot readback is limited to JSON storage documents. |
| `invariant.rtg.controller.cutover_uses_migration_membership` | `RtgController` | `controller` | Cutover applies exactly the selected migration membership. |
| `invariant.rtg.controller.reads_do_not_observe_transient_cutover` | `RtgController` | `controller` | Reads do not observe transient cutover or restore state. |
| `invariant.rtg.controller.projected_queries_use_live_overlay` | `RtgController` | `controller` | Projected validation uses explicit live-status overlays. |
| `invariant.rtg.controller.cutover_restores_on_failure` | `RtgController` | `controller` | failureRestore=restore_pre_cutover_snapshot names the required logical pre-cutover recovery outcome; it does not require materializing a full preimage. A known rejection before owner commit leaves state unchanged. Unresolved cross-owner effects are recovery-indeterminate until reconstruction verifies the logical outcome. |
| `invariant.rtg.controller.failed_cutover_is_legible` | `RtgController` | `controller` | Failed cutover records actionable diagnostic status. |
| `invariant.rtg.controller.cutover_order` | `RtgController` | `controller` | Cutover ordering preserves referenced state and validation. |
| `invariant.rtg.controller.abandonment_never_deletes_live_records` | `RtgController` | `controller` | Abandonment never deletes live records. |
| `invariant.rtg.controller.one_write_at_a_time` | `RtgController` | `controller` | Only one controller write mutates coordinated RTG domain state at a time. |
| `invariant.rtg.controller.resolved_uuids_before_mutation` | `RtgController` | `controller` | Batch-local references are resolved before validation and mutation so generated identities are stable in the domain result and runtime canonical effect. |
| `invariant.rtg.controller.write_atomicity_scoped` | `RtgController` | `controller` | Each owner batch is locally atomic. The controller does not promise an online distributed rollback across owners; uncertainty after an earlier owner commit is recovery-indeterminate. |
| `invariant.rtg.controller.routine_work_is_delta_scaled` | `RtgController` | `controller` | Non-state-transfer mutation and validation orchestration does not capture, copy, serialize, hash, or retain complete owner state for rollback or projection. Its scaffolding and transient recovery data may grow with the requested change and declared cascade closure, but not unrelated canonical state. Explicit snapshot export, persistence, restore, checkpoint, and reconstruction are exceptions. |
| `contract.rtg.controller.validation_skip_scope` | `RtgController` | `controller` | validationMode=skip bypasses cross-component change validation only. Every state owner still enforces local structural invariants and local batch atomicity, and the operation result leaves validationReport absent to identify that validation was skipped. |
| `invariant.rtg.controller.reads_mediated` | `RtgController` | `controller` | Application reads pass through controller public contracts. |
| `invariant.rtg.controller.live_flips_via_full_record_write` | `RtgController` | `controller` | Live-status changes preserve complete public records. |
| `invariant.rtg.controller.graph_type_is_schema_type_key` | `RtgController` | `controller` | Graph object type values correspond to schema type keys. |
| `contract.rtg.controller.apply_live_graph_changes.failures` | `ApplyLiveGraphChanges` | `controller.applyLiveGraphChanges` | Strict rejection has no graph effect. The graph-local batch either applies completely or leaves graph state unchanged. |
| `contract.rtg.controller.validate_live_graph_changes.failures` | `ValidateLiveGraphChanges` | `controller.validateLiveGraphChanges` | Every rejected validation attempt leaves component state unchanged. |
| `contract.rtg.controller.stage_knowledge_changes.failures` | `StageKnowledgeChanges` | `controller.stageKnowledgeChanges` | Rejected staging before owner commit has no effect. A local batch failure leaves that owner unchanged; unresolved failure after another owner commits is recovery-indeterminate. |
| `contract.rtg.controller.apply_migration_cutover.failures` | `ApplyMigrationCutover` | `controller.applyMigrationCutover` | A rejected cutover before owner commit leaves coordinated state unchanged and may record a legible failed migration. An unresolved failure after any owner commit raises RtgControllerRecoveryIndeterminate; the runtime assigns an indeterminate disposition, closes ordinary traffic, and requires reconstruction before a coherent outcome is claimed. |
| `contract.rtg.controller.execute_controller_query.failures` | `ExecuteControllerQuery` | `controller.executeQuery` | Query failures have no component state effect. |
| `contract.rtg.controller.controller_get_object.failures` | `ControllerGetObject` | `controller.getObject` | Invalid UUID text or an absent graph object produces RtgControllerObjectNotFound with corrective diagnostics and has no state effect. |
| `contract.rtg.controller.controller_list_migrations.failures` | `ControllerListMigrations` | `controller.listMigrations` | Listing has no state effect. |
| `contract.rtg.controller.controller_get_migration.failures` | `ControllerGetMigration` | `controller.getMigration` | Read failure has no state effect. |
| `contract.rtg.controller.validate_graph.failures` | `ValidateGraph` | `controller.validateGraph` | Validation has no component state effect. |
| `contract.rtg.controller.discover_anchor_types.failures` | `DiscoverAnchorTypes` | `controller.discoverAnchorTypes` | Discovery has no state effect. |
| `contract.rtg.controller.get_controller_schema_pack.failures` | `GetControllerSchemaPack` | `controller.getSchemaPack` | Schema-pack reads have no state effect. |
| `contract.rtg.controller.get_system_state.failures` | `GetSystemState` | `controller.getSystemState` | System-state inspection has no state effect. |
| `contract.rtg.controller.export_system_snapshot.failures` | `ExportSystemSnapshot` | `controller.exportSystemSnapshot` | Export returns one coordinated state and does not mutate components. |
| `contract.rtg.controller.persist_system_snapshot.failures` | `PersistSystemSnapshot` | `controller.persistSystemSnapshot` | Failure leaves no partial JSON document and remains visible as the operation outcome. |
| `contract.rtg.controller.list_persisted_snapshots.failures` | `ListPersistedSnapshots` | `controller.listPersistedSnapshots` | Listing is storage-scoped and has no state effect. |
| `contract.rtg.controller.list_schema_definitions_by_type_key.failures` | `ListSchemaDefinitionsByTypeKey` | `controller.listSchemaDefinitionsByTypeKey` | Invalid selection or collaborator failure leaves schema and controller state unchanged and returns a modeled controller failure. |
| `contract.rtg.controller.load_persisted_snapshot.failures` | `LoadPersistedSnapshot` | `controller.loadPersistedSnapshot` | Loading does not restore or otherwise mutate current system state. |
| `contract.rtg.controller.abandon_migration.failures` | `AbandonMigration` | `controller.abandonMigration` | Abandonment never deletes live records. Each owner batch is locally atomic; uncertainty after a prior owner commit is recovery-indeterminate rather than silently compensated. |
| `contract.rtg.controller.restore_from_snapshot.failures` | `RestoreFromSnapshot` | `controller.restoreFromSnapshot` | Invalid restoration before replacement leaves current state unchanged. The controller captures no full safety snapshot. Unresolved partial replacement raises RtgControllerRecoveryIndeterminate and requires reconstruction from the explicit restore target before ordinary traffic reopens. |
| `contract.rtg.controller.open_rtg_controller.failures` | `OpenRtgController` | `openRtgControllerSubject` | Invalid or incompatible dependencies do not return a partially usable controller. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgControllerValidationOptions` | `attribute` | `selection: RtgValidationTrackSelection` = `RtgValidationTrackSelection::'all'`, `tracks[0..*]: RtgValidationTrack`, `findingLimit[0..1]: Integer` | Controller validation uses the same canonical track-selection and finding-limit semantics as change validation. |
| `RtgControllerCutoverOptions` | `attribute` | `validationMode: RtgControllerValidationMode` = `RtgControllerValidationMode::strict`, `pruneRetired: Boolean` = `true`, `failureRestore: RtgControllerFailureRestore` = `RtgControllerFailureRestore::restore_pre_cutover_snapshot` | Defined by its typed fields and action requirements. |
| `RtgControllerDiscoveryOptions` | `attribute` | `includeNonLive: Boolean` = `false`, `limit[0..1]: Integer` | Defined by its typed fields and action requirements. |
| `RtgControllerSchemaPackOptions` | `attribute` | `live[0..1]: Boolean` = `true`, `includeLiveCounts: Boolean` = `true` | Defined by its typed fields and action requirements. |
| `RtgControllerAppliedChanges` | `attribute` | `graphWrites: Integer` = `0`, `schemaWrites: Integer` = `0`, `constraintWrites: Integer` = `0`, `migrationWrites: Integer` = `0`, `deletes: Integer` = `0`, `liveStatusChanges: Integer` = `0` | Defined by its typed fields and action requirements. |
| `RtgControllerOperationResult` | `attribute` | `status: RtgControllerOperationStatus`, `appliedChanges: RtgControllerAppliedChanges`, `validationReport[0..1]: RtgValidationReport`, `details: JsonObject`, `generatedIds: JsonObject` | Construction supplies all-zero applied counts and empty details/generatedIds when omitted. details is limited to operation-specific identifiers, candidate counts, pruned/skipped identity summaries, and short reasons; it never contains submitted changes, snapshots, validation report copies, or arbitrary exception data. |
| `RtgControllerLiveGraphValidationResult` | `attribute` | `status: RtgControllerValidationStatus`, `mutationState: RtgControllerMutationState`, `accepted: Boolean`, `generatedIds: JsonObject`, `validationReport: RtgValidationReport` | generatedIds maps each request-local reference to its resolved UUID exactly as apply would; the resolved change batch is not repeated in the result. |
| `RtgSystemSnapshot` | `attribute` | `graph: RtgGraphSnapshot`, `schema: RtgSchemaSnapshot`, `constraints: RtgConstraintSnapshot`, `migration: RtgMigrationSnapshot` | Defined by its typed fields and action requirements. |
| `RtgAnchorTypeDiscoveryEntry` | `attribute` | `typeKey: String`, `description: String`, `liveCount: Integer` | Defined by its typed fields and action requirements. |
| `RtgAnchorTypeDiscoveryResult` | `attribute` | `anchorTypes[0..*]: RtgAnchorTypeDiscoveryEntry` | Defined by its typed fields and action requirements. |
| `RtgControllerSchemaPack` | `attribute` | `schemaPack: RtgSchemaPack`, `liveCounts: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgPersistedSnapshotMetadata` | `attribute` | `relativePath: JsonRelativePath`, `sizeBytes: Integer`, `modifiedAt: Timestamp` | Defined by its typed fields and action requirements. |
| `RtgControllerSchemaCounts` | `attribute` | `anchor: Integer`, `dataObject: Integer`, `link: Integer`, `total: Integer` | Defined by its typed fields and action requirements. |
| `RtgControllerCandidateCounts` | `attribute` | `schema: Integer`, `constraints: Integer`, `graph: Integer`, `total: Integer` | Defined by its typed fields and action requirements. |
| `RtgControllerMigrationCounts` | `attribute` | `draft: Integer`, `ready: Integer`, `failed: Integer`, `applied: Integer`, `abandoned: Integer`, `total: Integer` | Defined by its typed fields and action requirements. |
| `RtgControllerSystemState` | `attribute` | `stateClassification: RtgControllerStateClassification`, `liveSchemaCounts: RtgControllerSchemaCounts`, `liveObjectCounts: RtgTypeCountList`, `nonLiveCandidateCounts: RtgControllerCandidateCounts`, `migrationCountsByStatus: RtgControllerMigrationCounts`, `migrationCountsScope: RtgControllerMigrationCountScope` = `RtgControllerMigrationCountScope::current_migration_store`, `persistedSnapshotPaths[0..*] ordered: JsonRelativePath`, `recommendedWorkflows[0..*]: RtgControllerWorkflow`, `recommendedNextSteps[0..*]: String` | Defined by its typed fields and action requirements. |
| `RtgPersistedSnapshotList` | `attribute` | `snapshots[0..*]: RtgPersistedSnapshotMetadata`, `total: Integer`, `nextOffset: Integer` | Defined by its typed fields and action requirements. |
| `RtgPersistedSnapshotDocument` | `attribute` | `relativePath: JsonRelativePath`, `snapshot: RtgSystemSnapshot` | Defined by its typed fields and action requirements. |
| `RtgSnapshotStateCounts` | `attribute` | `anchors: Integer`, `dataObjects: Integer`, `links: Integer`, `schemaDefinitions: Integer`, `constraints: Integer`, `migrations: Integer` | Defined by its typed fields and action requirements. |
| `RtgSnapshotPersistenceResult` | `attribute` | `status: RtgControllerOperationStatus`, `relativePath: JsonRelativePath`, `sizeBytes: Integer`, `digest: String`, `stateCounts: RtgSnapshotStateCounts` | Compact metadata for one persisted state transfer. The persisted snapshot is not repeated in this result. |
| `RtgControllerConfigurationInvalid` | `attribute` | `message: String`, `diagnostic[0..1]: RtgDiagnostic` | Defined by its typed fields and action requirements. |
| `RtgControllerValidationFailed` | `attribute` | `message: String`, `validationReport[0..1]: RtgValidationReport`, `diagnostic[0..1]: RtgDiagnostic` | Defined by its typed fields and action requirements. |
| `RtgControllerPreconditionFailed` | `attribute` | `message: String`, `diagnostic[0..1]: RtgDiagnostic` | Defined by its typed fields and action requirements. |
| `RtgControllerApplyFailed` | `attribute` | `message: String`, `diagnostic[0..1]: RtgDiagnostic` | Defined by its typed fields and action requirements. |
| `RtgControllerObjectNotFound` | `attribute` | `message: String`, `diagnostic[0..1]: RtgDiagnostic` | Defined by its typed fields and action requirements. |
| `RtgControllerDiscoveryFailed` | `attribute` | `message: String`, `diagnostic[0..1]: RtgDiagnostic` | Defined by its typed fields and action requirements. |
| `RtgControllerSnapshotFailed` | `attribute` | `message: String`, `diagnostic[0..1]: RtgDiagnostic` | Defined by its typed fields and action requirements. |
| `RtgControllerRecoveryIndeterminate` | `attribute` | `message: String`, `diagnostic[0..1]: RtgDiagnostic` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| `RtgControllerValidationMode` | `strict`, `skip` |
| `RtgControllerFailureRestore` | `restore_pre_cutover_snapshot` |
| `RtgControllerOperationStatus` | `applied`, `cutover_applied`, `cutover_failed`, `migration_abandoned`, `snapshot_persisted`, `restore_applied` |
| `RtgControllerValidationStatus` | `validated` |
| `RtgControllerMutationState` | `not_mutated` |
| `RtgControllerStateClassification` | `empty`, `schemaOnly`, `populated`, `hasStagedWork` |
| `RtgControllerWorkflow` | `schemaBootstrap`, `dataIngest`, `queryAnswer`, `safeUpdate`, `stagedWorkReview` |
| `RtgControllerMigrationCountScope` | `current_migration_store` |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `ApplyLiveGraphChangesContractVerification` | `ApplyLiveGraphChanges` | `liveMutationFlow`, `liveMutationLane`, `applyLiveGraphChangesFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#ApplyLiveGraphChangesContractVerification` |
| `StageKnowledgeChangesContractVerification` | `StageKnowledgeChanges` | `stagingFlow`, `stageKnowledgeChangesFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#StageKnowledgeChangesContractVerification` |
| `ValidateLiveGraphChangesContractVerification` | `ValidateLiveGraphChanges` | `validationFlow`, `validateLiveGraphChangesFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#ValidateLiveGraphChangesContractVerification` |
| `ApplyMigrationCutoverContractVerification` | `ApplyMigrationCutover` | `cutoverFlow`, `cutoverSequence`, `applyMigrationCutoverFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#ApplyMigrationCutoverContractVerification` |
| `AbandonMigrationContractVerification` | `AbandonMigration` | `abandonmentFlow`, `abandonMigrationFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#AbandonMigrationContractVerification` |
| `ExecuteControllerQueryContractVerification` | `ExecuteControllerQuery` | `stableQueryFlow`, `executeControllerQueryFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#ExecuteControllerQueryContractVerification` |
| `GetSystemStateContractVerification` | `GetSystemState` | `systemStateSemantics`, `getSystemStateFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#GetSystemStateContractVerification` |
| `ExportSystemSnapshotContractVerification` | `ExportSystemSnapshot` | `coordinatedSnapshotFlow`, `exportSystemSnapshotFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#ExportSystemSnapshotContractVerification` |
| `RestoreFromSnapshotContractVerification` | `RestoreFromSnapshot` | `restoreFlow`, `restoreFromSnapshotFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#RestoreFromSnapshotContractVerification` |
| `ControllerGetObjectContractVerification` | `ControllerGetObject` | `controllerGetObjectFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#ControllerGetObjectContractVerification` |
| `ControllerListMigrationsContractVerification` | `ControllerListMigrations` | `controllerListMigrationsFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#ControllerListMigrationsContractVerification` |
| `ControllerGetMigrationContractVerification` | `ControllerGetMigration` | `controllerGetMigrationFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#ControllerGetMigrationContractVerification` |
| `ValidateGraphContractVerification` | `ValidateGraph` | `validateGraphFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#ValidateGraphContractVerification` |
| `DiscoverAnchorTypesContractVerification` | `DiscoverAnchorTypes` | `discoverAnchorTypesFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#DiscoverAnchorTypesContractVerification` |
| `GetControllerSchemaPackContractVerification` | `GetControllerSchemaPack` | `getControllerSchemaPackFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#GetControllerSchemaPackContractVerification` |
| `PersistSystemSnapshotContractVerification` | `PersistSystemSnapshot` | `persistSystemSnapshotFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#PersistSystemSnapshotContractVerification` |
| `ListPersistedSnapshotsContractVerification` | `ListPersistedSnapshots` | `listPersistedSnapshotsFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#ListPersistedSnapshotsContractVerification` |
| `ListSchemaDefinitionsByTypeKeyContractVerification` | `ListSchemaDefinitionsByTypeKey` | `listSchemaDefinitionsByTypeKeyFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#ListSchemaDefinitionsByTypeKeyContractVerification` |
| `LoadPersistedSnapshotContractVerification` | `LoadPersistedSnapshot` | `loadPersistedSnapshotFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#LoadPersistedSnapshotContractVerification` |
| `OpenRtgControllerContractVerification` | `OpenRtgController` | `openRtgControllerFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#OpenRtgControllerContractVerification` |
| `RtgControllerBoundaryVerification` | `RtgController` | `controllerReadSemantics`, `discoverySemantics`, `persistedSnapshotSemantics`, `operationResultSemantics`, `publicContractsOnly`, `noTransportOwnership`, `intentionalBoundary`, `validatesBeforeRequiredMutation`, `strictValidationDefault`, `liveGraphLaneExcludesKnowledgeEngineering`, `knowledgeChangesMigrationScoped`, `cutoverOnlyLiveFlipAuthority`, `normalizedBatchesInternalPlans`, `schemaConstraintChangesUseMigrations`, `schemaConstraintDeletionUsesMigrations`, `nonLiveCandidatesMigrationScoped`, `systemInvariantsOwned`, `validationReportAuthoritative`, `snapshotUsesComponentSnapshots`, `snapshotJsonSerializable`, `persistedSnapshotStorageScoped`, `cutoverUsesMigrationMembership`, `readsHideTransientState`, `projectedQueriesUseLiveOverlay`, `cutoverRestoresOnFailure`, `failedCutoverLegible`, `cutoverOrder`, `abandonmentNeverDeletesLive`, `oneWriteAtATime`, `resolvedUuidsBeforeMutation`, `writeAtomicityScoped`, `validationSkipScope`, `readsMediated`, `liveFlipsViaFullRecordWrite`, `graphTypeIsSchemaTypeKey` | `components/rtg/controller/tests/test_rtg_controller_contract.py#RtgControllerBoundaryVerification` |
| `RtgControllerRoutineWorkScalingVerification` | `RtgController` | `controllerRoutineWorkBounded` | `components/rtg/controller/tests/test_message_native_controller.py#RtgControllerRoutineWorkScalingVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
