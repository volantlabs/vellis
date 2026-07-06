---
id: component.rtg.discovery
type: Component
status: draft
owner: humans
code:
  roots:
    - components/rtg/discovery
---

# RTG Discovery

## Purpose

Provide curated type-discovery views that help agents and humans narrow a large RTG schema space before requesting detailed schema packs or constructing queries.

This component is deferred for initial implementation. In v1, the controller may expose basic discovery by composing schema summaries and graph counts. This component exists to define the future boundary for knowledge-engineer-owned discovery view state.

## Responsibilities

- Store curated discovery views created by knowledge engineers.
- Store view cells or selections that map high-level ontology categories and semantic domains to anchor type keys.
- Support a simple two-dimensional view shape in v1 of this component, while preserving the option for later higher-dimensional views.
- Return anchor type keys and descriptions associated with selected view coordinates.
- Preserve view metadata such as view descriptions, row labels, column labels, and cell descriptions.
- Keep discovery view state separate from schema definitions, graph objects, constraints, migrations, and query execution.

## Non-responsibilities

- Does not store schema definitions.
- Does not store graph objects or graph population counts.
- Does not execute RTG queries.
- Does not validate graph data against schema or constraints.
- Does not rank results with embeddings, search indexes, or external retrieval systems in this draft.
- Does not own controller-level schema-pack assembly.
- Does not provide authorization or UI behavior.

## Provided contracts

### `RtgDiscovery.empty`

Kind:

- function

Inputs:

- None.

Outputs:

- `RtgDiscovery`

Errors:

- None.

Semantics:

- Returns an empty discovery registry with no curated views.

### `RtgDiscovery.put_view`

Kind:

- function

Inputs:

- `view`

Outputs:

- `RtgDiscoveryView`

Errors:

- `RtgDiscoveryViewInvalid`

Semantics:

- Creates or replaces one curated discovery view.
- The view records labels, descriptions, and cell mappings from selected coordinates to anchor type keys.
- The write does not verify that referenced anchor type keys exist in `component.rtg.schema`.

### `RtgDiscovery.list_views`

Kind:

- function

Inputs:

- None.

Outputs:

- `RtgDiscoveryViewList`

Errors:

- None.

Semantics:

- Lists available curated discovery views and their high-level descriptions.
- Does not include expanded schema packs or graph counts.

### `RtgDiscovery.select_anchor_types`

Kind:

- function

Inputs:

- `view_id`
- `coordinates`

Outputs:

- `RtgDiscoverySelection`

Errors:

- `RtgDiscoveryViewNotFound`
- `RtgDiscoverySelectionInvalid`

Semantics:

- Returns anchor type keys and cell descriptions for selected view coordinates.
- Coordinates may represent ontology category and semantic domain in a two-dimensional view.
- The result is discovery view data only; callers may enrich it with schema descriptions or graph counts through other components.

### `RtgDiscoveryView`

Kind:

- data structure

Fields:

- `view_id`
- `description`
- `row_labels`
- `column_labels`
- `cells`
- `metadata`

Semantics:

- Represents one curated two-dimensional discovery view.
- `view_id` is the stable identity of the view.
- `description` explains the view's intended navigation use.
- `row_labels` and `column_labels` map coordinate keys to human-readable labels.
- `cells` contains `RtgDiscoveryCell` records.
- `metadata` is JSON-serializable caller-supplied detail.

### `RtgDiscoveryCell`

Kind:

- data structure

Fields:

- `row_key`
- `column_key`
- `description`
- `anchor_type_keys`

Semantics:

- Maps one two-dimensional view coordinate to anchor type keys.
- `row_key` must exist in the parent view's `row_labels`.
- `column_key` must exist in the parent view's `column_labels`.
- `anchor_type_keys` is an ordered list of schema anchor type keys.
- The cell does not store schema definitions or graph counts.

### `RtgDiscoveryCoordinates`

Kind:

- data structure

Fields:

- `row_key`
- `column_key`

Semantics:

- Identifies one cell in a two-dimensional discovery view.

### `RtgDiscoverySelection`

Kind:

- data structure

Fields:

- `view_id`
- `coordinates`
- `anchor_type_keys`
- `cell_descriptions`

Semantics:

- Result of selecting one or more cells from a curated discovery view.
- `coordinates` contains the selected `RtgDiscoveryCoordinates`.
- `anchor_type_keys` is the deterministic de-duplicated ordered list of anchor type keys from selected cells.
- `cell_descriptions` maps selected coordinates to their cell descriptions.

### `RtgDiscoveryViewList`

Kind:

- data structure

Fields:

- `views`

Semantics:

- Ordered list wrapper for discovery views.
- `views` contains full `RtgDiscoveryView` records; it does not include schema packs or graph counts.

## Required contracts

May consume:

- JSON-serializable value conventions for view snapshots and metadata.
- RTG schema type-key string conventions.

Must not consume:

- Graph, schema, constraints, migration, query, controller, validation, SQL storage, JSON File Storage, authorization, UI, or runtime internals as required dependencies.

## Related components

- `component.rtg.controller` may use this component in the future to provide curated discovery before fetching schema packs.
- `component.rtg.schema` owns schema definitions and basic type descriptions.
- `component.rtg.graph` may provide live type counts to the controller, not to this component directly.

## Owned state

- Curated discovery view records.
- View cell or coordinate mappings to anchor type keys.
- View descriptions and labels.

## Invariants

### `invariant.rtg.discovery.views_not_schema`

Discovery views organize schema type keys for navigation but do not define or validate schema definitions.

### `invariant.rtg.discovery.no_graph_dependency`

Discovery view selection does not require graph object state or population counts.

### `invariant.rtg.discovery.knowledge_engineer_curated`

Curated views are explicit records intended to be authored by knowledge engineers or tools acting on their behalf.

## Verification

Required checks:

- Boundary tests for creating, replacing, and listing discovery views.
- Boundary tests for selecting anchor type keys by view coordinates.
- API-surface checks proving discovery does not expose schema mutation, graph mutation, query execution, or validation.

Required evidence:

- A caller can define a two-dimensional view that maps ontology categories and semantic domains to anchor type keys.
- A caller can select a view cell and receive the anchor type keys to pass to controller schema-pack discovery.

## Change rules

Agents may:

- Add private storage and indexing helpers inside `components/rtg/discovery`.
- Add higher-dimensional view support when the public contract is updated.
- Add boundary tests for curated discovery behavior.

Agents may not:

- Move schema definitions, graph objects, query execution, validation, migration, ledger, or authorization behavior into this component.
- Make graph population counts owned state of discovery.
- Add external search or embedding dependencies without explicit approval.

## Open questions

- Should aliases or search terms be part of curated discovery views, or should they belong to a later search component?
- When implemented, should this component add `import_snapshot`/`export_snapshot` contracts and join the controller system snapshot, mirroring the other stateful RTG stores?
