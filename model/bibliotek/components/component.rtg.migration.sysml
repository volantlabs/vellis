library package BibliotekRtgMigration {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;

    enum def RtgMigrationStatus {
        enum draft; enum ready; enum applied; enum failed; enum abandoned;
        doc /* Observable record lifecycle. Transition legality is defined by statusTransitionTable; no event-driven state execution semantics are implied. */
    }

    attribute def RtgMigrationReplacement { attribute oldResourceId : Uuid; attribute newResourceId : Uuid; }
    attribute def RtgMigrationEvidence {
        attribute evidenceId : String;
        attribute kind : String;
        attribute reference : String;
        attribute summary : String;
        attribute metadata : JsonObject;
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
        attribute evidence[0..*] : RtgMigrationEvidence;
        attribute metadata : JsonObject;
        doc /* Identity may be absent only on write. Stored records have a concrete generated or caller-supplied ID. The record stores references and intent, never referenced resources or executable transforms. */
    }
    attribute def RtgMigrationRecordList { attribute migrations[0..*] : RtgMigrationRecord; }
    attribute def RtgMigrationSnapshot { attribute migrations[0..*] : RtgMigrationRecord; }
    attribute def RtgMigrationDeleteResult { attribute deletedMigration : RtgMigrationRecord; }
    attribute def RtgMigrationCutoverPlan {
        attribute migrationId : String;
        attribute schemaMakeLive[0..*] : Uuid;
        attribute schemaMakeNonLive[0..*] : Uuid;
        attribute constraintMakeLive[0..*] : Uuid;
        attribute constraintMakeNonLive[0..*] : Uuid;
        attribute graphMakeLive[0..*] : Uuid;
        attribute graphMakeNonLive[0..*] : Uuid;
        attribute schemaReplacements[0..*] : RtgMigrationReplacement;
        attribute constraintReplacements[0..*] : RtgMigrationReplacement;
        attribute graphReplacements[0..*] : RtgMigrationReplacement;
    }

    attribute def RtgMigrationNotFound { attribute message : String; }
    attribute def RtgMigrationSnapshotInvalid { attribute message : String; }
    attribute def RtgMigrationIdInvalid { attribute message : String; }
    attribute def RtgMigrationIdConflict { attribute message : String; }
    attribute def RtgMigrationRecordInvalid { attribute message : String; }
    attribute def RtgMigrationReferenceInvalid { attribute message : String; }
    attribute def RtgMigrationStatusInvalid { attribute message : String; }
    attribute def RtgMigrationStatusTransitionInvalid { attribute message : String; }
    attribute def RtgMigrationDeleteInvalid { attribute message : String; }
    attribute def RtgMigrationEvidenceInvalid { attribute message : String; }

    action def ExportMigrationSnapshot { out snapshot : RtgMigrationSnapshot; doc /* Export all records without inspecting referenced component state. */ @FailureContract { errorIds = (); obligation = "Export is read-only and has no declared domain failure."; } }
    action def PutMigration {
        in migration : RtgMigrationRecord;
        out stored : RtgMigrationRecord;
        doc /* Generate or preserve migration identity and create or lifecycle-safe fully replace one structurally valid record. */
        @FailureContract { errorIds = ("RtgMigrationRecordInvalid", "RtgMigrationIdConflict", "RtgMigrationStatusTransitionInvalid"); obligation = "Rejected creation or replacement leaves all migration records and indexes unchanged; an existing record may preserve status or follow the lifecycle transition table."; }
    }
    action def GetMigration { in migrationId : String; out migration : RtgMigrationRecord; doc /* Return one migration tracking record by ID. */ @FailureContract { errorIds = ("RtgMigrationNotFound"); obligation = "Read failure has no effect."; } }
    action def ListMigrations { in status[0..1] : RtgMigrationStatus; out result : RtgMigrationRecordList; doc /* Return all records or records in one status in deterministic migration-ID order. */ @FailureContract { errorIds = ("RtgMigrationStatusInvalid"); obligation = "Read failure has no effect."; } }
    action def SetMigrationStatus {
        in migrationId : String;
        in status : RtgMigrationStatus;
        in statusMetadata[0..1] : JsonObject;
        out migration : RtgMigrationRecord;
        doc /* Apply only a permitted lifecycle transition and replace status metadata with the supplied object or an empty object. */
        @FailureContract { errorIds = ("RtgMigrationNotFound", "RtgMigrationStatusInvalid", "RtgMigrationStatusTransitionInvalid"); obligation = "A rejected transition changes neither status nor metadata."; }
    }
    action def AddMigrationEvidence { in migrationId : String; in evidence : RtgMigrationEvidence; out migration : RtgMigrationRecord; doc /* Append one evidence identity without interpreting or fetching its referenced artifact. */ @FailureContract { errorIds = ("RtgMigrationNotFound", "RtgMigrationEvidenceInvalid"); obligation = "Duplicate or invalid evidence changes no record."; } }
    action def DeleteMigration { in migrationId : String; out result : RtgMigrationDeleteResult; doc /* Delete one applied or abandoned record only; referenced resources and durable controller history remain unchanged. */ @FailureContract { errorIds = ("RtgMigrationNotFound", "RtgMigrationDeleteInvalid"); obligation = "Draft, ready, and failed records are not deleted and rejection has no effect."; } }
    action def BuildMigrationCutoverPlan { in migration : RtgMigrationRecord; out plan : RtgMigrationCutoverPlan; doc /* Purely copy ordered lifecycle membership and replacement mappings from a concrete valid migration record. */ @FailureContract { errorIds = ("RtgMigrationRecordInvalid"); obligation = "Plan construction reads and mutates no component store."; } }

    part def RtgMigration {
        doc /* Own identity-bearing migration records, lifecycle transitions, membership, and evidence. */
        @SpecIdentity { id = "component.rtg.migration"; lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        @DependencyPolicy { allowedComponentIds = (); forbiddenComponentIds = ("component.rtg.graph", "component.rtg.schema", "component.rtg.controller"); }
        item migrationRecords[0..*] : RtgMigrationRecord { @StateAuthority { authority = StateAuthorityKind::canonicalOwner; lifetime = StateLifetime::componentCoupled; persistence = StatePersistence::ephemeral; } }
        attribute statusIndex : JsonObject { @StateAuthority { authority = StateAuthorityKind::derived; lifetime = StateLifetime::componentCoupled; persistence = StatePersistence::ephemeral; } }
        perform action exportSnapshot[0..*] : ExportMigrationSnapshot;
        perform action putMigration[0..*] : PutMigration;
        perform action getMigration[0..*] : GetMigration;
        perform action listMigrations[0..*] : ListMigrations;
        perform action setStatus[0..*] : SetMigrationStatus;
        perform action addEvidence[0..*] : AddMigrationEvidence;
        perform action deleteMigration[0..*] : DeleteMigration;
        perform action buildCutoverPlan[0..*] : BuildMigrationCutoverPlan;
        dependency snapshotState from exportSnapshot to migrationRecords { @StateAccess { kind = StateAccessKind::read; effect = "return all migration records in migration-ID order"; } }
        dependency putState from putMigration to migrationRecords { @StateAccess { kind = StateAccessKind::write; effect = "create or lifecycle-safe replace one complete record"; } }
        dependency statusState from setStatus to migrationRecords { @StateAccess { kind = StateAccessKind::write; effect = "apply one allowed lifecycle transition or same-status metadata update"; } }
        dependency evidenceState from addEvidence to migrationRecords { @StateAccess { kind = StateAccessKind::write; effect = "append one evidence identity not already present"; } }
        dependency deleteState from deleteMigration to migrationRecords { @StateAccess { kind = StateAccessKind::delete; effect = "remove one terminal applied or abandoned record"; } }
        dependency planState from buildCutoverPlan to migrationRecords { @StateAccess { kind = StateAccessKind::none; effect = "purely copy cutover membership from the supplied record"; } }
        dependency getState from getMigration to migrationRecords { @StateAccess { kind = StateAccessKind::read; effect = "read one canonical record"; } }
        dependency listState from listMigrations to statusIndex { @StateAccess { kind = StateAccessKind::read; effect = "read deterministic status index"; } }
    }

    action def CreateEmptyRtgMigration { out part migration : RtgMigration; doc /* Return an empty store and status index. */ @FailureContract { errorIds = (); obligation = "Construction has no declared domain failure."; } }
    action def ImportRtgMigrationSnapshot { in snapshot : RtgMigrationSnapshot; out part migration : RtgMigration; doc /* Validate every record, identity, reference, lifecycle value, and uniqueness rule before rebuilding indexes and exposing the store. */ @FailureContract { errorIds = ("RtgMigrationSnapshotInvalid", "RtgMigrationRecordInvalid", "RtgMigrationIdConflict", "RtgMigrationReferenceInvalid"); obligation = "Failure returns no partially imported store."; } }

    requirement putMigrationEffect { subject operation : PutMigration; doc /* A new record may begin in any valid status. Replacing an existing ID must preserve status or follow the same transition table as set_status; all other fields are fully replaced. */ @StableId { id = "contract.rtg.migration.put_effect"; } }
    requirement statusTransitionTable { subject operation : SetMigrationStatus; doc /* Allowed changes are draft to ready or abandoned; ready to draft, applied, failed, or abandoned; failed to ready or abandoned. Applied and abandoned are terminal. Same-status update changes metadata only. */ @StableId { id = "contract.rtg.migration.status_transitions"; } }
    requirement evidenceEffect { subject operation : AddMigrationEvidence; doc /* Evidence IDs are unique within a migration; success appends one evidence record and preserves membership and status. */ @StableId { id = "contract.rtg.migration.evidence_effect"; } }
    requirement deleteEffect { subject operation : DeleteMigration; doc /* Only applied and abandoned records are deletable. Rejected deletion leaves state unchanged and never removes durable controller history. */ @StableId { id = "contract.rtg.migration.delete_effect"; } }
    requirement cutoverPlanEffect { subject operation : BuildMigrationCutoverPlan; doc /* The plan deterministically copies all make-live, make-non-live, and replacement membership without reading or mutating referenced component state. */ @StableId { id = "contract.rtg.migration.cutover_plan"; } }

    requirement idUnique { subject migration : RtgMigration; doc /* Migration IDs are unique. */ @StableId { id = "invariant.rtg.migration.id_unique"; } }
    requirement cutoverSetsDisjoint { subject migration : RtgMigration; doc /* Make-live and make-non-live sets and replacement sides do not conflict within one resource kind. */ @StableId { id = "invariant.rtg.migration.cutover_sets_disjoint"; } }
    requirement notNormalCrud { subject migration : RtgMigration; doc /* Migration records describe coordinated schema, constraint, and non-live graph lifecycle work, not ordinary live graph CRUD. */ @StableId { id = "invariant.rtg.migration.not_normal_crud"; } }
    requirement candidatesMaterialized { subject migration : RtgMigration; doc /* V1 membership references already materialized candidate records and contains no executable transforms or delta objects. */ @StableId { id = "invariant.rtg.migration.candidates_are_materialized_v1"; } }
    requirement referencesAreData { subject migration : RtgMigration; doc /* Referenced records remain owned by their source components; migration stores identities and intent only. */ @StableId { id = "invariant.rtg.migration.references_are_data"; } }
    requirement noStoreMutation { subject migration : RtgMigration; doc /* This component does not read or mutate graph, schema, or constraint stores. */ @StableId { id = "invariant.rtg.migration.no_store_mutation"; } }
    requirement statusTransitionControlled { subject migration : RtgMigration; doc /* Status changes, including replacement of an existing ID, preserve status or obey the single transition table. */ @StableId { id = "invariant.rtg.migration.status_transition_controlled"; } }
    requirement statusTrackingNotProof { subject migration : RtgMigration; doc /* Ready status records caller intent and is not proof that referenced cutover state is valid. */ @StableId { id = "invariant.rtg.migration.status_is_tracking_not_proof"; } }
    requirement completedHistoryExternal { subject migration : RtgMigration; doc /* Durable completed history belongs to controller audit. */ @StableId { id = "invariant.rtg.migration.completed_history_is_external"; } }
    requirement rollbackForwardChange { subject migration : RtgMigration; doc /* V1 rollback is represented by a later forward migration, not a special status or reverse executable operation. */ @StableId { id = "invariant.rtg.migration.rollback_is_forward_change_v1"; } }

    verification def RtgMigrationBoundaryVerification {
        subject migration : RtgMigration;
        objective { verify putMigrationEffect; verify statusTransitionTable; verify evidenceEffect; verify deleteEffect; verify cutoverPlanEffect; verify idUnique; verify cutoverSetsDisjoint; verify notNormalCrud; verify candidatesMaterialized; verify referencesAreData; verify noStoreMutation; verify statusTransitionControlled; verify statusTrackingNotProof; verify completedHistoryExternal; verify rollbackForwardChange; }
        @EvidenceBinding { verificationId = "verification.rtg.migration.boundary"; evidenceId = "components/rtg/migration/tests/test_rtg_migration_contract.py"; implementationScope = "InMemoryRtgMigration"; }
    }
}
