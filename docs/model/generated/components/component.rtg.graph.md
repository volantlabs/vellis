# component.rtg.graph

Generated from textual SysML v2 by `just model-render`; do not edit by hand.

- Model definition: `RtgGraph`
- Lifecycle: `accepted`
- Purpose: Own canonical RTG anchors, data objects, links, direct associations, and derived navigation indexes without schema or lifecycle filtering policy.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `exportSnapshot` | `ExportGraphSnapshot` | out `snapshot: RtgGraphSnapshot` | None | Return the complete unfiltered graph state without mutation. |
| `getObject` | `GetGraphObject` | in `objectUuid: Uuid`; out `object: RtgObject` | `RtgGraphUuidInvalid`, `RtgGraphObjectNotFound` | Return an anchor, data object, or link directly by UUID without lifecycle filtering. |
| `listByType` | `ListGraphObjectsByType` | in `objectType: String`; out `result: RtgObjectList` | `RtgGraphTypeInvalid` | Return all objects in the global type namespace for one type in stable component order, without lifecycle filtering. |
| `listAnchorData` | `ListAnchorData` | in `anchorUuid: Uuid`; out `result: RtgDataObjectList` | `RtgGraphUuidInvalid`, `RtgGraphAnchorNotFound` | Return directly associated data without lifecycle filtering. |
| `listDataAnchors` | `ListDataAnchors` | in `dataUuid: Uuid`; out `result: RtgAnchorList` | `RtgGraphUuidInvalid`, `RtgGraphDataObjectNotFound` | Return directly associated anchors without lifecycle filtering. |
| `listIncidentLinks` | `ListIncidentLinks` | in `objectUuid: Uuid`; in `direction: RtgLinkDirection` = `RtgLinkDirection::both`; out `result: RtgLinkList` | `RtgGraphUuidInvalid`, `RtgGraphObjectNotFound` | Return source, target, or all incident links without lifecycle filtering. |
| `countByType` | `CountGraphObjectsByType` | in `kind: RtgObjectKind[0..1]`; in `live: Boolean[0..1]`; out `result: RtgTypeCountList` | `RtgGraphTypeInvalid` | Return deterministic counts by type with optional object-kind and live-status filters. |
| `putAnchor` | `PutAnchor` | in `anchor: RtgAnchor`; out `stored: RtgAnchor` | `RtgGraphUuidInvalid`, `RtgGraphUuidConflict`, `RtgGraphTypeInvalid`, `RtgGraphTypeKindConflict`, `RtgGraphSystemValueInvalid` | Create or fully replace one anchor while preserving its associations and incident links. |
| `putDataObject` | `PutDataObject` | in `dataObject: RtgDataObject`; in `anchorUuids: Uuid[1..*]`; out `stored: RtgDataObject` | `RtgGraphUuidInvalid`, `RtgGraphUuidConflict`, `RtgGraphAnchorNotFound`, `RtgGraphTypeInvalid`, `RtgGraphTypeKindConflict`, `RtgGraphJsonValueInvalid`, `RtgGraphSystemValueInvalid` | Create or fully replace one data object and replace its complete direct anchor association set. |
| `putLink` | `PutLink` | in `link: RtgLink`; out `stored: RtgLink` | `RtgGraphUuidInvalid`, `RtgGraphUuidConflict`, `RtgGraphEndpointNotFound`, `RtgGraphTypeInvalid`, `RtgGraphTypeKindConflict`, `RtgGraphSystemValueInvalid` | Create or fully replace one directed typed link between existing non-link endpoints. |
| `associateData` | `AssociateData` | in `anchorUuid: Uuid`; in `dataUuid: Uuid` | `RtgGraphUuidInvalid`, `RtgGraphAnchorNotFound`, `RtgGraphDataObjectNotFound` | Idempotently add one direct anchor-data association. |
| `dissociateData` | `DissociateData` | in `anchorUuid: Uuid`; in `dataUuid: Uuid`; out `result: RtgGraphDeleteResult` | `RtgGraphUuidInvalid`, `RtgGraphAnchorNotFound`, `RtgGraphDataObjectNotFound`, `RtgGraphAnchorDataIndexEntryNotFound` | Remove one association and delete the data object plus incident links if it becomes ungrounded. |
| `deleteAnchor` | `DeleteAnchor` | in `anchorUuid: Uuid`; out `result: RtgGraphDeleteResult` | `RtgGraphUuidInvalid`, `RtgGraphAnchorNotFound` | Delete one anchor, its incident links, its associations, and data left with no anchors. |
| `deleteDataObject` | `DeleteDataObject` | in `dataUuid: Uuid`; out `result: RtgGraphDeleteResult` | `RtgGraphUuidInvalid`, `RtgGraphDataObjectNotFound` | Delete one data object, its associations, and incident links without deleting anchors. |
| `deleteLink` | `DeleteLink` | in `linkUuid: Uuid`; out `result: RtgGraphDeleteResult` | `RtgGraphUuidInvalid`, `RtgGraphLinkNotFound` | Delete exactly one link without deleting either endpoint. |
| `previewDeleteAnchor` | `PreviewDeleteAnchor` | in `anchorUuid: Uuid`; out `result: RtgGraphDeleteResult` | `RtgGraphUuidInvalid`, `RtgGraphAnchorNotFound` | Return the exact DeleteAnchor cascade from the same state without mutation. |
| `previewDeleteDataObject` | `PreviewDeleteDataObject` | in `dataUuid: Uuid`; out `result: RtgGraphDeleteResult` | `RtgGraphUuidInvalid`, `RtgGraphDataObjectNotFound` | Return the exact DeleteDataObject cascade from the same state without mutation. |
| `previewDissociateData` | `PreviewDissociateData` | in `anchorUuid: Uuid`; in `dataUuid: Uuid`; out `result: RtgGraphDeleteResult` | `RtgGraphUuidInvalid`, `RtgGraphAnchorNotFound`, `RtgGraphDataObjectNotFound`, `RtgGraphAnchorDataIndexEntryNotFound` | Return the exact DissociateData cascade from the same state without mutation. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `CreateEmptyRtgGraph` | out `graph: RtgGraph` | None | Return an empty graph with empty canonical state and derived indexes. |
| `ImportRtgGraphSnapshot` | in `snapshot: RtgGraphSnapshot`; out `graph: RtgGraph` | `RtgGraphSnapshotInvalid`, `RtgGraphUuidInvalid`, `RtgGraphUuidConflict`, `RtgGraphReferenceInvalid`, `RtgGraphTypeInvalid`, `RtgGraphTypeKindConflict`, `RtgGraphJsonValueInvalid`, `RtgGraphSystemValueInvalid` | Validate the whole snapshot, normalize live metadata, rebuild all derived indexes, and expose no partial graph. |

