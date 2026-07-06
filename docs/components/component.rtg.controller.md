---
id: component.rtg.controller
type: Component
status: accepted
owner: humans
code:
  roots:
    - components/rtg/controller
---

# RTG Controller

## Purpose

Provide the main in-code orchestration surface for the RTG knowledge graph system.

The controller coordinates graph, schema, constraint, migration, validation, query, discovery, snapshot, restore, and ledger-backed audit/replay operations behind one stable application-facing API. External interfaces such as MCP, REST, CLI, or SDK adapters should call this component rather than owning RTG domain workflow.

The RTG system is intended for humans working with AI agents to manage long-term knowledge content across varied domains. The live RTG graph stores active human/agent modeling content; subsystem state such as schema definitions, constraints, migration records, snapshots, and ledger records remains isolated behind dedicated component contracts.

## Responsibilities

- Bind configured component implementations into one RTG system handle.
- Provide application-facing operations for graph object changes, schema definition changes, constraint definition changes, migration management, validation, query, snapshot, restore, and migration cutover.
- Invoke validation for requested graph, schema, constraint, and migration-affecting changes before applying them in strict mode.
- Enforce cross-component RTG system invariants that are broader than any one lower-level store.
- Mint UUIDs for batch-local references, resolve all controller-mediated writes to concrete resource IDs, and apply lower-level writes with explicit resolved IDs.
- Record the fully resolved change batch with concrete resource IDs in the ledger so replay reproduces identical state.
- Allow direct live graph CRUD through controller operations when the requested object types and data satisfy current live schema and constraints.
- Validate proposed live graph CRUD without mutation or ledger writes for agent dry-runs, risky imports, and recovery probes.
- Require schema and constraint changes to flow through migration operations rather than direct live edits.
- Require schema and constraint retirement or deletion to flow through migration operations.
- Restrict non-live graph, schema, and constraint candidate records to active migration workflows.
- Apply accepted graph changes through `component.rtg.graph` contracts.
- Apply accepted schema definition changes through `component.rtg.schema` contracts.
- Apply accepted constraint definition changes through `component.rtg.constraints` contracts.
- Create, update, and read migration records through `component.rtg.migration` contracts.
- Apply migration cutover by activating migration candidate records, retiring replaced records, pruning retired records from in-memory stores after post-state validation, and removing completed migration records from the in-memory migration store.
- Protect migration cutover with an in-memory pre-cutover snapshot so failed cutover can restore the previous visible state.
- Mark migrations failed with diagnostic metadata when strict cutover validation or apply fails after a migration record is selected.
- Abandon draft, ready, or failed migration work and prune safe non-live candidates that are not live and not referenced by another migration.
- Execute queries through `component.rtg.query`.
- Provide application-facing read operations for graph objects and migration records so reads are mediated by the controller and can be queued during cutover, restore, and replay.
- Default controller query execution to live graph objects only; require explicit query options for non-live reads or caller-supplied live-status overlays.
- Keep migration-ID projection on the validation and cutover paths in v1; query execution does not accept migration IDs or derive migration overlays itself.
- Queue writes so only one write operation mutates RTG state or controller-owned ledger state at a time.
- Queue reads during migration cutover, restore, and replay so callers never observe transient cutover, restore, or replay state.
- Provide current-live-state and projected-post-migration validation operations for knowledge-engineering and recovery workflows.
- Provide basic discovery responses by composing schema definition metadata and graph type counts.
- Provide an application-facing system state summary for agents and operators, including live schema counts, live object counts, staged-work counts, migration status counts, ledger position, persisted snapshot paths, and recommended next steps.
- Export and restore coordinated JSON-serializable system snapshots for graph, schema, constraints, and migration state.
- Include the latest ledger position and transaction identifier represented by a system snapshot.
- List and load persisted system snapshots through JSON File Storage so transport adapters can offer recovery without arbitrary filesystem access.
- Own controller-level ledger behavior by recording controller request, response, and error payloads through a generic SQL storage dependency.
- Assign each controller operation a UUID transaction identifier, assign each persisted ledger entry a monotonically increasing ledger position, and record a timestamp with every ledger entry for audit readability.
- Store ledger request, response, and error payloads as JSON text through SQL storage.
- Retry failed ledger writes twice before queuing them as ledger failures.
- Persist queued ledger failures to `system/ledger_failures.json` through the required JSON File Storage dependency.
- Expose enough operation metadata to support future replay, time-travel, audit, and analytics over controller activity.
- Keep transport adapters thin by centralizing RTG workflow sequencing in this component.

## Non-responsibilities

- Does not own graph object storage internals.
- Does not own schema definition storage internals.
- Does not own constraint definition storage internals.
- Does not own migration record storage internals.
- Does not implement graph query matching algorithms.
- Does not implement object-shape or constraint validation algorithms.
- Does not provide MCP, REST, CLI, SDK, or UI transport behavior.
- Does not own user authentication, authorization, snapshot file IO, distributed locking, replication, or deployment topology.
- Does not expose arbitrary filesystem reads when listing or loading persisted snapshots; snapshot readback is constrained to JSON File Storage documents.
- Does not make SQL storage a responsibility of graph, schema, constraints, migration, validation, or query components.
- Does not provide curated discovery view state in v1; a future discovery component may own that state.
- Does not keep completed migration history in the in-memory migration store after successful cutover; durable history belongs to the controller ledger.
- Does not guarantee distributed transaction atomicity or own SQL engine behavior unless a future accepted runtime contract adds that guarantee.
- Does not use monotonic transaction identifiers; transaction identifiers are UUIDs, and ledger ordering for audit and replay is the controller-owned `ledger_position`.

## Provided contracts

### `RtgController.open`

Kind:

- function

Inputs:

- `graph`
- `schema`
- `constraints`
- `migration`
- `change_validator`
- `query_engine`
- `json_storage`
- `sql_storage`

Outputs:

- `RtgController`

Errors:

- `RtgControllerConfigurationInvalid`

Semantics:

- Returns a controller handle bound to supplied component implementations.
- The controller must use each dependency through its public contract.
- The controller must not replace configured dependencies except through explicit contracts such as `restore_from_snapshot`.
- `json_storage` is required because RTG controller features depend on it, including snapshot persistence and the ledger-failure failsafe.
- `sql_storage` is required for full v1 controller operation because the controller owns ledger-backed request, response, error, audit, and replay behavior.

### `RtgController.apply_live_graph_changes`

Kind:

- function

Inputs:

- `graph_changes`
- `validation_mode`

Outputs:

- `RtgControllerOperationResult`

Errors:

- `RtgControllerValidationFailed`
- `RtgControllerApplyFailed`

Semantics:

- Accepts normal live graph CRUD: anchor writes, data-object writes, link writes, direct anchor/data association changes, dissociations, graph deletes, and live graph replacements.
- Rejects non-live candidate creation and requests that attempt to make graph objects non-live.
- Does not accept schema, constraint, migration, evidence, or cutover changes.
- Internally converts the graph changes to a normalized `RtgChangeBatch` for validation, ledgering, replay, and apply sequencing; the normalized batch is not the application-facing workflow.
- Resolves new-resource IDs and batch-local references to concrete resource IDs before validation, ledger recording, and apply; callers may instead supply concrete IDs directly for import or relinking.
- Treats the change reference as the authoritative identity for controller-mediated writes; embedded record IDs are resolved to that identity before validation, ledger recording, and apply.
- Relies on lower-level component contracts for UUID/kind conflicts and same-kind full-record replacement semantics.
- Validates the projected post-change live graph through `component.rtg.change_validation` when `validation_mode` is `strict`.
- `validation_mode` supports `strict` and `skip`; `strict` is the default for normal controller writes.
- `skip` bypasses validation for privileged or internal interfaces but does not weaken lower-level store invariants.
- Performs controller-owned precondition checks before mutation, such as dependency availability, requested operation mode, and expected pre-mutation lifecycle assertions.
- Refuses mutation when validation returns blocking findings.
- Relies on validation that evaluates the projected post-state, including same-batch associations and delete/dissociation cascades.
- Applies accepted graph changes through `component.rtg.graph` mutation contracts.
- Applies the normalized operation atomically; on unexpected apply failure, restores touched graph, schema, constraint, and migration records from scoped preimages before returning failure.
- Returns operation results with applied changes, validation evidence, and the controller transaction identifier.
- Generates a UUID controller transaction identifier before attempting ledger writes.
- Records the resolved request before mutation and records the response or error after execution.
- If request or response ledger writes fail after configured retries, preserves the successful graph mutation and reports degraded audit state in the operation result.
- Returns the transaction identifier on success and on failures where a response can be produced.

### `RtgController.validate_live_graph_changes`

Kind:

- function

Inputs:

- `graph_changes`
- `validation_options`

Outputs:

- `RtgControllerLiveGraphValidationResult`

Errors:

- `RtgControllerPreconditionFailed`
- `RtgValidationInputInvalid`

Semantics:

- Accepts the same normal live graph CRUD envelope as `RtgController.apply_live_graph_changes`.
- Resolves batch-local references to concrete resource IDs using the same controller resolution rules as a real live graph write.
- Applies the same live-graph-lane preconditions as a real live graph write, including rejecting schema, constraint, migration, and non-live candidate work.
- Validates the projected post-change live graph through `component.rtg.change_validation`.
- Does not mutate graph, schema, constraints, migration, snapshots, or ledger state.
- Does not assign a controller transaction identifier and does not write request, response, or error records to the ledger.
- Returns whether the proposed write would be accepted, `mutation_state: "not_mutated"`, the generated concrete IDs for local refs, the resolved graph changes, and the validation report.
- Intended for dry-runs before risky imports and for recovery probes where validation evidence should not create planning data.

### `RtgController.stage_knowledge_changes`

Kind:

- function

Inputs:

- `knowledge_changes`
- `validation_mode`

Outputs:

- `RtgControllerOperationResult`

Errors:

- `RtgControllerValidationFailed`
- `RtgControllerPreconditionFailed`
- `RtgControllerApplyFailed`

Semantics:

- Accepts knowledge-engineering staging changes represented as a normalized `RtgChangeBatch`.
- Accepts non-live schema definitions, non-live constraint definitions, migration records, migration evidence/status changes, and non-live graph candidates when those candidates are referenced by a migration record.
- Rejects direct live schema or constraint writes.
- Rejects unscoped non-live graph, schema, or constraint candidates.
- Rejects graph, schema, or constraint live-status flips; `apply_migration_cutover` is the only controller operation that makes staged schema or constraint candidates live.
- Validates the projected graph, schema, constraint, and migration views through `component.rtg.change_validation` when `validation_mode` is `strict`.
- Strict validation includes migration records introduced in the same staging request and rejects the request when their projected cutover state has blocking findings.
- Applies accepted staged records through the owning graph, schema, constraint, and migration component contracts without making them live except where the supplied records are already existing migration records.
- Records resolved staging requests and responses through the controller ledger for audit and replay.
- Returns `RtgControllerOperationResult.status == "applied"` for compatibility. When candidate migrations are written, `details.operation_effect` is `staged_candidates_written`, `details.requires_cutover` indicates whether a cutover is needed, and `details` includes staged migration IDs and candidate counts.

### `RtgController.apply_migration_cutover`

Kind:

- function

Inputs:

- `migration_id`
- `cutover_options`

Outputs:

- `RtgControllerOperationResult`

Errors:

- `RtgControllerValidationFailed`
- `RtgControllerPreconditionFailed`
- `RtgControllerApplyFailed`

Semantics:

- Reads the migration record through `component.rtg.migration`.
- Obtains the cutover membership and replacement sets from `component.rtg.migration` as an `RtgMigrationCutoverPlan` (`RtgMigrationCutoverPlan.from_migration`) rather than re-deriving them, then orchestrates that plan; any `RtgChangeBatch` derived for validation is built from the plan.
- Maps missing migration records, invalid migration cutover plans, unsupported cutover options, and missing referenced cutover candidates to `RtgControllerPreconditionFailed` before mutation begins.
- Validates cutover readiness through `component.rtg.change_validation` by deriving an `RtgChangeBatch` from the migration record when required by `cutover_options`; the derived batch projects the schema, constraint, and graph live-status flips before any live mutation is applied.
- Exports a pre-cutover in-memory system snapshot while writes are paused and reads are queued.
- Applies cutover in this order: validate projected state, apply schema and constraint live-status flips, apply graph live-status flips, validate actual post-cutover state, prune retired records, then remove the completed migration record.
- Updates referenced schema definitions through `component.rtg.schema` so definitions marked make-live become live and definitions marked make-non-live become non-live.
- Updates referenced constraint definitions through `component.rtg.constraints` so definitions marked make-live become live and definitions marked make-non-live become non-live.
- Updates referenced graph objects through `component.rtg.graph` so objects marked make-live become live and objects marked make-non-live become non-live.
- Realizes each live-status flip as a full-record read-modify-write through the owning store's write contract (`put_definition`, `put_constraint`, `put_anchor`/`put_data_object`/`put_link`), since the stores expose no live-status-only mutation: it reads the current record, sets `system.live`, and writes the record back otherwise unchanged.
- Within one schema `type_key`, applies make-non-live flips before make-live flips so `component.rtg.schema`'s single-live-definition invariant is never transiently violated.
- Updates migration status through `component.rtg.migration` according to the migration lifecycle contract.
- Validates the projected post-cutover state before pruning replaced records.
- Validates the actual post-cutover graph, schema, and constraint state after live-status flips and before pruning or migration cleanup.
- Deletes records that the migration makes non-live after the post-cutover state is known to be valid.
- Removes the completed migration record from the in-memory migration store after successful cutover.
- Queues reads while cutover is mutating or pruning in-memory state.
- Preserves or restores the pre-cutover in-memory snapshot before returning failure when strict cutover validation, cutover mutation, post-cutover validation, pruning, or migration cleanup fails.
- Transitions the selected migration to `failed` with status metadata containing the transaction identifier and validation or error summary when strict cutover validation or apply fails and the migration record can still be updated safely.
- Records failed strict cutover as a replayable `cutover_failed` controller response so ledger replay preserves the failed migration status without applying the cutover.
- Reports failure state with validation or error details while preserving the previous live graph, schema, and constraint state.

