library package BibliotekRtgSchema {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;

    enum def RtgSchemaDefinitionKind {
        enum anchor;
        enum <'data_object'> dataObject;
        enum link;
    }
    enum def RtgSchemaDirection { enum source; enum target; enum either; }
    enum def RtgSchemaValueKind {
        enum string; enum integer; enum number; enum boolean;
        enum <'null'> nullValue;
        enum object; enum list; enum uuid;
    }

    attribute def RtgSchemaField {
        attribute required : Boolean;
        attribute valueKinds[1..*] : RtgSchemaValueKind;
        attribute properties : JsonObject;
        attribute items[0..1] : JsonObject;
        doc /* Field schema. Properties describes nested fields only for object values; items describes the item field only for list values. */
    }
    attribute def RtgSchemaPayload { doc /* One native anchor, data-object, or link schema payload selected by definition kind. */ }
    attribute def RtgAnchorSchemaPayload :> RtgSchemaPayload {
        attribute requiredDataTypes[0..*] : String;
        attribute optionalDataTypes[0..*] : String;
    }
    attribute def RtgDataObjectSchemaPayload :> RtgSchemaPayload {
        attribute properties : JsonObject;
        doc /* Strict mapping from property name to RtgSchemaField; undeclared properties are invalid for validation consumers. */
    }
    attribute def RtgLinkSchemaPayload :> RtgSchemaPayload {
        attribute allowedSourceTypes[1..*] : String;
        attribute allowedTargetTypes[1..*] : String;
    }
    item def RtgSchemaDefinition {
        attribute uuid[0..1] : Uuid;
        attribute kind : RtgSchemaDefinitionKind;
        attribute typeKey : String;
        attribute description : String;
        attribute payload : RtgSchemaPayload;
        attribute system : JsonObject;
        doc /* UUID may be absent on write only. Stored definitions have concrete UUID and Boolean system.live, defaulting missing live to true. */
    }
    attribute def RtgSchemaSnapshot { attribute definitions[0..*] : RtgSchemaDefinition; }
    attribute def RtgSchemaDefinitionList { attribute definitions[0..*] : RtgSchemaDefinition; }
    attribute def RtgSchemaAssociatedDataTypeList { attribute requiredDataTypes[0..*] : String; attribute optionalDataTypes[0..*] : String; }
    attribute def RtgSchemaLinkParticipation { attribute definitionUuid : Uuid; attribute typeKey : String; attribute direction : RtgSchemaDirection; attribute allowedSourceTypes[0..*] : String; attribute allowedTargetTypes[0..*] : String; attribute live : Boolean; }
    attribute def RtgSchemaLinkParticipationList { attribute links[0..*] : RtgSchemaLinkParticipation; }
    attribute def RtgSchemaAnchorTypeSummary { attribute definitionUuid : Uuid; attribute typeKey : String; attribute description : String; attribute live : Boolean; }
    attribute def RtgSchemaAnchorTypeSummaryList { attribute anchorTypes[0..*] : RtgSchemaAnchorTypeSummary; }
    attribute def RtgSchemaPack { attribute anchorSchemas[0..*] : RtgSchemaDefinition; attribute associatedDataObjectSchemas[0..*] : RtgSchemaDefinition; attribute linkSchemas[0..*] : RtgSchemaDefinition; }
    attribute def RtgSchemaDeleteResult { attribute deletedDefinition : RtgSchemaDefinition; }

    attribute def RtgSchemaDefinitionNotFound { attribute message : String; }
    attribute def RtgSchemaSnapshotInvalid { attribute message : String; }
    attribute def RtgSchemaUuidInvalid { attribute message : String; }
    attribute def RtgSchemaUuidConflict { attribute message : String; }
    attribute def RtgSchemaReferenceInvalid { attribute message : String; }
    attribute def RtgSchemaDefinitionInvalid { attribute message : String; }
    attribute def RtgSchemaDefinitionKindInvalid { attribute message : String; }
    attribute def RtgSchemaTypeKeyInvalid { attribute message : String; }
    attribute def RtgSchemaDirectionInvalid { attribute message : String; }
    attribute def RtgSchemaSystemValueInvalid { attribute message : String; }
    attribute def RtgSchemaLiveTypeConflict { attribute message : String; }

    action def ExportSchemaSnapshot { out snapshot : RtgSchemaSnapshot; doc /* Export every full definition with normalized live metadata without mutation or filtering. */ @FailureContract { errorIds = (); obligation = "Export has no declared domain failure."; } }
    action def PutSchemaDefinition { in definition : RtgSchemaDefinition; out stored : RtgSchemaDefinition; doc /* Generate or preserve identity, validate kind-specific payload, and atomically create or fully replace one definition. */ @FailureContract { errorIds = ("RtgSchemaUuidInvalid", "RtgSchemaUuidConflict", "RtgSchemaDefinitionInvalid", "RtgSchemaSystemValueInvalid", "RtgSchemaLiveTypeConflict"); obligation = "Rejected writes leave definitions and indexes unchanged."; } }
    action def GetSchemaDefinition { in definitionUuid : Uuid; out definition : RtgSchemaDefinition; doc /* Return one definition by UUID. */ @FailureContract { errorIds = ("RtgSchemaDefinitionNotFound"); obligation = "Read failure has no effect."; } }
    action def ListSchemaDefinitions { in kind[0..1] : RtgSchemaDefinitionKind; in live[0..1] : Boolean; out result : RtgSchemaDefinitionList; doc /* List definitions with optional kind and live filters in deterministic order. */ @FailureContract { errorIds = ("RtgSchemaDefinitionKindInvalid"); obligation = "Read failure has no effect."; } }
    action def ListDefinitionsByTypeKey { in schemaTypeKey : String; in kind[0..1] : RtgSchemaDefinitionKind; in live[0..1] : Boolean; out result : RtgSchemaDefinitionList; doc /* List every definition for one type key with optional kind/live filters, including multiple non-live candidates. */ @FailureContract { errorIds = ("RtgSchemaTypeKeyInvalid", "RtgSchemaDefinitionKindInvalid"); obligation = "Read failure has no effect."; } }
    action def ListAnchorDataTypeKeys { in anchorTypeKey : String; in live[0..1] : Boolean = true; out result : RtgSchemaAssociatedDataTypeList; doc /* Return required and optional associated data type keys declared by one anchor schema. */ @FailureContract { errorIds = ("RtgSchemaTypeKeyInvalid", "RtgSchemaDefinitionNotFound"); obligation = "Read failure has no effect."; } }
    action def ListLinkParticipation { in typeKey : String; in direction : RtgSchemaDirection = RtgSchemaDirection::either; in live[0..1] : Boolean = true; out result : RtgSchemaLinkParticipationList; doc /* Return link schemas that admit the type as source, target, or either endpoint. */ @FailureContract { errorIds = ("RtgSchemaTypeKeyInvalid", "RtgSchemaDirectionInvalid"); obligation = "Read failure has no effect."; } }
    action def ListAnchorTypeSummaries { in live[0..1] : Boolean = true; out result : RtgSchemaAnchorTypeSummaryList; doc /* Return anchor type identities and descriptions only, never graph counts. */ @FailureContract { errorIds = (); obligation = "Read is state-neutral."; } }
    action def GetSchemaPack { in anchorTypeKeys[1..*] : String; in live[0..1] : Boolean = true; out result : RtgSchemaPack; doc /* Expand requested anchor schemas with defined associated-data schemas and participating link schemas; omit missing referenced schemas but fail missing requested anchors. */ @FailureContract { errorIds = ("RtgSchemaTypeKeyInvalid", "RtgSchemaDefinitionNotFound"); obligation = "Read failure has no effect."; } }
    action def DeleteSchemaDefinition { in definitionUuid : Uuid; out result : RtgSchemaDeleteResult; doc /* Delete exactly one definition and no graph, constraint, or migration record. */ @FailureContract { errorIds = ("RtgSchemaDefinitionNotFound"); obligation = "Rejected delete has no effect."; } }

    part def <'component.rtg.schema'> RtgSchema {
        doc /* Own RTG-native schema definitions and derived navigation indexes, not object validation, graph state, migration membership, or cutover policy. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        item definitions[0..*] : RtgSchemaDefinition { doc /* Canonical component-owned schema-definition occurrences. */ }
        derived attribute navigationIndexes : JsonObject { doc /* Ephemeral navigation indexes derived from canonical schema definitions. */ }
        perform action exportSnapshot[0..*] : ExportSchemaSnapshot; perform action putDefinition[0..*] : PutSchemaDefinition; perform action getDefinition[0..*] : GetSchemaDefinition;
        perform action listDefinitions[0..*] : ListSchemaDefinitions; perform action listDefinitionsByTypeKey[0..*] : ListDefinitionsByTypeKey;
        perform action listAnchorDataTypeKeys[0..*] : ListAnchorDataTypeKeys; perform action listLinkParticipation[0..*] : ListLinkParticipation;
        perform action listAnchorTypeSummaries[0..*] : ListAnchorTypeSummaries; perform action getSchemaPack[0..*] : GetSchemaPack; perform action deleteDefinition[0..*] : DeleteSchemaDefinition;
        dependency snapshotState from exportSnapshot to definitions { doc /* read all canonical definitions. */ }
        dependency putState from putDefinition to definitions { doc /* atomically create/replace definition and rebuild affected indexes. */ }
        dependency getState from getDefinition to definitions { doc /* read one canonical definition. */ }
        dependency listState from listDefinitions to navigationIndexes { doc /* read kind/live indexes. */ }
        dependency listTypeState from listDefinitionsByTypeKey to navigationIndexes { doc /* read type-key index. */ }
        dependency anchorDataState from listAnchorDataTypeKeys to navigationIndexes { doc /* read associated-data index. */ }
        dependency linkState from listLinkParticipation to navigationIndexes { doc /* read source/target participation indexes. */ }
        dependency summaryState from listAnchorTypeSummaries to navigationIndexes { doc /* read anchor summary index. */ }
        dependency packState from getSchemaPack to navigationIndexes { doc /* assemble schema-only pack from canonical definitions and indexes. */ }
        dependency deleteState from deleteDefinition to definitions { doc /* remove one definition and affected indexes. */ }
    }
    action def CreateEmptyRtgSchema { out part schema : RtgSchema; doc /* Return an empty registry with empty derived indexes. */ @FailureContract { errorIds = (); obligation = "Construction has no declared domain failure."; } }
    action def ImportRtgSchemaSnapshot { in snapshot : RtgSchemaSnapshot; out part schema : RtgSchema; doc /* Validate every record, UUID, reference, payload, system value, and live uniqueness before rebuilding indexes and exposing the registry. */ @FailureContract { errorIds = ("RtgSchemaSnapshotInvalid", "RtgSchemaUuidInvalid", "RtgSchemaUuidConflict", "RtgSchemaReferenceInvalid", "RtgSchemaDefinitionInvalid", "RtgSchemaSystemValueInvalid", "RtgSchemaLiveTypeConflict"); obligation = "Failure returns no partially imported registry."; } }

    requirement <'contract.rtg.schema.write_effect'> definitionWriteEffect { subject operation : PutSchemaDefinition; doc /* Missing UUID generates a new UUID; supplied identity is preserved. Missing system.live becomes true. Kind selects the exact payload family and at most one live definition owns a kind/type-key pair. */ }
    requirement <'contract.rtg.schema.field_semantics'> fieldSemantics { subject schema : RtgSchema; doc /* A field has a non-empty ordered value-kind set. Nested properties are permitted only with object, items only with list, null is permitted only when explicitly listed, required fields must be present, and strict data-object payloads reject undeclared properties. */ }
    requirement <'contract.rtg.schema.payload_semantics'> payloadSemantics { subject schema : RtgSchema; doc /* Anchor payloads distinguish required from optional associated data types; data-object payloads map property names to recursive field definitions; link payloads contain non-empty allowed source and target type-key sets. Kind and payload family must agree. */ }
    requirement <'contract.rtg.schema.read_effect'> schemaReadEffect { subject schema : RtgSchema; doc /* Reads are deterministic, derive only from definitions and indexes, honor explicit filters/defaults, never inspect graph state, and never mutate. */ }
    requirement <'contract.rtg.schema.delete_effect'> schemaDeleteEffect { subject operation : DeleteSchemaDefinition; doc /* Delete removes only one definition and its derived entries; it performs no safety decision or cross-component cascade. */ }
    requirement <'contract.rtg.schema.snapshot_effect'> schemaSnapshotEffect { subject schema : RtgSchema; doc /* Snapshot round-trip preserves full records and normalized live state; import validates the whole candidate before visibility. */ }
    requirement <'invariant.rtg.schema.uuid_unique'> uuidUnique { subject schema : RtgSchema; doc /* Definition UUIDs are unique. */ }
    requirement <'invariant.rtg.schema.live_type_unique'> liveTypeUnique { subject schema : RtgSchema; doc /* At most one live definition owns a kind/type-key pair. */ }
    requirement <'invariant.rtg.schema.live_status_boolean'> liveStatusBoolean { subject schema : RtgSchema; doc /* Missing live normalizes to true and supplied live is Boolean. */ }
    requirement <'invariant.rtg.schema.no_change_set_ownership'> noChangeSetOwnership { subject schema : RtgSchema; doc /* Schema owns no change batches or migration membership. */ }
    requirement <'invariant.rtg.schema.no_object_validation'> noObjectValidation { subject schema : RtgSchema; doc /* Schema stores definitions but does not validate graph objects. */ }
    requirement <'invariant.rtg.schema.native_payloads'> nativePayloads { subject schema : RtgSchema; doc /* Payloads use anchor, data-object, field, and link concepts rather than storage-engine schemas. */ }
    requirement <'invariant.rtg.schema.no_inheritance_composition_v1'> noInheritanceCompositionV1 { subject schema : RtgSchema; doc /* V1 defines no inheritance or composition semantics. */ }
    requirement <'invariant.rtg.schema.type_key_changes_are_migration_concerns'> typeKeyChangesAreMigrationConcerns { subject schema : RtgSchema; doc /* Type-key lifecycle changes are coordinated outside the store. */ }
    requirement <'invariant.rtg.schema.navigation_indexes_match_payloads'> navigationIndexesMatchPayloads { subject schema : RtgSchema; doc /* Derived kind, type, live, associated-data, and link-participation indexes exactly match canonical payloads. */ }
    requirement <'invariant.rtg.schema.deterministic_list_ordering'> deterministicListOrdering { subject schema : RtgSchema; doc /* Public list results are deterministic for one registry state. */ }

    verification def RtgSchemaBoundaryVerification {
        subject schema : RtgSchema;
        objective { verify definitionWriteEffect; verify fieldSemantics; verify payloadSemantics; verify schemaReadEffect; verify schemaDeleteEffect; verify schemaSnapshotEffect; verify uuidUnique; verify liveTypeUnique; verify liveStatusBoolean; verify noChangeSetOwnership; verify noObjectValidation; verify nativePayloads; verify noInheritanceCompositionV1; verify typeKeyChangesAreMigrationConcerns; verify navigationIndexesMatchPayloads; verify deterministicListOrdering; }
        @EvidenceBinding { verificationId = "verification.rtg.schema.boundary"; evidenceId = "components/rtg/schema/tests/test_rtg_schema_contract.py"; implementationScope = "InMemoryRtgSchema"; }
    }
}