## Retained collaborator roles

| Role | Kind | Referenced type | Multiplicity |
|---|---|---|---|
| — | — | — | No retained collaborator roles. |

## Owned state

| State feature | Type | Ownership | Meaning |
|---|---|---|---|
| `anchors` | `RtgAnchor` | `owned` | Canonical component-owned anchor occurrences. |
| `dataObjects` | `RtgDataObject` | `owned` | Canonical component-owned data-object occurrences. |
| `links` | `RtgLink` | `owned` | Canonical component-owned link occurrences. |
| `anchorDataAssociations` | `JsonObject` | `owned` | Canonical identity-free direct associations. |
| `derivedIndexes` | `JsonObject` | `derived` | Ephemeral navigation indexes derived from canonical graph state. |

## Action and state effects

| Action | State / collaborator | Modeled effect |
|---|---|---|
| `putAnchor` | `anchors` | atomically create/replace anchor and maintain indexes. |
| `putDataObject` | `dataObjects` | atomically create/replace data, associations, and indexes. |
| `putLink` | `links` | atomically create/replace link and indexes. |
| `associateData` | `anchorDataAssociations` | idempotently add symmetric direct association. |
| `dissociateData` | `anchorDataAssociations` | remove association and complete cascade atomically. |
| `deleteAnchor` | `anchors` | remove anchor and complete cascade atomically. |
| `deleteDataObject` | `dataObjects` | remove data and complete cascade atomically. |
| `deleteLink` | `links` | remove exactly one link and index entries. |
| `exportSnapshot` | — | read complete canonical state. |
| `getObject` | — | direct unfiltered read. |
| `listByType` | — | read derived type index in stable order. |
| `listAnchorData` | — | read direct anchor-data index. |
| `listDataAnchors` | — | read inverse direct association index. |
| `listIncidentLinks` | — | read derived incident-link index. |
| `countByType` | — | derive counts from canonical records. |
| `previewDeleteAnchor` | — | compute exact anchor cascade without mutation. |
| `previewDeleteDataObject` | — | compute exact data cascade without mutation. |
| `previewDissociateData` | — | compute exact dissociation cascade without mutation. |

