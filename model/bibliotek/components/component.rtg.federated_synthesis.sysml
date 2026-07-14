library package BibliotekRtgFederatedSynthesis {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;

    doc /* Draft stateless deterministic synthesis of graph-local read records, confirmed bridge context, candidate limitations, and graph-qualified citations. */

    enum def RtgFederatedSynthesisStatus { enum complete; enum partial; enum no_supported_reads; }
    enum def RtgFederatedGraphReadStatus { enum executed; enum unsupported; enum skipped; enum failed; }

    attribute def RtgFederatedCitation {
        attribute graphId : String;
        attribute localUuid : Uuid;
        attribute label[0..1] : String;
        attribute kind : String default = "record";
        doc /* Canonical source identity is graphId plus localUuid; label and kind are presentation metadata and never identity fallbacks. */
    }

    attribute def RtgFederatedGraphRead {
        attribute graphId : String;
        attribute status : RtgFederatedGraphReadStatus;
        attribute queryName[0..1] : String;
        attribute summary : JsonObject;
        attribute citations[0..*] ordered : RtgFederatedCitation;
        attribute notes[0..*] ordered : String;
        doc /* One graph-local read attempt whose citations, when present, belong to the same graphId namespace. */
    }

    attribute def RtgFederatedBridgeContext {
        attribute bridgeId : String;
        attribute bridgeType : String;
        attribute sourceGraphId : String;
        attribute sourceLocalId : Uuid;
        attribute targetGraphId : String;
        attribute targetLocalId : Uuid;
        attribute confidence : Real;
        doc /* One confirmed cross-graph bridge hint with distinct graph namespaces and finite confidence from zero through one; context does not execute traversal or a join. */
    }

    attribute def RtgFederatedCandidateNotice {
        attribute candidateId : String;
        attribute status : String;
        attribute traversalPermission : Boolean;
        attribute reason : String;
        doc /* Candidate or policy notice kept separate from confirmed bridge context; false traversal permission always produces a limitation. */
    }

    attribute def RtgFederatedSynthesisRequest {
        attribute intentText : String;
        attribute reads[0..*] ordered : RtgFederatedGraphRead;
        attribute bridges[0..*] ordered : RtgFederatedBridgeContext;
        attribute candidateNotices[0..*] ordered : RtgFederatedCandidateNotice;
        doc /* Complete caller-supplied deterministic evidence envelope; the component performs no source reads itself. */
    }

    attribute def RtgFederatedSynthesisRecord {
        attribute status : RtgFederatedSynthesisStatus;
        attribute intentText : String;
        attribute answer : JsonObject;
        attribute citations[0..*] ordered : RtgFederatedCitation;
        attribute reads[0..*] ordered : RtgFederatedGraphRead;
        attribute bridges[0..*] ordered : RtgFederatedBridgeContext;
        attribute candidateNotices[0..*] ordered : RtgFederatedCandidateNotice;
        attribute limitations[0..*] ordered : String;
        doc /* Deterministic read-only answer envelope preserving normalized input context, explicit limitations, and unique graph-qualified citations from executed reads. */
    }

    attribute def RtgFederatedSynthesisInvalid { attribute 'message' : String; }

    action def SynthesizeFederatedContext {
        in request : RtgFederatedSynthesisRequest;
        out result : RtgFederatedSynthesisRecord;
        doc /* Validate and isolate all context, derive completion status and limitations, aggregate answer sections, and deduplicate executed-read citations by graph-qualified identity without querying, joining, or mutation. */
        @FailureContract { errorIds = ("RtgFederatedSynthesisInvalid"); }
    }

    part def <'component.rtg.federated_synthesis'> RtgFederatedSynthesizer {
        doc /* Produce deterministic federation evidence envelopes while owning no graph, route, bridge, candidate, query, citation resolver, semantic generator, transport, or persistence state. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::draft; owner = "humans"; }

        perform action synthesize[0..*] : SynthesizeFederatedContext { doc /* Pure aggregation with no graph, bridge, candidate, transport, model, or external state effect. */ }
    }

    requirement <'contract.rtg.federated_synthesis.status'> synthesisStatus {
        subject operation : SynthesizeFederatedContext;
        require constraint { doc /* No executed reads yields no_supported_reads. At least one executed read plus any unsupported, skipped, failed, or non-permitted candidate limitation yields partial. Executed reads with no limitations yield complete. */ }
    }
    requirement <'contract.rtg.federated_synthesis.answer'> answerEnvelope {
        subject operation : SynthesizeFederatedContext;
        require constraint { doc /* Answer reports a deterministic summary, distinct executed graph count, planned read count, confirmed bridge count, candidate-notice count, and one ordered section per supplied read without inventing graph-local facts. */ }
    }
    requirement <'invariant.rtg.federated_synthesis.graph_qualified_citations'> graphQualifiedCitations {
        subject synthesizer : RtgFederatedSynthesizer;
        require constraint { doc /* Every citation has an identifier graphId and canonical UUID localUuid, belongs to its containing graph read namespace, and is meaningful only as that pair; raw UUIDs, labels, kinds, titles, and domain keys are never standalone identity. */ }
    }
    requirement <'contract.rtg.federated_synthesis.citation_deduplication'> citationDeduplication {
        subject operation : SynthesizeFederatedContext;
        require constraint { doc /* Only executed reads contribute result citations. Exactly one citation is emitted per canonical (graphId, localUuid) pair, ordered by that pair; the first occurrence supplies presentation label and kind. */ }
    }
    requirement <'contract.rtg.federated_synthesis.bridge_context'> bridgeContext {
        subject operation : SynthesizeFederatedContext;
        require constraint { doc /* Every bridge context preserves one confirmed cross-graph hint with distinct graph IDs, canonical endpoint UUIDs, and finite confidence in the closed interval zero through one without traversal, joining, or identity merging. */ }
    }
    requirement <'invariant.rtg.federated_synthesis.no_candidate_traversal'> noCandidateTraversal {
        subject synthesizer : RtgFederatedSynthesizer;
        require constraint { doc /* Candidate notices remain separate from bridge context and evidence; every notice with traversalPermission=false appears as an ordered limitation and never grants traversal. */ }
    }
    requirement <'invariant.rtg.federated_synthesis.no_hidden_facts'> noHiddenFacts {
        subject synthesizer : RtgFederatedSynthesizer;
        require constraint { doc /* Unsupported, skipped, and failed reads appear as ordered limitations with supplied notes and are never filled from another graph, bridge context, model inference, or uncited source. */ }
    }
    requirement <'invariant.rtg.federated_synthesis.read_only'> readOnly {
        subject synthesizer : RtgFederatedSynthesizer;
        require constraint { doc /* Synthesis returns independent finite-JSON records and mutates no request, read, citation, bridge, candidate, graph, query, snapshot, dependency, or external artifact. */ }
    }
    requirement <'contract.rtg.federated_synthesis.intentional_boundary'> intentionalBoundary {
        subject synthesizer : RtgFederatedSynthesizer;
        require constraint { doc /* The component opens no graph root, executes no query or MCP tool, restores no snapshot, resolves no citation, traverses no bridge, promotes no candidate, performs no cross-graph join, generates no semantic prose, calls no model or network, and writes no fact. */ }
    }
    requirement <'contract.rtg.federated_synthesis.synthesize.failures'> synthesizeFederatedContextFailureSemantics {
        subject operation : SynthesizeFederatedContext;
        require constraint { doc /* Malformed identity, status, Boolean permission, endpoint namespace, confidence, text, or non-finite JSON returns no partial synthesis record and leaves all caller inputs unchanged. */ }
    }

    part contractContext {
        part synthesizer : RtgFederatedSynthesizer;
        satisfy synthesisStatus by synthesizer.synthesize;
        satisfy answerEnvelope by synthesizer.synthesize;
        satisfy graphQualifiedCitations by synthesizer;
        satisfy citationDeduplication by synthesizer.synthesize;
        satisfy bridgeContext by synthesizer.synthesize;
        satisfy noCandidateTraversal by synthesizer;
        satisfy noHiddenFacts by synthesizer;
        satisfy readOnly by synthesizer;
        satisfy intentionalBoundary by synthesizer;
        satisfy synthesizeFederatedContextFailureSemantics by synthesizer.synthesize;
    }

    verification def SynthesizeFederatedContextContractVerification {
        subject operation : SynthesizeFederatedContext;
        objective { verify synthesisStatus; verify answerEnvelope; verify citationDeduplication; verify bridgeContext; verify synthesizeFederatedContextFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/federated_synthesis/tests/test_rtg_federated_synthesis_contract.py#SynthesizeFederatedContextContractVerification"; implementationScope = "DeterministicRtgFederatedSynthesizer"; }
    }
    verification def RtgFederatedSynthesizerBoundaryVerification {
        subject synthesizer : RtgFederatedSynthesizer;
        objective { verify graphQualifiedCitations; verify noCandidateTraversal; verify noHiddenFacts; verify readOnly; verify intentionalBoundary; }
        @EvidenceBinding { evidenceId = "components/rtg/federated_synthesis/tests/test_rtg_federated_synthesis_contract.py#RtgFederatedSynthesizerBoundaryVerification"; implementationScope = "DeterministicRtgFederatedSynthesizer"; }
    }
}
