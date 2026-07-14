library package BibliotekRtgCitationResolution {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;

    doc /* Draft stateless resolver for one graph-qualified citation through one catalog-declared bounded projection. */

    enum def RtgCitationResolutionStatus {
        enum resolved;
        enum not_found;
        enum unsupported;
    }

    attribute def RtgCitationResolutionRequest {
        attribute graphId : String;
        attribute localUuid : Uuid;
        doc /* Canonical graph-qualified citation identity; the UUID has no meaning without graphId. */
    }

    attribute def RtgCitationProjectionSpec {
        attribute graphId : String;
        attribute queryName : String;
        attribute anchorBucket : String;
        doc /* Names the one approved opaque read and returned anchor bucket for a graph. */
    }

    attribute def RtgCitationProjectionRead {
        attribute projection : RtgCitationProjectionSpec;
        attribute rows[0..*] ordered : JsonObject;
        attribute provenance : JsonObject;
        doc /* Bounded projection rows and reader-supplied source provenance. */
    }

    attribute def RtgCitationResolutionRecord {
        attribute status : RtgCitationResolutionStatus;
        attribute graphId : String;
        attribute localUuid : Uuid;
        attribute queryName[0..1] : String;
        attribute anchorBucket[0..1] : String;
        attribute records[0..*] ordered : JsonObject;
        attribute provenance : JsonObject;
        doc /* Resolution outcome whose records are non-empty only when resolved and whose projection identity and provenance are present for resolved and not_found outcomes. */
    }

    attribute def RtgCitationResolutionInvalid { attribute 'message' : String; }

    action def GetCitationProjection {
        in graphId : String;
        out projection[0..1] : RtgCitationProjectionSpec;
        doc /* Return the single declared citation projection for graphId, or absence when the graph does not support citation resolution. */
        @FailureContract { errorIds = (); }
    }

    action def ReadCitationProjection {
        in projection : RtgCitationProjectionSpec;
        out result : RtgCitationProjectionRead;
        doc /* Execute exactly the supplied bounded read-only projection and preserve its identity in the result. */
        @FailureContract { errorIds = (); }
    }

    part def RtgCitationProjectionCatalog {
        doc /* Read-only declaration capability for one bounded citation projection per graph. */
        perform action getProjection[0..*] : GetCitationProjection;
    }

    part def RtgCitationProjectionReader {
        doc /* Read-only executor for an already declared bounded citation projection. */
        perform action readProjection[0..*] : ReadCitationProjection;
    }

    action def ResolveCitation {
        in request : RtgCitationResolutionRequest;
        out result : RtgCitationResolutionRecord;
        doc /* Validate graph-qualified identity, consult the retained catalog, skip the reader when unsupported, otherwise read exactly the declared projection and return only exact anchor UUID matches without mutation. */
        @FailureContract { errorIds = ("RtgCitationResolutionInvalid"); }
    }

    part def <'component.rtg.citation_resolution'> RtgCitationResolver {
        doc /* Resolve bounded graph-local citations while owning no citation, projection, graph, bridge, snapshot, or persistence state. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::draft; owner = "humans"; }

        ref part catalog[1] : RtgCitationProjectionCatalog { doc /* Retained read-only declaration provider supplied at construction. */ }
        ref part reader[1] : RtgCitationProjectionReader { doc /* Retained read-only projection provider supplied at construction. */ }
        perform action resolve[0..*] : ResolveCitation { doc /* Read collaborators only and leave all caller and dependency records unchanged. */ }

        dependency resolveCatalog from resolve to catalog { doc /* Consult exactly the retained catalog for request.graphId before any projection read. */ }
        dependency resolveReader from resolve to reader { doc /* Invoke the retained reader only when the catalog returned one declared projection. */ }
    }

    action def OpenRtgCitationResolver {
        in ref catalog : RtgCitationProjectionCatalog;
        in ref reader : RtgCitationProjectionReader;
        out part resolver : RtgCitationResolver;
        doc /* Bind exactly one projection catalog and one read-only projection reader without opening graph storage or executing a projection. */
        @FailureContract { errorIds = (); }
        bind resolver.catalog = catalog;
        bind resolver.reader = reader;
    }

    requirement <'contract.rtg.citation_resolution.catalog_capability'> catalogCapability {
        subject operation : GetCitationProjection;
        require constraint { doc /* A catalog lookup returns absence or exactly one projection declared for the requested graph and has no graph, projection, or external-storage state effect. */ }
    }
    requirement <'contract.rtg.citation_resolution.reader_capability'> readerCapability {
        subject operation : ReadCitationProjection;
        require constraint { doc /* A reader executes only the supplied opaque projection, returns that projection identity unchanged with JSON-safe rows and provenance, and performs no write. */ }
    }
    requirement <'contract.rtg.citation_resolution.result_semantics'> resultSemantics {
        subject operation : ResolveCitation;
        require constraint { doc /* Unsupported means no catalog declaration and no reader call. Not_found preserves projection identity and provenance with no records. Resolved preserves them and returns every matching row in reader order. */ }
    }
    requirement <'contract.rtg.citation_resolution.dependency_integrity'> dependencyIntegrity {
        subject operation : ResolveCitation;
        require constraint { doc /* The declared projection graphId equals the request graphId; reader output preserves graphId, queryName, and anchorBucket exactly; every row and provenance value is finite JSON; and malformed dependency output is rejected as RtgCitationResolutionInvalid. */ }
    }
    requirement <'invariant.rtg.citation_resolution.graph_qualified_identity'> graphQualifiedIdentity {
        subject resolver : RtgCitationResolver;
        require constraint { doc /* Every resolution requires a non-empty graph identifier and canonical valid graph-local UUID; labels, domain keys, and UUID-only requests are not accepted. */ }
    }
    requirement <'invariant.rtg.citation_resolution.bounded_projection'> boundedProjection {
        subject resolver : RtgCitationResolver;
        require constraint { doc /* Resolution accepts no caller-authored query and reads only the single projection returned by the retained catalog for the named graph. */ }
    }
    requirement <'invariant.rtg.citation_resolution.exact_anchor_match'> exactAnchorMatch {
        subject resolver : RtgCitationResolver;
        require constraint { doc /* Every returned record exposes anchors[anchorBucket] as a valid UUID equal to the requested localUuid; nonmatching rows are never returned. */ }
    }
    requirement <'invariant.rtg.citation_resolution.read_only'> readOnly {
        subject resolver : RtgCitationResolver;
        require constraint { doc /* Resolution mutates no request, projection, row, provenance, graph, descriptor, snapshot, bridge, dependency, or external storage. */ }
    }
    requirement <'invariant.rtg.citation_resolution.provenance_preserved'> provenancePreserved {
        subject resolver : RtgCitationResolver;
        require constraint { doc /* Resolved and not_found outcomes preserve an independent copy of reader-supplied provenance; unsupported outcomes contain empty provenance and no projection identity. */ }
    }
    requirement <'contract.rtg.citation_resolution.intentional_boundary'> intentionalBoundary {
        subject resolver : RtgCitationResolver;
        require constraint { doc /* The component owns no state, infers no graph, chooses no arbitrary query, opens no storage, executes no MCP call, traverses no bridge, merges no identity, joins no graphs, and performs no write. */ }
    }

    requirement <'contract.rtg.citation_resolution.get_projection.failures'> getCitationProjectionFailureSemantics { subject operation : GetCitationProjection; require constraint { doc /* Lookup has no state effect and returns no partial projection record. */ } }
    requirement <'contract.rtg.citation_resolution.read_projection.failures'> readCitationProjectionFailureSemantics { subject operation : ReadCitationProjection; require constraint { doc /* A failed read has no write effect and returns no partial bounded projection record. */ } }
    requirement <'contract.rtg.citation_resolution.resolve.failures'> resolveCitationFailureSemantics { subject operation : ResolveCitation; require constraint { doc /* Malformed identity or dependency output returns no partial resolution and leaves requests, dependencies, and external systems unchanged. */ } }
    requirement <'contract.rtg.citation_resolution.open.failures'> openRtgCitationResolverFailureSemantics { subject operation : OpenRtgCitationResolver; require constraint { doc /* Construction performs no catalog lookup, projection read, graph access, network call, or external side effect. */ } }

    part contractContext {
        part resolver : RtgCitationResolver;
        part catalog : RtgCitationProjectionCatalog;
        part reader : RtgCitationProjectionReader;
        satisfy catalogCapability by catalog.getProjection;
        satisfy readerCapability by reader.readProjection;
        satisfy resultSemantics by resolver.resolve;
        satisfy dependencyIntegrity by resolver.resolve;
        satisfy graphQualifiedIdentity by resolver;
        satisfy boundedProjection by resolver;
        satisfy exactAnchorMatch by resolver;
        satisfy readOnly by resolver;
        satisfy provenancePreserved by resolver;
        satisfy intentionalBoundary by resolver;
        satisfy getCitationProjectionFailureSemantics by catalog.getProjection;
        satisfy readCitationProjectionFailureSemantics by reader.readProjection;
        satisfy resolveCitationFailureSemantics by resolver.resolve;
        action openSubject : OpenRtgCitationResolver;
        satisfy openRtgCitationResolverFailureSemantics by openSubject;
    }

    verification def GetCitationProjectionContractVerification {
        subject operation : GetCitationProjection;
        objective { verify catalogCapability; verify getCitationProjectionFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/citation_resolution/tests/test_rtg_citation_resolution_contract.py#GetCitationProjectionContractVerification"; implementationScope = "RtgCitationProjectionCatalog"; }
    }
    verification def ReadCitationProjectionContractVerification {
        subject operation : ReadCitationProjection;
        objective { verify readerCapability; verify readCitationProjectionFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/citation_resolution/tests/test_rtg_citation_resolution_contract.py#ReadCitationProjectionContractVerification"; implementationScope = "RtgCitationProjectionReader"; }
    }
    verification def ResolveCitationContractVerification {
        subject operation : ResolveCitation;
        objective { verify resultSemantics; verify dependencyIntegrity; verify resolveCitationFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/citation_resolution/tests/test_rtg_citation_resolution_contract.py#ResolveCitationContractVerification"; implementationScope = "DeterministicRtgCitationResolver"; }
    }
    verification def OpenRtgCitationResolverContractVerification {
        subject operation : OpenRtgCitationResolver;
        objective { verify openRtgCitationResolverFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/citation_resolution/tests/test_rtg_citation_resolution_contract.py#OpenRtgCitationResolverContractVerification"; implementationScope = "DeterministicRtgCitationResolver"; }
    }
    verification def RtgCitationResolverBoundaryVerification {
        subject resolver : RtgCitationResolver;
        objective { verify graphQualifiedIdentity; verify boundedProjection; verify exactAnchorMatch; verify readOnly; verify provenancePreserved; verify intentionalBoundary; }
        @EvidenceBinding { evidenceId = "components/rtg/citation_resolution/tests/test_rtg_citation_resolution_contract.py#RtgCitationResolverBoundaryVerification"; implementationScope = "DeterministicRtgCitationResolver"; }
    }
}
