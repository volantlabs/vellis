# component.rtg.evidence_bounded_synthesis

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

- Model definition: `RtgEvidenceBoundedSynthesizer`
- Lifecycle: `draft`
- Purpose: Bound untrusted semantic claims to deterministic graph-qualified evidence while owning no graph, citation, bridge, model-provider, transport, persistence, or mutable domain state.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `synthesize` | `SynthesizeEvidenceBoundedClaims` | in `request: RtgEvidenceBoundedSynthesisRequest`; out `result: RtgEvidenceBoundedSynthesisRecord` | `RtgEvidenceBoundedSynthesisInvalid` | Validate and isolate the deterministic source, skip generation without usable citations, invoke the retained generator once otherwise, then atomically validate every draft claim against the source citation catalog. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `OpenRtgEvidenceBoundedSynthesizer` | in `generator: RtgSemanticDraftGenerator`; out `synthesizer: RtgEvidenceBoundedSynthesizer` | `RtgEvidenceBoundedSynthesisInvalid` | Bind exactly one semantic draft generator without generating prose, reading graph state, or selecting a model provider. |

## Retained collaborator roles

| Role | Kind | Referenced type | Multiplicity |
|---|---|---|---|
| `generator` | `part` | `RtgSemanticDraftGenerator` | `[1]` |

## Owned state

| State feature | Type | Ownership | Meaning |
|---|---|---|---|
| — | — | — | This component owns no abstract state. |

