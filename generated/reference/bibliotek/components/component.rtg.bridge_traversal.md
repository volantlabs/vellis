# component.rtg.bridge_traversal

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

- Model definition: `RtgBridgeTraverser`
- Lifecycle: `draft`
- Purpose: Resolve both endpoints of one active confirmed bridge while owning no bridge, citation, graph, candidate, snapshot, query, or persistence state.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `traverse` | `TraverseBridge` | in `request: RtgBridgeTraversalRequest`; out `result: RtgBridgeTraversalRecord` | `RtgBridgeTraversalInvalid`, `RtgBridgeTraversalNotAllowed`, `RtgGraphBridgeInvalid`, `RtgGraphBridgeNotFound`, `RtgCitationResolutionInvalid` | Validate one explicit bridge identity, read that assertion once, require active status, resolve source first and target second, and derive the aggregate status without mutation. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `OpenRtgBridgeTraverser` | in `bridgeStore: RtgGraphBridge`; in `citationResolver: RtgBridgeEndpointResolver`; out `traverser: RtgBridgeTraverser` | None | Retain exactly one confirmed-bridge store and one citation resolver without reading a bridge or resolving an endpoint. |

## Retained collaborator roles

| Role | Kind | Referenced type | Multiplicity |
|---|---|---|---|
| `bridgeStore` | `part` | `RtgGraphBridge` | `[1]` |
| `citationResolver` | `part` | `RtgBridgeEndpointResolver` | `[1]` |

## Owned state

| State feature | Type | Ownership | Meaning |
|---|---|---|---|
| — | — | — | This component owns no abstract state. |

## Action and state effects

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `traverse` | — | `declared` | Copy bridge.source.graphId and bridge.source.localUuid into one graph-qualified citation request without changing the assertion. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| `traverse` | `lookupBridge: GetBridge`, `shapeSourceRequest: local`, `resolveSource: ResolveBridgeEndpoint`, `shapeTargetRequest: local`, `resolveTarget: ResolveBridgeEndpoint`, `assembleResult: local` | `first lookupBridge then shapeSourceRequest;`; `first shapeSourceRequest then resolveSource;`; `first resolveSource then shapeTargetRequest;`; `first shapeTargetRequest then resolveTarget;`; `first resolveTarget then assembleResult;` |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.rtg.bridge_traversal.result_semantics` | `TraverseBridge` | `traverser.traverse` | Resolved means both endpoints resolved; partial means exactly one resolved; unresolved means neither resolved. Not_found and unsupported details remain in their independent endpoint records. |
| `contract.rtg.bridge_traversal.sequence` | `TraverseBridge` | `traverser.traverse` | Validate bridgeId before dependencies, read exactly one assertion, reject inactive status before resolution, then resolve source once before target once; any failure returns no partial traversal record. |
| `invariant.rtg.bridge_traversal.confirmed_active_only` | `RtgBridgeTraverser` | `traverser` | Only an explicit active RtgGraphBridgeAssertion grants traversal permission; candidates and revoked assertions never do. |
| `invariant.rtg.bridge_traversal.single_bridge` | `RtgBridgeTraverser` | `traverser` | One request reads and returns exactly one bridge assertion and never expands another bridge or path. |
| `invariant.rtg.bridge_traversal.graph_qualified_endpoints` | `RtgBridgeTraverser` | `traverser` | Each endpoint reference and resolution preserve identical graphId and localUuid identity; a mismatch or unsupported resolution status is rejected as RtgBridgeTraversalInvalid. |
| `invariant.rtg.bridge_traversal.no_join` | `RtgBridgeTraverser` | `traverser` | Source and target projection records remain independent and are never merged into a cross-graph row, path, or identity. |
| `invariant.rtg.bridge_traversal.read_only` | `RtgBridgeTraverser` | `traverser` | Traversal mutates no request, assertion, resolution record, bridge or candidate state, graph state, snapshot, dependency, or external storage. |
| `contract.rtg.bridge_traversal.intentional_boundary` | `RtgBridgeTraverser` | `traverser` | The component infers, discovers, scores, promotes, rejects, revokes, or writes no bridge; executes no arbitrary query or MCP call; opens no graph storage; expands no path; and synthesizes no joined object. |
| `contract.rtg.bridge_traversal.traverse.failures` | `TraverseBridge` | `traverser.traverse` | Invalid input, inactive permission, dependency failure, or endpoint mismatch returns no partial traversal record, suppresses no required-contract error, and leaves all inputs and dependencies unchanged. |
| `contract.rtg.bridge_traversal.open.failures` | `OpenRtgBridgeTraverser` | `openSubject` | Construction performs no bridge lookup, citation resolution, graph access, query, network call, or external side effect. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgBridgeTraversalRequest` | `attribute` | `bridgeId: String` | Names exactly one confirmed bridge assertion; endpoint references, labels, candidates, and inferred matches are not substitutes. |
| `RtgBridgeTraversalEndpoint` | `attribute` | `reference: RtgGraphLocalReference`, `resolution: RtgCitationResolutionRecord` | Preserves one graph-qualified bridge endpoint beside its independently resolved bounded projection. |
| `RtgBridgeTraversalRecord` | `attribute` | `status: RtgBridgeTraversalStatus`, `bridge: RtgGraphBridgeAssertion`, `source: RtgBridgeTraversalEndpoint`, `target: RtgBridgeTraversalEndpoint` | Preserves the complete bridge assertion and separate source and target endpoint records without producing a joined row or merged identity. |
| `RtgBridgeTraversalInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgBridgeTraversalNotAllowed` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| `RtgBridgeTraversalStatus` | `resolved`, `partial`, `unresolved` |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `TraverseBridgeContractVerification` | `TraverseBridge` | `resultSemantics`, `traversalSequence`, `traverseBridgeFailureSemantics` | `components/rtg/bridge_traversal/tests/test_rtg_bridge_traversal_contract.py#TraverseBridgeContractVerification` |
| `OpenRtgBridgeTraverserContractVerification` | `OpenRtgBridgeTraverser` | `openRtgBridgeTraverserFailureSemantics` | `components/rtg/bridge_traversal/tests/test_rtg_bridge_traversal_contract.py#OpenRtgBridgeTraverserContractVerification` |
| `RtgBridgeTraverserBoundaryVerification` | `RtgBridgeTraverser` | `confirmedActiveOnly`, `singleBridge`, `graphQualifiedEndpoints`, `noJoin`, `readOnly`, `intentionalBoundary` | `components/rtg/bridge_traversal/tests/test_rtg_bridge_traversal_contract.py#RtgBridgeTraverserBoundaryVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
