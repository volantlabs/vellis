library package BibliotekRtgGraph {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;

    enum def RtgObjectKind {
        enum anchor;
        enum data_object;
        enum link;
    }
    enum def RtgLinkDirection { enum source; enum target; enum both; }

    attribute def RtgSystem :> JsonObject {
        attribute live[0..1] : Boolean = true;
        doc /* JSON-safe caller metadata. Missing live normalizes to true; when supplied it is Boolean. Other keys are preserved without component-assigned meaning. */
    }
    abstract item def RtgObject {
        attribute uuid[0..1] : Uuid;
        attribute type : String;
        attribute system : RtgSystem;
        doc /* UUID may be absent only on a write request; every stored, returned, deleted, or snapshotted object has a concrete UUID. */
    }
    item def RtgAnchor :> RtgObject {
        attribute displayName[0..1] : String;
        doc /* Stable typed ontological anchor. Display name is optional, non-unique, and non-authoritative. */
    }
    item def RtgDataObject :> RtgObject {
        attribute properties : JsonObject;
        doc /* Typed JSON property store grounded through one or more direct anchor associations. */
    }
    item def RtgLink :> RtgObject {
        attribute sourceUuid : Uuid;
        attribute targetUuid : Uuid;
        doc /* Typed directed link whose endpoints are existing anchors or data objects, never links. */
    }
    attribute def RtgAnchorDataPair { attribute anchorUuid : Uuid; attribute dataUuid : Uuid; }
    attribute def RtgGraphDeleteResult {
        ref item deletedAnchors[0..*] : RtgAnchor;
        ref item deletedDataObjects[0..*] : RtgDataObject;
        ref item deletedLinks[0..*] : RtgLink;
        attribute removedAnchorDataPairs[0..*] : RtgAnchorDataPair;
        doc /* Complete cascade result; every list is present, including when empty. */
    }
    attribute def RtgGraphSnapshot {
        attribute anchors[0..*] : JsonObject;
        attribute dataObjects[0..*] : JsonObject;
        attribute links[0..*] : JsonObject;
        attribute anchorDataIndex : JsonObject;
        doc /* JSON-safe canonical records and direct anchor-to-data index sufficient for equivalent reconstruction. */
    }
    attribute def RtgObjectList { ref item objects[0..*] : RtgObject; }
    attribute def RtgAnchorList { ref item anchors[0..*] : RtgAnchor; }
    attribute def RtgDataObjectList { ref item dataObjects[0..*] : RtgDataObject; }
    attribute def RtgLinkList { ref item links[0..*] : RtgLink; }
    attribute def RtgTypeCount {
        attribute type : String;
        attribute kind : RtgObjectKind;
        attribute live[0..1] : Boolean;
        attribute count : Integer;
    }
    attribute def RtgTypeCountList { attribute counts[0..*] : RtgTypeCount; }

    attribute def RtgGraphSnapshotInvalid { attribute 'message' : String; }
    attribute def RtgGraphUuidInvalid { attribute 'message' : String; }
    attribute def RtgGraphUuidConflict { attribute 'message' : String; }
    attribute def RtgGraphReferenceInvalid { attribute 'message' : String; }
    attribute def RtgGraphTypeInvalid { attribute 'message' : String; }
    attribute def RtgGraphTypeKindConflict { attribute 'message' : String; }
    attribute def RtgGraphJsonValueInvalid { attribute 'message' : String; }
    attribute def RtgGraphSystemValueInvalid { attribute 'message' : String; }
    attribute def RtgGraphAnchorNotFound { attribute 'message' : String; }
    attribute def RtgGraphDataObjectNotFound { attribute 'message' : String; }
    attribute def RtgGraphLinkNotFound { attribute 'message' : String; }
    attribute def RtgGraphEndpointNotFound { attribute 'message' : String; }
    attribute def RtgGraphAnchorDataIndexEntryNotFound { attribute 'message' : String; }
    attribute def RtgGraphObjectNotFound { attribute 'message' : String; }

    action def ExportGraphSnapshot {
        out 'snapshot' : RtgGraphSnapshot;
        doc /* Return the complete unfiltered graph state without mutation. */
        @FailureContract { errorIds = (); }
    }
    action def PutAnchor {
        in anchor : RtgAnchor; out stored : RtgAnchor;
        doc /* Create or fully replace one anchor while preserving its associations and incident links. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphUuidConflict", "RtgGraphTypeInvalid", "RtgGraphTypeKindConflict", "RtgGraphSystemValueInvalid"); }
    }
    action def PutDataObject {
        in dataObject : RtgDataObject; in anchorUuids[1..*] : Uuid; out stored : RtgDataObject;
        doc /* Create or fully replace one data object and replace its complete direct anchor association set. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphUuidConflict", "RtgGraphAnchorNotFound", "RtgGraphTypeInvalid", "RtgGraphTypeKindConflict", "RtgGraphJsonValueInvalid", "RtgGraphSystemValueInvalid"); }
    }
    action def PutLink {
        in link : RtgLink; out stored : RtgLink;
        doc /* Create or fully replace one directed typed link between existing non-link endpoints. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphUuidConflict", "RtgGraphEndpointNotFound", "RtgGraphTypeInvalid", "RtgGraphTypeKindConflict", "RtgGraphSystemValueInvalid"); }
    }
    action def AssociateData {
        in anchorUuid : Uuid; in dataUuid : Uuid;
        doc /* Idempotently add one direct anchor-data association. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphAnchorNotFound", "RtgGraphDataObjectNotFound"); }
    }
    action def DissociateData {
        in anchorUuid : Uuid; in dataUuid : Uuid; out result : RtgGraphDeleteResult;
        doc /* Remove one association and delete the data object plus incident links if it becomes ungrounded. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphAnchorNotFound", "RtgGraphDataObjectNotFound", "RtgGraphAnchorDataIndexEntryNotFound"); }
    }
    action def DeleteAnchor {
        in anchorUuid : Uuid; out result : RtgGraphDeleteResult;
        doc /* Delete one anchor, its incident links, its associations, and data left with no anchors. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphAnchorNotFound"); }
    }
    action def DeleteDataObject {
        in dataUuid : Uuid; out result : RtgGraphDeleteResult;
        doc /* Delete one data object, its associations, and incident links without deleting anchors. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphDataObjectNotFound"); }
    }
    action def DeleteLink {
        in linkUuid : Uuid; out result : RtgGraphDeleteResult;
        doc /* Delete exactly one link without deleting either endpoint. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphLinkNotFound"); }
    }
    action def PreviewDeleteAnchor {
        in anchorUuid : Uuid; out result : RtgGraphDeleteResult;
        doc /* Return the exact DeleteAnchor cascade from the same state without mutation. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphAnchorNotFound"); }
    }
    action def PreviewDeleteDataObject {
        in dataUuid : Uuid; out result : RtgGraphDeleteResult;
        doc /* Return the exact DeleteDataObject cascade from the same state without mutation. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphDataObjectNotFound"); }
    }
    action def PreviewDissociateData {
        in anchorUuid : Uuid; in dataUuid : Uuid; out result : RtgGraphDeleteResult;
        doc /* Return the exact DissociateData cascade from the same state without mutation. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphAnchorNotFound", "RtgGraphDataObjectNotFound", "RtgGraphAnchorDataIndexEntryNotFound"); }
    }
    action def GetGraphObject {
        in objectUuid : Uuid; out object : RtgObject;
        doc /* Return an anchor, data object, or link directly by UUID without lifecycle filtering. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphObjectNotFound"); }
    }
    action def ListGraphObjectsByType {
        in objectType : String; out result : RtgObjectList;
        doc /* Return all objects in the global type namespace for one type in stable component order, without lifecycle filtering. */
        @FailureContract { errorIds = ("RtgGraphTypeInvalid"); }
    }
    action def ListAnchorData {
        in anchorUuid : Uuid; out result : RtgDataObjectList;
        doc /* Return directly associated data without lifecycle filtering. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphAnchorNotFound"); }
    }
    action def ListDataAnchors {
        in dataUuid : Uuid; out result : RtgAnchorList;
        doc /* Return directly associated anchors without lifecycle filtering. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphDataObjectNotFound"); }
    }
    action def ListIncidentLinks {
        in objectUuid : Uuid; in direction : RtgLinkDirection default = RtgLinkDirection::both; out result : RtgLinkList;
        doc /* Return source, target, or all incident links without lifecycle filtering. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphObjectNotFound"); }
    }
    action def CountGraphObjectsByType {
        in kind[0..1] : RtgObjectKind; in live[0..1] : Boolean; out result : RtgTypeCountList;
        doc /* Return deterministic counts by type with optional object-kind and live-status filters. */
        @FailureContract { errorIds = ("RtgGraphTypeInvalid"); }
    }

    part def RtgGraphReadView {
        perform action exportSnapshot[0..*] : ExportGraphSnapshot { doc /* read complete canonical state. */ }
        perform action getObject[0..*] : GetGraphObject { doc /* direct unfiltered read. */ }
        perform action listByType[0..*] : ListGraphObjectsByType { doc /* read derived type index in stable order. */ }
        perform action listAnchorData[0..*] : ListAnchorData { doc /* read direct anchor-data index. */ }
        perform action listDataAnchors[0..*] : ListDataAnchors { doc /* read inverse direct association index. */ }
        perform action listIncidentLinks[0..*] : ListIncidentLinks { doc /* read derived incident-link index. */ }
        perform action countByType[0..*] : CountGraphObjectsByType { doc /* derive counts from canonical records. */ }
    }

    part def <'component.rtg.graph'> RtgGraph :> RtgGraphReadView {
        doc /* Own canonical RTG anchors, data objects, links, direct associations, and derived navigation indexes without schema or lifecycle filtering policy. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        item anchors[0..*] : RtgAnchor { doc /* Canonical component-owned anchor occurrences. */ }
        item dataObjects[0..*] : RtgDataObject { doc /* Canonical component-owned data-object occurrences. */ }
        item links[0..*] : RtgLink { doc /* Canonical component-owned link occurrences. */ }
        attribute anchorDataAssociations : JsonObject { doc /* Canonical identity-free direct associations. */ }
        derived attribute derivedIndexes : JsonObject { doc /* Ephemeral navigation indexes derived from canonical graph state. */ }
        perform action putAnchor[0..*] : PutAnchor; perform action putDataObject[0..*] : PutDataObject; perform action putLink[0..*] : PutLink;
        perform action associateData[0..*] : AssociateData; perform action dissociateData[0..*] : DissociateData;
        perform action deleteAnchor[0..*] : DeleteAnchor; perform action deleteDataObject[0..*] : DeleteDataObject; perform action deleteLink[0..*] : DeleteLink;
        perform action previewDeleteAnchor[0..*] : PreviewDeleteAnchor { doc /* compute exact anchor cascade without mutation. */ }
        perform action previewDeleteDataObject[0..*] : PreviewDeleteDataObject { doc /* compute exact data cascade without mutation. */ }
        perform action previewDissociateData[0..*] : PreviewDissociateData { doc /* compute exact dissociation cascade without mutation. */ }
        dependency putAnchorState from putAnchor to anchors { @StateAccess { kind = StateAccessKind::write; } doc /* atomically create/replace anchor and maintain indexes. */ }
        dependency putDataState from putDataObject to dataObjects { @StateAccess { kind = StateAccessKind::write; } doc /* atomically create/replace data, associations, and indexes. */ }
        dependency putLinkState from putLink to links { @StateAccess { kind = StateAccessKind::write; } doc /* atomically create/replace link and indexes. */ }
        dependency associateState from associateData to anchorDataAssociations { @StateAccess { kind = StateAccessKind::write; } doc /* idempotently add symmetric direct association. */ }
        dependency dissociateState from dissociateData to anchorDataAssociations { @StateAccess { kind = StateAccessKind::write; } doc /* remove association and complete cascade atomically. */ }
        dependency deleteAnchorState from deleteAnchor to anchors { @StateAccess { kind = StateAccessKind::delete; } doc /* remove anchor and complete cascade atomically. */ }
        dependency deleteDataState from deleteDataObject to dataObjects { @StateAccess { kind = StateAccessKind::delete; } doc /* remove data and complete cascade atomically. */ }
        dependency deleteLinkState from deleteLink to links { @StateAccess { kind = StateAccessKind::delete; } doc /* remove exactly one link and index entries. */ }
        dependency exportSnapshotState from exportSnapshot to anchors { @StateAccess { kind = StateAccessKind::read; } doc /* read all canonical records, associations, and their stable identities without mutation. */ }
        dependency getObjectState from getObject to anchors { @StateAccess { kind = StateAccessKind::read; } doc /* read the one global object namespace across anchors, data objects, and links. */ }
        dependency listByTypeState from listByType to derivedIndexes { @StateAccess { kind = StateAccessKind::read; } doc /* read the derived type index and canonical records without mutation. */ }
        dependency listAnchorDataState from listAnchorData to anchorDataAssociations { @StateAccess { kind = StateAccessKind::read; } doc /* read direct anchor-to-data associations without mutation. */ }
        dependency listDataAnchorsState from listDataAnchors to anchorDataAssociations { @StateAccess { kind = StateAccessKind::read; } doc /* read inverse direct associations without mutation. */ }
        dependency listIncidentLinksState from listIncidentLinks to derivedIndexes { @StateAccess { kind = StateAccessKind::read; } doc /* read incident-link indexes and canonical links without mutation. */ }
        dependency countByTypeState from countByType to derivedIndexes { @StateAccess { kind = StateAccessKind::read; } doc /* derive deterministic counts without mutation. */ }
        dependency previewDeleteAnchorState from previewDeleteAnchor to anchors { @StateAccess { kind = StateAccessKind::read; } doc /* compute the exact cascade from current canonical state with no state effect. */ }
        dependency previewDeleteDataState from previewDeleteDataObject to dataObjects { @StateAccess { kind = StateAccessKind::read; } doc /* compute the exact cascade from current canonical state with no state effect. */ }
        dependency previewDissociateState from previewDissociateData to anchorDataAssociations { @StateAccess { kind = StateAccessKind::read; } doc /* compute the exact dissociation cascade from current canonical state with no state effect. */ }
    }

    action def CreateEmptyRtgGraph { out part graph : RtgGraph; doc /* Return an empty graph with empty canonical state and derived indexes. */ @FailureContract { errorIds = (); } }
    action def ImportRtgGraphSnapshot { in 'snapshot' : RtgGraphSnapshot; out part graph : RtgGraph; doc /* Validate the whole snapshot, normalize live metadata, rebuild all derived indexes, and expose no partial graph. */ @FailureContract { errorIds = ("RtgGraphSnapshotInvalid", "RtgGraphUuidInvalid", "RtgGraphUuidConflict", "RtgGraphReferenceInvalid", "RtgGraphTypeInvalid", "RtgGraphTypeKindConflict", "RtgGraphJsonValueInvalid", "RtgGraphSystemValueInvalid"); } }


    requirement <'contract.rtg.graph.put_effect'> putEffect {
        subject graph : RtgGraph;
        require constraint {
            doc /* Puts generate a UUID when omitted, preserve a supplied valid UUID, normalize missing system.live to true, fully replace the named record fields, preserve unrelated records, and atomically maintain associations and indexes. */
        }
    }

    requirement <'contract.rtg.graph.association_effect'> associationEffect {
        subject graph : RtgGraph;
        require constraint {
            doc /* Association is a direct identity-free many-to-many relation. Repeated association is idempotent; removing the last anchor grounds deletion of the data object and its incident links. */
        }
    }

    requirement <'contract.rtg.graph.delete_effect'> deleteEffect {
        subject graph : RtgGraph;
        require constraint {
            doc /* Deletes return the complete cascade with always-present result lists and leave no dangling links or associations; rejected deletes have no effect. */
        }
    }

    requirement <'contract.rtg.graph.preview_effect'> previewEffect {
        subject graph : RtgGraph;
        require constraint {
            doc /* Each preview returns exactly the cascade the paired mutation would produce from the same state and changes no canonical or derived state. */
        }
    }

    requirement <'contract.rtg.graph.snapshot_effect'> snapshotEffect {
        subject graph : RtgGraph;
        require constraint {
            doc /* Export preserves UUIDs, types, endpoints, properties, system metadata, and direct associations without filtering. Import validates the whole candidate and rebuilds derived indexes. */
        }
    }

    requirement <'invariant.rtg.graph.global_uuid_uniqueness'> globalUuidUniqueness {
        subject graph : RtgGraph;
        require constraint {
            doc /* UUIDs are globally unique across graph object kinds. */
        }
    }

    requirement <'invariant.rtg.graph.well_formed_uuids'> wellFormedUuids {
        subject graph : RtgGraph;
        require constraint {
            doc /* Every stored identity is a well-formed UUID. */
        }
    }

    requirement <'invariant.rtg.graph.uuid_generation'> uuidGeneration {
        subject graph : RtgGraph;
        require constraint {
            doc /* Generated identities are UUIDs and valid caller identities are preserved. */
        }
    }

    requirement <'invariant.rtg.graph.well_formed_types'> wellFormedTypes {
        subject graph : RtgGraph;
        require constraint {
            doc /* Every object has a non-empty type key. */
        }
    }

    requirement <'invariant.rtg.graph.single_global_type_namespace'> singleGlobalTypeNamespace {
        subject graph : RtgGraph;
        require constraint {
            doc /* A type key belongs to only one object kind. */
        }
    }

    requirement <'invariant.rtg.graph.many_to_many_data_association'> manyToManyDataAssociation {
        subject graph : RtgGraph;
        require constraint {
            doc /* Anchors and data objects support direct many-to-many association. */
        }
    }

    requirement <'invariant.rtg.graph.no_unassociated_data_objects'> noUnassociatedDataObjects {
        subject graph : RtgGraph;
        require constraint {
            doc /* Every stored data object has at least one anchor. */
        }
    }

    requirement <'invariant.rtg.graph.association_indexes_reference_existing_objects'> associationIndexesReferenceExistingObjects {
        subject graph : RtgGraph;
        require constraint {
            doc /* Associations reference existing anchors and data objects. */
        }
    }

    requirement <'invariant.rtg.graph.no_association_objects'> noAssociationObjects {
        subject graph : RtgGraph;
        require constraint {
            doc /* Direct associations have no object identity, type, metadata, or link representation. */
        }
    }

    requirement <'invariant.rtg.graph.valid_link_endpoints'> validLinkEndpoints {
        subject graph : RtgGraph;
        require constraint {
            doc /* Link endpoints exist and are anchors or data objects. */
        }
    }

    requirement <'invariant.rtg.graph.no_dangling_references_after_delete'> noDanglingReferencesAfterDelete {
        subject graph : RtgGraph;
        require constraint {
            doc /* Deletes leave no dangling association or link references. */
        }
    }

    requirement <'invariant.rtg.graph.no_link_to_link_edges'> noLinkToLinkEdges {
        subject graph : RtgGraph;
        require constraint {
            doc /* Links cannot be link endpoints. */
        }
    }

    requirement <'invariant.rtg.graph.type_indexes_match_canonical_maps'> typeIndexesMatchCanonicalMaps {
        subject graph : RtgGraph;
        require constraint {
            doc /* Derived type indexes equal canonical object membership. */
        }
    }

    requirement <'invariant.rtg.graph.association_indexes_are_symmetric'> associationIndexesAreSymmetric {
        subject graph : RtgGraph;
        require constraint {
            doc /* Both direct association directions agree. */
        }
    }

    requirement <'invariant.rtg.graph.incident_link_indexes_match_canonical_links'> incidentLinkIndexesMatchCanonicalLinks {
        subject graph : RtgGraph;
        require constraint {
            doc /* Incident-link indexes derive exactly from canonical links. */
        }
    }

    requirement <'invariant.rtg.graph.json_serializable_property_stores'> jsonSerializablePropertyStores {
        subject graph : RtgGraph;
        require constraint {
            doc /* Properties and system metadata are JSON-safe. */
        }
    }

    requirement <'invariant.rtg.graph.system_live_boolean'> systemLiveBoolean {
        subject graph : RtgGraph;
        require constraint {
            doc /* Missing system.live normalizes to true and supplied live is Boolean. */
        }
    }

    requirement <'invariant.rtg.graph.schema_neutrality'> schemaNeutrality {
        subject graph : RtgGraph;
        require constraint {
            doc /* Graph storage does not enforce application schema or ontology meaning. */
        }
    }

    requirement <'invariant.rtg.graph.anchor_display_name_non_authoritative'> anchorDisplayNameNonAuthoritative {
        subject graph : RtgGraph;
        require constraint {
            doc /* Display name is optional, non-unique, and not identity. */
        }
    }

    requirement <'invariant.rtg.graph.unfiltered_reads'> unfilteredReads {
        subject graph : RtgGraph;
        require constraint {
            doc /* Base reads never hide objects by live status, visibility, role, or publication. */
        }
    }

    requirement <'invariant.rtg.graph.type_counts_match_canonical_maps'> typeCountsMatchCanonicalMaps {
        subject graph : RtgGraph;
        require constraint {
            doc /* Counts derive from canonical records and explicit kind/live filters. */
        }
    }

    requirement <'invariant.rtg.graph.mutation_atomicity'> mutationAtomicity {
        subject graph : RtgGraph;
        require constraint {
            doc /* Each mutation preserves every graph invariant or has no effect. */
        }
    }

    requirement <'invariant.rtg.graph.preview_matches_delete'> previewMatchesDelete {
        subject graph : RtgGraph;
        require constraint {
            doc /* Preview cascades match their corresponding mutations. */
        }
    }

    requirement <'contract.rtg.graph.export_graph_snapshot.failures'> exportGraphSnapshotFailureSemantics {
        subject operation : ExportGraphSnapshot;
        require constraint {
            doc /* Export has no declared domain failure. */
        }
    }

    requirement <'contract.rtg.graph.put_anchor.failures'> putAnchorFailureSemantics {
        subject operation : PutAnchor;
        require constraint {
            doc /* Rejected writes have no effect. */
        }
    }

    requirement <'contract.rtg.graph.put_data_object.failures'> putDataObjectFailureSemantics {
        subject operation : PutDataObject;
        require constraint {
            doc /* Rejected writes change neither records nor indexes. */
        }
    }

    requirement <'contract.rtg.graph.put_link.failures'> putLinkFailureSemantics {
        subject operation : PutLink;
        require constraint {
            doc /* Rejected writes change neither links nor incident indexes. */
        }
    }

    requirement <'contract.rtg.graph.associate_data.failures'> associateDataFailureSemantics {
        subject operation : AssociateData;
        require constraint {
            doc /* Failure has no effect. */
        }
    }

    requirement <'contract.rtg.graph.dissociate_data.failures'> dissociateDataFailureSemantics {
        subject operation : DissociateData;
        require constraint {
            doc /* Failure has no effect. */
        }
    }

    requirement <'contract.rtg.graph.delete_anchor.failures'> deleteAnchorFailureSemantics {
        subject operation : DeleteAnchor;
        require constraint {
            doc /* Failure has no effect and success leaves no dangling reference. */
        }
    }

    requirement <'contract.rtg.graph.delete_data_object.failures'> deleteDataObjectFailureSemantics {
        subject operation : DeleteDataObject;
        require constraint {
            doc /* Failure has no effect. */
        }
    }

    requirement <'contract.rtg.graph.delete_link.failures'> deleteLinkFailureSemantics {
        subject operation : DeleteLink;
        require constraint {
            doc /* Failure has no effect. */
        }
    }

    requirement <'contract.rtg.graph.preview_delete_anchor.failures'> previewDeleteAnchorFailureSemantics {
        subject operation : PreviewDeleteAnchor;
        require constraint {
            doc /* Success and failure are state-neutral. */
        }
    }

    requirement <'contract.rtg.graph.preview_delete_data_object.failures'> previewDeleteDataObjectFailureSemantics {
        subject operation : PreviewDeleteDataObject;
        require constraint {
            doc /* Success and failure are state-neutral. */
        }
    }

    requirement <'contract.rtg.graph.preview_dissociate_data.failures'> previewDissociateDataFailureSemantics {
        subject operation : PreviewDissociateData;
        require constraint {
            doc /* Success and failure are state-neutral. */
        }
    }

    requirement <'contract.rtg.graph.get_graph_object.failures'> getGraphObjectFailureSemantics {
        subject operation : GetGraphObject;
        require constraint {
            doc /* Read failure has no effect. */
        }
    }

    requirement <'contract.rtg.graph.list_graph_objects_by_type.failures'> listGraphObjectsByTypeFailureSemantics {
        subject operation : ListGraphObjectsByType;
        require constraint {
            doc /* Read failure has no effect. */
        }
    }

    requirement <'contract.rtg.graph.list_anchor_data.failures'> listAnchorDataFailureSemantics {
        subject operation : ListAnchorData;
        require constraint {
            doc /* Read failure has no effect. */
        }
    }

    requirement <'contract.rtg.graph.list_data_anchors.failures'> listDataAnchorsFailureSemantics {
        subject operation : ListDataAnchors;
        require constraint {
            doc /* Read failure has no effect. */
        }
    }

    requirement <'contract.rtg.graph.list_incident_links.failures'> listIncidentLinksFailureSemantics {
        subject operation : ListIncidentLinks;
        require constraint {
            doc /* Invalid direction is rejected before reading and failure has no effect. */
        }
    }

    requirement <'contract.rtg.graph.count_graph_objects_by_type.failures'> countGraphObjectsByTypeFailureSemantics {
        subject operation : CountGraphObjectsByType;
        require constraint {
            doc /* Read failure has no effect. */
        }
    }

    requirement <'contract.rtg.graph.create_empty_rtg_graph.failures'> createEmptyRtgGraphFailureSemantics {
        subject operation : CreateEmptyRtgGraph;
        require constraint {
            doc /* Construction has no declared domain failure. */
        }
    }

    requirement <'contract.rtg.graph.import_rtg_graph_snapshot.failures'> importRtgGraphSnapshotFailureSemantics {
        subject operation : ImportRtgGraphSnapshot;
        require constraint {
            doc /* Failure returns no partially reconstructed graph. */
        }
    }

    part contractContext {
        part graph : RtgGraph;
        satisfy putEffect by graph;
        satisfy associationEffect by graph;
        satisfy deleteEffect by graph;
        satisfy previewEffect by graph;
        satisfy snapshotEffect by graph;
        satisfy globalUuidUniqueness by graph;
        satisfy wellFormedUuids by graph;
        satisfy uuidGeneration by graph;
        satisfy wellFormedTypes by graph;
        satisfy singleGlobalTypeNamespace by graph;
        satisfy manyToManyDataAssociation by graph;
        satisfy noUnassociatedDataObjects by graph;
        satisfy associationIndexesReferenceExistingObjects by graph;
        satisfy noAssociationObjects by graph;
        satisfy validLinkEndpoints by graph;
        satisfy noDanglingReferencesAfterDelete by graph;
        satisfy noLinkToLinkEdges by graph;
        satisfy typeIndexesMatchCanonicalMaps by graph;
        satisfy associationIndexesAreSymmetric by graph;
        satisfy incidentLinkIndexesMatchCanonicalLinks by graph;
        satisfy jsonSerializablePropertyStores by graph;
        satisfy systemLiveBoolean by graph;
        satisfy schemaNeutrality by graph;
        satisfy anchorDisplayNameNonAuthoritative by graph;
        satisfy unfilteredReads by graph;
        satisfy typeCountsMatchCanonicalMaps by graph;
        satisfy mutationAtomicity by graph;
        satisfy previewMatchesDelete by graph;

        satisfy exportGraphSnapshotFailureSemantics by graph.exportSnapshot;
        satisfy putAnchorFailureSemantics by graph.putAnchor;
        satisfy putDataObjectFailureSemantics by graph.putDataObject;
        satisfy putLinkFailureSemantics by graph.putLink;
        satisfy associateDataFailureSemantics by graph.associateData;
        satisfy dissociateDataFailureSemantics by graph.dissociateData;
        satisfy deleteAnchorFailureSemantics by graph.deleteAnchor;
        satisfy deleteDataObjectFailureSemantics by graph.deleteDataObject;
        satisfy deleteLinkFailureSemantics by graph.deleteLink;
        satisfy previewDeleteAnchorFailureSemantics by graph.previewDeleteAnchor;
        satisfy previewDeleteDataObjectFailureSemantics by graph.previewDeleteDataObject;
        satisfy previewDissociateDataFailureSemantics by graph.previewDissociateData;
        satisfy getGraphObjectFailureSemantics by graph.getObject;
        satisfy listGraphObjectsByTypeFailureSemantics by graph.listByType;
        satisfy listAnchorDataFailureSemantics by graph.listAnchorData;
        satisfy listDataAnchorsFailureSemantics by graph.listDataAnchors;
        satisfy listIncidentLinksFailureSemantics by graph.listIncidentLinks;
        satisfy countGraphObjectsByTypeFailureSemantics by graph.countByType;
        action createEmptyRtgGraphSubject : CreateEmptyRtgGraph;
        satisfy createEmptyRtgGraphFailureSemantics by createEmptyRtgGraphSubject;
        action importRtgGraphSnapshotSubject : ImportRtgGraphSnapshot;
        satisfy importRtgGraphSnapshotFailureSemantics by importRtgGraphSnapshotSubject;
    }
    verification def ExportGraphSnapshotContractVerification {
        subject operation : ExportGraphSnapshot;
        objective { verify exportGraphSnapshotFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#ExportGraphSnapshotContractVerification"; implementationScope = "InMemoryRtgGraph"; }
    }

    verification def PutAnchorContractVerification {
        subject operation : PutAnchor;
        objective { verify putAnchorFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#PutAnchorContractVerification"; implementationScope = "InMemoryRtgGraph"; }
    }

    verification def PutDataObjectContractVerification {
        subject operation : PutDataObject;
        objective { verify putDataObjectFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#PutDataObjectContractVerification"; implementationScope = "InMemoryRtgGraph"; }
    }

    verification def PutLinkContractVerification {
        subject operation : PutLink;
        objective { verify putLinkFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#PutLinkContractVerification"; implementationScope = "InMemoryRtgGraph"; }
    }

    verification def AssociateDataContractVerification {
        subject operation : AssociateData;
        objective { verify associateDataFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#AssociateDataContractVerification"; implementationScope = "InMemoryRtgGraph"; }
    }

    verification def DissociateDataContractVerification {
        subject operation : DissociateData;
        objective { verify dissociateDataFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#DissociateDataContractVerification"; implementationScope = "InMemoryRtgGraph"; }
    }

    verification def DeleteAnchorContractVerification {
        subject operation : DeleteAnchor;
        objective { verify deleteAnchorFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#DeleteAnchorContractVerification"; implementationScope = "InMemoryRtgGraph"; }
    }

    verification def DeleteDataObjectContractVerification {
        subject operation : DeleteDataObject;
        objective { verify deleteDataObjectFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#DeleteDataObjectContractVerification"; implementationScope = "InMemoryRtgGraph"; }
    }

    verification def DeleteLinkContractVerification {
        subject operation : DeleteLink;
        objective { verify deleteLinkFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#DeleteLinkContractVerification"; implementationScope = "InMemoryRtgGraph"; }
    }

    verification def PreviewDeleteAnchorContractVerification {
        subject operation : PreviewDeleteAnchor;
        objective { verify previewDeleteAnchorFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#PreviewDeleteAnchorContractVerification"; implementationScope = "InMemoryRtgGraph"; }
    }

    verification def PreviewDeleteDataObjectContractVerification {
        subject operation : PreviewDeleteDataObject;
        objective { verify previewDeleteDataObjectFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#PreviewDeleteDataObjectContractVerification"; implementationScope = "InMemoryRtgGraph"; }
    }

    verification def PreviewDissociateDataContractVerification {
        subject operation : PreviewDissociateData;
        objective { verify previewDissociateDataFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#PreviewDissociateDataContractVerification"; implementationScope = "InMemoryRtgGraph"; }
    }

    verification def GetGraphObjectContractVerification {
        subject operation : GetGraphObject;
        objective { verify getGraphObjectFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#GetGraphObjectContractVerification"; implementationScope = "InMemoryRtgGraph"; }
    }

    verification def ListGraphObjectsByTypeContractVerification {
        subject operation : ListGraphObjectsByType;
        objective { verify listGraphObjectsByTypeFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#ListGraphObjectsByTypeContractVerification"; implementationScope = "InMemoryRtgGraph"; }
    }

    verification def ListAnchorDataContractVerification {
        subject operation : ListAnchorData;
        objective { verify listAnchorDataFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#ListAnchorDataContractVerification"; implementationScope = "InMemoryRtgGraph"; }
    }

    verification def ListDataAnchorsContractVerification {
        subject operation : ListDataAnchors;
        objective { verify listDataAnchorsFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#ListDataAnchorsContractVerification"; implementationScope = "InMemoryRtgGraph"; }
    }

    verification def ListIncidentLinksContractVerification {
        subject operation : ListIncidentLinks;
        objective { verify listIncidentLinksFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#ListIncidentLinksContractVerification"; implementationScope = "InMemoryRtgGraph"; }
    }

    verification def CountGraphObjectsByTypeContractVerification {
        subject operation : CountGraphObjectsByType;
        objective { verify countGraphObjectsByTypeFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#CountGraphObjectsByTypeContractVerification"; implementationScope = "InMemoryRtgGraph"; }
    }

    verification def CreateEmptyRtgGraphContractVerification {
        subject operation : CreateEmptyRtgGraph;
        objective { verify createEmptyRtgGraphFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#CreateEmptyRtgGraphContractVerification"; implementationScope = "InMemoryRtgGraph"; }
    }

    verification def ImportRtgGraphSnapshotContractVerification {
        subject operation : ImportRtgGraphSnapshot;
        objective { verify importRtgGraphSnapshotFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#ImportRtgGraphSnapshotContractVerification"; implementationScope = "InMemoryRtgGraph"; }
    }



    verification def RtgGraphBoundaryVerification {
        subject graph : RtgGraph;
        objective {
            verify putEffect; verify associationEffect; verify deleteEffect; verify previewEffect; verify snapshotEffect;
            verify globalUuidUniqueness; verify wellFormedUuids; verify uuidGeneration; verify wellFormedTypes;
            verify singleGlobalTypeNamespace; verify manyToManyDataAssociation; verify noUnassociatedDataObjects;
            verify associationIndexesReferenceExistingObjects; verify noAssociationObjects; verify validLinkEndpoints;
            verify noDanglingReferencesAfterDelete; verify noLinkToLinkEdges; verify typeIndexesMatchCanonicalMaps;
            verify associationIndexesAreSymmetric; verify incidentLinkIndexesMatchCanonicalLinks;
            verify jsonSerializablePropertyStores; verify systemLiveBoolean; verify schemaNeutrality;
            verify anchorDisplayNameNonAuthoritative; verify unfilteredReads; verify typeCountsMatchCanonicalMaps;
            verify mutationAtomicity; verify previewMatchesDelete;
        }
        @EvidenceBinding { evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py#RtgGraphBoundaryVerification"; implementationScope = "InMemoryRtgGraph"; }
    }
}