### `RtgController.abandon_migration`

Kind:

- function

Inputs:

- `migration_id`
- `reason | None`

Outputs:

- `RtgControllerOperationResult`

Errors:

- `RtgControllerPreconditionFailed`
- `RtgControllerApplyFailed`

Semantics:

- Reads the migration record through `component.rtg.migration`.
- Rejects abandonment of applied migrations.
- Transitions draft, ready, or failed migrations to `abandoned` with optional status metadata before removing the terminal migration record from the in-memory migration store.
- Prunes non-live schema, constraint, and graph candidates listed in the migration's make-live sets only when the candidate is not live and is not referenced by another migration.
- Never deletes live records and never deletes records listed only in make-non-live sets.
- Returns pruned, skipped, shared, missing, and live candidate IDs in operation details.
- Records abandonment requests and responses through the controller ledger for audit and replay.

### `RtgController.execute_query`

Kind:

- function

Inputs:

- `query_spec`
- `query_options`

Outputs:

- `RtgQueryResult`

Errors:

- `RtgQuerySpecInvalid`
- `RtgQueryUnsupported`

Semantics:

- Delegates query execution to `component.rtg.query`.
- Applies live-only query options by default.
- Passes caller-supplied `RtgQueryOptions`, including `live_filter` and `live_status_overlay`, through to the query engine when provided.
- Does not accept migration IDs and does not derive migration live-status overlays in v1.
- Does not mutate graph, schema, constraints, or migration state.

### `RtgController.get_object`

Kind:

- function

Inputs:

- `object_uuid`

Outputs:

- `RtgObject`

Errors:

- `RtgControllerObjectNotFound`

Semantics:

- Returns a graph object by UUID through `component.rtg.graph` read contracts.
- Returns the object and its live status without lifecycle filtering, so callers can read live and non-live migration candidates by identity.
- Queues while migration cutover or restore is mutating or replacing in-memory state.
- Does not mutate graph, schema, constraints, or migration state.

### `RtgController.list_migrations`

Kind:

- function

Inputs:

- `status | None`

Outputs:

- `RtgMigrationRecordList`

Errors:

- `RtgMigrationStatusInvalid`

Semantics:

- Lists migration records through `component.rtg.migration`, optionally filtered by status.
- Lets adapters and agents drive the migration lifecycle through the controller rather than reaching into the migration store directly.
- Queues while migration cutover or restore is mutating or replacing in-memory state.
- Does not mutate graph, schema, constraints, or migration state.

### `RtgController.get_migration`

Kind:

- function

Inputs:

- `migration_id`

Outputs:

- `RtgMigrationRecord`

Errors:

- `RtgMigrationNotFound`

Semantics:

- Returns one migration record by ID through `component.rtg.migration`.
- Queues while migration cutover or restore is mutating or replacing in-memory state.
- Does not mutate graph, schema, constraints, or migration state.

### `RtgController.validate_graph`

Kind:

- function

Inputs:

- `migration_ids | None`
- `validation_options`

Outputs:

- `RtgValidationReport`

Errors:

- `RtgControllerValidationFailed`

Semantics:

- Validates the current live graph against current live schema definitions and constraint definitions when `migration_ids` is omitted.
- Validates the projected post-migration graph/schema/constraint state when one or more migration IDs are supplied.
- Returns all deterministic findings that can be produced for the requested validation scope.
- Returns a validation report even when the graph is invalid; `RtgControllerValidationFailed` signals an input or execution failure, not the presence of blocking findings.
- Does not mutate graph, schema, constraints, or migration state.

### `RtgController.discover_anchor_types`

Kind:

- function

Inputs:

- `discovery_options`

Outputs:

- `RtgAnchorTypeDiscoveryResult`

Errors:

- `RtgControllerDiscoveryFailed`

Semantics:

- Returns live anchor schema type keys, semantic descriptions, and graph live-count metadata for basic type discovery.
- Uses schema read contracts for type descriptions and graph read/count contracts for population counts.
- Does not require a separate discovery component in v1.
- Does not inspect non-live migration candidates unless explicitly requested by discovery options.

### `RtgController.get_schema_pack`

Kind:

- function

Inputs:

- `anchor_type_keys`
- `schema_pack_options`

Outputs:

- `RtgControllerSchemaPack`

Errors:

- `RtgControllerDiscoveryFailed`

Semantics:

- Returns expanded schema details for selected anchor types.
- Includes each selected anchor schema, its required and optional associated data object schemas, and link schemas where the anchor type is an allowed source or target.
- Returns a controller-owned `RtgControllerSchemaPack` that composes the schema-only `RtgSchemaPack` from `component.rtg.schema` with live graph counts from `component.rtg.graph`.
- May include live graph counts for returned types.
- Produces enough schema detail for agents to plan targeted queries without reading every type in a large RTG system.

### `RtgController.get_system_state`

Kind:

- function

Inputs:

- None.

Outputs:

- `RtgControllerSystemState`

Errors:

- `RtgControllerDiscoveryFailed`

Semantics:

- Returns a read-only controller-owned summary of the current RTG application state.
- Includes live schema counts by kind, live graph object counts by kind and type, non-live candidate counts by category, migration counts by status, latest ledger position and transaction identifier, ledger record count, and persisted snapshot paths visible through JSON File Storage.
- Classifies state as `empty`, `schema_only`, `populated`, `has_staged_work`, or `needs_replay`.
- Includes recommended workflow identifiers and recommended next steps suitable for an MCP-only agent or human operator.
- Does not mutate graph, schema, constraints, migration, snapshots, or ledger state.

### `RtgController.export_system_snapshot`

Kind:

- function

Inputs:

- None.

Outputs:

- `RtgSystemSnapshot`

Errors:

- `RtgControllerSnapshotFailed`

Semantics:

- Exports graph, schema, constraints, and migration snapshots through each component's public snapshot contract.
- Produces a single JSON-serializable snapshot value containing enough state to restore the configured stateful RTG components.
- Includes the last ledger position, transaction identifier, and timestamp represented by the snapshot, so replay can resume from an unambiguous position.
- The snapshot may be written to a JSON file by caller-owned storage or adapter code.
- Does not require any particular persistence backend.

### `RtgController.persist_system_snapshot`

Kind:

- function

Inputs:

- `relative_path`

Outputs:

- `RtgControllerOperationResult`

Errors:

- `RtgControllerSnapshotFailed`

Semantics:

- Exports a system snapshot and writes it as a JSON-compatible document through the required JSON File Storage dependency.

### `RtgController.list_persisted_snapshots`

Kind:

- function

Inputs:

- None.

Outputs:

- `RtgPersistedSnapshotList`

Errors:

- `RtgControllerSnapshotFailed`

Semantics:

- Lists JSON File Storage documents that look like persisted RTG system snapshots.
- Returns relative paths and snapshot metadata when the document can be decoded as a system snapshot.
- Does not expose arbitrary filesystem paths or non-JSON storage contents.
- Does not mutate graph, schema, constraints, migration, snapshots, or ledger state.

### `RtgController.load_persisted_snapshot`

Kind:

- function

Inputs:

- `relative_path`

Outputs:

- `RtgPersistedSnapshotDocument`

Errors:

- `RtgControllerSnapshotFailed`

Semantics:

- Loads one JSON File Storage document by relative path and decodes it as an RTG system snapshot.
- Returns the relative path and decoded snapshot for use with restore or replay start options.
- Does not expose arbitrary filesystem reads outside JSON File Storage.
- Does not mutate graph, schema, constraints, migration, snapshots, or ledger state.

### `RtgController.replay_ledger`

Kind:

- function

Inputs:

- `replay_options`

Outputs:

- `RtgControllerOperationResult`

Errors:

- `RtgControllerReplayFailed`

Semantics:

- Replays state-altering controller requests from ledger storage to rebuild or time-travel RTG system state.
- Ignores read-only query and discovery requests for state reconstruction.
- May start from a supplied system snapshot or from a persisted snapshot path, and replay only ledger entries whose `ledger_position` is greater than the snapshot's recorded `last_ledger_position`.
- Uses stored controller request payloads and operation names as the v1 replay source of truth.
- Requires replay to start from an explicitly empty controller state or from a supplied `start_snapshot`/`start_snapshot_path`; replay into active mutable state without an explicit seed is rejected.
- Replays only operations whose recorded response indicates the state change was accepted (status `applied`, `restore_applied`, `migration_abandoned`, `cutover_failed`, or a successful cutover); operations recorded as validation-rejected, precondition-failed, or rolled back are skipped because they produced no accepted state change.
- Requires a clean or snapshot-seeded starting store: replay reuses the recorded resolved UUIDs, so replaying onto a store that already contains those resources is rejected unless a `start_snapshot` explicitly defines the starting state. In v1 callers seed replay from `empty` stores or a `start_snapshot`.
- Applies replayed operations with validation skipped, because the recorded requests were validated when first applied, and reuses the recorded resolved UUIDs rather than minting new ones.
- Replays migration cutover from the ledgered cutover request payload, including the migration record captured at request time, rather than looking up the migration from the current migration store after it may have been pruned.
- Replays `cutover_failed` responses by restoring the failed migration status metadata without applying schema, constraint, or graph live-status flips.
- Returns `details.replay_window` with `start_source`, `start_ledger_position`, `effective_after_ledger_position`, `through_ledger_position`, `ledger_records_seen`, and a note explaining that snapshot-seeded replay starts after the snapshot ledger position.
- Queues reads and writes while replay is restoring a seed snapshot or applying ledgered state changes.
- Does not append new ledger entries while replaying; replay reconstructs state rather than recording new activity.
- Treats unknown state-mutating operation names as blocking replay errors.
- Does not require lower-level graph, schema, constraints, migration, validation, or query components to know about ledger storage.

### `RtgController.verify_replay_from_ledger`

Kind:

- function

Inputs:

- `replay_options`

Outputs:

- `RtgControllerReplayVerificationResult`

Errors:

- `RtgControllerReplayFailed`
- `RtgControllerSnapshotFailed`

Semantics:

- Verifies ledger replay in isolated scratch controller state without appending ledger entries.
- Accepts the same replay options as `replay_ledger`, including `start_snapshot_path`.
- If no start snapshot is supplied, uses empty scratch component state as the replay seed.
- Reuses the canonical `replay_ledger` operation internally so replay semantics remain single-source.
- Restores the pre-verification controller state before returning or raising.
- Returns ledger records seen, mutating requests replayed, `replay_window`, pre/post summaries, count diffs, and post-replay validation report.

### `RtgController.list_migration_history`

Kind:

- function

Inputs:

- None.

Outputs:

- `RtgControllerMigrationHistory`

Errors:

- `RtgControllerReplayFailed`

Semantics:

- Reconstructs migration audit events from controller ledger request/response records.
- Returns events for staged migrations, successful cutovers, failed cutovers, and abandoned migrations.
- Includes migration ID, description when available, transaction ID, ledger position, status, recorded timestamp, and summary.
- Does not require applied migrations to remain in the in-memory migration store.
- Does not mutate graph, schema, constraints, migration, snapshots, or ledger state.

### `RtgController.flush_ledger_failures`

Kind:

- function

Inputs:

- None.

Outputs:

- `RtgControllerOperationResult`

Errors:

- None.

Semantics:

- Attempts to write queued ledger request, response, or error records that previously failed to persist to SQL storage.
- Reads `system/ledger_failures.json` through JSON File Storage when queued failures were spilled to file storage, merges those persisted records with in-memory failures, and attempts to flush both queues.
- Queues with other controller operations while reading and updating controller-owned ledger failure state.
- Does not mutate graph, schema, constraints, or migration state.

### `RtgController.restore_from_snapshot`

Kind:

- function

Inputs:

- `snapshot`
- `restore_options`

Outputs:

- `RtgControllerOperationResult`

Errors:

- `RtgControllerSnapshotFailed`

Semantics:

