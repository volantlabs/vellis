# component.rtg.federated_synthesis

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

- Model definition: `RtgFederatedSynthesizer`
- Lifecycle: `draft`
- Purpose: Produce deterministic federation evidence envelopes while owning no graph, route, bridge, candidate, query, citation resolver, semantic generator, transport, or persistence state.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `synthesize` | `SynthesizeFederatedContext` | in `request: RtgFederatedSynthesisRequest`; out `result: RtgFederatedSynthesisRecord` | `RtgFederatedSynthesisInvalid` | Validate and isolate all context, derive completion status and limitations, aggregate answer sections, and deduplicate executed-read citations by graph-qualified identity without querying, joining, or mutation. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| — | — | — | No package-level construction action. |

## Retained collaborator roles

| Role | Kind | Referenced type | Multiplicity |
|---|---|---|---|
| — | — | — | No retained collaborator roles. |

## Owned state

| State feature | Type | Ownership | Meaning |
|---|---|---|---|
| — | — | — | This component owns no abstract state. |

## Action and state effects

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `synthesize` | — | `declared` | Pure aggregation with no graph, bridge, candidate, transport, model, or external state effect. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| — | — | No action decomposition required at this boundary. |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.rtg.federated_synthesis.status` | `SynthesizeFederatedContext` | `synthesizer.synthesize` | No executed reads yields no_supported_reads. At least one executed read plus any unsupported, skipped, failed, or non-permitted candidate limitation yields partial. Executed reads with no limitations yield complete. |
| `contract.rtg.federated_synthesis.answer` | `SynthesizeFederatedContext` | `synthesizer.synthesize` | Answer reports a deterministic summary, distinct executed graph count, planned read count, confirmed bridge count, candidate-notice count, and one ordered section per supplied read without inventing graph-local facts. |
| `invariant.rtg.federated_synthesis.graph_qualified_citations` | `RtgFederatedSynthesizer` | `synthesizer` | Every citation has an identifier graphId and canonical UUID localUuid, belongs to its containing graph read namespace, and is meaningful only as that pair; raw UUIDs, labels, kinds, titles, and domain keys are never standalone identity. |
| `contract.rtg.federated_synthesis.citation_deduplication` | `SynthesizeFederatedContext` | `synthesizer.synthesize` | Only executed reads contribute result citations. Exactly one citation is emitted per canonical (graphId, localUuid) pair, ordered by that pair; the first occurrence supplies presentation label and kind. |
| `contract.rtg.federated_synthesis.bridge_context` | `SynthesizeFederatedContext` | `synthesizer.synthesize` | Every bridge context preserves one confirmed cross-graph hint with distinct graph IDs, canonical endpoint UUIDs, and finite confidence in the closed interval zero through one without traversal, joining, or identity merging. |
| `invariant.rtg.federated_synthesis.no_candidate_traversal` | `RtgFederatedSynthesizer` | `synthesizer` | Candidate notices remain separate from bridge context and evidence; every notice with traversalPermission=false appears as an ordered limitation and never grants traversal. |
| `invariant.rtg.federated_synthesis.no_hidden_facts` | `RtgFederatedSynthesizer` | `synthesizer` | Unsupported, skipped, and failed reads appear as ordered limitations with supplied notes and are never filled from another graph, bridge context, model inference, or uncited source. |
| `invariant.rtg.federated_synthesis.read_only` | `RtgFederatedSynthesizer` | `synthesizer` | Synthesis returns independent finite-JSON records and mutates no request, read, citation, bridge, candidate, graph, query, snapshot, dependency, or external artifact. |
| `contract.rtg.federated_synthesis.intentional_boundary` | `RtgFederatedSynthesizer` | `synthesizer` | The component opens no graph root, executes no query or MCP tool, restores no snapshot, resolves no citation, traverses no bridge, promotes no candidate, performs no cross-graph join, generates no semantic prose, calls no model or network, and writes no fact. |
| `contract.rtg.federated_synthesis.synthesize.failures` | `SynthesizeFederatedContext` | `synthesizer.synthesize` | Malformed identity, status, Boolean permission, endpoint namespace, confidence, text, or non-finite JSON returns no partial synthesis record and leaves all caller inputs unchanged. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgFederatedCitation` | `attribute` | `graphId: String`, `localUuid: Uuid`, `label[0..1]: String`, `kind: String` = `"record"` | Canonical source identity is graphId plus localUuid; label and kind are presentation metadata and never identity fallbacks. |
| `RtgFederatedGraphRead` | `attribute` | `graphId: String`, `status: RtgFederatedGraphReadStatus`, `queryName[0..1]: String`, `summary: JsonObject`, `citations[0..*] ordered: RtgFederatedCitation`, `notes[0..*] ordered: String` | One graph-local read attempt whose citations, when present, belong to the same graphId namespace. |
| `RtgFederatedBridgeContext` | `attribute` | `bridgeId: String`, `bridgeType: String`, `sourceGraphId: String`, `sourceLocalId: Uuid`, `targetGraphId: String`, `targetLocalId: Uuid`, `confidence: Real` | One confirmed cross-graph bridge hint with distinct graph namespaces and finite confidence from zero through one; context does not execute traversal or a join. |
| `RtgFederatedCandidateNotice` | `attribute` | `candidateId: String`, `status: String`, `traversalPermission: Boolean`, `reason: String` | Candidate or policy notice kept separate from confirmed bridge context; false traversal permission always produces a limitation. |
| `RtgFederatedSynthesisRequest` | `attribute` | `intentText: String`, `reads[0..*] ordered: RtgFederatedGraphRead`, `bridges[0..*] ordered: RtgFederatedBridgeContext`, `candidateNotices[0..*] ordered: RtgFederatedCandidateNotice` | Complete caller-supplied deterministic evidence envelope; the component performs no source reads itself. |
| `RtgFederatedSynthesisRecord` | `attribute` | `status: RtgFederatedSynthesisStatus`, `intentText: String`, `answer: JsonObject`, `citations[0..*] ordered: RtgFederatedCitation`, `reads[0..*] ordered: RtgFederatedGraphRead`, `bridges[0..*] ordered: RtgFederatedBridgeContext`, `candidateNotices[0..*] ordered: RtgFederatedCandidateNotice`, `limitations[0..*] ordered: String` | Deterministic read-only answer envelope preserving normalized input context, explicit limitations, and unique graph-qualified citations from executed reads. |
| `RtgFederatedSynthesisInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| `RtgFederatedSynthesisStatus` | `complete`, `partial`, `no_supported_reads` |
| `RtgFederatedGraphReadStatus` | `executed`, `unsupported`, `skipped`, `failed` |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `SynthesizeFederatedContextContractVerification` | `SynthesizeFederatedContext` | `synthesisStatus`, `answerEnvelope`, `citationDeduplication`, `bridgeContext`, `synthesizeFederatedContextFailureSemantics` | `components/rtg/federated_synthesis/tests/test_rtg_federated_synthesis_contract.py#SynthesizeFederatedContextContractVerification` |
| `RtgFederatedSynthesizerBoundaryVerification` | `RtgFederatedSynthesizer` | `graphQualifiedCitations`, `noCandidateTraversal`, `noHiddenFacts`, `readOnly`, `intentionalBoundary` | `components/rtg/federated_synthesis/tests/test_rtg_federated_synthesis_contract.py#RtgFederatedSynthesizerBoundaryVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
