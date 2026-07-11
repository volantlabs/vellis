---
id: component.rtg.graph
type: Component
status: accepted
owner: humans
model: model/bibliotek/components/component.rtg.graph.sysml
code:
  roots:
    - components/rtg/graph
---

# Reified Type Graph

## Purpose

Provide a schema-neutral in-memory graph-like model for stable ontological anchors, typed data objects, and typed links between graph objects.

The component owns the RTG object store that higher-level schema, query, persistence, ledger, discovery, and controller features build on. It stores both live and non-live objects and must not model its in-memory state as a property graph database merely because the RTG is graph-like. The graph stores active human/agent modeling content; subsystem records such as schema definitions, constraint definitions, migration records, and ledger events belong to their own components.

## Responsibilities

- Represent anchors as stable typed ontological objects identified by UUID.
- Store an optional anchor `display_name` for human and UI navigation.
- Represent data objects as typed JSON-serializable property stores identified by UUID and grounded by at least one anchor.
- Represent links as typed directed edges identified by UUID, with source and target UUIDs that resolve to anchors or data objects.
- Store a JSON-serializable `system` property store on every anchor, data object, and link.
- Normalize missing `system.live` values to `true` and reject non-boolean `system.live` values.
- Represent anchor-to-data association only through direct UUID indexes, not association objects, synthetic links, or LPG-style edges.
- Maintain canonical UUID-to-object maps for anchors, data objects, and links.
- Maintain a single global type namespace across anchors, data objects, and links.
- Maintain derived type-to-object UUID indexes.
- Maintain derived data-to-anchor and anchor-to-data UUID indexes.
- Maintain derived incident-link indexes from anchor or data UUID to link UUID.
- Enforce referential integrity for anchor-data indexes and link endpoints.
- Generate object UUIDs for new anchors, data objects, and links, and accept caller-supplied UUIDs for special cases such as importing or relinking existing data.
- Provide full-object write operations for anchors, data objects, and links.
- Provide mutation operations for associating, dissociating, and deleting graph objects without leaving dangling references or ungrounded data objects.
- Provide read operations for direct lookup by UUID, listing by type, listing anchor-data index entries, and listing links incident to an object.
- Provide non-mutating preview of delete and dissociation cascade effects using the same cascade logic as the mutating operations.
- Provide type count operations that can optionally count live or non-live records for discovery and system introspection.
- Provide graph snapshot import and export for callers that own persistence, replay, migration, testing, or storage adapters.

## Non-responsibilities

- Does not define the ontology, type taxonomy, schema language, or meaning of caller-supplied object types.
- Does not validate data object property stores against application-specific schemas.
- Does not validate graph deltas against schema definitions.
- Does not provide schema storage.
- Does not authorize who may supply explicit UUIDs; deciding when an explicit UUID is appropriate is a caller-level policy concern.
- Does not use links to model the association between anchors and data objects.
- Does not create, store, expose, or return anchor-data association objects.
- Does not require all links to connect only anchors; links may connect any existing anchor or data object unless a caller-level ontology forbids it.
- Does not make links endpoints for other links in this draft.
- Does not authenticate users or authorize access to graph objects.
- Does not own durable persistence, replay ledgers, time walking, auditing, replication, backup, or distributed coordination.
- Does not filter query results by lifecycle, `system.live`, visibility, user role, or publication state.
- Does not own fine-grained status management beyond defaulting, validating, and preserving the boolean `system.live` value.
- Does not decide whether non-live objects are valid migration candidates or tied to an active migration.
- Does not default reads to live-only; lifecycle filtering and user-facing query defaults are controller or query options.
- Does not compute display names from associated data objects.
- Does not provide a general-purpose graph query language, inference engine, reasoner, ontology editor, or migration orchestrator.
- Does not expose graph database primitives as its in-memory object model.
- Does not assign semantic meaning to arbitrary `system` keys beyond defaulting, validating, and preserving `system.live`.

## Provided contracts

### `RtgGraph.empty`

