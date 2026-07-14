# component.rtg.graph_bridge

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

- Model definition: `RtgGraphBridge`
- Lifecycle: `draft`
- Purpose: Own explicit bridge assertions and candidate review lifecycle while remaining independent of graph contents, routing, persistence, transports, identity inference, and traversal execution.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `putBridge` | `PutBridge` | in `bridge: RtgGraphBridgeDraft`; out `stored: RtgGraphBridgeAssertion` | `RtgGraphBridgeInvalid` | Normalize and validate one draft, derive its direction-sensitive identity, and create or fully replace the active assertion without inspecting either graph. |
| `getBridge` | `GetBridge` | in `bridgeId: String`; out `bridge: RtgGraphBridgeAssertion` | `RtgGraphBridgeInvalid`, `RtgGraphBridgeNotFound` | Return an independent copy of one assertion by its derived identifier. |
| `listBridges` | `ListBridges` | in `status: RtgGraphBridgeStatusFilter` = `RtgGraphBridgeStatusFilter::'all'`; out `result: RtgGraphBridgeList` | `RtgGraphBridgeInvalid` | Return independent assertion copies in ascending bridgeId order, optionally filtered by lifecycle status. |
| `findBridges` | `FindBridges` | in `reference: RtgGraphLocalReference`; in `status: RtgGraphBridgeStatusFilter` = `RtgGraphBridgeStatusFilter::active`; out `result: RtgGraphBridgeList` | `RtgGraphBridgeInvalid` | Return ordered assertions whose source or target equals the graph-qualified reference; active assertions are the default. |
| `revokeBridge` | `RevokeBridge` | in `bridgeId: String`; in `revokedAt: String`; in `revokedBy: String`; in `reason: String`; out `bridge: RtgGraphBridgeAssertion` | `RtgGraphBridgeInvalid`, `RtgGraphBridgeNotFound` | Mark one assertion revoked while preserving identity, endpoints, type, confidence, assertion metadata, and provenance. |
| `putCandidate` | `PutCandidate` | in `candidate: RtgGraphBridgeCandidateDraft`; out `stored: RtgGraphBridgeCandidate` | `RtgGraphBridgeInvalid` | Normalize and validate one proposal, derive its evidence-sensitive identity, and create or fully replace the candidate without creating an assertion. |
| `getCandidate` | `GetCandidate` | in `candidateId: String`; out `candidate: RtgGraphBridgeCandidate` | `RtgGraphBridgeInvalid`, `RtgGraphBridgeNotFound` | Return an independent copy of one candidate without changing review state. |
| `listCandidates` | `ListCandidates` | in `status: RtgGraphBridgeCandidateStatusFilter` = `RtgGraphBridgeCandidateStatusFilter::candidate_only`; out `result: RtgGraphBridgeCandidateList` | `RtgGraphBridgeInvalid` | Return independent candidate copies in ascending candidateId order; pending review candidates are the default. |
| `findCandidates` | `FindCandidates` | in `reference: RtgGraphLocalReference`; in `status: RtgGraphBridgeCandidateStatusFilter` = `RtgGraphBridgeCandidateStatusFilter::candidate_only`; out `result: RtgGraphBridgeCandidateList` | `RtgGraphBridgeInvalid` | Return ordered candidates whose source or target equals the graph-qualified reference; pending review candidates are the default. |
| `promoteCandidate` | `PromoteCandidate` | in `candidateId: String`; in `assertedAt: String`; in `assertedBy: String`; out `bridge: RtgGraphBridgeAssertion` | `RtgGraphBridgeInvalid`, `RtgGraphBridgeNotFound` | Convert exactly one candidate_only proposal into an active assertion, preserve its evidence as provenance, and record the produced bridge identity on the promoted candidate. |
| `rejectCandidate` | `RejectCandidate` | in `candidateId: String`; in `rejectedAt: String`; in `rejectedBy: String`; in `reason: String`; out `candidate: RtgGraphBridgeCandidate` | `RtgGraphBridgeInvalid`, `RtgGraphBridgeNotFound` | Mark exactly one candidate_only proposal rejected without creating or modifying any assertion. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `CreateEmptyRtgGraphBridge` | out `bridgeStore: RtgGraphBridge` | None | Return an in-memory bridge store with no assertions or candidates. |

## Retained collaborator roles

| Role | Kind | Referenced type | Multiplicity |
|---|---|---|---|
| — | — | — | No retained collaborator roles. |

## Owned state

