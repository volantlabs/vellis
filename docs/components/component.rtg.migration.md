---
id: component.rtg.migration
type: Component
status: accepted
owner: humans
code:
  roots:
    - components/rtg/migration
---

# RTG Migration

## Purpose

Manage migration records that describe coordinated lifecycle transitions for RTG schema definitions, constraint definitions, and RTG graph objects.

The component owns the data needed to track an ontology, constraint, or migration-graph edit from draft planning through readiness and cutover. It does not own ordinary live graph CRUD, schema definitions, constraint definitions, graph objects, validation, constraint enforcement, or the controller that performs operational cutover.

## Responsibilities

- Store migration records identified by stable migration IDs.
- Generate migration IDs for new migration records, and accept caller-supplied IDs for special cases such as importing or relinking existing migration records.
- Store a plain-language migration description that explains the intended ontology, constraint, or graph migration change.
- Record which non-live schema definitions are intended to become live during cutover.
- Record which live schema definitions are intended to become non-live during cutover.
- Record which non-live constraint definitions are intended to become live during cutover.
- Record which live constraint definitions are intended to become non-live during cutover.
- Record which non-live RTG graph objects are intended to become live during cutover.
- Record which live RTG graph objects are intended to become non-live during cutover.
- Record old-to-new mappings between schema definitions when a migration replaces definitions.
- Record old-to-new mappings between constraint definitions when a migration replaces constraints.
- Record old-to-new mappings between RTG graph objects when a migration replaces objects.
- Track migration status using the initial lifecycle `draft`, `ready`, `applied`, `failed`, and `abandoned`.
- Store caller-supplied validation, constraint, review, or approval evidence references as migration metadata.
- Track non-live candidate membership for schema, constraint, and graph records so lower-level stores do not need migration identifiers in their own system metadata.
- Import and export migration snapshots for persistence, review, testing, or replay consumers.
- Enforce structural integrity of migration records themselves.

## Non-responsibilities

- Does not store schema definitions.
- Does not store constraint definitions.
- Does not store RTG graph objects.
- Does not track ordinary live graph CRUD within the current live schema and constraint boundaries.
- Does not validate RTG graph objects against schema definitions.
- Does not enforce multi-object graph constraints.
- Does not generate transformed graph objects or schema definitions.
- Does not decide whether a migration is semantically correct.
- Does not mutate `component.rtg.schema` records directly.
- Does not mutate `component.rtg.constraints` records directly.
- Does not mutate `component.rtg.graph` records directly.
- Does not perform cutover by itself.
- Does not execute bulk transforms or delta objects in v1; candidate replacement records must be materialized before cutover.
- Does not model rollback as a special migration status or reverse operation in v1.
- Does not retain completed migration history after the controller removes applied migrations from the in-memory migration store; durable history belongs to the controller ledger.
- Does not own durable persistence, audit history, authorization, UI workflow, distributed locking, or distributed transaction coordination.
- Does not guarantee atomicity across schema, constraints, and graph stores unless a future accepted runtime contract adds that guarantee.

## Provided contracts

### `RtgMigration.empty`

Kind:

- function

Inputs:

- None.

Outputs:

- `RtgMigration`

Errors:

- None.

Semantics:

- Returns an empty in-memory migration store with no migration records.
- The returned store owns its in-memory migration maps and derived indexes.

### `RtgMigration.import_snapshot`

Kind:

- function

Inputs:

- `RtgMigrationSnapshot`

Outputs:

- `RtgMigration`

Errors:

- `RtgMigrationSnapshotInvalid`
- `RtgMigrationRecordInvalid`
- `RtgMigrationIdConflict`
- `RtgMigrationReferenceInvalid`

Semantics:

- Builds an in-memory migration store from a JSON-serializable snapshot.
- Validates structural integrity of each migration record.
- Validates uniqueness of migration IDs.
- Validates that references inside a migration record are internally well formed.
- Does not verify that referenced schema definitions exist in `component.rtg.schema`.
- Does not verify that referenced constraint definitions exist in `component.rtg.constraints`.
- Does not verify that referenced graph objects exist in `component.rtg.graph`.
- Does not validate referenced graph objects, schema definitions, or constraint definitions.

### `RtgMigration.export_snapshot`

Kind:

- function

Inputs:

- None.

Outputs:

- `RtgMigrationSnapshot`

Errors:

- None.

Semantics:

- Returns a JSON-serializable snapshot of all migration records.
- The snapshot contains enough information to reconstruct equivalent migration tracking state through `RtgMigration.import_snapshot`.
- Export does not inspect schema definition state, constraint definition state, or graph object state.

### `RtgMigration.put_migration`

Kind:

- function

Inputs:

- `migration`

Outputs:

- `RtgMigrationRecord`

Errors:

- `RtgMigrationRecordInvalid`
- `RtgMigrationIdConflict`