Kind:

- function

Inputs:

- None.

Outputs:

- `RtgGraph`

Errors:

- None.

Semantics:

- Returns a graph handle with no anchors, data objects, links, anchor-data index entries, or incident-link index entries.
- The returned graph owns its in-memory object maps and derived indexes.

### `RtgGraph.import_snapshot`

Kind:

- function

Inputs:

- `RtgGraphSnapshot`

Outputs:

- `RtgGraph`

Errors:

- `RtgGraphSnapshotInvalid`
- `RtgGraphUuidInvalid`
- `RtgGraphUuidConflict`
- `RtgGraphReferenceInvalid`
- `RtgGraphTypeInvalid`
- `RtgGraphTypeKindConflict`
- `RtgGraphJsonValueInvalid`
- `RtgGraphSystemValueInvalid`

Semantics:

- Builds an in-memory graph from a JSON-serializable snapshot containing anchors, data objects, links, and an anchor-to-data UUID index.
- Validates global UUID uniqueness across anchors, data objects, and links.
- Normalizes missing object `system.live` values to `true`.
- Validates that every resulting object `system.live` value is boolean.
- Validates that every type is well formed.
- Validates that each type belongs to only one object kind across the imported graph.
- Validates that every anchor-to-data index entry references an existing anchor and an existing data object.
- Validates that every data object is referenced by at least one anchor-to-data index entry.
- Validates that every link source and target resolves to an existing anchor or data object.
- Rejects links whose source or target resolves to another link.
- Rebuilds all derived indexes from canonical object maps and the imported anchor-to-data index.

### `RtgGraph.export_snapshot`

Kind:

- function

Inputs:

- None.

Outputs:

- `RtgGraphSnapshot`

Errors:

- None.

Semantics:

- Returns a JSON-serializable snapshot of the current in-memory graph state.
- The snapshot preserves object UUIDs, object types, anchor-to-data UUID index entries, link endpoints, data properties, and system metadata.
- Exported objects always include a boolean `system.live` value after normalization.
- The snapshot contains enough information to reconstruct an equivalent graph through `RtgGraph.import_snapshot`.
- Export does not filter by lifecycle, `system.live`, visibility, role, or publication state.

### `RtgGraph.put_anchor`

Kind:

- function

Inputs:

- `anchor`

Outputs:

- `RtgAnchor`

Errors:

- `RtgGraphUuidInvalid`
- `RtgGraphUuidConflict`
- `RtgGraphTypeInvalid`
- `RtgGraphTypeKindConflict`
- `RtgGraphSystemValueInvalid`

Semantics:

- Creates a new anchor or fully replaces the type and system metadata of an existing anchor with the same UUID.
- When `anchor.uuid` is omitted, the component generates a new unique UUID and creates the anchor.
- When `anchor.uuid` is supplied, the component uses it unchanged to create or fully replace that anchor, which supports import and relinking workflows.
- `anchor.uuid` must not identify a data object or link.
- `anchor.type` must be well formed.
- `anchor.type` must not already belong to the data object or link kind in the current graph.
- Missing `anchor.system.live` defaults to `true`; supplied `anchor.system.live` must be boolean.
- Updating an existing anchor preserves its data object associations and incident links.
- Object maps and derived indexes are updated atomically with the anchor record.

### `RtgGraph.put_data_object`

Kind:

- function

Inputs:

- `data_object`
- `anchor_uuids`

Outputs:

- `RtgDataObject`

Errors:

- `RtgGraphUuidInvalid`
- `RtgGraphUuidConflict`
- `RtgGraphAnchorNotFound`
- `RtgGraphTypeInvalid`
- `RtgGraphTypeKindConflict`
- `RtgGraphJsonValueInvalid`
- `RtgGraphSystemValueInvalid`

Semantics:

- Creates a new data object or fully replaces the type, property store, system metadata, and direct anchor associations of an existing data object with the same UUID.
- When `data_object.uuid` is omitted, the component generates a new unique UUID and creates the data object.
- When `data_object.uuid` is supplied, the component uses it unchanged to create or fully replace that data object, which supports import and relinking workflows.
- `data_object.uuid` must not identify an anchor or link.
- `data_object.type` must be well formed.
- `data_object.type` must not already belong to the anchor or link kind in the current graph.
- `data_object.properties` must be a JSON-serializable object.
- Missing `data_object.system.live` defaults to `true`; supplied `data_object.system.live` must be boolean.
- `anchor_uuids` must contain at least one existing anchor UUID.
- Replacing an existing data object's `anchor_uuids` replaces its direct anchor-data index entries.
- Replacing anchor-data index entries through this contract does not delete the data object, because the replacement must still leave it grounded by at least one anchor.
- Existing incident links for the data object are preserved.
- Object maps and derived indexes are updated atomically with the data object record and anchor-data indexes.

### `RtgGraph.put_link`

Kind:

- function

Inputs:

- `link`

Outputs:

- `RtgLink`

Errors:

- `RtgGraphUuidInvalid`
- `RtgGraphUuidConflict`
- `RtgGraphEndpointNotFound`
- `RtgGraphTypeInvalid`
- `RtgGraphTypeKindConflict`
- `RtgGraphSystemValueInvalid`

Semantics:

- Creates a new directed typed link or fully replaces the type, endpoints, and system metadata of an existing link with the same UUID.
- When `link.uuid` is omitted, the component generates a new unique UUID and creates the link.
- When `link.uuid` is supplied, the component uses it unchanged to create or fully replace that link, which supports import and relinking workflows.
- `link.uuid` must not identify an anchor or data object.
- `link.type` must be well formed.
- `link.type` must not already belong to the anchor or data object kind in the current graph.
- `link.source_uuid` and `link.target_uuid` must resolve to existing anchors or data objects.
- Links may point from an anchor to an anchor, anchor to data object, data object to anchor, or data object to data object.
- Links may not point to links.
- Missing `link.system.live` defaults to `true`; supplied `link.system.live` must be boolean.
- Object maps, type indexes, and incident-link indexes are updated atomically with the link record.

### `RtgGraph.associate_data`

Kind:

- function

Inputs:

- `anchor_uuid`
- `data_uuid`

Outputs:

- None.

Errors:

- `RtgGraphUuidInvalid`
- `RtgGraphAnchorNotFound`
- `RtgGraphDataObjectNotFound`

Semantics:

- Adds a direct index entry between an existing anchor and an existing data object.
- Repeating the same association is idempotent.
- The association is not represented as an object, link, edge, or metadata-bearing record.
- Anchor-to-data and data-to-anchor indexes are updated atomically.

### `RtgGraph.dissociate_data`

Kind:

- function

Inputs:

- `anchor_uuid`
- `data_uuid`

Outputs:

- `RtgGraphDeleteResult`

Errors:

- `RtgGraphUuidInvalid`
- `RtgGraphAnchorNotFound`
- `RtgGraphDataObjectNotFound`
- `RtgGraphAnchorDataIndexEntryNotFound`

Semantics:

- Removes the direct index entry between an existing anchor and an existing data object.
- The operation does not delete the anchor.
- If the data object has no remaining anchor associations after dissociation, the data object is also deleted.
- Links that reference a cascaded data object are also deleted.
- Anchor-to-data, data-to-anchor, type, object, and incident-link indexes are updated atomically.
- Returned delete result uses always-present lists; lists are empty when no object of that category was deleted.

### `RtgGraph.delete_anchor`

Kind:

- function

Inputs:

- `anchor_uuid`

Outputs:

- `RtgGraphDeleteResult`

Errors:

- `RtgGraphUuidInvalid`
- `RtgGraphAnchorNotFound`

Semantics:

- Deletes an existing anchor from the in-memory graph.
- Removes all direct index entries between the anchor and data objects.
- Deletes all links that reference the anchor as source or target.
- Deletes any data object that has no remaining anchor associations after the anchor is deleted.
- Preserves data objects associated with at least one other anchor, including data objects whose remaining anchors have `system.live` set to `false`.
- Deletes links that reference any cascaded data object.
- Object maps and all derived indexes are updated atomically.
- Returned delete result uses always-present lists.

### `RtgGraph.delete_data_object`

Kind:

- function

Inputs:

- `data_uuid`

Outputs:

- `RtgGraphDeleteResult`

Errors:

- `RtgGraphUuidInvalid`
- `RtgGraphDataObjectNotFound`

Semantics:

- Deletes an existing data object from the in-memory graph.
- Removes all direct index entries between the data object and anchors.
- Deletes all links that reference the data object as source or target.
- Does not delete associated anchors.
- Object maps and all derived indexes are updated atomically.
- Returned delete result uses always-present lists.

### `RtgGraph.delete_link`

Kind:

- function

Inputs:

- `link_uuid`

Outputs:

- `RtgGraphDeleteResult`

Errors:

- `RtgGraphUuidInvalid`
- `RtgGraphLinkNotFound`

Semantics:

- Deletes an existing link from the in-memory graph.
- Does not delete the link's source or target object.
- Object maps, type indexes, and incident-link indexes are updated atomically.
- Returned delete result contains the deleted link in `deleted_links` and otherwise uses empty lists.

### `RtgGraph.preview_delete_anchor`

Kind:

- function

Inputs:

- `anchor_uuid`

Outputs:

- `RtgGraphDeleteResult`

Errors:

- `RtgGraphUuidInvalid`
- `RtgGraphAnchorNotFound`

Semantics:

- Returns the objects and index entries that `delete_anchor` would remove, without mutating the graph.
- Computes cascade effects using the same logic as `delete_anchor`, so callers such as validators can evaluate projected post-delete state without reimplementing cascade rules.
- Does not mutate object maps or derived indexes.

### `RtgGraph.preview_delete_data_object`

Kind:

- function

Inputs:

- `data_uuid`

Outputs:

- `RtgGraphDeleteResult`

Errors:

- `RtgGraphUuidInvalid`
- `RtgGraphDataObjectNotFound`

Semantics:

- Returns the objects and index entries that `delete_data_object` would remove, without mutating the graph.
- Computes cascade effects using the same logic as `delete_data_object`.
- Does not mutate object maps or derived indexes.

### `RtgGraph.preview_dissociate_data`

Kind:

- function

Inputs:

- `anchor_uuid`
- `data_uuid`

Outputs:

- `RtgGraphDeleteResult`

Errors:

- `RtgGraphUuidInvalid`
- `RtgGraphAnchorNotFound`
- `RtgGraphDataObjectNotFound`
- `RtgGraphAnchorDataIndexEntryNotFound`

Semantics:

- Returns the index entry, and any cascaded data object and incident links, that `dissociate_data` would remove, without mutating the graph.
- Computes cascade effects using the same logic as `dissociate_data`, including deletion of a data object left with no remaining anchor association.
- Does not mutate object maps or derived indexes.

### `RtgGraph.get_object`

Kind:

- function

Inputs:

- `object_uuid`

Outputs:

- `RtgObject`

Errors:

- `RtgGraphUuidInvalid`
- `RtgGraphObjectNotFound`

Semantics:

- Returns an anchor, data object, or link by UUID when it exists.
- Lookup is direct and does not apply lifecycle, `system.live`, visibility, role, or publication filtering.

### `RtgGraph.list_by_type`

Kind:

- function

Inputs:

- `object_type`

Outputs:

- `RtgObjectList`

Errors:

- `RtgGraphTypeInvalid`

Semantics:

- Lists objects with the requested type using the component-owned global type index.
- Type strings are resolved across the single RTG type namespace.
- Results are not filtered by lifecycle, `system.live`, visibility, role, or publication state.
- List ordering is stable for a given graph state but does not encode semantic ordering.

### `RtgGraph.list_anchor_data`

