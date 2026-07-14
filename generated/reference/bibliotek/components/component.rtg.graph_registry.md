# component.rtg.graph_registry

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

- Model definition: `RtgGraphRegistry`
- Lifecycle: `draft`
- Purpose: Own graph descriptors and deterministic routing decisions while remaining independent of graph contents, execution, transport lifecycle, authorization, and bridge state.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `putGraph` | `PutGraph` | in `graph: RtgGraphDescriptor`; out `stored: RtgGraphDescriptor` | `RtgGraphRegistryInvalid` | Normalize, validate, and create or fully replace one descriptor by graphId without probing storage or endpoints. |
| `listGraphs` | `ListGraphs` | out `result: RtgGraphList` | None | Return canonical descriptor copies in ascending graphId order. |
| `getGraph` | `GetGraph` | in `graphId: String`; out `graph: RtgGraphDescriptor` | `RtgGraphRegistryInvalid`, `RtgGraphNotFound` | Return a canonical copy of the descriptor named by normalized graphId. |
| `compileIntent` | `CompileIntent` | in `intent: RtgGraphIntent`; out `route: RtgGraphRouteRecord` | `RtgGraphRegistryInvalid`, `RtgGraphNotFound` | Rank deterministic candidate descriptors; explicit targets win, unambiguous high-confidence reads may auto-select, and writes without explicit targets never select. |
| `compileFederatedIntent` | `CompileFederatedIntent` | in `intent: RtgGraphFederatedIntent`; out `plan: RtgGraphFederatedPlan` | `RtgGraphRegistryInvalid`, `RtgGraphNotFound` | Produce ordered graph-local advisory steps without executing queries, joining results, resolving identity, or authorizing writes. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `CreateEmptyRtgGraphRegistry` | out `registry: RtgGraphRegistry` | None | Return an in-memory registry with no graph descriptors. |

## Retained collaborator roles

| Role | Kind | Referenced type | Multiplicity |
|---|---|---|---|
| — | — | — | No retained collaborator roles. |

## Owned state

| State feature | Type | Ownership | Meaning |
|---|---|---|---|
| `descriptors` | `RtgGraphDescriptor` | `owned` | Canonical in-memory descriptors keyed by normalized graphId; repository file formats remain adapter concerns. |