| State feature | Type | Ownership | Meaning |
|---|---|---|---|
| `bridgeAssertions` | `RtgGraphBridgeAssertion` | `owned` | Canonical assertions keyed by derived bridgeId. |
| `bridgeCandidates` | `RtgGraphBridgeCandidate` | `owned` | Canonical review proposals keyed by derived candidateId and never included in assertion state. |

## Action and state effects

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `putBridge` | `bridgeAssertions` | `write` | Create or fully replace one valid active assertion. |
| `getBridge` | `bridgeAssertions` | `read` | Return one assertion copy without mutation. |
| `listBridges` | `bridgeAssertions` | `read` | Filter and order assertion copies without mutation. |
| `findBridges` | `bridgeAssertions` | `read` | Match graph-qualified endpoints without mutation. |
| `revokeBridge` | `bridgeAssertions` | `write` | Replace one assertion with its revoked lifecycle record. |
| `putCandidate` | `bridgeCandidates` | `write` | Create or fully replace one valid pending candidate. |
| `getCandidate` | `bridgeCandidates` | `read` | Return one candidate copy without mutation. |
| `listCandidates` | `bridgeCandidates` | `read` | Filter and order candidate copies without mutation. |
| `findCandidates` | `bridgeCandidates` | `read` | Match graph-qualified candidate endpoints without mutation. |
| `promoteCandidate` | `bridgeCandidates` | `read` | Require one existing candidate_only proposal. |
| `promoteCandidate` | `bridgeCandidates` | `write` | Record promoted status and the resulting bridge identity. |
| `promoteCandidate` | `bridgeAssertions` | `write` | Create or replace the active assertion derived from the proposal. |
| `rejectCandidate` | `bridgeCandidates` | `write` | Record rejected status and complete rejection metadata. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| — | — | No action decomposition required at this boundary. |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.rtg.graph_bridge.bridge_validity` | `PutBridge` | `bridgeStore.putBridge` | Graph and bridge type identities are non-empty identifiers; local UUIDs are concrete; endpoints use different graphIds; confidence is finite from zero through one; assertion actor/time are non-empty; provenance is non-empty; and metadata is finite JSON. |
| `contract.rtg.graph_bridge.candidate_validity` | `PutCandidate` | `bridgeStore.putCandidate` | Candidate identities and endpoints obey bridge validity; evidence and rationale are non-empty; confidence is finite from zero through one; proposal actor/time are non-empty; and metadata is finite JSON. |
| `contract.rtg.graph_bridge.put_effect` | `PutBridge` | `bridgeStore.putBridge` | Success creates or fully replaces exactly one active assertion under its derived bridgeId and returns an independent copy; rejection leaves both owned collections unchanged. |
| `contract.rtg.graph_bridge.candidate_put_effect` | `PutCandidate` | `bridgeStore.putCandidate` | Success creates or fully replaces exactly one candidate_only proposal under its derived candidateId without creating or modifying an assertion; rejection leaves both collections unchanged. |
| `contract.rtg.graph_bridge.assertion_reads` | `RtgGraphBridge` | `bridgeStore` | Get, list, and find return independent copies without mutation; list and find are ascending by bridgeId; find matches either endpoint exactly and defaults to active assertions. |
| `contract.rtg.graph_bridge.candidate_reads` | `RtgGraphBridge` | `bridgeStore` | Get, list, and find return independent copies without mutation; list and find are ascending by candidateId; find matches either endpoint exactly and defaults to candidate_only proposals. |
| `contract.rtg.graph_bridge.revocation` | `RevokeBridge` | `bridgeStore.revokeBridge` | Success preserves assertion identity and assertion-time facts, sets revoked status and complete revocation actor/time/reason, and causes default active finds to exclude it. |
| `contract.rtg.graph_bridge.candidate_review` | `RtgGraphBridge` | `bridgeStore` | Only candidate_only proposals may transition. Promotion atomically creates or replaces the corresponding active assertion and records its bridgeId; rejection records complete rejection metadata and changes no assertion. |
| `invariant.rtg.graph_bridge.graph_local_identity` | `RtgGraphBridge` | `bridgeStore` | Every endpoint, provenance entry, and evidence entry is a (graphId, localUuid) pair; raw UUID-only references are never accepted. |
| `invariant.rtg.graph_bridge.cross_graph_only` | `RtgGraphBridge` | `bridgeStore` | Every assertion and candidate has source and target in different graphs. |
| `invariant.rtg.graph_bridge.deterministic_identity` | `RtgGraphBridge` | `bridgeStore` | bridgeId is deterministic and direction-sensitive for the ordered (bridgeType, source, target) tuple. |
| `invariant.rtg.graph_bridge.candidate_identity` | `RtgGraphBridge` | `bridgeStore` | candidateId is deterministic for the ordered (bridgeType, source, target, ordered evidence) tuple. |
| `invariant.rtg.graph_bridge.provenance_required` | `RtgGraphBridge` | `bridgeStore` | Every assertion carries at least one graph-qualified provenance reference. |
| `invariant.rtg.graph_bridge.candidates_are_not_bridges` | `RtgGraphBridge` | `bridgeStore` | Candidates never appear in assertion lists, active lookups, or traversal permission until explicit successful promotion. |
| `invariant.rtg.graph_bridge.reified_metadata` | `RtgGraphBridge` | `bridgeStore` | Confidence, assertion and candidate metadata, provenance, and lifecycle metadata remain on the reified records, never graph links or endpoint references. |
| `contract.rtg.graph_bridge.intentional_boundary` | `RtgGraphBridge` | `bridgeStore` | The component opens no graph storage, validates no endpoint existence, executes no query or write, infers or merges no identity, performs no traversal or join, starts no transport, and owns no durable adapter. |
| `contract.rtg.graph_bridge.put_bridge.failures` | `PutBridge` | `bridgeStore.putBridge` | Invalid drafts expose no partial assertion or replacement. |
| `contract.rtg.graph_bridge.get_bridge.failures` | `GetBridge` | `bridgeStore.getBridge` | Malformed or missing identities do not mutate state or select a fallback assertion. |
| `contract.rtg.graph_bridge.list_bridges.failures` | `ListBridges` | `bridgeStore.listBridges` | Invalid filters return no partial list and have no state effect. |
| `contract.rtg.graph_bridge.find_bridges.failures` | `FindBridges` | `bridgeStore.findBridges` | Invalid references or filters return no partial list and have no state effect. |
| `contract.rtg.graph_bridge.revoke_bridge.failures` | `RevokeBridge` | `bridgeStore.revokeBridge` | Invalid revocation metadata and malformed or missing identities leave the assertion unchanged. |
| `contract.rtg.graph_bridge.put_candidate.failures` | `PutCandidate` | `bridgeStore.putCandidate` | Invalid drafts expose no partial candidate or replacement and never create an assertion. |
| `contract.rtg.graph_bridge.get_candidate.failures` | `GetCandidate` | `bridgeStore.getCandidate` | Malformed or missing identities do not mutate state or select a fallback candidate. |
| `contract.rtg.graph_bridge.list_candidates.failures` | `ListCandidates` | `bridgeStore.listCandidates` | Invalid filters return no partial list and have no state effect. |
| `contract.rtg.graph_bridge.find_candidates.failures` | `FindCandidates` | `bridgeStore.findCandidates` | Invalid references or filters return no partial list and have no state effect. |
| `contract.rtg.graph_bridge.promote_candidate.failures` | `PromoteCandidate` | `bridgeStore.promoteCandidate` | Invalid metadata, malformed or missing identity, or non-candidate_only state leaves both collections unchanged and creates no assertion. |
| `contract.rtg.graph_bridge.reject_candidate.failures` | `RejectCandidate` | `bridgeStore.rejectCandidate` | Invalid rejection metadata, malformed or missing identity, or non-candidate_only state leaves both collections unchanged. |
| `contract.rtg.graph_bridge.create_empty.failures` | `CreateEmptyRtgGraphBridge` | `createEmptySubject` | Construction creates no graph, storage, file, process, network, or transport side effect. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgGraphLocalReference` | `attribute` | `graphId: String`, `localUuid: Uuid` | One object identity qualified by its owning graph; localUuid has no cross-graph meaning without graphId. |
| `RtgGraphBridgeDraft` | `attribute` | `bridgeType: String`, `source: RtgGraphLocalReference`, `target: RtgGraphLocalReference`, `confidence: Real`, `assertedAt: String`, `assertedBy: String`, `provenance[1..*] ordered: RtgGraphLocalReference`, `metadata: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgGraphBridgeAssertion` | `item` | `bridgeId: String`, `bridgeType: String`, `source: RtgGraphLocalReference`, `target: RtgGraphLocalReference`, `confidence: Real`, `assertedAt: String`, `assertedBy: String`, `provenance[1..*] ordered: RtgGraphLocalReference`, `metadata: JsonObject`, `status: RtgGraphBridgeStatus` = `RtgGraphBridgeStatus::active`, `revokedAt[0..1]: String`, `revokedBy[0..1]: String`, `revocationReason[0..1]: String` | Reified, direction-sensitive cross-graph relationship with its own identity, evidence, confidence, lifecycle, and metadata. |
| `RtgGraphBridgeCandidateDraft` | `attribute` | `bridgeType: String`, `source: RtgGraphLocalReference`, `target: RtgGraphLocalReference`, `confidence: Real`, `proposedAt: String`, `proposedBy: String`, `evidence[1..*] ordered: RtgGraphLocalReference`, `rationale: String`, `metadata: JsonObject` | Defined by its typed fields and action requirements. |
| `RtgGraphBridgeCandidate` | `item` | `candidateId: String`, `bridgeType: String`, `source: RtgGraphLocalReference`, `target: RtgGraphLocalReference`, `confidence: Real`, `proposedAt: String`, `proposedBy: String`, `evidence[1..*] ordered: RtgGraphLocalReference`, `rationale: String`, `metadata: JsonObject`, `status: RtgGraphBridgeCandidateStatus` = `RtgGraphBridgeCandidateStatus::candidate_only`, `promotedBridgeId[0..1]: String`, `rejectedAt[0..1]: String`, `rejectedBy[0..1]: String`, `rejectionReason[0..1]: String` | Review proposal that grants no traversal permission until explicitly promoted. |
| `RtgGraphBridgeList` | `attribute` | `bridges[0..*] ordered: RtgGraphBridgeAssertion` | Defined by its typed fields and action requirements. |
| `RtgGraphBridgeCandidateList` | `attribute` | `candidates[0..*] ordered: RtgGraphBridgeCandidate` | Defined by its typed fields and action requirements. |
| `RtgGraphBridgeInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgGraphBridgeNotFound` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| `RtgGraphBridgeStatus` | `active`, `revoked` |
| `RtgGraphBridgeStatusFilter` | `active`, `revoked`, `all` |
| `RtgGraphBridgeCandidateStatus` | `candidate_only`, `promoted`, `rejected` |
| `RtgGraphBridgeCandidateStatusFilter` | `candidate_only`, `promoted`, `rejected`, `all` |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `PutBridgeContractVerification` | `PutBridge` | `bridgeValidity`, `putEffect`, `putBridgeFailureSemantics` | `components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#PutBridgeContractVerification` |
| `GetBridgeContractVerification` | `GetBridge` | `getBridgeFailureSemantics` | `components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#GetBridgeContractVerification` |
| `ListBridgesContractVerification` | `ListBridges` | `listBridgesFailureSemantics` | `components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#ListBridgesContractVerification` |
| `FindBridgesContractVerification` | `FindBridges` | `findBridgesFailureSemantics` | `components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#FindBridgesContractVerification` |
| `RevokeBridgeContractVerification` | `RevokeBridge` | `revocationEffect`, `revokeBridgeFailureSemantics` | `components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#RevokeBridgeContractVerification` |
| `PutCandidateContractVerification` | `PutCandidate` | `candidateValidity`, `candidatePutEffect`, `putCandidateFailureSemantics` | `components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#PutCandidateContractVerification` |
| `GetCandidateContractVerification` | `GetCandidate` | `getCandidateFailureSemantics` | `components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#GetCandidateContractVerification` |
| `ListCandidatesContractVerification` | `ListCandidates` | `listCandidatesFailureSemantics` | `components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#ListCandidatesContractVerification` |
| `FindCandidatesContractVerification` | `FindCandidates` | `findCandidatesFailureSemantics` | `components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#FindCandidatesContractVerification` |
| `PromoteCandidateContractVerification` | `PromoteCandidate` | `promoteCandidateFailureSemantics` | `components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#PromoteCandidateContractVerification` |
| `RejectCandidateContractVerification` | `RejectCandidate` | `rejectCandidateFailureSemantics` | `components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#RejectCandidateContractVerification` |
| `CreateEmptyRtgGraphBridgeContractVerification` | `CreateEmptyRtgGraphBridge` | `createEmptyRtgGraphBridgeFailureSemantics` | `components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#CreateEmptyRtgGraphBridgeContractVerification` |
| `RtgGraphBridgeBoundaryVerification` | `RtgGraphBridge` | `assertionReads`, `candidateReads`, `candidateReviewEffect`, `graphLocalIdentity`, `crossGraphOnly`, `deterministicIdentity`, `candidateIdentity`, `provenanceRequired`, `candidatesAreNotBridges`, `reifiedMetadata`, `intentionalBoundary` | `components/rtg/graph_bridge/tests/test_rtg_graph_bridge_contract.py#RtgGraphBridgeBoundaryVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
