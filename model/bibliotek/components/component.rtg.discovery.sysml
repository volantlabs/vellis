library package BibliotekRtgDiscovery {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;

    doc /* Draft registry of knowledge-engineer-curated, two-dimensional type-discovery views. */

    attribute def RtgDiscoveryCoordinates { attribute rowKey : String; attribute columnKey : String; }
    attribute def RtgDiscoveryCell { attribute rowKey : String; attribute columnKey : String; attribute description : String; attribute anchorTypeKeys[0..*] : String; }
    item def RtgDiscoveryView {
        attribute viewId : String;
        attribute description : String;
        attribute rowLabels : JsonObject;
        attribute columnLabels : JsonObject;
        attribute cells[0..*] : RtgDiscoveryCell;
        attribute metadata : JsonObject;
        doc /* viewId is stable identity; label objects map coordinate keys to human-readable labels. Each coordinate is unique and every cell uses declared row and column keys. */
    }
    attribute def RtgDiscoverySelection { attribute viewId : String; attribute coordinates[1..*] : RtgDiscoveryCoordinates; attribute anchorTypeKeys[0..*] : String; attribute cellDescriptions : JsonObject; }
    attribute def RtgDiscoveryViewList { attribute views[0..*] : RtgDiscoveryView; }
    attribute def RtgDiscoveryViewInvalid { attribute message : String; attribute diagnostic : JsonObject; }
    attribute def RtgDiscoveryViewNotFound { attribute message : String; attribute diagnostic : JsonObject; }
    attribute def RtgDiscoverySelectionInvalid { attribute message : String; attribute diagnostic : JsonObject; }

    action def PutDiscoveryView {
        in view : RtgDiscoveryView;
        out stored : RtgDiscoveryView;
        doc /* Validate and create or completely replace the view with the same viewId. Anchor type keys remain opaque and are not checked against schema. */
        @FailureContract { errorIds = ("RtgDiscoveryViewInvalid"); obligation = "Invalid identity, labels, or duplicate/unknown cell coordinates leave the prior registry unchanged."; }
    }
    action def ListDiscoveryViews {
        out result : RtgDiscoveryViewList;
        doc /* Return full curated views in ascending viewId order without mutation. */
        @FailureContract { errorIds = (); obligation = "This read has no state effect."; }
    }
    action def SelectDiscoveryAnchorTypes {
        in viewId : String;
        in coordinates[1..*] : RtgDiscoveryCoordinates;
        out result : RtgDiscoverySelection;
        doc /* Preserve requested coordinates and return the first-occurrence, de-duplicated anchor type keys plus coordinate-to-description mapping for the selected cells. */
        @FailureContract { errorIds = ("RtgDiscoveryViewNotFound", "RtgDiscoverySelectionInvalid"); obligation = "Unknown views, duplicate/unknown coordinates, or empty selections have no state effect."; }
    }

    part def RtgDiscovery {
        doc /* Own curated navigation metadata while remaining independent of schema contents, graph population, query execution, and transports. */
        @SpecIdentity { id = "component.rtg.discovery"; lifecycleStatus = SpecLifecycle::draft; owner = "humans"; }
        @DependencyPolicy { allowedComponentIds = (); forbiddenComponentIds = ("component.rtg.graph", "component.rtg.schema", "component.rtg.query", "component.rtg.controller"); }
        item curatedViews[0..*] : RtgDiscoveryView { @StateAuthority { authority = StateAuthorityKind::canonicalOwner; lifetime = StateLifetime::componentCoupled; persistence = StatePersistence::unspecified; } }
        perform action putView[0..*] : PutDiscoveryView;
        perform action listViews[0..*] : ListDiscoveryViews;
        perform action selectAnchorTypes[0..*] : SelectDiscoveryAnchorTypes;
        dependency putState from putView to curatedViews { @StateAccess { kind = StateAccessKind::write; effect = "create or fully replace one valid view atomically"; } }
        dependency listState from listViews to curatedViews { @StateAccess { kind = StateAccessKind::read; effect = "return full views in view-ID order without mutation"; } }
        dependency selectState from selectAnchorTypes to curatedViews { @StateAccess { kind = StateAccessKind::read; effect = "return the stable union and descriptions of selected cells without mutation"; } }
    }
    action def CreateEmptyRtgDiscovery {
        out part discovery : RtgDiscovery;
        doc /* Return a registry with no curated views. */
        @FailureContract { errorIds = (); obligation = "Construction has no external side effect."; }
    }

    requirement viewValidity { subject operation : PutDiscoveryView; doc /* viewId and label keys are non-empty; row and column label values are strings; each cell coordinate is unique and refers to declared labels; all metadata and descriptions are JSON-safe and anchor type keys preserve caller order. */ @StableId { id = "contract.rtg.discovery.view_validity"; } }
    requirement replacementEffect { subject operation : PutDiscoveryView; doc /* A valid put stores exactly the supplied view under viewId, replacing any prior version atomically and leaving other views unchanged. */ @StableId { id = "contract.rtg.discovery.replacement"; } }
    requirement selectionEffect { subject operation : SelectDiscoveryAnchorTypes; doc /* Selection requires an existing view and one or more unique existing coordinates. Results preserve coordinate order, de-duplicate anchor keys by first occurrence, and include descriptions keyed without coordinate ambiguity. */ @StableId { id = "contract.rtg.discovery.selection"; } }
    requirement deterministicReads { subject discovery : RtgDiscovery; doc /* Listing is ordered by viewId; selection is ordered by request coordinates and cell anchor-key order. Reads never mutate curatedViews. */ @StableId { id = "contract.rtg.discovery.deterministic_reads"; } }
    requirement viewsNotSchema { subject discovery : RtgDiscovery; doc /* Views organize opaque type keys but do not define or validate schema. */ @StableId { id = "invariant.rtg.discovery.views_not_schema"; } }
    requirement noGraphDependency { subject discovery : RtgDiscovery; doc /* Selection does not require graph objects or population counts. */ @StableId { id = "invariant.rtg.discovery.no_graph_dependency"; } }
    requirement knowledgeEngineerCurated { subject discovery : RtgDiscovery; doc /* Curated views are explicit knowledge-engineering records, not inferred search results. */ @StableId { id = "invariant.rtg.discovery.knowledge_engineer_curated"; } }

    verification def RtgDiscoveryBoundaryVerification {
        subject discovery : RtgDiscovery;
        objective { verify viewValidity; verify replacementEffect; verify selectionEffect; verify deterministicReads; verify viewsNotSchema; verify noGraphDependency; verify knowledgeEngineerCurated; }
        @EvidenceBinding { verificationId = "verification.rtg.discovery.boundary"; evidenceId = "pending"; implementationScope = "unimplemented-draft"; }
    }
}