- Restores graph, schema, constraints, and migration state from a previously exported JSON-serializable system snapshot as a controller operation.
- Reconstructs stateful component state by calling each component's public snapshot import contract directly.
- Rebinds the controller to the restored stateful component handles while preserving configured stateless dependencies such as validation and query implementations.
- Does not apply migrations or run validation as part of snapshot import unless a future accepted contract explicitly adds that behavior.
- Records the restore request and response in the controller ledger.
- May be used as an operational recovery or rollback action.
- `restore_options` controls recovery behavior such as whether to skip ledger recording for internal restores.
- Queues reads and writes while restore is replacing in-memory component handles.

### `RtgControllerOperationResult`

Kind:

- data structure

Fields:

- `status`
- `transaction_id`
- `ledger_position`
- `applied_changes`
- `validation_report`
- `snapshot`
- `details`

Semantics:

- Canonical result of a state-changing controller operation.
- `status` is a stable string code. V1 status codes include `applied`, `cutover_applied`, `cutover_failed`, `migration_abandoned`, `snapshot_persisted`, `restore_applied`, `replay_applied`, and `ledger_failures_flushed`.
- `transaction_id` is the UUID controller transaction identifier recorded in the ledger.
- `ledger_position` is the latest persisted ledger position for the operation when ledger recording succeeded, and is absent when the operation did not write to the ledger or all ledger writes for that operation failed.
- `applied_changes` is an `RtgControllerAppliedChanges` count summary that reports visible state changes caused by the operation.
- `validation_report` carries the `RtgValidationReport` produced when validation ran, and is absent when validation was skipped.
- `snapshot` carries a coordinated system snapshot when the operation returns one.
- `details` carries operation-specific JSON-safe metadata, including degraded-audit details, staging effect metadata, replay counts, and ledger failure flush counts.

### `RtgControllerValidationFailed`

Kind:

- error

Fields:

- `message`
- `transaction_id`
- `validation_report`
- `diagnostic`

Semantics:

- Raised when a controller mutation request is rejected by validation before the requested state change is accepted.
- `transaction_id` is included when the controller assigned one before validation rejection.
- `validation_report` is included when validation ran and produced findings, so transport adapters can return actionable, whole-payload repair guidance without bypassing the controller or calling validators directly.
- `diagnostic` is optional JSON-safe structured corrective guidance for controller-owned lifecycle failures, such as failed cutover preservation, replay preconditions, snapshot recovery, and migration audit next steps.
- Transport adapters may serialize this error as an expected operation response rather than as a transport failure.

### Structured diagnostics

Controller-owned errors may include an optional `diagnostic` object with stable fields such as `code`, `category`, `path`, `problem`, `remedy`, `minimal_example`, `guide_topics`, `safe_to_retry`, and `mutation_state`.

The controller owns diagnostics for operation sequencing and lifecycle invariants only. It may teach valid next actions for replay, snapshots, migration cutover, staged-work cleanup, and ledger-backed audit, but it must not duplicate query, schema, or transport input-shape diagnostics owned by other components.

### `RtgControllerAppliedChanges`

Kind:

- data structure

Fields:

- `graph_writes`
- `schema_writes`
- `constraint_writes`
- `migration_writes`
- `deletes`
- `live_status_changes`

Semantics:

- Reports count summaries from a controller operation.
- `graph_writes`, `schema_writes`, `constraint_writes`, and `migration_writes` count records written through the owning lower-level component contracts.
- `deletes` counts records deleted or pruned through the owning lower-level component contracts.
- `live_status_changes` counts lifecycle flips applied during migration cutover or normalized batch execution.
- Validation rejection, precondition failure, and failures that restore or preserve the previous visible state report zero counts.
- Replay correctness is based on ledgered resolved request payloads, not on `applied_changes`; this structure is for caller feedback, diagnostics, and tests.

### `RtgControllerValidationOptions`

Kind:

- data structure

Fields:

- `tracks`
- `finding_limit`

Semantics:

- Controller-facing validation options passed to `component.rtg.change_validation`.
- `tracks` is `all` or a list containing `schema_object`, `constraint_network`, or `migration_cutover`; the default is `all`.
- `finding_limit` is a positive integer or absent; when absent, validation returns all deterministic findings practical for the requested scope.
- `finding_limit` limits returned findings only; validation acceptance remains controlled by all findings produced by the executed tracks.

### `RtgControllerCutoverOptions`

Kind:

- data structure

Fields:

- `validation_mode`
- `prune_retired`
- `failure_restore`

Semantics:

- Controls `RtgController.apply_migration_cutover`.
- `validation_mode` is `strict` or `skip`; the default is `strict`.
- `prune_retired` is a boolean; the default is `true`.
- `failure_restore` is `restore_pre_cutover_snapshot`; v1 has no alternate failure-restore mode.

### `RtgControllerDiscoveryOptions`

Kind:

- data structure

Fields:

- `include_non_live`
- `limit`

Semantics:

- Controls basic controller discovery.
- `include_non_live` is a boolean; the default is `false`.
- `limit` is a positive integer or absent; when absent, discovery returns every matching anchor type.

### `RtgControllerSchemaPackOptions`

Kind:

- data structure

Fields:

- `live`
- `include_live_counts`

Semantics:

- Controls `RtgController.get_schema_pack`.
- `live` is `true`, `false`, or absent; the default is `true` for controller-facing schema packs.
- `include_live_counts` is a boolean; the default is `true`.

### `RtgControllerReplayOptions`

Kind:

- data structure

Fields:

- `start_snapshot`
- `start_snapshot_path`
- `after_ledger_position`
- `through_ledger_position`

Semantics:

- Controls ledger replay.
- `start_snapshot` is an optional `RtgSystemSnapshot` used as the initial state.
- `start_snapshot_path` is an optional JSON File Storage relative path to a persisted `RtgSystemSnapshot`.
- Supplying both `start_snapshot` and `start_snapshot_path` is rejected.
- `after_ledger_position` is optional and, when supplied, replay starts with entries whose `ledger_position` is greater than this value. When `start_snapshot` is supplied, its `last_ledger_position` is the default.
- `through_ledger_position` is optional and, when supplied, replay stops after applying entries at or below that position.
- Replay order is always ascending `ledger_position`; timestamps are not replay cursors.

### `RtgControllerReplayVerificationResult`

Kind:

- data structure

Fields:

- `status`
- `ledger_records_seen`
- `mutating_requests_replayed`
- `replay_window`
- `pre_summary`
- `post_summary`
- `count_diffs`
- `validation_report`

Semantics:

- Reports a ledger replay verification performed in scratch state.
- `status` is `replay_verified`.
- `replay_window` reports the start source, start/effective ledger positions, optional through position, records seen, and replay-window note.
- `pre_summary` and `post_summary` summarize graph counts, schema counts, constraint count, migration counts, and ledger pointers for the replay seed and replay result.
- `count_diffs` reports post-minus-pre count changes for graph, schema, constraint, and migration counts.
- `validation_report` is the post-replay controller validation result.

