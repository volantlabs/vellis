library package BibliotekRtgSchema {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;

    enum def RtgSchemaDefinitionKind {
        enum anchor;
        enum data_object;
        enum link;
    }
    enum def RtgSchemaParticipationQueryDirection { enum source; enum target; enum either; }
    enum def RtgSchemaParticipationDirection { enum source; enum target; enum both; }
    enum def RtgSchemaValueKind {
        enum string; enum integer; enum number; enum boolean;
        enum 'null';
        enum object; enum list; enum uuid;
    }
    enum def RtgSchemaStringFormat { enum date; enum date_time; enum uri; }
    enum def RtgSchemaTimeShape { enum state_now; enum state_as_of; enum 'event'; }
    enum def RtgSchemaIdentityMatchStrategy { enum exact; enum normalized; enum composite; }
    enum def RtgSchemaIdentityScope { enum same_type; }
    enum def RtgSchemaLinkKind {
        enum semantic; enum structural; enum governance;
        enum provenance; enum versioning; enum junction;
    }

    calc def SchemaValueKindCompatible {
        in actual : RtgSchemaValueKind;
        in allowed : RtgSchemaValueKind;
        doc /* Schema kinds are refinement predicates rather than mutually exclusive JSON tags: integer satisfies number, and uuid satisfies string. */
        return compatible : Boolean = actual == allowed or
            (actual == RtgSchemaValueKind::integer and allowed == RtgSchemaValueKind::number) or
            (actual == RtgSchemaValueKind::uuid and allowed == RtgSchemaValueKind::string);
    }

    attribute def RtgSchemaProperty {
        attribute name : String;
        attribute field : RtgSchemaField;
        doc /* One entry in a logical unique-key property map. Realization codecs may encode the entry collection as a JSON object. */
    }
    attribute def RtgSchemaField {
        attribute required : Boolean;
        attribute valueKinds[1..*] : RtgSchemaValueKind;
        attribute properties[0..*] : RtgSchemaProperty;
        attribute items[0..1] : RtgSchemaField;
        attribute allowedValues[0..*] : JsonScalar;
        attribute format[0..1] : RtgSchemaStringFormat;
        attribute minimum[0..1] : Real;
        attribute maximum[0..1] : Real;
        attribute pattern[0..1] : String;
        doc /* Recursive field schema. Allowed value kinds, allowed scalar values, and property names are unique unordered sets. Properties is non-empty only when object is allowed; items is present only when list is allowed. Optional format and pattern refine strings, while inclusive minimum/maximum refine numbers. */
    }
    abstract attribute def RtgSchemaPayload { doc /* One native anchor, data-object, or link schema payload selected by definition kind. */ }
    attribute def RtgAnchorSchemaPayload :> RtgSchemaPayload {
        attribute requiredDataTypes[0..*] : String;
        attribute optionalDataTypes[0..*] : String;
        doc /* Required and optional type-key sets are individually unique and mutually disjoint. */
    }
    attribute def RtgDataObjectSchemaPayload :> RtgSchemaPayload {
        attribute properties[0..*] : RtgSchemaProperty;
        doc /* Strict unique-key property map; undeclared properties are invalid for validation consumers. Realization codecs may encode it as a JSON object. */
    }
    attribute def RtgLinkSchemaPayload :> RtgSchemaPayload {
        attribute allowedSourceTypes[1..*] : String;
        attribute allowedTargetTypes[1..*] : String;
        attribute linkKind[0..1] : RtgSchemaLinkKind;
        doc /* Each endpoint set is unique and unordered. One type may occur in both sets. New and stored link definitions require linkKind; omission is representable only for explicit legacy-snapshot retrofit. */
    }
    attribute def RtgIdentityCriterion {
        attribute criterionKey : String;
        attribute propertyPaths[1..*] : String;
        attribute matchStrategy : RtgSchemaIdentityMatchStrategy;
        attribute scope : RtgSchemaIdentityScope;
        doc /* A stable named same-type identity rule over one or more unique logical property paths. */
    }
    item def RtgSchemaDefinition {
        attribute uuid[0..1] : Uuid;
        attribute kind : RtgSchemaDefinitionKind;
        attribute typeKey : String;
        attribute description : String;
        attribute payload : RtgSchemaPayload;
        attribute timeShape[0..1] : RtgSchemaTimeShape;
        attribute identityCriteria[0..*] : RtgIdentityCriterion;
        attribute system : JsonObject;
        doc /* UUID may be absent on write only. Description is non-empty human-readable semantic text. Anchor and data-object definitions require timeShape; links prohibit it. Identity criteria are optional for nodes and prohibited for links. Stored definitions have concrete UUID and Boolean system.live, defaulting missing live to true. */
    }
    attribute def RtgSchemaSnapshot { item definitions[0..*] ordered : RtgSchemaDefinition; }
    attribute def RtgSchemaDefinitionList { item definitions[0..*] ordered : RtgSchemaDefinition; }
    attribute def RtgSchemaAssociatedDataTypeList { attribute requiredDataTypes[0..*] ordered : String; attribute optionalDataTypes[0..*] ordered : String; }
    attribute def RtgSchemaLinkParticipation { attribute definitionUuid : Uuid; attribute typeKey : String; attribute direction : RtgSchemaParticipationDirection; attribute allowedSourceTypes[0..*] ordered : String; attribute allowedTargetTypes[0..*] ordered : String; attribute live : Boolean; }
    attribute def RtgSchemaLinkParticipationList { attribute links[0..*] ordered : RtgSchemaLinkParticipation; }
    attribute def RtgSchemaAnchorTypeSummary { attribute definitionUuid : Uuid; attribute typeKey : String; attribute description : String; attribute live : Boolean; }
    attribute def RtgSchemaAnchorTypeSummaryList { attribute anchorTypes[0..*] ordered : RtgSchemaAnchorTypeSummary; }
    attribute def RtgSchemaPack { item anchorSchemas[0..*] ordered : RtgSchemaDefinition; item associatedDataObjectSchemas[0..*] ordered : RtgSchemaDefinition; item linkSchemas[0..*] ordered : RtgSchemaDefinition; }
    attribute def RtgSchemaDeleteResult { item deletedDefinition : RtgSchemaDefinition; }
    attribute def RtgSchemaLinkKindRetrofitEntry { attribute definitionUuid : Uuid; attribute typeKey : String; attribute linkKind : RtgSchemaLinkKind; }
    attribute def RtgSchemaLinkKindRetrofitReport { attribute defaultedLinkDefinitions[0..*] ordered : RtgSchemaLinkKindRetrofitEntry; }
    attribute def RtgSchemaLinkKindRetrofitResult { attribute 'snapshot' : RtgSchemaSnapshot; attribute report : RtgSchemaLinkKindRetrofitReport; }

    attribute def RtgSchemaDefinitionNotFound { attribute 'message' : String; }
    attribute def RtgSchemaSnapshotInvalid { attribute 'message' : String; }
    attribute def RtgSchemaUuidInvalid { attribute 'message' : String; }
    attribute def RtgSchemaUuidConflict { attribute 'message' : String; }
    attribute def RtgSchemaDefinitionInvalid { attribute 'message' : String; }
    attribute def RtgSchemaPayloadInvalid { attribute 'message' : String; }
    attribute def RtgSchemaDefinitionKindInvalid { attribute 'message' : String; }
    attribute def RtgSchemaTypeKeyInvalid { attribute 'message' : String; }
    attribute def RtgSchemaDirectionInvalid { attribute 'message' : String; }
    attribute def RtgSchemaSystemValueInvalid { attribute 'message' : String; }
    attribute def RtgSchemaLiveTypeConflict { attribute 'message' : String; }

    action def ExportSchemaSnapshot { out 'snapshot' : RtgSchemaSnapshot; doc /* Export every full definition with normalized live metadata without mutation or filtering. */ @FailureContract { errorIds = (); } }
    action def PutSchemaDefinition { in definition : RtgSchemaDefinition; out stored : RtgSchemaDefinition; doc /* Generate or preserve identity, validate definition structure and the selected payload, and atomically create or fully replace one definition. */ @FailureContract { errorIds = ("RtgSchemaUuidInvalid", "RtgSchemaDefinitionKindInvalid", "RtgSchemaTypeKeyInvalid", "RtgSchemaDefinitionInvalid", "RtgSchemaPayloadInvalid", "RtgSchemaSystemValueInvalid", "RtgSchemaLiveTypeConflict"); } }
    action def GetSchemaDefinition { in definitionUuid : Uuid; out definition : RtgSchemaDefinition; doc /* Return one definition by UUID. */ @FailureContract { errorIds = ("RtgSchemaDefinitionNotFound"); } }
    action def ListSchemaDefinitions { in kind[0..1] : RtgSchemaDefinitionKind; in live[0..1] : Boolean; out result : RtgSchemaDefinitionList; doc /* List definitions with optional kind and live filters in deterministic order. */ @FailureContract { errorIds = ("RtgSchemaDefinitionKindInvalid"); } }
    action def ListDefinitionsByTypeKey { in schemaTypeKey : String; in kind[0..1] : RtgSchemaDefinitionKind; in live[0..1] : Boolean; out result : RtgSchemaDefinitionList; doc /* List every definition for one type key with optional kind/live filters, including multiple non-live candidates. */ @FailureContract { errorIds = ("RtgSchemaTypeKeyInvalid", "RtgSchemaDefinitionKindInvalid"); } }
    action def ListAnchorDataTypeKeys { in anchorTypeKey : String; in live[0..1] : Boolean default = true; out result : RtgSchemaAssociatedDataTypeList; doc /* Return required and optional associated data type keys declared by one anchor schema. */ @FailureContract { errorIds = ("RtgSchemaTypeKeyInvalid", "RtgSchemaDefinitionNotFound"); } }
    action def ListLinkParticipation { in typeKey : String; in direction : RtgSchemaParticipationQueryDirection default = RtgSchemaParticipationQueryDirection::either; in live[0..1] : Boolean default = true; out result : RtgSchemaLinkParticipationList; doc /* Return link schemas that admit the type as source, target, or either endpoint. Each result reports source, target, or both relative to the queried type. */ @FailureContract { errorIds = ("RtgSchemaTypeKeyInvalid", "RtgSchemaDirectionInvalid"); } }
    action def ListAnchorTypeSummaries { in live[0..1] : Boolean default = true; out result : RtgSchemaAnchorTypeSummaryList; doc /* Return anchor type identities and descriptions only, never graph counts. */ @FailureContract { errorIds = (); } }
    action def GetSchemaPack { in anchorTypeKeys[1..*] ordered : String; in live[0..1] : Boolean default = true; out result : RtgSchemaPack; doc /* Expand unique requested anchor schemas in request order with defined associated-data schemas and participating link schemas; omit missing referenced schemas but fail missing requested anchors. */ @FailureContract { errorIds = ("RtgSchemaTypeKeyInvalid", "RtgSchemaDefinitionNotFound"); } }
    action def DeleteSchemaDefinition { in definitionUuid : Uuid; out result : RtgSchemaDeleteResult; doc /* Delete exactly one definition and no graph, constraint, or migration record. */ @FailureContract { errorIds = ("RtgSchemaDefinitionNotFound"); } }
    action def RetrofitSchemaSnapshotLinkKinds { in 'snapshot' : RtgSchemaSnapshot; in defaultKind : RtgSchemaLinkKind; out result : RtgSchemaLinkKindRetrofitResult; doc /* Return a new snapshot in which only missing legacy link kinds are defaulted; do not mutate the input snapshot. */ @FailureContract { errorIds = ("RtgSchemaSnapshotInvalid", "RtgSchemaPayloadInvalid"); } }

    part def <'component.rtg.schema'> RtgSchema {
        doc /* Own RTG-native schema definitions and derived navigation indexes, not object validation, graph state, migration membership, or cutover policy. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        item definitions[0..*] : RtgSchemaDefinition { doc /* Canonical component-owned schema-definition occurrences. */ }
        derived attribute navigationIndexes : JsonObject { doc /* Ephemeral navigation indexes derived from canonical schema definitions. */ }
        perform action exportSnapshot[0..*] : ExportSchemaSnapshot; perform action putDefinition[0..*] : PutSchemaDefinition; perform action getDefinition[0..*] : GetSchemaDefinition;
        perform action listDefinitions[0..*] : ListSchemaDefinitions; perform action listDefinitionsByTypeKey[0..*] : ListDefinitionsByTypeKey;
        perform action listAnchorDataTypeKeys[0..*] : ListAnchorDataTypeKeys; perform action listLinkParticipation[0..*] : ListLinkParticipation;
        perform action listAnchorTypeSummaries[0..*] : ListAnchorTypeSummaries; perform action getSchemaPack[0..*] : GetSchemaPack; perform action deleteDefinition[0..*] : DeleteSchemaDefinition;
        dependency snapshotState from exportSnapshot to definitions { @StateAccess { kind = StateAccessKind::read; } doc /* read all canonical definitions. */ }
        dependency putState from putDefinition to definitions { @StateAccess { kind = StateAccessKind::write; } doc /* atomically create/replace definition and rebuild affected indexes. */ }
        dependency getState from getDefinition to definitions { @StateAccess { kind = StateAccessKind::read; } doc /* read one canonical definition. */ }
        dependency listState from listDefinitions to navigationIndexes { @StateAccess { kind = StateAccessKind::read; } doc /* read kind/live indexes. */ }
        dependency listTypeState from listDefinitionsByTypeKey to navigationIndexes { @StateAccess { kind = StateAccessKind::read; } doc /* read type-key index. */ }
        dependency anchorDataState from listAnchorDataTypeKeys to navigationIndexes { @StateAccess { kind = StateAccessKind::read; } doc /* read associated-data index. */ }
        dependency linkState from listLinkParticipation to navigationIndexes { @StateAccess { kind = StateAccessKind::read; } doc /* read source/target participation indexes. */ }
        dependency summaryState from listAnchorTypeSummaries to navigationIndexes { @StateAccess { kind = StateAccessKind::read; } doc /* read anchor summary index. */ }
        dependency packState from getSchemaPack to navigationIndexes { @StateAccess { kind = StateAccessKind::read; } doc /* assemble schema-only pack from canonical definitions and indexes. */ }
        dependency deleteState from deleteDefinition to definitions { @StateAccess { kind = StateAccessKind::delete; } doc /* remove one definition and affected indexes. */ }
    }
    action def CreateEmptyRtgSchema { out part schema : RtgSchema; doc /* Return an empty registry with empty derived indexes. */ @FailureContract { errorIds = (); } }
    action def ImportRtgSchemaSnapshot { in 'snapshot' : RtgSchemaSnapshot; out part schema : RtgSchema; doc /* Validate every record, UUID, kind, type key, payload, system value, and global live uniqueness before rebuilding indexes and exposing the registry. */ @FailureContract { errorIds = ("RtgSchemaSnapshotInvalid", "RtgSchemaUuidInvalid", "RtgSchemaUuidConflict", "RtgSchemaDefinitionKindInvalid", "RtgSchemaTypeKeyInvalid", "RtgSchemaDefinitionInvalid", "RtgSchemaPayloadInvalid", "RtgSchemaSystemValueInvalid", "RtgSchemaLiveTypeConflict"); } }


    requirement <'contract.rtg.schema.write_effect'> definitionWriteEffect {
        subject operation : PutSchemaDefinition;
        require constraint {
            doc /* Missing UUID generates a new UUID; supplied identity is preserved and fully replaces that record. Description is non-empty semantic text. Missing system.live becomes true. Kind selects the exact payload family and at most one live definition of any kind owns a type key. */
        }
    }

    requirement <'contract.rtg.schema.field_semantics'> fieldSemantics {
        subject schema : RtgSchema;
        require constraint {
            doc /* A field has a non-empty unique unordered value-kind set. Compatibility follows SchemaValueKindCompatible: Boolean never satisfies a numeric kind; integer satisfies integer and number; a fractional number satisfies number; every string satisfies string and a canonical UUID string also satisfies uuid. allowedValues is an optional non-empty unique scalar set compatible with the declared kinds. date is an RFC 3339 full-date, date_time is an RFC 3339 datetime with explicit timezone, uri is an absolute URI with scheme, pattern is a valid RE2 unanchored search, and inclusive numeric bounds require a numeric kind with minimum no greater than maximum. Nested properties are permitted only with object, items only with list, null is permitted only when explicitly listed, required fields must be present, and strict data-object payloads reject undeclared properties recursively. */
        }
    }

    requirement <'contract.rtg.schema.canonical_ordering'> canonicalOrdering {
        subject schema : RtgSchema;
        require constraint {
            doc /* Definition lists and snapshots use ascending textual UUID order. Associated-data results encode each type-key set in ascending text order. Link-participation results use ascending link type key with textual definition UUID as tie-breaker and encode endpoint sets in ascending text order. Anchor summaries use definition order. Schema packs preserve unique requested anchor-key order, then use definition order for associated-data and link schemas. */
        }
    }

    requirement <'contract.rtg.schema.intentional_boundary'> intentionalBoundary {
        subject schema : RtgSchema;
        require constraint {
            doc /* Schema owns native definition records and navigation only. It does not validate graph objects or changes, enforce graph-pattern constraints, own discovery views/counts, migration membership/cutover, inheritance/composition, general schema query/inference, persistence, authorization, workflow, or distributed coordination. */
        }
    }

    requirement <'contract.rtg.schema.payload_semantics'> payloadSemantics {
        subject schema : RtgSchema;
        require constraint {
            doc /* Anchor payloads distinguish disjoint required and optional associated-data type-key sets; data-object payloads map unique property names to recursive field definitions; link payloads contain non-empty unique source and target type-key sets whose overlap is allowed and require one of the six RtgSchemaLinkKind values. Kind and payload family must agree. */
        }
    }

    requirement <'contract.rtg.schema.kernel_meta_model'> kernelMetaModelSemantics {
        subject schema : RtgSchema;
        require constraint {
            doc /* Every anchor and data-object definition declares exactly one time shape: state_now, state_as_of, or event. Link definitions declare no time shape. state_as_of is valid only for data objects whose required valid_from and valid_to fields are strings refined by date_time format. created_at and updated_at are kernel-owned system fields and cannot be declared as domain properties. A node may declare uniquely keyed same-type identity criteria using exact, normalized, or composite matching; anchor paths are limited to display_name, data-object paths must resolve through declared properties, and links declare no identity criteria. */
        }
    }

    requirement <'contract.rtg.schema.link_kind_retrofit'> linkKindRetrofitSemantics {
        subject operation : RetrofitSchemaSnapshotLinkKinds;
        require constraint {
            doc /* The only permitted default is semantic. Each link definition missing linkKind receives that value and one deterministically ordered report entry; existing recognized kinds and every non-link definition remain unchanged. Invalid snapshots, defaults, or existing kinds fail without mutating the input. */
        }
    }

    requirement <'contract.rtg.schema.read_effect'> schemaReadEffect {
        subject schema : RtgSchema;
        require constraint {
            doc /* Reads are deterministic, derive only from definitions and indexes, honor explicit filters/defaults, never inspect graph state, and never mutate. */
        }
    }

    requirement <'contract.rtg.schema.delete_effect'> schemaDeleteEffect {
        subject operation : DeleteSchemaDefinition;
        require constraint {
            doc /* Delete removes only one definition and its derived entries; it performs no safety decision or cross-component cascade. */
        }
    }

    requirement <'contract.rtg.schema.snapshot_effect'> schemaSnapshotEffect {
        subject schema : RtgSchema;
        require constraint {
            doc /* Snapshot round-trip preserves full records and normalized live state; import validates the whole candidate before visibility. */
        }
    }

    requirement <'invariant.rtg.schema.uuid_unique'> uuidUnique {
        subject schema : RtgSchema;
        require constraint {
            doc /* Definition UUIDs are unique. */
        }
    }

    requirement <'invariant.rtg.schema.live_type_unique'> liveTypeUnique {
        subject schema : RtgSchema;
        require constraint {
            doc /* At most one live definition across all definition kinds owns a type key. */
        }
    }

    requirement <'invariant.rtg.schema.live_status_boolean'> liveStatusBoolean {
        subject schema : RtgSchema;
        require constraint {
            doc /* Missing live normalizes to true and supplied live is Boolean. */
        }
    }

    requirement <'invariant.rtg.schema.no_change_set_ownership'> noChangeSetOwnership {
        subject schema : RtgSchema;
        require constraint {
            doc /* Schema owns no change batches or migration membership. */
        }
    }

    requirement <'invariant.rtg.schema.no_object_validation'> noObjectValidation {
        subject schema : RtgSchema;
        require constraint {
            doc /* Schema stores definitions but does not validate graph objects. */
        }
    }

    requirement <'invariant.rtg.schema.native_payloads'> nativePayloads {
        subject schema : RtgSchema;
        require constraint {
            doc /* Payloads use anchor, data-object, field, and link concepts rather than storage-engine schemas. */
        }
    }

    requirement <'invariant.rtg.schema.no_inheritance_composition_v1'> noInheritanceCompositionV1 {
        subject schema : RtgSchema;
        require constraint {
            doc /* V1 defines no inheritance or composition semantics. */
        }
    }

    requirement <'invariant.rtg.schema.type_key_changes_are_migration_concerns'> typeKeyChangesAreMigrationConcerns {
        subject schema : RtgSchema;
        require constraint {
            doc /* Type-key lifecycle changes are coordinated outside the store. */
        }
    }

    requirement <'invariant.rtg.schema.navigation_indexes_match_payloads'> navigationIndexesMatchPayloads {
        subject schema : RtgSchema;
        require constraint {
            doc /* Derived kind, type, live, associated-data, and link-participation indexes exactly match canonical payloads. */
        }
    }

    requirement <'invariant.rtg.schema.deterministic_list_ordering'> deterministicListOrdering {
        subject schema : RtgSchema;
        require constraint {
            doc /* Public list results are deterministic for one registry state. */
        }
    }

    requirement <'contract.rtg.schema.export_schema_snapshot.failures'> exportSchemaSnapshotFailureSemantics {
        subject operation : ExportSchemaSnapshot;
        require constraint {
            doc /* Export has no declared domain failure. */
        }
    }

    requirement <'contract.rtg.schema.put_schema_definition.failures'> putSchemaDefinitionFailureSemantics {
        subject operation : PutSchemaDefinition;
        require constraint {
            doc /* Rejected writes leave definitions and indexes unchanged. */
        }
    }

    requirement <'contract.rtg.schema.get_schema_definition.failures'> getSchemaDefinitionFailureSemantics {
        subject operation : GetSchemaDefinition;
        require constraint {
            doc /* Read failure has no effect. */
        }
    }

    requirement <'contract.rtg.schema.list_schema_definitions.failures'> listSchemaDefinitionsFailureSemantics {
        subject operation : ListSchemaDefinitions;
        require constraint {
            doc /* Read failure has no effect. */
        }
    }

    requirement <'contract.rtg.schema.list_definitions_by_type_key.failures'> listDefinitionsByTypeKeyFailureSemantics {
        subject operation : ListDefinitionsByTypeKey;
        require constraint {
            doc /* Read failure has no effect. */
        }
    }

    requirement <'contract.rtg.schema.list_anchor_data_type_keys.failures'> listAnchorDataTypeKeysFailureSemantics {
        subject operation : ListAnchorDataTypeKeys;
        require constraint {
            doc /* Read failure has no effect. */
        }
    }

    requirement <'contract.rtg.schema.list_link_participation.failures'> listLinkParticipationFailureSemantics {
        subject operation : ListLinkParticipation;
        require constraint {
            doc /* Read failure has no effect. */
        }
    }

    requirement <'contract.rtg.schema.list_anchor_type_summaries.failures'> listAnchorTypeSummariesFailureSemantics {
        subject operation : ListAnchorTypeSummaries;
        require constraint {
            doc /* Read is state-neutral. */
        }
    }

    requirement <'contract.rtg.schema.get_schema_pack.failures'> getSchemaPackFailureSemantics {
        subject operation : GetSchemaPack;
        require constraint {
            doc /* Read failure has no effect. */
        }
    }

    requirement <'contract.rtg.schema.delete_schema_definition.failures'> deleteSchemaDefinitionFailureSemantics {
        subject operation : DeleteSchemaDefinition;
        require constraint {
            doc /* Rejected delete has no effect. */
        }
    }

    requirement <'contract.rtg.schema.create_empty_rtg_schema.failures'> createEmptyRtgSchemaFailureSemantics {
        subject operation : CreateEmptyRtgSchema;
        require constraint {
            doc /* Construction has no declared domain failure. */
        }
    }

    requirement <'contract.rtg.schema.import_rtg_schema_snapshot.failures'> importRtgSchemaSnapshotFailureSemantics {
        subject operation : ImportRtgSchemaSnapshot;
        require constraint {
            doc /* Failure returns no partially imported registry. */
        }
    }

    requirement <'contract.rtg.schema.retrofit_schema_snapshot_link_kinds.failures'> retrofitSchemaSnapshotLinkKindsFailureSemantics {
        subject operation : RetrofitSchemaSnapshotLinkKinds;
        require constraint {
            doc /* Failure returns no projected snapshot, does not mutate the input snapshot, and does not create a schema registry. */
        }
    }

    part contractContext {
        part schema : RtgSchema;
        satisfy definitionWriteEffect by schema.putDefinition;
        satisfy fieldSemantics by schema;
        satisfy payloadSemantics by schema;
        satisfy kernelMetaModelSemantics by schema;
        satisfy schemaReadEffect by schema;
        satisfy canonicalOrdering by schema;
        satisfy intentionalBoundary by schema;
        satisfy schemaSnapshotEffect by schema;
        satisfy uuidUnique by schema;
        satisfy liveTypeUnique by schema;
        satisfy liveStatusBoolean by schema;
        satisfy noChangeSetOwnership by schema;
        satisfy noObjectValidation by schema;
        satisfy nativePayloads by schema;
        satisfy noInheritanceCompositionV1 by schema;
        satisfy typeKeyChangesAreMigrationConcerns by schema;
        satisfy navigationIndexesMatchPayloads by schema;
        satisfy deterministicListOrdering by schema;
        satisfy schemaDeleteEffect by schema.deleteDefinition;

        satisfy exportSchemaSnapshotFailureSemantics by schema.exportSnapshot;
        satisfy putSchemaDefinitionFailureSemantics by schema.putDefinition;
        satisfy getSchemaDefinitionFailureSemantics by schema.getDefinition;
        satisfy listSchemaDefinitionsFailureSemantics by schema.listDefinitions;
        satisfy listDefinitionsByTypeKeyFailureSemantics by schema.listDefinitionsByTypeKey;
        satisfy listAnchorDataTypeKeysFailureSemantics by schema.listAnchorDataTypeKeys;
        satisfy listLinkParticipationFailureSemantics by schema.listLinkParticipation;
        satisfy listAnchorTypeSummariesFailureSemantics by schema.listAnchorTypeSummaries;
        satisfy getSchemaPackFailureSemantics by schema.getSchemaPack;
        satisfy deleteSchemaDefinitionFailureSemantics by schema.deleteDefinition;
        action createEmptyRtgSchemaSubject : CreateEmptyRtgSchema;
        satisfy createEmptyRtgSchemaFailureSemantics by createEmptyRtgSchemaSubject;
        action importRtgSchemaSnapshotSubject : ImportRtgSchemaSnapshot;
        satisfy importRtgSchemaSnapshotFailureSemantics by importRtgSchemaSnapshotSubject;
        action retrofitSchemaSnapshotLinkKindsSubject : RetrofitSchemaSnapshotLinkKinds;
        satisfy linkKindRetrofitSemantics by retrofitSchemaSnapshotLinkKindsSubject;
        satisfy retrofitSchemaSnapshotLinkKindsFailureSemantics by retrofitSchemaSnapshotLinkKindsSubject;
    }

    verification def PutSchemaDefinitionContractVerification {
        subject operation : PutSchemaDefinition;
        objective {
            verify definitionWriteEffect;

            verify putSchemaDefinitionFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/rtg/schema/tests/test_rtg_schema_contract.py#PutSchemaDefinitionContractVerification";
            implementationScope = "InMemoryRtgSchema";
        }
    }

    verification def DeleteSchemaDefinitionContractVerification {
        subject operation : DeleteSchemaDefinition;
        objective {
            verify schemaDeleteEffect;

            verify deleteSchemaDefinitionFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/rtg/schema/tests/test_rtg_schema_contract.py#DeleteSchemaDefinitionContractVerification";
            implementationScope = "InMemoryRtgSchema";
        }
    }
    verification def ExportSchemaSnapshotContractVerification {
        subject operation : ExportSchemaSnapshot;
        objective { verify exportSchemaSnapshotFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/schema/tests/test_rtg_schema_contract.py#ExportSchemaSnapshotContractVerification"; implementationScope = "InMemoryRtgSchema"; }
    }

    verification def GetSchemaDefinitionContractVerification {
        subject operation : GetSchemaDefinition;
        objective { verify getSchemaDefinitionFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/schema/tests/test_rtg_schema_contract.py#GetSchemaDefinitionContractVerification"; implementationScope = "InMemoryRtgSchema"; }
    }

    verification def ListSchemaDefinitionsContractVerification {
        subject operation : ListSchemaDefinitions;
        objective { verify listSchemaDefinitionsFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/schema/tests/test_rtg_schema_contract.py#ListSchemaDefinitionsContractVerification"; implementationScope = "InMemoryRtgSchema"; }
    }

    verification def ListDefinitionsByTypeKeyContractVerification {
        subject operation : ListDefinitionsByTypeKey;
        objective { verify listDefinitionsByTypeKeyFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/schema/tests/test_rtg_schema_contract.py#ListDefinitionsByTypeKeyContractVerification"; implementationScope = "InMemoryRtgSchema"; }
    }

    verification def ListAnchorDataTypeKeysContractVerification {
        subject operation : ListAnchorDataTypeKeys;
        objective { verify listAnchorDataTypeKeysFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/schema/tests/test_rtg_schema_contract.py#ListAnchorDataTypeKeysContractVerification"; implementationScope = "InMemoryRtgSchema"; }
    }

    verification def ListLinkParticipationContractVerification {
        subject operation : ListLinkParticipation;
        objective { verify listLinkParticipationFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/schema/tests/test_rtg_schema_contract.py#ListLinkParticipationContractVerification"; implementationScope = "InMemoryRtgSchema"; }
    }

    verification def ListAnchorTypeSummariesContractVerification {
        subject operation : ListAnchorTypeSummaries;
        objective { verify listAnchorTypeSummariesFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/schema/tests/test_rtg_schema_contract.py#ListAnchorTypeSummariesContractVerification"; implementationScope = "InMemoryRtgSchema"; }
    }

    verification def GetSchemaPackContractVerification {
        subject operation : GetSchemaPack;
        objective { verify getSchemaPackFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/schema/tests/test_rtg_schema_contract.py#GetSchemaPackContractVerification"; implementationScope = "InMemoryRtgSchema"; }
    }

    verification def CreateEmptyRtgSchemaContractVerification {
        subject operation : CreateEmptyRtgSchema;
        objective { verify createEmptyRtgSchemaFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/schema/tests/test_rtg_schema_contract.py#CreateEmptyRtgSchemaContractVerification"; implementationScope = "InMemoryRtgSchema"; }
    }

    verification def ImportRtgSchemaSnapshotContractVerification {
        subject operation : ImportRtgSchemaSnapshot;
        objective { verify importRtgSchemaSnapshotFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/schema/tests/test_rtg_schema_contract.py#ImportRtgSchemaSnapshotContractVerification"; implementationScope = "InMemoryRtgSchema"; }
    }
    verification def RetrofitSchemaSnapshotLinkKindsContractVerification {
        subject operation : RetrofitSchemaSnapshotLinkKinds;
        objective { verify linkKindRetrofitSemantics; verify retrofitSchemaSnapshotLinkKindsFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/schema/tests/test_rtg_schema_contract.py#RetrofitSchemaSnapshotLinkKindsContractVerification"; implementationScope = "InMemoryRtgSchema"; }
    }



    verification def RtgSchemaBoundaryVerification {
        subject schema : RtgSchema;
        objective { verify fieldSemantics; verify payloadSemantics; verify kernelMetaModelSemantics; verify schemaReadEffect; verify canonicalOrdering; verify intentionalBoundary; verify schemaSnapshotEffect; verify uuidUnique; verify liveTypeUnique; verify liveStatusBoolean; verify noChangeSetOwnership; verify noObjectValidation; verify nativePayloads; verify noInheritanceCompositionV1; verify typeKeyChangesAreMigrationConcerns; verify navigationIndexesMatchPayloads; verify deterministicListOrdering; }
        @EvidenceBinding { evidenceId = "components/rtg/schema/tests/test_rtg_schema_contract.py#RtgSchemaBoundaryVerification"; implementationScope = "InMemoryRtgSchema"; }
    }
}