Semantics:

- Creates a new migration record or fully replaces an existing migration record with the same migration ID.
- When the migration ID is omitted, the component generates a new unique migration ID and creates the record.
- When the migration ID is supplied, the component uses it unchanged to create or fully replace that record, which supports import and relinking workflows.
- Validates the migration record as migration-tracking data.
- Requires `migration.description` to be a non-empty plain-language explanation of the intended change; an empty or missing description is rejected as `RtgMigrationRecordInvalid`.
- Validates that make-live and make-non-live sets are disjoint per resource category.
- Validates that replacement mappings and candidate membership are structurally well formed.
- Does not verify referenced schema definition UUIDs against `component.rtg.schema`.
- Does not verify referenced constraint definition UUIDs against `component.rtg.constraints`.
- Does not verify referenced graph object UUIDs against `component.rtg.graph`.
- Does not mutate schema definitions, constraint definitions, or graph objects.

### `RtgMigration.get_migration`

Kind:

- function

Inputs:

- `migration_id`

Outputs:

- `RtgMigrationRecord`

Errors:

- `RtgMigrationNotFound`

Semantics:

- Returns one migration record by ID.
- The returned record describes intended lifecycle transitions and migration metadata; it is not evidence that the migration is ready or has been applied.

### `RtgMigration.list_migrations`

Kind:

- function

Inputs:

- `status | None`

Outputs:

- `RtgMigrationRecordList`

Errors:

- `RtgMigrationStatusInvalid`

Semantics:

- Lists migration records, optionally filtered by migration status.

### `RtgMigration.set_status`

Kind:

- function

Inputs:

- `migration_id`
- `status`
- `status_metadata`

Outputs:

- `RtgMigrationRecord`

Errors:

- `RtgMigrationNotFound`
- `RtgMigrationStatusInvalid`
- `RtgMigrationStatusTransitionInvalid`

Semantics:

- Updates the migration record status and caller-supplied status metadata.
- Enforces the initial allowed transitions: `draft` to `ready` or `abandoned`; `ready` to `draft`, `applied`, `failed`, or `abandoned`; `failed` to `ready` or `abandoned`.
- Treats `applied` and `abandoned` as terminal statuses unless a future accepted contract adds reopening behavior.
- Setting the status to its current value is allowed and updates only `status_metadata`; it is an idempotent no-op for the status itself, not a transition error.
- Does not independently validate readiness with schema, constraints, graph, controller, or validation components.
- Does not apply lifecycle changes to schema definitions, constraint definitions, or graph objects.

### `RtgMigration.add_evidence`

Kind:

- function

Inputs:

- `migration_id`
- `evidence`

Outputs:

- `RtgMigrationRecord`

Errors:

- `RtgMigrationNotFound`
- `RtgMigrationEvidenceInvalid`

Semantics:

- Adds caller-supplied evidence metadata to a migration record.
- Evidence may reference validation reports, constraint reports, review approvals, generated artifacts, or external audit records.
- The component stores evidence references as migration data and does not re-run or interpret the referenced checks.
- A duplicate `evidence_id` within the same migration record is rejected as `RtgMigrationEvidenceInvalid`.

### `RtgMigration.delete_migration`

Kind:

- function

Inputs:

- `migration_id`

Outputs:

- `RtgMigrationDeleteResult`

Errors:

- `RtgMigrationNotFound`
- `RtgMigrationDeleteInvalid`

Semantics:

- Deletes one migration record from the migration store.
- Deletion does not mutate schema definitions, constraint definitions, or graph objects.
- Terminal `applied` and `abandoned` migrations are deletable so the controller can prune completed migrations from the in-memory store after a successful cutover or abandonment.
- Draft, ready, and failed migrations are not deletable in v1; callers must move them to `abandoned` first when they should be removed.
- Deleting an applied migration from the in-memory store does not delete durable audit history already captured by a controller ledger.

### `RtgMigrationDeleteResult`

Kind:

- data structure

Fields:

- `deleted_migration`

Semantics:

- Represents the outcome of a migration record delete.
- `deleted_migration` contains the full migration record that was removed.
- This component does not cascade deletes into schema, constraint, or graph records, so the result reports only the removed migration record.

### `RtgMigrationCutoverPlan.from_migration`

Kind:

- function

Inputs:

- `migration`

Outputs:

- `RtgMigrationCutoverPlan`

Errors:

- `RtgMigrationRecordInvalid`

Semantics:

- Produces an ordered data representation of the lifecycle flips requested by a migration record.
- The plan lists schema definition UUIDs to make live, schema definition UUIDs to make non-live, constraint definition UUIDs to make live, constraint definition UUIDs to make non-live, graph object UUIDs to make live, and graph object UUIDs to make non-live.
- The plan lists materialized candidate records only by reference; it does not describe delta transforms.
- The plan is data for a higher-level controller or tool to apply through `component.rtg.schema`, `component.rtg.constraints`, and `component.rtg.graph`.
- The plan does not perform cutover.