### `RtgControllerMigrationHistory`

Kind:

- data structure

Fields:

- `events`

Semantics:

- `events` is an ordered list of JSON-safe migration audit events reconstructed from the controller ledger.
- Event `event_type` values include `staged`, `cutover_applied`, `cutover_failed`, and `abandoned`.

### `RtgControllerRestoreOptions`

Kind:

- data structure

Fields:

- `ledger_mode`

Semantics:

- Controls `RtgController.restore_from_snapshot`.
- `ledger_mode` is `record` or `skip`; the default is `record`.
- `skip` is reserved for internal recovery paths and does not weaken snapshot validation.

### `RtgControllerLedgerFailureRecord`

Kind:

- data structure

Fields:

- `transaction_id`
- `ledger_position`
- `operation_name`
- `record_kind`
- `payload_json`
- `failure_message`
- `retry_count`
- `first_failed_timestamp`
- `last_failed_timestamp`

Semantics:

- JSON object shape stored in `system/ledger_failures.json` when SQL ledger persistence fails after configured retries.
- `record_kind` is `request`, `response`, or `error`.
- `payload_json` is the same JSON text that failed to persist through SQL storage.
- `ledger_position` is present when a position had already been reserved for the failed ledger entry; otherwise it is absent.

### `RtgSystemSnapshot`

Kind:

- data structure

Fields:

- `graph`
- `schema`
- `constraints`
- `migration`
- `last_ledger_position`
- `last_transaction_id`
- `last_transaction_timestamp`

Semantics:

- A single JSON-serializable value composing the public snapshots of the stateful RTG components.
- `graph`, `schema`, `constraints`, and `migration` are the respective component snapshots.
- Discovery state is intentionally excluded in v1 because `component.rtg.discovery` is deferred and owns no snapshot contract yet; adding it later is a known extension point.
- `last_ledger_position` is the latest persisted ledger position represented by the snapshot state.
- `last_transaction_id` and `last_transaction_timestamp` identify the controller operation associated with that ledger position for audit readability.

### `RtgAnchorTypeDiscoveryResult`

Kind:

- data structure

Fields:

- `anchor_types`

Semantics:

- Basic discovery result composed from schema metadata and graph counts.
- Each `anchor_types` entry contains an anchor schema type key, its semantic description, and a live graph population count.

### `RtgControllerSchemaPack`

Kind:

- data structure

Fields:

- `schema_pack`
- `live_counts`

Semantics:

- Controller-owned expansion of a schema pack with live graph counts.
- `schema_pack` is the schema-only `RtgSchemaPack` from `component.rtg.schema`.
- `live_counts` maps returned schema type keys to live graph population counts from `component.rtg.graph`.

### `RtgControllerSystemState`

Kind:

- data structure

Fields:

- `state_classification`
- `live_schema_counts`
- `live_object_counts`
- `non_live_candidate_counts`
- `migration_counts_by_status`
- `migration_counts_scope`
- `migration_history_hint`
- `last_ledger_position`
- `last_transaction_id`
- `ledger_record_count`
- `persisted_snapshot_paths`
- `recommended_workflows`
- `recommended_next_steps`

Semantics:

- Agent/operator summary of the current controller state.
- `state_classification` is one of `empty`, `schema_only`, `populated`, `has_staged_work`, or `needs_replay`.
- `migration_counts_by_status` describes the current migration store, not the full durable audit history.
- `migration_counts_scope` is `current_migration_store`.
- `migration_history_hint` is present when ledger-backed migration events are available through a history/audit operation even though current migration counts may be clean after cutover or abandonment.
- `recommended_workflows` contains stable generic workflow identifiers for transport adapters and agents, such as `schema_bootstrap`, `data_ingest`, `query_answer`, `safe_update`, `snapshot_replay_check`, `staged_work_review`, and `replay_recovery`.
- `recommended_next_steps` is advisory text for transport adapters and agents; controller invariants remain authoritative.

### `RtgPersistedSnapshotList`

Kind:

- data structure

Fields:

- `snapshots`

Semantics:

- Lists persisted snapshot-like JSON documents available through JSON File Storage.
- Each entry contains a relative path and best-effort snapshot metadata.

### `RtgPersistedSnapshotDocument`

Kind:

- data structure

Fields:

- `relative_path`
- `snapshot`

Semantics:

- Loaded persisted snapshot document suitable for `restore_from_snapshot` or replay start options.

## Required contracts

May consume:

- `component.rtg.graph`
- `component.rtg.schema`
- `component.rtg.constraints`
- `component.rtg.migration`
- `component.rtg.change_validation`
- `component.rtg.query`
- `component.storage.sql` for controller-owned ledger storage.
- `component.storage.json_file` for snapshot persistence and the ledger-failure failsafe.
- Public snapshot import contracts for graph, schema, constraints, and migration.

Must not consume:

- Private internals of graph, schema, constraints, migration, validation, or query components.
- Private SQL database connections or tables outside `component.storage.sql`.
- MCP, REST, CLI, SDK, UI, authentication, authorization, or deployment-specific frameworks as required dependencies.

## Related components

- MCP, REST, CLI, and SDK adapters should call the controller instead of duplicating RTG workflow rules.
- Reference applications should wire this component as the application composition root when it exists.
- Lower-level stores remain authoritative for their own state and invariants.

## Runtime notes

- The controller composes the lower-level components and owns their orchestration sequencing. How those components are bound to the controller — in-process, dependency-injected, or addressed across a message broker — is a topology choice outside this contract and changes neither the controller's behavior nor the lower-level component contracts.

## Owned state

- Bound component handles for the configured RTG system.
- Operation sequencing authority for controller contracts.
- Write serialization and read queuing authority during cutover and restore.
- Controller ledger tables, monotonically increasing ledger positions, UUID transaction identifiers, and per-entry ledger timestamps.
- Snapshot metadata that identifies the last ledger position, transaction identifier, and timestamp represented by a snapshot.
- No durable domain state beyond caller-supplied dependencies unless a future accepted contract adds it.

## Invariants

### `invariant.rtg.controller.public_contracts_only`

The controller uses dependencies only through public component contracts.

### `invariant.rtg.controller.no_transport_ownership`

The controller does not depend on MCP, REST, CLI, SDK, or UI transport frameworks.

### `invariant.rtg.controller.validates_before_required_mutation`

Operations that require validation must not apply graph, schema, constraint, migration-record, or migration-cutover mutations after blocking validation findings.

### `invariant.rtg.controller.strict_validation_default`

Normal write operations use strict validation by default and apply immediately only when no blocking findings are produced.

### `invariant.rtg.controller.live_graph_lane_excludes_knowledge_engineering`

