# component.rtg.schema

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

- Model definition: `RtgSchema`
- Lifecycle: `accepted`
- Purpose: Own RTG-native schema definitions and derived navigation indexes, not object validation, graph state, migration membership, or cutover policy.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `exportSnapshot` | `ExportSchemaSnapshot` | out `snapshot: RtgSchemaSnapshot` | None | Export every full definition with normalized live metadata without mutation or filtering. |
| `putDefinition` | `PutSchemaDefinition` | in `definition: RtgSchemaDefinition`; out `stored: RtgSchemaDefinition` | `RtgSchemaUuidInvalid`, `RtgSchemaDefinitionKindInvalid`, `RtgSchemaTypeKeyInvalid`, `RtgSchemaDefinitionInvalid`, `RtgSchemaPayloadInvalid`, `RtgSchemaSystemValueInvalid`, `RtgSchemaLiveTypeConflict` | Generate or preserve identity, validate definition structure and the selected payload, and atomically create or fully replace one definition. |
| `getDefinition` | `GetSchemaDefinition` | in `definitionUuid: Uuid`; out `definition: RtgSchemaDefinition` | `RtgSchemaDefinitionNotFound` | Return one definition by UUID. |
| `listDefinitions` | `ListSchemaDefinitions` | in `kind: RtgSchemaDefinitionKind[0..1]`; in `live: Boolean[0..1]`; out `result: RtgSchemaDefinitionList` | `RtgSchemaDefinitionKindInvalid` | List definitions with optional kind and live filters in deterministic order. |
| `listDefinitionsByTypeKey` | `ListDefinitionsByTypeKey` | in `schemaTypeKey: String`; in `kind: RtgSchemaDefinitionKind[0..1]`; in `live: Boolean[0..1]`; out `result: RtgSchemaDefinitionList` | `RtgSchemaTypeKeyInvalid`, `RtgSchemaDefinitionKindInvalid` | List every definition for one type key with optional kind/live filters, including multiple non-live candidates. |
| `listAnchorDataTypeKeys` | `ListAnchorDataTypeKeys` | in `anchorTypeKey: String`; in `live: Boolean[0..1]` = `true`; out `result: RtgSchemaAssociatedDataTypeList` | `RtgSchemaTypeKeyInvalid`, `RtgSchemaDefinitionNotFound` | Return required and optional associated data type keys declared by one anchor schema. |
| `listLinkParticipation` | `ListLinkParticipation` | in `typeKey: String`; in `direction: RtgSchemaParticipationQueryDirection` = `RtgSchemaParticipationQueryDirection::either`; in `live: Boolean[0..1]` = `true`; out `result: RtgSchemaLinkParticipationList` | `RtgSchemaTypeKeyInvalid`, `RtgSchemaDirectionInvalid` | Return link schemas that admit the type as source, target, or either endpoint. Each result reports source, target, or both relative to the queried type. |
| `listAnchorTypeSummaries` | `ListAnchorTypeSummaries` | in `live: Boolean[0..1]` = `true`; out `result: RtgSchemaAnchorTypeSummaryList` | None | Return anchor type identities and descriptions only, never graph counts. |
| `getSchemaPack` | `GetSchemaPack` | in `anchorTypeKeys: String[1..*] ordered`; in `live: Boolean[0..1]` = `true`; out `result: RtgSchemaPack` | `RtgSchemaTypeKeyInvalid`, `RtgSchemaDefinitionNotFound` | Expand unique requested anchor schemas in request order with defined associated-data schemas and participating link schemas; omit missing referenced schemas but fail missing requested anchors. |
| `deleteDefinition` | `DeleteSchemaDefinition` | in `definitionUuid: Uuid`; out `result: RtgSchemaDeleteResult` | `RtgSchemaDefinitionNotFound` | Delete exactly one definition and no graph, constraint, or migration record. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `CreateEmptyRtgSchema` | out `schema: RtgSchema` | None | Return an empty registry with empty derived indexes. |
| `ImportRtgSchemaSnapshot` | in `snapshot: RtgSchemaSnapshot`; out `schema: RtgSchema` | `RtgSchemaSnapshotInvalid`, `RtgSchemaUuidInvalid`, `RtgSchemaUuidConflict`, `RtgSchemaDefinitionKindInvalid`, `RtgSchemaTypeKeyInvalid`, `RtgSchemaDefinitionInvalid`, `RtgSchemaPayloadInvalid`, `RtgSchemaSystemValueInvalid`, `RtgSchemaLiveTypeConflict` | Validate every record, UUID, kind, type key, payload, system value, and global live uniqueness before rebuilding indexes and exposing the registry. |