### `RtgMigrationCutoverPlan`

Kind:

- data structure

Fields:

- `schema_make_live`
- `schema_make_non_live`
- `constraint_make_live`
- `constraint_make_non_live`
- `graph_make_live`
- `graph_make_non_live`
- `schema_replacements`
- `constraint_replacements`
- `graph_replacements`

Semantics:

- Ordered data representation of the lifecycle flips and replacement mappings requested by a migration record.
- Make-live and make-non-live fields contain concrete resource IDs only; the plan does not embed schema definitions, constraint definitions, or graph objects.
- Replacement fields contain `RtgMigrationReplacement` records.
- The controller applies this plan through schema, constraint, and graph component contracts.

### `RtgMigrationSnapshot`

Kind:

- data structure

Fields:

- `migrations`

Semantics:

- JSON-serializable migration store snapshot.
- `migrations` contains full migration records with concrete migration IDs.
- Import validates the records and rebuilds derived status indexes from them.

### `RtgMigrationRecord`

Kind:

- data structure

Fields:

- `migration_id`
- `description`
- `status`
- `schema_make_live`
- `schema_make_non_live`
- `constraint_make_live`
- `constraint_make_non_live`
- `graph_make_live`
- `graph_make_non_live`
- `schema_replacements`
- `constraint_replacements`
- `graph_replacements`
- `evidence`
- `metadata`

Semantics:

- Represents one in-flight ontology, constraint, or migration-graph change set.
- `migration_id` identifies the record and may be omitted on write, in which case the component generates one.
- Returned, stored, deleted-result, and snapshot migration records always contain a concrete migration ID.
- `description` explains the intended change for humans, agents, and audit consumers.
- Make-live sets identify non-live candidate records prepared for cutover.
- Make-non-live sets identify live records that will be retired and pruned by the controller after a valid cutover.
- Replacement mappings contain `RtgMigrationReplacement` records that relate old records to materialized new records.
- `evidence` contains `RtgMigrationEvidence` records.
- The record does not contain the schema definitions, constraint definitions, or graph objects it references.
- The record does not contain executable transform code or delta objects in v1.

### `RtgMigrationReplacement`

Kind:

- data structure

Fields:

- `old_resource_id`
- `new_resource_id`

Semantics:

- Relates one retiring resource to one materialized replacement resource in the same resource category.
- The IDs are schema definition UUIDs, constraint definition UUIDs, or graph object UUIDs according to the containing replacement field (`schema_replacements`, `constraint_replacements`, or `graph_replacements`).
- The migration component validates structural form and disjointness but does not verify the referenced resources exist.

### `RtgMigrationEvidence`

Kind:

- data structure

Fields:

- `evidence_id`
- `kind`
- `reference`
- `summary`
- `metadata`

Semantics:

- Caller-supplied evidence attached to a migration record.
- `evidence_id` is unique within one migration record.
- `kind` identifies the evidence family, such as `validation_report`, `human_approval`, `generated_artifact`, or `external_audit`.
- `reference` is a caller-owned identifier, path, URL, or transaction ID.
- `summary` is concise human-readable evidence context.
- `metadata` is JSON-serializable caller-supplied detail.
- The migration component stores evidence records but does not fetch, validate, or interpret referenced artifacts.

### `RtgMigrationRecordList`

Kind:

- data structure

Fields:

- `migrations`

Semantics:

- Ordered list wrapper for migration records.
- `migrations` contains full `RtgMigrationRecord` values with concrete migration IDs.

## Required contracts

May consume:

- Schema definition UUID and live-status conventions from `component.rtg.schema`.
- Constraint definition UUID and live-status conventions from `component.rtg.constraints`.
- RTG graph object UUID and `system.live` conventions from `component.rtg.graph`.
- JSON-serializable value conventions for migration snapshots and metadata.

Must not consume:

- Schema registry internals from `component.rtg.schema`.
- Graph storage internals from `component.rtg.graph`.
- Object validation internals.
- Graph constraints internals.
- Persistence, UI, authorization, or runtime orchestration components.

## Related components

- `component.rtg.schema` owns schema definition records whose lifecycle may be referenced by migration records.
- `component.rtg.constraints` owns constraint definition records whose lifecycle may be referenced by migration records.
- `component.rtg.graph` owns RTG graph objects whose lifecycle may be referenced by migration records.
- `component.rtg.change_validation` may produce evidence referenced by migration records.
- A higher-level controller, tool, or application service reads migration records and applies lifecycle changes through schema, constraints, and graph component contracts.
- `component.rtg.controller` removes completed migrations from this in-memory store after successful cutover and records durable history in its ledger.