The live graph lane accepts only normal live graph CRUD and rejects schema, constraint, migration, evidence, cutover, and non-live candidate changes.

### `invariant.rtg.controller.knowledge_changes_are_migration_scoped`

Knowledge-engineering staging changes that create non-live graph, schema, or constraint candidates must tie those candidates to a migration record before the controller records or applies the staging request.

### `invariant.rtg.controller.cutover_is_only_live_flip_authority_for_staged_schema_constraints`

The controller does not make staged schema or constraint candidates live through live graph work or staging work; only migration cutover may activate staged schema or constraint records.

### `invariant.rtg.controller.normalized_batches_are_internal_controller_plans`

`RtgChangeBatch` is the controller and validator's normalized proposed-state representation for validation, ledger, replay, and internal sequencing. It is not the single application-facing workflow for all controller writes.

### `invariant.rtg.controller.schema_constraint_changes_use_migrations`

Schema and constraint changes exposed by the controller flow through migration records rather than direct live edits.

### `invariant.rtg.controller.schema_constraint_deletion_uses_migrations`

Schema and constraint retirement or deletion exposed by the controller flows through migration records so validation, ledger capture, and post-state checks can run.

### `invariant.rtg.controller.non_live_candidates_are_migration_scoped`

The controller rejects creation of non-live graph, schema, or constraint records unless the request is tied to an active migration workflow.

### `invariant.rtg.controller.system_invariants_owned`

Cross-component operation invariants exposed by the RTG system API are enforced by the controller rather than by lower-level stores reaching into one another.

### `invariant.rtg.controller.validation_report_authoritative`

When validation is required, the controller must not re-implement validation algorithms or ignore blocking validation findings. It may only add controller-owned precondition checks and mutation sequencing rules.

### `invariant.rtg.controller.snapshot_uses_component_snapshots`

System snapshots are composed from the public snapshot contracts of owned component handles.

### `invariant.rtg.controller.snapshot_json_serializable`

System snapshots must be JSON-serializable values containing graph, schema, constraints, and migration state.

### `invariant.rtg.controller.snapshot_records_ledger_position`

Each exported snapshot records the latest ledger position, transaction identifier, and timestamp represented by the snapshot state.

### `invariant.rtg.controller.persisted_snapshot_readback_is_storage_scoped`

Persisted snapshot listing and loading are limited to JSON File Storage relative documents and do not expose arbitrary filesystem reads.

### `invariant.rtg.controller.cutover_uses_migration_membership`

Migration cutover lifecycle flips come from the migration component's `RtgMigrationCutoverPlan` (`from_migration`), not from ad hoc controller selection; the controller orchestrates the plan and does not own cutover membership.

### `invariant.rtg.controller.reads_do_not_observe_transient_cutover`

All controller reads, including queries, discovery, get-object, migration reads, and validation, must wait while migration cutover, restore, or replay is mutating or replacing in-memory system state.

### `invariant.rtg.controller.projected_queries_use_live_overlay`

Projected migration queries use a controller-derived live-status overlay from migration records rather than a full copied graph.

### `invariant.rtg.controller.cutover_restores_on_failure`

Migration cutover must restore the pre-cutover in-memory system state before returning failure when a cutover step fails after mutation begins.

### `invariant.rtg.controller.failed_cutover_is_legible`

When strict migration cutover validation or apply fails for a selected migration, the controller preserves the previous live state and marks the migration `failed` with diagnostic metadata when that status update can be applied safely.

### `invariant.rtg.controller.failed_cutover_replay_preserves_status`

Ledger replay must reproduce accepted failed-cutover status changes without applying the rejected cutover's live-status flips.

### `invariant.rtg.controller.cutover_order`

Migration cutover validates projected state, flips schema and constraint live status, flips graph live status, validates actual post-state, prunes retired records, and removes the completed migration record in that order.

### `invariant.rtg.controller.abandonment_never_deletes_live_records`

Migration abandonment may prune only non-live make-live candidates that are not referenced by another migration. It must not delete live records or make-non-live targets.

### `invariant.rtg.controller.one_write_at_a_time`

Controller write operations mutate RTG system state and controller-owned ledger state serially.

### `invariant.rtg.controller.ledger_records_black_box_activity`

The controller records request, response, and error payloads for controller operations with a transaction identifier.

### `invariant.rtg.controller.ledger_payloads_are_json_text`

Controller ledger request, response, and error payloads are serialized as JSON text before being written through SQL storage.

### `invariant.rtg.controller.transaction_id_always_assigned`

Every controller request receives a transaction identifier before mutation or ledger write attempts.

### `invariant.rtg.controller.transaction_ids_are_uuids`

Controller transaction identifiers are UUIDs and are not assumed to be monotonic.

### `invariant.rtg.controller.ledger_position_is_replay_cursor`

Each persisted ledger entry has a monotonically increasing `ledger_position`, assigned when the resolved request is recorded before mutation, so replay order reflects submission order even when later operations fail. Audit display may use timestamps, but replay ordering and snapshot resume use `ledger_position`.

### `invariant.rtg.controller.resolved_uuids_before_ledger`

The controller resolves all controller-mediated writes and batch-local references to concrete resource IDs before recording the request and applying changes. Ledgered batches therefore carry concrete IDs and replay reproduces identical state. Component-level ID generation serves direct callers; controller-mediated writes always pass explicit resolved IDs and defer UUID/kind conflict and same-kind replacement semantics to the owning lower-level component contracts.

### `invariant.rtg.controller.write_atomicity_scoped`

Controller writes are atomic. Rollback on apply failure uses a pre-image scoped to the objects the batch touches rather than a whole-graph snapshot. Whole-graph snapshots are used only for migration cutover and restore.

### `invariant.rtg.controller.reads_mediated`

Application-facing reads, including query, discovery, get-object, migration reads, and validation, are served through the controller so they can be queued during migration cutover, restore, and replay.

### `invariant.rtg.controller.live_flips_via_full_record_write`

The controller realizes every `system.live` change as a full-record read-modify-write through the owning store's existing write contract; the lower-level stores expose no live-status-only mutation and stay unaware of migration lifecycle. Within one schema `type_key`, make-non-live precedes make-live so the schema single-live-definition invariant holds at every step.

### `invariant.rtg.controller.graph_type_is_schema_type_key`

A graph object's `type` string is the same key as the schema definition `type_key` for that object's type. The controller relies on this identity when it joins graph type counts with schema type keys and when validation checks graph objects against schema definitions; `component.rtg.graph` stays type-string-neutral and does not enforce it.

## Verification

Required checks:

- Boundary tests for controller construction with explicit dependencies.
- Contract tests for applying accepted live graph changes through `apply_live_graph_changes`.
- Contract tests proving the live graph lane rejects schema, constraint, migration, evidence, cutover, and non-live candidate changes.
- Contract tests for staging accepted migration-scoped schema, constraint, migration-record, evidence, and non-live graph candidate changes through `stage_knowledge_changes`.
- Contract tests proving strict staging rejects invalid projected cutover state for migration records introduced in the same staging request.
- Contract tests proving knowledge staging rejects direct live schema or constraint writes and unscoped non-live candidates.
- Contract tests proving rejected live graph and knowledge staging requests do not mutate graph, schema, constraints, or migration state.
- Contract tests for migration cutover lifecycle flips across schema, constraint, and graph records.
- Contract tests proving migration cutover follows the specified operation order.
- Contract tests proving failed cutover restores the pre-cutover in-memory state.
- Contract tests proving failed strict cutover marks the selected migration `failed` with diagnostic metadata while preserving live state.
- Replay tests proving failed strict cutover preserves failed migration status and does not apply rejected live-status flips.
- Contract tests proving migration abandonment prunes only safe non-live candidates and never deletes live or shared records.
- Contract tests proving cutover precondition failures are surfaced as controller-level errors before mutation begins.
- Contract tests proving schema and constraint changes must flow through migration operations.
- Contract tests proving schema and constraint deletion must flow through migration operations.
- Contract tests proving non-live candidate creation outside an active migration is rejected.
- Contract tests for `strict` and `skip` validation modes.
- Contract tests for query delegation without mutation.
- Contract tests proving controller queries default to live-only results.
- Contract tests for projected migration-state validation from migration IDs and explicit query options.
- Contract tests proving controller query execution passes caller-supplied live-status options without deriving migration overlays.
- Contract tests proving writes are serialized and reads wait during cutover, restore, or replay.
- Contract tests proving controller `get_object`, `list_migrations`, and `get_migration` delegate to component reads and are queued during cutover and restore.
- Contract tests proving one live graph request can create a new anchor, its required associated data object, and a link between new objects using batch-local references that resolve to controller-minted UUIDs.
- Contract tests proving normalized resolved requests recorded in the ledger carry concrete resource IDs and replay to identical state.
- Contract tests proving proposed deletes are validated through graph preview contracts and that normal writes do not snapshot the whole graph.
- Contract tests proving an unexpected apply failure restores only the touched objects.
- Snapshot export/restore round-trip tests across graph, schema, constraints, and migration snapshots.
- Snapshot persistence tests using JSON File Storage.
- Snapshot readback tests proving persisted snapshots can be listed and loaded through JSON File Storage without arbitrary filesystem access.
- Ledger tests proving requests, responses, errors, and transaction identifiers are recorded through SQL storage.
- Ledger tests proving JSON request, response, and error payloads are stored as text in SQL rows.
- Ledger failure tests proving failed ledger writes are queued or written to the JSON File Storage failsafe.
- Ledger failure tests proving failed ledger writes are retried twice before being queued.
- Ledger failure tests proving JSON failsafe records are written to `system/ledger_failures.json` through JSON File Storage.
- Ledger failure tests proving flush operations serialize controller-owned ledger failure state.
- Replay tests proving state-altering requests can rebuild state while read-only requests are ignored for state reconstruction.
- Replay tests proving application writes wait while replay owns system state.
- Replay tests proving unknown state-mutating operation names produce blocking replay errors.
- Replay tests proving ledger entries are ordered by `ledger_position` and resume after a snapshot's recorded `last_ledger_position`.
- Replay tests proving persisted `start_snapshot_path` is resolved through JSON File Storage, ambiguous replay starts are rejected, and isolated replay verification restores current state without ledger writes.
- Migration-history tests proving staged, successful cutover, failed cutover, and abandoned events can be reconstructed from ledger records after applied migrations are pruned from the live migration store.
- Ledger tests proving equal timestamps do not change replay order.
- Ledger failure tests proving `system/ledger_failures.json` records follow the `RtgControllerLedgerFailureRecord` shape.
- Discovery tests proving anchor type descriptions and live counts are composed from schema and graph contracts.
- System-state tests proving live counts, staged-work counts, migration status counts, persisted snapshot paths, ledger metadata, classifications, and recommended next steps are reported without mutation.
- Restore tests proving controller state is restored through public component snapshot import contracts.
- Restore-operation tests proving snapshot restore is ledgered and can serve as a recovery action.
- Forbidden-dependency checks proving transport frameworks are not required by the controller.

Required evidence:

- MCP, REST, CLI, or SDK adapters can be thin wrappers over the controller API.
- A migration cutover uses migration membership and updates graph, schema, and constraint live status through store contracts.
- A successful migration cutover prunes replaced non-live records from in-memory stores and removes the completed migration from the in-memory migration store.
- A failed strict migration cutover leaves live state unchanged and makes failed staged work legible through migration status metadata.
- Abandoned staged work remains auditable through the ledger while safe non-live candidate clutter is pruned from current in-memory stores.
- A system snapshot can be exported and restored as a JSON-serializable value and can be persisted through JSON File Storage.
- A persisted system snapshot can be listed and loaded by relative path for restore and replay.
- A ledger transaction identifier can correlate a controller request with its response or error.
- A ledger write failure after successful mutation can be surfaced without changing the already-applied RTG state.

## Change rules

Agents may:

- Add private orchestration helpers inside the controller component root.
- Add controller operations when they sequence existing component contracts without taking over lower-level state.
- Add thin convenience methods when they delegate to the same validated controller operations.
- Add boundary tests for workflow sequencing.
- Add ledger table details inside the controller boundary when they use `component.storage.sql`.

Agents may not:

- Move graph, schema, constraint, migration, validation, or query owned state into the controller.
- Bypass public component contracts to reach private internals.
- Add transport-specific dependencies as required controller dependencies.
- Fold MCP, REST, CLI, SDK, UI, authentication, authorization, SQL engine, JSON storage engine, or distributed runtime responsibilities into this component.
- Move SQL storage primitives into this component instead of consuming `component.storage.sql`.
- Move curated discovery view state into the controller while `component.rtg.discovery` is the intended future owner.
- Change accepted public contracts, owned state, invariants, or dependency rules without explicit human approval.

## Open questions

- Should authorization remain entirely outside the controller, or should the controller accept caller context for a future authorization component?
- What normalized operation form, if any, should supplement full request/response ledger records after v1?
- Should a future support or diagnostic component enrich controller query and validation responses with additional suggestions based on live schema, graph, constraint, or discovery context?
- When the async runtime exists, should the controller's ledger, replay, and audit responsibilities move into a runtime-owned audit-ledger component, and what triggers that split?