## Invariants and behavioral obligations

| Stable ID | Modeled obligation |
|---|---|
| `contract.rtg.graph.put_effect` | Puts generate a UUID when omitted, preserve a supplied valid UUID, normalize missing system.live to true, fully replace the named record fields, preserve unrelated records, and atomically maintain associations and indexes. |
| `contract.rtg.graph.association_effect` | Association is a direct identity-free many-to-many relation. Repeated association is idempotent; removing the last anchor grounds deletion of the data object and its incident links. |
| `contract.rtg.graph.delete_effect` | Deletes return the complete cascade with always-present result lists and leave no dangling links or associations; rejected deletes have no effect. |
| `contract.rtg.graph.preview_effect` | Each preview returns exactly the cascade the paired mutation would produce from the same state and changes no canonical or derived state. |
| `contract.rtg.graph.snapshot_effect` | Export preserves UUIDs, types, endpoints, properties, system metadata, and direct associations without filtering. Import validates the whole candidate and rebuilds derived indexes. |
| `invariant.rtg.graph.global_uuid_uniqueness` | UUIDs are globally unique across graph object kinds. |
| `invariant.rtg.graph.well_formed_uuids` | Every stored identity is a well-formed UUID. |
| `invariant.rtg.graph.uuid_generation` | Generated identities are UUIDs and valid caller identities are preserved. |
| `invariant.rtg.graph.well_formed_types` | Every object has a non-empty type key. |
| `invariant.rtg.graph.single_global_type_namespace` | A type key belongs to only one object kind. |
| `invariant.rtg.graph.many_to_many_data_association` | Anchors and data objects support direct many-to-many association. |
| `invariant.rtg.graph.no_unassociated_data_objects` | Every stored data object has at least one anchor. |
| `invariant.rtg.graph.association_indexes_reference_existing_objects` | Associations reference existing anchors and data objects. |
| `invariant.rtg.graph.no_association_objects` | Direct associations have no object identity, type, metadata, or link representation. |
| `invariant.rtg.graph.valid_link_endpoints` | Link endpoints exist and are anchors or data objects. |
| `invariant.rtg.graph.no_dangling_references_after_delete` | Deletes leave no dangling association or link references. |
| `invariant.rtg.graph.no_link_to_link_edges` | Links cannot be link endpoints. |
| `invariant.rtg.graph.type_indexes_match_canonical_maps` | Derived type indexes equal canonical object membership. |
| `invariant.rtg.graph.association_indexes_are_symmetric` | Both direct association directions agree. |
| `invariant.rtg.graph.incident_link_indexes_match_canonical_links` | Incident-link indexes derive exactly from canonical links. |
| `invariant.rtg.graph.json_serializable_property_stores` | Properties and system metadata are JSON-safe. |
| `invariant.rtg.graph.system_live_boolean` | Missing system.live normalizes to true and supplied live is Boolean. |
| `invariant.rtg.graph.schema_neutrality` | Graph storage does not enforce application schema or ontology meaning. |
| `invariant.rtg.graph.anchor_display_name_non_authoritative` | Display name is optional, non-unique, and not identity. |
| `invariant.rtg.graph.unfiltered_reads` | Base reads never hide objects by live status, visibility, role, or publication. |
| `invariant.rtg.graph.type_counts_match_canonical_maps` | Counts derive from canonical records and explicit kind/live filters. |
| `invariant.rtg.graph.mutation_atomicity` | Each mutation preserves every graph invariant or has no effect. |
| `invariant.rtg.graph.preview_matches_delete` | Preview cascades match their corresponding mutations. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgSystem` | `attribute` | `live[0..1]: Boolean` = `true` | JSON-safe caller metadata. Missing live normalizes to true; when supplied it is Boolean. Other keys are preserved without component-assigned meaning. |
| `RtgObject` | `item` | `uuid[0..1]: Uuid`, `type: String`, `system: RtgSystem` | UUID may be absent only on a write request; every stored, returned, deleted, or snapshotted object has a concrete UUID. |
| `RtgAnchor` | `item` | `uuid[0..1]: Uuid`, `type: String`, `system: RtgSystem`, `displayName[0..1]: String` | Stable typed ontological anchor. Display name is optional, non-unique, and non-authoritative. |
| `RtgDataObject` | `item` | `uuid[0..1]: Uuid`, `type: String`, `system: RtgSystem`, `properties: JsonObject` | Typed JSON property store grounded through one or more direct anchor associations. |
| `RtgLink` | `item` | `uuid[0..1]: Uuid`, `type: String`, `system: RtgSystem`, `sourceUuid: Uuid`, `targetUuid: Uuid` | Typed directed link whose endpoints are existing anchors or data objects, never links. |
| `RtgAnchorDataPair` | `attribute` | `anchorUuid: Uuid`, `dataUuid: Uuid` | Defined by its typed fields and action requirements. |
| `RtgGraphDeleteResult` | `attribute` | `deletedAnchors[0..*]: RtgAnchor`, `deletedDataObjects[0..*]: RtgDataObject`, `deletedLinks[0..*]: RtgLink`, `removedAnchorDataPairs[0..*]: RtgAnchorDataPair` | Complete cascade result; every list is present, including when empty. |
| `RtgGraphSnapshot` | `attribute` | `anchors[0..*]: JsonObject`, `dataObjects[0..*]: JsonObject`, `links[0..*]: JsonObject`, `anchorDataIndex: JsonObject` | JSON-safe canonical records and direct anchor-to-data index sufficient for equivalent reconstruction. |
| `RtgObjectList` | `attribute` | `objects[0..*]: RtgObject` | Defined by its typed fields and action requirements. |
| `RtgAnchorList` | `attribute` | `anchors[0..*]: RtgAnchor` | Defined by its typed fields and action requirements. |
| `RtgDataObjectList` | `attribute` | `dataObjects[0..*]: RtgDataObject` | Defined by its typed fields and action requirements. |
| `RtgLinkList` | `attribute` | `links[0..*]: RtgLink` | Defined by its typed fields and action requirements. |
| `RtgTypeCount` | `attribute` | `type: String`, `kind: RtgObjectKind`, `live[0..1]: Boolean`, `count: Integer` | Defined by its typed fields and action requirements. |
| `RtgTypeCountList` | `attribute` | `counts[0..*]: RtgTypeCount` | Defined by its typed fields and action requirements. |
| `RtgGraphSnapshotInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgGraphUuidInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgGraphUuidConflict` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgGraphReferenceInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgGraphTypeInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgGraphTypeKindConflict` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgGraphJsonValueInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgGraphSystemValueInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgGraphAnchorNotFound` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgGraphDataObjectNotFound` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgGraphLinkNotFound` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgGraphEndpointNotFound` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgGraphAnchorDataIndexEntryNotFound` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgGraphObjectNotFound` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Model and external values |
|---|---|
| `RtgObjectKind` | `anchor`, `dataObject` → `data_object`, `link` |
| `RtgLinkDirection` | `source`, `target`, `both` |

## Verification

| Verification | Objectives | Evidence |
|---|---|---|
| `RtgGraphBoundaryVerification` | `putEffect`, `associationEffect`, `deleteEffect`, `previewEffect`, `snapshotEffect`, `globalUuidUniqueness`, `wellFormedUuids`, `uuidGeneration`, `wellFormedTypes`, `singleGlobalTypeNamespace`, `manyToManyDataAssociation`, `noUnassociatedDataObjects`, `associationIndexesReferenceExistingObjects`, `noAssociationObjects`, `validLinkEndpoints`, `noDanglingReferencesAfterDelete`, `noLinkToLinkEdges`, `typeIndexesMatchCanonicalMaps`, `associationIndexesAreSymmetric`, `incidentLinkIndexesMatchCanonicalLinks`, `jsonSerializablePropertyStores`, `systemLiveBoolean`, `schemaNeutrality`, `anchorDisplayNameNonAuthoritative`, `unfilteredReads`, `typeCountsMatchCanonicalMaps`, `mutationAtomicity`, `previewMatchesDelete` | `components/rtg/graph/tests/test_rtg_graph_contract.py` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