## Retained collaborator roles

| Role | Kind | Referenced type | Multiplicity |
|---|---|---|---|
| — | — | — | No retained collaborator roles. |

## Owned state

| State feature | Type | Ownership | Meaning |
|---|---|---|---|
| `definitions` | `RtgSchemaDefinition` | `owned` | Canonical component-owned schema-definition occurrences. |
| `navigationIndexes` | `JsonObject` | `derived` | Ephemeral navigation indexes derived from canonical schema definitions. |

## Action and state effects

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `exportSnapshot` | `definitions` | `read` | read all canonical definitions. |
| `putDefinition` | `definitions` | `write` | atomically create/replace definition and rebuild affected indexes. |
| `getDefinition` | `definitions` | `read` | read one canonical definition. |
| `listDefinitions` | `navigationIndexes` | `read` | read kind/live indexes. |
| `listDefinitionsByTypeKey` | `navigationIndexes` | `read` | read type-key index. |
| `listAnchorDataTypeKeys` | `navigationIndexes` | `read` | read associated-data index. |
| `listLinkParticipation` | `navigationIndexes` | `read` | read source/target participation indexes. |
| `listAnchorTypeSummaries` | `navigationIndexes` | `read` | read anchor summary index. |
| `getSchemaPack` | `navigationIndexes` | `read` | assemble schema-only pack from canonical definitions and indexes. |
| `deleteDefinition` | `definitions` | `delete` | remove one definition and affected indexes. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| — | — | No action decomposition required at this boundary. |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.rtg.schema.write_effect` | `PutSchemaDefinition` | `schema.putDefinition` | Missing UUID generates a new UUID; supplied identity is preserved and fully replaces that record. Description is non-empty semantic text. Missing system.live becomes true. Kind selects the exact payload family and at most one live definition of any kind owns a type key. |
| `contract.rtg.schema.field_semantics` | `RtgSchema` | `schema` | A field has a non-empty unique unordered value-kind set. Compatibility follows SchemaValueKindCompatible: Boolean never satisfies a numeric kind; integer satisfies integer and number; a fractional number satisfies number; every string satisfies string and a canonical UUID string also satisfies uuid. allowedValues is an optional non-empty unique scalar set compatible with the declared kinds. date is an RFC 3339 full-date, date_time is an RFC 3339 datetime with explicit timezone, uri is an absolute URI with scheme, pattern is a valid RE2 unanchored search, and inclusive numeric bounds require a numeric kind with minimum no greater than maximum. Nested properties are permitted only with object, items only with list, null is permitted only when explicitly listed, required fields must be present, and strict data-object payloads reject undeclared properties recursively. |
| `contract.rtg.schema.canonical_ordering` | `RtgSchema` | `schema` | Definition lists and snapshots use ascending textual UUID order. Associated-data results encode each type-key set in ascending text order. Link-participation results use ascending link type key with textual definition UUID as tie-breaker and encode endpoint sets in ascending text order. Anchor summaries use definition order. Schema packs preserve unique requested anchor-key order, then use definition order for associated-data and link schemas. |
| `contract.rtg.schema.intentional_boundary` | `RtgSchema` | `schema` | Schema owns native definition records and navigation only. It does not validate graph objects or changes, enforce graph-pattern constraints, own discovery views/counts, migration membership/cutover, inheritance/composition, general schema query/inference, persistence, authorization, workflow, or distributed coordination. |
| `contract.rtg.schema.payload_semantics` | `RtgSchema` | `schema` | Anchor payloads distinguish disjoint required and optional associated-data type-key sets; data-object payloads map unique property names to recursive field definitions; link payloads contain non-empty unique source and target type-key sets whose overlap is allowed and require one of the six RtgSchemaLinkKind values. Kind and payload family must agree. |
| `contract.rtg.schema.kernel_meta_model` | `RtgSchema` | `schema` | Every anchor and data-object definition declares exactly one time shape: state_now, state_as_of, or event. Link definitions declare no time shape. state_as_of is valid only for data objects whose required valid_from and valid_to fields are strings refined by date_time format. created_at and updated_at are kernel-owned system fields and cannot be declared as domain properties. A node may declare uniquely keyed same-type identity criteria using exact, normalized, or composite matching; anchor paths are limited to display_name, data-object paths must resolve through declared properties, and links declare no identity criteria. |
| `contract.rtg.schema.link_kind_retrofit` | `RetrofitSchemaSnapshotLinkKinds` | `retrofitSchemaSnapshotLinkKindsSubject` | The only permitted default is semantic. Each link definition missing linkKind receives that value and one deterministically ordered report entry; existing recognized kinds and every non-link definition remain unchanged. Invalid snapshots, defaults, or existing kinds fail without mutating the input. |
| `contract.rtg.schema.read_effect` | `RtgSchema` | `schema` | Reads are deterministic, derive only from definitions and indexes, honor explicit filters/defaults, never inspect graph state, and never mutate. |
| `contract.rtg.schema.delete_effect` | `DeleteSchemaDefinition` | `schema.deleteDefinition` | Delete removes only one definition and its derived entries; it performs no safety decision or cross-component cascade. |
| `contract.rtg.schema.snapshot_effect` | `RtgSchema` | `schema` | Snapshot round-trip preserves full records and normalized live state; import validates the whole candidate before visibility. |
| `invariant.rtg.schema.uuid_unique` | `RtgSchema` | `schema` | Definition UUIDs are unique. |
| `invariant.rtg.schema.live_type_unique` | `RtgSchema` | `schema` | At most one live definition across all definition kinds owns a type key. |
| `invariant.rtg.schema.live_status_boolean` | `RtgSchema` | `schema` | Missing live normalizes to true and supplied live is Boolean. |
| `invariant.rtg.schema.no_change_set_ownership` | `RtgSchema` | `schema` | Schema owns no change batches or migration membership. |
| `invariant.rtg.schema.no_object_validation` | `RtgSchema` | `schema` | Schema stores definitions but does not validate graph objects. |
| `invariant.rtg.schema.native_payloads` | `RtgSchema` | `schema` | Payloads use anchor, data-object, field, and link concepts rather than storage-engine schemas. |
| `invariant.rtg.schema.no_inheritance_composition_v1` | `RtgSchema` | `schema` | V1 defines no inheritance or composition semantics. |
| `invariant.rtg.schema.type_key_changes_are_migration_concerns` | `RtgSchema` | `schema` | Type-key lifecycle changes are coordinated outside the store. |
| `invariant.rtg.schema.schema_evolution_ops_external` | `RtgSchema` | `schema` | This component stores and validates full schema definitions. Reviewed schema-evolution operation history belongs to migration records, and diff review, graph-data effects, and cutover sequencing belong to the controller. |
| `invariant.rtg.schema.destructive_changes_are_migration_concerns` | `RtgSchema` | `schema` | Destructive or data-affecting changes to live types, properties, or link types are not schema-store behavior. Deleting a schema definition deletes registry state only and never strips or rewrites graph data. |
| `invariant.rtg.schema.navigation_indexes_match_payloads` | `RtgSchema` | `schema` | Derived kind, type, live, associated-data, and link-participation indexes exactly match canonical payloads. |
| `invariant.rtg.schema.deterministic_list_ordering` | `RtgSchema` | `schema` | Public list results are deterministic for one registry state. |
| `contract.rtg.schema.export_schema_snapshot.failures` | `ExportSchemaSnapshot` | `schema.exportSnapshot` | Export has no declared domain failure. |
| `contract.rtg.schema.put_schema_definition.failures` | `PutSchemaDefinition` | `schema.putDefinition` | Rejected writes leave definitions and indexes unchanged. |
| `contract.rtg.schema.get_schema_definition.failures` | `GetSchemaDefinition` | `schema.getDefinition` | Read failure has no effect. |
| `contract.rtg.schema.list_schema_definitions.failures` | `ListSchemaDefinitions` | `schema.listDefinitions` | Read failure has no effect. |
| `contract.rtg.schema.list_definitions_by_type_key.failures` | `ListDefinitionsByTypeKey` | `schema.listDefinitionsByTypeKey` | Read failure has no effect. |
| `contract.rtg.schema.list_anchor_data_type_keys.failures` | `ListAnchorDataTypeKeys` | `schema.listAnchorDataTypeKeys` | Read failure has no effect. |
| `contract.rtg.schema.list_link_participation.failures` | `ListLinkParticipation` | `schema.listLinkParticipation` | Read failure has no effect. |
| `contract.rtg.schema.list_anchor_type_summaries.failures` | `ListAnchorTypeSummaries` | `schema.listAnchorTypeSummaries` | Read is state-neutral. |
| `contract.rtg.schema.get_schema_pack.failures` | `GetSchemaPack` | `schema.getSchemaPack` | Read failure has no effect. |
| `contract.rtg.schema.delete_schema_definition.failures` | `DeleteSchemaDefinition` | `schema.deleteDefinition` | Rejected delete has no effect. |
| `contract.rtg.schema.create_empty_rtg_schema.failures` | `CreateEmptyRtgSchema` | `createEmptyRtgSchemaSubject` | Construction has no declared domain failure. |
| `contract.rtg.schema.import_rtg_schema_snapshot.failures` | `ImportRtgSchemaSnapshot` | `importRtgSchemaSnapshotSubject` | Failure returns no partially imported registry. |
| `contract.rtg.schema.retrofit_schema_snapshot_link_kinds.failures` | `RetrofitSchemaSnapshotLinkKinds` | `retrofitSchemaSnapshotLinkKindsSubject` | Failure returns no projected snapshot, does not mutate the input snapshot, and does not create a schema registry. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgSchemaProperty` | `attribute` | `name: String`, `field: RtgSchemaField` | One entry in a logical unique-key property map. Realization codecs may encode the entry collection as a JSON object. |
| `RtgSchemaField` | `attribute` | `required: Boolean`, `valueKinds[1..*]: RtgSchemaValueKind`, `properties[0..*]: RtgSchemaProperty`, `items[0..1]: RtgSchemaField`, `allowedValues[0..*]: JsonScalar`, `format[0..1]: RtgSchemaStringFormat`, `minimum[0..1]: Real`, `maximum[0..1]: Real`, `pattern[0..1]: String` | Recursive field schema. Allowed value kinds, allowed scalar values, and property names are unique unordered sets. Properties is non-empty only when object is allowed; items is present only when list is allowed. Optional format and pattern refine strings, while inclusive minimum/maximum refine numbers. |
| `RtgSchemaPayload` | `attribute` | — | One native anchor, data-object, or link schema payload selected by definition kind. |
| `RtgAnchorSchemaPayload` | `attribute` | `requiredDataTypes[0..*]: String`, `optionalDataTypes[0..*]: String` | Required and optional type-key sets are individually unique and mutually disjoint. |
| `RtgDataObjectSchemaPayload` | `attribute` | `properties[0..*]: RtgSchemaProperty` | Strict unique-key property map; undeclared properties are invalid for validation consumers. Realization codecs may encode it as a JSON object. |
| `RtgLinkSchemaPayload` | `attribute` | `allowedSourceTypes[1..*]: String`, `allowedTargetTypes[1..*]: String`, `linkKind[0..1]: RtgSchemaLinkKind` | Each endpoint set is unique and unordered. One type may occur in both sets. New and stored link definitions require linkKind; omission is representable only for explicit legacy-snapshot retrofit. |
| `RtgIdentityCriterion` | `attribute` | `criterionKey: String`, `propertyPaths[1..*]: String`, `matchStrategy: RtgSchemaIdentityMatchStrategy`, `scope: RtgSchemaIdentityScope` | A stable named same-type identity rule over one or more unique logical property paths. |
| `RtgSchemaDefinition` | `item` | `uuid[0..1]: Uuid`, `kind: RtgSchemaDefinitionKind`, `typeKey: String`, `description: String`, `payload: RtgSchemaPayload`, `timeShape[0..1]: RtgSchemaTimeShape`, `identityCriteria[0..*]: RtgIdentityCriterion`, `system: JsonObject` | UUID may be absent on write only. Description is non-empty human-readable semantic text. Anchor and data-object definitions require timeShape; links prohibit it. Identity criteria are optional for nodes and prohibited for links. Stored definitions have concrete UUID and Boolean system.live, defaulting missing live to true. |
| `RtgSchemaSnapshot` | `attribute` | `definitions[0..*] ordered: RtgSchemaDefinition` | Defined by its typed fields and action requirements. |
| `RtgSchemaDefinitionList` | `attribute` | `definitions[0..*] ordered: RtgSchemaDefinition` | Defined by its typed fields and action requirements. |
| `RtgSchemaAssociatedDataTypeList` | `attribute` | `requiredDataTypes[0..*] ordered: String`, `optionalDataTypes[0..*] ordered: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaLinkParticipation` | `attribute` | `definitionUuid: Uuid`, `typeKey: String`, `direction: RtgSchemaParticipationDirection`, `allowedSourceTypes[0..*] ordered: String`, `allowedTargetTypes[0..*] ordered: String`, `live: Boolean` | Defined by its typed fields and action requirements. |
| `RtgSchemaLinkParticipationList` | `attribute` | `links[0..*] ordered: RtgSchemaLinkParticipation` | Defined by its typed fields and action requirements. |
| `RtgSchemaAnchorTypeSummary` | `attribute` | `definitionUuid: Uuid`, `typeKey: String`, `description: String`, `live: Boolean` | Defined by its typed fields and action requirements. |
| `RtgSchemaAnchorTypeSummaryList` | `attribute` | `anchorTypes[0..*] ordered: RtgSchemaAnchorTypeSummary` | Defined by its typed fields and action requirements. |
| `RtgSchemaPack` | `attribute` | `anchorSchemas[0..*] ordered: RtgSchemaDefinition`, `associatedDataObjectSchemas[0..*] ordered: RtgSchemaDefinition`, `linkSchemas[0..*] ordered: RtgSchemaDefinition` | Defined by its typed fields and action requirements. |
| `RtgSchemaDeleteResult` | `attribute` | `deletedDefinition: RtgSchemaDefinition` | Defined by its typed fields and action requirements. |
| `RtgSchemaLinkKindRetrofitEntry` | `attribute` | `definitionUuid: Uuid`, `typeKey: String`, `linkKind: RtgSchemaLinkKind` | Defined by its typed fields and action requirements. |
| `RtgSchemaLinkKindRetrofitReport` | `attribute` | `defaultedLinkDefinitions[0..*] ordered: RtgSchemaLinkKindRetrofitEntry` | Defined by its typed fields and action requirements. |
| `RtgSchemaLinkKindRetrofitResult` | `attribute` | `snapshot: RtgSchemaSnapshot`, `report: RtgSchemaLinkKindRetrofitReport` | Defined by its typed fields and action requirements. |
| `RtgSchemaDefinitionNotFound` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaSnapshotInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaUuidInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaUuidConflict` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaDefinitionInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaPayloadInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaDefinitionKindInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaTypeKeyInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaDirectionInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaSystemValueInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaLiveTypeConflict` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| `RtgSchemaDefinitionKind` | `anchor`, `data_object`, `link` |
| `RtgSchemaParticipationQueryDirection` | `source`, `target`, `either` |
| `RtgSchemaParticipationDirection` | `source`, `target`, `both` |
| `RtgSchemaValueKind` | `string`, `integer`, `number`, `boolean`, `null`, `object`, `list`, `uuid` |
| `RtgSchemaStringFormat` | `date`, `date_time`, `uri` |
| `RtgSchemaTimeShape` | `state_now`, `state_as_of`, `event` |
| `RtgSchemaIdentityMatchStrategy` | `exact`, `normalized`, `composite` |
| `RtgSchemaIdentityScope` | `same_type` |
| `RtgSchemaLinkKind` | `semantic`, `structural`, `governance`, `provenance`, `versioning`, `junction` |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `PutSchemaDefinitionContractVerification` | `PutSchemaDefinition` | `definitionWriteEffect`, `putSchemaDefinitionFailureSemantics` | `components/rtg/schema/tests/test_rtg_schema_contract.py#PutSchemaDefinitionContractVerification` |
| `DeleteSchemaDefinitionContractVerification` | `DeleteSchemaDefinition` | `schemaDeleteEffect`, `deleteSchemaDefinitionFailureSemantics` | `components/rtg/schema/tests/test_rtg_schema_contract.py#DeleteSchemaDefinitionContractVerification` |
| `ExportSchemaSnapshotContractVerification` | `ExportSchemaSnapshot` | `exportSchemaSnapshotFailureSemantics` | `components/rtg/schema/tests/test_rtg_schema_contract.py#ExportSchemaSnapshotContractVerification` |
| `GetSchemaDefinitionContractVerification` | `GetSchemaDefinition` | `getSchemaDefinitionFailureSemantics` | `components/rtg/schema/tests/test_rtg_schema_contract.py#GetSchemaDefinitionContractVerification` |
| `ListSchemaDefinitionsContractVerification` | `ListSchemaDefinitions` | `listSchemaDefinitionsFailureSemantics` | `components/rtg/schema/tests/test_rtg_schema_contract.py#ListSchemaDefinitionsContractVerification` |
| `ListDefinitionsByTypeKeyContractVerification` | `ListDefinitionsByTypeKey` | `listDefinitionsByTypeKeyFailureSemantics` | `components/rtg/schema/tests/test_rtg_schema_contract.py#ListDefinitionsByTypeKeyContractVerification` |
| `ListAnchorDataTypeKeysContractVerification` | `ListAnchorDataTypeKeys` | `listAnchorDataTypeKeysFailureSemantics` | `components/rtg/schema/tests/test_rtg_schema_contract.py#ListAnchorDataTypeKeysContractVerification` |
| `ListLinkParticipationContractVerification` | `ListLinkParticipation` | `listLinkParticipationFailureSemantics` | `components/rtg/schema/tests/test_rtg_schema_contract.py#ListLinkParticipationContractVerification` |
| `ListAnchorTypeSummariesContractVerification` | `ListAnchorTypeSummaries` | `listAnchorTypeSummariesFailureSemantics` | `components/rtg/schema/tests/test_rtg_schema_contract.py#ListAnchorTypeSummariesContractVerification` |
| `GetSchemaPackContractVerification` | `GetSchemaPack` | `getSchemaPackFailureSemantics` | `components/rtg/schema/tests/test_rtg_schema_contract.py#GetSchemaPackContractVerification` |
| `CreateEmptyRtgSchemaContractVerification` | `CreateEmptyRtgSchema` | `createEmptyRtgSchemaFailureSemantics` | `components/rtg/schema/tests/test_rtg_schema_contract.py#CreateEmptyRtgSchemaContractVerification` |
| `ImportRtgSchemaSnapshotContractVerification` | `ImportRtgSchemaSnapshot` | `importRtgSchemaSnapshotFailureSemantics` | `components/rtg/schema/tests/test_rtg_schema_contract.py#ImportRtgSchemaSnapshotContractVerification` |
| `RetrofitSchemaSnapshotLinkKindsContractVerification` | `RetrofitSchemaSnapshotLinkKinds` | `linkKindRetrofitSemantics`, `retrofitSchemaSnapshotLinkKindsFailureSemantics` | `components/rtg/schema/tests/test_rtg_schema_contract.py#RetrofitSchemaSnapshotLinkKindsContractVerification` |
| `RtgSchemaBoundaryVerification` | `RtgSchema` | `fieldSemantics`, `payloadSemantics`, `kernelMetaModelSemantics`, `schemaReadEffect`, `canonicalOrdering`, `intentionalBoundary`, `schemaSnapshotEffect`, `uuidUnique`, `liveTypeUnique`, `liveStatusBoolean`, `noChangeSetOwnership`, `noObjectValidation`, `nativePayloads`, `noInheritanceCompositionV1`, `typeKeyChangesAreMigrationConcerns`, `schemaEvolutionOpsExternal`, `destructiveChangesAreMigrationConcerns`, `navigationIndexesMatchPayloads`, `deterministicListOrdering` | `components/rtg/schema/tests/test_rtg_schema_contract.py#RtgSchemaBoundaryVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
