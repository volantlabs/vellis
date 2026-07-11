# component.rtg.migration

Generated from textual SysML v2 by `just model-render`; do not edit by hand.

- Model definition: `RtgMigration`
- Lifecycle: `accepted`
- Purpose: Own identity-bearing migration records, lifecycle transitions, membership, and evidence.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `exportSnapshot` | `ExportMigrationSnapshot` | out `snapshot: RtgMigrationSnapshot` | None | Export all records without inspecting referenced component state. |
| `putMigration` | `PutMigration` | in `migration: RtgMigrationRecord`; out `stored: RtgMigrationRecord` | `RtgMigrationRecordInvalid`, `RtgMigrationIdConflict`, `RtgMigrationStatusTransitionInvalid` | Generate or preserve migration identity and create or lifecycle-safe fully replace one structurally valid record. |
| `getMigration` | `GetMigration` | in `migrationId: String`; out `migration: RtgMigrationRecord` | `RtgMigrationNotFound` | Return one migration tracking record by ID. |
| `listMigrations` | `ListMigrations` | in `status: RtgMigrationStatus[0..1]`; out `result: RtgMigrationRecordList` | `RtgMigrationStatusInvalid` | Return all records or records in one status in deterministic migration-ID order. |
| `setStatus` | `SetMigrationStatus` | in `migrationId: String`; in `status: RtgMigrationStatus`; in `statusMetadata: JsonObject[0..1]`; out `migration: RtgMigrationRecord` | `RtgMigrationNotFound`, `RtgMigrationStatusInvalid`, `RtgMigrationStatusTransitionInvalid` | Apply only a permitted lifecycle transition and replace status metadata with the supplied object or an empty object. |
| `addEvidence` | `AddMigrationEvidence` | in `migrationId: String`; in `evidence: RtgMigrationEvidence`; out `migration: RtgMigrationRecord` | `RtgMigrationNotFound`, `RtgMigrationEvidenceInvalid` | Append one evidence identity without interpreting or fetching its referenced artifact. |
| `deleteMigration` | `DeleteMigration` | in `migrationId: String`; out `result: RtgMigrationDeleteResult` | `RtgMigrationNotFound`, `RtgMigrationDeleteInvalid` | Delete one applied or abandoned record only; referenced resources and durable controller history remain unchanged. |
| `buildCutoverPlan` | `BuildMigrationCutoverPlan` | in `migration: RtgMigrationRecord`; out `plan: RtgMigrationCutoverPlan` | `RtgMigrationRecordInvalid` | Purely copy ordered lifecycle membership and replacement mappings from a concrete valid migration record. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `CreateEmptyRtgMigration` | out `migration: RtgMigration` | None | Return an empty store and status index. |
| `ImportRtgMigrationSnapshot` | in `snapshot: RtgMigrationSnapshot`; out `migration: RtgMigration` | `RtgMigrationSnapshotInvalid`, `RtgMigrationRecordInvalid`, `RtgMigrationIdConflict`, `RtgMigrationReferenceInvalid` | Validate every record, identity, reference, lifecycle value, and uniqueness rule before rebuilding indexes and exposing the store. |

## Retained collaborator roles

| Role | Kind | Referenced type | Multiplicity |
|---|---|---|---|
| — | — | — | No retained collaborator roles. |

## Owned state

| State feature | Type | Ownership | Meaning |
|---|---|---|---|
| `migrationRecords` | `RtgMigrationRecord` | `owned` | Canonical component-owned migration occurrences. |
| `statusIndex` | `JsonObject` | `derived` | Ephemeral status index derived from canonical migration records. |

## Action and state effects

| Action | State / collaborator | Modeled effect |
|---|---|---|
| `exportSnapshot` | `migrationRecords` | return all migration records in migration-ID order. |
| `putMigration` | `migrationRecords` | create or lifecycle-safe replace one complete record. |
| `setStatus` | `migrationRecords` | apply one allowed lifecycle transition or same-status metadata update. |
| `addEvidence` | `migrationRecords` | append one evidence identity not already present. |
| `deleteMigration` | `migrationRecords` | remove one terminal applied or abandoned record. |
| `buildCutoverPlan` | `migrationRecords` | purely copy cutover membership from the supplied record. |
| `getMigration` | `migrationRecords` | read one canonical record. |
| `listMigrations` | `statusIndex` | read deterministic status index. |

## Invariants and behavioral obligations

