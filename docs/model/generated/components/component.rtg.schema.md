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

| Action | State / collaborator | Modeled effect |
|---|---|---|
| `exportSnapshot` | `definitions` | read all canonical definitions. |
| `putDefinition` | `definitions` | atomically create/replace definition and rebuild affected indexes. |
| `getDefinition` | `definitions` | read one canonical definition. |
| `listDefinitions` | `navigationIndexes` | read kind/live indexes. |
| `listDefinitionsByTypeKey` | `navigationIndexes` | read type-key index. |
| `listAnchorDataTypeKeys` | `navigationIndexes` | read associated-data index. |
| `listLinkParticipation` | `navigationIndexes` | read source/target participation indexes. |
| `listAnchorTypeSummaries` | `navigationIndexes` | read anchor summary index. |
| `getSchemaPack` | `navigationIndexes` | assemble schema-only pack from canonical definitions and indexes. |
| `deleteDefinition` | `definitions` | remove one definition and affected indexes. |

## Invariants and behavioral obligations

| Stable ID | Modeled obligation |
|---|---|
| `contract.rtg.schema.write_effect` | Missing UUID generates a new UUID; supplied identity is preserved. Missing system.live becomes true. Kind selects the exact payload family and at most one live definition owns a kind/type-key pair. |
| `contract.rtg.schema.field_semantics` | A field has a non-empty ordered value-kind set. Nested properties are permitted only with object, items only with list, null is permitted only when explicitly listed, required fields must be present, and strict data-object payloads reject undeclared properties. |
| `contract.rtg.schema.payload_semantics` | Anchor payloads distinguish required from optional associated data types; data-object payloads map property names to recursive field definitions; link payloads contain non-empty allowed source and target type-key sets. Kind and payload family must agree. |
| `contract.rtg.schema.read_effect` | Reads are deterministic, derive only from definitions and indexes, honor explicit filters/defaults, never inspect graph state, and never mutate. |
| `contract.rtg.schema.delete_effect` | Delete removes only one definition and its derived entries; it performs no safety decision or cross-component cascade. |
| `contract.rtg.schema.snapshot_effect` | Snapshot round-trip preserves full records and normalized live state; import validates the whole candidate before visibility. |
| `invariant.rtg.schema.uuid_unique` | Definition UUIDs are unique. |
| `invariant.rtg.schema.live_type_unique` | At most one live definition owns a kind/type-key pair. |
| `invariant.rtg.schema.live_status_boolean` | Missing live normalizes to true and supplied live is Boolean. |
| `invariant.rtg.schema.no_change_set_ownership` | Schema owns no change batches or migration membership. |
| `invariant.rtg.schema.no_object_validation` | Schema stores definitions but does not validate graph objects. |
| `invariant.rtg.schema.native_payloads` | Payloads use anchor, data-object, field, and link concepts rather than storage-engine schemas. |
| `invariant.rtg.schema.no_inheritance_composition_v1` | V1 defines no inheritance or composition semantics. |
| `invariant.rtg.schema.type_key_changes_are_migration_concerns` | Type-key lifecycle changes are coordinated outside the store. |
| `invariant.rtg.schema.navigation_indexes_match_payloads` | Derived kind, type, live, associated-data, and link-participation indexes exactly match canonical payloads. |
| `invariant.rtg.schema.deterministic_list_ordering` | Public list results are deterministic for one registry state. |

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

| Enumeration | Model and external values |
|---|---|
| `RtgSchemaDefinitionKind` | `anchor`, `dataObject` → `data_object`, `link` |
| `RtgSchemaDirection` | `source`, `target`, `either` |
| `RtgSchemaValueKind` | `string`, `integer`, `number`, `boolean`, `nullValue` → `null`, `object`, `list`, `uuid` |

## Verification

| Verification | Objectives | Evidence |
|---|---|---|
| `RtgSchemaBoundaryVerification` | `definitionWriteEffect`, `fieldSemantics`, `payloadSemantics`, `schemaReadEffect`, `schemaDeleteEffect`, `schemaSnapshotEffect`, `uuidUnique`, `liveTypeUnique`, `liveStatusBoolean`, `noChangeSetOwnership`, `noObjectValidation`, `nativePayloads`, `noInheritanceCompositionV1`, `typeKeyChangesAreMigrationConcerns`, `navigationIndexesMatchPayloads`, `deterministicListOrdering` | `components/rtg/schema/tests/test_rtg_schema_contract.py` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
