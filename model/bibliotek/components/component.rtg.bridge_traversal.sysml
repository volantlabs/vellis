library package BibliotekRtgBridgeTraversal {
    private import SoftwareComponentModeling::*;
    private import BibliotekRtgGraphBridge::*;
    private import BibliotekRtgCitationResolution::*;
    private import ScalarValues::*;

    doc /* Draft stateless traversal of one explicit active confirmed bridge through two independent bounded citation resolutions. */

    enum def RtgBridgeTraversalStatus { enum resolved; enum partial; enum unresolved; }

    attribute def RtgBridgeTraversalRequest {
        attribute bridgeId : String;
        doc /* Names exactly one confirmed bridge assertion; endpoint references, labels, candidates, and inferred matches are not substitutes. */
    }
    attribute def RtgBridgeTraversalEndpoint {
        attribute reference : RtgGraphLocalReference;
        attribute resolution : RtgCitationResolutionRecord;
        doc /* Preserves one graph-qualified bridge endpoint beside its independently resolved bounded projection. */
    }
    attribute def RtgBridgeTraversalRecord {
        attribute status : RtgBridgeTraversalStatus;
        item bridge : RtgGraphBridgeAssertion;
        attribute source : RtgBridgeTraversalEndpoint;
        attribute target : RtgBridgeTraversalEndpoint;
        doc /* Preserves the complete bridge assertion and separate source and target endpoint records without producing a joined row or merged identity. */
    }
    attribute def RtgBridgeTraversalInvalid { attribute 'message' : String; }
    attribute def RtgBridgeTraversalNotAllowed { attribute 'message' : String; }

    action def TraverseBridge {
        in request : RtgBridgeTraversalRequest;
        out result : RtgBridgeTraversalRecord;
        doc /* Validate one explicit bridge identity, read that assertion once, require active status, resolve source first and target second, and derive the aggregate status without mutation. */
        @FailureContract { errorIds = ("RtgBridgeTraversalInvalid", "RtgBridgeTraversalNotAllowed", "RtgGraphBridgeInvalid", "RtgGraphBridgeNotFound", "RtgCitationResolutionInvalid"); }
    }

    action def ResolveBridgeEndpoint :> ResolveCitation {
        doc /* Narrow bridge-traversal dependency contract for one graph-qualified citation resolution. */
    }
    part def RtgBridgeEndpointResolver {
        doc /* Read-only endpoint-resolution capability supplied by component.rtg.citation_resolution. */
        perform action resolve[0..*] : ResolveBridgeEndpoint;
    }

    part def <'component.rtg.bridge_traversal'> RtgBridgeTraverser {
        doc /* Resolve both endpoints of one active confirmed bridge while owning no bridge, citation, graph, candidate, snapshot, query, or persistence state. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::draft; owner = "humans"; }

        ref part bridgeStore[1] : RtgGraphBridge {
            doc /* Retained confirmed-bridge read provider supplied at construction. */
            perform traverse.lookupBridge;
        }
        ref part citationResolver[1] : RtgBridgeEndpointResolver {
            doc /* Retained bounded graph-local citation resolver supplied at construction. */
            perform traverse.resolveSource;
            perform traverse.resolveTarget;
        }
        perform action traverse[0..*] : TraverseBridge {
            action lookupBridge : GetBridge {
                in bridgeId redefines GetBridge::bridgeId = traverse.request.bridgeId;
                out bridge redefines GetBridge::bridge;
            }
            action shapeSourceRequest {
                in bridge : RtgGraphBridgeAssertion = lookupBridge.bridge;
                out request : RtgCitationResolutionRequest;
                doc /* Copy bridge.source.graphId and bridge.source.localUuid into one graph-qualified citation request without changing the assertion. */
            }
            action resolveSource : ResolveBridgeEndpoint {
                in request redefines ResolveBridgeEndpoint::request = shapeSourceRequest.request;
                out result redefines ResolveBridgeEndpoint::result;
            }
            action shapeTargetRequest {
                in bridge : RtgGraphBridgeAssertion = lookupBridge.bridge;
                out request : RtgCitationResolutionRequest;
                doc /* Copy bridge.target.graphId and bridge.target.localUuid into one graph-qualified citation request without changing the assertion. */
            }
            action resolveTarget : ResolveBridgeEndpoint {
                in request redefines ResolveBridgeEndpoint::request = shapeTargetRequest.request;
                out result redefines ResolveBridgeEndpoint::result;
            }
            action assembleResult {
                in bridge : RtgGraphBridgeAssertion = lookupBridge.bridge;
                in sourceResolution : RtgCitationResolutionRecord = resolveSource.result;
                in targetResolution : RtgCitationResolutionRecord = resolveTarget.result;
                out result : RtgBridgeTraversalRecord = traverse.result;
                doc /* Reject either identity mismatch; otherwise preserve independent endpoint records and report resolved for two resolved endpoints, partial for exactly one, or unresolved for neither. */
            }
            first lookupBridge then shapeSourceRequest;
            first shapeSourceRequest then resolveSource;
            first resolveSource then shapeTargetRequest;
            first shapeTargetRequest then resolveTarget;
            first resolveTarget then assembleResult;
        }
    }

    action def OpenRtgBridgeTraverser {
        in ref bridgeStore : RtgGraphBridge;
        in ref citationResolver : RtgBridgeEndpointResolver;
        out part traverser : RtgBridgeTraverser;
        doc /* Retain exactly one confirmed-bridge store and one citation resolver without reading a bridge or resolving an endpoint. */
        @FailureContract { errorIds = (); }
        bind traverser.bridgeStore = bridgeStore;
        bind traverser.citationResolver = citationResolver;
    }

    requirement <'contract.rtg.bridge_traversal.result_semantics'> resultSemantics { subject operation : TraverseBridge; require constraint { doc /* Resolved means both endpoints resolved; partial means exactly one resolved; unresolved means neither resolved. Not_found and unsupported details remain in their independent endpoint records. */ } }
    requirement <'contract.rtg.bridge_traversal.sequence'> traversalSequence { subject operation : TraverseBridge; require constraint { doc /* Validate bridgeId before dependencies, read exactly one assertion, reject inactive status before resolution, then resolve source once before target once; any failure returns no partial traversal record. */ } }
    requirement <'invariant.rtg.bridge_traversal.confirmed_active_only'> confirmedActiveOnly { subject traverser : RtgBridgeTraverser; require constraint { doc /* Only an explicit active RtgGraphBridgeAssertion grants traversal permission; candidates and revoked assertions never do. */ } }
    requirement <'invariant.rtg.bridge_traversal.single_bridge'> singleBridge { subject traverser : RtgBridgeTraverser; require constraint { doc /* One request reads and returns exactly one bridge assertion and never expands another bridge or path. */ } }
    requirement <'invariant.rtg.bridge_traversal.graph_qualified_endpoints'> graphQualifiedEndpoints { subject traverser : RtgBridgeTraverser; require constraint { doc /* Each endpoint reference and resolution preserve identical graphId and localUuid identity; a mismatch or unsupported resolution status is rejected as RtgBridgeTraversalInvalid. */ } }
    requirement <'invariant.rtg.bridge_traversal.no_join'> noJoin { subject traverser : RtgBridgeTraverser; require constraint { doc /* Source and target projection records remain independent and are never merged into a cross-graph row, path, or identity. */ } }
    requirement <'invariant.rtg.bridge_traversal.read_only'> readOnly { subject traverser : RtgBridgeTraverser; require constraint { doc /* Traversal mutates no request, assertion, resolution record, bridge or candidate state, graph state, snapshot, dependency, or external storage. */ } }
    requirement <'contract.rtg.bridge_traversal.intentional_boundary'> intentionalBoundary { subject traverser : RtgBridgeTraverser; require constraint { doc /* The component infers, discovers, scores, promotes, rejects, revokes, or writes no bridge; executes no arbitrary query or MCP call; opens no graph storage; expands no path; and synthesizes no joined object. */ } }
    requirement <'contract.rtg.bridge_traversal.traverse.failures'> traverseBridgeFailureSemantics { subject operation : TraverseBridge; require constraint { doc /* Invalid input, inactive permission, dependency failure, or endpoint mismatch returns no partial traversal record, suppresses no required-contract error, and leaves all inputs and dependencies unchanged. */ } }
    requirement <'contract.rtg.bridge_traversal.open.failures'> openRtgBridgeTraverserFailureSemantics { subject operation : OpenRtgBridgeTraverser; require constraint { doc /* Construction performs no bridge lookup, citation resolution, graph access, query, network call, or external side effect. */ } }

    part contractContext {
        part traverser : RtgBridgeTraverser;
        satisfy resultSemantics by traverser.traverse;
        satisfy traversalSequence by traverser.traverse;
        satisfy confirmedActiveOnly by traverser;
        satisfy singleBridge by traverser;
        satisfy graphQualifiedEndpoints by traverser;
        satisfy noJoin by traverser;
        satisfy readOnly by traverser;
        satisfy intentionalBoundary by traverser;
        satisfy traverseBridgeFailureSemantics by traverser.traverse;
        action openSubject : OpenRtgBridgeTraverser;
        satisfy openRtgBridgeTraverserFailureSemantics by openSubject;
    }

    verification def TraverseBridgeContractVerification {
        subject operation : TraverseBridge;
        objective { verify resultSemantics; verify traversalSequence; verify traverseBridgeFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/bridge_traversal/tests/test_rtg_bridge_traversal_contract.py#TraverseBridgeContractVerification"; implementationScope = "DeterministicRtgBridgeTraverser"; }
    }
    verification def OpenRtgBridgeTraverserContractVerification {
        subject operation : OpenRtgBridgeTraverser;
        objective { verify openRtgBridgeTraverserFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/bridge_traversal/tests/test_rtg_bridge_traversal_contract.py#OpenRtgBridgeTraverserContractVerification"; implementationScope = "DeterministicRtgBridgeTraverser"; }
    }
    verification def RtgBridgeTraverserBoundaryVerification {
        subject traverser : RtgBridgeTraverser;
        objective { verify confirmedActiveOnly; verify singleBridge; verify graphQualifiedEndpoints; verify noJoin; verify readOnly; verify intentionalBoundary; }
        @EvidenceBinding { evidenceId = "components/rtg/bridge_traversal/tests/test_rtg_bridge_traversal_contract.py#RtgBridgeTraverserBoundaryVerification"; implementationScope = "DeterministicRtgBridgeTraverser"; }
    }
}
