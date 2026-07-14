# component.rtg.controller

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

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
| `getObject` | `ControllerGetObject` | in `objectUuid: String`; out `object: RtgObject` | `RtgControllerObjectNotFound` | Normalize UUID text and return the public graph record without lifecycle filtering; invalid and absent UUIDs are reported through the controller-owned not-found contract. |
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
| `getSystemState` | `sqlStorage` | `dependency` | read durable ledger counts and pointers. |
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
| `replayLedger` | `graph` | `dependency` | replace graph state with the reconstructed result. |
| `replayLedger` | `schema` | `dependency` | replace schema state with the reconstructed result. |
| `replayLedger` | `constraints` | `dependency` | replace constraint state with the reconstructed result. |
| `replayLedger` | `migration` | `dependency` | replace migration state with the reconstructed result. |
| `replayLedger` | `sqlStorage` | `dependency` | read the selected ascending durable ledger window. |
| `verifyReplayFromLedger` | `graph` | `dependency` | compare current graph summary with isolated replay output without mutation. |
| `verifyReplayFromLedger` | `schema` | `dependency` | compare current schema summary with isolated replay output without mutation. |
| `verifyReplayFromLedger` | `constraints` | `dependency` | compare current constraint summary with isolated replay output without mutation. |
| `verifyReplayFromLedger` | `migration` | `dependency` | compare current migration summary with isolated replay output without mutation. |
| `verifyReplayFromLedger` | `changeValidator` | `dependency` | validate isolated reconstructed state. |
| `verifyReplayFromLedger` | `queryEngine` | `dependency` | evaluate validation patterns against isolated state. |
| `verifyReplayFromLedger` | `sqlStorage` | `dependency` | read the selected ledger window without changing it. |
| `listMigrationHistory` | `sqlStorage` | `dependency` | read migration-related ledger records in ledger order. |
| `flushLedgerFailures` | `sqlStorage` | `dependency` | retry queued records against durable ledger storage. |
| `restoreFromSnapshot` | `graph` | `dependency` | replace graph state from the validated snapshot. |
| `restoreFromSnapshot` | `schema` | `dependency` | replace schema state from the validated snapshot. |
| `restoreFromSnapshot` | `constraints` | `dependency` | replace constraint state from the validated snapshot. |
| `restoreFromSnapshot` | `migration` | `dependency` | replace migration state from the validated snapshot. |
| `restoreFromSnapshot` | `sqlStorage` | `dependency` | preserve or record the ledger cursor as requested. |
| `applyLiveGraphChanges` | `ledger` | `write` | record the resolved request and its applied, rejected, failed, or degraded outcome. |
| `stageKnowledgeChanges` | `ledger` | `write` | record the migration-scoped staging outcome. |
| `applyMigrationCutover` | `ledger` | `write` | record applied or failed cutover status after restoration handling. |
| `getSystemState` | `ledger` | `read` | report durable and queued ledger state without mutation. |
| `exportSystemSnapshot` | `ledger` | `read` | capture the represented ledger cursor and transaction identity. |
| `persistSystemSnapshot` | `ledger` | `write` | capture the represented cursor and record the persistence outcome. |
| `abandonMigration` | `ledger` | `write` | record the abandonment outcome after candidate handling. |
| `replayLedger` | `ledger` | `read` | reconstruct from the selected monotonic ledger window without recording replayed requests again. |
| `verifyReplayFromLedger` | `ledger` | `read` | read the source replay window without replacing current state or appending replayed activity. |
| `listMigrationHistory` | `ledger` | `read` | return migration events in ledger order without mutation. |
| `flushLedgerFailures` | `ledger` | `write` | remove only queued outcomes that become durable and retain remaining failures. |
| `restoreFromSnapshot` | `ledger` | `write` | restore the represented cursor and record restoration only when requested. |
| `validateLiveGraphChanges` | `ledger` | `noStateEffect` | validation neither reads nor changes durable or queued ledger state. |
| `executeQuery` | `ledger` | `noStateEffect` | query execution does not append, replace, or inspect mutation ledger state. |
| `getObject` | `ledger` | `noStateEffect` | object reads have no ledger state effect. |
| `listMigrations` | `ledger` | `noStateEffect` | migration listing has no ledger state effect. |
| `getMigration` | `ledger` | `noStateEffect` | migration reads have no ledger state effect. |
| `validateGraph` | `ledger` | `noStateEffect` | whole-graph validation has no ledger state effect. |
| `discoverAnchorTypes` | `ledger` | `noStateEffect` | discovery reads have no ledger state effect. |
| `getSchemaPack` | `ledger` | `noStateEffect` | schema-pack reads have no ledger state effect. |
| `listPersistedSnapshots` | `ledger` | `noStateEffect` | persisted-snapshot listing has no controller-ledger state effect. |
| `loadPersistedSnapshot` | `ledger` | `noStateEffect` | loading without restoration has no controller-ledger state effect. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| `applyLiveGraphChanges` | `normalize: local`, `validateProjection: ValidateRtgChangeBatch`, `applyProjection: local`, `reject: local`, `restorePreimage: local`, `recordOutcome: local` | `first normalize then validateProjection;`; `first restorePreimage then recordOutcome;`; `first reject then recordOutcome;` |
| `applyMigrationCutover` | `derivePlan: local`, `validateProjection: ValidateRtgChangeBatch`, `capturePreimage: local`, `applyCutover: local`, `validateActualState: ValidateRtgChangeBatch`, `commitApplied: local`, `restorePreimage: local`, `recordFailed: local` | `first derivePlan then validateProjection;`; `first capturePreimage then applyCutover;`; `first restorePreimage then recordFailed;` |
| `executeQuery` | `evaluate: ExecuteRtgQuery` | — |
| `replayLedger` | `selectWindow: local`, `reconstructIsolated: local`, `validateReconstruction: ValidateRtgChangeBatch`, `replaceCurrentState: local` | `first selectWindow then reconstructIsolated;`; `first reconstructIsolated then validateReconstruction;` |
| `restoreFromSnapshot` | `projectSnapshot: local`, `validateSnapshot: ValidateRtgChangeBatch`, `replaceCoordinatedState: local`, `recordRestore: local` | `first projectSnapshot then validateSnapshot;`; `first replaceCoordinatedState then recordRestore;` |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.rtg.controller.live_mutation_flow` | `ApplyLiveGraphChanges` | `controller.applyLiveGraphChanges` | Normalize references, construct a projected state, validate it in strict mode, apply only an accepted projection, restore all touched component state on apply failure, then expose the ledger outcome. |
| `contract.rtg.controller.live_mutation_lane` | `ApplyLiveGraphChanges` | `controller.applyLiveGraphChanges` | The live lane accepts live anchor, data-object, and link writes, associations, dissociations, deletes, and live replacements. It rejects schema, constraint, migration, non-live candidate creation, and requests that make graph objects non-live. strict is the default; skip bypasses change validation only and never lower-store invariants. |
| `contract.rtg.controller.staging_flow` | `StageKnowledgeChanges` | `controller.stageKnowledgeChanges` | Staging accepts migration-scoped non-live graph, schema, and constraint candidates plus migration records, evidence, and permitted status changes. It rejects direct live schema/constraint writes, unscoped candidates, and live-status flips reserved for cutover. Strict mode validates the projected cutover before any write. A successful result has status applied and details keys operation_effect=staged_candidates_written, requires_cutover, staged_migration_ids, and candidate_counts with schema, constraints, and graph counts. |
| `contract.rtg.controller.validation_flow` | `ValidateLiveGraphChanges` | `controller.validateLiveGraphChanges` | Resolve the request exactly as a write would, validate the projected state, return generated identities and resolved changes, and mutate neither component state nor the controller ledger. |
| `contract.rtg.controller.cutover_flow` | `ApplyMigrationCutover` | `controller.applyMigrationCutover` | Read the selected migration membership, snapshot coordinated state, apply make-live and make-non-live changes in reference-safe order, validate the result, and either commit an applied status or restore the snapshot and record failed status. |
| `contract.rtg.controller.cutover_sequence` | `ApplyMigrationCutover` | `controller.applyMigrationCutover` | Under the write lock: derive the plan from the selected migration; validate the projected state; capture a coordinated preimage; make schema and constraint changes, with make-non-live before make-live for a type key; make graph live changes; validate actual state; optionally prune retired records; then remove the completed migration. Any failure restores the preimage, marks the migration failed when safe, and records cutover_failed. |
| `contract.rtg.controller.abandonment_flow` | `AbandonMigration` | `controller.abandonMigration` | Applied migrations cannot be abandoned. Draft, ready, or failed work becomes abandoned; only non-live make-live candidates unshared by another migration may be pruned. Live records and make-non-live targets are never deleted. details.pruned_candidates groups removed IDs under schema, constraints, and graph; details.skipped_candidates groups retained IDs under the same keys and gives each a reason of shared, missing, or live. |
| `contract.rtg.controller.stable_query_flow` | `ExecuteControllerQuery` | `controller.executeQuery` | Execute each query while writes are excluded so the query engine receives one coherent graph read view; query execution does not append a mutation record. |
| `contract.rtg.controller.read_semantics` | `RtgController` | `controller` | Query defaults to live-only at the controller boundary unless explicit query options override it. Direct object reads do not lifecycle-filter. Migration reads are deterministically ordered. All reads queue behind cutover, restore, and replay mutation and never append mutation ledger records. |
| `contract.rtg.controller.discovery_semantics` | `RtgController` | `controller` | Discovery composes schema-owned descriptions with graph counts, excludes non-live definitions by default, and applies a positive optional limit. Schema packs contain selected anchors, associated-data schemas, participating links, and live counts when requested. |
| `contract.rtg.controller.system_state_semantics` | `GetSystemState` | `controller.getSystemState` | State classification is exactly empty, schema_only, populated, has_staged_work, or needs_replay. liveSchemaCounts has anchor, data-object, link, and total definition counts; liveObjectCounts is the graph-owned ordered type-count list; nonLiveCandidateCounts has schema, constraints, graph, and total counts; migrationCountsByStatus has draft, ready, failed, applied, abandoned, and total counts. The result also reports storage-scoped snapshot paths, ledger pointers/count, stable workflow identifiers, and advisory next steps without mutation. Type names and snapshot metadata remain available through their dedicated discovery and snapshot-list actions. |
| `contract.rtg.controller.snapshot_flow` | `ExportSystemSnapshot` | `controller.exportSystemSnapshot` | Export graph, schema, constraint, and migration snapshots together with the represented ledger cursor and transaction identity from one visible controller state. |
| `contract.rtg.controller.persisted_snapshot_semantics` | `RtgController` | `controller` | Persist writes the coordinated snapshot atomically through JSON storage. List and load expose only valid snapshot-like JSON documents below that storage root; load validates but does not apply the snapshot. |
| `contract.rtg.controller.restore_flow` | `RestoreFromSnapshot` | `controller.restoreFromSnapshot` | Construct and semantically validate all four candidate component states before replacing any current component or the represented snapshot cursor. Success replaces the coordinated state as one serialized visible change. Failure preserves current component state; skip mode also preserves ledger state, while record mode may append request/error audit records and advance only the audit ledger pointer. |
| `contract.rtg.controller.replay_flow` | `ReplayLedger` | `controller.replayLedger` | Start from empty or an explicitly supplied structurally valid snapshot state, including a snapshot captured after a skip-mode mutation, replay resolved mutating requests after the selected cursor through the optional stop cursor in ledger order, and keep replay itself ledger-silent. Public restore remains semantically validating; rollback and replay may reinstate a previously visible skip-mode state so recovery does not strand it. The replay_applied result details contain ledger_records_seen, mutating_requests_replayed, and replay_window. |
| `contract.rtg.controller.replay_selection` | `ReplayLedger` | `controller.replayLedger` | Exactly zero or one start snapshot source is supplied. Replay starts after the explicit cursor or the snapshot cursor, stops at an optional inclusive through cursor, processes ascending ledger positions, reuses recorded resolved identities, and replays only accepted mutating outcomes; rejected and rolled-back requests and read-only calls have no reconstruction effect. |
| `contract.rtg.controller.replay_verification` | `VerifyReplayFromLedger` | `controller.verifyReplayFromLedger` | Replay verification uses isolated scratch component instances, never mutates the captured current instances, preserves the existing preSummary/postSummary/countDiffs meanings, and also reports start/replayed/live summaries, exact canonical graph-schema-constraint-migration digests and equality, separate ledger-cursor equality, live count differences, replay-window details, and post-replay validation. Accounting satisfies ledgerRecordsScanned = eligibleMutatingRequests + failedOrRejectedTransactionsSkipped + administrativeRecordsSkipped + terminalRecordsSkipped; requestRecordsSeen counts every request record independently, administrativeRecordsSkipped counts records for non-replayable operations, and terminalRecordsSkipped counts response/error records for replayable operations. Verification restores the exact captured instances and cursor metadata even when current domain state does not validate, and never appends ledger records. |
| `contract.rtg.controller.migration_history` | `ListMigrationHistory` | `controller.listMigrationHistory` | Migration history reconstructs one typed staged, staging_rejected, staging_failed, cutover_applied, cutover_failed, or abandoned event per affected migration in terminal-ledger order even when no migration record entered or remains in the current migration store. Every event reports accurate finding count and codes; successful events report zero findings. Rejected staging and validation-failed cutover retain their canonical validation reports, failed staging retains only recorded structured error information, and rejected staging is neither staged nor replayable. |
| `contract.rtg.controller.ledger_failure_semantics` | `FlushLedgerFailures` | `controller.flushLedgerFailures` | Failed audit records retain request/response/error kind, original JSON payload, failure text, retry count, timestamps, transaction identity, and any reserved position. Flush retries in original order, removes only durable successes, and reports ledger_failures_flushed with integer details.flushed and details.remaining counts rather than raising for records that remain unavailable. |
| `contract.rtg.controller.operation_results` | `RtgController` | `controller` | State-changing results use only applied, cutover_applied, cutover_failed, migration_abandoned, snapshot_persisted, restore_applied, replay_applied, or ledger_failures_flushed. generatedIds maps every request-local reference resolved by that operation and is empty when none are generated. Zero visible state change reports zero applied counts; validationReport is absent when skipped; details carries operation-specific JSON-safe evidence. |
| `contract.rtg.controller.ledger_outcomes` | `RtgController` | `controller` | Every controller call has a UUID transaction identity. Durable ledger success advances the monotonic cursor; a ledger failure after a state effect is returned as degraded audit state and queued for explicit flush. |
| `invariant.rtg.controller.public_contracts_only` | `RtgController` | `controller` | Lower components are used only through public contracts. |
| `invariant.rtg.controller.no_transport_ownership` | `RtgController` | `controller` | Controller owns no MCP, REST, CLI, SDK, or UI transport. |
| `contract.rtg.controller.intentional_boundary` | `RtgController` | `controller` | The controller owns cross-component sequencing, recovery, and audit outcomes, not lower-store records or algorithms. It owns no authentication/authorization, UI or transport, snapshot filesystem mechanics, replication/deployment topology, distributed lock, SQL engine behavior, or distributed transaction guarantee. Curated discovery-view state remains outside v1. |
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
| `invariant.rtg.controller.snapshot_records_ledger_position` | `RtgController` | `controller` | Snapshots identify the represented ledger position and transaction. |
| `invariant.rtg.controller.persisted_snapshot_readback_is_storage_scoped` | `RtgController` | `controller` | Snapshot readback is limited to JSON storage documents. |
| `invariant.rtg.controller.cutover_uses_migration_membership` | `RtgController` | `controller` | Cutover applies exactly the selected migration membership. |
| `invariant.rtg.controller.reads_do_not_observe_transient_cutover` | `RtgController` | `controller` | Reads do not observe transient cutover, restore, or replay state. |
| `invariant.rtg.controller.projected_queries_use_live_overlay` | `RtgController` | `controller` | Projected validation uses explicit live-status overlays. |
| `invariant.rtg.controller.cutover_restores_on_failure` | `RtgController` | `controller` | Failed cutover restores the pre-cutover visible state. |
| `invariant.rtg.controller.failed_cutover_is_legible` | `RtgController` | `controller` | Failed cutover records actionable diagnostic status. |
| `invariant.rtg.controller.failed_cutover_replay_preserves_status` | `RtgController` | `controller` | Replay reproduces recorded failed-cutover status. |
| `invariant.rtg.controller.cutover_order` | `RtgController` | `controller` | Cutover ordering preserves referenced state and validation. |
| `invariant.rtg.controller.abandonment_never_deletes_live_records` | `RtgController` | `controller` | Abandonment never deletes live records. |
| `invariant.rtg.controller.one_write_at_a_time` | `RtgController` | `controller` | Only one controller write mutates system or ledger state at a time. |
| `invariant.rtg.controller.ledger_records_black_box_activity` | `RtgController` | `controller` | Ledger records controller requests, results, and visible failures. |
| `invariant.rtg.controller.ledger_payloads_are_json_text` | `RtgController` | `controller` | Ledger request, response, and error payloads are JSON text. |
| `invariant.rtg.controller.transaction_id_always_assigned` | `RtgController` | `controller` | Every controller operation receives a transaction identifier. |
| `invariant.rtg.controller.transaction_ids_are_uuids` | `RtgController` | `controller` | Transaction identifiers are UUIDs. |
| `invariant.rtg.controller.ledger_position_is_replay_cursor` | `RtgController` | `controller` | Ledger position is monotonic and is the replay cursor. |
| `invariant.rtg.controller.resolved_uuids_before_ledger` | `RtgController` | `controller` | Batch-local references are resolved before durable ledger recording. |
| `invariant.rtg.controller.write_atomicity_scoped` | `RtgController` | `controller` | Failed normalized apply restores touched component state within the controller scope. |
| `invariant.rtg.controller.reads_mediated` | `RtgController` | `controller` | Application reads pass through controller public contracts. |
| `invariant.rtg.controller.live_flips_via_full_record_write` | `RtgController` | `controller` | Live-status changes preserve complete public records. |
| `invariant.rtg.controller.graph_type_is_schema_type_key` | `RtgController` | `controller` | Graph object type values correspond to schema type keys. |
| `contract.rtg.controller.apply_live_graph_changes.failures` | `ApplyLiveGraphChanges` | `controller.applyLiveGraphChanges` | Strict rejection has no graph effect; apply failure restores touched component state and remains visible in the ledger outcome. |
| `contract.rtg.controller.validate_live_graph_changes.failures` | `ValidateLiveGraphChanges` | `controller.validateLiveGraphChanges` | Every rejected validation attempt leaves component state and ledger unchanged and receives no controller transaction identifier. |
| `contract.rtg.controller.stage_knowledge_changes.failures` | `StageKnowledgeChanges` | `controller.stageKnowledgeChanges` | Rejected staging has no effect; failed apply restores touched state and records the visible outcome. |
| `contract.rtg.controller.apply_migration_cutover.failures` | `ApplyMigrationCutover` | `controller.applyMigrationCutover` | A failed cutover restores the pre-cutover visible state and records a legible failed outcome. |
| `contract.rtg.controller.execute_controller_query.failures` | `ExecuteControllerQuery` | `controller.executeQuery` | Query failures have no component or ledger effect. |
| `contract.rtg.controller.controller_get_object.failures` | `ControllerGetObject` | `controller.getObject` | Invalid UUID text or an absent graph object produces RtgControllerObjectNotFound with corrective diagnostics and has no state or ledger effect. |
| `contract.rtg.controller.controller_list_migrations.failures` | `ControllerListMigrations` | `controller.listMigrations` | Listing has no state or ledger effect. |
| `contract.rtg.controller.controller_get_migration.failures` | `ControllerGetMigration` | `controller.getMigration` | Read failure has no state or ledger effect. |
| `contract.rtg.controller.validate_graph.failures` | `ValidateGraph` | `controller.validateGraph` | Validation has no component or ledger effect. |
| `contract.rtg.controller.discover_anchor_types.failures` | `DiscoverAnchorTypes` | `controller.discoverAnchorTypes` | Discovery has no state or ledger effect. |
| `contract.rtg.controller.get_controller_schema_pack.failures` | `GetControllerSchemaPack` | `controller.getSchemaPack` | Schema-pack reads have no state or ledger effect. |
| `contract.rtg.controller.get_system_state.failures` | `GetSystemState` | `controller.getSystemState` | System-state inspection has no state or ledger effect. |
| `contract.rtg.controller.export_system_snapshot.failures` | `ExportSystemSnapshot` | `controller.exportSystemSnapshot` | Export returns one coordinated state and does not mutate components or ledger. |
| `contract.rtg.controller.persist_system_snapshot.failures` | `PersistSystemSnapshot` | `controller.persistSystemSnapshot` | Failure leaves no partial JSON document and remains visible as the operation outcome. |
| `contract.rtg.controller.list_persisted_snapshots.failures` | `ListPersistedSnapshots` | `controller.listPersistedSnapshots` | Listing is storage-scoped and has no state or ledger effect. |
| `contract.rtg.controller.load_persisted_snapshot.failures` | `LoadPersistedSnapshot` | `controller.loadPersistedSnapshot` | Loading does not restore or otherwise mutate current system state. |
| `contract.rtg.controller.abandon_migration.failures` | `AbandonMigration` | `controller.abandonMigration` | Abandonment never deletes live records; failure restores touched state and records the outcome. |
| `contract.rtg.controller.replay_ledger.failures` | `ReplayLedger` | `controller.replayLedger` | Ambiguous replay inputs are rejected and replay does not append replayed activity to the source ledger. |
| `contract.rtg.controller.verify_replay_from_ledger.failures` | `VerifyReplayFromLedger` | `controller.verifyReplayFromLedger` | Verification runs against isolated scratch state and has no current-state or source-ledger effect. |
| `contract.rtg.controller.list_migration_history.failures` | `ListMigrationHistory` | `controller.listMigrationHistory` | History inspection has no component or ledger effect. |
| `contract.rtg.controller.flush_ledger_failures.failures` | `FlushLedgerFailures` | `controller.flushLedgerFailures` | Successfully durable queued outcomes are removed; remaining failures stay queued and legible in the result rather than raising. |
| `contract.rtg.controller.restore_from_snapshot.failures` | `RestoreFromSnapshot` | `controller.restoreFromSnapshot` | Invalid or failed restoration does not expose a partially restored coordinated state. |
| `contract.rtg.controller.open_rtg_controller.failures` | `OpenRtgController` | `openRtgControllerSubject` | Invalid or incompatible dependencies do not return a partially usable controller. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgControllerValidationOptions` | `attribute` | `selection: RtgValidationTrackSelection` = `RtgValidationTrackSelection::'all'`, `tracks[0..*]: RtgValidationTrack`, `findingLimit[0..1]: Integer` | Controller validation uses the same canonical track-selection and finding-limit semantics as change validation. |
| `RtgControllerCutoverOptions` | `attribute` | `validationMode: RtgControllerValidationMode` = `RtgControllerValidationMode::strict`, `pruneRetired: Boolean` = `true`, `failureRestore: RtgControllerFailureRestore` = `RtgControllerFailureRestore::restore_pre_cutover_snapshot` | Defined by its typed fields and action requirements. |
| `RtgControllerDiscoveryOptions` | `attribute` | `includeNonLive: Boolean` = `false`, `limit[0..1]: Integer` | Defined by its typed fields and action requirements. |
| `RtgControllerSchemaPackOptions` | `attribute` | `live[0..1]: Boolean` = `true`, `includeLiveCounts: Boolean` = `true` | Defined by its typed fields and action requirements. |
| `RtgControllerReplayOptions` | `attribute` | `startSnapshot[0..1]: RtgSystemSnapshot`, `startSnapshotPath[0..1]: JsonRelativePath`, `afterLedgerPosition[0..1]: Integer`, `throughLedgerPosition[0..1]: Integer` | Defined by its typed fields and action requirements. |
| `RtgControllerRestoreOptions` | `attribute` | `ledgerMode: RtgControllerLedgerMode` = `RtgControllerLedgerMode::record` | Defined by its typed fields and action requirements. |
| `RtgControllerAppliedChanges` | `attribute` | `graphWrites: Integer`, `schemaWrites: Integer`, `constraintWrites: Integer`, `migrationWrites: Integer`, `deletes: Integer`, `liveStatusChanges: Integer` | Defined by its typed fields and action requirements. |
| `RtgControllerOperationResult` | `attribute` | `status: RtgControllerOperationStatus`, `transactionId: Uuid`, `ledgerPosition[0..1]: Integer`, `appliedChanges: RtgControllerAppliedChanges`, `validationReport[0..1]: RtgValidationReport`, `snapshot[0..1]: RtgSystemSnapshot`, `details: JsonObject`, `generatedIds: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgControllerLiveGraphValidationResult` | `attribute` | `status: RtgControllerValidationStatus`, `mutationState: RtgControllerMutationState`, `accepted: Boolean`, `generatedIds: JsonObject`, `resolvedGraphChanges: RtgGraphChangeSet`, `validationReport: RtgValidationReport` | generatedIds maps each request-local reference to its resolved UUID exactly as apply would. |
| `RtgControllerReplayVerificationResult` | `attribute` | `status: RtgControllerReplayVerificationStatus`, `ledgerRecordsSeen: Integer`, `ledgerRecordsScanned: Integer`, `mutatingRequestsReplayed: Integer`, `replayWindow: JsonObject`, `preSummary: JsonObject`, `postSummary: JsonObject`, `countDiffs: JsonObject`, `startSummary: JsonObject`, `replayedSummary: JsonObject`, `liveSummary: JsonObject`, `replayDelta: JsonObject`, `liveCountDiffs: JsonObject`, `replayedStateDigest: String`, `liveStateDigest: String`, `stateEquivalentToLive: Boolean`, `ledgerCursorEquivalentToLive: Boolean`, `requestRecordsSeen: Integer`, `eligibleMutatingRequests: Integer`, `administrativeRecordsSkipped: Integer`, `terminalRecordsSkipped: Integer`, `failedOrRejectedTransactionsSkipped: Integer`, `validationReport: RtgValidationReport` | Defined by its typed fields and action requirements. |
| `RtgControllerMigrationHistoryEvent` | `attribute` | `eventType: RtgControllerMigrationEventType`, `migrationId: String`, `description[0..1]: String`, `transactionId: Uuid`, `ledgerPosition: Integer`, `status: String`, `recordedAt: Timestamp`, `summary: String`, `operationName: String`, `staged: Boolean`, `mutationState[0..1]: String`, `findingCount: Integer`, `findingCodes[0..*]: String`, `validationReport[0..1]: RtgValidationReport`, `error[0..1]: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgControllerMigrationHistory` | `attribute` | `events[0..*]: RtgControllerMigrationHistoryEvent` | Defined by its typed fields and action requirements. |
| `RtgControllerLedgerFailureRecord` | `attribute` | `transactionId: Uuid`, `ledgerPosition[0..1]: Integer`, `operationName: String`, `recordKind: RtgControllerLedgerRecordKind`, `payloadJson: String`, `failureMessage: String`, `retryCount: Integer`, `firstFailedTimestamp: Timestamp`, `lastFailedTimestamp: Timestamp` | Defined by its typed fields and action requirements. |
| `RtgControllerLedger` | `item` | `position: Integer`, `queuedFailures[0..*]: RtgControllerLedgerFailureRecord` | Defined by its typed fields and action requirements. |
| `RtgSystemSnapshot` | `attribute` | `graph: RtgGraphSnapshot`, `schema: RtgSchemaSnapshot`, `constraints: RtgConstraintSnapshot`, `migration: RtgMigrationSnapshot`, `lastLedgerPosition[0..1]: Integer`, `lastTransactionId[0..1]: Uuid`, `lastTransactionTimestamp[0..1]: Timestamp` | Defined by its typed fields and action requirements. |
| `RtgAnchorTypeDiscoveryEntry` | `attribute` | `typeKey: String`, `description: String`, `liveCount: Integer` | Defined by its typed fields and action requirements. |
| `RtgAnchorTypeDiscoveryResult` | `attribute` | `anchorTypes[0..*]: RtgAnchorTypeDiscoveryEntry` | Defined by its typed fields and action requirements. |
| `RtgControllerSchemaPack` | `attribute` | `schemaPack: RtgSchemaPack`, `liveCounts: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgPersistedSnapshotMetadata` | `attribute` | `relativePath: JsonRelativePath`, `sizeBytes: Integer`, `modifiedAt: Timestamp` | Defined by its typed fields and action requirements. |
| `RtgControllerSchemaCounts` | `attribute` | `anchor: Integer`, `dataObject: Integer`, `link: Integer`, `total: Integer` | Defined by its typed fields and action requirements. |
| `RtgControllerCandidateCounts` | `attribute` | `schema: Integer`, `constraints: Integer`, `graph: Integer`, `total: Integer` | Defined by its typed fields and action requirements. |
| `RtgControllerMigrationCounts` | `attribute` | `draft: Integer`, `ready: Integer`, `failed: Integer`, `applied: Integer`, `abandoned: Integer`, `total: Integer` | Defined by its typed fields and action requirements. |
| `RtgControllerSystemState` | `attribute` | `stateClassification: RtgControllerStateClassification`, `liveSchemaCounts: RtgControllerSchemaCounts`, `liveObjectCounts: RtgTypeCountList`, `nonLiveCandidateCounts: RtgControllerCandidateCounts`, `migrationCountsByStatus: RtgControllerMigrationCounts`, `migrationCountsScope: RtgControllerMigrationCountScope` = `RtgControllerMigrationCountScope::current_migration_store`, `migrationHistoryHint[0..1]: String`, `persistedSnapshotPaths[0..*] ordered: JsonRelativePath`, `ledgerRecordCount: Integer`, `lastLedgerPosition[0..1]: Integer`, `lastTransactionId[0..1]: Uuid`, `recommendedWorkflows[0..*]: RtgControllerWorkflow`, `recommendedNextSteps[0..*]: String` | Defined by its typed fields and action requirements. |
| `RtgPersistedSnapshotList` | `attribute` | `snapshots[0..*]: RtgPersistedSnapshotMetadata` | Defined by its typed fields and action requirements. |
| `RtgPersistedSnapshotDocument` | `attribute` | `relativePath: JsonRelativePath`, `snapshot: RtgSystemSnapshot` | Defined by its typed fields and action requirements. |
| `RtgControllerConfigurationInvalid` | `attribute` | `message: String`, `diagnostic[0..1]: RtgDiagnostic` | Defined by its typed fields and action requirements. |
| `RtgControllerValidationFailed` | `attribute` | `message: String`, `transactionId[0..1]: Uuid`, `validationReport[0..1]: RtgValidationReport`, `diagnostic[0..1]: RtgDiagnostic` | Defined by its typed fields and action requirements. |
| `RtgControllerPreconditionFailed` | `attribute` | `message: String`, `diagnostic[0..1]: RtgDiagnostic` | Defined by its typed fields and action requirements. |
| `RtgControllerApplyFailed` | `attribute` | `message: String`, `diagnostic[0..1]: RtgDiagnostic` | Defined by its typed fields and action requirements. |
| `RtgControllerObjectNotFound` | `attribute` | `message: String`, `diagnostic[0..1]: RtgDiagnostic` | Defined by its typed fields and action requirements. |
| `RtgControllerDiscoveryFailed` | `attribute` | `message: String`, `diagnostic[0..1]: RtgDiagnostic` | Defined by its typed fields and action requirements. |
| `RtgControllerSnapshotFailed` | `attribute` | `message: String`, `diagnostic[0..1]: RtgDiagnostic` | Defined by its typed fields and action requirements. |
| `RtgControllerReplayFailed` | `attribute` | `message: String`, `diagnostic[0..1]: RtgDiagnostic` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| `RtgControllerValidationMode` | `strict`, `skip` |
| `RtgControllerFailureRestore` | `restore_pre_cutover_snapshot` |
| `RtgControllerLedgerMode` | `record`, `skip` |
| `RtgControllerOperationStatus` | `applied`, `cutover_applied`, `cutover_failed`, `migration_abandoned`, `snapshot_persisted`, `restore_applied`, `replay_applied`, `ledger_failures_flushed` |
| `RtgControllerValidationStatus` | `validated` |
| `RtgControllerReplayVerificationStatus` | `replay_verified` |
| `RtgControllerMutationState` | `not_mutated` |
| `RtgControllerStateClassification` | `empty`, `schemaOnly`, `populated`, `hasStagedWork`, `needsReplay` |
| `RtgControllerWorkflow` | `schemaBootstrap`, `dataIngest`, `queryAnswer`, `safeUpdate`, `snapshotReplayCheck`, `stagedWorkReview`, `replayRecovery` |
| `RtgControllerMigrationCountScope` | `current_migration_store` |
| `RtgControllerLedgerRecordKind` | `request`, `response`, `error` |
| `RtgControllerMigrationEventType` | `staged`, `staging_rejected`, `staging_failed`, `cutover_applied`, `cutover_failed`, `abandoned` |

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
| `ReplayLedgerContractVerification` | `ReplayLedger` | `replayFlow`, `replaySelection`, `replayLedgerFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#ReplayLedgerContractVerification` |
| `VerifyReplayFromLedgerContractVerification` | `VerifyReplayFromLedger` | `replayVerification`, `verifyReplayFromLedgerFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#VerifyReplayFromLedgerContractVerification` |
| `ListMigrationHistoryContractVerification` | `ListMigrationHistory` | `migrationHistorySemantics`, `listMigrationHistoryFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#ListMigrationHistoryContractVerification` |
| `FlushLedgerFailuresContractVerification` | `FlushLedgerFailures` | `ledgerFailureSemantics`, `flushLedgerFailuresFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#FlushLedgerFailuresContractVerification` |
| `ControllerGetObjectContractVerification` | `ControllerGetObject` | `controllerGetObjectFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#ControllerGetObjectContractVerification` |
| `ControllerListMigrationsContractVerification` | `ControllerListMigrations` | `controllerListMigrationsFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#ControllerListMigrationsContractVerification` |
| `ControllerGetMigrationContractVerification` | `ControllerGetMigration` | `controllerGetMigrationFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#ControllerGetMigrationContractVerification` |
| `ValidateGraphContractVerification` | `ValidateGraph` | `validateGraphFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#ValidateGraphContractVerification` |
| `DiscoverAnchorTypesContractVerification` | `DiscoverAnchorTypes` | `discoverAnchorTypesFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#DiscoverAnchorTypesContractVerification` |
| `GetControllerSchemaPackContractVerification` | `GetControllerSchemaPack` | `getControllerSchemaPackFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#GetControllerSchemaPackContractVerification` |
| `PersistSystemSnapshotContractVerification` | `PersistSystemSnapshot` | `persistSystemSnapshotFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#PersistSystemSnapshotContractVerification` |
| `ListPersistedSnapshotsContractVerification` | `ListPersistedSnapshots` | `listPersistedSnapshotsFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#ListPersistedSnapshotsContractVerification` |
| `LoadPersistedSnapshotContractVerification` | `LoadPersistedSnapshot` | `loadPersistedSnapshotFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#LoadPersistedSnapshotContractVerification` |
| `OpenRtgControllerContractVerification` | `OpenRtgController` | `openRtgControllerFailureSemantics` | `components/rtg/controller/tests/test_rtg_controller_contract.py#OpenRtgControllerContractVerification` |
| `RtgControllerBoundaryVerification` | `RtgController` | `controllerReadSemantics`, `discoverySemantics`, `persistedSnapshotSemantics`, `operationResultSemantics`, `ledgerOutcomeFlow`, `publicContractsOnly`, `noTransportOwnership`, `intentionalBoundary`, `validatesBeforeRequiredMutation`, `strictValidationDefault`, `liveGraphLaneExcludesKnowledgeEngineering`, `knowledgeChangesMigrationScoped`, `cutoverOnlyLiveFlipAuthority`, `normalizedBatchesInternalPlans`, `schemaConstraintChangesUseMigrations`, `schemaConstraintDeletionUsesMigrations`, `nonLiveCandidatesMigrationScoped`, `systemInvariantsOwned`, `validationReportAuthoritative`, `snapshotUsesComponentSnapshots`, `snapshotJsonSerializable`, `snapshotRecordsLedgerPosition`, `persistedSnapshotStorageScoped`, `cutoverUsesMigrationMembership`, `readsHideTransientState`, `projectedQueriesUseLiveOverlay`, `cutoverRestoresOnFailure`, `failedCutoverLegible`, `failedCutoverReplayPreservesStatus`, `cutoverOrder`, `abandonmentNeverDeletesLive`, `oneWriteAtATime`, `ledgerRecordsBlackBoxActivity`, `ledgerPayloadsJsonText`, `transactionIdAlwaysAssigned`, `transactionIdsUuids`, `ledgerPositionReplayCursor`, `resolvedUuidsBeforeLedger`, `writeAtomicityScoped`, `readsMediated`, `liveFlipsViaFullRecordWrite`, `graphTypeIsSchemaTypeKey` | `components/rtg/controller/tests/test_rtg_controller_contract.py#RtgControllerBoundaryVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
