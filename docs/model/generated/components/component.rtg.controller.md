# component.rtg.controller

Generated from textual SysML v2 by `just model-render`; do not edit by hand.

- Model definition: `RtgController`
- Lifecycle: `accepted`
- Purpose: Coordinate cross-component RTG invariants, mutation lanes, cutover, recovery, replay, and audit outcomes.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `applyLiveGraphChanges` | `ApplyLiveGraphChanges` | in `graphChanges: RtgGraphChangeSet`; in `validationMode: RtgControllerValidationMode` = `RtgControllerValidationMode::strict`; out `result: RtgControllerOperationResult` | `RtgControllerValidationFailed`, `RtgControllerApplyFailed` | Validate and apply normal live graph CRUD in the serialized mutation lane. |
| `validateLiveGraphChanges` | `ValidateLiveGraphChanges` | in `graphChanges: RtgGraphChangeSet`; in `validationOptions: RtgControllerValidationOptions[0..1]`; out `result: RtgControllerLiveGraphValidationResult` | `RtgControllerPreconditionFailed`, `RtgValidationInputInvalid` | Normalize exactly as apply would and return generated identities, resolved changes, and validation without component or ledger mutation. |
| `stageKnowledgeChanges` | `StageKnowledgeChanges` | in `knowledgeChanges: RtgChangeBatch`; in `validationMode: RtgControllerValidationMode` = `RtgControllerValidationMode::strict`; out `result: RtgControllerOperationResult` | `RtgControllerValidationFailed`, `RtgControllerPreconditionFailed`, `RtgControllerApplyFailed` | Validate and stage migration-scoped non-live graph, schema, constraint, and migration records. |
| `applyMigrationCutover` | `ApplyMigrationCutover` | in `migrationId: String`; in `cutoverOptions: RtgControllerCutoverOptions[0..1]`; out `result: RtgControllerOperationResult` | `RtgControllerPreconditionFailed`, `RtgControllerValidationFailed`, `RtgControllerApplyFailed` | Apply exactly one migration membership in reference-safe order, validate the result, and either commit or restore. |
| `executeQuery` | `ExecuteControllerQuery` | in `querySpec: RtgQuerySpec`; in `queryOptions: RtgQueryOptions[0..1]`; out `result: RtgQueryResult` | `RtgQuerySpecInvalid`, `RtgQueryUnsupported` | Execute against one coherent graph view while controller mutations are excluded; do not append a mutation ledger record. |
| `getObject` | `ControllerGetObject` | in `objectUuid: String`; out `object: RtgObject` | `RtgControllerObjectNotFound` | Normalize UUID text and return the public graph record without lifecycle filtering. |
| `listMigrations` | `ControllerListMigrations` | in `status: RtgMigrationStatus[0..1]`; out `result: RtgMigrationRecordList` | `RtgMigrationStatusInvalid` | Return all migration records or one status in deterministic migration-ID order. |
| `getMigration` | `ControllerGetMigration` | in `migrationId: String`; out `result: RtgMigrationRecord` | `RtgMigrationNotFound` | Return one migration tracking record by stable migration ID. |
| `validateGraph` | `ValidateGraph` | in `migrationIds: String[0..*]`; in `validationOptions: RtgControllerValidationOptions[0..1]`; out `report: RtgValidationReport` | `RtgControllerValidationFailed` | Validate current state or named migration projections without mutation. |
| `discoverAnchorTypes` | `DiscoverAnchorTypes` | in `discoveryOptions: RtgControllerDiscoveryOptions[0..1]`; out `result: RtgAnchorTypeDiscoveryResult` | `RtgControllerDiscoveryFailed` | Compose schema summaries and graph counts; absent options exclude non-live types and impose no limit. |
| `getSchemaPack` | `GetControllerSchemaPack` | in `anchorTypeKeys: String[1..*]`; in `schemaPackOptions: RtgControllerSchemaPackOptions[0..1]`; out `result: RtgControllerSchemaPack` | `RtgControllerDiscoveryFailed` | Return the schema closure for named anchors and, by default, current live counts. |
| `getSystemState` | `GetSystemState` | out `result: RtgControllerSystemState` | `RtgControllerDiscoveryFailed` | Return a read-only classified summary, bounded history pointers, and recommended workflows. |
| `exportSystemSnapshot` | `ExportSystemSnapshot` | out `snapshot: RtgSystemSnapshot` | `RtgControllerSnapshotFailed` | Export all four component snapshots with the represented ledger cursor and transaction identity from one coordinated state. |
| `persistSystemSnapshot` | `PersistSystemSnapshot` | in `relativePath: JsonRelativePath`; out `result: RtgControllerOperationResult` | `RtgControllerSnapshotFailed` | Export and atomically store one coordinated snapshot under JSON storage authority. |
| `listPersistedSnapshots` | `ListPersistedSnapshots` | out `result: RtgPersistedSnapshotList` | `RtgControllerSnapshotFailed` | List only valid persisted system snapshots visible through the bound JSON storage root. |
| `loadPersistedSnapshot` | `LoadPersistedSnapshot` | in `relativePath: JsonRelativePath`; out `result: RtgPersistedSnapshotDocument` | `RtgControllerSnapshotFailed` | Read and validate a persisted snapshot document without applying it. |
| `abandonMigration` | `AbandonMigration` | in `migrationId: String`; in `reason: String[0..1]`; out `result: RtgControllerOperationResult` | `RtgControllerPreconditionFailed`, `RtgControllerApplyFailed` | Mark migration work abandoned and prune only safe non-live candidates owned by that migration. |
| `replayLedger` | `ReplayLedger` | in `replayOptions: RtgControllerReplayOptions[0..1]`; out `result: RtgControllerOperationResult` | `RtgControllerReplayFailed` | Reconstruct component state from an empty or explicit snapshot base and a monotonic ledger window. |
| `verifyReplayFromLedger` | `VerifyReplayFromLedger` | in `replayOptions: RtgControllerReplayOptions[0..1]`; out `result: RtgControllerReplayVerificationResult` | `RtgControllerReplayFailed`, `RtgControllerSnapshotFailed` | Replay into isolated state and compare pre/post summaries and validation without replacing current state. |
| `listMigrationHistory` | `ListMigrationHistory` | out `result: RtgControllerMigrationHistory` | `RtgControllerReplayFailed` | Return migration-related controller events in ledger order, including durable failure outcomes. |
| `flushLedgerFailures` | `FlushLedgerFailures` | out `result: RtgControllerOperationResult` | None | Retry queued audit records in original order and report the remaining degraded-audit state. |
| `restoreFromSnapshot` | `RestoreFromSnapshot` | in `snapshot: RtgSystemSnapshot`; in `restoreOptions: RtgControllerRestoreOptions[0..1]`; out `result: RtgControllerOperationResult` | `RtgControllerSnapshotFailed` | Validate then atomically replace coordinated component state, preserving or recording the ledger cursor as requested. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `OpenRtgController` | in `graph: RtgGraph`; in `schema: RtgSchema`; in `constraints: RtgConstraints`; in `migration: RtgMigration`; in `changeValidator: RtgChangeValidator`; in `queryEngine: RtgQueryEngine`; in `jsonStorage: JsonFileStorage`; in `sqlStorage: SqlStorage`; out `controller: RtgController` | `RtgControllerConfigurationInvalid` | Bind exactly one implementation of each of the eight required Bibliotek roles and initialize or validate the durable ledger schema. |

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
| `sqlStorage` | `part` | `SqlStorage` | `[1]` |

