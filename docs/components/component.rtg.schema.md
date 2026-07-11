---
id: component.rtg.schema
type: Component
status: accepted
owner: humans
model: model/bibliotek/components/component.rtg.schema.sysml
code:
  roots:
    - components/rtg/schema
---

# RTG Schema

## Purpose

Provide a schema-definition store for RTG-native object-level integrity definitions.

The component owns the in-memory definition network that higher-level validation, migration, editing, publication, and discovery operations consume. It is intentionally parallel to `component.rtg.graph`: graph stores active human/agent modeling content, while schema stores subsystem definition records. Schema definitions describe valid RTG anchors, data objects, and links, but this component does not execute validation against graph data.

## Responsibilities

- Represent schema definitions as stable definition records identified by UUID.
- Support the v1 definition kinds `anchor`, `data_object`, and `link`.
- Store a globally unique `type_key` for each live schema definition across all definition kinds.
- Store a plain-language semantic description on each schema definition for agent-facing type discovery.
- Store RTG-native definition payloads rather than JSON Schema or external schema-language payloads.
- Define anchor schemas with required and optional associated data object type keys.
- Define data object schemas with explicit property definitions.
- Define link schemas with allowed source and target type-key sets for anchors or data objects.
- Store a JSON-serializable `system` property store on every definition.
- Normalize missing `system.live` values to `true` and reject non-boolean `system.live` values.
- Store live and non-live schema definitions in the same registry.
- Maintain canonical UUID-to-definition maps.
- Maintain derived indexes for lookup by definition kind, schema type key, anchor-associated data type, and link participation.
- Enforce UUID uniqueness across definitions.
- Enforce structural integrity of RTG-native schema definition records as registry data.
- Generate definition UUIDs for new definitions, and accept caller-supplied UUIDs for special cases such as importing or relinking existing definitions.
- Provide full-record write operations for definitions.
- Provide read operations for direct lookup, listing by kind, listing by schema type key, anchor-associated data type, and link participation.
- Provide read operations that let callers discover all anchor type keys with semantic descriptions.
- Provide read operations that return expanded schema packs for selected anchor types.
- Provide schema snapshot import and export for callers that own persistence, replay, migration, testing, or storage adapters.

## Non-responsibilities

- Does not own schema change sets, migration plans, cutover plans, or publication workflow.
- Does not decide which non-live definitions participate in a migration.
- Does not validate RTG anchors, data objects, or links against schema definitions.
- Does not validate proposed graph data for addition to the live graph.
- Does not enforce multi-object constraints or graph-pattern rules.
- Does not apply object changes to `component.rtg.graph`.
- Does not inspect live RTG graph contents.
- Does not decide whether existing graph data is compatible with a schema change.
- Does not own curated discovery views, discovery grids, search ranking, or graph population counts.
- Does not allow inheritance or composition semantics in v1 schema definitions.
- Does not define or validate component-owned `system` metadata beyond preserving schema record `system.live`.
- Does not own type-key changes as in-place edits; type-key replacement is a migration workflow coordinated above this component.
- Does not provide generic schema definition links in v1.
- Does not own durable persistence, audit history, authorization, UI workflow, migration execution, or distributed coordination.
- Does not provide a general-purpose schema query language, inference engine, ontology reasoner, or migration orchestrator.

## Provided contracts

### `RtgSchema.empty`

Kind:

- function

Inputs:

- None.

Outputs:

- `RtgSchema`

Errors:

- None.

Semantics:

- Returns an empty in-memory schema registry with no definitions or derived indexes.
- The returned registry owns its in-memory definition maps and derived indexes.

### `RtgSchema.import_snapshot`

Kind:

- function

Inputs:

- `RtgSchemaSnapshot`

Outputs:

- `RtgSchema`

Errors:

- `RtgSchemaSnapshotInvalid`
- `RtgSchemaUuidInvalid`
- `RtgSchemaUuidConflict`
- `RtgSchemaReferenceInvalid`
- `RtgSchemaDefinitionInvalid`
- `RtgSchemaSystemValueInvalid`
- `RtgSchemaLiveTypeConflict`

Semantics:

- Builds an in-memory schema registry from a JSON-serializable snapshot containing definitions.
- Validates global UUID uniqueness across definitions.
- Normalizes missing `system.live` values to `true`.
- Validates that every resulting record `system.live` value is boolean.
- Validates that each live schema type key has at most one live definition for the same definition kind.
- Validates that each live schema type key belongs to at most one live definition across all definition kinds.
- Rebuilds all derived indexes from canonical record maps.
- Does not validate RTG graph objects against the imported definitions.

### `RtgSchema.export_snapshot`

Kind:

- function

Inputs:

- None.

Outputs:

- `RtgSchemaSnapshot`

Errors:

- None.

Semantics:

- Returns a JSON-serializable snapshot of the current in-memory schema registry state.
- The snapshot preserves definition UUIDs, definition kinds, schema type keys, definition payloads, and system metadata.
- Exported records always include a boolean `system.live` value after normalization.
- The snapshot contains enough information to reconstruct an equivalent schema registry through `RtgSchema.import_snapshot`.
- Export does not validate graph objects, query graph contents, or filter definitions by consumer visibility.

### `RtgSchema.put_definition`

Kind:

- function

Inputs:

- `definition`

Outputs:

- `RtgSchemaDefinition`

Errors:

- `RtgSchemaUuidInvalid`
- `RtgSchemaUuidConflict`
- `RtgSchemaDefinitionInvalid`
- `RtgSchemaSystemValueInvalid`
- `RtgSchemaLiveTypeConflict`

Semantics:

- Creates a new definition or fully replaces the kind, schema type key, payload, and system metadata of an existing definition with the same UUID.
- When `definition.uuid` is omitted, the component generates a new unique UUID and creates the definition.
- When `definition.uuid` is supplied, the component uses it unchanged to create or fully replace that definition, which supports import and relinking workflows.
- `definition.kind` must be one of `anchor`, `data_object`, or `link` in v1.
- `definition.description` must be a non-empty plain-language semantic description.
- `definition.payload` must match the RTG-native payload shape required for the definition kind.
- Missing `definition.system.live` defaults to `true`; supplied `definition.system.live` must be boolean.
- A live definition must not conflict with another live definition for the same schema type key across any definition kind.
- Non-live definitions may share a definition kind and schema type key with live or other non-live definitions.
- Object maps and derived indexes are updated atomically with the definition record.
- The write does not validate, migrate, or rewrite RTG graph objects.
- Replacing the type key of a live definition is not a normal in-place edit for controller consumers; controller-level type changes must be modeled as migrations.

### `RtgSchema.get_definition`

Kind:

- function

Inputs:

- `definition_uuid`

Outputs:

- `RtgSchemaDefinition`

Errors:

- `RtgSchemaDefinitionNotFound`

Semantics:

- Returns one definition by UUID.
- The returned definition describes schema registry data only and is not a validation result for any graph object.

### `RtgSchema.list_definitions`

Kind:

- function

Inputs:

- `kind | None`
- `live | None`

Outputs:

- `RtgSchemaDefinitionList`

Errors:

- `RtgSchemaDefinitionKindInvalid`

Semantics:

- Lists definitions, optionally filtered by definition kind and live status.
- Results are stable schema records for consumers to interpret outside this component.

### `RtgSchema.list_definitions_by_type_key`

Kind:

- function

Inputs:

- `schema_type_key`
- `kind | None`
- `live | None`

Outputs:

- `RtgSchemaDefinitionList`

Errors:

- `RtgSchemaTypeKeyInvalid`
- `RtgSchemaDefinitionKindInvalid`

Semantics:

- Lists definitions matching a schema type key, optionally filtered by definition kind and live status.
- The result may include multiple non-live candidate definitions for the same kind and schema type key.

### `RtgSchema.list_anchor_data_type_keys`

Kind:

- function

Inputs:

- `anchor_type_key`
- `live | None`

Outputs:

- `RtgSchemaAssociatedDataTypeList`

Errors:

- `RtgSchemaTypeKeyInvalid`
- `RtgSchemaDefinitionNotFound`

Semantics:

- Returns the required and optional data object type keys declared by one anchor schema.
- Reads the anchor schema payload and derived anchor-associated-data index.
- Does not inspect graph objects to determine whether associations exist.

### `RtgSchema.list_link_participation`

Kind:

- function

Inputs:

- `type_key`
- `direction`
- `live | None`

Outputs:

- `RtgSchemaLinkParticipationList`

Errors:

- `RtgSchemaTypeKeyInvalid`
- `RtgSchemaDirectionInvalid`

Semantics:

- Returns link schema definitions where `type_key` appears in allowed source types, allowed target types, or either endpoint depending on `direction`.
- `direction` is one of `source`, `target`, or `either`; `either` returns definitions where `type_key` is an allowed source or target. Any other value is rejected as `RtgSchemaDirectionInvalid`.
- Supports controller schema-pack assembly and low-level discovery without generic schema definition links.
- Does not inspect graph links.

### `RtgSchema.list_anchor_type_summaries`

Kind:

- function

Inputs:

- `live | None`

Outputs:

- `RtgSchemaAnchorTypeSummaryList`

Errors:

- None.

Semantics:

- Lists anchor schema type keys and semantic descriptions.
- Results are schema metadata only and do not include graph population counts.
- This contract supports basic controller-owned discovery without requiring a separate discovery component.

### `RtgSchema.get_schema_pack`

Kind:

- function

Inputs:

- `anchor_type_keys`
- `live | None`

Outputs:

- `RtgSchemaPack`

Errors:

- `RtgSchemaTypeKeyInvalid`
- `RtgSchemaDefinitionNotFound`

Semantics:

- Returns expanded schema details for selected anchor type keys.
- Includes each selected anchor schema, its required and optional associated data object schemas, and link schemas where the selected anchor type is allowed as a source or target.
- `RtgSchemaDefinitionNotFound` is raised only when a requested `anchor_type_keys` entry has no matching definition; referenced associated-data or link type keys that have no defined schema are omitted from the pack rather than raising.
- Uses schema-owned indexes over anchor-associated data type keys and link source/target participation.
- The pack is schema-only; graph counts, query planning, curated discovery views, and authorization are outside this component.

### `RtgSchema.delete_definition`

Kind:

- function

Inputs:

- `definition_uuid`

Outputs:

- `RtgSchemaDeleteResult`

Errors:

- `RtgSchemaDefinitionNotFound`

Semantics:

- Deletes a definition from the schema registry.
- Does not delete or alter RTG graph objects.
- Does not decide whether deletion is safe for live graph data.

### `RtgSchemaDeleteResult`

Kind:

- data structure

Fields:

- `deleted_definition`

Semantics:

- Represents the outcome of a schema definition delete.
- `deleted_definition` contains the full schema definition record that was removed.
- This component does not cascade deletes into graph, constraint, or migration records, so the result reports only the removed definition.

### `RtgSchemaSnapshot`

Kind:

- data structure

Fields:

- `definitions`

Semantics:

- JSON-serializable schema registry snapshot.
- `definitions` contains full schema definition records with concrete UUIDs.
- Import validates the records and rebuilds derived indexes from them.

### `RtgSchemaDefinition`

Kind:

- data structure

Fields:

- `uuid`
- `kind`
- `type_key`
- `description`
- `payload`
- `system`

Semantics:

- Represents one RTG-native schema definition.
- `uuid` identifies the definition and may be omitted on write, in which case the component generates one.
- Returned, stored, deleted-result, and snapshot schema definition records always contain a concrete UUID.
- `kind` is `anchor`, `data_object`, or `link` in v1.
- `type_key` is the type string used by RTG graph objects and is globally unique among live schema definitions.
- `description` is a plain-language semantic description intended for humans and agents.
- `payload` is interpreted according to `kind`.
- `system.live` is component metadata, not a user-designable schema field.

### `RtgAnchorSchemaPayload`

Kind:

- data structure

Fields:

- `required_data_types`
- `optional_data_types`

Semantics:

- Describes which data object type keys may be directly associated with anchors of this type.
- `required_data_types` and `optional_data_types` distinguish ordinary integrity requirements from optional associations.
- Each `required_data_types` entry means an anchor of this type must have at least one directly associated data object of that type.
- Cardinality beyond required versus optional belongs in `component.rtg.constraints`.

### `RtgDataObjectSchemaPayload`

Kind:

- data structure

Fields:

- `properties`

Semantics:

- Describes valid data object properties for one data object type.
- `properties` maps property name to `RtgSchemaField` records.
- V1 data object schemas are strict: a data object is invalid when it contains properties not declared by its data object schema.
- Required properties must exist and must contain values valid for their field schemas.
- Optional properties may be omitted.
- Supported v1 value kinds are `string`, `integer`, `number`, `boolean`, `null`, `object`, `list`, and `uuid`.
- Required properties may be `null` only when the field schema explicitly allows `null`.
- Nested object schemas are allowed, but should remain an exceptional modeling choice because deeply nested domain data may indicate a missing RTG type.

### `RtgSchemaField`

Kind:

- data structure

Fields:

- `required`
- `value_kinds`
- `properties`
- `items`

Semantics:

- Describes one data object property field.
- `required` is a boolean that applies to the field in its containing object.
- `value_kinds` is a non-empty ordered list containing supported v1 value kinds: `string`, `integer`, `number`, `boolean`, `null`, `object`, `list`, or `uuid`.
- `properties` is present only when `object` is in `value_kinds` and maps nested property names to `RtgSchemaField` records.
- `items` is present only when `list` is in `value_kinds` and describes list item values.
- A field allows `null` only when `null` appears in `value_kinds`.
- Validation consumers reject a value when its kind is not included in `value_kinds`.

### `RtgLinkSchemaPayload`

Kind:

- data structure

Fields:

- `allowed_source_types`
- `allowed_target_types`

Semantics:

- Describes the anchor or data object type keys that may be used as source and target endpoints for a link type.
- Link schemas may allow anchor endpoints, data object endpoints, or both.

### `RtgSchemaPack`

Kind:

- data structure

Fields:

- `anchor_schemas`
- `associated_data_object_schemas`
- `link_schemas`

Semantics:

- Expanded, schema-only detail for selected anchor type keys.
- `anchor_schemas` contains each selected anchor `RtgSchemaDefinition`.
- `associated_data_object_schemas` contains the required and optional data object `RtgSchemaDefinition` records for those anchors.
- `link_schemas` contains link `RtgSchemaDefinition` records where a selected anchor type is an allowed source or target.
- Contains no graph counts; population counts are added by controller-level discovery.
- List-valued schema outputs such as `RtgSchemaDefinitionList`, `RtgSchemaAssociatedDataTypeList`, `RtgSchemaLinkParticipationList`, and `RtgSchemaAnchorTypeSummaryList` are ordered lists of the corresponding element type.

### `RtgSchemaDefinitionList`

Kind:

- data structure

Fields:

- `definitions`

Semantics:

- Ordered list wrapper for schema definition records.
- `definitions` contains full `RtgSchemaDefinition` records with concrete UUIDs.

### `RtgSchemaAssociatedDataTypeList`

Kind:

- data structure

Fields:

- `required_data_types`
- `optional_data_types`

Semantics:

- Lists data object type keys declared by one anchor schema.
- `required_data_types` and `optional_data_types` are ordered lists of schema type keys.
- The result contains schema metadata only and does not prove that graph anchors currently satisfy those requirements.

### `RtgSchemaLinkParticipation`

Kind:

- data structure

Fields:

- `definition_uuid`
- `type_key`
- `direction`
- `allowed_source_types`
- `allowed_target_types`
- `live`

Semantics:

- Describes one link schema definition that mentions a queried type key.
- `direction` is `source`, `target`, or `both` relative to the queried type key.
- Source and target type lists are copied from the link schema payload.

### `RtgSchemaLinkParticipationList`

Kind:

- data structure

Fields:

- `links`

Semantics:

- Ordered list wrapper for `RtgSchemaLinkParticipation` records.

### `RtgSchemaAnchorTypeSummary`

Kind:

- data structure

Fields:

- `definition_uuid`
- `type_key`
- `description`
- `live`

Semantics:

- Describes one anchor schema type for discovery and schema-pack selection.
- Contains schema metadata only and no graph population counts.

### `RtgSchemaAnchorTypeSummaryList`

Kind:

- data structure

Fields:

- `anchor_types`

Semantics:

- Ordered list wrapper for `RtgSchemaAnchorTypeSummary` records.

## Required contracts

May consume:

- RTG object kind names and type-string conventions aligned with `component.rtg.graph`.
- JSON-serializable value conventions for snapshots, definition payloads, and system metadata.
- RTG-native schema payload conventions defined by this component.

Must not consume:

- Live graph storage internals from `component.rtg.graph`.
- RTG graph mutation APIs.
- Object validation components.
- Graph constraints components.
- Migration or publication components.
- Persistence, migration runner, UI, authorization, or runtime orchestration components.

