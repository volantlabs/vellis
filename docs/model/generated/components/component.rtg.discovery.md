# component.rtg.discovery

Generated from textual SysML v2 by `just model-render`; do not edit by hand.

- Model definition: `RtgDiscovery`
- Lifecycle: `draft`
- Purpose: Own curated navigation metadata while remaining independent of schema contents, graph population, query execution, and transports.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `putView` | `PutDiscoveryView` | in `view: RtgDiscoveryView`; out `stored: RtgDiscoveryView` | `RtgDiscoveryViewInvalid` | Validate and create or completely replace the view with the same viewId. Anchor type keys remain opaque and are not checked against schema. |
| `listViews` | `ListDiscoveryViews` | out `result: RtgDiscoveryViewList` | None | Return full curated views in ascending viewId order without mutation. |
| `selectAnchorTypes` | `SelectDiscoveryAnchorTypes` | in `viewId: String`; in `coordinates: RtgDiscoveryCoordinates[1..*]`; out `result: RtgDiscoverySelection` | `RtgDiscoveryViewNotFound`, `RtgDiscoverySelectionInvalid` | Preserve requested coordinates and return the first-occurrence, de-duplicated anchor type keys plus coordinate-to-description mapping for the selected cells. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `CreateEmptyRtgDiscovery` | out `discovery: RtgDiscovery` | None | Return a registry with no curated views. |

## Retained collaborator roles

| Role | Kind | Referenced type | Multiplicity |
|---|---|---|---|
| — | — | — | No retained collaborator roles. |

## Owned state

| State feature | Type | Ownership | Meaning |
|---|---|---|---|
| `curatedViews` | `RtgDiscoveryView` | `owned` | Canonical component-owned curated discovery views; persistence remains unspecified. |

## Action and state effects

| Action | State / collaborator | Modeled effect |
|---|---|---|
| `putView` | `curatedViews` | create or fully replace one valid view atomically. |
| `listViews` | `curatedViews` | return full views in view-ID order without mutation. |
| `selectAnchorTypes` | `curatedViews` | return the stable union and descriptions of selected cells without mutation. |

## Invariants and behavioral obligations

| Stable ID | Modeled obligation |
|---|---|
| `contract.rtg.discovery.view_validity` | viewId and label keys are non-empty; row and column label values are strings; each cell coordinate is unique and refers to declared labels; all metadata and descriptions are JSON-safe and anchor type keys preserve caller order. |
| `contract.rtg.discovery.replacement` | A valid put stores exactly the supplied view under viewId, replacing any prior version atomically and leaving other views unchanged. |
| `contract.rtg.discovery.selection` | Selection requires an existing view and one or more unique existing coordinates. Results preserve coordinate order, de-duplicate anchor keys by first occurrence, and include descriptions keyed without coordinate ambiguity. |
| `contract.rtg.discovery.deterministic_reads` | Listing is ordered by viewId; selection is ordered by request coordinates and cell anchor-key order. Reads never mutate curatedViews. |
| `invariant.rtg.discovery.views_not_schema` | Views organize opaque type keys but do not define or validate schema. |
| `invariant.rtg.discovery.no_graph_dependency` | Selection does not require graph objects or population counts. |
| `invariant.rtg.discovery.knowledge_engineer_curated` | Curated views are explicit knowledge-engineering records, not inferred search results. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgDiscoveryCoordinates` | `attribute` | `rowKey: String`, `columnKey: String` | Defined by its typed fields and action requirements. |
| `RtgDiscoveryCell` | `attribute` | `rowKey: String`, `columnKey: String`, `description: String`, `anchorTypeKeys[0..*]: String` | Defined by its typed fields and action requirements. |
| `RtgDiscoveryView` | `item` | `viewId: String`, `description: String`, `rowLabels: JsonObject`, `columnLabels: JsonObject`, `cells[0..*]: RtgDiscoveryCell`, `metadata: JsonObject` | viewId is stable identity; label objects map coordinate keys to human-readable labels. Each coordinate is unique and every cell uses declared row and column keys. |
| `RtgDiscoverySelection` | `attribute` | `viewId: String`, `coordinates[1..*]: RtgDiscoveryCoordinates`, `anchorTypeKeys[0..*]: String`, `cellDescriptions: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgDiscoveryViewList` | `attribute` | `views[0..*]: RtgDiscoveryView` | Defined by its typed fields and action requirements. |
| `RtgDiscoveryViewInvalid` | `attribute` | `message: String`, `diagnostic: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgDiscoveryViewNotFound` | `attribute` | `message: String`, `diagnostic: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgDiscoverySelectionInvalid` | `attribute` | `message: String`, `diagnostic: JsonObject` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Model and external values |
|---|---|
| — | No component-owned public enumerations. |

## Verification

| Verification | Objectives | Evidence |
|---|---|---|
| `RtgDiscoveryBoundaryVerification` | `viewValidity`, `replacementEffect`, `selectionEffect`, `deterministicReads`, `viewsNotSchema`, `noGraphDependency`, `knowledgeEngineerCurated` | `pending` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