| Stable ID | Modeled obligation |
|---|---|
| `contract.rtg.migration.put_effect` | A new record may begin in any valid status. Replacing an existing ID must preserve status or follow the same transition table as set_status; all other fields are fully replaced. |
| `contract.rtg.migration.status_transitions` | Allowed changes are draft to ready or abandoned; ready to draft, applied, failed, or abandoned; failed to ready or abandoned. Applied and abandoned are terminal. Same-status update changes metadata only. |
| `contract.rtg.migration.evidence_effect` | Evidence IDs are unique within a migration; success appends one evidence record and preserves membership and status. |
| `contract.rtg.migration.delete_effect` | Only applied and abandoned records are deletable. Rejected deletion leaves state unchanged and never removes durable controller history. |
| `contract.rtg.migration.cutover_plan` | The plan deterministically copies all make-live, make-non-live, and replacement membership without reading or mutating referenced component state. |
| `invariant.rtg.migration.id_unique` | Migration IDs are unique. |
| `invariant.rtg.migration.cutover_sets_disjoint` | Make-live and make-non-live sets and replacement sides do not conflict within one resource kind. |
| `invariant.rtg.migration.not_normal_crud` | Migration records describe coordinated schema, constraint, and non-live graph lifecycle work, not ordinary live graph CRUD. |
| `invariant.rtg.migration.candidates_are_materialized_v1` | V1 membership references already materialized candidate records and contains no executable transforms or delta objects. |
| `invariant.rtg.migration.references_are_data` | Referenced records remain owned by their source components; migration stores identities and intent only. |
| `invariant.rtg.migration.no_store_mutation` | This component does not read or mutate graph, schema, or constraint stores. |
| `invariant.rtg.migration.status_transition_controlled` | Status changes, including replacement of an existing ID, preserve status or obey the single transition table. |
| `invariant.rtg.migration.status_is_tracking_not_proof` | Ready status records caller intent and is not proof that referenced cutover state is valid. |
| `invariant.rtg.migration.completed_history_is_external` | Durable completed history belongs to controller audit. |
| `invariant.rtg.migration.rollback_is_forward_change_v1` | V1 rollback is represented by a later forward migration, not a special status or reverse executable operation. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgMigrationReplacement` | `attribute` | `oldResourceId: Uuid`, `newResourceId: Uuid` | Defined by its typed fields and action requirements. |
| `RtgMigrationEvidence` | `attribute` | `evidenceId: String`, `kind: String`, `reference: String`, `summary: String`, `metadata: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgMigrationRecord` | `item` | `migrationId[0..1]: String`, `description: String`, `status: RtgMigrationStatus` = `RtgMigrationStatus::draft`, `schemaMakeLive[0..*]: Uuid`, `schemaMakeNonLive[0..*]: Uuid`, `constraintMakeLive[0..*]: Uuid`, `constraintMakeNonLive[0..*]: Uuid`, `graphMakeLive[0..*]: Uuid`, `graphMakeNonLive[0..*]: Uuid`, `schemaReplacements[0..*]: RtgMigrationReplacement`, `constraintReplacements[0..*]: RtgMigrationReplacement`, `graphReplacements[0..*]: RtgMigrationReplacement`, `evidence[0..*]: RtgMigrationEvidence`, `metadata: JsonObject` | Identity may be absent only on write. Stored records have a concrete generated or caller-supplied ID. The record stores references and intent, never referenced resources or executable transforms. |
| `RtgMigrationRecordList` | `attribute` | `migrations[0..*]: RtgMigrationRecord` | Defined by its typed fields and action requirements. |
| `RtgMigrationSnapshot` | `attribute` | `migrations[0..*]: RtgMigrationRecord` | Defined by its typed fields and action requirements. |
| `RtgMigrationDeleteResult` | `attribute` | `deletedMigration: RtgMigrationRecord` | Defined by its typed fields and action requirements. |
| `RtgMigrationCutoverPlan` | `attribute` | `migrationId: String`, `schemaMakeLive[0..*]: Uuid`, `schemaMakeNonLive[0..*]: Uuid`, `constraintMakeLive[0..*]: Uuid`, `constraintMakeNonLive[0..*]: Uuid`, `graphMakeLive[0..*]: Uuid`, `graphMakeNonLive[0..*]: Uuid`, `schemaReplacements[0..*]: RtgMigrationReplacement`, `constraintReplacements[0..*]: RtgMigrationReplacement`, `graphReplacements[0..*]: RtgMigrationReplacement` | Defined by its typed fields and action requirements. |
| `RtgMigrationNotFound` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgMigrationSnapshotInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgMigrationIdInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgMigrationIdConflict` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgMigrationRecordInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgMigrationReferenceInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgMigrationStatusInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgMigrationStatusTransitionInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgMigrationDeleteInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgMigrationEvidenceInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Model and external values |
|---|---|
| `RtgMigrationStatus` | `draft`, `ready`, `applied`, `failed`, `abandoned` |

## Verification

| Verification | Objectives | Evidence |
|---|---|---|
| `RtgMigrationBoundaryVerification` | `putMigrationEffect`, `statusTransitionTable`, `evidenceEffect`, `deleteEffect`, `cutoverPlanEffect`, `idUnique`, `cutoverSetsDisjoint`, `notNormalCrud`, `candidatesMaterialized`, `referencesAreData`, `noStoreMutation`, `statusTransitionControlled`, `statusTrackingNotProof`, `completedHistoryExternal`, `rollbackForwardChange` | `components/rtg/migration/tests/test_rtg_migration_contract.py` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