## Action and state effects

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `putGraph` | `descriptors` | `write` | Atomically create or fully replace one valid descriptor. |
| `listGraphs` | `descriptors` | `read` | Return ordered descriptor copies without exposing mutable owned state. |
| `getGraph` | `descriptors` | `read` | Resolve one normalized graph identity without mutation. |
| `compileIntent` | `descriptors` | `read` | Rank candidates from descriptor vocabulary without graph-local calls. |
| `compileFederatedIntent` | `descriptors` | `read` | Compile independent graph-local steps without executing or joining them. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| — | — | No action decomposition required at this boundary. |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.rtg.graph_registry.descriptor_validity` | `PutGraph` | `registry.putGraph` | Descriptor identity and required text are non-empty; graphId and optional serverName are identifiers; domains are non-empty and sequences contain no duplicate normalized values; metadata is finite JSON; HTTP endpoint hints include a host and valid TCP port while paths start with slash. |
| `contract.rtg.graph_registry.put_effect` | `PutGraph` | `registry.putGraph` | Success stores exactly one normalized descriptor under graphId, fully replaces any prior descriptor with that identity, returns an independent copy, and leaves other descriptors unchanged; rejection leaves registry state unchanged. |
| `contract.rtg.graph_registry.read_effects` | `RtgGraphRegistry` | `registry` | Listing is ascending by graphId and get resolves one normalized identity; both return independent copies and never mutate descriptors. |
| `contract.rtg.graph_registry.route_compilation` | `CompileIntent` | `registry.compileIntent` | Explicit existing targetGraphId selects exactly that graph. Otherwise deterministic scoring uses request text, domain hints, and tag hints; only one non-tied read candidate at or above the fixed confidence threshold may auto-select. |
| `contract.rtg.graph_registry.federated_planning` | `CompileFederatedIntent` | `registry.compileFederatedIntent` | Explicit targetGraphIds preserve caller order. Inferred reads include every positive-scoring candidate in deterministic rank order. Write and admin plans remain non-executable and all steps retain graph-local identity. |
| `invariant.rtg.graph_registry.unique_graph_ids` | `RtgGraphRegistry` | `registry` | At most one canonical descriptor exists for each normalized graphId. |
| `invariant.rtg.graph_registry.deterministic_listing` | `RtgGraphRegistry` | `registry` | List and route outputs are deterministic for the same registry state and normalized intent. |
| `invariant.rtg.graph_registry.no_implicit_write_target` | `RtgGraphRegistry` | `registry` | A write or admin intent without an explicit target never selects a graph or yields an executable federated plan. |
| `invariant.rtg.graph_registry.route_records_are_advisory` | `RtgGraphRegistry` | `registry` | Routing mutates no graph, starts no MCP server, grants no authorization, proves no freshness, and executes no graph-local query. |
| `invariant.rtg.graph_registry.cross_graph_identity_is_explicit` | `RtgGraphRegistry` | `registry` | Graph-local identifiers are meaningful only with graphId; registry behavior never treats raw UUIDs, labels, or domain keys as global identity and never merges graph results. |
| `contract.rtg.graph_registry.intentional_boundary` | `RtgGraphRegistry` | `registry` | The component does not open storage, inspect graph contents or validation state, run transports, execute federation capabilities, authorize access, resolve bridges, or own a durable registry file. |
| `contract.rtg.graph_registry.put_graph.failures` | `PutGraph` | `registry.putGraph` | Invalid descriptors expose no partial replacement and leave all descriptors unchanged. |
| `contract.rtg.graph_registry.list_graphs.failures` | `ListGraphs` | `registry.listGraphs` | Listing has no state effect and returns no mutable alias to owned descriptors. |
| `contract.rtg.graph_registry.get_graph.failures` | `GetGraph` | `registry.getGraph` | Invalid or unknown graph identities do not mutate registry state or select a fallback graph. |
| `contract.rtg.graph_registry.compile_intent.failures` | `CompileIntent` | `registry.compileIntent` | Malformed intents and unknown explicit targets do not mutate descriptors or invoke any graph-local capability. |
| `contract.rtg.graph_registry.compile_federated_intent.failures` | `CompileFederatedIntent` | `registry.compileFederatedIntent` | Malformed intents or any unknown explicit target produce no partial plan, state mutation, graph-local call, or joined result. |
| `contract.rtg.graph_registry.create_empty.failures` | `CreateEmptyRtgGraphRegistry` | `createEmptySubject` | Construction creates no storage, process, network, graph, or registry-file side effect. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgGraphMcpEndpoint` | `attribute` | `transport: RtgGraphMcpTransport`, `host[0..1]: String`, `port[0..1]: Integer`, `path: String` = `"/mcp"`, `serverName[0..1]: String` | Local MCP launch or client-configuration hint; it is not a live transport handle. |
| `RtgGraphDescriptor` | `item` | `graphId: String`, `title: String`, `storageRoot: String`, `sqlDatabasePath: String`, `authority: String`, `writePolicy: String`, `domains[1..*] ordered: String`, `tags[0..*] ordered: String`, `mcpEndpoint[0..1]: RtgGraphMcpEndpoint`, `metadata: JsonObject` | Declarative identity, routing vocabulary, authority guidance, local storage pointers, and optional endpoint metadata for one independently owned graph monograph. |
| `RtgGraphIntent` | `attribute` | `operation: RtgGraphOperation`, `text: String`, `targetGraphId[0..1]: String`, `domainHints[0..*] ordered: String`, `tagHints[0..*] ordered: String` | Defined by its typed fields and action requirements. |
| `RtgGraphRouteCandidate` | `attribute` | `graphId: String`, `score: Real`, `reasons[0..*] ordered: String` | Defined by its typed fields and action requirements. |
| `RtgGraphRouteRecord` | `attribute` | `intent: RtgGraphIntent`, `candidates[0..*] ordered: RtgGraphRouteCandidate`, `selectedGraphId[0..1]: String`, `requiresConfirmation: Boolean`, `reason: String` | Defined by its typed fields and action requirements. |
| `RtgGraphFederatedIntent` | `attribute` | `operation: RtgGraphOperation`, `text: String`, `targetGraphIds[0..*] ordered: String`, `domainHints[0..*] ordered: String`, `tagHints[0..*] ordered: String` | Defined by its typed fields and action requirements. |
| `RtgGraphFederatedPlanStep` | `attribute` | `graphId: String`, `operation: RtgGraphOperation`, `intentText: String`, `score: Real`, `reasons[0..*] ordered: String` | Defined by its typed fields and action requirements. |
| `RtgGraphFederatedPlan` | `attribute` | `intent: RtgGraphFederatedIntent`, `steps[0..*] ordered: RtgGraphFederatedPlanStep`, `requiresConfirmation: Boolean`, `executable: Boolean`, `reason: String` | Defined by its typed fields and action requirements. |
| `RtgGraphList` | `attribute` | `graphs[0..*] ordered: RtgGraphDescriptor` | Defined by its typed fields and action requirements. |
| `RtgGraphRegistryInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RtgGraphNotFound` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| `RtgGraphOperation` | `read`, `write`, `admin` |
| `RtgGraphMcpTransport` | `http`, `stdio` |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `PutGraphContractVerification` | `PutGraph` | `descriptorValidity`, `putEffect`, `putGraphFailureSemantics` | `components/rtg/graph_registry/tests/test_rtg_graph_registry_contract.py#PutGraphContractVerification` |
| `ListGraphsContractVerification` | `ListGraphs` | `listGraphsFailureSemantics` | `components/rtg/graph_registry/tests/test_rtg_graph_registry_contract.py#ListGraphsContractVerification` |
| `GetGraphContractVerification` | `GetGraph` | `getGraphFailureSemantics` | `components/rtg/graph_registry/tests/test_rtg_graph_registry_contract.py#GetGraphContractVerification` |
| `CompileIntentContractVerification` | `CompileIntent` | `routeCompilation`, `compileIntentFailureSemantics` | `components/rtg/graph_registry/tests/test_rtg_graph_registry_contract.py#CompileIntentContractVerification` |
| `CompileFederatedIntentContractVerification` | `CompileFederatedIntent` | `federatedPlanning`, `compileFederatedIntentFailureSemantics` | `components/rtg/graph_registry/tests/test_rtg_graph_registry_contract.py#CompileFederatedIntentContractVerification` |
| `CreateEmptyRtgGraphRegistryContractVerification` | `CreateEmptyRtgGraphRegistry` | `createEmptyRtgGraphRegistryFailureSemantics` | `components/rtg/graph_registry/tests/test_rtg_graph_registry_contract.py#CreateEmptyRtgGraphRegistryContractVerification` |
| `RtgGraphRegistryBoundaryVerification` | `RtgGraphRegistry` | `readEffects`, `uniqueGraphIds`, `deterministicListing`, `noImplicitWriteTarget`, `routeRecordsAreAdvisory`, `crossGraphIdentityIsExplicit`, `intentionalBoundary` | `components/rtg/graph_registry/tests/test_rtg_graph_registry_contract.py#RtgGraphRegistryBoundaryVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