## Owned state

| State feature | Type | Ownership | Meaning |
|---|---|---|---|
| `ledger` | `RtgControllerLedger` | `referenced` | Independently durable canonical controller ledger and degraded-audit queue. |

## Action and state effects

| Action | State / collaborator | Modeled effect |
|---|---|---|
| `applyLiveGraphChanges` | `graph` | apply the accepted resolved graph change set. |
| `applyLiveGraphChanges` | `changeValidator` | validate the projected graph state before mutation. |
| `applyLiveGraphChanges` | `schema` | supply schema state to projection validation. |
| `applyLiveGraphChanges` | `constraints` | supply constraint state to projection validation. |
| `applyLiveGraphChanges` | `migration` | supply migration overlays to projection validation. |
| `applyLiveGraphChanges` | `queryEngine` | supply declarative query evaluation to validation tracks. |
| `validateLiveGraphChanges` | `graph` | read canonical graph state and build a projection without mutation. |
| `validateLiveGraphChanges` | `schema` | read schema state required by selected validation tracks. |
| `validateLiveGraphChanges` | `constraints` | read constraint definitions required by selected tracks. |
| `validateLiveGraphChanges` | `migration` | read migration state required by selected tracks. |
| `validateLiveGraphChanges` | `queryEngine` | evaluate validation patterns without mutation. |
| `validateLiveGraphChanges` | `changeValidator` | validate the resolved projected state. |
| `stageKnowledgeChanges` | `graph` | create or replace migration-scoped non-live graph candidates. |
| `stageKnowledgeChanges` | `schema` | create or replace migration-scoped non-live schema candidates. |
| `stageKnowledgeChanges` | `constraints` | create or replace migration-scoped non-live constraint candidates. |
| `stageKnowledgeChanges` | `migration` | maintain migration records, membership, evidence, and status. |
| `stageKnowledgeChanges` | `changeValidator` | validate projected cutover state before staged writes. |
| `stageKnowledgeChanges` | `queryEngine` | evaluate declarative validation patterns. |
| `applyMigrationCutover` | `graph` | apply graph live-status changes and restore graph state on failure. |
| `applyMigrationCutover` | `schema` | apply schema live-status changes and restore schema state on failure. |
| `applyMigrationCutover` | `constraints` | apply constraint live-status changes and restore constraint state on failure. |
| `applyMigrationCutover` | `migration` | derive the plan and commit applied or failed lifecycle status. |
| `applyMigrationCutover` | `changeValidator` | validate projected and actual cutover states. |
| `applyMigrationCutover` | `queryEngine` | evaluate declarative validation patterns. |
| `executeQuery` | `graph` | supply one coherent graph read view while writes are excluded. |
| `executeQuery` | `queryEngine` | evaluate the caller query specification. |
| `getObject` | `graph` | retrieve one graph object without mutation. |
| `listMigrations` | `migration` | read deterministic current migration records. |
| `getMigration` | `migration` | read one current migration record. |
| `validateGraph` | `graph` | read canonical graph state for validation. |
| `validateGraph` | `schema` | read schema state for validation. |
| `validateGraph` | `constraints` | read constraints for validation. |
| `validateGraph` | `migration` | read migrations and requested overlays for validation. |
| `validateGraph` | `queryEngine` | evaluate declarative validation patterns. |
| `validateGraph` | `changeValidator` | execute selected validation tracks. |
| `discoverAnchorTypes` | `graph` | count current objects by type and lifecycle. |
| `discoverAnchorTypes` | `schema` | read anchor type keys and descriptions. |
| `getSchemaPack` | `graph` | read requested live counts. |
| `getSchemaPack` | `schema` | read the selected schema closure. |
| `getSystemState` | `graph` | summarize graph population and staged candidates. |
| `getSystemState` | `schema` | summarize live and non-live schema state. |
| `getSystemState` | `constraints` | summarize constraint candidates. |
| `getSystemState` | `migration` | summarize current migration lifecycle state. |
| `getSystemState` | `jsonStorage` | list storage-scoped persisted snapshots. |
| `getSystemState` | `sqlStorage` | read durable ledger counts and pointers. |
| `exportSystemSnapshot` | `graph` | export the graph snapshot. |
| `exportSystemSnapshot` | `schema` | export the schema snapshot. |
| `exportSystemSnapshot` | `constraints` | export the constraint snapshot. |
| `exportSystemSnapshot` | `migration` | export the migration snapshot. |
| `persistSystemSnapshot` | `graph` | export graph state for the coordinated snapshot. |
| `persistSystemSnapshot` | `schema` | export schema state for the coordinated snapshot. |
| `persistSystemSnapshot` | `constraints` | export constraint state for the coordinated snapshot. |
| `persistSystemSnapshot` | `migration` | export migration state for the coordinated snapshot. |
| `persistSystemSnapshot` | `jsonStorage` | atomically write the coordinated snapshot document. |
| `listPersistedSnapshots` | `jsonStorage` | list persisted snapshot metadata. |
| `loadPersistedSnapshot` | `jsonStorage` | read and validate one persisted snapshot document. |
| `abandonMigration` | `graph` | prune only safe non-live graph candidates. |
| `abandonMigration` | `schema` | prune only safe non-live schema candidates. |
| `abandonMigration` | `constraints` | prune only safe non-live constraint candidates. |
| `abandonMigration` | `migration` | transition the selected migration to abandoned. |
| `replayLedger` | `graph` | replace graph state with the reconstructed result. |
| `replayLedger` | `schema` | replace schema state with the reconstructed result. |
| `replayLedger` | `constraints` | replace constraint state with the reconstructed result. |
| `replayLedger` | `migration` | replace migration state with the reconstructed result. |
| `replayLedger` | `sqlStorage` | read the selected ascending durable ledger window. |
| `verifyReplayFromLedger` | `graph` | compare current graph summary with isolated replay output without mutation. |
| `verifyReplayFromLedger` | `schema` | compare current schema summary with isolated replay output without mutation. |
| `verifyReplayFromLedger` | `constraints` | compare current constraint summary with isolated replay output without mutation. |
| `verifyReplayFromLedger` | `migration` | compare current migration summary with isolated replay output without mutation. |
| `verifyReplayFromLedger` | `changeValidator` | validate isolated reconstructed state. |
| `verifyReplayFromLedger` | `queryEngine` | evaluate validation patterns against isolated state. |
| `verifyReplayFromLedger` | `sqlStorage` | read the selected ledger window without changing it. |
| `listMigrationHistory` | `sqlStorage` | read migration-related ledger records in ledger order. |
| `flushLedgerFailures` | `sqlStorage` | retry queued records against durable ledger storage. |
| `restoreFromSnapshot` | `graph` | replace graph state from the validated snapshot. |
| `restoreFromSnapshot` | `schema` | replace schema state from the validated snapshot. |
| `restoreFromSnapshot` | `constraints` | replace constraint state from the validated snapshot. |
| `restoreFromSnapshot` | `migration` | replace migration state from the validated snapshot. |
| `restoreFromSnapshot` | `sqlStorage` | preserve or record the ledger cursor as requested. |
| `applyLiveGraphChanges` | `ledger` | record the resolved request and its applied, rejected, failed, or degraded outcome. |
| `stageKnowledgeChanges` | `ledger` | record the migration-scoped staging outcome. |
| `applyMigrationCutover` | `ledger` | record applied or failed cutover status after restoration handling. |
| `getSystemState` | `ledger` | report durable and queued ledger state without mutation. |
| `exportSystemSnapshot` | `ledger` | capture the represented ledger cursor and transaction identity. |
| `persistSystemSnapshot` | `ledger` | capture the represented cursor and record the persistence outcome. |
| `abandonMigration` | `ledger` | record the abandonment outcome after candidate handling. |
| `replayLedger` | `ledger` | reconstruct from the selected monotonic ledger window without recording replayed requests again. |
| `verifyReplayFromLedger` | `ledger` | read the source replay window without replacing current state or appending replayed activity. |
| `listMigrationHistory` | `ledger` | return migration events in ledger order without mutation. |
| `flushLedgerFailures` | `ledger` | remove only queued outcomes that become durable and retain remaining failures. |
| `restoreFromSnapshot` | `ledger` | restore the represented cursor and record restoration only when requested. |