Kind:

- function

Inputs:

- `anchor_uuid`

Outputs:

- `RtgDataObjectList`

Errors:

- `RtgGraphUuidInvalid`
- `RtgGraphAnchorNotFound`

Semantics:

- Returns the data objects directly associated with an anchor.
- The operation reads the direct anchor-to-data index rather than traversing synthetic association links.
- Returned data objects are not filtered by lifecycle, `system.live`, visibility, role, or publication state.

### `RtgGraph.list_data_anchors`

Kind:

- function

Inputs:

- `data_uuid`

Outputs:

- `RtgAnchorList`

Errors:

- `RtgGraphUuidInvalid`
- `RtgGraphDataObjectNotFound`

Semantics:

- Returns the anchors directly associated with a data object.
- The operation reads the direct data-to-anchor index rather than traversing synthetic association links.
- Returned anchors are not filtered by lifecycle, `system.live`, visibility, role, or publication state.

### `RtgGraph.list_incident_links`

Kind:

- function

Inputs:

- `object_uuid`
- `direction`

Outputs:

- `RtgLinkList`

Errors:

- `RtgGraphUuidInvalid`
- `RtgGraphObjectNotFound`

Semantics:

- Lists links where `object_uuid` is the source, target, or either endpoint depending on `direction`.
- Returned links are not filtered by lifecycle, `system.live`, visibility, role, or publication state.

### `RtgGraph.count_by_type`

Kind:

- function

Inputs:

- `kind | None`
- `live | None`

Outputs:

- `RtgTypeCountList`

Errors:

- `RtgGraphTypeInvalid`

Semantics:

- Returns deterministic counts of objects grouped by type.
- `kind` may filter counts to anchors, data objects, or links.
- `live` may filter counts by `system.live`.
- Counts are derived from canonical object maps and do not create a separate population index as public state.
- The operation does not apply visibility, role, publication, schema, or authorization filtering.

### `RtgAnchor`

Kind:

- data structure

Fields:

- `uuid`
- `type`
- `display_name`
- `system`

Semantics:

- Represents a stable ontological object or reified relationship concept.
- `uuid` identifies the anchor and may be omitted on write, in which case the component generates one.
- Returned, stored, deleted-result, and snapshot anchor records always contain a concrete UUID.
- `display_name` is optional, non-unique, and intended for human navigation, visualization, and upstream UI labels.
- When `display_name` is absent, consumers may use the anchor type and UUID as a fallback label.
- Anchors may be associated with zero, one, or many data objects through direct indexes.
- `system` is a JSON-serializable object with a boolean `live` value and any additional caller-supplied metadata.
- Missing `system.live` is normalized to `true`.

### `RtgDataObject`

Kind:

- data structure

Fields:

- `uuid`
- `type`
- `properties`
- `system`

Semantics:

- Represents a typed JSON-serializable property store.
- `uuid` identifies the data object and may be omitted on write, in which case the component generates one.
- Returned, stored, deleted-result, and snapshot data object records always contain a concrete UUID.
- Data objects must be associated with one or many anchors through direct indexes.
- `properties` stores domain data and is schema-neutral to this component.
- `system` is a JSON-serializable object with a boolean `live` value and any additional caller-supplied metadata.
- Missing `system.live` is normalized to `true`.

### `RtgLink`

Kind:

- data structure

Fields:

- `uuid`
- `type`
- `source_uuid`
- `target_uuid`
- `system`

Semantics:

- Represents a typed directed edge between existing anchors or data objects.
- `uuid` identifies the link and may be omitted on write, in which case the component generates one.
- Returned, stored, deleted-result, and snapshot link records always contain a concrete UUID.
- `source_uuid` and `target_uuid` must not refer to links.
- `system` is a JSON-serializable object with a boolean `live` value and any additional caller-supplied metadata.
- Missing `system.live` is normalized to `true`.

### `RtgObject`

Kind:

- data structure

Semantics:

- A read result that is one of `RtgAnchor`, `RtgDataObject`, or `RtgLink`.
- Callers distinguish the kind by which structure is returned.
- List-valued read outputs such as `RtgObjectList`, `RtgAnchorList`, `RtgDataObjectList`, `RtgLinkList`, and `RtgTypeCountList` are ordered lists of the corresponding element type, ordered deterministically for a given graph state.

### `RtgGraphDeleteResult`

Kind:

- data structure

Fields:

- `deleted_anchors`
- `deleted_data_objects`
- `deleted_links`
- `removed_anchor_data_pairs`

Semantics:

- Represents object and index entries removed by a delete or dissociation operation.
- All fields are always present.
- `deleted_anchors`, `deleted_data_objects`, and `deleted_links` contain full deleted object records.
- `removed_anchor_data_pairs` contains two-item UUID pairs in the form `[anchor_uuid, data_uuid]`.
- `removed_anchor_data_pairs` is not a list of association objects and carries no association UUIDs, types, properties, or system metadata.
- Empty lists represent categories where no records were removed.
- Each list is ordered deterministically by UUID string; `removed_anchor_data_pairs` is ordered by anchor UUID and then data UUID.

### `RtgSystem`

Kind:

- data structure

Fields:

- `live`
- additional caller-supplied JSON properties

Semantics:

- Represents component-level and caller-supplied metadata for an anchor, data object, or link.
- `live` is a boolean that defaults to `true` when omitted.
- RTG defaults, validates, and preserves `live` but does not use it to filter reads, enforce workflow transitions, or decide delete cascade behavior.

### `RtgGraphSnapshot`

Kind:

- data structure

Fields:

- `anchors`
- `data_objects`
- `links`
- `anchor_data_index`

Semantics:

- Represents a JSON-serializable graph snapshot.
- `anchors`, `data_objects`, and `links` contain canonical object records.
- `anchor_data_index` is a JSON object whose keys are anchor UUIDs and whose values are lists of data object UUIDs.
- `anchor_data_index` serializes direct index entries; it is not a collection of association objects.
- Every object `system` store in an exported graph has a boolean `live`.
- A snapshot does not expose derived index material beyond the direct `anchor_data_index`; import rebuilds all other derived indexes from canonical records.
- Snapshot schema versioning is not owned by this draft component unless added through a later accepted contract.

### `RtgTypeCount`

Kind:

- data structure

Fields:

- `type`
- `kind`
- `live`
- `count`

Semantics:

- Represents a count of graph objects by type, object kind, and optional live-status filter.
- Counts are for introspection and discovery support only and do not encode authorization or query visibility.

## Required contracts

May consume:

- Standard UUID parsing, formatting, and comparison APIs.
- Standard JSON value validation APIs.
- In-memory collection, mapping, and indexing APIs.

Must not consume:

- Ontology-specific schema validators.
- Schema storage components.
- Graph delta validation components.
- Query, filtering, search, or graph traversal engines.
- Authentication, authorization, or user-management services.
- Persistence services, replay ledgers, audit logs, graph databases, document databases, remote object stores, queues, or distributed runtimes.
- Inference engines or ontology reasoners.
- The JSON File Storage component as a mandatory dependency.

## Owned state

- Canonical in-memory map of anchor UUID to `RtgAnchor`.
- Canonical in-memory map of data object UUID to `RtgDataObject`.
- Canonical in-memory map of link UUID to `RtgLink`.
- Derived global type-to-object-UUIDs index.
- Derived global type-to-object-kind index.
- Derived data-object-UUID-to-anchor-UUIDs index.
- Derived anchor-UUID-to-data-object-UUIDs index.
- Derived anchor-or-data-object-UUID-to-incident-link-UUIDs index.

## Invariants

### `global_uuid_uniqueness`

Each UUID identifies at most one RTG object across anchors, data objects, and links.

### `well_formed_uuids`

Every object UUID, endpoint UUID, and index UUID must be parseable as a UUID value.

### `uuid_generation`

