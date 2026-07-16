library package BibliotekRuntimePythonRealization {
    private import SoftwareComponentModeling::*;
    private import ScalarValues::*;
    private import BibliotekRuntimeMessaging::*;
    private import BibliotekRuntimeComponentAdapter::*;
    private import BibliotekRtgGraph::*;
    private import BibliotekRtgQuery::*;
    private import BibliotekRtgChangeValidation::*;
    private import BibliotekRtgSchema::*;
    private import BibliotekRtgConstraints::*;
    private import BibliotekRtgMigration::*;
    private import BibliotekStorageJsonFile::*;
    private import BibliotekStorageSql::*;
    private import BibliotekRtgController::*;
    private import BibliotekInterfaceMcpGateway::*;

    metadata def RuntimePythonBinding {
        :>> annotatedElement : SysML::PartDefinition;
        attribute componentContractId : String;
        attribute bindingId : String;
        attribute bindingVersion : Integer;
        attribute resourcePath : String;
    }
    metadata def RuntimePythonActionBinding {
        :>> annotatedElement : SysML::ActionUsage;
        attribute actionId : String;
        attribute replayMode : RuntimeReplayMode;
        attribute idempotency : RuntimeActionIdempotency;
        attribute resolvedArgumentFromResult[0..1] : String;
        attribute externallyEffectful : Boolean;
        attribute concurrencyLane : String;
        attribute consistencyGroup[0..1] : String;
        attribute consistencyAccess : RuntimeConsistencyAccess;
        attribute deadlineSeconds[0..1] : Real;
        attribute modeledFaultTraceDisposition : RuntimeTraceDisposition;
        attribute failureNames[0..*] : String;
        attribute failureDispositionNames[0..*] : String;
        attribute failureDispositionValues[0..*] : RuntimeTraceDisposition;
        attribute recoveryAuthorized : Boolean;
        attribute requestPayloadDisposition : RuntimePayloadDisposition default = RuntimePayloadDisposition::command;
        attribute resultPayloadDisposition : RuntimePayloadDisposition default = RuntimePayloadDisposition::query_result;
        attribute faultPayloadDisposition : RuntimePayloadDisposition default = RuntimePayloadDisposition::diagnostic;
        attribute effectPayloadDisposition[0..1] : RuntimePayloadDisposition;
    }

    part def PythonMcpGatewayRuntimeBinding :> ComponentRuntimeAdapter {
        @RuntimePythonBinding { componentContractId = "component.interface.mcp_gateway"; bindingId = "binding.python.interface.mcp_gateway.v2"; bindingVersion = 1; resourcePath = "components/interface/mcp_gateway/resources/runtime_binding.json"; }
    }

    part def PythonRtgSchemaRuntimeBinding :> ComponentRuntimeAdapter {
        @RuntimePythonBinding { componentContractId = "component.rtg.schema"; bindingId = "binding.python.rtg.schema.v1"; bindingVersion = 1; resourcePath = "components/rtg/schema/resources/runtime_binding.json"; }
        perform action export_snapshot[0..*] : ExportSchemaSnapshot {
            @RuntimePythonActionBinding { actionId = "component.rtg.schema.export_snapshot"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = (); recoveryAuthorized = false; resultPayloadDisposition = RuntimePayloadDisposition::state_transfer; }
        }
        perform action replace_snapshot[0..*] : ReplaceSchemaSnapshot {
            @RuntimePythonActionBinding { actionId = "component.rtg.schema.replace_snapshot"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgSchemaSnapshotInvalid", "RtgSchemaUuidInvalid", "RtgSchemaUuidConflict", "RtgSchemaDefinitionKindInvalid", "RtgSchemaTypeKeyInvalid", "RtgSchemaDefinitionInvalid", "RtgSchemaPayloadInvalid", "RtgSchemaSystemValueInvalid", "RtgSchemaLiveTypeConflict"); recoveryAuthorized = false; requestPayloadDisposition = RuntimePayloadDisposition::state_transfer; effectPayloadDisposition = RuntimePayloadDisposition::state_transfer; }
        }
        perform action apply_batch[0..*] : ApplyRtgSchemaBatch { @RuntimePythonActionBinding { actionId = "component.rtg.schema.apply_batch"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgSchemaUuidInvalid", "RtgSchemaUuidConflict", "RtgSchemaDefinitionKindInvalid", "RtgSchemaTypeKeyInvalid", "RtgSchemaDefinitionInvalid", "RtgSchemaPayloadInvalid", "RtgSchemaSystemValueInvalid", "RtgSchemaLiveTypeConflict", "RtgSchemaDefinitionNotFound"); recoveryAuthorized = false; effectPayloadDisposition = RuntimePayloadDisposition::canonical_delta; } }
        perform action count_summary[0..*] : CountRtgSchemaSummary { @RuntimePythonActionBinding { actionId = "component.rtg.schema.count_summary"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = (); recoveryAuthorized = false; } }
        perform action put_definition[0..*] : PutSchemaDefinition {
            @RuntimePythonActionBinding { actionId = "component.rtg.schema.put_definition"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::non_idempotent; resolvedArgumentFromResult = "definition"; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgSchemaUuidInvalid", "RtgSchemaDefinitionKindInvalid", "RtgSchemaTypeKeyInvalid", "RtgSchemaDefinitionInvalid", "RtgSchemaPayloadInvalid", "RtgSchemaSystemValueInvalid", "RtgSchemaLiveTypeConflict"); recoveryAuthorized = false; }
        }
        perform action get_definition[0..*] : GetSchemaDefinition {
            @RuntimePythonActionBinding { actionId = "component.rtg.schema.get_definition"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgSchemaDefinitionNotFound"); recoveryAuthorized = false; }
        }
        perform action list_definitions[0..*] : ListSchemaDefinitions {
            @RuntimePythonActionBinding { actionId = "component.rtg.schema.list_definitions"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgSchemaDefinitionKindInvalid", "RtgSchemaPayloadInvalid"); recoveryAuthorized = false; }
        }
        perform action list_definitions_by_type_key[0..*] : ListDefinitionsByTypeKey {
            @RuntimePythonActionBinding { actionId = "component.rtg.schema.list_definitions_by_type_key"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgSchemaTypeKeyInvalid", "RtgSchemaDefinitionKindInvalid", "RtgSchemaPayloadInvalid"); recoveryAuthorized = false; }
        }
        perform action list_anchor_data_type_keys[0..*] : ListAnchorDataTypeKeys {
            @RuntimePythonActionBinding { actionId = "component.rtg.schema.list_anchor_data_type_keys"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgSchemaTypeKeyInvalid", "RtgSchemaDefinitionNotFound"); recoveryAuthorized = false; }
        }
        perform action list_link_participation[0..*] : ListLinkParticipation {
            @RuntimePythonActionBinding { actionId = "component.rtg.schema.list_link_participation"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgSchemaTypeKeyInvalid", "RtgSchemaDirectionInvalid"); recoveryAuthorized = false; }
        }
        perform action list_anchor_type_summaries[0..*] : ListAnchorTypeSummaries {
            @RuntimePythonActionBinding { actionId = "component.rtg.schema.list_anchor_type_summaries"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = (); recoveryAuthorized = false; }
        }
        perform action get_schema_pack[0..*] : GetSchemaPack {
            @RuntimePythonActionBinding { actionId = "component.rtg.schema.get_schema_pack"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgSchemaTypeKeyInvalid", "RtgSchemaDefinitionNotFound"); recoveryAuthorized = false; }
        }
        perform action delete_definition[0..*] : DeleteSchemaDefinition {
            @RuntimePythonActionBinding { actionId = "component.rtg.schema.delete_definition"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgSchemaDefinitionNotFound"); recoveryAuthorized = false; }
        }
    }

    part def PythonRtgConstraintsRuntimeBinding :> ComponentRuntimeAdapter {
        @RuntimePythonBinding { componentContractId = "component.rtg.constraints"; bindingId = "binding.python.rtg.constraints.v1"; bindingVersion = 1; resourcePath = "components/rtg/constraints/resources/runtime_binding.json"; }
        perform action export_snapshot[0..*] : ExportConstraintSnapshot {
            @RuntimePythonActionBinding { actionId = "component.rtg.constraints.export_snapshot"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = (); recoveryAuthorized = false; resultPayloadDisposition = RuntimePayloadDisposition::state_transfer; }
        }
        perform action replace_snapshot[0..*] : ReplaceConstraintSnapshot {
            @RuntimePythonActionBinding { actionId = "component.rtg.constraints.replace_snapshot"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgConstraintSnapshotInvalid", "RtgConstraintUuidInvalid", "RtgConstraintUuidConflict", "RtgConstraintKindInvalid", "RtgConstraintDefinitionInvalid", "RtgConstraintPayloadInvalid", "RtgConstraintSystemValueInvalid"); recoveryAuthorized = false; requestPayloadDisposition = RuntimePayloadDisposition::state_transfer; effectPayloadDisposition = RuntimePayloadDisposition::state_transfer; }
        }
        perform action apply_batch[0..*] : ApplyRtgConstraintBatch { @RuntimePythonActionBinding { actionId = "component.rtg.constraints.apply_batch"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgConstraintUuidInvalid", "RtgConstraintUuidConflict", "RtgConstraintKindInvalid", "RtgConstraintDefinitionInvalid", "RtgConstraintPayloadInvalid", "RtgConstraintSystemValueInvalid", "RtgConstraintNotFound"); recoveryAuthorized = false; effectPayloadDisposition = RuntimePayloadDisposition::canonical_delta; } }
        perform action count_summary[0..*] : CountRtgConstraintSummary { @RuntimePythonActionBinding { actionId = "component.rtg.constraints.count_summary"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = (); recoveryAuthorized = false; } }
        perform action put_constraint[0..*] : PutConstraint {
            @RuntimePythonActionBinding { actionId = "component.rtg.constraints.put_constraint"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::non_idempotent; resolvedArgumentFromResult = "constraint"; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgConstraintUuidInvalid", "RtgConstraintUuidConflict", "RtgConstraintKindInvalid", "RtgConstraintDefinitionInvalid", "RtgConstraintPayloadInvalid", "RtgConstraintSystemValueInvalid"); recoveryAuthorized = false; }
        }
        perform action get_constraint[0..*] : GetConstraint {
            @RuntimePythonActionBinding { actionId = "component.rtg.constraints.get_constraint"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgConstraintNotFound"); recoveryAuthorized = false; }
        }
        perform action list_constraints[0..*] : ListConstraints {
            @RuntimePythonActionBinding { actionId = "component.rtg.constraints.list_constraints"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgConstraintKindInvalid", "RtgConstraintPayloadInvalid"); recoveryAuthorized = false; }
        }
        perform action list_constraints_by_target[0..*] : ListConstraintsByTarget {
            @RuntimePythonActionBinding { actionId = "component.rtg.constraints.list_constraints_by_target"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgConstraintTargetInvalid", "RtgConstraintKindInvalid"); recoveryAuthorized = false; }
        }
        perform action delete_constraint[0..*] : DeleteConstraint {
            @RuntimePythonActionBinding { actionId = "component.rtg.constraints.delete_constraint"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgConstraintNotFound"); recoveryAuthorized = false; }
        }
    }

    part def PythonRtgMigrationRuntimeBinding :> ComponentRuntimeAdapter {
        @RuntimePythonBinding { componentContractId = "component.rtg.migration"; bindingId = "binding.python.rtg.migration.v1"; bindingVersion = 1; resourcePath = "components/rtg/migration/resources/runtime_binding.json"; }
        perform action export_snapshot[0..*] : ExportMigrationSnapshot {
            @RuntimePythonActionBinding { actionId = "component.rtg.migration.export_snapshot"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = (); recoveryAuthorized = false; resultPayloadDisposition = RuntimePayloadDisposition::state_transfer; }
        }
        perform action replace_snapshot[0..*] : ReplaceMigrationSnapshot {
            @RuntimePythonActionBinding { actionId = "component.rtg.migration.replace_snapshot"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgMigrationSnapshotInvalid", "RtgMigrationIdInvalid", "RtgMigrationIdConflict", "RtgMigrationRecordInvalid", "RtgMigrationStatusInvalid", "RtgMigrationEvidenceInvalid"); recoveryAuthorized = false; requestPayloadDisposition = RuntimePayloadDisposition::state_transfer; effectPayloadDisposition = RuntimePayloadDisposition::state_transfer; }
        }
        perform action apply_batch[0..*] : ApplyRtgMigrationBatch { @RuntimePythonActionBinding { actionId = "component.rtg.migration.apply_batch"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgMigrationIdInvalid", "RtgMigrationIdConflict", "RtgMigrationNotFound", "RtgMigrationRecordInvalid", "RtgMigrationStatusInvalid", "RtgMigrationStatusTransitionInvalid", "RtgMigrationEvidenceInvalid", "RtgMigrationDeleteNotAllowed"); recoveryAuthorized = false; effectPayloadDisposition = RuntimePayloadDisposition::canonical_delta; } }
        perform action count_summary[0..*] : CountRtgMigrationSummary { @RuntimePythonActionBinding { actionId = "component.rtg.migration.count_summary"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = (); recoveryAuthorized = false; } }
        perform action find_candidate_owners[0..*] : FindMigrationCandidateOwners { @RuntimePythonActionBinding { actionId = "component.rtg.migration.find_candidate_owners"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgMigrationRecordInvalid"); recoveryAuthorized = false; } }
        perform action put_migration[0..*] : PutMigration {
            @RuntimePythonActionBinding { actionId = "component.rtg.migration.put_migration"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::non_idempotent; resolvedArgumentFromResult = "migration"; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgMigrationIdInvalid", "RtgMigrationRecordInvalid", "RtgMigrationStatusInvalid", "RtgMigrationStatusTransitionInvalid", "RtgMigrationEvidenceInvalid"); recoveryAuthorized = false; }
        }
        perform action get_migration[0..*] : GetMigration {
            @RuntimePythonActionBinding { actionId = "component.rtg.migration.get_migration"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgMigrationNotFound"); recoveryAuthorized = false; }
        }
        perform action list_migrations[0..*] : ListMigrations {
            @RuntimePythonActionBinding { actionId = "component.rtg.migration.list_migrations"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgMigrationStatusInvalid", "RtgMigrationRecordInvalid"); recoveryAuthorized = false; }
        }
        perform action set_status[0..*] : SetMigrationStatus {
            @RuntimePythonActionBinding { actionId = "component.rtg.migration.set_status"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgMigrationIdInvalid", "RtgMigrationNotFound", "RtgMigrationRecordInvalid", "RtgMigrationStatusInvalid", "RtgMigrationStatusTransitionInvalid"); recoveryAuthorized = false; }
        }
        perform action add_evidence[0..*] : AddMigrationEvidence {
            @RuntimePythonActionBinding { actionId = "component.rtg.migration.add_evidence"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgMigrationNotFound", "RtgMigrationEvidenceInvalid"); recoveryAuthorized = false; }
        }
        perform action delete_migration[0..*] : DeleteMigration {
            @RuntimePythonActionBinding { actionId = "component.rtg.migration.delete_migration"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgMigrationIdInvalid", "RtgMigrationNotFound", "RtgMigrationDeleteNotAllowed"); recoveryAuthorized = false; }
        }
    }

    part def PythonJsonFileStorageRuntimeBinding :> ComponentRuntimeAdapter {
        @RuntimePythonBinding { componentContractId = "component.storage.json_file"; bindingId = "binding.python.storage.json_file.v1"; bindingVersion = 1; resourcePath = "components/storage/json_file/resources/runtime_binding.json"; }
        perform action write[0..*] : WriteJsonDocument {
            @RuntimePythonActionBinding { actionId = "component.storage.json_file.write"; replayMode = RuntimeReplayMode::external_exchange; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = true; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("StoragePathInvalid", "JsonValueNotSerializable", "StoragePermissionDenied", "StorageWriteFailed"); recoveryAuthorized = false; requestPayloadDisposition = RuntimePayloadDisposition::external_document; }
        }
        perform action read[0..*] : ReadJsonDocument {
            @RuntimePythonActionBinding { actionId = "component.storage.json_file.read"; replayMode = RuntimeReplayMode::external_exchange; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("StoragePathInvalid", "JsonDocumentNotFound", "JsonDocumentInvalid", "StoragePermissionDenied", "StorageReadFailed"); recoveryAuthorized = false; resultPayloadDisposition = RuntimePayloadDisposition::external_document; }
        }
        perform action delete[0..*] : DeleteJsonDocument {
            @RuntimePythonActionBinding { actionId = "component.storage.json_file.delete"; replayMode = RuntimeReplayMode::external_exchange; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = true; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("StoragePathInvalid", "JsonDocumentNotFound", "StoragePermissionDenied", "StorageDeleteFailed"); recoveryAuthorized = false; }
        }
        perform action list[0..*] : ListJsonDocuments {
            @RuntimePythonActionBinding { actionId = "component.storage.json_file.list"; replayMode = RuntimeReplayMode::external_exchange; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("StoragePathInvalid", "StorageDirectoryNotFound", "StoragePermissionDenied", "StorageReadFailed"); recoveryAuthorized = false; }
        }
    }

    part def PythonSqlStorageRuntimeBinding :> ComponentRuntimeAdapter {
        @RuntimePythonBinding { componentContractId = "component.storage.sql"; bindingId = "binding.python.storage.sql.v1"; bindingVersion = 1; resourcePath = "components/storage/sql/resources/runtime_binding.json"; }
        perform action execute[0..*] : ExecuteSql {
            @RuntimePythonActionBinding { actionId = "component.storage.sql.execute"; replayMode = RuntimeReplayMode::external_exchange; idempotency = RuntimeActionIdempotency::unspecified; externallyEffectful = true; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("SqlStatementInvalid", "SqlParameterInvalid", "SqlExecutionFailed", "SqlStoragePermissionDenied"); recoveryAuthorized = false; }
        }
        perform action query[0..*] : QuerySql {
            @RuntimePythonActionBinding { actionId = "component.storage.sql.query"; replayMode = RuntimeReplayMode::external_exchange; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("SqlStatementInvalid", "SqlParameterInvalid", "SqlExecutionFailed", "SqlStoragePermissionDenied"); recoveryAuthorized = false; }
        }
        perform action transaction[0..*] : ExecuteSqlTransaction {
            @RuntimePythonActionBinding { actionId = "component.storage.sql.transaction"; replayMode = RuntimeReplayMode::external_exchange; idempotency = RuntimeActionIdempotency::unspecified; externallyEffectful = true; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("SqlStatementInvalid", "SqlParameterInvalid", "SqlTransactionFailed", "SqlStoragePermissionDenied"); recoveryAuthorized = false; }
        }
    }

    part def PythonRtgControllerRuntimeBinding :> ComponentRuntimeAdapter {
        @RuntimePythonBinding { componentContractId = "component.rtg.controller"; bindingId = "binding.python.rtg.controller.v2"; bindingVersion = 1; resourcePath = "components/rtg/controller/resources/runtime_binding.json"; }
        perform action apply_live_graph_changes[0..*] : ApplyLiveGraphChanges {
            @RuntimePythonActionBinding { actionId = "component.rtg.controller.apply_live_graph_changes"; replayMode = RuntimeReplayMode::coordinator_trace; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = false; concurrencyLane = "mutation"; consistencyAccess = RuntimeConsistencyAccess::exclusive; consistencyGroup = "rtg.state"; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; deadlineSeconds = 30; failureNames = ("RtgControllerValidationFailed", "RtgControllerApplyFailed", "RtgControllerRecoveryIndeterminate"); failureDispositionNames = ("RtgControllerRecoveryIndeterminate"); failureDispositionValues = (RuntimeTraceDisposition::indeterminate); recoveryAuthorized = false; }
        }
        perform action validate_live_graph_changes[0..*] : ValidateLiveGraphChanges {
            @RuntimePythonActionBinding { actionId = "component.rtg.controller.validate_live_graph_changes"; replayMode = RuntimeReplayMode::coordinator_trace; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "read"; consistencyAccess = RuntimeConsistencyAccess::shared; consistencyGroup = "rtg.state"; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; deadlineSeconds = 30; failureNames = ("RtgControllerPreconditionFailed", "RtgValidationInputInvalid"); recoveryAuthorized = false; }
        }
        perform action stage_knowledge_changes[0..*] : StageKnowledgeChanges {
            @RuntimePythonActionBinding { actionId = "component.rtg.controller.stage_knowledge_changes"; replayMode = RuntimeReplayMode::coordinator_trace; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = false; concurrencyLane = "mutation"; consistencyAccess = RuntimeConsistencyAccess::exclusive; consistencyGroup = "rtg.state"; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; deadlineSeconds = 30; failureNames = ("RtgControllerValidationFailed", "RtgControllerPreconditionFailed", "RtgControllerApplyFailed", "RtgControllerRecoveryIndeterminate"); failureDispositionNames = ("RtgControllerRecoveryIndeterminate"); failureDispositionValues = (RuntimeTraceDisposition::indeterminate); recoveryAuthorized = false; }
        }
        perform action apply_migration_cutover[0..*] : ApplyMigrationCutover {
            @RuntimePythonActionBinding { actionId = "component.rtg.controller.apply_migration_cutover"; replayMode = RuntimeReplayMode::coordinator_trace; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = false; concurrencyLane = "mutation"; consistencyAccess = RuntimeConsistencyAccess::exclusive; consistencyGroup = "rtg.state"; modeledFaultTraceDisposition = RuntimeTraceDisposition::committed; deadlineSeconds = 120; failureNames = ("RtgControllerPreconditionFailed", "RtgControllerValidationFailed", "RtgControllerApplyFailed", "RtgControllerRecoveryIndeterminate"); recoveryAuthorized = false; failureDispositionNames = ("RtgControllerPreconditionFailed", "RtgControllerRecoveryIndeterminate"); failureDispositionValues = (RuntimeTraceDisposition::aborted, RuntimeTraceDisposition::indeterminate); }
        }
        perform action execute_query[0..*] : ExecuteControllerQuery {
            @RuntimePythonActionBinding { actionId = "component.rtg.controller.execute_query"; replayMode = RuntimeReplayMode::coordinator_trace; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "read"; consistencyAccess = RuntimeConsistencyAccess::shared; consistencyGroup = "rtg.state"; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; deadlineSeconds = 30; failureNames = ("RtgQuerySpecInvalid", "RtgQueryUnsupported"); recoveryAuthorized = false; }
        }
        perform action get_object[0..*] : ControllerGetObject {
            @RuntimePythonActionBinding { actionId = "component.rtg.controller.get_object"; replayMode = RuntimeReplayMode::coordinator_trace; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "read"; consistencyAccess = RuntimeConsistencyAccess::shared; consistencyGroup = "rtg.state"; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; deadlineSeconds = 30; failureNames = ("RtgControllerObjectNotFound"); recoveryAuthorized = false; }
        }
        perform action list_migrations[0..*] : ControllerListMigrations {
            @RuntimePythonActionBinding { actionId = "component.rtg.controller.list_migrations"; replayMode = RuntimeReplayMode::coordinator_trace; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "read"; consistencyAccess = RuntimeConsistencyAccess::shared; consistencyGroup = "rtg.state"; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; deadlineSeconds = 30; failureNames = ("RtgMigrationStatusInvalid"); recoveryAuthorized = false; }
        }
        perform action get_migration[0..*] : ControllerGetMigration {
            @RuntimePythonActionBinding { actionId = "component.rtg.controller.get_migration"; replayMode = RuntimeReplayMode::coordinator_trace; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "read"; consistencyAccess = RuntimeConsistencyAccess::shared; consistencyGroup = "rtg.state"; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; deadlineSeconds = 30; failureNames = ("RtgMigrationNotFound"); recoveryAuthorized = false; }
        }
        perform action validate_graph[0..*] : ValidateGraph {
            @RuntimePythonActionBinding { actionId = "component.rtg.controller.validate_graph"; replayMode = RuntimeReplayMode::coordinator_trace; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "read"; consistencyAccess = RuntimeConsistencyAccess::shared; consistencyGroup = "rtg.state"; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; deadlineSeconds = 30; failureNames = ("RtgControllerValidationFailed"); recoveryAuthorized = false; }
        }
        perform action discover_anchor_types[0..*] : DiscoverAnchorTypes {
            @RuntimePythonActionBinding { actionId = "component.rtg.controller.discover_anchor_types"; replayMode = RuntimeReplayMode::coordinator_trace; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "read"; consistencyAccess = RuntimeConsistencyAccess::shared; consistencyGroup = "rtg.state"; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; deadlineSeconds = 30; failureNames = ("RtgControllerDiscoveryFailed"); recoveryAuthorized = false; }
        }
        perform action get_schema_pack[0..*] : GetControllerSchemaPack {
            @RuntimePythonActionBinding { actionId = "component.rtg.controller.get_schema_pack"; replayMode = RuntimeReplayMode::coordinator_trace; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "read"; consistencyAccess = RuntimeConsistencyAccess::shared; consistencyGroup = "rtg.state"; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; deadlineSeconds = 30; failureNames = ("RtgControllerDiscoveryFailed"); recoveryAuthorized = false; }
        }
        perform action list_schema_definitions_by_type_key[0..*] : ListSchemaDefinitionsByTypeKey {
            @RuntimePythonActionBinding { actionId = "component.rtg.controller.list_schema_definitions_by_type_key"; replayMode = RuntimeReplayMode::coordinator_trace; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "read"; consistencyAccess = RuntimeConsistencyAccess::shared; consistencyGroup = "rtg.state"; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; deadlineSeconds = 30; failureNames = ("RtgControllerPreconditionFailed"); recoveryAuthorized = false; }
        }
        perform action get_system_state[0..*] : GetSystemState {
            @RuntimePythonActionBinding { actionId = "component.rtg.controller.get_system_state"; replayMode = RuntimeReplayMode::coordinator_trace; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "read"; consistencyAccess = RuntimeConsistencyAccess::shared; consistencyGroup = "rtg.state"; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; deadlineSeconds = 30; failureNames = ("RtgControllerDiscoveryFailed"); recoveryAuthorized = false; }
        }
        perform action export_system_snapshot[0..*] : ExportSystemSnapshot {
            @RuntimePythonActionBinding { actionId = "component.rtg.controller.export_system_snapshot"; replayMode = RuntimeReplayMode::coordinator_trace; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "read"; consistencyAccess = RuntimeConsistencyAccess::shared; consistencyGroup = "rtg.state"; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; deadlineSeconds = 30; failureNames = ("RtgControllerSnapshotFailed"); recoveryAuthorized = false; resultPayloadDisposition = RuntimePayloadDisposition::state_transfer; }
        }
        perform action persist_system_snapshot[0..*] : PersistSystemSnapshot {
            @RuntimePythonActionBinding { actionId = "component.rtg.controller.persist_system_snapshot"; replayMode = RuntimeReplayMode::coordinator_trace; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = false; concurrencyLane = "mutation"; consistencyAccess = RuntimeConsistencyAccess::exclusive; consistencyGroup = "rtg.state"; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; deadlineSeconds = 30; failureNames = ("RtgControllerSnapshotFailed"); recoveryAuthorized = false; resultPayloadDisposition = RuntimePayloadDisposition::query_result; }
        }
        perform action list_persisted_snapshots[0..*] : ListPersistedSnapshots {
            @RuntimePythonActionBinding { actionId = "component.rtg.controller.list_persisted_snapshots"; replayMode = RuntimeReplayMode::coordinator_trace; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "read"; consistencyAccess = RuntimeConsistencyAccess::shared; consistencyGroup = "rtg.state"; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; deadlineSeconds = 30; failureNames = ("RtgControllerSnapshotFailed"); recoveryAuthorized = false; }
        }
        perform action load_persisted_snapshot[0..*] : LoadPersistedSnapshot {
            @RuntimePythonActionBinding { actionId = "component.rtg.controller.load_persisted_snapshot"; replayMode = RuntimeReplayMode::coordinator_trace; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "read"; consistencyAccess = RuntimeConsistencyAccess::shared; consistencyGroup = "rtg.state"; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; deadlineSeconds = 30; failureNames = ("RtgControllerSnapshotFailed"); recoveryAuthorized = false; resultPayloadDisposition = RuntimePayloadDisposition::state_transfer; }
        }
        perform action abandon_migration[0..*] : AbandonMigration {
            @RuntimePythonActionBinding { actionId = "component.rtg.controller.abandon_migration"; replayMode = RuntimeReplayMode::coordinator_trace; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = false; concurrencyLane = "mutation"; consistencyAccess = RuntimeConsistencyAccess::exclusive; consistencyGroup = "rtg.state"; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; deadlineSeconds = 30; failureNames = ("RtgControllerPreconditionFailed", "RtgControllerApplyFailed", "RtgControllerRecoveryIndeterminate"); failureDispositionNames = ("RtgControllerRecoveryIndeterminate"); failureDispositionValues = (RuntimeTraceDisposition::indeterminate); recoveryAuthorized = false; }
        }
        perform action restore_from_snapshot[0..*] : RestoreFromSnapshot {
            @RuntimePythonActionBinding { actionId = "component.rtg.controller.restore_from_snapshot"; replayMode = RuntimeReplayMode::coordinator_trace; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = false; concurrencyLane = "mutation"; consistencyAccess = RuntimeConsistencyAccess::exclusive; consistencyGroup = "rtg.state"; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; deadlineSeconds = 120; failureNames = ("RtgControllerSnapshotFailed", "RtgControllerRecoveryIndeterminate"); recoveryAuthorized = false; failureDispositionNames = ("RtgControllerRecoveryIndeterminate"); failureDispositionValues = (RuntimeTraceDisposition::indeterminate); requestPayloadDisposition = RuntimePayloadDisposition::state_transfer; }
        }
    }

    part def PythonRtgGraphRuntimeBinding :> ComponentRuntimeAdapter {
        @RuntimePythonBinding { componentContractId = "component.rtg.graph"; bindingId = "binding.python.rtg.graph.v1"; bindingVersion = 1; resourcePath = "components/rtg/graph/resources/runtime_binding.json"; }
        perform action export_snapshot[0..*] : ExportGraphSnapshot {
            @RuntimePythonActionBinding { actionId = "component.rtg.graph.export_snapshot"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = (); recoveryAuthorized = false; resultPayloadDisposition = RuntimePayloadDisposition::state_transfer; }
        }
        perform action replace_snapshot[0..*] : ReplaceGraphSnapshot {
            @RuntimePythonActionBinding { actionId = "component.rtg.graph.replace_snapshot"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgGraphSnapshotInvalid", "RtgGraphUuidInvalid", "RtgGraphUuidConflict", "RtgGraphReferenceInvalid", "RtgGraphTypeInvalid", "RtgGraphTypeKindConflict", "RtgGraphJsonValueInvalid", "RtgGraphSystemValueInvalid"); recoveryAuthorized = false; requestPayloadDisposition = RuntimePayloadDisposition::state_transfer; effectPayloadDisposition = RuntimePayloadDisposition::state_transfer; }
        }
        perform action apply_batch[0..*] : ApplyRtgGraphBatch { @RuntimePythonActionBinding { actionId = "component.rtg.graph.apply_batch"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgGraphUuidInvalid", "RtgGraphUuidConflict", "RtgGraphReferenceInvalid", "RtgGraphTypeInvalid", "RtgGraphTypeKindConflict", "RtgGraphJsonValueInvalid", "RtgGraphSystemValueInvalid", "RtgGraphAnchorNotFound", "RtgGraphDataObjectNotFound", "RtgGraphLinkNotFound", "RtgGraphEndpointNotFound", "RtgGraphAnchorDataIndexEntryNotFound", "RtgGraphObjectNotFound"); recoveryAuthorized = false; effectPayloadDisposition = RuntimePayloadDisposition::canonical_delta; } }
        perform action put_anchor[0..*] : PutAnchor {
            @RuntimePythonActionBinding { actionId = "component.rtg.graph.put_anchor"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::non_idempotent; resolvedArgumentFromResult = "anchor"; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgGraphUuidInvalid", "RtgGraphUuidConflict", "RtgGraphTypeInvalid", "RtgGraphTypeKindConflict", "RtgGraphSystemValueInvalid"); recoveryAuthorized = false; }
        }
        perform action put_data_object[0..*] : PutDataObject {
            @RuntimePythonActionBinding { actionId = "component.rtg.graph.put_data_object"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::non_idempotent; resolvedArgumentFromResult = "data_object"; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgGraphUuidInvalid", "RtgGraphUuidConflict", "RtgGraphAnchorNotFound", "RtgGraphTypeInvalid", "RtgGraphTypeKindConflict", "RtgGraphJsonValueInvalid", "RtgGraphSystemValueInvalid"); recoveryAuthorized = false; }
        }
        perform action put_link[0..*] : PutLink {
            @RuntimePythonActionBinding { actionId = "component.rtg.graph.put_link"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::non_idempotent; resolvedArgumentFromResult = "link"; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgGraphUuidInvalid", "RtgGraphUuidConflict", "RtgGraphEndpointNotFound", "RtgGraphTypeInvalid", "RtgGraphTypeKindConflict", "RtgGraphSystemValueInvalid"); recoveryAuthorized = false; }
        }
        perform action associate_data[0..*] : AssociateData {
            @RuntimePythonActionBinding { actionId = "component.rtg.graph.associate_data"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgGraphUuidInvalid", "RtgGraphAnchorNotFound", "RtgGraphDataObjectNotFound"); recoveryAuthorized = false; }
        }
        perform action dissociate_data[0..*] : DissociateData {
            @RuntimePythonActionBinding { actionId = "component.rtg.graph.dissociate_data"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgGraphUuidInvalid", "RtgGraphAnchorNotFound", "RtgGraphDataObjectNotFound", "RtgGraphAnchorDataIndexEntryNotFound"); recoveryAuthorized = false; }
        }
        perform action delete_anchor[0..*] : DeleteAnchor {
            @RuntimePythonActionBinding { actionId = "component.rtg.graph.delete_anchor"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgGraphUuidInvalid", "RtgGraphAnchorNotFound"); recoveryAuthorized = false; }
        }
        perform action delete_data_object[0..*] : DeleteDataObject {
            @RuntimePythonActionBinding { actionId = "component.rtg.graph.delete_data_object"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgGraphUuidInvalid", "RtgGraphDataObjectNotFound"); recoveryAuthorized = false; }
        }
        perform action delete_link[0..*] : DeleteLink {
            @RuntimePythonActionBinding { actionId = "component.rtg.graph.delete_link"; replayMode = RuntimeReplayMode::canonical_effect; idempotency = RuntimeActionIdempotency::non_idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgGraphUuidInvalid", "RtgGraphLinkNotFound"); recoveryAuthorized = false; }
        }
        perform action preview_delete_anchor[0..*] : PreviewDeleteAnchor {
            @RuntimePythonActionBinding { actionId = "component.rtg.graph.preview_delete_anchor"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgGraphUuidInvalid", "RtgGraphAnchorNotFound"); recoveryAuthorized = false; }
        }
        perform action preview_delete_data_object[0..*] : PreviewDeleteDataObject {
            @RuntimePythonActionBinding { actionId = "component.rtg.graph.preview_delete_data_object"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgGraphUuidInvalid", "RtgGraphDataObjectNotFound"); recoveryAuthorized = false; }
        }
        perform action preview_dissociate_data[0..*] : PreviewDissociateData {
            @RuntimePythonActionBinding { actionId = "component.rtg.graph.preview_dissociate_data"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgGraphUuidInvalid", "RtgGraphAnchorNotFound", "RtgGraphDataObjectNotFound", "RtgGraphAnchorDataIndexEntryNotFound"); recoveryAuthorized = false; }
        }
        perform action get_object[0..*] : GetGraphObject {
            @RuntimePythonActionBinding { actionId = "component.rtg.graph.get_object"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgGraphUuidInvalid", "RtgGraphObjectNotFound"); recoveryAuthorized = false; }
        }
        perform action list_by_type[0..*] : ListGraphObjectsByType {
            @RuntimePythonActionBinding { actionId = "component.rtg.graph.list_by_type"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgGraphTypeInvalid", "RtgGraphReferenceInvalid"); recoveryAuthorized = false; }
        }
        perform action list_anchor_data[0..*] : ListAnchorData {
            @RuntimePythonActionBinding { actionId = "component.rtg.graph.list_anchor_data"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgGraphUuidInvalid", "RtgGraphAnchorNotFound", "RtgGraphReferenceInvalid"); recoveryAuthorized = false; }
        }
        perform action list_data_anchors[0..*] : ListDataAnchors {
            @RuntimePythonActionBinding { actionId = "component.rtg.graph.list_data_anchors"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgGraphUuidInvalid", "RtgGraphDataObjectNotFound", "RtgGraphReferenceInvalid"); recoveryAuthorized = false; }
        }
        perform action list_incident_links[0..*] : ListIncidentLinks {
            @RuntimePythonActionBinding { actionId = "component.rtg.graph.list_incident_links"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgGraphUuidInvalid", "RtgGraphObjectNotFound", "RtgGraphReferenceInvalid"); recoveryAuthorized = false; }
        }
        perform action count_by_type[0..*] : CountGraphObjectsByType {
            @RuntimePythonActionBinding { actionId = "component.rtg.graph.count_by_type"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgGraphTypeInvalid"); recoveryAuthorized = false; }
        }
    }

    part def PythonRtgQueryRuntimeBinding :> ComponentRuntimeAdapter {
        @RuntimePythonBinding { componentContractId = "component.rtg.query"; bindingId = "binding.python.rtg.query.v1"; bindingVersion = 1; resourcePath = "components/rtg/query/resources/runtime_binding.json"; }
        perform action execute[0..*] : ExecuteRtgQuery {
            @RuntimePythonActionBinding { actionId = "component.rtg.query.execute"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgQuerySpecInvalid", "RtgQueryUnsupported"); recoveryAuthorized = false; }
        }
        perform action execute_projected[0..*] : ExecuteProjectedRtgQuery {
            @RuntimePythonActionBinding { actionId = "component.rtg.query.execute_projected"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgQuerySpecInvalid", "RtgQueryUnsupported"); recoveryAuthorized = false; }
        }
    }

    part def PythonRtgChangeValidationRuntimeBinding :> ComponentRuntimeAdapter {
        @RuntimePythonBinding { componentContractId = "component.rtg.change_validation"; bindingId = "binding.python.rtg.change_validation.v1"; bindingVersion = 1; resourcePath = "components/rtg/change_validation/resources/runtime_binding.json"; }
        perform action validate_batch[0..*] : ValidateRtgChangeBatch {
            @RuntimePythonActionBinding { actionId = "component.rtg.change_validation.validate_batch"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgValidationInputInvalid"); recoveryAuthorized = false; }
        }
        perform action validate_graph_state[0..*] : ValidateRtgGraphState {
            @RuntimePythonActionBinding { actionId = "component.rtg.change_validation.validate_graph_state"; replayMode = RuntimeReplayMode::no_state_effect; idempotency = RuntimeActionIdempotency::idempotent; externallyEffectful = false; concurrencyLane = "serialized"; consistencyAccess = RuntimeConsistencyAccess::independent; modeledFaultTraceDisposition = RuntimeTraceDisposition::aborted; failureNames = ("RtgValidationInputInvalid"); recoveryAuthorized = false; }
        }
    }

    doc /* Python participation metadata is a model-owned projection source. Logical component actions remain runtime-neutral; these usages allocate them to the standard adapter without component-role classification. */
}
