library package BibliotekRtgGraphBridge {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;

    doc /* Draft store of explicit graph-qualified bridge assertions and separately reviewable bridge candidates. */

    enum def RtgGraphBridgeStatus { enum active; enum revoked; }
    enum def RtgGraphBridgeStatusFilter { enum active; enum revoked; enum 'all'; }
    enum def RtgGraphBridgeCandidateStatus { enum candidate_only; enum promoted; enum rejected; }
    enum def RtgGraphBridgeCandidateStatusFilter { enum candidate_only; enum promoted; enum rejected; enum 'all'; }

    attribute def RtgGraphLocalReference {
        attribute graphId : String;
        attribute localUuid : Uuid;
        doc /* One object identity qualified by its owning graph; localUuid has no cross-graph meaning without graphId. */
    }

    attribute def RtgGraphBridgeDraft {
        attribute bridgeType : String;
        attribute source : RtgGraphLocalReference;
        attribute target : RtgGraphLocalReference;
        attribute confidence : Real;
        attribute assertedAt : String;
        attribute assertedBy : String;
        attribute provenance[1..*] ordered : RtgGraphLocalReference;
        attribute 'metadata' : JsonObject;
    }

    item def RtgGraphBridgeAssertion {
        attribute bridgeId : String;
        attribute bridgeType : String;
        attribute source : RtgGraphLocalReference;
        attribute target : RtgGraphLocalReference;
        attribute confidence : Real;
        attribute assertedAt : String;
        attribute assertedBy : String;
        attribute provenance[1..*] ordered : RtgGraphLocalReference;
        attribute 'metadata' : JsonObject;
        attribute status : RtgGraphBridgeStatus default = RtgGraphBridgeStatus::active;
        attribute revokedAt[0..1] : String;
        attribute revokedBy[0..1] : String;
        attribute revocationReason[0..1] : String;
        doc /* Reified, direction-sensitive cross-graph relationship with its own identity, evidence, confidence, lifecycle, and metadata. */
    }

    attribute def RtgGraphBridgeCandidateDraft {
        attribute bridgeType : String;
        attribute source : RtgGraphLocalReference;
        attribute target : RtgGraphLocalReference;
        attribute confidence : Real;
        attribute proposedAt : String;
        attribute proposedBy : String;
        attribute evidence[1..*] ordered : RtgGraphLocalReference;
        attribute rationale : String;
        attribute 'metadata' : JsonObject;
    }

    item def RtgGraphBridgeCandidate {
        attribute candidateId : String;
        attribute bridgeType : String;
        attribute source : RtgGraphLocalReference;
        attribute target : RtgGraphLocalReference;
        attribute confidence : Real;
        attribute proposedAt : String;
        attribute proposedBy : String;
        attribute evidence[1..*] ordered : RtgGraphLocalReference;
        attribute rationale : String;
        attribute 'metadata' : JsonObject;
        attribute status : RtgGraphBridgeCandidateStatus default = RtgGraphBridgeCandidateStatus::candidate_only;
        attribute promotedBridgeId[0..1] : String;
        attribute rejectedAt[0..1] : String;
        attribute rejectedBy[0..1] : String;
        attribute rejectionReason[0..1] : String;
        doc /* Review proposal that grants no traversal permission until explicitly promoted. */
    }

    attribute def RtgGraphBridgeList { item bridges[0..*] ordered : RtgGraphBridgeAssertion; }
    attribute def RtgGraphBridgeCandidateList { item candidates[0..*] ordered : RtgGraphBridgeCandidate; }
    attribute def RtgGraphBridgeInvalid { attribute 'message' : String; }
    attribute def RtgGraphBridgeNotFound { attribute 'message' : String; }

    action def PutBridge {
        in bridge : RtgGraphBridgeDraft;
        out stored : RtgGraphBridgeAssertion;
        doc /* Normalize and validate one draft, derive its direction-sensitive identity, and create or fully replace the active assertion without inspecting either graph. */
        @FailureContract { errorIds = ("RtgGraphBridgeInvalid"); }
    }
    action def GetBridge {
        in bridgeId : String;
        out bridge : RtgGraphBridgeAssertion;
        doc /* Return an independent copy of one assertion by its derived identifier. */
        @FailureContract { errorIds = ("RtgGraphBridgeInvalid", "RtgGraphBridgeNotFound"); }
    }
    action def ListBridges {
        in status : RtgGraphBridgeStatusFilter default = RtgGraphBridgeStatusFilter::'all';
        out result : RtgGraphBridgeList;
        doc /* Return independent assertion copies in ascending bridgeId order, optionally filtered by lifecycle status. */
        @FailureContract { errorIds = ("RtgGraphBridgeInvalid"); }
    }
    action def FindBridges {
        in reference : RtgGraphLocalReference;
        in status : RtgGraphBridgeStatusFilter default = RtgGraphBridgeStatusFilter::active;
        out result : RtgGraphBridgeList;
        doc /* Return ordered assertions whose source or target equals the graph-qualified reference; active assertions are the default. */
        @FailureContract { errorIds = ("RtgGraphBridgeInvalid"); }
    }
    action def RevokeBridge {
        in bridgeId : String;
        in revokedAt : String;
        in revokedBy : String;
        in reason : String;
        out bridge : RtgGraphBridgeAssertion;
        doc /* Mark one assertion revoked while preserving identity, endpoints, type, confidence, assertion metadata, and provenance. */
        @FailureContract { errorIds = ("RtgGraphBridgeInvalid", "RtgGraphBridgeNotFound"); }
    }
    action def PutCandidate {
        in candidate : RtgGraphBridgeCandidateDraft;
        out stored : RtgGraphBridgeCandidate;
        doc /* Normalize and validate one proposal, derive its evidence-sensitive identity, and create or fully replace the candidate without creating an assertion. */
        @FailureContract { errorIds = ("RtgGraphBridgeInvalid"); }
    }
    action def GetCandidate {
        in candidateId : String;
        out candidate : RtgGraphBridgeCandidate;
        doc /* Return an independent copy of one candidate without changing review state. */
        @FailureContract { errorIds = ("RtgGraphBridgeInvalid", "RtgGraphBridgeNotFound"); }
    }
    action def ListCandidates {
        in status : RtgGraphBridgeCandidateStatusFilter default = RtgGraphBridgeCandidateStatusFilter::candidate_only;
        out result : RtgGraphBridgeCandidateList;
        doc /* Return independent candidate copies in ascending candidateId order; pending review candidates are the default. */
        @FailureContract { errorIds = ("RtgGraphBridgeInvalid"); }
    }
    action def FindCandidates {
        in reference : RtgGraphLocalReference;
        in status : RtgGraphBridgeCandidateStatusFilter default = RtgGraphBridgeCandidateStatusFilter::candidate_only;
        out result : RtgGraphBridgeCandidateList;
        doc /* Return ordered candidates whose source or target equals the graph-qualified reference; pending review candidates are the default. */
        @FailureContract { errorIds = ("RtgGraphBridgeInvalid"); }
    }
    action def PromoteCandidate {
        in candidateId : String;
        in assertedAt : String;
        in assertedBy : String;
        out bridge : RtgGraphBridgeAssertion;
        doc /* Convert exactly one candidate_only proposal into an active assertion, preserve its evidence as provenance, and record the produced bridge identity on the promoted candidate. */
        @FailureContract { errorIds = ("RtgGraphBridgeInvalid", "RtgGraphBridgeNotFound"); }
    }
    action def RejectCandidate {
        in candidateId : String;
        in rejectedAt : String;
        in rejectedBy : String;
        in reason : String;
        out candidate : RtgGraphBridgeCandidate;
        doc /* Mark exactly one candidate_only proposal rejected without creating or modifying any assertion. */
        @FailureContract { errorIds = ("RtgGraphBridgeInvalid", "RtgGraphBridgeNotFound"); }
    }

    part def <'component.rtg.graph_bridge'> RtgGraphBridge {
        doc /* Own explicit bridge assertions and candidate review lifecycle while remaining independent of graph contents, routing, persistence, transports, identity inference, and traversal execution. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::draft; owner = "humans"; }

        item bridgeAssertions[0..*] : RtgGraphBridgeAssertion { doc /* Canonical assertions keyed by derived bridgeId. */ }
        item bridgeCandidates[0..*] : RtgGraphBridgeCandidate { doc /* Canonical review proposals keyed by derived candidateId and never included in assertion state. */ }

        perform action putBridge[0..*] : PutBridge;
        perform action getBridge[0..*] : GetBridge;
        perform action listBridges[0..*] : ListBridges;
        perform action findBridges[0..*] : FindBridges;
        perform action revokeBridge[0..*] : RevokeBridge;
        perform action putCandidate[0..*] : PutCandidate;
        perform action getCandidate[0..*] : GetCandidate;
        perform action listCandidates[0..*] : ListCandidates;
        perform action findCandidates[0..*] : FindCandidates;
        perform action promoteCandidate[0..*] : PromoteCandidate;
        perform action rejectCandidate[0..*] : RejectCandidate;

        dependency putBridgeState from putBridge to bridgeAssertions { @StateAccess { kind = StateAccessKind::write; } doc /* Create or fully replace one valid active assertion. */ }
        dependency getBridgeState from getBridge to bridgeAssertions { @StateAccess { kind = StateAccessKind::read; } doc /* Return one assertion copy without mutation. */ }
        dependency listBridgeState from listBridges to bridgeAssertions { @StateAccess { kind = StateAccessKind::read; } doc /* Filter and order assertion copies without mutation. */ }
        dependency findBridgeState from findBridges to bridgeAssertions { @StateAccess { kind = StateAccessKind::read; } doc /* Match graph-qualified endpoints without mutation. */ }
        dependency revokeBridgeState from revokeBridge to bridgeAssertions { @StateAccess { kind = StateAccessKind::write; } doc /* Replace one assertion with its revoked lifecycle record. */ }
        dependency putCandidateState from putCandidate to bridgeCandidates { @StateAccess { kind = StateAccessKind::write; } doc /* Create or fully replace one valid pending candidate. */ }
        dependency getCandidateState from getCandidate to bridgeCandidates { @StateAccess { kind = StateAccessKind::read; } doc /* Return one candidate copy without mutation. */ }
        dependency listCandidateState from listCandidates to bridgeCandidates { @StateAccess { kind = StateAccessKind::read; } doc /* Filter and order candidate copies without mutation. */ }
        dependency findCandidateState from findCandidates to bridgeCandidates { @StateAccess { kind = StateAccessKind::read; } doc /* Match graph-qualified candidate endpoints without mutation. */ }
        dependency promoteCandidateRead from promoteCandidate to bridgeCandidates { @StateAccess { kind = StateAccessKind::read; } doc /* Require one existing candidate_only proposal. */ }
        dependency promoteCandidateWrite from promoteCandidate to bridgeCandidates { @StateAccess { kind = StateAccessKind::write; } doc /* Record promoted status and the resulting bridge identity. */ }
        dependency promoteBridgeWrite from promoteCandidate to bridgeAssertions { @StateAccess { kind = StateAccessKind::write; } doc /* Create or replace the active assertion derived from the proposal. */ }
        dependency rejectCandidateState from rejectCandidate to bridgeCandidates { @StateAccess { kind = StateAccessKind::write; } doc /* Record rejected status and complete rejection metadata. */ }
    }

    action def CreateEmptyRtgGraphBridge {
        out part bridgeStore : RtgGraphBridge;
        doc /* Return an in-memory bridge store with no assertions or candidates. */
        @FailureContract { errorIds = (); }
    }

    requirement <'contract.rtg.graph_bridge.bridge_validity'> bridgeValidity {
        subject operation : PutBridge;
        require constraint { doc /* Graph and bridge type identities are non-empty identifiers; local UUIDs are concrete; endpoints use different graphIds; confidence is finite from zero through one; assertion actor/time are non-empty; provenance is non-empty; and metadata is finite JSON. */ }
    }
    requirement <'contract.rtg.graph_bridge.candidate_validity'> candidateValidity {
        subject operation : PutCandidate;
        require constraint { doc /* Candidate identities and endpoints obey bridge validity; evidence and rationale are non-empty; confidence is finite from zero through one; proposal actor/time are non-empty; and metadata is finite JSON. */ }
    }
    requirement <'contract.rtg.graph_bridge.put_effect'> putEffect {
        subject operation : PutBridge;
        require constraint { doc /* Success creates or fully replaces exactly one active assertion under its derived bridgeId and returns an independent copy; rejection leaves both owned collections unchanged. */ }
    }
    requirement <'contract.rtg.graph_bridge.candidate_put_effect'> candidatePutEffect {
        subject operation : PutCandidate;
        require constraint { doc /* Success creates or fully replaces exactly one candidate_only proposal under its derived candidateId without creating or modifying an assertion; rejection leaves both collections unchanged. */ }
    }
    requirement <'contract.rtg.graph_bridge.assertion_reads'> assertionReads {
        subject bridgeStore : RtgGraphBridge;
        require constraint { doc /* Get, list, and find return independent copies without mutation; list and find are ascending by bridgeId; find matches either endpoint exactly and defaults to active assertions. */ }
    }
    requirement <'contract.rtg.graph_bridge.candidate_reads'> candidateReads {
        subject bridgeStore : RtgGraphBridge;
        require constraint { doc /* Get, list, and find return independent copies without mutation; list and find are ascending by candidateId; find matches either endpoint exactly and defaults to candidate_only proposals. */ }
    }
    requirement <'contract.rtg.graph_bridge.revocation'> revocationEffect {
        subject operation : RevokeBridge;
        require constraint { doc /* Success preserves assertion identity and assertion-time facts, sets revoked status and complete revocation actor/time/reason, and causes default active finds to exclude it. */ }
    }
    requirement <'contract.rtg.graph_bridge.candidate_review'> candidateReviewEffect {
        subject bridgeStore : RtgGraphBridge;
        require constraint { doc /* Only candidate_only proposals may transition. Promotion atomically creates or replaces the corresponding active assertion and records its bridgeId; rejection records complete rejection metadata and changes no assertion. */ }
    }

    requirement <'invariant.rtg.graph_bridge.graph_local_identity'> graphLocalIdentity { subject bridgeStore : RtgGraphBridge; require constraint { doc /* Every endpoint, provenance entry, and evidence entry is a (graphId, localUuid) pair; raw UUID-only references are never accepted. */ } }
    requirement <'invariant.rtg.graph_bridge.cross_graph_only'> crossGraphOnly { subject bridgeStore : RtgGraphBridge; require constraint { doc /* Every assertion and candidate has source and target in different graphs. */ } }
    requirement <'invariant.rtg.graph_bridge.deterministic_identity'> deterministicIdentity { subject bridgeStore : RtgGraphBridge; require constraint { doc /* bridgeId is deterministic and direction-sensitive for the ordered (bridgeType, source, target) tuple. */ } }
    requirement <'invariant.rtg.graph_bridge.candidate_identity'> candidateIdentity { subject bridgeStore : RtgGraphBridge; require constraint { doc /* candidateId is deterministic for the ordered (bridgeType, source, target, ordered evidence) tuple. */ } }
    requirement <'invariant.rtg.graph_bridge.provenance_required'> provenanceRequired { subject bridgeStore : RtgGraphBridge; require constraint { doc /* Every assertion carries at least one graph-qualified provenance reference. */ } }
    requirement <'invariant.rtg.graph_bridge.candidates_are_not_bridges'> candidatesAreNotBridges { subject bridgeStore : RtgGraphBridge; require constraint { doc /* Candidates never appear in assertion lists, active lookups, or traversal permission until explicit successful promotion. */ } }
    requirement <'invariant.rtg.graph_bridge.reified_metadata'> reifiedMetadata { subject bridgeStore : RtgGraphBridge; require constraint { doc /* Confidence, assertion and candidate metadata, provenance, and lifecycle metadata remain on the reified records, never graph links or endpoint references. */ } }
    requirement <'contract.rtg.graph_bridge.intentional_boundary'> intentionalBoundary { subject bridgeStore : RtgGraphBridge; require constraint { doc /* The component opens no graph storage, validates no endpoint existence, executes no query or write, infers or merges no identity, performs no traversal or join, starts no transport, and owns no durable adapter. */ } }

    requirement <'contract.rtg.graph_bridge.put_bridge.failures'> putBridgeFailureSemantics { subject operation : PutBridge; require constraint { doc /* Invalid drafts expose no partial assertion or replacement. */ } }
    requirement <'contract.rtg.graph_bridge.get_bridge.failures'> getBridgeFailureSemantics { subject operation : GetBridge; require constraint { doc /* Malformed or missing identities do not mutate state or select a fallback assertion. */ } }
    requirement <'contract.rtg.graph_bridge.list_bridges.failures'> listBridgesFailureSemantics { subject operation : ListBridges; require constraint { doc /* Invalid filters return no partial list and have no state effect. */ } }
    requirement <'contract.rtg.graph_bridge.find_bridges.failures'> findBridgesFailureSemantics { subject operation : FindBridges; require constraint { doc /* Invalid references or filters return no partial list and have no state effect. */ } }
    requirement <'contract.rtg.graph_bridge.revoke_bridge.failures'> revokeBridgeFailureSemantics { subject operation : RevokeBridge; require constraint { doc /* Invalid revocation metadata and malformed or missing identities leave the assertion unchanged. */ } }
    requirement <'contract.rtg.graph_bridge.put_candidate.failures'> putCandidateFailureSemantics { subject operation : PutCandidate; require constraint { doc /* Invalid drafts expose no partial candidate or replacement and never create an assertion. */ } }
    requirement <'contract.rtg.graph_bridge.get_candidate.failures'> getCandidateFailureSemantics { subject operation : GetCandidate; require constraint { doc /* Malformed or missing identities do not mutate state or select a fallback candidate. */ } }
    requirement <'contract.rtg.graph_bridge.list_candidates.failures'> listCandidatesFailureSemantics { subject operation : ListCandidates; require constraint { doc /* Invalid filters return no partial list and have no state effect. */ } }
    requirement <'contract.rtg.graph_bridge.find_candidates.failures'> findCandidatesFailureSemantics { subject operation : FindCandidates; require constraint { doc /* Invalid references or filters return no partial list and have no state effect. */ } }
    requirement <'contract.rtg.graph_bridge.promote_candidate.failures'> promoteCandidateFailureSemantics { subject operation : PromoteCandidate; require constraint { doc /* Invalid metadata, malformed or missing identity, or non-candidate_only state leaves both collections unchanged and creates no assertion. */ } }
    requirement <'contract.rtg.graph_bridge.reject_candidate.failures'> rejectCandidateFailureSemantics { subject operation : RejectCandidate; require constraint { doc /* Invalid rejection metadata, malformed or missing identity, or non-candidate_only state leaves both collections unchanged. */ } }
    requirement <'contract.rtg.graph_bridge.create_empty.failures'> createEmptyRtgGraphBridgeFailureSemantics { subject operation : CreateEmptyRtgGraphBridge; require constraint { doc /* Construction creates no graph, storage, file, process, network, or transport side effect. */ } }

    part contractContext {
        part bridgeStore : RtgGraphBridge;
        satisfy bridgeValidity by bridgeStore.putBridge;
        satisfy candidateValidity by bridgeStore.putCandidate;
        satisfy putEffect by bridgeStore.putBridge;
        satisfy candidatePutEffect by bridgeStore.putCandidate;
        satisfy assertionReads by bridgeStore;
        satisfy candidateReads by bridgeStore;
        satisfy revocationEffect by bridgeStore.revokeBridge;
        satisfy candidateReviewEffect by bridgeStore;
        satisfy graphLocalIdentity by bridgeStore;
        satisfy crossGraphOnly by bridgeStore;
        satisfy deterministicIdentity by bridgeStore;
        satisfy candidateIdentity by bridgeStore;
        satisfy provenanceRequired by bridgeStore;
        satisfy candidatesAreNotBridges by bridgeStore;
        satisfy reifiedMetadata by bridgeStore;
        satisfy intentionalBoundary by bridgeStore;
        satisfy putBridgeFailureSemantics by bridgeStore.putBridge;
        satisfy getBridgeFailureSemantics by bridgeStore.getBridge;
        satisfy listBridgesFailureSemantics by bridgeStore.listBridges;
        satisfy findBridgesFailureSemantics by bridgeStore.findBridges;
        satisfy revokeBridgeFailureSemantics by bridgeStore.revokeBridge;
        satisfy putCandidateFailureSemantics by bridgeStore.putCandidate;
        satisfy getCandidateFailureSemantics by bridgeStore.getCandidate;
        satisfy listCandidatesFailureSemantics by bridgeStore.listCandidates;
        satisfy findCandidatesFailureSemantics by bridgeStore.findCandidates;
        satisfy promoteCandidateFailureSemantics by bridgeStore.promoteCandidate;
        satisfy rejectCandidateFailureSemantics by bridgeStore.rejectCandidate;
        action createEmptySubject : CreateEmptyRtgGraphBridge;
        satisfy createEmptyRtgGraphBridgeFailureSemantics by createEmptySubject;
    }

    verification def PutBridgeContractVerification { subject operation : PutBridge; objective { verify bridgeValidity; verify putEffect; verify putBridgeFailureSemantics; } @EvidenceBinding { evidenceId = "components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#PutBridgeContractVerification"; implementationScope = "InMemoryRtgGraphBridge"; } }
    verification def GetBridgeContractVerification { subject operation : GetBridge; objective { verify getBridgeFailureSemantics; } @EvidenceBinding { evidenceId = "components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#GetBridgeContractVerification"; implementationScope = "InMemoryRtgGraphBridge"; } }
    verification def ListBridgesContractVerification { subject operation : ListBridges; objective { verify listBridgesFailureSemantics; } @EvidenceBinding { evidenceId = "components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#ListBridgesContractVerification"; implementationScope = "InMemoryRtgGraphBridge"; } }
    verification def FindBridgesContractVerification { subject operation : FindBridges; objective { verify findBridgesFailureSemantics; } @EvidenceBinding { evidenceId = "components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#FindBridgesContractVerification"; implementationScope = "InMemoryRtgGraphBridge"; } }
    verification def RevokeBridgeContractVerification { subject operation : RevokeBridge; objective { verify revocationEffect; verify revokeBridgeFailureSemantics; } @EvidenceBinding { evidenceId = "components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#RevokeBridgeContractVerification"; implementationScope = "InMemoryRtgGraphBridge"; } }
    verification def PutCandidateContractVerification { subject operation : PutCandidate; objective { verify candidateValidity; verify candidatePutEffect; verify putCandidateFailureSemantics; } @EvidenceBinding { evidenceId = "components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#PutCandidateContractVerification"; implementationScope = "InMemoryRtgGraphBridge"; } }
    verification def GetCandidateContractVerification { subject operation : GetCandidate; objective { verify getCandidateFailureSemantics; } @EvidenceBinding { evidenceId = "components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#GetCandidateContractVerification"; implementationScope = "InMemoryRtgGraphBridge"; } }
    verification def ListCandidatesContractVerification { subject operation : ListCandidates; objective { verify listCandidatesFailureSemantics; } @EvidenceBinding { evidenceId = "components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#ListCandidatesContractVerification"; implementationScope = "InMemoryRtgGraphBridge"; } }
    verification def FindCandidatesContractVerification { subject operation : FindCandidates; objective { verify findCandidatesFailureSemantics; } @EvidenceBinding { evidenceId = "components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#FindCandidatesContractVerification"; implementationScope = "InMemoryRtgGraphBridge"; } }
    verification def PromoteCandidateContractVerification { subject operation : PromoteCandidate; objective { verify promoteCandidateFailureSemantics; } @EvidenceBinding { evidenceId = "components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#PromoteCandidateContractVerification"; implementationScope = "InMemoryRtgGraphBridge"; } }
    verification def RejectCandidateContractVerification { subject operation : RejectCandidate; objective { verify rejectCandidateFailureSemantics; } @EvidenceBinding { evidenceId = "components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#RejectCandidateContractVerification"; implementationScope = "InMemoryRtgGraphBridge"; } }
    verification def CreateEmptyRtgGraphBridgeContractVerification { subject operation : CreateEmptyRtgGraphBridge; objective { verify createEmptyRtgGraphBridgeFailureSemantics; } @EvidenceBinding { evidenceId = "components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#CreateEmptyRtgGraphBridgeContractVerification"; implementationScope = "InMemoryRtgGraphBridge"; } }
    verification def RtgGraphBridgeBoundaryVerification {
        subject bridgeStore : RtgGraphBridge;
        objective { verify assertionReads; verify candidateReads; verify candidateReviewEffect; verify graphLocalIdentity; verify crossGraphOnly; verify deterministicIdentity; verify candidateIdentity; verify provenanceRequired; verify candidatesAreNotBridges; verify reifiedMetadata; verify intentionalBoundary; }
        @EvidenceBinding { evidenceId = "components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#RtgGraphBridgeBoundaryVerification"; implementationScope = "InMemoryRtgGraphBridge"; }
    }
}
