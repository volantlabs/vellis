# component.rtg.schema

Generated from textual SysML v2 by `just model-render`; do not edit by hand.

- Model definition: `RtgSchema`
- Lifecycle: `accepted`
- Purpose: Own RTG-native schema definitions and derived navigation indexes, not object validation, graph state, migration membership, or cutover policy.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `exportSnapshot` | `ExportSchemaSnapshot` | out `snapshot: RtgSchemaSnapshot` | None | Export every full definition with normalized live metadata without mutation or filtering. |
| `putDefinition` | `PutSchemaDefinition` | in `definition: RtgSchemaDefinition`; out `stored: RtgSchemaDefinition` | `RtgSchemaUuidInvalid`, `RtgSchemaUuidConflict`, `RtgSchemaDefinitionInvalid`, `RtgSchemaSystemValueInvalid`, `RtgSchemaLiveTypeConflict` | Generate or preserve identity, validate kind-specific payload, and atomically create or fully replace one definition. |
| `getDefinition` | `GetSchemaDefinition` | in `definitionUuid: Uuid`; out `definition: RtgSchemaDefinition` | `RtgSchemaDefinitionNotFound` | Return one definition by UUID. |
| `listDefinitions` | `ListSchemaDefinitions` | in `kind: RtgSchemaDefinitionKind[0..1]`; in `live: Boolean[0..1]`; out `result: RtgSchemaDefinitionList` | `RtgSchemaDefinitionKindInvalid` | List definitions with optional kind and live filters in deterministic order. |
| `listDefinitionsByTypeKey` | `ListDefinitionsByTypeKey` | in `schemaTypeKey: String`; in `kind: RtgSchemaDefinitionKind[0..1]`; in `live: Boolean[0..1]`; out `result: RtgSchemaDefinitionList` | `RtgSchemaTypeKeyInvalid`, `RtgSchemaDefinitionKindInvalid` | List every definition for one type key with optional kind/live filters, including multiple non-live candidates. |
| `listAnchorDataTypeKeys` | `ListAnchorDataTypeKeys` | in `anchorTypeKey: String`; in `live: Boolean[0..1]` = `true`; out `result: RtgSchemaAssociatedDataTypeList` | `RtgSchemaTypeKeyInvalid`, `RtgSchemaDefinitionNotFound` | Return required and optional associated data type keys declared by one anchor schema. |
| `listLinkParticipation` | `ListLinkParticipation` | in `typeKey: String`; in `direction: RtgSchemaDirection` = `RtgSchemaDirection::either`; in `live: Boolean[0..1]` = `true`; out `result: RtgSchemaLinkParticipationList` | `RtgSchemaTypeKeyInvalid`, `RtgSchemaDirectionInvalid` | Return link schemas that admit the type as source, target, or either endpoint. |
| `listAnchorTypeSummaries` | `ListAnchorTypeSummaries` | in `live: Boolean[0..1]` = `true`; out `result: RtgSchemaAnchorTypeSummaryList` | None | Return anchor type identities and descriptions only, never graph counts. |
| `getSchemaPack` | `GetSchemaPack` | in `anchorTypeKeys: String[1..*]`; in `live: Boolean[0..1]` = `true`; out `result: RtgSchemaPack` | `RtgSchemaTypeKeyInvalid`, `RtgSchemaDefinitionNotFound` | Expand requested anchor schemas with defined associated-data schemas and participating link schemas; omit missing referenced schemas but fail missing requested anchors. |
| `deleteDefinition` | `DeleteSchemaDefinition` | in `definitionUuid: Uuid`; out `result: RtgSchemaDeleteResult` | `RtgSchemaDefinitionNotFound` | Delete exactly one definition and no graph, constraint, or migration record. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `CreateEmptyRtgSchema` | out `schema: RtgSchema` | None | Return an empty registry with empty derived indexes. |
| `ImportRtgSchemaSnapshot` | in `snapshot: RtgSchemaSnapshot`; out `schema: RtgSchema` | `RtgSchemaSnapshotInvalid`, `RtgSchemaUuidInvalid`, `RtgSchemaUuidConflict`, `RtgSchemaReferenceInvalid`, `RtgSchemaDefinitionInvalid`, `RtgSchemaSystemValueInvalid`, `RtgSchemaLiveTypeConflict` | Validate every record, UUID, reference, payload, system value, and live uniqueness before rebuilding indexes and exposing the registry. |

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
| `contract.rtg.schema.write_effect` | `PutSchemaDefinition` | `schema.putDefinition` | Missing UUID generates a new UUID; supplied identity is preserved. Missing system.live becomes true. Kind selects the exact payload family and at most one live definition owns a kind/type-key pair. |
| `contract.rtg.schema.field_semantics` | `RtgSchema` | `schema` | A field has a non-empty ordered value-kind set. Nested properties are permitted only with object, items only with list, null is permitted only when explicitly listed, required fields must be present, and strict data-object payloads reject undeclared properties. |
| `contract.rtg.schema.payload_semantics` | `RtgSchema` | `schema` | Anchor payloads distinguish required from optional associated data types; data-object payloads map property names to recursive field definitions; link payloads contain non-empty allowed source and target type-key sets. Kind and payload family must agree. |
| `contract.rtg.schema.read_effect` | `RtgSchema` | `schema` | Reads are deterministic, derive only from definitions and indexes, honor explicit filters/defaults, never inspect graph state, and never mutate. |
| `contract.rtg.schema.delete_effect` | `DeleteSchemaDefinition` | `schema.deleteDefinition` | Delete removes only one definition and its derived entries; it performs no safety decision or cross-component cascade. |
| `contract.rtg.schema.snapshot_effect` | `RtgSchema` | `schema` | Snapshot round-trip preserves full records and normalized live state; import validates the whole candidate before visibility. |
| `invariant.rtg.schema.uuid_unique` | `RtgSchema` | `schema` | Definition UUIDs are unique. |
| `invariant.rtg.schema.live_type_unique` | `RtgSchema` | `schema` | At most one live definition owns a kind/type-key pair. |
| `invariant.rtg.schema.live_status_boolean` | `RtgSchema` | `schema` | Missing live normalizes to true and supplied live is Boolean. |
| `invariant.rtg.schema.no_change_set_ownership` | `RtgSchema` | `schema` | Schema owns no change batches or migration membership. |
| `invariant.rtg.schema.no_object_validation` | `RtgSchema` | `schema` | Schema stores definitions but does not validate graph objects. |
| `invariant.rtg.schema.native_payloads` | `RtgSchema` | `schema` | Payloads use anchor, data-object, field, and link concepts rather than storage-engine schemas. |
| `invariant.rtg.schema.no_inheritance_composition_v1` | `RtgSchema` | `schema` | V1 defines no inheritance or composition semantics. |
| `invariant.rtg.schema.type_key_changes_are_migration_concerns` | `RtgSchema` | `schema` | Type-key lifecycle changes are coordinated outside the store. |
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

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgSchemaField` | `attribute` | `required: Boolean`, `valueKinds[1..*]: RtgSchemaValueKind`, `properties: JsonObject`, `items[0..1]: JsonObject` | Field schema. Properties describes nested fields only for object values; items describes the item field only for list values. |
| `RtgSchemaPayload` | `attribute` | — | One native anchor, data-object, or link schema payload selected by definition kind. |
| `RtgAnchorSchemaPayload` | `attribute` | `requiredDataTypes[0..*]: String`, `optionalDataTypes[0..*]: String` | Defined by its typed fields and action requirements. |
| `RtgDataObjectSchemaPayload` | `attribute` | `properties: JsonObject` | Strict mapping from property name to RtgSchemaField; undeclared properties are invalid for validation consumers. |
| `RtgLinkSchemaPayload` | `attribute` | `allowedSourceTypes[1..*]: String`, `allowedTargetTypes[1..*]: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaDefinition` | `item` | `uuid[0..1]: Uuid`, `kind: RtgSchemaDefinitionKind`, `typeKey: String`, `description: String`, `payload: RtgSchemaPayload`, `system: JsonObject` | UUID may be absent on write only. Stored definitions have concrete UUID and Boolean system.live, defaulting missing live to true. |
| `RtgSchemaSnapshot` | `attribute` | `definitions[0..*]: RtgSchemaDefinition` | Defined by its typed fields and action requirements. |
| `RtgSchemaDefinitionList` | `attribute` | `definitions[0..*]: RtgSchemaDefinition` | Defined by its typed fields and action requirements. |
| `RtgSchemaAssociatedDataTypeList` | `attribute` | `requiredDataTypes[0..*]: String`, `optionalDataTypes[0..*]: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaLinkParticipation` | `attribute` | `definitionUuid: Uuid`, `typeKey: String`, `direction: RtgSchemaDirection`, `allowedSourceTypes[0..*]: String`, `allowedTargetTypes[0..*]: String`, `live: Boolean` | Defined by its typed fields and action requirements. |
| `RtgSchemaLinkParticipationList` | `attribute` | `links[0..*]: RtgSchemaLinkParticipation` | Defined by its typed fields and action requirements. |
| `RtgSchemaAnchorTypeSummary` | `attribute` | `definitionUuid: Uuid`, `typeKey: String`, `description: String`, `live: Boolean` | Defined by its typed fields and action requirements. |
| `RtgSchemaAnchorTypeSummaryList` | `attribute` | `anchorTypes[0..*]: RtgSchemaAnchorTypeSummary` | Defined by its typed fields and action requirements. |
| `RtgSchemaPack` | `attribute` | `anchorSchemas[0..*]: RtgSchemaDefinition`, `associatedDataObjectSchemas[0..*]: RtgSchemaDefinition`, `linkSchemas[0..*]: RtgSchemaDefinition` | Defined by its typed fields and action requirements. |
| `RtgSchemaDeleteResult` | `attribute` | `deletedDefinition: RtgSchemaDefinition` | Defined by its typed fields and action requirements. |
| `RtgSchemaDefinitionNotFound` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaSnapshotInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaUuidInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaUuidConflict` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaReferenceInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaDefinitionInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaDefinitionKindInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaTypeKeyInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaDirectionInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaSystemValueInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgSchemaLiveTypeConflict` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| `RtgSchemaDefinitionKind` | `anchor`, `data_object`, `link` |
| `RtgSchemaDirection` | `source`, `target`, `either` |
| `RtgSchemaValueKind` | `string`, `integer`, `number`, `boolean`, `null`, `object`, `list`, `uuid` |

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
| `RtgSchemaBoundaryVerification` | `RtgSchema` | `fieldSemantics`, `payloadSemantics`, `schemaReadEffect`, `schemaSnapshotEffect`, `uuidUnique`, `liveTypeUnique`, `liveStatusBoolean`, `noChangeSetOwnership`, `noObjectValidation`, `nativePayloads`, `noInheritanceCompositionV1`, `typeKeyChangesAreMigrationConcerns`, `navigationIndexesMatchPayloads`, `deterministicListOrdering` | `components/rtg/schema/tests/test_rtg_schema_contract.py#RtgSchemaBoundaryVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