## Related components

- `component.rtg.graph` owns live and non-live RTG graph object state while this component owns live and non-live schema definition state.
- `component.rtg.change_validation` may consume schema definition records to validate individual RTG objects.
- `component.rtg.constraints` owns semantic and network-level constraint definition records outside this component.
- `component.rtg.migration` owns the change-set records that identify which schema definitions, constraint definitions, and graph objects participate in a cutover.

## Owned state

- Schema definition records.
- Definition UUID namespace.
- Definition-kind indexes.
- Schema-type-key indexes.
- Anchor-associated-data type indexes.
- Link source/target participation indexes.

## Invariants

### `invariant.rtg.schema.uuid_unique`

Each UUID identifies at most one schema definition.

### `invariant.rtg.schema.live_type_unique`

At most one live definition exists for a given schema type key across all schema definition kinds.

### `invariant.rtg.schema.live_status_boolean`

Every definition has a boolean `system.live` value after normalization.

### `invariant.rtg.schema.no_change_set_ownership`

The component does not own migration change sets, publication plans, or readiness state.

### `invariant.rtg.schema.no_object_validation`

The component never reports whether an RTG graph object satisfies a schema definition.

### `invariant.rtg.schema.native_payloads`

Schema definition payloads use the RTG-native anchor, data object, and link definition model rather than JSON Schema or another external schema language.

### `invariant.rtg.schema.no_inheritance_composition_v1`

V1 schema definitions do not implement inheritance or composition semantics.

### `invariant.rtg.schema.type_key_changes_are_migration_concerns`

Type-key replacement is handled by migration workflows above this component rather than as an ordinary in-place schema edit.

### `invariant.rtg.schema.navigation_indexes_match_payloads`

Anchor-associated-data and link participation indexes match canonical schema definition payloads after every successful mutation and import.

### `invariant.rtg.schema.deterministic_list_ordering`

List and snapshot outputs are ordered deterministically for a given registry state, for example by UUID, so boundary tests can assert stable results.

## Verification

Required checks:

- Boundary tests for empty registry creation.
- Boundary tests for adding, replacing, retrieving, listing, exporting, and importing definitions.
- Boundary tests for UUID conflict rejection across definitions.
- Boundary tests proving writes without a supplied UUID receive a generated unique UUID, and writes with a supplied UUID use it unchanged.
- Boundary tests for `system.live` defaulting and boolean validation.
- Boundary tests proving multiple non-live definitions may share a kind and schema type key.
- Boundary tests proving conflicting live definitions for the same schema type key across different definition kinds are rejected.
- Boundary tests for RTG-native anchor, data object, and link payload validation.
- Boundary tests proving required associated data types mean at least one direct data object association of each required type.
- Boundary tests proving undeclared data object properties are rejected by schema/object validation consumers.
- Boundary tests proving anchor-associated-data and link participation indexes match schema payloads.
- Boundary tests for anchor type summaries and expanded schema packs.
- API-surface checks proving change-set, migration, publication, and object-validation contracts are not exposed by this component.

Required evidence:

- A consumer can store a live schema definition and a non-live replacement candidate with the same kind and schema type key.
- A consumer can list live definitions separately from non-live definitions.
- A consumer can retrieve all live anchor type keys with semantic descriptions.
- A consumer can retrieve a schema pack for selected anchor types without reading graph state.
- A consumer can list data object type keys associated with an anchor type.
- A consumer can list link schemas that participate with an anchor or data object type.
- The schema component does not accept RTG graph objects as validation inputs.
- The schema component does not expose migration change-set membership.

## Change rules

Agents may:

- Change private storage and indexing of definitions.
- Add schema definition fields when they remain definition data.
- Add boundary tests for registry behavior.
- Refactor internal snapshot import and export.

Agents may not:

- Add migration change-set APIs.
- Add object validation APIs.
- Add graph-wide constraint APIs.
- Add generic schema definition link APIs without explicit human approval.
- Add curated discovery view state.
- Add inheritance or composition semantics without explicit human approval.
- Read or mutate live RTG graph objects.
- Fold validator, constraints, migration, persistence, publication, or editor responsibilities into this component.
- Change accepted public contracts, owned state, invariants, or dependency rules without explicit human approval.

## Open questions

- None.