The component generates a new unique UUID for any anchor, data object, or link written without a caller-supplied UUID, and uses a caller-supplied UUID unchanged when one is provided.

### `well_formed_types`

Every type must be a string that is non-empty, contains no leading or trailing whitespace, and contains no control characters.

### `single_global_type_namespace`

Within one graph state, a type string may belong to anchors, data objects, or links, but not more than one object kind.

### `many_to_many_data_association`

Anchors may be associated with many data objects, and data objects must be associated with at least one anchor.

### `no_unassociated_data_objects`

The graph must not contain a data object that has no direct association with an anchor.

### `association_indexes_reference_existing_objects`

Anchor-to-data and data-to-anchor indexes must reference only existing anchors and existing data objects.

### `no_association_objects`

Direct anchor-data association must exist only as UUID index entries and must not carry UUIDs, types, domain properties, system metadata, or independent object identity.

### `valid_link_endpoints`

Every link source and target UUID must resolve to an existing anchor or data object in the graph.

### `no_dangling_references_after_delete`

Delete and dissociation operations must remove affected anchor-data index entries and incident links so no index entry or link points to a missing object.

### `no_link_to_link_edges`

Links must not use other links as source or target endpoints.

### `type_indexes_match_canonical_maps`

Type indexes must match the canonical UUID-to-object maps after every successful mutation and import.

### `association_indexes_are_symmetric`

The anchor-to-data and data-to-anchor indexes must represent the same pairs after every successful mutation and import.

### `incident_link_indexes_match_canonical_links`

Incident-link indexes must match the canonical link map after every successful mutation and import.

### `json_serializable_property_stores`

Data object `properties` and all object `system` stores must be JSON-serializable objects.

### `system_live_boolean`

Every anchor, data object, and link must have a boolean `system.live` value after normalization.

### `schema_neutrality`

The component must preserve caller-supplied type strings, data properties, and system metadata without enforcing ontology-specific or application-specific schemas.

### `anchor_display_name_non_authoritative`

Anchor display names are optional, non-unique labels for navigation and visualization only; they do not define anchor identity or schema validity.

### `unfiltered_reads`

Read and export operations must not hide objects based on `system.live`, lifecycle, visibility, role, or publication metadata.

### `type_counts_match_canonical_maps`

Type count results must match the canonical UUID-to-object maps and requested filters.

### `mutation_atomicity`

A failed mutation must not leave object maps or derived indexes in a partially updated state.

### `preview_matches_delete`

Preview operations return exactly the objects and index entries the corresponding delete or dissociation operation would remove, share cascade logic with the mutating operations, and do not mutate graph state.

## Verification

Required checks:

- Contract tests for creating, replacing, fetching, listing, associating, dissociating, and deleting anchors, data objects, and links.
- UUID validation tests for object IDs, endpoint IDs, anchor-data index IDs, and lookup IDs.
- Type validation tests for empty strings, whitespace-only strings, leading or trailing whitespace, control characters, valid plain-English names, and valid Neo4J-style convention names.
- Type namespace tests proving a type cannot be used across multiple object kinds in the same graph state.
- Association-index tests proving anchors and data objects can be associated many-to-many without synthetic links or association objects.
- Referential-integrity tests for missing association endpoints, missing link endpoints, UUID conflicts, attempted cross-kind UUID reuse, link-to-link endpoints, delete cascades, and no dangling references after delete.
- Type-index tests proving list-by-type results match canonical UUID-to-object maps after creates, replacements, deletes, and imports.
- Association-index tests proving anchor-to-data and data-to-anchor listings remain symmetric after association, dissociation, data replacement, delete, and import operations.
- Incident-link-index tests proving incident link listings match canonical link records after link creation, link replacement, link deletion, endpoint deletion, and import operations.
- Snapshot round-trip tests proving exported snapshots can be imported into an equivalent in-memory graph.
- JSON serializability tests for data properties and system metadata.
- `system.live` tests proving anchors, data objects, and links default missing live values to `true` and reject non-boolean live values.
- Anchor display-name tests proving labels are optional, preserved, exported, imported, and non-unique.
- Unfiltered-read tests proving `system.live` does not change direct lookup, type listing, association listing, incident-link listing, or snapshot export results.
- Type count tests for anchor, data object, and link counts with live and non-live filters.
- Mutation failure tests proving object maps and derived indexes remain consistent after rejected operations.
- Preview tests proving `preview_delete_anchor`, `preview_delete_data_object`, and `preview_dissociate_data` return the same removal set as the corresponding mutation and do not mutate the graph.
- No-forbidden-dependency check proving the component does not require schema storage, schema validation, query engines, authentication services, persistence services, replay ledgers, audit logs, graph databases, queues, distributed runtimes, inference engines, or JSON File Storage.