## Invariants and behavioral obligations

| Stable ID | Modeled obligation |
|---|---|
| `contract.rtg.controller.live_mutation_flow` | Normalize references, construct a projected state, validate it in strict mode, apply only an accepted projection, restore all touched component state on apply failure, then expose the ledger outcome. |
| `contract.rtg.controller.live_mutation_lane` | The live lane accepts live anchor, data-object, and link writes, associations, dissociations, deletes, and live replacements. It rejects schema, constraint, migration, non-live candidate creation, and requests that make graph objects non-live. strict is the default; skip bypasses change validation only and never lower-store invariants. |
| `contract.rtg.controller.staging_flow` | Staging accepts migration-scoped non-live graph, schema, and constraint candidates plus migration records, evidence, and permitted status changes. It rejects direct live schema/constraint writes, unscoped candidates, and live-status flips reserved for cutover. Strict mode validates the projected cutover before any write. A successful result has status applied and details keys operation_effect=staged_candidates_written, requires_cutover, staged_migration_ids, and candidate_counts with schema, constraints, and graph counts. |
| `contract.rtg.controller.validation_flow` | Resolve the request exactly as a write would, validate the projected state, return generated identities and resolved changes, and mutate neither component state nor the controller ledger. |
| `contract.rtg.controller.cutover_flow` | Read the selected migration membership, snapshot coordinated state, apply make-live and make-non-live changes in reference-safe order, validate the result, and either commit an applied status or restore the snapshot and record failed status. |
| `contract.rtg.controller.cutover_sequence` | Under the write lock: derive the plan from the selected migration; validate the projected state; capture a coordinated preimage; make schema and constraint changes, with make-non-live before make-live for a type key; make graph live changes; validate actual state; optionally prune retired records; then remove the completed migration. Any failure restores the preimage, marks the migration failed when safe, and records cutover_failed. |
| `contract.rtg.controller.abandonment_flow` | Applied migrations cannot be abandoned. Draft, ready, or failed work becomes abandoned; only non-live make-live candidates unshared by another migration may be pruned. Live records and make-non-live targets are never deleted. details.pruned_candidates groups removed IDs under schema, constraints, and graph; details.skipped_candidates groups retained IDs under the same keys and gives each a reason of shared, missing, or live. |
| `contract.rtg.controller.stable_query_flow` | Execute each query while writes are excluded so the query engine receives one coherent graph read view; query execution does not append a mutation record. |
| `contract.rtg.controller.read_semantics` | Query defaults to live-only at the controller boundary unless explicit query options override it. Direct object reads do not lifecycle-filter. Migration reads are deterministically ordered. All reads queue behind cutover, restore, and replay mutation and never append mutation ledger records. |
| `contract.rtg.controller.discovery_semantics` | Discovery composes schema-owned descriptions with graph counts, excludes non-live definitions by default, and applies a positive optional limit. Schema packs contain selected anchors, associated-data schemas, participating links, and live counts when requested. |
| `contract.rtg.controller.system_state_semantics` | State classification is exactly empty, schema_only, populated, has_staged_work, or needs_replay. liveSchemaCounts has anchor, data_object, and link counts; liveObjectCounts groups counts by object kind and type key; nonLiveCandidateCounts has schema, constraints, and graph totals; migrationCountsByStatus has draft, ready, failed, applied, and abandoned totals. The result also reports storage-scoped snapshot paths, ledger pointers/count, stable workflow identifiers, and advisory next steps without mutation. |
| `contract.rtg.controller.snapshot_flow` | Export graph, schema, constraint, and migration snapshots together with the represented ledger cursor and transaction identity from one visible controller state. |
| `contract.rtg.controller.persisted_snapshot_semantics` | Persist writes the coordinated snapshot atomically through JSON storage. List and load expose only valid snapshot-like JSON documents below that storage root; load validates but does not apply the snapshot. |
| `contract.rtg.controller.restore_flow` | Validate all supplied component snapshots before replacement, expose no partially restored state, and honor the requested ledger recording mode. |
| `contract.rtg.controller.replay_flow` | Start from empty or explicitly supplied snapshot state, replay resolved mutating requests after the selected cursor through the optional stop cursor in ledger order, and keep replay itself ledger-silent. The replay_applied result details contain ledger_records_seen, mutating_requests_replayed, and replay_window. |
| `contract.rtg.controller.replay_selection` | Exactly zero or one start snapshot source is supplied. Replay starts after the explicit cursor or the snapshot cursor, stops at an optional inclusive through cursor, processes ascending ledger positions, reuses recorded resolved identities, and replays only accepted mutating outcomes; rejected and rolled-back requests and read-only calls have no reconstruction effect. |
| `contract.rtg.controller.replay_verification` | Replay verification uses isolated scratch state, returns replay_verified with seed/result summaries, count differences, replay-window details, records seen, requests replayed, and post-replay validation, then leaves current state and source ledger unchanged. |
| `contract.rtg.controller.migration_history` | Migration history reconstructs staged, cutover_applied, cutover_failed, and abandoned events in ledger order even when terminal migration records are absent from the current migration store. |
| `contract.rtg.controller.ledger_failure_semantics` | Failed audit records retain request/response/error kind, original JSON payload, failure text, retry count, timestamps, transaction identity, and any reserved position. Flush retries in original order, removes only durable successes, and reports ledger_failures_flushed with integer details.flushed and details.remaining counts rather than raising for records that remain unavailable. |
| `contract.rtg.controller.operation_results` | State-changing results use only applied, cutover_applied, cutover_failed, migration_abandoned, snapshot_persisted, restore_applied, replay_applied, or ledger_failures_flushed. Zero visible state change reports zero applied counts; validationReport is absent when skipped; details carries operation-specific JSON-safe evidence. |
| `contract.rtg.controller.ledger_outcomes` | Every controller call has a UUID transaction identity. Durable ledger success advances the monotonic cursor; a ledger failure after a state effect is returned as degraded audit state and queued for explicit flush. |
| `invariant.rtg.controller.public_contracts_only` | Lower components are used only through public contracts. |
| `invariant.rtg.controller.no_transport_ownership` | Controller owns no MCP, REST, CLI, SDK, or UI transport. |
| `invariant.rtg.controller.validates_before_required_mutation` | Strict mutation validates the projected state before apply. |
| `invariant.rtg.controller.strict_validation_default` | Normal mutation defaults to strict validation. |
| `invariant.rtg.controller.live_graph_lane_excludes_knowledge_engineering` | Live CRUD excludes schema, constraint, migration, and non-live work. |
| `invariant.rtg.controller.knowledge_changes_are_migration_scoped` | Non-live knowledge changes belong to active migration work. |
| `invariant.rtg.controller.cutover_is_only_live_flip_authority_for_staged_schema_constraints` | Cutover is the only authority for staged schema and constraint live flips. |
| `invariant.rtg.controller.normalized_batches_are_internal_controller_plans` | Normalized batches are internal plans, not a generic public mutation backdoor. |
| `invariant.rtg.controller.schema_constraint_changes_use_migrations` | Schema and constraint writes use migration workflows. |
| `invariant.rtg.controller.schema_constraint_deletion_uses_migrations` | Schema and constraint retirement/deletion uses migration workflows. |
| `invariant.rtg.controller.non_live_candidates_are_migration_scoped` | Non-live candidates are referenced by active migration membership. |
| `invariant.rtg.controller.system_invariants_owned` | Cross-component invariants are enforced by the controller. |
| `invariant.rtg.controller.validation_report_authoritative` | Blocking validation findings control strict acceptance. |
| `invariant.rtg.controller.snapshot_uses_component_snapshots` | Coordinated snapshots are assembled through component snapshot contracts. |
| `invariant.rtg.controller.snapshot_json_serializable` | Exported system snapshots are JSON-serializable. |
| `invariant.rtg.controller.snapshot_records_ledger_position` | Snapshots identify the represented ledger position and transaction. |
| `invariant.rtg.controller.persisted_snapshot_readback_is_storage_scoped` | Snapshot readback is limited to JSON storage documents. |
| `invariant.rtg.controller.cutover_uses_migration_membership` | Cutover applies exactly the selected migration membership. |
| `invariant.rtg.controller.reads_do_not_observe_transient_cutover` | Reads do not observe transient cutover, restore, or replay state. |
| `invariant.rtg.controller.projected_queries_use_live_overlay` | Projected validation uses explicit live-status overlays. |
| `invariant.rtg.controller.cutover_restores_on_failure` | Failed cutover restores the pre-cutover visible state. |
| `invariant.rtg.controller.failed_cutover_is_legible` | Failed cutover records actionable diagnostic status. |
| `invariant.rtg.controller.failed_cutover_replay_preserves_status` | Replay reproduces recorded failed-cutover status. |
| `invariant.rtg.controller.cutover_order` | Cutover ordering preserves referenced state and validation. |
| `invariant.rtg.controller.abandonment_never_deletes_live_records` | Abandonment never deletes live records. |
| `invariant.rtg.controller.one_write_at_a_time` | Only one controller write mutates system or ledger state at a time. |
| `invariant.rtg.controller.ledger_records_black_box_activity` | Ledger records controller requests, results, and visible failures. |
| `invariant.rtg.controller.ledger_payloads_are_json_text` | Ledger request, response, and error payloads are JSON text. |
| `invariant.rtg.controller.transaction_id_always_assigned` | Every controller operation receives a transaction identifier. |
| `invariant.rtg.controller.transaction_ids_are_uuids` | Transaction identifiers are UUIDs. |
| `invariant.rtg.controller.ledger_position_is_replay_cursor` | Ledger position is monotonic and is the replay cursor. |
| `invariant.rtg.controller.resolved_uuids_before_ledger` | Batch-local references are resolved before durable ledger recording. |
| `invariant.rtg.controller.write_atomicity_scoped` | Failed normalized apply restores touched component state within the controller scope. |
| `invariant.rtg.controller.reads_mediated` | Application reads pass through controller public contracts. |
| `invariant.rtg.controller.live_flips_via_full_record_write` | Live-status changes preserve complete public records. |
| `invariant.rtg.controller.graph_type_is_schema_type_key` | Graph object type values correspond to schema type keys. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgControllerValidationTrackChoice` | `attribute` | — | Externally encoded as either the literal "all" or a non-empty unique ordered list of RtgValidationTrack literals. |
| `RtgControllerValidationOptions` | `attribute` | `tracks[0..1]: RtgControllerValidationTrackChoice`, `findingLimit[0..1]: Integer` | Omitted tracks means "all" and an absent finding limit means unlimited; a present limit is positive and limits returned findings without changing acceptance. |
| `RtgControllerCutoverOptions` | `attribute` | `validationMode: RtgControllerValidationMode` = `RtgControllerValidationMode::strict`, `pruneRetired: Boolean` = `true`, `failureRestore: RtgControllerFailureRestore` = `RtgControllerFailureRestore::restorePreCutoverSnapshot` | Defined by its typed fields and action requirements. |
| `RtgControllerDiscoveryOptions` | `attribute` | `includeNonLive: Boolean` = `false`, `limit[0..1]: Integer` | Defined by its typed fields and action requirements. |
| `RtgControllerSchemaPackOptions` | `attribute` | `live[0..1]: Boolean` = `true`, `includeLiveCounts: Boolean` = `true` | Defined by its typed fields and action requirements. |
| `RtgControllerReplayOptions` | `attribute` | `startSnapshot[0..1]: RtgSystemSnapshot`, `startSnapshotPath[0..1]: JsonRelativePath`, `afterLedgerPosition[0..1]: Integer`, `throughLedgerPosition[0..1]: Integer` | Defined by its typed fields and action requirements. |
| `RtgControllerRestoreOptions` | `attribute` | `ledgerMode: RtgControllerLedgerMode` = `RtgControllerLedgerMode::record` | Defined by its typed fields and action requirements. |
| `RtgControllerAppliedChanges` | `attribute` | `graphWrites: Integer`, `schemaWrites: Integer`, `constraintWrites: Integer`, `migrationWrites: Integer`, `deletes: Integer`, `liveStatusChanges: Integer` | Defined by its typed fields and action requirements. |
| `RtgControllerOperationResult` | `attribute` | `status: RtgControllerOperationStatus`, `transactionId: Uuid`, `ledgerPosition[0..1]: Integer`, `appliedChanges: RtgControllerAppliedChanges`, `validationReport[0..1]: RtgValidationReport`, `snapshot[0..1]: RtgSystemSnapshot`, `details: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgControllerLiveGraphValidationResult` | `attribute` | `status: RtgControllerValidationStatus`, `mutationState: RtgControllerMutationState`, `accepted: Boolean`, `generatedIds: JsonObject`, `resolvedGraphChanges: RtgGraphChangeSet`, `validationReport: RtgValidationReport` | generatedIds maps each request-local reference to its resolved UUID exactly as apply would. |
| `RtgControllerReplayVerificationResult` | `attribute` | `status: RtgControllerReplayVerificationStatus`, `ledgerRecordsSeen: Integer`, `mutatingRequestsReplayed: Integer`, `replayWindow: JsonObject`, `preSummary: JsonObject`, `postSummary: JsonObject`, `countDiffs: JsonObject`, `validationReport: RtgValidationReport` | Defined by its typed fields and action requirements. |
| `RtgControllerMigrationHistoryEvent` | `attribute` | `eventType: RtgControllerMigrationEventType`, `migrationId: String`, `description[0..1]: String`, `transactionId: Uuid`, `ledgerPosition: Integer`, `status: String`, `recordedAt: Timestamp`, `summary: String` | Defined by its typed fields and action requirements. |
| `RtgControllerMigrationHistory` | `attribute` | `events[0..*]: RtgControllerMigrationHistoryEvent` | Defined by its typed fields and action requirements. |
| `RtgControllerLedgerFailureRecord` | `attribute` | `transactionId: Uuid`, `ledgerPosition[0..1]: Integer`, `operationName: String`, `recordKind: RtgControllerLedgerRecordKind`, `payloadJson: String`, `failureMessage: String`, `retryCount: Integer`, `firstFailedTimestamp: Timestamp`, `lastFailedTimestamp: Timestamp` | Defined by its typed fields and action requirements. |
| `RtgControllerLedger` | `item` | `position: Integer`, `queuedFailures[0..*]: RtgControllerLedgerFailureRecord` | Defined by its typed fields and action requirements. |
| `RtgSystemSnapshot` | `attribute` | `graph: RtgGraphSnapshot`, `schema: RtgSchemaSnapshot`, `constraints: RtgConstraintSnapshot`, `migration: RtgMigrationSnapshot`, `lastLedgerPosition[0..1]: Integer`, `lastTransactionId[0..1]: Uuid`, `lastTransactionTimestamp[0..1]: Timestamp` | Defined by its typed fields and action requirements. |
| `RtgAnchorTypeDiscoveryEntry` | `attribute` | `typeKey: String`, `description: String`, `liveCount: Integer` | Defined by its typed fields and action requirements. |
| `RtgAnchorTypeDiscoveryResult` | `attribute` | `anchorTypes[0..*]: RtgAnchorTypeDiscoveryEntry` | Defined by its typed fields and action requirements. |
| `RtgControllerSchemaPack` | `attribute` | `schemaPack: RtgSchemaPack`, `liveCounts: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgPersistedSnapshotMetadata` | `attribute` | `relativePath: JsonRelativePath`, `sizeBytes: Integer`, `modifiedAt: Timestamp` | Defined by its typed fields and action requirements. |
| `RtgControllerSystemState` | `attribute` | `stateClassification: RtgControllerStateClassification`, `liveSchemaCounts: JsonObject`, `liveObjectCounts: JsonObject`, `nonLiveCandidateCounts: JsonObject`, `migrationCountsByStatus: JsonObject`, `migrationCountsScope: RtgControllerMigrationCountScope` = `RtgControllerMigrationCountScope::currentMigrationStore`, `migrationHistoryHint[0..1]: String`, `persistedSnapshotPaths[0..*]: JsonRelativePath`, `ledgerRecordCount: Integer`, `lastLedgerPosition[0..1]: Integer`, `lastTransactionId[0..1]: Uuid`, `recommendedWorkflows[0..*]: RtgControllerWorkflow`, `recommendedNextSteps[0..*]: String` | Defined by its typed fields and action requirements. |
| `RtgPersistedSnapshotList` | `attribute` | `snapshots[0..*]: RtgPersistedSnapshotMetadata` | Defined by its typed fields and action requirements. |
| `RtgPersistedSnapshotDocument` | `attribute` | `relativePath: JsonRelativePath`, `snapshot: RtgSystemSnapshot` | Defined by its typed fields and action requirements. |
| `RtgControllerConfigurationInvalid` | `attribute` | `message: String`, `diagnostic: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgControllerValidationFailed` | `attribute` | `message: String`, `transactionId[0..1]: Uuid`, `validationReport[0..1]: RtgValidationReport`, `diagnostic: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgControllerPreconditionFailed` | `attribute` | `message: String`, `diagnostic: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgControllerApplyFailed` | `attribute` | `message: String`, `diagnostic: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgControllerObjectNotFound` | `attribute` | `message: String`, `diagnostic: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgControllerDiscoveryFailed` | `attribute` | `message: String`, `diagnostic: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgControllerSnapshotFailed` | `attribute` | `message: String`, `diagnostic: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgControllerReplayFailed` | `attribute` | `message: String`, `diagnostic: JsonObject` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Model and external values |
|---|---|
| `RtgControllerValidationMode` | `strict`, `skip` |
| `RtgControllerFailureRestore` | `restorePreCutoverSnapshot` → `restore_pre_cutover_snapshot` |
| `RtgControllerLedgerMode` | `record`, `skip` |
| `RtgControllerOperationStatus` | `applied`, `cutoverApplied` → `cutover_applied`, `cutoverFailed` → `cutover_failed`, `migrationAbandoned` → `migration_abandoned`, `snapshotPersisted` → `snapshot_persisted`, `restoreApplied` → `restore_applied`, `replayApplied` → `replay_applied`, `ledgerFailuresFlushed` → `ledger_failures_flushed` |
| `RtgControllerValidationStatus` | `validated` |
| `RtgControllerReplayVerificationStatus` | `replayVerified` → `replay_verified` |
| `RtgControllerMutationState` | `notMutated` → `not_mutated` |
| `RtgControllerStateClassification` | `empty`, `schemaOnly`, `populated`, `hasStagedWork`, `needsReplay` |
| `RtgControllerWorkflow` | `schemaBootstrap`, `dataIngest`, `queryAnswer`, `safeUpdate`, `snapshotReplayCheck`, `stagedWorkReview`, `replayRecovery` |
| `RtgControllerMigrationCountScope` | `currentMigrationStore` → `current_migration_store` |
| `RtgControllerLedgerRecordKind` | `request`, `response`, `error` |
| `RtgControllerMigrationEventType` | `staged`, `cutoverApplied` → `cutover_applied`, `cutoverFailed` → `cutover_failed`, `abandoned` |

## Verification

| Verification | Objectives | Evidence |
|---|---|---|
| `RtgControllerBoundaryVerification` | `liveMutationFlow`, `liveMutationLane`, `stagingFlow`, `validationFlow`, `cutoverFlow`, `cutoverSequence`, `abandonmentFlow`, `stableQueryFlow`, `controllerReadSemantics`, `discoverySemantics`, `systemStateSemantics`, `coordinatedSnapshotFlow`, `persistedSnapshotSemantics`, `restoreFlow`, `replayFlow`, `replaySelection`, `replayVerification`, `migrationHistorySemantics`, `ledgerFailureSemantics`, `operationResultSemantics`, `ledgerOutcomeFlow`, `publicContractsOnly`, `noTransportOwnership`, `validatesBeforeRequiredMutation`, `strictValidationDefault`, `liveGraphLaneExcludesKnowledgeEngineering`, `knowledgeChangesMigrationScoped`, `cutoverOnlyLiveFlipAuthority`, `normalizedBatchesInternalPlans`, `schemaConstraintChangesUseMigrations`, `schemaConstraintDeletionUsesMigrations`, `nonLiveCandidatesMigrationScoped`, `systemInvariantsOwned`, `validationReportAuthoritative`, `snapshotUsesComponentSnapshots`, `snapshotJsonSerializable`, `snapshotRecordsLedgerPosition`, `persistedSnapshotStorageScoped`, `cutoverUsesMigrationMembership`, `readsHideTransientState`, `projectedQueriesUseLiveOverlay`, `cutoverRestoresOnFailure`, `failedCutoverLegible`, `failedCutoverReplayPreservesStatus`, `cutoverOrder`, `abandonmentNeverDeletesLive`, `oneWriteAtATime`, `ledgerRecordsBlackBoxActivity`, `ledgerPayloadsJsonText`, `transactionIdAlwaysAssigned`, `transactionIdsUuids`, `ledgerPositionReplayCursor`, `resolvedUuidsBeforeLedger`, `writeAtomicityScoped`, `readsMediated`, `liveFlipsViaFullRecordWrite`, `graphTypeIsSchemaTypeKey` | `components/rtg/controller/tests/test_rtg_controller_contract.py` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