## Owned state

- Migration records.
- Migration status values and status-transition authority.
- Sets of schema definition UUIDs intended to become live or non-live.
- Sets of constraint definition UUIDs intended to become live or non-live.
- Sets of RTG graph object UUIDs intended to become live or non-live.
- Old-to-new schema definition mappings.
- Old-to-new constraint definition mappings.
- Old-to-new RTG graph object mappings.
- Caller-supplied evidence metadata and references.

## Invariants

### `invariant.rtg.migration.id_unique`

Each migration ID identifies at most one migration record.

### `invariant.rtg.migration.cutover_sets_disjoint`

Within one migration record, the same schema definition UUID, constraint definition UUID, or graph object UUID must not appear in both the make-live and make-non-live sets for the same resource category.

### `invariant.rtg.migration.not_normal_crud`

Migration records describe ontology, constraint, or migration-graph changes and do not track ordinary live graph CRUD within current schema and constraint boundaries.

### `invariant.rtg.migration.candidates_are_materialized_v1`

V1 migrations reference materialized candidate schema, constraint, and graph records rather than executable bulk transforms or delta objects.

### `invariant.rtg.migration.references_are_data`

References to schema definitions, constraint definitions, graph objects, reports, approvals, or external artifacts are stored as migration data and are not interpreted as proof by this component.

### `invariant.rtg.migration.no_store_mutation`

The migration component does not directly mutate schema definition state, constraint definition state, or graph object state.

### `invariant.rtg.migration.status_transition_controlled`

Migration status changes follow the allowed transition rules owned by this component.

### `invariant.rtg.migration.status_is_tracking_not_proof`

The `ready` status records caller intent or approval state, but is not proof that referenced schema definitions, constraint definitions, or graph objects exist or are semantically valid for cutover.

### `invariant.rtg.migration.completed_history_is_external`

After successful controller cutover, durable migration audit history is expected to live in the controller ledger rather than in this in-memory migration store.

### `invariant.rtg.migration.rollback_is_forward_change_v1`

Rollback of ontology, constraint, or graph migration changes is modeled as a new forward migration in v1; snapshot restore is a controller recovery operation, not migration-store behavior.

## Verification

Required checks:

- Boundary tests for empty migration store creation.
- Boundary tests for adding, replacing, retrieving, listing, exporting, and importing migration records.
- Boundary tests for migration ID conflict rejection.
- Boundary tests proving writes without a supplied migration ID receive a generated unique ID, and writes with a supplied ID use it unchanged.
- Boundary tests proving terminal `applied` and `abandoned` migrations can be deleted while `draft`, `ready`, and `failed` migrations are rejected by delete.
- Boundary tests for invalid migration record rejection.
- Boundary tests for disjoint make-live and make-non-live sets.
- Boundary tests for required migration descriptions.
- Boundary tests for materialized replacement mappings.
- Boundary tests for allowed and forbidden migration status transitions.
- Boundary tests proving `ready` status can be recorded without inspecting schema, constraints, graph, or validation state.
- Boundary tests for evidence metadata storage.
- API-surface checks proving the component does not mutate schema definitions, constraint definitions, or graph objects.

Required evidence:

- A migration record can identify non-live schema definitions to make live and live schema definitions to make non-live.
- A migration record can identify non-live constraint definitions to make live and live constraint definitions to make non-live.
- A migration record can identify non-live graph objects to make live and live graph objects to make non-live.
- A cutover plan can be derived from a migration record without applying it.
- A type replacement migration can reference materialized non-live graph candidates without defining an executable transform.
- Updating migration status does not alter schema, constraints, or graph state.
- A migration marked `ready` is still only migration-tracking data and requires external validation before controller cutover.
- The component can store validation or approval evidence references without interpreting them.
- A rollback plan can be represented as a new migration record that moves the system toward the desired prior state.

## Change rules

Agents may:

- Change private storage and indexing of migration records.
- Add migration metadata fields when they remain migration-tracking data.
- Add status values and transition rules when the public lifecycle contract is updated with explicit human approval.
- Add boundary tests for migration store behavior.
- Refactor cutover-plan construction as long as it remains data-only.

Agents may not:

- Add schema definition storage.
- Add constraint definition storage.
- Add RTG graph object storage.
- Add object validation or graph constraint enforcement.
- Add executable bulk transform or delta-object semantics without explicit human approval.
- Directly mutate `component.rtg.schema`, `component.rtg.constraints`, or `component.rtg.graph`.
- Fold controller, persistence, UI, authorization, distributed transaction, or runtime orchestration responsibilities into this component.
- Change accepted public contracts, owned state, invariants, or dependency rules without explicit human approval.

## Open questions

- What future component or contract should own space-efficient delta migration objects for field renames or other small changes that currently require full materialized candidates?
