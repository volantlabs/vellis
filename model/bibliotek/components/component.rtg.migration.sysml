library package BibliotekRtgMigration {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;

    enum def RtgMigrationStatus {
        enum draft; enum ready; enum applied; enum failed; enum abandoned;
        doc /* Observable record lifecycle. Transition legality is defined by statusTransitionTable; no event-driven state execution semantics are implied. */
    }

    calc def MigrationStatusTransitionAllowed {
        in current : RtgMigrationStatus;
        in requested : RtgMigrationStatus;
        return allowed : Boolean = current == requested or
            (current == RtgMigrationStatus::draft and
                (requested == RtgMigrationStatus::ready or requested == RtgMigrationStatus::abandoned)) or
            (current == RtgMigrationStatus::ready and
                (requested == RtgMigrationStatus::draft or requested == RtgMigrationStatus::applied or
                 requested == RtgMigrationStatus::failed or requested == RtgMigrationStatus::abandoned)) or
            (current == RtgMigrationStatus::failed and
                (requested == RtgMigrationStatus::ready or requested == RtgMigrationStatus::abandoned));
    }

    attribute def RtgMigrationReplacement { attribute oldResourceId : Uuid; attribute newResourceId : Uuid; }
    attribute def RtgMigrationEvidence {
        attribute evidenceId : String;
        attribute kind : String;
        attribute reference : String;
        attribute summary : String;
        attribute 'metadata' : JsonObject;
    }
    item def RtgMigrationRecord {
        attribute migrationId[0..1] : String;
        attribute description : String;
        attribute status : RtgMigrationStatus = RtgMigrationStatus::draft;
        attribute schemaMakeLive[0..*] : Uuid;
        attribute schemaMakeNonLive[0..*] : Uuid;
        attribute constraintMakeLive[0..*] : Uuid;
        attribute constraintMakeNonLive[0..*] : Uuid;
        attribute graphMakeLive[0..*] : Uuid;
        attribute graphMakeNonLive[0..*] : Uuid;
        attribute schemaReplacements[0..*] : RtgMigrationReplacement;
        attribute constraintReplacements[0..*] : RtgMigrationReplacement;
        attribute graphReplacements[0..*] : RtgMigrationReplacement;
        attribute evidence[0..*] ordered : RtgMigrationEvidence;
        attribute 'metadata' : JsonObject;
        doc /* Identity may be absent only on write. Stored records have a concrete generated or caller-supplied ID. The record stores references and intent, never referenced resources or executable transforms. */
    }
    attribute def RtgMigrationRecordList { item migrations[0..*] ordered : RtgMigrationRecord; }
    attribute def RtgMigrationSnapshot { item migrations[0..*] ordered : RtgMigrationRecord; }
    attribute def RtgMigrationDeleteResult { item deletedMigration : RtgMigrationRecord; }
    attribute def RtgMigrationCutoverPlan {
        attribute migrationId : String;
        attribute schemaMakeLive[0..*] ordered : Uuid;
        attribute schemaMakeNonLive[0..*] ordered : Uuid;
        attribute constraintMakeLive[0..*] ordered : Uuid;
        attribute constraintMakeNonLive[0..*] ordered : Uuid;
        attribute graphMakeLive[0..*] ordered : Uuid;
        attribute graphMakeNonLive[0..*] ordered : Uuid;
        attribute schemaReplacements[0..*] ordered : RtgMigrationReplacement;
        attribute constraintReplacements[0..*] ordered : RtgMigrationReplacement;
        attribute graphReplacements[0..*] ordered : RtgMigrationReplacement;
    }

    attribute def RtgMigrationNotFound { attribute 'message' : String; }
    attribute def RtgMigrationSnapshotInvalid { attribute 'message' : String; }
    attribute def RtgMigrationIdInvalid { attribute 'message' : String; }
    attribute def RtgMigrationIdConflict { attribute 'message' : String; }
    attribute def RtgMigrationRecordInvalid { attribute 'message' : String; }
    attribute def RtgMigrationStatusInvalid { attribute 'message' : String; }
    attribute def RtgMigrationStatusTransitionInvalid { attribute 'message' : String; }
    attribute def RtgMigrationDeleteNotAllowed { attribute 'message' : String; }
    attribute def RtgMigrationEvidenceInvalid { attribute 'message' : String; }

    action def ExportMigrationSnapshot { out 'snapshot' : RtgMigrationSnapshot; doc /* Export all records without inspecting referenced component state. */ @FailureContract { errorIds = (); } }
    action def PutMigration {
        in migration : RtgMigrationRecord;
        out stored : RtgMigrationRecord;
        doc /* Generate or preserve migration identity and create or lifecycle-safe fully replace one structurally valid record. */
        @FailureContract { errorIds = ("RtgMigrationIdInvalid", "RtgMigrationRecordInvalid", "RtgMigrationStatusInvalid", "RtgMigrationStatusTransitionInvalid", "RtgMigrationEvidenceInvalid"); }
    }
    action def GetMigration { in migrationId : String; out migration : RtgMigrationRecord; doc /* Return one migration tracking record by ID. */ @FailureContract { errorIds = ("RtgMigrationNotFound"); } }
    action def ListMigrations { in status[0..1] : RtgMigrationStatus; out result : RtgMigrationRecordList; doc /* Return all records or records in one status in deterministic migration-ID order. */ @FailureContract { errorIds = ("RtgMigrationStatusInvalid"); } }
    action def SetMigrationStatus {
        in migrationId : String;
        in status : RtgMigrationStatus;
        in statusMetadata[0..1] : JsonObject;
        out migration : RtgMigrationRecord;
        doc /* Apply only a permitted lifecycle transition and replace status metadata with the supplied object or an empty object. */
        @FailureContract { errorIds = ("RtgMigrationIdInvalid", "RtgMigrationNotFound", "RtgMigrationRecordInvalid", "RtgMigrationStatusInvalid", "RtgMigrationStatusTransitionInvalid"); }
    }
    action def AddMigrationEvidence { in migrationId : String; in evidence : RtgMigrationEvidence; out migration : RtgMigrationRecord; doc /* Append one evidence identity without interpreting or fetching its referenced artifact. */ @FailureContract { errorIds = ("RtgMigrationNotFound", "RtgMigrationEvidenceInvalid"); } }
    action def DeleteMigration { in migrationId : String; out result : RtgMigrationDeleteResult; doc /* Delete one applied or abandoned record only; referenced resources and durable controller history remain unchanged. */ @FailureContract { errorIds = ("RtgMigrationIdInvalid", "RtgMigrationNotFound", "RtgMigrationDeleteNotAllowed"); } }
    action def BuildMigrationCutoverPlan { in migration : RtgMigrationRecord; out plan : RtgMigrationCutoverPlan; doc /* Purely copy ordered lifecycle membership and replacement mappings from a concrete valid migration record. */ @FailureContract { errorIds = ("RtgMigrationRecordInvalid"); } }

    part def <'component.rtg.migration'> RtgMigration {
        doc /* Own identity-bearing migration records, lifecycle transitions, membership, and evidence. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        item migrationRecords[0..*] : RtgMigrationRecord { doc /* Canonical component-owned migration occurrences. */ }
        derived attribute statusIndex : JsonObject { doc /* Ephemeral status index derived from canonical migration records. */ }
        perform action exportSnapshot[0..*] : ExportMigrationSnapshot;
        perform action putMigration[0..*] : PutMigration;
        perform action getMigration[0..*] : GetMigration;
        perform action listMigrations[0..*] : ListMigrations;
        perform action setStatus[0..*] : SetMigrationStatus;
        perform action addEvidence[0..*] : AddMigrationEvidence;
        perform action deleteMigration[0..*] : DeleteMigration;
        perform action buildCutoverPlan[0..*] : BuildMigrationCutoverPlan;
        dependency snapshotState from exportSnapshot to migrationRecords { @StateAccess { kind = StateAccessKind::read; } doc /* return all migration records in migration-ID order. */ }
        dependency putState from putMigration to migrationRecords { @StateAccess { kind = StateAccessKind::write; } doc /* create or lifecycle-safe replace one complete record. */ }
        dependency statusState from setStatus to migrationRecords { @StateAccess { kind = StateAccessKind::write; } doc /* apply one allowed lifecycle transition or same-status metadata update. */ }
        dependency evidenceState from addEvidence to migrationRecords { @StateAccess { kind = StateAccessKind::write; } doc /* append one evidence identity not already present. */ }
        dependency deleteState from deleteMigration to migrationRecords { @StateAccess { kind = StateAccessKind::delete; } doc /* remove one terminal applied or abandoned record. */ }
        dependency planState from buildCutoverPlan to migrationRecords { @StateAccess { kind = StateAccessKind::read; } doc /* purely copy cutover membership from the supplied record. */ }
        dependency getState from getMigration to migrationRecords { @StateAccess { kind = StateAccessKind::read; } doc /* read one canonical record. */ }
        dependency listState from listMigrations to statusIndex { @StateAccess { kind = StateAccessKind::read; } doc /* read deterministic status index. */ }
    }

    action def CreateEmptyRtgMigration { out part migration : RtgMigration; doc /* Return an empty store and status index. */ @FailureContract { errorIds = (); } }
    action def ImportRtgMigrationSnapshot { in 'snapshot' : RtgMigrationSnapshot; out part migration : RtgMigration; doc /* Validate the container and every record, concrete identity, lifecycle value, JSON value, membership rule, evidence identity, and migration-ID uniqueness rule before exposing the store. Snapshot construction does not apply transitions between records. */ @FailureContract { errorIds = ("RtgMigrationSnapshotInvalid", "RtgMigrationIdInvalid", "RtgMigrationIdConflict", "RtgMigrationRecordInvalid", "RtgMigrationStatusInvalid", "RtgMigrationEvidenceInvalid"); } }


    requirement <'contract.rtg.migration.put_effect'> putMigrationEffect {
        subject operation : PutMigration;
        require constraint {
            doc /* A new record may begin in any valid status. Replacing an existing ID must preserve status or satisfy MigrationStatusTransitionAllowed for the stored and requested statuses; all other fields are fully replaced. */
        }
    }

    requirement <'contract.rtg.migration.membership'> membershipSemantics {
        subject operation : PutMigration;
        require constraint {
            doc /* Each make-live and make-non-live collection is a duplicate-free logical set and the two sets are disjoint per resource kind. Each replacement maps a distinct old identity in make-non-live to a distinct new identity in make-live; replacement old and new identities differ. Additions and removals without a replacement remain legal. Stored and returned encodings use ascending UUID order, with replacements ordered by old then new UUID. */
        }
    }

    requirement <'contract.rtg.migration.status_transitions'> statusTransitionTable {
        subject operation : SetMigrationStatus;
        require constraint {
            doc /* The stored and requested statuses must satisfy MigrationStatusTransitionAllowed. Thus draft changes to ready or abandoned; ready to draft, applied, failed, or abandoned; failed to ready or abandoned; applied and abandoned are terminal. Every accepted transition, including same-status, replaces metadata.status_metadata with the supplied JSON object or an empty object and preserves unrelated metadata. */
        }
    }

    requirement <'contract.rtg.migration.evidence_effect'> evidenceEffect {
        subject operation : AddMigrationEvidence;
        require constraint {
            doc /* Evidence IDs are unique within a migration; success appends one evidence record and preserves membership and status. */
        }
    }

    requirement <'contract.rtg.migration.delete_effect'> deleteEffect {
        subject operation : DeleteMigration;
        require constraint {
            doc /* Only applied and abandoned records are deletable. Rejected deletion leaves state unchanged and never removes durable controller history. */
        }
    }

    requirement <'contract.rtg.migration.cutover_plan'> cutoverPlanEffect {
        subject operation : BuildMigrationCutoverPlan;
        require constraint {
            doc /* The plan deterministically copies all make-live, make-non-live, and replacement membership without reading or mutating referenced component state. */
        }
    }

    requirement <'contract.rtg.migration.intentional_boundary'> intentionalBoundary {
        subject migration : RtgMigration;
        require constraint {
            doc /* Migration stores lifecycle intent, membership, mappings, and evidence only. It does not establish semantic readiness, validate or mutate referenced stores, execute transforms or rollback, enforce graph constraints, own durable audit/persistence/authorization/UI, or guarantee cross-store atomicity or distributed locking. */
        }
    }

    requirement <'invariant.rtg.migration.id_unique'> idUnique {
        subject migration : RtgMigration;
        require constraint {
            doc /* Migration IDs are unique. */
        }
    }

    requirement <'invariant.rtg.migration.cutover_sets_disjoint'> cutoverSetsDisjoint {
        subject migration : RtgMigration;
        require constraint {
            doc /* Make-live and make-non-live sets are unique and disjoint within each resource kind. Replacement mappings are one-to-one, map old make-non-live identities to new make-live identities, and never map an identity to itself. */
        }
    }

    requirement <'invariant.rtg.migration.not_normal_crud'> notNormalCrud {
        subject migration : RtgMigration;
        require constraint {
            doc /* Migration records describe coordinated schema, constraint, and non-live graph lifecycle work, not ordinary live graph CRUD. */
        }
    }

    requirement <'invariant.rtg.migration.candidates_are_materialized_v1'> candidatesMaterialized {
        subject migration : RtgMigration;
        require constraint {
            doc /* V1 membership references already materialized candidate records and contains no executable transforms or delta objects. */
        }
    }

    requirement <'invariant.rtg.migration.references_are_data'> referencesAreData {
        subject migration : RtgMigration;
        require constraint {
            doc /* Referenced records remain owned by their source components; migration stores identities and intent only. */
        }
    }

    requirement <'invariant.rtg.migration.no_store_mutation'> noStoreMutation {
        subject migration : RtgMigration;
        require constraint {
            doc /* This component does not read or mutate graph, schema, or constraint stores. */
        }
    }

    requirement <'invariant.rtg.migration.status_transition_controlled'> statusTransitionControlled {
        subject migration : RtgMigration;
        require constraint {
            doc /* Status changes, including replacement of an existing ID, preserve status or obey the single transition table. */
        }
    }

    requirement <'invariant.rtg.migration.status_is_tracking_not_proof'> statusTrackingNotProof {
        subject migration : RtgMigration;
        require constraint {
            doc /* Ready status records caller intent and is not proof that referenced cutover state is valid. */
        }
    }

    requirement <'invariant.rtg.migration.completed_history_is_external'> completedHistoryExternal {
        subject migration : RtgMigration;
        require constraint {
            doc /* Durable completed history belongs to controller audit. */
        }
    }

    requirement <'invariant.rtg.migration.rollback_is_forward_change_v1'> rollbackForwardChange {
        subject migration : RtgMigration;
        require constraint {
            doc /* V1 rollback is represented by a later forward migration, not a special status or reverse executable operation. */
        }
    }

    requirement <'contract.rtg.migration.export_migration_snapshot.failures'> exportMigrationSnapshotFailureSemantics {
        subject operation : ExportMigrationSnapshot;
        require constraint {
            doc /* Export is read-only and has no declared domain failure. */
        }
    }

    requirement <'contract.rtg.migration.put_migration.failures'> putMigrationFailureSemantics {
        subject operation : PutMigration;
        require constraint {
            doc /* Rejected creation or replacement leaves all migration records and indexes unchanged; an existing record may preserve status or follow the lifecycle transition table. */
        }
    }

    requirement <'contract.rtg.migration.get_migration.failures'> getMigrationFailureSemantics {
        subject operation : GetMigration;
        require constraint {
            doc /* Read failure has no effect. */
        }
    }

    requirement <'contract.rtg.migration.list_migrations.failures'> listMigrationsFailureSemantics {
        subject operation : ListMigrations;
        require constraint {
            doc /* Read failure has no effect. */
        }
    }

    requirement <'contract.rtg.migration.set_migration_status.failures'> setMigrationStatusFailureSemantics {
        subject operation : SetMigrationStatus;
        require constraint {
            doc /* A rejected transition changes neither status nor metadata. */
        }
    }

    requirement <'contract.rtg.migration.add_migration_evidence.failures'> addMigrationEvidenceFailureSemantics {
        subject operation : AddMigrationEvidence;
        require constraint {
            doc /* Duplicate or invalid evidence changes no record. */
        }
    }

    requirement <'contract.rtg.migration.delete_migration.failures'> deleteMigrationFailureSemantics {
        subject operation : DeleteMigration;
        require constraint {
            doc /* Draft, ready, and failed records are not deleted and rejection has no effect. */
        }
    }

    requirement <'contract.rtg.migration.build_migration_cutover_plan.failures'> buildMigrationCutoverPlanFailureSemantics {
        subject operation : BuildMigrationCutoverPlan;
        require constraint {
            doc /* Plan construction reads and mutates no component store. */
        }
    }

    requirement <'contract.rtg.migration.create_empty_rtg_migration.failures'> createEmptyRtgMigrationFailureSemantics {
        subject operation : CreateEmptyRtgMigration;
        require constraint {
            doc /* Construction has no declared domain failure. */
        }
    }

    requirement <'contract.rtg.migration.import_rtg_migration_snapshot.failures'> importRtgMigrationSnapshotFailureSemantics {
        subject operation : ImportRtgMigrationSnapshot;
        require constraint {
            doc /* Failure returns no partially imported store. */
        }
    }

    part contractContext {
        part migration : RtgMigration;
        satisfy putMigrationEffect by migration.putMigration;
        satisfy membershipSemantics by migration.putMigration;
        satisfy statusTransitionTable by migration.setStatus;
        satisfy evidenceEffect by migration.addEvidence;
        satisfy deleteEffect by migration.deleteMigration;
        satisfy cutoverPlanEffect by migration.buildCutoverPlan;
        satisfy intentionalBoundary by migration;
        satisfy idUnique by migration;
        satisfy cutoverSetsDisjoint by migration;
        satisfy notNormalCrud by migration;
        satisfy candidatesMaterialized by migration;
        satisfy referencesAreData by migration;
        satisfy noStoreMutation by migration;
        satisfy statusTransitionControlled by migration;
        satisfy statusTrackingNotProof by migration;
        satisfy completedHistoryExternal by migration;
        satisfy rollbackForwardChange by migration;

        satisfy exportMigrationSnapshotFailureSemantics by migration.exportSnapshot;
        satisfy putMigrationFailureSemantics by migration.putMigration;
        satisfy getMigrationFailureSemantics by migration.getMigration;
        satisfy listMigrationsFailureSemantics by migration.listMigrations;
        satisfy setMigrationStatusFailureSemantics by migration.setStatus;
        satisfy addMigrationEvidenceFailureSemantics by migration.addEvidence;
        satisfy deleteMigrationFailureSemantics by migration.deleteMigration;
        satisfy buildMigrationCutoverPlanFailureSemantics by migration.buildCutoverPlan;
        action createEmptyRtgMigrationSubject : CreateEmptyRtgMigration;
        satisfy createEmptyRtgMigrationFailureSemantics by createEmptyRtgMigrationSubject;
        action importRtgMigrationSnapshotSubject : ImportRtgMigrationSnapshot;
        satisfy importRtgMigrationSnapshotFailureSemantics by importRtgMigrationSnapshotSubject;
    }

    verification def PutMigrationContractVerification {
        subject operation : PutMigration;
        objective {
            verify putMigrationEffect;
            verify membershipSemantics;

            verify putMigrationFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/rtg/migration/tests/test_rtg_migration_contract.py#PutMigrationContractVerification";
            implementationScope = "InMemoryRtgMigration";
        }
    }

    verification def SetMigrationStatusContractVerification {
        subject operation : SetMigrationStatus;
        objective {
            verify statusTransitionTable;

            verify setMigrationStatusFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/rtg/migration/tests/test_rtg_migration_contract.py#SetMigrationStatusContractVerification";
            implementationScope = "InMemoryRtgMigration";
        }
    }

    verification def AddMigrationEvidenceContractVerification {
        subject operation : AddMigrationEvidence;
        objective {
            verify evidenceEffect;

            verify addMigrationEvidenceFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/rtg/migration/tests/test_rtg_migration_contract.py#AddMigrationEvidenceContractVerification";
            implementationScope = "InMemoryRtgMigration";
        }
    }

    verification def DeleteMigrationContractVerification {
        subject operation : DeleteMigration;
        objective {
            verify deleteEffect;

            verify deleteMigrationFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/rtg/migration/tests/test_rtg_migration_contract.py#DeleteMigrationContractVerification";
            implementationScope = "InMemoryRtgMigration";
        }
    }

    verification def BuildMigrationCutoverPlanContractVerification {
        subject operation : BuildMigrationCutoverPlan;
        objective {
            verify cutoverPlanEffect;

            verify buildMigrationCutoverPlanFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/rtg/migration/tests/test_rtg_migration_contract.py#BuildMigrationCutoverPlanContractVerification";
            implementationScope = "InMemoryRtgMigration";
        }
    }
    verification def ExportMigrationSnapshotContractVerification {
        subject operation : ExportMigrationSnapshot;
        objective { verify exportMigrationSnapshotFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/migration/tests/test_rtg_migration_contract.py#ExportMigrationSnapshotContractVerification"; implementationScope = "InMemoryRtgMigration"; }
    }

    verification def GetMigrationContractVerification {
        subject operation : GetMigration;
        objective { verify getMigrationFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/migration/tests/test_rtg_migration_contract.py#GetMigrationContractVerification"; implementationScope = "InMemoryRtgMigration"; }
    }

    verification def ListMigrationsContractVerification {
        subject operation : ListMigrations;
        objective { verify listMigrationsFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/migration/tests/test_rtg_migration_contract.py#ListMigrationsContractVerification"; implementationScope = "InMemoryRtgMigration"; }
    }

    verification def CreateEmptyRtgMigrationContractVerification {
        subject operation : CreateEmptyRtgMigration;
        objective { verify createEmptyRtgMigrationFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/migration/tests/test_rtg_migration_contract.py#CreateEmptyRtgMigrationContractVerification"; implementationScope = "InMemoryRtgMigration"; }
    }

    verification def ImportRtgMigrationSnapshotContractVerification {
        subject operation : ImportRtgMigrationSnapshot;
        objective { verify importRtgMigrationSnapshotFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/migration/tests/test_rtg_migration_contract.py#ImportRtgMigrationSnapshotContractVerification"; implementationScope = "InMemoryRtgMigration"; }
    }



    verification def RtgMigrationBoundaryVerification {
        subject migration : RtgMigration;
        objective { verify intentionalBoundary; verify idUnique; verify cutoverSetsDisjoint; verify notNormalCrud; verify candidatesMaterialized; verify referencesAreData; verify noStoreMutation; verify statusTransitionControlled; verify statusTrackingNotProof; verify completedHistoryExternal; verify rollbackForwardChange; }
        @EvidenceBinding { evidenceId = "components/rtg/migration/tests/test_rtg_migration_contract.py#RtgMigrationBoundaryVerification"; implementationScope = "InMemoryRtgMigration"; }
    }
}
