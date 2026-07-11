library package BibliotekRtgGraph {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;

    enum def RtgObjectKind {
        enum anchor;
        enum dataObject { @ExternalName { name = "data_object"; } }
        enum link;
    }
    enum def RtgLinkDirection { enum source; enum target; enum both; }

    attribute def RtgSystem :> JsonObject {
        attribute live[0..1] : Boolean = true;
        doc /* JSON-safe caller metadata. Missing live normalizes to true; when supplied it is Boolean. Other keys are preserved without component-assigned meaning. */
    }
    item def RtgObject {
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

    attribute def RtgGraphSnapshotInvalid { attribute message : String; }
    attribute def RtgGraphUuidInvalid { attribute message : String; }
    attribute def RtgGraphUuidConflict { attribute message : String; }
    attribute def RtgGraphReferenceInvalid { attribute message : String; }
    attribute def RtgGraphTypeInvalid { attribute message : String; }
    attribute def RtgGraphTypeKindConflict { attribute message : String; }
    attribute def RtgGraphJsonValueInvalid { attribute message : String; }
    attribute def RtgGraphSystemValueInvalid { attribute message : String; }
    attribute def RtgGraphAnchorNotFound { attribute message : String; }
    attribute def RtgGraphDataObjectNotFound { attribute message : String; }
    attribute def RtgGraphLinkNotFound { attribute message : String; }
    attribute def RtgGraphEndpointNotFound { attribute message : String; }
    attribute def RtgGraphAnchorDataIndexEntryNotFound { attribute message : String; }
    attribute def RtgGraphObjectNotFound { attribute message : String; }

    action def ExportGraphSnapshot {
        out snapshot : RtgGraphSnapshot;
        doc /* Return the complete unfiltered graph state without mutation. */
        @FailureContract { errorIds = (); obligation = "Export has no declared domain failure."; }
    }
    action def PutAnchor {
        in anchor : RtgAnchor; out stored : RtgAnchor;
        doc /* Create or fully replace one anchor while preserving its associations and incident links. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphUuidConflict", "RtgGraphTypeInvalid", "RtgGraphTypeKindConflict", "RtgGraphSystemValueInvalid"); obligation = "Rejected writes have no effect."; }
    }
    action def PutDataObject {
        in dataObject : RtgDataObject; in anchorUuids[1..*] : Uuid; out stored : RtgDataObject;
        doc /* Create or fully replace one data object and replace its complete direct anchor association set. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphUuidConflict", "RtgGraphAnchorNotFound", "RtgGraphTypeInvalid", "RtgGraphTypeKindConflict", "RtgGraphJsonValueInvalid", "RtgGraphSystemValueInvalid"); obligation = "Rejected writes change neither records nor indexes."; }
    }
    action def PutLink {
        in link : RtgLink; out stored : RtgLink;
        doc /* Create or fully replace one directed typed link between existing non-link endpoints. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphUuidConflict", "RtgGraphEndpointNotFound", "RtgGraphTypeInvalid", "RtgGraphTypeKindConflict", "RtgGraphSystemValueInvalid"); obligation = "Rejected writes change neither links nor incident indexes."; }
    }
    action def AssociateData {
        in anchorUuid : Uuid; in dataUuid : Uuid;
        doc /* Idempotently add one direct anchor-data association. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphAnchorNotFound", "RtgGraphDataObjectNotFound"); obligation = "Failure has no effect."; }
    }
    action def DissociateData {
        in anchorUuid : Uuid; in dataUuid : Uuid; out result : RtgGraphDeleteResult;
        doc /* Remove one association and delete the data object plus incident links if it becomes ungrounded. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphAnchorNotFound", "RtgGraphDataObjectNotFound", "RtgGraphAnchorDataIndexEntryNotFound"); obligation = "Failure has no effect."; }
    }
    action def DeleteAnchor {
        in anchorUuid : Uuid; out result : RtgGraphDeleteResult;
        doc /* Delete one anchor, its incident links, its associations, and data left with no anchors. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphAnchorNotFound"); obligation = "Failure has no effect and success leaves no dangling reference."; }
    }
    action def DeleteDataObject {
        in dataUuid : Uuid; out result : RtgGraphDeleteResult;
        doc /* Delete one data object, its associations, and incident links without deleting anchors. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphDataObjectNotFound"); obligation = "Failure has no effect."; }
    }
    action def DeleteLink {
        in linkUuid : Uuid; out result : RtgGraphDeleteResult;
        doc /* Delete exactly one link without deleting either endpoint. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphLinkNotFound"); obligation = "Failure has no effect."; }
    }
    action def PreviewDeleteAnchor {
        in anchorUuid : Uuid; out result : RtgGraphDeleteResult;
        doc /* Return the exact DeleteAnchor cascade from the same state without mutation. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphAnchorNotFound"); obligation = "Success and failure are state-neutral."; }
    }
    action def PreviewDeleteDataObject {
        in dataUuid : Uuid; out result : RtgGraphDeleteResult;
        doc /* Return the exact DeleteDataObject cascade from the same state without mutation. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphDataObjectNotFound"); obligation = "Success and failure are state-neutral."; }
    }
    action def PreviewDissociateData {
        in anchorUuid : Uuid; in dataUuid : Uuid; out result : RtgGraphDeleteResult;
        doc /* Return the exact DissociateData cascade from the same state without mutation. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphAnchorNotFound", "RtgGraphDataObjectNotFound", "RtgGraphAnchorDataIndexEntryNotFound"); obligation = "Success and failure are state-neutral."; }
    }
    action def GetGraphObject {
        in objectUuid : Uuid; out object : RtgObject;
        doc /* Return an anchor, data object, or link directly by UUID without lifecycle filtering. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphObjectNotFound"); obligation = "Read failure has no effect."; }
    }
    action def ListGraphObjectsByType {
        in objectType : String; out result : RtgObjectList;
        doc /* Return all objects in the global type namespace for one type in stable component order, without lifecycle filtering. */
        @FailureContract { errorIds = ("RtgGraphTypeInvalid"); obligation = "Read failure has no effect."; }
    }
    action def ListAnchorData {
        in anchorUuid : Uuid; out result : RtgDataObjectList;
        doc /* Return directly associated data without lifecycle filtering. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphAnchorNotFound"); obligation = "Read failure has no effect."; }
    }
    action def ListDataAnchors {
        in dataUuid : Uuid; out result : RtgAnchorList;
        doc /* Return directly associated anchors without lifecycle filtering. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphDataObjectNotFound"); obligation = "Read failure has no effect."; }
    }
    action def ListIncidentLinks {
        in objectUuid : Uuid; in direction : RtgLinkDirection = RtgLinkDirection::both; out result : RtgLinkList;
        doc /* Return source, target, or all incident links without lifecycle filtering. */
        @FailureContract { errorIds = ("RtgGraphUuidInvalid", "RtgGraphObjectNotFound"); obligation = "Invalid direction is rejected before reading and failure has no effect."; }
    }
    action def CountGraphObjectsByType {
        in kind[0..1] : RtgObjectKind; in live[0..1] : Boolean; out result : RtgTypeCountList;
        doc /* Return deterministic counts by type with optional object-kind and live-status filters. */
        @FailureContract { errorIds = ("RtgGraphTypeInvalid"); obligation = "Read failure has no effect."; }
    }

    part def RtgGraphReadView {
        perform action exportSnapshot[0..*] : ExportGraphSnapshot { @StateAccess { kind = StateAccessKind::read; effect = "read complete canonical state"; } }
        perform action getObject[0..*] : GetGraphObject { @StateAccess { kind = StateAccessKind::read; effect = "direct unfiltered read"; } }
        perform action listByType[0..*] : ListGraphObjectsByType { @StateAccess { kind = StateAccessKind::read; effect = "read derived type index in stable order"; } }
        perform action listAnchorData[0..*] : ListAnchorData { @StateAccess { kind = StateAccessKind::read; effect = "read direct anchor-data index"; } }
        perform action listDataAnchors[0..*] : ListDataAnchors { @StateAccess { kind = StateAccessKind::read; effect = "read inverse direct association index"; } }
        perform action listIncidentLinks[0..*] : ListIncidentLinks { @StateAccess { kind = StateAccessKind::read; effect = "read derived incident-link index"; } }
        perform action countByType[0..*] : CountGraphObjectsByType { @StateAccess { kind = StateAccessKind::read; effect = "derive counts from canonical records"; } }
    }

    part def RtgGraph :> RtgGraphReadView {
        doc /* Own canonical RTG anchors, data objects, links, direct associations, and derived navigation indexes without schema or lifecycle filtering policy. */
        @SpecIdentity { id = "component.rtg.graph"; lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        @DependencyPolicy { allowedComponentIds = (); forbiddenComponentIds = ("component.rtg.schema", "component.rtg.constraints", "component.rtg.migration", "component.rtg.controller"); }
        item anchors[0..*] : RtgAnchor { @StateAuthority { authority = StateAuthorityKind::canonicalOwner; lifetime = StateLifetime::componentCoupled; persistence = StatePersistence::ephemeral; } }
        item dataObjects[0..*] : RtgDataObject { @StateAuthority { authority = StateAuthorityKind::canonicalOwner; lifetime = StateLifetime::componentCoupled; persistence = StatePersistence::ephemeral; } }
        item links[0..*] : RtgLink { @StateAuthority { authority = StateAuthorityKind::canonicalOwner; lifetime = StateLifetime::componentCoupled; persistence = StatePersistence::ephemeral; } }
        attribute anchorDataAssociations : JsonObject { @StateAuthority { authority = StateAuthorityKind::canonicalOwner; lifetime = StateLifetime::componentCoupled; persistence = StatePersistence::ephemeral; } }
        attribute derivedIndexes : JsonObject { @StateAuthority { authority = StateAuthorityKind::derived; lifetime = StateLifetime::componentCoupled; persistence = StatePersistence::ephemeral; } }
        perform action putAnchor[0..*] : PutAnchor; perform action putDataObject[0..*] : PutDataObject; perform action putLink[0..*] : PutLink;
        perform action associateData[0..*] : AssociateData; perform action dissociateData[0..*] : DissociateData;
        perform action deleteAnchor[0..*] : DeleteAnchor; perform action deleteDataObject[0..*] : DeleteDataObject; perform action deleteLink[0..*] : DeleteLink;
        perform action previewDeleteAnchor[0..*] : PreviewDeleteAnchor { @StateAccess { kind = StateAccessKind::read; effect = "compute exact anchor cascade without mutation"; } }
        perform action previewDeleteDataObject[0..*] : PreviewDeleteDataObject { @StateAccess { kind = StateAccessKind::read; effect = "compute exact data cascade without mutation"; } }
        perform action previewDissociateData[0..*] : PreviewDissociateData { @StateAccess { kind = StateAccessKind::read; effect = "compute exact dissociation cascade without mutation"; } }
        dependency putAnchorState from putAnchor to anchors { @StateAccess { kind = StateAccessKind::write; effect = "atomically create/replace anchor and maintain indexes"; } }
        dependency putDataState from putDataObject to dataObjects { @StateAccess { kind = StateAccessKind::write; effect = "atomically create/replace data, associations, and indexes"; } }
        dependency putLinkState from putLink to links { @StateAccess { kind = StateAccessKind::write; effect = "atomically create/replace link and indexes"; } }
        dependency associateState from associateData to anchorDataAssociations { @StateAccess { kind = StateAccessKind::write; effect = "idempotently add symmetric direct association"; } }
        dependency dissociateState from dissociateData to anchorDataAssociations { @StateAccess { kind = StateAccessKind::delete; effect = "remove association and complete cascade atomically"; } }
        dependency deleteAnchorState from deleteAnchor to anchors { @StateAccess { kind = StateAccessKind::delete; effect = "remove anchor and complete cascade atomically"; } }
        dependency deleteDataState from deleteDataObject to dataObjects { @StateAccess { kind = StateAccessKind::delete; effect = "remove data and complete cascade atomically"; } }
        dependency deleteLinkState from deleteLink to links { @StateAccess { kind = StateAccessKind::delete; effect = "remove exactly one link and index entries"; } }
    }

    action def CreateEmptyRtgGraph { out part graph : RtgGraph; doc /* Return an empty graph with empty canonical state and derived indexes. */ @FailureContract { errorIds = (); obligation = "Construction has no declared domain failure."; } }
    action def ImportRtgGraphSnapshot { in snapshot : RtgGraphSnapshot; out part graph : RtgGraph; doc /* Validate the whole snapshot, normalize live metadata, rebuild all derived indexes, and expose no partial graph. */ @FailureContract { errorIds = ("RtgGraphSnapshotInvalid", "RtgGraphUuidInvalid", "RtgGraphUuidConflict", "RtgGraphReferenceInvalid", "RtgGraphTypeInvalid", "RtgGraphTypeKindConflict", "RtgGraphJsonValueInvalid", "RtgGraphSystemValueInvalid"); obligation = "Failure returns no partially reconstructed graph."; } }

    requirement putEffect { subject graph : RtgGraph; doc /* Puts generate a UUID when omitted, preserve a supplied valid UUID, normalize missing system.live to true, fully replace the named record fields, preserve unrelated records, and atomically maintain associations and indexes. */ @StableId { id = "contract.rtg.graph.put_effect"; } }
    requirement associationEffect { subject graph : RtgGraph; doc /* Association is a direct identity-free many-to-many relation. Repeated association is idempotent; removing the last anchor grounds deletion of the data object and its incident links. */ @StableId { id = "contract.rtg.graph.association_effect"; } }
    requirement deleteEffect { subject graph : RtgGraph; doc /* Deletes return the complete cascade with always-present result lists and leave no dangling links or associations; rejected deletes have no effect. */ @StableId { id = "contract.rtg.graph.delete_effect"; } }
    requirement previewEffect { subject graph : RtgGraph; doc /* Each preview returns exactly the cascade the paired mutation would produce from the same state and changes no canonical or derived state. */ @StableId { id = "contract.rtg.graph.preview_effect"; } }
    requirement snapshotEffect { subject graph : RtgGraph; doc /* Export preserves UUIDs, types, endpoints, properties, system metadata, and direct associations without filtering. Import validates the whole candidate and rebuilds derived indexes. */ @StableId { id = "contract.rtg.graph.snapshot_effect"; } }
    requirement globalUuidUniqueness { subject graph : RtgGraph; doc /* UUIDs are globally unique across graph object kinds. */ @StableId { id = "invariant.rtg.graph.global_uuid_uniqueness"; } }
    requirement wellFormedUuids { subject graph : RtgGraph; doc /* Every stored identity is a well-formed UUID. */ @StableId { id = "invariant.rtg.graph.well_formed_uuids"; } }
    requirement uuidGeneration { subject graph : RtgGraph; doc /* Generated identities are UUIDs and valid caller identities are preserved. */ @StableId { id = "invariant.rtg.graph.uuid_generation"; } }
    requirement wellFormedTypes { subject graph : RtgGraph; doc /* Every object has a non-empty type key. */ @StableId { id = "invariant.rtg.graph.well_formed_types"; } }
    requirement singleGlobalTypeNamespace { subject graph : RtgGraph; doc /* A type key belongs to only one object kind. */ @StableId { id = "invariant.rtg.graph.single_global_type_namespace"; } }
    requirement manyToManyDataAssociation { subject graph : RtgGraph; doc /* Anchors and data objects support direct many-to-many association. */ @StableId { id = "invariant.rtg.graph.many_to_many_data_association"; } }
    requirement noUnassociatedDataObjects { subject graph : RtgGraph; doc /* Every stored data object has at least one anchor. */ @StableId { id = "invariant.rtg.graph.no_unassociated_data_objects"; } }
    requirement associationIndexesReferenceExistingObjects { subject graph : RtgGraph; doc /* Associations reference existing anchors and data objects. */ @StableId { id = "invariant.rtg.graph.association_indexes_reference_existing_objects"; } }
    requirement noAssociationObjects { subject graph : RtgGraph; doc /* Direct associations have no object identity, type, metadata, or link representation. */ @StableId { id = "invariant.rtg.graph.no_association_objects"; } }
    requirement validLinkEndpoints { subject graph : RtgGraph; doc /* Link endpoints exist and are anchors or data objects. */ @StableId { id = "invariant.rtg.graph.valid_link_endpoints"; } }
    requirement noDanglingReferencesAfterDelete { subject graph : RtgGraph; doc /* Deletes leave no dangling association or link references. */ @StableId { id = "invariant.rtg.graph.no_dangling_references_after_delete"; } }
    requirement noLinkToLinkEdges { subject graph : RtgGraph; doc /* Links cannot be link endpoints. */ @StableId { id = "invariant.rtg.graph.no_link_to_link_edges"; } }
    requirement typeIndexesMatchCanonicalMaps { subject graph : RtgGraph; doc /* Derived type indexes equal canonical object membership. */ @StableId { id = "invariant.rtg.graph.type_indexes_match_canonical_maps"; } }
    requirement associationIndexesAreSymmetric { subject graph : RtgGraph; doc /* Both direct association directions agree. */ @StableId { id = "invariant.rtg.graph.association_indexes_are_symmetric"; } }
    requirement incidentLinkIndexesMatchCanonicalLinks { subject graph : RtgGraph; doc /* Incident-link indexes derive exactly from canonical links. */ @StableId { id = "invariant.rtg.graph.incident_link_indexes_match_canonical_links"; } }
    requirement jsonSerializablePropertyStores { subject graph : RtgGraph; doc /* Properties and system metadata are JSON-safe. */ @StableId { id = "invariant.rtg.graph.json_serializable_property_stores"; } }
    requirement systemLiveBoolean { subject graph : RtgGraph; doc /* Missing system.live normalizes to true and supplied live is Boolean. */ @StableId { id = "invariant.rtg.graph.system_live_boolean"; } }
    requirement schemaNeutrality { subject graph : RtgGraph; doc /* Graph storage does not enforce application schema or ontology meaning. */ @StableId { id = "invariant.rtg.graph.schema_neutrality"; } }
    requirement anchorDisplayNameNonAuthoritative { subject graph : RtgGraph; doc /* Display name is optional, non-unique, and not identity. */ @StableId { id = "invariant.rtg.graph.anchor_display_name_non_authoritative"; } }
    requirement unfilteredReads { subject graph : RtgGraph; doc /* Base reads never hide objects by live status, visibility, role, or publication. */ @StableId { id = "invariant.rtg.graph.unfiltered_reads"; } }
    requirement typeCountsMatchCanonicalMaps { subject graph : RtgGraph; doc /* Counts derive from canonical records and explicit kind/live filters. */ @StableId { id = "invariant.rtg.graph.type_counts_match_canonical_maps"; } }
    requirement mutationAtomicity { subject graph : RtgGraph; doc /* Each mutation preserves every graph invariant or has no effect. */ @StableId { id = "invariant.rtg.graph.mutation_atomicity"; } }
    requirement previewMatchesDelete { subject graph : RtgGraph; doc /* Preview cascades match their corresponding mutations. */ @StableId { id = "invariant.rtg.graph.preview_matches_delete"; } }

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
        @EvidenceBinding { verificationId = "verification.rtg.graph.boundary"; evidenceId = "components/rtg/graph/tests/test_rtg_graph_contract.py"; implementationScope = "InMemoryRtgGraph"; }
    }
}