Required evidence:

- Boundary tests covering representative anchor, data object, and link types.
- Tests proving writes without a supplied UUID receive a generated unique UUID, and writes with a supplied UUID use it unchanged.
- Tests proving data objects cannot be created or replaced without at least one existing anchor UUID.
- Tests proving repeated association is idempotent and repeated dissociation reports a missing association.
- Tests proving deleting anchors removes direct index entries, deletes incident links, cascades data objects with no remaining anchor associations, and preserves data objects associated with any other anchor, including anchors whose `system.live` is `false`.
- Tests proving deleting data objects removes direct index entries and incident links without deleting associated anchors.
- Tests proving dissociating the final anchor from a data object deletes that data object and its incident links.
- Tests proving delete results always contain deterministic `deleted_anchors`, `deleted_data_objects`, `deleted_links`, and `removed_anchor_data_pairs` lists.
- Tests proving link adjacency queries return source, target, and bidirectional incident links.
- Tests proving live anchor type counts can be produced for controller discovery without reading schema state.
- Snapshot fixtures containing anchors, data objects, many-to-many anchor-data index entries, links between anchors and data objects, and `system.live` metadata.
- Snapshot fixtures proving omitted `system.live` imports as `true`.
- Error mapping tests for invalid UUIDs, invalid types, type kind conflicts, invalid JSON values, missing anchors, missing data objects, missing links, missing anchor-data index entries, invalid system live values, and invalid link endpoints.

## Change rules

Agents may:

- Implement or refactor private internals inside `components/rtg/graph`.
- Add helper modules inside the component root.
- Add or update boundary-level tests for the provided contracts.
- Improve internal indexing strategies while preserving object maps, association index semantics, delete cascades, unfiltered reads, and public errors.
- Add snapshot adapter examples outside the component only when the RTG graph component remains persistence-neutral and ledger-neutral.

Agents may not:

- Replace direct anchor-data indexes with universal association links without explicit approval.
- Add anchor-data association objects, UUIDs, types, domain properties, or system metadata without explicit approval.
- Change anchor-data association from many-to-many to ownership without explicit approval.
- Change links to support link-to-link endpoints without explicit approval.
- Add partial object update contracts or field-specific system update contracts without explicit approval.
- Remove component UUID generation or stop honoring caller-supplied UUIDs without explicit approval.
- Add ontology-specific or application-specific schema validation as a component responsibility without explicit approval.
- Add lifecycle/status filtering, query execution, publication workflows, migration orchestration, replay, audit, persistence, or schema storage as a component responsibility without explicit approval.
- Add migration membership semantics to object `system` metadata without explicit approval.
- Add display names to data objects or links without explicit approval.
- Add authentication, authorization, durable persistence, replication, graph database, queue, distributed runtime, or JSON File Storage as a required dependency without explicit approval.
- Weaken global UUID uniqueness, well-formed type rules, single type namespace, association integrity, no-unassociated-data, no-dangling-reference, link endpoint integrity, `system.live`, JSON serializability, schema neutrality, unfiltered reads, or mutation atomicity invariants.
- Change lifecycle status from `draft` without human owner approval.

## Open questions

- None.
