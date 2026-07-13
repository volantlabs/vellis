# component.rtg.migration

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

- Model definition: `RtgMigration`
- Lifecycle: `accepted`
- Purpose: Own identity-bearing migration records, lifecycle transitions, membership, and evidence.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `exportSnapshot` | `ExportMigrationSnapshot` | out `snapshot: RtgMigrationSnapshot` | None | Export all records without inspecting referenced component state. |
| `putMigration` | `PutMigration` | in `migration: RtgMigrationRecord`; out `stored: RtgMigrationRecord` | `RtgMigrationIdInvalid`, `RtgMigrationRecordInvalid`, `RtgMigrationStatusInvalid`, `RtgMigrationStatusTransitionInvalid`, `RtgMigrationEvidenceInvalid` | Generate or preserve migration identity and create or lifecycle-safe fully replace one structurally valid record. |
| `getMigration` | `GetMigration` | in `migrationId: String`; out `migration: RtgMigrationRecord` | `RtgMigrationNotFound` | Return one migration tracking record by ID. |
| `listMigrations` | `ListMigrations` | in `status: RtgMigrationStatus[0..1]`; out `result: RtgMigrationRecordList` | `RtgMigrationStatusInvalid` | Return all records or records in one status in deterministic migration-ID order. |
| `setStatus` | `SetMigrationStatus` | in `migrationId: String`; in `status: RtgMigrationStatus`; in `statusMetadata: JsonObject[0..1]`; out `migration: RtgMigrationRecord` | `RtgMigrationIdInvalid`, `RtgMigrationNotFound`, `RtgMigrationRecordInvalid`, `RtgMigrationStatusInvalid`, `RtgMigrationStatusTransitionInvalid` | Apply only a permitted lifecycle transition and replace status metadata with the supplied object or an empty object. |
| `addEvidence` | `AddMigrationEvidence` | in `migrationId: String`; in `evidence: RtgMigrationEvidence`; out `migration: RtgMigrationRecord` | `RtgMigrationNotFound`, `RtgMigrationEvidenceInvalid` | Append one evidence identity without interpreting or fetching its referenced artifact. |
| `deleteMigration` | `DeleteMigration` | in `migrationId: String`; out `result: RtgMigrationDeleteResult` | `RtgMigrationIdInvalid`, `RtgMigrationNotFound`, `RtgMigrationDeleteNotAllowed` | Delete one applied or abandoned record only; referenced resources and durable controller history remain unchanged. |
| `buildCutoverPlan` | `BuildMigrationCutoverPlan` | in `migration: RtgMigrationRecord`; out `plan: RtgMigrationCutoverPlan` | `RtgMigrationRecordInvalid` | Purely copy ordered lifecycle membership and replacement mappings from a concrete valid migration record. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `CreateEmptyRtgMigration` | out `migration: RtgMigration` | None | Return an empty store and status index. |
| `ImportRtgMigrationSnapshot` | in `snapshot: RtgMigrationSnapshot`; out `migration: RtgMigration` | `RtgMigrationSnapshotInvalid`, `RtgMigrationIdInvalid`, `RtgMigrationIdConflict`, `RtgMigrationRecordInvalid`, `RtgMigrationStatusInvalid`, `RtgMigrationEvidenceInvalid` | Validate the container and every record, concrete identity, lifecycle value, JSON value, membership rule, evidence identity, and migration-ID uniqueness rule before exposing the store. Snapshot construction does not apply transitions between records. |

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

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `exportSnapshot` | `migrationRecords` | `read` | return all migration records in migration-ID order. |
| `putMigration` | `migrationRecords` | `write` | create or lifecycle-safe replace one complete record. |
| `setStatus` | `migrationRecords` | `write` | apply one allowed lifecycle transition or same-status metadata update. |
| `addEvidence` | `migrationRecords` | `write` | append one evidence identity not already present. |
| `deleteMigration` | `migrationRecords` | `delete` | remove one terminal applied or abandoned record. |
| `buildCutoverPlan` | `migrationRecords` | `read` | purely copy cutover membership from the supplied record. |
| `getMigration` | `migrationRecords` | `read` | read one canonical record. |
| `listMigrations` | `statusIndex` | `read` | read deterministic status index. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| — | — | No action decomposition required at this boundary. |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.rtg.migration.put_effect` | `PutMigration` | `migration.putMigration` | A new record may begin in any valid status. Replacing an existing ID must preserve status or satisfy MigrationStatusTransitionAllowed for the stored and requested statuses; all other fields are fully replaced. |
| `contract.rtg.migration.membership` | `PutMigration` | `migration.putMigration` | Each make-live and make-non-live collection is a duplicate-free logical set and the two sets are disjoint per resource kind. Each replacement maps a distinct old identity in make-non-live to a distinct new identity in make-live; replacement old and new identities differ. Additions and removals without a replacement remain legal. Stored and returned encodings use ascending UUID order, with replacements ordered by old then new UUID. |
| `contract.rtg.migration.status_transitions` | `SetMigrationStatus` | `migration.setStatus` | The stored and requested statuses must satisfy MigrationStatusTransitionAllowed. Thus draft changes to ready or abandoned; ready to draft, applied, failed, or abandoned; failed to ready or abandoned; applied and abandoned are terminal. Every accepted transition, including same-status, replaces metadata.status_metadata with the supplied JSON object or an empty object and preserves unrelated metadata. |
| `contract.rtg.migration.evidence_effect` | `AddMigrationEvidence` | `migration.addEvidence` | Evidence IDs are unique within a migration; success appends one evidence record and preserves membership and status. |
| `contract.rtg.migration.delete_effect` | `DeleteMigration` | `migration.deleteMigration` | Only applied and abandoned records are deletable. Rejected deletion leaves state unchanged and never removes durable controller history. |
| `contract.rtg.migration.cutover_plan` | `BuildMigrationCutoverPlan` | `migration.buildCutoverPlan` | The plan deterministically copies all make-live, make-non-live, and replacement membership without reading or mutating referenced component state. |
| `contract.rtg.migration.intentional_boundary` | `RtgMigration` | `migration` | Migration stores lifecycle intent, membership, mappings, and evidence only. It does not establish semantic readiness, validate or mutate referenced stores, execute transforms or rollback, enforce graph constraints, own durable audit/persistence/authorization/UI, or guarantee cross-store atomicity or distributed locking. |
| `invariant.rtg.migration.id_unique` | `RtgMigration` | `migration` | Migration IDs are unique. |
| `invariant.rtg.migration.cutover_sets_disjoint` | `RtgMigration` | `migration` | Make-live and make-non-live sets are unique and disjoint within each resource kind. Replacement mappings are one-to-one, map old make-non-live identities to new make-live identities, and never map an identity to itself. |
| `invariant.rtg.migration.not_normal_crud` | `RtgMigration` | `migration` | Migration records describe coordinated schema, constraint, and non-live graph lifecycle work, not ordinary live graph CRUD. |
| `invariant.rtg.migration.candidates_are_materialized_v1` | `RtgMigration` | `migration` | V1 membership references already materialized candidate records and contains no executable transforms or delta objects. |
| `invariant.rtg.migration.references_are_data` | `RtgMigration` | `migration` | Referenced records remain owned by their source components; migration stores identities and intent only. |
| `invariant.rtg.migration.no_store_mutation` | `RtgMigration` | `migration` | This component does not read or mutate graph, schema, or constraint stores. |
| `invariant.rtg.migration.status_transition_controlled` | `RtgMigration` | `migration` | Status changes, including replacement of an existing ID, preserve status or obey the single transition table. |
| `invariant.rtg.migration.status_is_tracking_not_proof` | `RtgMigration` | `migration` | Ready status records caller intent and is not proof that referenced cutover state is valid. |
| `invariant.rtg.migration.completed_history_is_external` | `RtgMigration` | `migration` | Durable completed history belongs to controller audit. |
| `invariant.rtg.migration.rollback_is_forward_change_v1` | `RtgMigration` | `migration` | V1 rollback is represented by a later forward migration, not a special status or reverse executable operation. |
| `contract.rtg.migration.export_migration_snapshot.failures` | `ExportMigrationSnapshot` | `migration.exportSnapshot` | Export is read-only and has no declared domain failure. |
| `contract.rtg.migration.put_migration.failures` | `PutMigration` | `migration.putMigration` | Rejected creation or replacement leaves all migration records and indexes unchanged; an existing record may preserve status or follow the lifecycle transition table. |
| `contract.rtg.migration.get_migration.failures` | `GetMigration` | `migration.getMigration` | Read failure has no effect. |
| `contract.rtg.migration.list_migrations.failures` | `ListMigrations` | `migration.listMigrations` | Read failure has no effect. |
| `contract.rtg.migration.set_migration_status.failures` | `SetMigrationStatus` | `migration.setStatus` | A rejected transition changes neither status nor metadata. |
| `contract.rtg.migration.add_migration_evidence.failures` | `AddMigrationEvidence` | `migration.addEvidence` | Duplicate or invalid evidence changes no record. |
| `contract.rtg.migration.delete_migration.failures` | `DeleteMigration` | `migration.deleteMigration` | Draft, ready, and failed records are not deleted and rejection has no effect. |
| `contract.rtg.migration.build_migration_cutover_plan.failures` | `BuildMigrationCutoverPlan` | `migration.buildCutoverPlan` | Plan construction reads and mutates no component store. |
| `contract.rtg.migration.create_empty_rtg_migration.failures` | `CreateEmptyRtgMigration` | `createEmptyRtgMigrationSubject` | Construction has no declared domain failure. |
| `contract.rtg.migration.import_rtg_migration_snapshot.failures` | `ImportRtgMigrationSnapshot` | `importRtgMigrationSnapshotSubject` | Failure returns no partially imported store. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgMigrationReplacement` | `attribute` | `oldResourceId: Uuid`, `newResourceId: Uuid` | Defined by its typed fields and action requirements. |
| `RtgMigrationEvidence` | `attribute` | `evidenceId: String`, `kind: String`, `reference: String`, `summary: String`, `metadata: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgMigrationRecord` | `item` | `migrationId[0..1]: String`, `description: String`, `status: RtgMigrationStatus` = `RtgMigrationStatus::draft`, `schemaMakeLive[0..*]: Uuid`, `schemaMakeNonLive[0..*]: Uuid`, `constraintMakeLive[0..*]: Uuid`, `constraintMakeNonLive[0..*]: Uuid`, `graphMakeLive[0..*]: Uuid`, `graphMakeNonLive[0..*]: Uuid`, `schemaReplacements[0..*]: RtgMigrationReplacement`, `constraintReplacements[0..*]: RtgMigrationReplacement`, `graphReplacements[0..*]: RtgMigrationReplacement`, `evidence[0..*] ordered: RtgMigrationEvidence`, `metadata: JsonObject` | Identity may be absent only on write. Stored records have a concrete generated or caller-supplied ID. The record stores references and intent, never referenced resources or executable transforms. |
| `RtgMigrationRecordList` | `attribute` | `migrations[0..*] ordered: RtgMigrationRecord` | Defined by its typed fields and action requirements. |
| `RtgMigrationSnapshot` | `attribute` | `migrations[0..*] ordered: RtgMigrationRecord` | Defined by its typed fields and action requirements. |
| `RtgMigrationDeleteResult` | `attribute` | `deletedMigration: RtgMigrationRecord` | Defined by its typed fields and action requirements. |
| `RtgMigrationCutoverPlan` | `attribute` | `migrationId: String`, `schemaMakeLive[0..*] ordered: Uuid`, `schemaMakeNonLive[0..*] ordered: Uuid`, `constraintMakeLive[0..*] ordered: Uuid`, `constraintMakeNonLive[0..*] ordered: Uuid`, `graphMakeLive[0..*] ordered: Uuid`, `graphMakeNonLive[0..*] ordered: Uuid`, `schemaReplacements[0..*] ordered: RtgMigrationReplacement`, `constraintReplacements[0..*] ordered: RtgMigrationReplacement`, `graphReplacements[0..*] ordered: RtgMigrationReplacement` | Defined by its typed fields and action requirements. |
| `RtgMigrationNotFound` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgMigrationSnapshotInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgMigrationIdInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgMigrationIdConflict` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgMigrationRecordInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgMigrationStatusInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgMigrationStatusTransitionInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgMigrationDeleteNotAllowed` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgMigrationEvidenceInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| `RtgMigrationStatus` | `draft`, `ready`, `applied`, `failed`, `abandoned` |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `PutMigrationContractVerification` | `PutMigration` | `putMigrationEffect`, `membershipSemantics`, `putMigrationFailureSemantics` | `components/rtg/migration/tests/test_rtg_migration_contract.py#PutMigrationContractVerification` |
| `SetMigrationStatusContractVerification` | `SetMigrationStatus` | `statusTransitionTable`, `setMigrationStatusFailureSemantics` | `components/rtg/migration/tests/test_rtg_migration_contract.py#SetMigrationStatusContractVerification` |
| `AddMigrationEvidenceContractVerification` | `AddMigrationEvidence` | `evidenceEffect`, `addMigrationEvidenceFailureSemantics` | `components/rtg/migration/tests/test_rtg_migration_contract.py#AddMigrationEvidenceContractVerification` |
| `DeleteMigrationContractVerification` | `DeleteMigration` | `deleteEffect`, `deleteMigrationFailureSemantics` | `components/rtg/migration/tests/test_rtg_migration_contract.py#DeleteMigrationContractVerification` |
| `BuildMigrationCutoverPlanContractVerification` | `BuildMigrationCutoverPlan` | `cutoverPlanEffect`, `buildMigrationCutoverPlanFailureSemantics` | `components/rtg/migration/tests/test_rtg_migration_contract.py#BuildMigrationCutoverPlanContractVerification` |
| `ExportMigrationSnapshotContractVerification` | `ExportMigrationSnapshot` | `exportMigrationSnapshotFailureSemantics` | `components/rtg/migration/tests/test_rtg_migration_contract.py#ExportMigrationSnapshotContractVerification` |
| `GetMigrationContractVerification` | `GetMigration` | `getMigrationFailureSemantics` | `components/rtg/migration/tests/test_rtg_migration_contract.py#GetMigrationContractVerification` |
| `ListMigrationsContractVerification` | `ListMigrations` | `listMigrationsFailureSemantics` | `components/rtg/migration/tests/test_rtg_migration_contract.py#ListMigrationsContractVerification` |
| `CreateEmptyRtgMigrationContractVerification` | `CreateEmptyRtgMigration` | `createEmptyRtgMigrationFailureSemantics` | `components/rtg/migration/tests/test_rtg_migration_contract.py#CreateEmptyRtgMigrationContractVerification` |
| `ImportRtgMigrationSnapshotContractVerification` | `ImportRtgMigrationSnapshot` | `importRtgMigrationSnapshotFailureSemantics` | `components/rtg/migration/tests/test_rtg_migration_contract.py#ImportRtgMigrationSnapshotContractVerification` |
| `RtgMigrationBoundaryVerification` | `RtgMigration` | `intentionalBoundary`, `idUnique`, `cutoverSetsDisjoint`, `notNormalCrud`, `candidatesMaterialized`, `referencesAreData`, `noStoreMutation`, `statusTransitionControlled`, `statusTrackingNotProof`, `completedHistoryExternal`, `rollbackForwardChange` | `components/rtg/migration/tests/test_rtg_migration_contract.py#RtgMigrationBoundaryVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