## Action and state effects

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `synthesize` | `generator` | `dependency` | Invoke exactly the retained generator only when the deterministic source has supported reads and at least one graph-qualified citation. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| — | — | No action decomposition required at this boundary. |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.rtg.evidence_bounded_synthesis.generator_capability` | `GenerateSemanticDraft` | `generator.generate` | The generator receives an isolated read-only request copy and returns only an untrusted draft; it may use any provider but receives no graph, citation-resolver, bridge, persistence, or write capability from this component. |
| `contract.rtg.evidence_bounded_synthesis.status` | `SynthesizeEvidenceBoundedClaims` | `synthesizer.synthesize` | At least one accepted claim with no source or generator limitation yields complete; accepted claims with any limitation yield partial; no accepted claim yields no_supported_claims. |
| `contract.rtg.evidence_bounded_synthesis.source_envelope` | `SynthesizeEvidenceBoundedClaims` | `synthesizer.synthesize` | Request and source intents match exactly, source status is valid, source limitations are preserved, and the caller source remains unchanged. |
| `contract.rtg.evidence_bounded_synthesis.fail_closed_draft` | `SynthesizeEvidenceBoundedClaims` | `synthesizer.synthesize` | Every generated claim and limitation is validated before result assembly; any malformed claim, kind, text, uncertainty, citation reference, or unknown evidence identity rejects the entire draft with no partial claim result. |
| `invariant.rtg.evidence_bounded_synthesis.source_bound_claims` | `RtgEvidenceBoundedSynthesizer` | `synthesizer` | Every accepted claim cites at least one canonical (graphId, localUuid) identity present in the source citation catalog, duplicates are removed in first-use order, and result citations contain exactly the identities used by accepted claims. |
| `invariant.rtg.evidence_bounded_synthesis.cross_graph_comparison` | `RtgEvidenceBoundedSynthesizer` | `synthesizer` | Every comparison claim cites evidence from at least two distinct graph namespaces; absence of a source relationship is never transformed into a negative comparison finding. |
| `invariant.rtg.evidence_bounded_synthesis.inference_disclosure` | `RtgEvidenceBoundedSynthesizer` | `synthesizer` | Every inference claim carries non-empty uncertainty prose and still cites its graph-qualified evidence inputs. |
| `invariant.rtg.evidence_bounded_synthesis.no_entailment_claim` | `RtgEvidenceBoundedSynthesizer` | `synthesizer` | Every result reports entailmentStatus=not_verified; citation presence is structural grounding and never proof that the prose follows from the evidence. |
| `contract.rtg.evidence_bounded_synthesis.no_evidence_short_circuit` | `SynthesizeEvidenceBoundedClaims` | `synthesizer.synthesize` | A source with no supported reads or no graph-qualified citation yields no_supported_claims with an explicit limitation and does not invoke the generator. |
| `invariant.rtg.evidence_bounded_synthesis.read_only` | `RtgEvidenceBoundedSynthesizer` | `synthesizer` | Synthesis deep-isolates generator input and mutates no request, source record, citation, read, bridge, candidate, generator-owned value, graph, or external artifact. |
| `contract.rtg.evidence_bounded_synthesis.intentional_boundary` | `RtgEvidenceBoundedSynthesizer` | `synthesizer` | The component executes no graph query or MCP tool, resolves no citation, traverses or promotes no bridge, restores no snapshot, joins or merges no identities, selects no provider, proves no factual correctness, and writes no claim or fact. |
| `contract.rtg.evidence_bounded_synthesis.synthesize.failures` | `SynthesizeEvidenceBoundedClaims` | `synthesizer.synthesize` | Malformed request, source status, intent, source citation, generator result, claim, or limitation raises RtgEvidenceBoundedSynthesisInvalid, returns no partial record, and leaves caller inputs unchanged. |
| `contract.rtg.evidence_bounded_synthesis.generate.failures` | `GenerateSemanticDraft` | `generator.generate` | The logical generator capability defines no component-owned failure outcome; a provider-specific failure returns no partial draft and remains the supplied provider's error rather than fabricated evidence-bounded output. |
| `contract.rtg.evidence_bounded_synthesis.open.failures` | `OpenRtgEvidenceBoundedSynthesizer` | `openSubject` | A missing generator capability creates no synthesizer and construction performs no generation, graph access, provider selection, network call, or external side effect. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgEvidenceCitationRef` | `attribute` | `graphId: String`, `localUuid: Uuid` | Graph-qualified reference to one citation already present in the deterministic source envelope. |
| `RtgSemanticClaimDraft` | `attribute` | `text: String`, `kind: RtgSemanticClaimKind`, `citationRefs[0..*] ordered: RtgEvidenceCitationRef`, `uncertainty[0..1]: String` | Untrusted proposed prose; an inference requires uncertainty and every accepted claim requires source-bound evidence. |
| `RtgSemanticSynthesisDraft` | `attribute` | `claims[0..*] ordered: RtgSemanticClaimDraft`, `limitations[0..*] ordered: String` | Complete untrusted generator output validated atomically before any claim is accepted. |
| `RtgEvidenceBoundedSynthesisRequest` | `attribute` | `intentText: String`, `source: RtgFederatedSynthesisRecord` | One deterministic evidence envelope whose intent must exactly match intentText. |
| `RtgEvidenceBoundedClaim` | `attribute` | `text: String`, `kind: RtgSemanticClaimKind`, `citations[1..*] ordered: RtgFederatedCitation`, `uncertainty[0..1]: String` | Accepted prose carrying only canonical source citations; evidence presence bounds access but does not establish entailment. |
| `RtgEvidenceBoundedSynthesisRecord` | `attribute` | `status: RtgEvidenceBoundedSynthesisStatus`, `intentText: String`, `sourceStatus: RtgFederatedSynthesisStatus`, `claims[0..*] ordered: RtgEvidenceBoundedClaim`, `citations[0..*] ordered: RtgFederatedCitation`, `limitations[0..*] ordered: String`, `entailmentStatus: RtgEntailmentStatus` = `RtgEntailmentStatus::not_verified` | Read-only semantic result preserving source status and limitations, generator limitations, only used citations, and explicit non-verification of entailment. |
| `RtgEvidenceBoundedSynthesisInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| `RtgEvidenceBoundedSynthesisStatus` | `complete`, `partial`, `no_supported_claims` |
| `RtgSemanticClaimKind` | `summary`, `comparison`, `inference` |
| `RtgEntailmentStatus` | `not_verified` |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `SemanticDraftGeneratorContractVerification` | `GenerateSemanticDraft` | `generatorCapability`, `generateSemanticDraftFailureSemantics` | `components/rtg/evidence_bounded_synthesis/tests/test_rtg_evidence_bounded_synthesis_contract.py#SemanticDraftGeneratorContractVerification` |
| `SynthesizeEvidenceBoundedClaimsContractVerification` | `SynthesizeEvidenceBoundedClaims` | `synthesisStatus`, `sourceEnvelope`, `failClosedDraft`, `noEvidenceShortCircuit`, `synthesizeFailureSemantics` | `components/rtg/evidence_bounded_synthesis/tests/test_rtg_evidence_bounded_synthesis_contract.py#SynthesizeEvidenceBoundedClaimsContractVerification` |
| `RtgEvidenceBoundedSynthesizerBoundaryVerification` | `RtgEvidenceBoundedSynthesizer` | `sourceBoundClaims`, `crossGraphComparison`, `inferenceDisclosure`, `noEntailmentClaim`, `readOnly`, `intentionalBoundary` | `components/rtg/evidence_bounded_synthesis/tests/test_rtg_evidence_bounded_synthesis_contract.py#RtgEvidenceBoundedSynthesizerBoundaryVerification` |
| `OpenRtgEvidenceBoundedSynthesizerContractVerification` | `OpenRtgEvidenceBoundedSynthesizer` | `openRtgEvidenceBoundedSynthesizerFailureSemantics` | `components/rtg/evidence_bounded_synthesis/tests/test_rtg_evidence_bounded_synthesis_contract.py#OpenRtgEvidenceBoundedSynthesizerContractVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
