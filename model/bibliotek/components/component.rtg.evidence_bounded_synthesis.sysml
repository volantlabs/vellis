library package BibliotekRtgEvidenceBoundedSynthesis {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import BibliotekRtgFederatedSynthesis::*;
    private import ScalarValues::*;

    doc /* Draft stateless semantic synthesis whose untrusted claims are structurally bounded to graph-qualified citations in one deterministic federated evidence envelope. */

    enum def RtgEvidenceBoundedSynthesisStatus { enum complete; enum partial; enum no_supported_claims; }
    enum def RtgSemanticClaimKind { enum summary; enum comparison; enum inference; }
    enum def RtgEntailmentStatus { enum not_verified; }

    attribute def RtgEvidenceCitationRef {
        attribute graphId : String;
        attribute localUuid : Uuid;
        doc /* Graph-qualified reference to one citation already present in the deterministic source envelope. */
    }

    attribute def RtgSemanticClaimDraft {
        attribute text : String;
        attribute kind : RtgSemanticClaimKind;
        attribute citationRefs[0..*] ordered : RtgEvidenceCitationRef;
        attribute uncertainty[0..1] : String;
        doc /* Untrusted proposed prose; an inference requires uncertainty and every accepted claim requires source-bound evidence. */
    }

    attribute def RtgSemanticSynthesisDraft {
        attribute claims[0..*] ordered : RtgSemanticClaimDraft;
        attribute limitations[0..*] ordered : String;
        doc /* Complete untrusted generator output validated atomically before any claim is accepted. */
    }

    attribute def RtgEvidenceBoundedSynthesisRequest {
        attribute intentText : String;
        attribute source : RtgFederatedSynthesisRecord;
        doc /* One deterministic evidence envelope whose intent must exactly match intentText. */
    }

    attribute def RtgEvidenceBoundedClaim {
        attribute text : String;
        attribute kind : RtgSemanticClaimKind;
        attribute citations[1..*] ordered : RtgFederatedCitation;
        attribute uncertainty[0..1] : String;
        doc /* Accepted prose carrying only canonical source citations; evidence presence bounds access but does not establish entailment. */
    }

    attribute def RtgEvidenceBoundedSynthesisRecord {
        attribute status : RtgEvidenceBoundedSynthesisStatus;
        attribute intentText : String;
        attribute sourceStatus : RtgFederatedSynthesisStatus;
        attribute claims[0..*] ordered : RtgEvidenceBoundedClaim;
        attribute citations[0..*] ordered : RtgFederatedCitation;
        attribute limitations[0..*] ordered : String;
        attribute entailmentStatus : RtgEntailmentStatus default = RtgEntailmentStatus::not_verified;
        doc /* Read-only semantic result preserving source status and limitations, generator limitations, only used citations, and explicit non-verification of entailment. */
    }

    attribute def RtgEvidenceBoundedSynthesisInvalid { attribute 'message' : String; }

    action def GenerateSemanticDraft {
        in request : RtgEvidenceBoundedSynthesisRequest;
        out draft : RtgSemanticSynthesisDraft;
        doc /* Propose untrusted claims from an isolated request copy treated as read-only; a model, deterministic algorithm, human-authored adapter, or other provider may realize this capability. */
        @FailureContract { errorIds = (); }
    }

    part def RtgSemanticDraftGenerator {
        doc /* Caller-supplied read-only capability that proposes drafts but neither validates evidence bounds nor gains graph write authority. */
        perform action generate[0..*] : GenerateSemanticDraft;
    }

    action def SynthesizeEvidenceBoundedClaims {
        in request : RtgEvidenceBoundedSynthesisRequest;
        out result : RtgEvidenceBoundedSynthesisRecord;
        doc /* Validate and isolate the deterministic source, skip generation without usable citations, invoke the retained generator once otherwise, then atomically validate every draft claim against the source citation catalog. */
        @FailureContract { errorIds = ("RtgEvidenceBoundedSynthesisInvalid"); }
    }

    part def <'component.rtg.evidence_bounded_synthesis'> RtgEvidenceBoundedSynthesizer {
        doc /* Bound untrusted semantic claims to deterministic graph-qualified evidence while owning no graph, citation, bridge, model-provider, transport, persistence, or mutable domain state. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::draft; owner = "humans"; }

        ref part generator[1] : RtgSemanticDraftGenerator { doc /* Retained caller-supplied read-only draft capability bound at construction. */ }
        perform action synthesize[0..*] : SynthesizeEvidenceBoundedClaims { doc /* Isolate source evidence, optionally read the generator, and mutate no caller, graph, bridge, provider, or external state. */ }

        dependency synthesizeGenerator from synthesize to generator { doc /* Invoke exactly the retained generator only when the deterministic source has supported reads and at least one graph-qualified citation. */ }
    }

    action def OpenRtgEvidenceBoundedSynthesizer {
        in ref generator : RtgSemanticDraftGenerator;
        out part synthesizer : RtgEvidenceBoundedSynthesizer;
        doc /* Bind exactly one semantic draft generator without generating prose, reading graph state, or selecting a model provider. */
        @FailureContract { errorIds = ("RtgEvidenceBoundedSynthesisInvalid"); }
        bind synthesizer.generator = generator;
    }

    requirement <'contract.rtg.evidence_bounded_synthesis.generator_capability'> generatorCapability {
        subject operation : GenerateSemanticDraft;
        require constraint { doc /* The generator receives an isolated read-only request copy and returns only an untrusted draft; it may use any provider but receives no graph, citation-resolver, bridge, persistence, or write capability from this component. */ }
    }
    requirement <'contract.rtg.evidence_bounded_synthesis.status'> synthesisStatus {
        subject operation : SynthesizeEvidenceBoundedClaims;
        require constraint { doc /* At least one accepted claim with no source or generator limitation yields complete; accepted claims with any limitation yield partial; no accepted claim yields no_supported_claims. */ }
    }
    requirement <'contract.rtg.evidence_bounded_synthesis.source_envelope'> sourceEnvelope {
        subject operation : SynthesizeEvidenceBoundedClaims;
        require constraint { doc /* Request and source intents match exactly, source status is valid, source limitations are preserved, and the caller source remains unchanged. */ }
    }
    requirement <'contract.rtg.evidence_bounded_synthesis.fail_closed_draft'> failClosedDraft {
        subject operation : SynthesizeEvidenceBoundedClaims;
        require constraint { doc /* Every generated claim and limitation is validated before result assembly; any malformed claim, kind, text, uncertainty, citation reference, or unknown evidence identity rejects the entire draft with no partial claim result. */ }
    }
    requirement <'invariant.rtg.evidence_bounded_synthesis.source_bound_claims'> sourceBoundClaims {
        subject synthesizer : RtgEvidenceBoundedSynthesizer;
        require constraint { doc /* Every accepted claim cites at least one canonical (graphId, localUuid) identity present in the source citation catalog, duplicates are removed in first-use order, and result citations contain exactly the identities used by accepted claims. */ }
    }
    requirement <'invariant.rtg.evidence_bounded_synthesis.cross_graph_comparison'> crossGraphComparison {
        subject synthesizer : RtgEvidenceBoundedSynthesizer;
        require constraint { doc /* Every comparison claim cites evidence from at least two distinct graph namespaces; absence of a source relationship is never transformed into a negative comparison finding. */ }
    }
    requirement <'invariant.rtg.evidence_bounded_synthesis.inference_disclosure'> inferenceDisclosure {
        subject synthesizer : RtgEvidenceBoundedSynthesizer;
        require constraint { doc /* Every inference claim carries non-empty uncertainty prose and still cites its graph-qualified evidence inputs. */ }
    }
    requirement <'invariant.rtg.evidence_bounded_synthesis.no_entailment_claim'> noEntailmentClaim {
        subject synthesizer : RtgEvidenceBoundedSynthesizer;
        require constraint { doc /* Every result reports entailmentStatus=not_verified; citation presence is structural grounding and never proof that the prose follows from the evidence. */ }
    }
    requirement <'contract.rtg.evidence_bounded_synthesis.no_evidence_short_circuit'> noEvidenceShortCircuit {
        subject operation : SynthesizeEvidenceBoundedClaims;
        require constraint { doc /* A source with no supported reads or no graph-qualified citation yields no_supported_claims with an explicit limitation and does not invoke the generator. */ }
    }
    requirement <'invariant.rtg.evidence_bounded_synthesis.read_only'> readOnly {
        subject synthesizer : RtgEvidenceBoundedSynthesizer;
        require constraint { doc /* Synthesis deep-isolates generator input and mutates no request, source record, citation, read, bridge, candidate, generator-owned value, graph, or external artifact. */ }
    }
    requirement <'contract.rtg.evidence_bounded_synthesis.intentional_boundary'> intentionalBoundary {
        subject synthesizer : RtgEvidenceBoundedSynthesizer;
        require constraint { doc /* The component executes no graph query or MCP tool, resolves no citation, traverses or promotes no bridge, restores no snapshot, joins or merges no identities, selects no provider, proves no factual correctness, and writes no claim or fact. */ }
    }
    requirement <'contract.rtg.evidence_bounded_synthesis.synthesize.failures'> synthesizeFailureSemantics {
        subject operation : SynthesizeEvidenceBoundedClaims;
        require constraint { doc /* Malformed request, source status, intent, source citation, generator result, claim, or limitation raises RtgEvidenceBoundedSynthesisInvalid, returns no partial record, and leaves caller inputs unchanged. */ }
    }
    requirement <'contract.rtg.evidence_bounded_synthesis.generate.failures'> generateSemanticDraftFailureSemantics {
        subject operation : GenerateSemanticDraft;
        require constraint { doc /* The logical generator capability defines no component-owned failure outcome; a provider-specific failure returns no partial draft and remains the supplied provider's error rather than fabricated evidence-bounded output. */ }
    }
    requirement <'contract.rtg.evidence_bounded_synthesis.open.failures'> openRtgEvidenceBoundedSynthesizerFailureSemantics {
        subject operation : OpenRtgEvidenceBoundedSynthesizer;
        require constraint { doc /* A missing generator capability creates no synthesizer and construction performs no generation, graph access, provider selection, network call, or external side effect. */ }
    }

    part contractContext {
        part synthesizer : RtgEvidenceBoundedSynthesizer;
        part generator : RtgSemanticDraftGenerator;
        satisfy generatorCapability by generator.generate;
        satisfy generateSemanticDraftFailureSemantics by generator.generate;
        satisfy synthesisStatus by synthesizer.synthesize;
        satisfy sourceEnvelope by synthesizer.synthesize;
        satisfy failClosedDraft by synthesizer.synthesize;
        satisfy sourceBoundClaims by synthesizer;
        satisfy crossGraphComparison by synthesizer;
        satisfy inferenceDisclosure by synthesizer;
        satisfy noEntailmentClaim by synthesizer;
        satisfy noEvidenceShortCircuit by synthesizer.synthesize;
        satisfy readOnly by synthesizer;
        satisfy intentionalBoundary by synthesizer;
        satisfy synthesizeFailureSemantics by synthesizer.synthesize;
        action openSubject : OpenRtgEvidenceBoundedSynthesizer;
        satisfy openRtgEvidenceBoundedSynthesizerFailureSemantics by openSubject;
    }

    verification def SemanticDraftGeneratorContractVerification {
        subject operation : GenerateSemanticDraft;
        objective { verify generatorCapability; verify generateSemanticDraftFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/evidence_bounded_synthesis/tests/test_rtg_evidence_bounded_synthesis_contract.py#SemanticDraftGeneratorContractVerification"; implementationScope = "ReferenceSemanticDraftGenerator"; }
    }
    verification def SynthesizeEvidenceBoundedClaimsContractVerification {
        subject operation : SynthesizeEvidenceBoundedClaims;
        objective { verify synthesisStatus; verify sourceEnvelope; verify failClosedDraft; verify noEvidenceShortCircuit; verify synthesizeFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/evidence_bounded_synthesis/tests/test_rtg_evidence_bounded_synthesis_contract.py#SynthesizeEvidenceBoundedClaimsContractVerification"; implementationScope = "EvidenceBoundedRtgSynthesizer"; }
    }
    verification def RtgEvidenceBoundedSynthesizerBoundaryVerification {
        subject synthesizer : RtgEvidenceBoundedSynthesizer;
        objective { verify sourceBoundClaims; verify crossGraphComparison; verify inferenceDisclosure; verify noEntailmentClaim; verify readOnly; verify intentionalBoundary; }
        @EvidenceBinding { evidenceId = "components/rtg/evidence_bounded_synthesis/tests/test_rtg_evidence_bounded_synthesis_contract.py#RtgEvidenceBoundedSynthesizerBoundaryVerification"; implementationScope = "EvidenceBoundedRtgSynthesizer"; }
    }
    verification def OpenRtgEvidenceBoundedSynthesizerContractVerification {
        subject operation : OpenRtgEvidenceBoundedSynthesizer;
        objective { verify openRtgEvidenceBoundedSynthesizerFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/evidence_bounded_synthesis/tests/test_rtg_evidence_bounded_synthesis_contract.py#OpenRtgEvidenceBoundedSynthesizerContractVerification"; implementationScope = "EvidenceBoundedRtgSynthesizer.open"; }
    }
}
